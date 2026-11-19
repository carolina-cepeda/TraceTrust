"""Application services that orchestrate adapters and analytical modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .graph import TraceGraphArtifact, traverse
from .ingestion import FileSystemSnapshotReader, SnapshotBundle
from .models import Finding, ReconciliationMatch, TrustAssessment


class AnalysisRepository(Protocol):
    def snapshot(self, snapshot_id: str | None = None) -> SnapshotBundle: ...
    def snapshot_ids(self) -> list[str]: ...
    def matches(self) -> list[ReconciliationMatch]: ...
    def findings(self) -> list[Finding]: ...
    def assessments(self) -> list[TrustAssessment]: ...
    def graph(self, snapshot_id: str | None = None) -> TraceGraphArtifact: ...


class FilesystemAnalysisRepository:
    """Read one prepared analysis workspace from disk.

    Expected layout: ``root/observed/manifest.json`` plus generated artifacts
    in ``root/`` (reconciliation, findings, trust scores and graph JSON).
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._snapshots: dict[str, SnapshotBundle] = {}

    def _snapshot_roots(self) -> list[Path]:
        roots = []
        observed = self.root / "observed"
        if (observed / "manifest.json").is_file():
            roots.append(observed)
        snapshots = self.root / "snapshots"
        if snapshots.is_dir():
            roots.extend(sorted(path for path in snapshots.iterdir()
                                if path.is_dir() and (path / "manifest.json").is_file()))
        return roots

    def snapshot_ids(self) -> list[str]:
        ids = []
        for root in self._snapshot_roots():
            ids.append(FileSystemSnapshotReader().read(root).manifest.snapshot_id)
        return ids

    def snapshot(self, snapshot_id: str | None = None) -> SnapshotBundle:
        if snapshot_id in self._snapshots:
            return self._snapshots[snapshot_id]
        reader = FileSystemSnapshotReader()
        for root in self._snapshot_roots():
            bundle = reader.read(root)
            self._snapshots[bundle.manifest.snapshot_id] = bundle
        if not self._snapshots:
            raise FileNotFoundError(f"No snapshots found under {self.root}")
        if snapshot_id is None:
            return next(iter(self._snapshots.values()))
        if snapshot_id not in self._snapshots:
            raise ValueError(f"Unknown snapshot: {snapshot_id}")
        return self._snapshots[snapshot_id]

    def _jsonl(self, filename: str) -> list[str]:
        path = self.root / filename
        if path.is_file():
            return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        lines: list[str] = []
        for snapshot_root in self._snapshot_roots():
            artifact = snapshot_root / filename
            if artifact.is_file():
                lines.extend(line for line in artifact.read_text(encoding="utf-8").splitlines() if line.strip())
        return lines

    def matches(self) -> list[ReconciliationMatch]:
        return [ReconciliationMatch.model_validate_json(line) for line in self._jsonl("reconciliation.jsonl")]

    def findings(self) -> list[Finding]:
        return [Finding.model_validate_json(line) for line in self._jsonl("findings.jsonl")]

    def assessments(self) -> list[TrustAssessment]:
        return [TrustAssessment.model_validate_json(line) for line in self._jsonl("trust_scores.jsonl")]

    def graph(self, snapshot_id: str | None = None) -> TraceGraphArtifact:
        bundle = self.snapshot(snapshot_id)
        path = bundle.root / "trace_graph.json"
        if not path.is_file():
            path = self.root / "trace_graph.json"
        return TraceGraphArtifact.model_validate_json(path.read_text(encoding="utf-8"))


class AnalysisService:
    """Use-case facade used by the HTTP layer and future CLI clients."""

    def __init__(self, repository: AnalysisRepository):
        self.repository = repository

    def snapshot_summary(self, snapshot_id: str | None = None) -> dict[str, Any]:
        snapshot = self.repository.snapshot(snapshot_id)
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
        return [self.snapshot_summary(snapshot_id) for snapshot_id in self.repository.snapshot_ids()]

    def lots(self, snapshot_id: str) -> list[dict[str, Any]]:
        summary = self.snapshot_summary(snapshot_id)
        if summary["snapshot_id"] != snapshot_id:
            raise ValueError(f"Unknown snapshot: {snapshot_id}")
        events = self.repository.snapshot(snapshot_id).events
        findings = [finding for finding in self.repository.findings() if finding.snapshot_id == snapshot_id]
        assessments = {assessment.entity_id: assessment for assessment in self.repository.assessments()
                       if assessment.snapshot_id == snapshot_id}
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
        self.repository.snapshot(snapshot_id)
        node_id = f"lot:{snapshot_id}:{lot_id}"
        if direction == "both":
            return {"ancestors": traverse(self.repository.graph(snapshot_id), node_id, direction="ancestors", depth=depth),
                    "descendants": traverse(self.repository.graph(snapshot_id), node_id, direction="descendants", depth=depth)}
        return traverse(self.repository.graph(snapshot_id), node_id, direction=direction, depth=depth)

    def graph(self, snapshot_id: str) -> dict[str, Any]:
        graph = self.repository.graph(snapshot_id).model_dump(mode="json")
        graph["snapshot_id"] = snapshot_id
        return graph

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

    def relation(self, match_id: str) -> dict[str, Any]:
        for match in self.repository.matches():
            if match.match_id == match_id:
                return match.model_dump(mode="json")
        raise ValueError(f"Unknown relation: {match_id}")

    def evidence(self, snapshot_id: str, event_id: str) -> list[dict[str, Any]]:
        event = next((item for item in self.repository.snapshot(snapshot_id).events
                      if item.event_id == event_id), None)
        if event is None:
            raise ValueError(f"Unknown event: {snapshot_id}/{event_id}")
        return [evidence.model_dump(mode="json") for evidence in event.evidence_refs]

    def anomalies(self, snapshot_id: str) -> list[dict[str, Any]]:
        return [finding.model_dump(mode="json") for finding in self.repository.findings()
                if finding.snapshot_id == snapshot_id and finding.rule_id == "isolation_forest_anomaly"]
