"""Comparable tabular anomaly detectors for the academic evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from .anomaly import FEATURE_NAMES, build_features
from .reconciliation import load_events
from .rules import load_matches


def _metrics(expected: set[str], predicted: set[str]) -> dict[str, float]:
    tp, fp, fn = len(expected & predicted), len(predicted - expected), len(expected - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6),
            "false_positives": fp, "false_negatives": fn}


def benchmark_detectors(events, matches, expected_ids: set[str], contamination: float = 0.1) -> dict:
    features = build_features(events, matches)
    matrix = [[features[event.event_id][name] for name in FEATURE_NAMES] for event in events]
    scaled = StandardScaler().fit_transform(matrix)
    detectors = {
        "isolation_forest": IsolationForest(contamination=contamination, random_state=42, n_estimators=100),
        "lof": LocalOutlierFactor(contamination=contamination, n_neighbors=min(20, max(2, len(events) - 1))),
        "one_class_svm": OneClassSVM(nu=contamination, gamma="scale"),
    }
    results = {}
    for name, detector in detectors.items():
        predictions = detector.fit_predict(scaled)
        predicted_ids = {event.event_id for event, prediction in zip(events, predictions) if prediction == -1}
        results[name] = _metrics(expected_ids, predicted_ids)
        results[name]["anomaly_count"] = len(predicted_ids)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("matches", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    expected = {item["event_id"] for item in json.loads(args.ground_truth.read_text(encoding="utf-8"))["perturbations"]}
    report = benchmark_detectors(load_events(args.events), load_matches(args.matches), expected)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
