"""End-to-end analytical pipeline for a prepared TraceTrust workspace."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .anomaly import anomaly_findings, detect_anomalies
from .benchmarks import benchmark_detectors
from .calibration import sensitivity_analysis
from .evaluation import evaluate
from .graph import project_graph
from .models import EvaluationReport
from .reconciliation import load_events, reconcile
from .rules import run_rules
from .trust_score import calculate_all_lots


PIPELINE_VERSION = "pipeline-v1"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _write_jsonl(path: Path, items: list[Any]) -> None:
    _atomic_write(path, "".join(item.model_dump_json() + "\n" for item in items))


def run_pipeline(root: str | Path) -> dict[str, Any]:
    """Run all analytical stages and persist a coherent artifact set."""
    workspace = Path(root)
    gold_events = load_events(workspace / "gold" / "events.jsonl")
    observed_events = load_events(workspace / "observed" / "events.jsonl")
    matches = reconcile(gold_events, observed_events)
    deterministic_findings = run_rules(gold_events + observed_events, matches)
    observations = detect_anomalies(observed_events, matches)
    findings = deterministic_findings + anomaly_findings(observed_events, observations)
    assessments = calculate_all_lots(observed_events, matches, findings)
    graph = project_graph(observed_events, matches, findings, assessments)

    _write_jsonl(workspace / "reconciliation.jsonl", matches)
    _write_jsonl(workspace / "anomalies.jsonl", observations)
    _write_jsonl(workspace / "findings.jsonl", findings)
    _write_jsonl(workspace / "trust_scores.jsonl", assessments)
    _atomic_write(workspace / "trace_graph.json", graph.model_dump_json(indent=2))

    evaluation: EvaluationReport | None = None
    ground_truth_path = workspace / "ground_truth.json"
    if ground_truth_path.is_file():
        ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        evaluation = evaluate(ground_truth, matches, findings)
        _atomic_write(workspace / "evaluation.json", evaluation.model_dump_json(indent=2))
        expected_ids = {item["event_id"] for item in ground_truth.get("perturbations", [])}
        _atomic_write(workspace / "benchmarks.json", json.dumps(
            benchmark_detectors(observed_events, matches, expected_ids), indent=2))
        lot_ids = sorted({lot for event in observed_events for lot in event.input_lots + event.output_lots})
        _atomic_write(workspace / "calibration.json", json.dumps(
            sensitivity_analysis(lot_ids, observed_events, matches, findings), indent=2))

    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "gold_events": len(gold_events),
        "observed_events": len(observed_events),
        "matches": len(matches),
        "findings": len(findings),
        "anomalies": sum(observation.is_anomaly for observation in observations),
        "trust_assessments": len(assessments),
        "graph_nodes": len(graph.nodes),
        "graph_edges": len(graph.edges),
        "evaluation": evaluation.metrics if evaluation else None,
    }
    _atomic_write(workspace / "pipeline_summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_pipeline(args.workspace), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
