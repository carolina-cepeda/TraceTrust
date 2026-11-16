import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tracetrust.api import create_app
from tracetrust.generator import generate_dataset
from tracetrust.graph import project_graph
from tracetrust.reconciliation import load_events, reconcile
from tracetrust.rules import run_rules
from tracetrust.storage import persist_analysis
from tracetrust.trust_score import calculate_all_lots


class ApiTests(unittest.TestCase):
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
            self.assertEqual(client.get("/snapshots/observed-7").json()["lot_count"], 2)
            self.assertEqual(len(client.get("/snapshots").json()["items"]), 1)
            self.assertEqual(len(client.get("/lots/observed-7").json()["items"]), 2)
            lineage = client.get("/lots/observed-7/lot-00001/lineage?direction=ancestors").json()
            self.assertTrue(any(node["node_type"] == "event" for node in lineage["nodes"]))
            self.assertEqual(client.get("/trust/observed-7/lot-00001").status_code, 200)
            self.assertIn("items", client.get("/findings/observed-7").json())
            self.assertEqual(client.get("/").status_code, 200)

            database = root / "tracetrust.db"
            persist_analysis(root, database)
            sqlite_client = TestClient(create_app(database=str(database)))
            self.assertEqual(sqlite_client.get("/snapshots/observed-7").status_code, 200)
            self.assertEqual(sqlite_client.get("/trust/observed-7/lot-00001").status_code, 200)


if __name__ == "__main__":
    unittest.main()
