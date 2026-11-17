"""Deterministic integrity rules over canonical events and reconciliations."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from .models import (
    CanonicalTraceabilityEvent,
    EventType,
    Finding,
    FindingSeverity,
    MatchStatus,
    ReconciliationMatch,
)
from .reconciliation import load_events


RULES_VERSION = "rules-v1"


def load_matches(path: str | Path) -> list[ReconciliationMatch]:
    return [
        ReconciliationMatch.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _finding(
    *, rule_id: str, severity: FindingSeverity, event: CanonicalTraceabilityEvent,
    entity_ids: list[str], source_event_ids: list[str], values: dict,
    explanation: str,
) -> Finding:
    stable_key = "-".join([rule_id, *sorted(entity_ids), *sorted(source_event_ids)])
    return Finding(
        finding_id=f"finding-{stable_key}", rule_id=rule_id, severity=severity,
        snapshot_id=event.snapshot_id, entity_ids=sorted(set(entity_ids)),
        source_event_ids=sorted(set(source_event_ids)), values=values,
        explanation=explanation, algorithm_version=RULES_VERSION,
    )


def quantity_discrepancies(
    events: list[CanonicalTraceabilityEvent],
    matches: list[ReconciliationMatch],
    tolerance: float = 0.05,
) -> list[Finding]:
    by_key = {(event.snapshot_id, event.event_id): event for event in events}
    findings = []
    for match in matches:
        if match.status == MatchStatus.NON_MATCH:
            continue
        left = by_key.get((match.left_snapshot_id, match.left_event_id))
        right = by_key.get((match.right_snapshot_id, match.right_event_id))
        if left is None or right is None:
            continue
        denominator = max(abs(left.quantity), abs(right.quantity), 1.0)
        relative_difference = abs(left.quantity - right.quantity) / denominator
        if relative_difference > tolerance:
            findings.append(_finding(
                rule_id="quantity_compatibility", severity=FindingSeverity.HIGH,
                event=left, entity_ids=left.input_lots + left.output_lots,
                source_event_ids=[left.event_id, right.event_id],
                values={"left_quantity": left.quantity, "right_quantity": right.quantity,
                        "unit": left.unit, "relative_difference": round(relative_difference, 6),
                        "tolerance": tolerance, "match_id": match.match_id},
                explanation=(f"La cantidad reconciliada difiere en {relative_difference:.1%}; "
                             "la relación requiere revisión operacional."),
            ))
    return findings


def missing_evidence(events: list[CanonicalTraceabilityEvent]) -> list[Finding]:
    findings = []
    required = {EventType.TRANSFER, EventType.RECEIPT, EventType.TRANSFORMATION, EventType.SPLIT, EventType.MERGE}
    for event in events:
        if event.event_type in required and not event.evidence_refs:
            findings.append(_finding(
                rule_id="required_evidence", severity=FindingSeverity.MEDIUM,
                event=event, entity_ids=event.input_lots + event.output_lots,
                source_event_ids=[event.event_id], values={"event_type": event.event_type.value},
                explanation="El evento requiere evidencia de soporte, pero no tiene referencias asociadas.",
            ))
    return findings


def impossible_temporal_sequence(events: list[CanonicalTraceabilityEvent]) -> list[Finding]:
    by_lot: dict[str, list[CanonicalTraceabilityEvent]] = {}
    for event in events:
        for lot_id in set(event.input_lots + event.output_lots):
            by_lot.setdefault(lot_id, []).append(event)
    findings = []
    for lot_id, lot_events in by_lot.items():
        # A receipt can legitimately precede a later transformation of the
        # received lot. Temporal validation therefore compares it with the
        # origin event, not every downstream transformation.
        productions = [e for e in lot_events if e.event_type == EventType.PRODUCTION]
        receipts = [e for e in lot_events if e.event_type == EventType.RECEIPT]
        for receipt in receipts:
            for production in productions:
                if receipt.timestamp < production.timestamp:
                    findings.append(_finding(
                        rule_id="temporal_sequence", severity=FindingSeverity.CRITICAL,
                        event=receipt, entity_ids=[lot_id],
                        source_event_ids=[production.event_id, receipt.event_id],
                        values={"producer_timestamp": production.timestamp.isoformat(),
                                "receipt_timestamp": receipt.timestamp.isoformat()},
                        explanation="La recepción ocurre antes de la producción o transformación del lote.",
                    ))
    return findings


def orphan_lot_references(events: list[CanonicalTraceabilityEvent]) -> list[Finding]:
    origin_types = {EventType.PRODUCTION, EventType.TRANSFORMATION, EventType.SPLIT, EventType.MERGE}
    produced = {
        lot_id for event in events if event.event_type in origin_types
        for lot_id in event.output_lots
    }
    findings = []
    for event in events:
        missing = sorted(set(event.input_lots) - produced)
        if missing:
            findings.append(_finding(
                rule_id="orphan_lot_reference", severity=FindingSeverity.CRITICAL,
                event=event, entity_ids=missing, source_event_ids=[event.event_id],
                values={"missing_lot_ids": missing},
                explanation="El evento referencia lotes de entrada sin un origen observable en el snapshot.",
            ))
    return findings


def run_rules(
    events: list[CanonicalTraceabilityEvent],
    matches: list[ReconciliationMatch] | None = None,
    *, tolerance: float = 0.05,
) -> list[Finding]:
    matches = matches or []
    findings = []
    findings.extend(quantity_discrepancies(events, matches, tolerance=tolerance))
    findings.extend(missing_evidence(events))
    findings.extend(impossible_temporal_sequence(events))
    findings.extend(orphan_lot_references(events))
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left_events", type=Path)
    parser.add_argument("right_events", type=Path)
    parser.add_argument("matches", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    events = load_events(args.left_events) + load_events(args.right_events)
    findings = run_rules(events, load_matches(args.matches))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(finding.model_dump_json() + "\n" for finding in findings), encoding="utf-8")
    counts = {severity.value: sum(finding.severity == severity for finding in findings)
              for severity in FindingSeverity}
    print(json.dumps({"findings": len(findings), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
