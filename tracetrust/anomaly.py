"""Tabular anomaly detection over canonical traceability events."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from sklearn.ensemble import IsolationForest

from .models import (
    AnomalyObservation,
    CanonicalTraceabilityEvent,
    Finding,
    FindingSeverity,
    ReconciliationMatch,
)
from .reconciliation import load_events
from .rules import load_matches


MODEL_VERSION = "isolation-forest-v1"


FEATURE_NAMES = (
    "quantity",
    "lot_count",
    "evidence_missing",
    "hours_since_previous_event",
    "actor_event_frequency",
    "matched_quantity_difference",
)


def _hours(left: datetime, right: datetime) -> float:
    return abs((left - right).total_seconds()) / 3600


def build_features(events: list[CanonicalTraceabilityEvent], matches: list[ReconciliationMatch]) -> dict[str, dict[str, float]]:
    by_lot: dict[str, list[CanonicalTraceabilityEvent]] = {}
    actor_counts = Counter(event.actor for event in events)
    quantity_difference: dict[str, float] = {}
    for match in matches:
        for component in match.components:
            if component.name == "quantity":
                quantity_difference[match.right_event_id] = 1.0 - component.similarity
    for event in events:
        for lot_id in set(event.input_lots + event.output_lots):
            by_lot.setdefault(lot_id, []).append(event)
    features: dict[str, dict[str, float]] = {}
    for event in events:
        related = sorted(
            (other for lot_events in by_lot.values() for other in lot_events if other.event_id != event.event_id),
            key=lambda other: _hours(event.timestamp, other.timestamp),
        )
        features[event.event_id] = {
            "quantity": float(event.quantity),
            "lot_count": float(len(set(event.input_lots + event.output_lots))),
            "evidence_missing": float(not bool(event.evidence_refs)),
            "hours_since_previous_event": _hours(event.timestamp, related[0].timestamp) if related else 0.0,
            "actor_event_frequency": float(actor_counts[event.actor]),
            "matched_quantity_difference": quantity_difference.get(event.event_id, 0.0),
        }
    return features


def detect_anomalies(
    events: list[CanonicalTraceabilityEvent],
    matches: list[ReconciliationMatch] | None = None,
    *, contamination: float = 0.1,
    random_state: int = 42,
) -> list[AnomalyObservation]:
    if not events:
        return []
    if not 0 < contamination <= 0.5:
        raise ValueError("contamination must be greater than 0 and no greater than 0.5")
    features = build_features(events, matches or [])
    matrix = [[features[event.event_id][name] for name in FEATURE_NAMES] for event in events]
    model = IsolationForest(contamination=contamination, random_state=random_state, n_estimators=100)
    model.fit(matrix)
    decisions = model.decision_function(matrix)
    predictions = model.predict(matrix)
    return [
        AnomalyObservation(
            event_id=event.event_id, snapshot_id=event.snapshot_id,
            anomaly_score=round(float(-decision), 6), is_anomaly=prediction == -1,
            features=features[event.event_id], model_version=MODEL_VERSION,
        )
        for event, decision, prediction in zip(events, decisions, predictions)
    ]


def anomaly_findings(
    events: list[CanonicalTraceabilityEvent], observations: list[AnomalyObservation],
) -> list[Finding]:
    by_id = {event.event_id: event for event in events}
    findings = []
    for observation in observations:
        if not observation.is_anomaly:
            continue
        event = by_id[observation.event_id]
        findings.append(Finding(
            finding_id=f"finding-tabular-anomaly-{event.event_id}",
            rule_id="isolation_forest_anomaly", severity=FindingSeverity.MEDIUM,
            snapshot_id=event.snapshot_id,
            entity_ids=sorted(set(event.input_lots + event.output_lots)),
            source_event_ids=[event.event_id], values={"anomaly_score": observation.anomaly_score,
                                                       "features": observation.features},
            explanation="Isolation Forest identificó un patrón estadísticamente atípico en el evento.",
            algorithm_version=MODEL_VERSION,
        ))
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("matches", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    observations = detect_anomalies(load_events(args.events), load_matches(args.matches))
    args.output.write_text("".join(item.model_dump_json() + "\n" for item in observations), encoding="utf-8")
    print(json.dumps({"events": len(observations), "anomalies": sum(item.is_anomaly for item in observations)}, indent=2))


if __name__ == "__main__":
    main()
