"""Trackup integration: validate, persist and analyze canonical event batches."""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .anomaly import anomaly_findings, detect_anomalies
from .graph import project_graph
from .models import (
    AnonymizationPolicy,
    CanonicalTraceabilityEvent,
    Finding,
    SnapshotFile,
    SnapshotManifest,
    SourceSchema,
)
from .reconciliation import reconcile
from .rules import run_rules
from .trust_score import calculate_all_lots


class TrackupOutboxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    aggregate: str = Field(min_length=1)
    type: str = Field(min_length=1)
    payload: dict[str, Any]
    created_at: datetime


class TrackupBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    source_system: str = Field(default="trackup", min_length=1)
    schema_version: str = Field(default="1.0.0", pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    exporter_version: str = Field(default="trackup-bridge-v1", min_length=1)
    source_schema: SourceSchema
    anonymization: AnonymizationPolicy
    events: list[CanonicalTraceabilityEvent] = Field(default_factory=list, max_length=500)
    outbox_events: list[TrackupOutboxEvent] = Field(default_factory=list, max_length=500)


class TrackupBatchResult(BaseModel):
    snapshot_id: str
    accepted: int
    duplicates: int
    analysis: dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with open(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
        Path(temporary).replace(path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _canonical_from_outbox(
    item: TrackupOutboxEvent, request: TrackupBatchRequest
) -> CanonicalTraceabilityEvent:
    """Accept only payloads that already carry a complete traceability event.

    Trackup domain events such as ``LotPublished`` are useful operational events,
    but they do not contain enough evidence to become a TraceTrust event safely.
    The bridge therefore rejects them instead of filling fields with guesses.
    """
    payload = item.payload.get("canonical_event", item.payload)
    required = {
        "event_type", "timestamp", "actor", "organization", "input_lots",
        "output_lots", "quantity", "unit", "location",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"Outbox event {item.id} is not traceable; missing: {', '.join(missing)}")
    values = dict(payload)
    values.setdefault("event_id", item.id)
    values.setdefault("source_system", request.source_system)
    values.setdefault("source_record_id", item.aggregate)
    values.setdefault("snapshot_id", request.snapshot_id)
    values.setdefault("original_timestamp", str(values["timestamp"]))
    values.setdefault("original_quantity", str(values["quantity"]))
    values.setdefault("evidence_refs", [])
    values.setdefault("raw_payload", item.payload)
    return CanonicalTraceabilityEvent.model_validate(values)


def _write_jsonl(path: Path, events: list[CanonicalTraceabilityEvent]) -> None:
    _atomic_write(path, "".join(event.model_dump_json() + "\n" for event in events))


def ingest_trackup_batch(root: str | Path, request: TrackupBatchRequest) -> TrackupBatchResult:
    """Persist an idempotent Trackup batch and calculate its current analysis."""
    snapshot_root = Path(root) / "snapshots" / request.snapshot_id
    events_path = snapshot_root / "events.jsonl"
    existing: dict[str, CanonicalTraceabilityEvent] = {}
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = CanonicalTraceabilityEvent.model_validate_json(line)
                existing[event.event_id] = event

    incoming = list(request.events)
    incoming.extend(_canonical_from_outbox(item, request) for item in request.outbox_events)
    accepted = 0
    duplicates = 0
    for event in incoming:
        if event.snapshot_id != request.snapshot_id:
            raise ValueError(f"Event {event.event_id} belongs to another snapshot")
        if event.source_system != request.source_system:
            raise ValueError(f"Event {event.event_id} belongs to another source system")
        previous = existing.get(event.event_id)
        if previous:
            if previous.model_dump(mode="json") != event.model_dump(mode="json"):
                raise ValueError(f"Event {event.event_id} was reused with different content")
            duplicates += 1
            continue
        existing[event.event_id] = event
        accepted += 1

    events = sorted(existing.values(), key=lambda event: (event.timestamp, event.event_id))
    _write_jsonl(events_path, events)
    manifest = SnapshotManifest(
        snapshot_id=request.snapshot_id,
        source_system=request.source_system,
        extracted_at=datetime.now(timezone.utc),
        schema_version=request.schema_version,
        source_schema=request.source_schema,
        exporter_version=request.exporter_version,
        anonymization=request.anonymization,
        files=[SnapshotFile(path="events.jsonl", format="jsonl", row_count=len(events), sha256=_sha256(events_path))],
    )
    _atomic_write(snapshot_root / "manifest.json", manifest.model_dump_json(indent=2))

    matches = reconcile([], events)
    findings: list[Finding] = run_rules(events, matches)
    observations = detect_anomalies(events, matches)
    findings.extend(anomaly_findings(events, observations))
    assessments = calculate_all_lots(events, matches, findings)
    graph = project_graph(events, matches, findings, assessments)
    _atomic_write(
        snapshot_root / "reconciliation.jsonl",
        "".join(item.model_dump_json() + "\n" for item in matches),
    )
    _atomic_write(
        snapshot_root / "findings.jsonl",
        "".join(item.model_dump_json() + "\n" for item in findings),
    )
    _atomic_write(
        snapshot_root / "trust_scores.jsonl",
        "".join(item.model_dump_json() + "\n" for item in assessments),
    )
    _atomic_write(snapshot_root / "trace_graph.json", graph.model_dump_json(indent=2))
    return TrackupBatchResult(
        snapshot_id=request.snapshot_id,
        accepted=accepted,
        duplicates=duplicates,
        analysis={
            "events": len(events),
            "findings": len(findings),
            "anomalies": sum(item.is_anomaly for item in observations),
            "trust_assessments": len(assessments),
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
        },
    )
