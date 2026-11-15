import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from tracetrust.generator import generate_dataset
from tracetrust.models import CanonicalTraceabilityEvent, EventType, SnapshotManifest
from tracetrust.reconciliation import load_events, reconcile
from tracetrust.rules import run_rules


class ContractTests(unittest.TestCase):
    def test_canonical_event_preserves_raw_payload(self):
        event = CanonicalTraceabilityEvent(
            event_id="evt-1", source_system="demo", source_record_id="row-1",
            snapshot_id="snap-1", event_type=EventType.PRODUCTION,
            timestamp="2026-01-01T00:00:00Z", original_timestamp="2026-01-01T00:00:00Z",
            actor="actor-1", organization="org-1", output_lots=["lot-1"],
            quantity=100, original_quantity="100 kg", unit="kg",
            location="municipality_demo", raw_payload={"legacy_quantity": "100"},
        )
        self.assertEqual(event.raw_payload["legacy_quantity"], "100")

    def test_manifest_rejects_non_anonymized_export(self):
        with self.assertRaises(ValidationError):
            SnapshotManifest(
                snapshot_id="snap-1", source_system="demo",
                extracted_at="2026-01-01T00:00:00Z", schema_version="1.0.0",
                source_schema={"database_engine": "demo", "migration_ids": ["m1"]},
                exporter_version="test",
                anonymization={"profile": "unsafe", "names_removed": False}, files=[],
            )

    def test_generator_is_reproducible_and_manifest_hash_matches(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            result_a = generate_dataset(first, lots=4, seed=7)
            result_b = generate_dataset(second, lots=4, seed=7)
            self.assertEqual(result_a, result_b)
            self.assertEqual(
                Path(first, "gold", "events.jsonl").read_text(encoding="utf-8"),
                Path(second, "gold", "events.jsonl").read_text(encoding="utf-8"),
            )
            observed = [json.loads(line) for line in Path(first, "observed", "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(ref["snapshot_id"] == "observed-7" for event in observed for ref in event["evidence_refs"]))
            manifest = json.loads(Path(first, "gold", "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["files"][0]["row_count"], 8)
            self.assertEqual(len(result_a["perturbations"]), 2)

    def test_reconciliation_matches_events_and_exposes_components(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(directory, lots=4, seed=7, discrepancy_rate=1, missing_evidence_rate=0)
            gold = load_events(Path(directory, "gold", "events.jsonl"))
            observed = load_events(Path(directory, "observed", "events.jsonl"))
            results = reconcile(gold, observed)
            self.assertEqual(len(results), 8)
            self.assertTrue(all(result.status.value == "match" for result in results))
            self.assertTrue(all(result.relation_kind.value == "RECORDED" for result in results))
            quantity_result = next(result for result in results if "receive" in result.left_event_id)
            self.assertLess(quantity_result.score, 1.0)
            self.assertEqual(len(quantity_result.components), 6)

    def test_reconciliation_can_require_manual_review(self):
        left = CanonicalTraceabilityEvent(
            event_id="left", source_system="a", source_record_id="record-a",
            snapshot_id="snap-a", event_type=EventType.RECEIPT,
            timestamp="2026-01-01T00:00:00Z", original_timestamp="2026-01-01T00:00:00Z",
            actor="actor-a", organization="org-a", input_lots=["lot-a"], output_lots=["lot-a"],
            quantity=100, original_quantity="100", unit="kg", location="loc-a", raw_payload={},
        )
        right = left.model_copy(update={
            "event_id": "right", "source_record_id": "record-b", "snapshot_id": "snap-b",
            "input_lots": ["lot-b"], "output_lots": ["lot-b"], "organization": "org-a",
            "timestamp": left.timestamp + timedelta(hours=24), "quantity": 500,
        })
        results = reconcile([left], [right])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status.value, "review")

    def test_rules_find_quantity_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(directory, lots=10, seed=42)
            gold = load_events(Path(directory, "gold", "events.jsonl"))
            observed = load_events(Path(directory, "observed", "events.jsonl"))
            matches = reconcile(gold, observed)
            findings = run_rules(gold + observed, matches)
            rule_ids = {finding.rule_id for finding in findings}
            self.assertIn("quantity_compatibility", rule_ids)
            self.assertIn("required_evidence", rule_ids)
            self.assertTrue(all(finding.algorithm_version == "rules-v1" for finding in findings))

    def test_rules_detect_temporal_and_orphan_lot_errors(self):
        production = CanonicalTraceabilityEvent(
            event_id="prod", source_system="demo", source_record_id="prod",
            snapshot_id="snap", event_type=EventType.PRODUCTION,
            timestamp="2026-01-02T00:00:00Z", original_timestamp="2026-01-02T00:00:00Z",
            actor="producer", organization="org", output_lots=["lot-1"], quantity=100,
            original_quantity="100", unit="kg", location="loc", raw_payload={},
        )
        receipt = production.model_copy(update={
            "event_id": "receipt", "source_record_id": "receipt",
            "event_type": EventType.RECEIPT, "timestamp": production.timestamp - timedelta(hours=1),
            "input_lots": ["lot-1"], "output_lots": ["lot-1"],
            "evidence_refs": [],
        })
        orphan = receipt.model_copy(update={
            "event_id": "orphan", "source_record_id": "orphan",
            "input_lots": ["lot-missing"], "output_lots": ["lot-missing"],
        })
        findings = run_rules([production, receipt, orphan])
        self.assertIn("orphan_lot_reference", {finding.rule_id for finding in findings})
        self.assertIn("required_evidence", {finding.rule_id for finding in findings})


if __name__ == "__main__":
    unittest.main()
