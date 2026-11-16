"""Application services that orchestrate adapters and analytical modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .graph import TraceGraphArtifact, traverse
from .ingestion import FileSystemSnapshotReader, SnapshotBundle
from .models import Finding, ReconciliationMatch, TrustAssessment


class AnalysisRepository(Protocol):
    def snapshot(self) -> SnapshotBundle: ...
    def matches(self) -> list[ReconciliationMatch]: ...
    def findings(self) -> list[Finding]: ...
    def assessments(self) -> list[TrustAssessment]: ...
    def graph(self) -> TraceGraphArtifact: ...


class FilesystemAnalysisRepository:
    """Read one prepared analysis workspace from disk.

    Expected layout: ``root/observed/manifest.json`` plus generated artifacts
    in ``root/`` (reconciliation, findings, trust scores and graph JSON).
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._snapshot: SnapshotBundle | None = None

    def snapshot(self) -> SnapshotBundle:
        if self._snapshot is None:
            self._snapshot = FileSystemSnapshotReader().read(self.root / "observed")
        return self._snapshot

    def _jsonl(self, filename: str) -> list[str]:
        path = self.root / filename
        if not path.is_file():
            return []
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def matches(self) -> list[ReconciliationMatch]:
        return [ReconciliationMatch.model_validate_json(line) for line in self._jsonl("reconciliation.jsonl")]

    def findings(self) -> list[Finding]:
        return [Finding.model_validate_json(line) for line in self._jsonl("findings.jsonl")]

    def assessments(self) -> list[TrustAssessment]:
        return [TrustAssessment.model_validate_json(line) for line in self._jsonl("trust_scores.jsonl")]

    def graph(self) -> TraceGraphArtifact:
        path = self.root / "trace_graph.json"
        return TraceGraphArtifact.model_validate_json(path.read_text(encoding="utf-8"))


class AnalysisService:
    """Use-case facade used by the HTTP layer and future CLI clients."""

    def __init__(self, repository: AnalysisRepository):
        self.repository = repository

    def snapshot_summary(self) -> dict[str, Any]:
        snapshot = self.repository.snapshot()
        events = snapshot.events
        lots = sorted({lot for event in events for lot in event.input_lots + event.output_lots})
        findings = [f for f in self.repository.findings() if f.snapshot_id == snapshot.manifest.snapshot_id]
        assessments = self.repository.assessments()
        return {
            "snapshot_id": snapshot.manifest.snapshot_id,
            "source_system": snapshot.manifest.source_system,
            "event_count": len(events),
            "lot_count": len(lots),
            "finding_count": len(findings),
            "average_trust_score": round(sum(a.score for a in assessments) / len(assessments), 4)
            if assessments else None,
        }

    def snapshots(self) -> list[dict[str, Any]]:
        return [self.snapshot_summary()]

    def lots(self, snapshot_id: str) -> list[dict[str, Any]]:
        summary = self.snapshot_summary()
        if summary["snapshot_id"] != snapshot_id:
            raise ValueError(f"Unknown snapshot: {snapshot_id}")
        events = self.repository.snapshot().events
        findings = self.repository.findings()
        assessments = {assessment.entity_id: assessment for assessment in self.repository.assessments()}
        lot_ids = sorted({lot for event in events for lot in event.input_lots + event.output_lots})
        return [
            {
                "lot_id": lot_id,
                "event_count": sum(lot_id in event.input_lots + event.output_lots for event in events),
                "finding_count": sum(lot_id in finding.entity_ids and finding.snapshot_id == snapshot_id
                                       for finding in findings),
                "trust_score": assessments[lot_id].score if lot_id in assessments else None,
            }
            for lot_id in lot_ids
        ]

    def lineage(self, snapshot_id: str, lot_id: str, direction: str, depth: int) -> dict[str, Any]:
        if snapshot_id != self.repository.snapshot().manifest.snapshot_id:
            raise ValueError(f"Unknown snapshot: {snapshot_id}")
        node_id = f"lot:{snapshot_id}:{lot_id}"
        if direction == "both":
            return {"ancestors": traverse(self.repository.graph(), node_id, direction="ancestors", depth=depth),
                    "descendants": traverse(self.repository.graph(), node_id, direction="descendants", depth=depth)}
        return traverse(self.repository.graph(), node_id, direction=direction, depth=depth)

    def findings(self, snapshot_id: str, severity: str | None = None) -> list[dict[str, Any]]:
        results = [f for f in self.repository.findings() if f.snapshot_id == snapshot_id]
        if severity:
            results = [f for f in results if f.severity.value == severity]
        return [finding.model_dump(mode="json") for finding in results]

    def trust(self, snapshot_id: str, lot_id: str) -> dict[str, Any]:
        for assessment in self.repository.assessments():
            if assessment.snapshot_id == snapshot_id and assessment.entity_id == lot_id:
                return assessment.model_dump(mode="json")
        raise ValueError(f"No Trust Score for {snapshot_id}/{lot_id}")
