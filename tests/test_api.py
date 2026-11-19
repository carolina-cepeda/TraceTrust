import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tracetrust.api import create_app
from tracetrust.generator import generate_dataset
from tracetrust.graph import project_graph
from tracetrust.models import AnonymizationPolicy, SourceSchema
from tracetrust.reconciliation import load_events, reconcile
from tracetrust.rules import run_rules
from tracetrust.storage import persist_analysis
from tracetrust.trust_score import calculate_all_lots


class ApiTests(unittest.TestCase):
    def test_trackup_ingestion_persists_analyzes_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate_dataset(root, lots=1, seed=11)
            event = load_events(root / "observed" / "events.jsonl")[0]
            payload = event.model_dump(mode="json")
            payload["snapshot_id"] = "trackup-11"
            payload["source_system"] = "trackup"
            payload["event_id"] = "trackup-event-11"
            payload["source_record_id"] = "lot:lot-00001"

            request = {
                "snapshot_id": "trackup-11",
                "source_system": "trackup",
                "source_schema": {"database_engine": "postgresql", "migration_ids": ["0010_ordering_schema"]},
                "anonymization": AnonymizationPolicy(
                    profile="strict", names_removed=True, phones_removed=True,
                    actor_ids_pseudonymized=True, precise_locations_removed=True, media_refs_removed=True,
                ).model_dump(),
                "outbox_events": [{
                    "id": "outbox-11", "aggregate": "lot:lot-00001", "type": "TraceabilityEventRecorded",
                    "payload": {"canonical_event": payload},
                    "created_at": "2026-11-19T12:00:00Z",
                }],
            }
            client = TestClient(create_app(str(root)))
            first = client.post("/api/v1/ingest/trackup", json=request)
            self.assertEqual(first.status_code, 202)
            self.assertEqual(first.json()["accepted"], 1)
            duplicate = client.post("/api/v1/ingest/trackup", json=request)
            self.assertEqual(duplicate.status_code, 202)
            self.assertEqual(duplicate.json()["duplicates"], 1)
            self.assertEqual(client.get("/api/v1/snapshots/trackup-11").status_code, 200)
            self.assertTrue((root / "snapshots" / "trackup-11" / "trace_graph.json").is_file())

            unsupported = {**request, "snapshot_id": "trackup-unsupported", "outbox_events": [{
                **request["outbox_events"][0], "id": "outbox-unsupported",
                "type": "LotPublished", "payload": {"lotId": "lot-00001"},
            }]}
            rejected = client.post("/api/v1/ingest/trackup", json=unsupported)
            self.assertEqual(rejected.status_code, 422)

    def test_http_api_exposes_snapshot_lineage_findings_and_trust(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate_dataset(root, lots=2, seed=7)
            gold = load_events(root / "gold" / "events.jsonl")
            observed = load_events(root / "observed" / "events.jsonl")
            matches = reconcile(gold, observed)
            findings = run_rules(gold + observed, matches)
            assessments = calculate_all_lots(observed, matches, findings)
            (root / "reconciliation.jsonl").write_text("".join(m.model_dump_json() + "\n" for m in matches), encoding="utf-8")
            (root / "findings.jsonl").write_text("".join(f.model_dump_json() + "\n" for f in findings), encoding="utf-8")
            (root / "trust_scores.jsonl").write_text("".join(a.model_dump_json() + "\n" for a in assessments), encoding="utf-8")
            (root / "trace_graph.json").write_text(project_graph(observed, matches, findings, assessments).model_dump_json(), encoding="utf-8")

            client = TestClient(create_app(str(root)))
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/ready").json()["status"], "ready")
            self.assertEqual(client.get("/snapshots/observed-7").json()["lot_count"], 2)
            self.assertEqual(len(client.get("/snapshots").json()["items"]), 1)
            self.assertEqual(len(client.get("/lots/observed-7").json()["items"]), 2)
            lineage = client.get("/lots/observed-7/lot-00001/lineage?direction=ancestors").json()
            self.assertTrue(any(node["node_type"] == "event" for node in lineage["nodes"]))
            self.assertEqual(client.get("/trust/observed-7/lot-00001").status_code, 200)
            v1 = client.get("/api/v1/snapshots?limit=1&offset=0")
            self.assertEqual(v1.status_code, 200)
            self.assertEqual(v1.json()["total"], 1)
            self.assertFalse(v1.json()["has_more"])
            self.assertEqual(client.get("/api/v1/snapshots/observed-7/lots?limit=1").json()["total"], 2)
            self.assertEqual(client.get("/api/v1/trust/observed-7/lot-00001").status_code, 200)
            graph_response = client.get("/api/v1/snapshots/observed-7/graph")
            self.assertEqual(graph_response.status_code, 200)
            self.assertTrue(graph_response.json()["nodes"])
            self.assertTrue(graph_response.json()["edges"])
            self.assertIn("items", client.get("/findings/observed-7").json())
            self.assertIn("X-Request-ID", client.get("/health").headers)
            self.assertEqual(client.get("/health").headers["X-API-Version"], "v1")
            self.assertIn("items", client.get("/events/observed-7/evt-receive-00001/evidence").json())
            self.assertEqual(client.get("/relations/match-gold-7-evt-prod-00001-observed-7-evt-prod-00001").status_code, 200)
            self.assertEqual(client.get("/").status_code, 200)

            database = root / "tracetrust.db"
            persist_analysis(root, database)
            sqlite_client = TestClient(create_app(database=str(database)))
            self.assertEqual(sqlite_client.get("/snapshots/observed-7").status_code, 200)
            self.assertEqual(sqlite_client.get("/trust/observed-7/lot-00001").status_code, 200)

            protected = TestClient(create_app(str(root), api_key="secret"))
            self.assertEqual(protected.get("/snapshots").status_code, 401)
            self.assertEqual(protected.get("/ready").status_code, 200)
            self.assertEqual(protected.get("/snapshots", headers={"X-API-Key": "secret"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
