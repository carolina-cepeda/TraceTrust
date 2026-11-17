"""Generate a richer multi-stage TraceTrust scenario for the visual demo."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .generator import _event, _rebind_snapshot, _sha256, _write_jsonl
from .models import EventType, SnapshotManifest


def generate_complex_dataset(output_dir: str | Path, *, lots: int = 12, seed: int = 84) -> dict[str, Any]:
    """Create a deterministic chain: production → receipt → process → ship → pack → delivery."""
    if lots < 2:
        raise ValueError("lots must be at least 2 for the complex scenario")
    rng = random.Random(seed)
    root = Path(output_dir)
    gold_dir, observed_dir = root / "gold", root / "observed"
    gold_dir.mkdir(parents=True, exist_ok=True)
    observed_dir.mkdir(parents=True, exist_ok=True)
    gold_snapshot, observed_snapshot = f"gold-{seed}", f"observed-{seed}"
    base = datetime(2026, 2, 1, 6, tzinfo=timezone.utc)
    gold, observed, perturbations, expected = [], [], [], []
    for index in range(1, lots + 1):
        source = f"lot-{index:05d}"
        processed = f"lot-{index:05d}-processed"
        packaged = f"lot-{index:05d}-packaged"
        quantity = float(rng.randint(520, 840))
        stages = [
            ("production", EventType.PRODUCTION, [], [source], quantity, 0),
            ("receipt", EventType.RECEIPT, [source], [source], quantity, 4),
            ("processing", EventType.TRANSFORMATION, [source], [processed], quantity * .94, 10),
            ("shipping", EventType.TRANSFER, [processed], [processed], quantity * .94, 14),
            ("packaging", EventType.TRANSFORMATION, [processed], [packaged], quantity * .91, 20),
            ("delivery", EventType.RECEIPT, [packaged], [packaged], quantity * .91, 27),
        ]
        for stage, event_type, inputs, outputs, amount, hours in stages:
            event_id = f"evt-{stage}-{index:05d}"
            event = _event(
                snapshot_id=gold_snapshot, event_id=event_id,
                source_record_id=f"complex-{stage}-{index:05d}", event_type=event_type,
                timestamp=base + timedelta(hours=index * 30 + hours),
                actor=f"actor-{stage}-{index:03d}", organization=f"org-{stage}-demo",
                input_lots=inputs, output_lots=outputs, quantity=round(amount, 2),
            )
            gold.append(event)
            expected.append({"left_event_id": event_id, "right_event_id": event_id})
            observed_event = _rebind_snapshot(event, observed_snapshot)
            if stage == "shipping" and index % 4 == 0:
                altered = round(event.quantity + 55, 2)
                observed_event = observed_event.model_copy(update={
                    "quantity": altered, "original_quantity": f"{altered:.2f}",
                    "raw_payload": {**observed_event.raw_payload, "quantity_perturbed": True},
                })
                perturbations.append({"type": "quantity_discrepancy", "event_id": event_id,
                                      "expected_quantity": event.quantity, "observed_quantity": altered})
            if stage in {"processing", "delivery"} and index % 5 == 0:
                observed_event = observed_event.model_copy(update={"evidence_refs": []})
                perturbations.append({"type": "missing_evidence", "event_id": event_id})
            observed.append(observed_event)

    for directory, snapshot_id, events in ((gold_dir, gold_snapshot, gold), (observed_dir, observed_snapshot, observed)):
        path = directory / "events.jsonl"
        _write_jsonl(path, [event.model_dump(mode="json") for event in events])
        manifest = SnapshotManifest(
            snapshot_id=snapshot_id, source_system="synthetic_tracop",
            extracted_at=datetime.now(timezone.utc), schema_version="1.0.0",
            source_schema={"database_engine": "synthetic", "migration_ids": ["complex-demo-001"]},
            exporter_version="tracetrust-complex-generator-0.1.0",
            anonymization={"profile": "synthetic-strict", "names_removed": True,
                           "phones_removed": True, "actor_ids_pseudonymized": True,
                           "precise_locations_removed": True, "media_refs_removed": True},
            files=[{"path": "events.jsonl", "format": "jsonl", "row_count": len(events),
                    "sha256": _sha256(path)}],
        )
        (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    truth = {"seed": seed, "lots": lots, "profile": "complex", "gold_snapshot_id": gold_snapshot,
             "observed_snapshot_id": observed_snapshot, "expected_record_matches": len(gold),
             "expected_event_matches": expected, "perturbations": perturbations}
    (root / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    return truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--lots", type=int, default=12)
    parser.add_argument("--seed", type=int, default=84)
    args = parser.parse_args()
    print(json.dumps(generate_complex_dataset(args.output_dir, lots=args.lots, seed=args.seed), indent=2))


if __name__ == "__main__":
    main()
