"""Reproducible gold/observed data generator for MVP evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import CanonicalTraceabilityEvent, EventType, SnapshotManifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _event(
    *, snapshot_id: str, event_id: str, source_record_id: str,
    event_type: EventType, timestamp: datetime, actor: str,
    organization: str, input_lots: list[str], output_lots: list[str],
    quantity: float, evidence: bool = True,
) -> CanonicalTraceabilityEvent:
    raw_timestamp = timestamp.isoformat().replace("+00:00", "Z")
    evidence_refs = []
    if evidence:
        evidence_refs.append({
            "source_system": "synthetic_evidence",
            "source_record_id": f"evidence-{event_id}",
            "snapshot_id": snapshot_id,
            "evidence_type": "delivery_receipt",
        })
    return CanonicalTraceabilityEvent(
        event_id=event_id, source_system="synthetic_tracop",
        source_record_id=source_record_id, snapshot_id=snapshot_id,
        event_type=event_type, timestamp=timestamp,
        original_timestamp=raw_timestamp, actor=actor,
        organization=organization, input_lots=input_lots,
        output_lots=output_lots, quantity=quantity,
        original_quantity=f"{quantity:.2f}", unit="kg",
        location="municipality_demo", evidence_refs=evidence_refs,
        raw_payload={"event_type": event_type.value, "quantity": f"{quantity:.2f}",
                     "unit": "kg", "actor": actor, "organization": organization},
    )


def _rebind_snapshot(event: CanonicalTraceabilityEvent, snapshot_id: str) -> CanonicalTraceabilityEvent:
    """Copy an event and every nested evidence reference into a snapshot."""
    evidence_refs = [ref.model_copy(update={"snapshot_id": snapshot_id}) for ref in event.evidence_refs]
    return event.model_copy(update={"snapshot_id": snapshot_id, "evidence_refs": evidence_refs})


def generate_dataset(
    output_dir: str | Path, *, lots: int = 10, seed: int = 42,
    discrepancy_rate: float = 0.2, missing_evidence_rate: float = 0.1,
) -> dict[str, Any]:
    """Generate deterministic gold and observed JSONL snapshots.

    The observed set is a controlled perturbation of gold. Perturbations are
    recorded explicitly so evaluation can compare findings against ground truth.
    """
    if lots < 1:
        raise ValueError("lots must be positive")
    if not 0 <= discrepancy_rate <= 1 or not 0 <= missing_evidence_rate <= 1:
        raise ValueError("perturbation rates must be between 0 and 1")

    rng = random.Random(seed)
    root = Path(output_dir)
    gold_dir, observed_dir = root / "gold", root / "observed"
    gold_dir.mkdir(parents=True, exist_ok=True)
    observed_dir.mkdir(parents=True, exist_ok=True)
    base_time = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    gold_snapshot, observed_snapshot = f"gold-{seed}", f"observed-{seed}"
    gold_events: list[CanonicalTraceabilityEvent] = []
    observed_events: list[CanonicalTraceabilityEvent] = []
    perturbations: list[dict[str, Any]] = []
    expected_event_matches: list[dict[str, str]] = []

    for index in range(1, lots + 1):
        lot_id, quantity = f"lot-{index:05d}", float(rng.randint(450, 700))
        produced_at = base_time + timedelta(hours=index * 3)
        received_at = produced_at + timedelta(hours=8)
        production = _event(
            snapshot_id=gold_snapshot, event_id=f"evt-prod-{index:05d}",
            source_record_id=f"producer-record-{index:05d}",
            event_type=EventType.PRODUCTION, timestamp=produced_at,
            actor=f"actor-producer-{index:03d}", organization="org-producers-demo",
            input_lots=[], output_lots=[lot_id], quantity=quantity,
        )
        receipt = _event(
            snapshot_id=gold_snapshot, event_id=f"evt-receive-{index:05d}",
            source_record_id=f"receiver-record-{index:05d}",
            event_type=EventType.RECEIPT, timestamp=received_at,
            actor="actor-receiver-001", organization="org-collection-demo",
            input_lots=[lot_id], output_lots=[lot_id], quantity=quantity,
        )
        gold_events.extend([production, receipt])
        expected_event_matches.extend([
            {"left_event_id": production.event_id, "right_event_id": production.event_id},
            {"left_event_id": receipt.event_id, "right_event_id": receipt.event_id},
        ])
        observed_production = _rebind_snapshot(production, observed_snapshot)
        observed_receipt = _rebind_snapshot(receipt, observed_snapshot)
        if rng.random() < discrepancy_rate:
            delta = float(rng.choice([-50, -40, 40, 50]))
            observed_quantity = max(0, quantity + delta)
            observed_receipt = observed_receipt.model_copy(update={
                "quantity": observed_quantity,
                "original_quantity": f"{observed_quantity:.2f}",
                "raw_payload": {**observed_receipt.raw_payload, "quantity_perturbed": True},
            })
            perturbations.append({"type": "quantity_discrepancy",
                                  "event_id": observed_receipt.event_id,
                                  "expected_quantity": quantity,
                                  "observed_quantity": observed_quantity})
        if rng.random() < missing_evidence_rate:
            observed_receipt = observed_receipt.model_copy(update={"evidence_refs": []})
            perturbations.append({"type": "missing_evidence", "event_id": observed_receipt.event_id})
        observed_events.extend([observed_production, observed_receipt])

    for directory, snapshot_id, events in ((gold_dir, gold_snapshot, gold_events),
                                            (observed_dir, observed_snapshot, observed_events)):
        events_path = directory / "events.jsonl"
        _write_jsonl(events_path, [event.model_dump(mode="json") for event in events])
        manifest = SnapshotManifest(
            snapshot_id=snapshot_id, source_system="synthetic_tracop",
            extracted_at=datetime.now(timezone.utc), schema_version="1.0.0",
            source_schema={"database_engine": "synthetic", "migration_ids": ["demo-001"]},
            exporter_version="tracetrust-generator-0.1.0",
            anonymization={"profile": "synthetic-strict", "names_removed": True,
                           "phones_removed": True, "actor_ids_pseudonymized": True,
                           "precise_locations_removed": True, "media_refs_removed": True},
            files=[{"path": "events.jsonl", "format": "jsonl",
                    "row_count": len(events), "sha256": _sha256(events_path)}],
        )
        (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    ground_truth = {"seed": seed, "lots": lots,
                    "gold_snapshot_id": gold_snapshot,
                    "observed_snapshot_id": observed_snapshot,
                    "expected_record_matches": lots * 2,
        "expected_event_matches": expected_event_matches,
                    "perturbations": perturbations}
    (root / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    return ground_truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--lots", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--discrepancy-rate", type=float, default=0.2)
    parser.add_argument("--missing-evidence-rate", type=float, default=0.1)
    args = parser.parse_args()
    print(json.dumps(generate_dataset(args.output_dir, lots=args.lots, seed=args.seed,
                                       discrepancy_rate=args.discrepancy_rate,
                                       missing_evidence_rate=args.missing_evidence_rate), indent=2))


if __name__ == "__main__":
    main()
