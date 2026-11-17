import json
import hashlib
import csv
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from tracetrust.generator import generate_dataset
from tracetrust.models import CanonicalTraceabilityEvent, EventType, Finding, FindingSeverity, SnapshotManifest
from tracetrust.reconciliation import load_events, reconcile
from tracetrust.rules import run_rules
from tracetrust.trust_score import calculate_trust_score
from tracetrust.trust_score import calculate_all_lots
from tracetrust.graph import project_graph, traverse
from tracetrust.anomaly import anomaly_findings, detect_anomalies
from tracetrust.evaluation import evaluate
from tracetrust.ingestion import FileSystemSnapshotReader
from tracetrust.pipeline import run_pipeline
from tracetrust.neo4j import export_cypher


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

    def test_snapshot_reader_accepts_canonical_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate_dataset(root, lots=1, seed=7)
            event = load_events(root / "gold" / "events.jsonl")[0].model_dump(mode="json")
            csv_path = root / "events.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=event.keys())
                writer.writeheader()
                row = dict(event)
                for field in ("input_lots", "output_lots", "evidence_refs", "raw_payload"):
                    row[field] = json.dumps(row[field])
                writer.writerow(row)
            digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            manifest = {
                "snapshot_id": event["snapshot_id"], "source_system": "synthetic_tracop",
                "extracted_at": "2026-01-01T00:00:00Z", "schema_version": "1.0.0",
                "source_schema": {"database_engine": "synthetic", "migration_ids": ["demo-001"]},
                "exporter_version": "test", "anonymization": {
                    "profile": "synthetic-strict", "names_removed": True, "phones_removed": True,
                    "actor_ids_pseudonymized": True, "precise_locations_removed": True, "media_refs_removed": True,
                }, "files": [{"path": "events.csv", "format": "csv", "row_count": 1, "sha256": digest}],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            bundle = FileSystemSnapshotReader().read(root)
            self.assertEqual(len(bundle.events), 1)

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

    def test_trust_score_exposes_six_factors_and_penalizes_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(directory, lots=10, seed=42)
            gold = load_events(Path(directory, "gold", "events.jsonl"))
            observed = load_events(Path(directory, "observed", "events.jsonl"))
            matches = reconcile(gold, observed)
            findings = run_rules(gold + observed, matches)
            assessment = calculate_trust_score("lot-00010", observed, matches, findings)
            self.assertEqual(len(assessment.factors), 6)
            self.assertLess(assessment.score, 100)
            self.assertEqual(assessment.critical_penalties, [])
            self.assertEqual(round(sum(f.weight for f in assessment.factors), 6), 1.0)

    def test_graph_projection_supports_genealogy_and_impact_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(directory, lots=2, seed=7)
            gold = load_events(Path(directory, "gold", "events.jsonl"))
            observed = load_events(Path(directory, "observed", "events.jsonl"))
            matches = reconcile(gold, observed)
            findings = run_rules(gold + observed, matches)
            assessments = calculate_all_lots(observed, matches, findings)
            artifact = project_graph(observed, matches, findings, assessments)
            self.assertGreaterEqual(len(artifact.nodes), 10)
            self.assertTrue(any(edge.relation == "reconciles_with" for edge in artifact.edges))
            node_ids = {node.id for node in artifact.nodes}
            self.assertTrue(all(edge.source in node_ids and edge.target in node_ids for edge in artifact.edges))
            lineage = traverse(artifact, "lot:observed-7:lot-00001", direction="ancestors")
            impact = traverse(artifact, "lot:observed-7:lot-00001", direction="descendants")
            self.assertTrue(any(node["node_type"] == "event" for node in lineage["nodes"]))
            self.assertTrue(any(node["node_type"] == "event" for node in impact["nodes"]))

    def test_anomaly_detector_returns_reproducible_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(directory, lots=10, seed=42)
            gold = load_events(Path(directory, "gold", "events.jsonl"))
            observed = load_events(Path(directory, "observed", "events.jsonl"))
            matches = reconcile(gold, observed)
            observations_a = detect_anomalies(observed, matches, random_state=42)
            observations_b = detect_anomalies(observed, matches, random_state=42)
            self.assertEqual([item.model_dump() for item in observations_a], [item.model_dump() for item in observations_b])
            self.assertEqual(len(observations_a), 20)
            self.assertTrue(all(len(item.features) == 6 for item in observations_a))
            self.assertEqual(len(anomaly_findings(observed, observations_a)), sum(item.is_anomaly for item in observations_a))

    def test_evaluation_reports_ground_truth_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            ground_truth = generate_dataset(directory, lots=4, seed=7)
            gold = load_events(Path(directory, "gold", "events.jsonl"))
            observed = load_events(Path(directory, "observed", "events.jsonl"))
            matches = reconcile(gold, observed)
            findings = run_rules(gold + observed, matches)
            report = evaluate(ground_truth, matches, findings)
            self.assertEqual(report.metrics["reconciliation_f1"], 1.0)
            self.assertEqual(report.metrics["finding_recall"], 1.0)

            false_positive = Finding(
                finding_id="false-positive", rule_id="test_rule", severity=FindingSeverity.LOW,
                snapshot_id="observed-7", entity_ids=["lot-999"], source_event_ids=["unexpected-event"],
                values={}, explanation="synthetic false positive", algorithm_version="test",
            )
            report_with_false_positive = evaluate(ground_truth, matches, findings + [false_positive])
            self.assertLess(report_with_false_positive.metrics["finding_precision"], 1.0)

    def test_pipeline_runs_all_stages_and_writes_coherent_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(directory, lots=4, seed=7)
            summary = run_pipeline(directory)
            self.assertEqual(summary["matches"], 8)
            self.assertEqual(summary["trust_assessments"], 4)
            self.assertTrue(Path(directory, "pipeline_summary.json").is_file())
            self.assertTrue(Path(directory, "trace_graph.json").is_file())
            self.assertTrue(Path(directory, "evaluation.json").is_file())
            self.assertTrue(Path(directory, "benchmarks.json").is_file())
            self.assertTrue(Path(directory, "calibration.json").is_file())

    def test_neo4j_export_preserves_all_graph_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(directory, lots=2, seed=7)
            run_pipeline(directory)
            graph_path = Path(directory, "trace_graph.json")
            output = Path(directory, "trace_graph.cypher")
            from tracetrust.models import TraceGraphArtifact
            artifact = TraceGraphArtifact.model_validate_json(graph_path.read_text(encoding="utf-8"))
            export_cypher(artifact, output)
            cypher = output.read_text(encoding="utf-8")
            self.assertIn("UNWIND $nodes AS node", cypher)
            self.assertIn("RECONCILES_WITH", cypher)
            self.assertIn("properties_json", cypher)


if __name__ == "__main__":
    unittest.main()
