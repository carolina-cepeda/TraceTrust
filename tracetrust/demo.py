"""One-command preparation and health check for the TraceTrust presentation demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import TraceGraphArtifact
from .neo4j import export_cypher
from .pipeline import run_pipeline
from .storage import persist_analysis


REQUIRED_ARTIFACTS = (
    "pipeline_summary.json", "evaluation.json", "benchmarks.json", "calibration.json",
    "reconciliation.jsonl", "findings.jsonl", "anomalies.jsonl", "trust_scores.jsonl",
    "trace_graph.json", "trace_graph.cypher",
)


def prepare_demo(workspace: str | Path, database: str | Path | None = None) -> dict:
    """Rebuild analytical artifacts, exports and the local read model."""
    root = Path(workspace)
    summary = run_pipeline(root)
    graph_path = root / "trace_graph.json"
    artifact = TraceGraphArtifact.model_validate_json(graph_path.read_text(encoding="utf-8"))
    export_cypher(artifact, root / "trace_graph.cypher")
    database_path = Path(database) if database else root / "tracetrust.db"
    persist_analysis(root, database_path)
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    if missing:
        raise RuntimeError(f"Demo artifacts missing: {', '.join(missing)}")
    return {"status": "ready", "workspace": str(root), "database": str(database_path),
            "artifacts": len(REQUIRED_ARTIFACTS), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, help="Prepared workspace, e.g. data/demo")
    parser.add_argument("--database", type=Path, help="Optional SQLite read-model path")
    args = parser.parse_args()
    print(json.dumps(prepare_demo(args.workspace, args.database), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
