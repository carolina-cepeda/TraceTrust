"""Generate a robust adversarial scenario with several traceability failures."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from .complex_demo import generate_complex_dataset
from .generator import _sha256, _write_jsonl
from .models import SnapshotManifest
from .reconciliation import load_events


def generate_robust_dataset(output_dir: str | Path, *, lots: int = 16, seed: int = 126) -> dict:
    """Build the complex chain and add temporal, lineage, evidence and source drift defects."""
    root = Path(output_dir)
    truth = generate_complex_dataset(root, lots=lots, seed=seed)
    gold = load_events(root / "gold" / "events.jsonl")
    observed = load_events(root / "observed" / "events.jsonl")
    by_id = {event.event_id: event for event in gold}
    perturbations = list(truth["perturbations"])

    # 1) A receipt arrives before its production event.
    temporal_id = "evt-receipt-00003"
    temporal = next(event for event in observed if event.event_id == temporal_id)
    production_time = by_id["evt-production-00003"].timestamp
    observed[observed.index(temporal)] = temporal.model_copy(update={
        "timestamp": production_time - timedelta(hours=2),
        "original_timestamp": (production_time - timedelta(hours=2)).isoformat(),
        "raw_payload": {**temporal.raw_payload, "temporal_perturbed": True},
    })
    perturbations.append({"type": "temporal_sequence", "event_id": temporal_id})

    # 2) Processing references a lot with no observable origin.
    orphan_id = "evt-processing-00006"
    orphan = next(event for event in observed if event.event_id == orphan_id)
    observed[observed.index(orphan)] = orphan.model_copy(update={
        "input_lots": [*orphan.input_lots, "lot-missing-00006"],
        "raw_payload": {**orphan.raw_payload, "orphan_reference": True},
    })
    perturbations.append({"type": "orphan_lot_reference", "event_id": orphan_id})

    # 3) The record exists but its organization drifted between exports.
    drift_id = "evt-shipping-00010"
    drift = next(event for event in observed if event.event_id == drift_id)
    observed[observed.index(drift)] = drift.model_copy(update={
        "organization": "org-unknown-external",
        "raw_payload": {**drift.raw_payload, "organization_drift": True},
    })
    perturbations.append({"type": "organization_drift", "event_id": drift_id})

    events_path = root / "observed" / "events.jsonl"
    _write_jsonl(events_path, [event.model_dump(mode="json") for event in observed])
    manifest_path = root / "observed" / "manifest.json"
    manifest = SnapshotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    files = [item.model_copy(update={"row_count": len(observed), "sha256": _sha256(events_path)})
             for item in manifest.files]
    manifest_path.write_text(manifest.model_copy(update={"files": files}).model_dump_json(indent=2), encoding="utf-8")
    truth["profile"] = "robust-adversarial"
    truth["perturbations"] = perturbations
    (root / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    return truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--lots", type=int, default=16)
    parser.add_argument("--seed", type=int, default=126)
    args = parser.parse_args()
    print(json.dumps(generate_robust_dataset(args.output_dir, lots=args.lots, seed=args.seed), indent=2))


if __name__ == "__main__":
    main()
