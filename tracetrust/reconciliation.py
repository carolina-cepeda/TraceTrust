"""Deterministic, explainable reconciliation for canonical events."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher
from pathlib import Path

from .models import (
    CanonicalTraceabilityEvent,
    MatchComponent,
    MatchStatus,
    ReconciliationMatch,
    RelationKind,
)


ALGORITHM_VERSION = "reconciliation-v1"


@dataclass(frozen=True)
class Candidate:
    left: CanonicalTraceabilityEvent
    right: CanonicalTraceabilityEvent
    reasons: list[str]


def load_events(path: str | Path) -> list[CanonicalTraceabilityEvent]:
    """Load and validate canonical events from JSONL."""
    source = Path(path)
    return [
        CanonicalTraceabilityEvent.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def _string_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _time_similarity(left: CanonicalTraceabilityEvent, right: CanonicalTraceabilityEvent) -> float:
    delta = abs(left.timestamp - right.timestamp)
    return max(0.0, 1.0 - delta / timedelta(hours=48))


def _quantity_similarity(left: CanonicalTraceabilityEvent, right: CanonicalTraceabilityEvent) -> float:
    denominator = max(left.quantity, right.quantity, 1.0)
    return max(0.0, 1.0 - abs(left.quantity - right.quantity) / denominator)


def select_candidates(
    left_events: list[CanonicalTraceabilityEvent],
    right_events: list[CanonicalTraceabilityEvent],
) -> list[Candidate]:
    """Select plausible pairs before scoring, avoiding an all-to-all join."""
    candidates: list[Candidate] = []
    for left in left_events:
        for right in right_events:
            reasons: list[str] = []
            if left.source_record_id == right.source_record_id:
                reasons.append("same_source_record_id")
            if left.event_type == right.event_type:
                reasons.append("same_event_type")
            if set(left.input_lots + left.output_lots) & set(right.input_lots + right.output_lots):
                reasons.append("shared_lot_reference")
            if left.organization == right.organization:
                reasons.append("same_organization")
            if abs(left.timestamp - right.timestamp) <= timedelta(hours=48):
                reasons.append("timestamp_within_48h")
            if "same_source_record_id" in reasons or (
                "same_event_type" in reasons
                and ("shared_lot_reference" in reasons or "same_organization" in reasons)
            ):
                candidates.append(Candidate(left, right, reasons))
    return candidates


def score_candidate(candidate: Candidate) -> ReconciliationMatch:
    left, right = candidate.left, candidate.right
    components = [
        ("source_record_id", 0.35, _string_similarity(left.source_record_id, right.source_record_id),
         "identificador de registro de origen"),
        ("lot_overlap", 0.25, _jaccard(left.input_lots + left.output_lots, right.input_lots + right.output_lots),
         "solapamiento de lotes"),
        ("event_type", 0.15, float(left.event_type == right.event_type), "tipo de evento"),
        ("organization", 0.10, float(left.organization == right.organization), "organización"),
        ("timestamp", 0.10, _time_similarity(left, right), "proximidad temporal"),
        ("quantity", 0.05, _quantity_similarity(left, right), "compatibilidad de cantidad"),
    ]
    component_models = [
        MatchComponent(name=name, weight=weight, similarity=similarity,
                       contribution=round(weight * similarity, 6),
                       explanation=explanation)
        for name, weight, similarity, explanation in components
    ]
    score = round(sum(component.contribution for component in component_models), 6)
    status = (MatchStatus.MATCH if score >= 0.80 else
              MatchStatus.REVIEW if score >= 0.55 else MatchStatus.NON_MATCH)
    return ReconciliationMatch(
        match_id=f"match-{left.snapshot_id}-{left.event_id}-{right.snapshot_id}-{right.event_id}",
        left_event_id=left.event_id, right_event_id=right.event_id,
        left_snapshot_id=left.snapshot_id, right_snapshot_id=right.snapshot_id,
        status=status,
        relation_kind=RelationKind.RECORDED if left.source_record_id == right.source_record_id
        else RelationKind.INFERRED,
        score=score, components=component_models,
        candidate_reasons=candidate.reasons, algorithm_version=ALGORITHM_VERSION,
    )


def reconcile(
    left_events: list[CanonicalTraceabilityEvent],
    right_events: list[CanonicalTraceabilityEvent],
) -> list[ReconciliationMatch]:
    """Return one best auditable decision per left-side event."""
    scored = [score_candidate(candidate) for candidate in select_candidates(left_events, right_events)]
    # A reconciliation is a one-to-one assignment: one source record cannot be
    # silently matched to multiple records in the other source.
    selected: list[ReconciliationMatch] = []
    used_left: set[tuple[str, str]] = set()
    used_right: set[tuple[str, str]] = set()
    for result in sorted(scored, key=lambda item: (-item.score, item.match_id)):
        left_key = (result.left_snapshot_id, result.left_event_id)
        right_key = (result.right_snapshot_id, result.right_event_id)
        if left_key in used_left or right_key in used_right:
            continue
        selected.append(result)
        used_left.add(left_key)
        used_right.add(right_key)
    order = {(event.snapshot_id, event.event_id): index for index, event in enumerate(left_events)}
    return sorted(selected, key=lambda item: order[(item.left_snapshot_id, item.left_event_id)])


def reconcile_files(left_path: str | Path, right_path: str | Path, output_path: str | Path) -> list[ReconciliationMatch]:
    results = reconcile(load_events(left_path), load_events(right_path))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(result.model_dump_json() + "\n" for result in results), encoding="utf-8"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left_events", type=Path)
    parser.add_argument("right_events", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    results = reconcile_files(args.left_events, args.right_events, args.output)
    counts = {status.value: sum(result.status == status for result in results) for status in MatchStatus}
    print(json.dumps({"matches": len(results), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
