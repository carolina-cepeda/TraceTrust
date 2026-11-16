"""Explainable Trust Score calculation for lots in a canonical snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import (
    CanonicalTraceabilityEvent,
    EventType,
    Finding,
    FindingSeverity,
    MatchStatus,
    ReconciliationMatch,
    TrustAssessment,
    TrustFactor,
)
from .reconciliation import load_events
from .rules import load_matches


TRUST_SCORE_VERSION = "trust-score-v1"
DEFAULT_WEIGHTS = {
    "provenance_evidence": 0.20,
    "genealogy_continuity": 0.20,
    "quantity_consistency": 0.20,
    "temporal_coherence": 0.15,
    "cross_validation": 0.15,
    "attribute_completeness": 0.10,
}


def load_findings(path: str | Path) -> list[Finding]:
    return [
        Finding.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _events_for_lot(events: list[CanonicalTraceabilityEvent], lot_id: str) -> list[CanonicalTraceabilityEvent]:
    return [event for event in events if lot_id in event.input_lots + event.output_lots]


def _finding_for_lot(findings: list[Finding], lot_id: str, snapshot_id: str) -> list[Finding]:
    return [finding for finding in findings
            if finding.snapshot_id == snapshot_id and lot_id in finding.entity_ids]


def _factor(name: str, weight: float, score: float, explanation: str) -> TrustFactor:
    score = _clamp(score)
    return TrustFactor(
        name=name, weight=weight, score=round(score, 6),
        contribution=round(weight * score, 6), explanation=explanation,
    )


def calculate_trust_score(
    entity_id: str,
    events: list[CanonicalTraceabilityEvent],
    matches: list[ReconciliationMatch],
    findings: list[Finding],
    *,
    weights: dict[str, float] | None = None,
    critical_cap: float = 60.0,
) -> TrustAssessment:
    """Calculate a lot score while keeping every factor inspectable."""
    weights = dict(weights or DEFAULT_WEIGHTS)
    if set(weights) != set(DEFAULT_WEIGHTS) or abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError("Trust Score weights must contain the six factors and sum to 1")
    entity_events = _events_for_lot(events, entity_id)
    if not entity_events:
        raise ValueError(f"No events found for lot {entity_id}")
    snapshot_id = entity_events[0].snapshot_id
    entity_findings = _finding_for_lot(findings, entity_id, snapshot_id)
    event_ids = {event.event_id for event in entity_events}
    required_events = [event for event in entity_events if event.event_type in {
        EventType.TRANSFER, EventType.RECEIPT, EventType.TRANSFORMATION,
        EventType.SPLIT, EventType.MERGE,
    }]
    missing_evidence = sum(
        1 for event in required_events if not event.evidence_refs
    )
    provenance = 1.0 - (missing_evidence / len(required_events) if required_events else 0.0)
    continuity = 0.0 if any(f.rule_id == "orphan_lot_reference" for f in entity_findings) else 1.0
    quantity_findings = [f for f in entity_findings if f.rule_id == "quantity_compatibility"]
    max_quantity_difference = max(
        (float(f.values.get("relative_difference", 0.0)) for f in quantity_findings), default=0.0
    )
    quantity_consistency = 1.0 - _clamp(max_quantity_difference)
    temporal = 0.0 if any(f.rule_id == "temporal_sequence" for f in entity_findings) else 1.0
    matching_scores = [
        match.score for match in matches
        if match.status != MatchStatus.NON_MATCH
        and match.right_snapshot_id == snapshot_id
        and match.right_event_id in event_ids
    ]
    cross_validation = sum(matching_scores) / len(matching_scores) if matching_scores else 0.5
    complete_events = sum(
        bool(event.actor and event.organization and event.location and event.raw_payload
             and event.unit and (event.output_lots or event.input_lots))
        for event in entity_events
    )
    completeness = complete_events / len(entity_events)
    factors = [
        _factor("provenance_evidence", weights["provenance_evidence"], provenance,
                f"{missing_evidence} de {len(required_events)} eventos con evidencia requerida carecen de soporte."),
        _factor("genealogy_continuity", weights["genealogy_continuity"], continuity,
                "No se detectan referencias huérfanas para el lote." if continuity == 1 else
                "Existe al menos una referencia de lote sin origen observable."),
        _factor("quantity_consistency", weights["quantity_consistency"], quantity_consistency,
                f"Máxima discrepancia relativa observada: {max_quantity_difference:.1%}."),
        _factor("temporal_coherence", weights["temporal_coherence"], temporal,
                "La secuencia temporal es coherente." if temporal == 1 else
                "Existe una secuencia temporal imposible."),
        _factor("cross_validation", weights["cross_validation"], cross_validation,
                f"Promedio de score en {len(matching_scores)} correspondencias reconciliadas."),
        _factor("attribute_completeness", weights["attribute_completeness"], completeness,
                f"{complete_events} de {len(entity_events)} eventos tienen atributos mínimos completos."),
    ]
    uncapped = round(100 * sum(factor.contribution for factor in factors), 6)
    critical_penalties = sorted({finding.rule_id for finding in entity_findings
                                 if finding.severity == FindingSeverity.CRITICAL})
    score = min(uncapped, critical_cap) if critical_penalties else uncapped
    explanation = (f"Trust Score {score:.2f}/100 basado en seis factores explicables. "
                   f"Puntaje sin límite crítico: {uncapped:.2f}.")
    if critical_penalties:
        explanation += f" Se aplicó límite de {critical_cap:.0f} por: {', '.join(critical_penalties)}."
    return TrustAssessment(
        assessment_id=f"trust-{entity_id}-{snapshot_id}",
        entity_id=entity_id, snapshot_id=snapshot_id,
        score=round(score, 6), uncapped_score=uncapped, factors=factors,
        critical_penalties=critical_penalties, explanation=explanation,
        algorithm_version=TRUST_SCORE_VERSION,
    )


def calculate_all_lots(
    events: list[CanonicalTraceabilityEvent],
    matches: list[ReconciliationMatch],
    findings: list[Finding],
) -> list[TrustAssessment]:
    lot_ids = sorted({lot_id for event in events for lot_id in event.input_lots + event.output_lots})
    return [calculate_trust_score(lot_id, events, matches, findings) for lot_id in lot_ids]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("matches", type=Path)
    parser.add_argument("findings", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    assessments = calculate_all_lots(load_events(args.events), load_matches(args.matches), load_findings(args.findings))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(assessment.model_dump_json() + "\n" for assessment in assessments), encoding="utf-8")
    print(json.dumps({"assessments": len(assessments),
                      "average_score": round(sum(a.score for a in assessments) / len(assessments), 2)}, indent=2))


if __name__ == "__main__":
    main()
