"""Reproducible evaluation against the generator's ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import EvaluationReport, Finding, ReconciliationMatch


EVALUATION_VERSION = "evaluation-v1"


def _metrics(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6)}


def evaluate(
    ground_truth: dict,
    matches: list[ReconciliationMatch],
    findings: list[Finding],
) -> EvaluationReport:
    expected_pairs = {(item["left_event_id"], item["right_event_id"])
                      for item in ground_truth.get("expected_event_matches", [])}
    predicted_pairs = {(match.left_event_id, match.right_event_id)
                       for match in matches if match.status.value == "match"}
    match_tp = len(expected_pairs & predicted_pairs)
    match_fp = len(predicted_pairs - expected_pairs)
    match_fn = len(expected_pairs - predicted_pairs)
    expected_findings = {item["event_id"] for item in ground_truth.get("perturbations", [])}
    predicted_findings = {event_id for finding in findings for event_id in finding.source_event_ids}
    finding_tp = len(expected_findings & predicted_findings)
    finding_fp = len(predicted_findings - expected_findings)
    finding_fn = len(expected_findings - predicted_findings)
    metrics = {
        **{f"reconciliation_{key}": value for key, value in _metrics(match_tp, match_fp, match_fn).items()},
        **{f"finding_{key}": value for key, value in _metrics(finding_tp, finding_fp, finding_fn).items()},
    }
    return EvaluationReport(
        dataset_seed=int(ground_truth["seed"]), metrics=metrics,
        details={"expected_matches": len(expected_pairs), "predicted_matches": len(predicted_pairs),
                 "expected_perturbations": len(expected_findings), "predicted_perturbations": len(predicted_findings)},
        evaluation_version=EVALUATION_VERSION,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("matches", type=Path)
    parser.add_argument("findings", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    ground_truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    matches = [ReconciliationMatch.model_validate_json(line) for line in args.matches.read_text(encoding="utf-8").splitlines() if line.strip()]
    findings = [Finding.model_validate_json(line) for line in args.findings.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate(ground_truth, matches, findings)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
