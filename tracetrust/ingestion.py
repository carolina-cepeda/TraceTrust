"""Snapshot ingestion ports and filesystem adapter.

The domain consumes validated canonical events. Filesystem, PostgreSQL and
future API adapters can implement the same boundary without leaking transport
details into reconciliation or scoring.
"""

from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .models import CanonicalTraceabilityEvent, SnapshotManifest


class SnapshotValidationError(ValueError):
    """Raised when an exported snapshot cannot be trusted or parsed."""


class SnapshotBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: SnapshotManifest
    events: list[CanonicalTraceabilityEvent] = Field(default_factory=list)
    root: Path


class SnapshotReader(Protocol):
    def read(self, root: str | Path) -> SnapshotBundle:
        """Read and validate a snapshot from a source."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class FileSystemSnapshotReader:
    """Validate manifest integrity before exposing canonical events."""

    def read(self, root: str | Path) -> SnapshotBundle:
        snapshot_root = Path(root).resolve()
        manifest_path = snapshot_root / "manifest.json"
        if not manifest_path.is_file():
            raise SnapshotValidationError(f"Missing manifest: {manifest_path}")
        manifest = SnapshotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        all_events: list[CanonicalTraceabilityEvent] = []
        for file_entry in manifest.files:
            file_path = (snapshot_root / file_entry.path).resolve()
            if snapshot_root not in file_path.parents and file_path != snapshot_root:
                raise SnapshotValidationError(f"Manifest path escapes snapshot root: {file_entry.path}")
            if not file_path.is_file():
                raise SnapshotValidationError(f"Missing snapshot file: {file_path}")
            actual_hash = _sha256(file_path)
            if actual_hash != file_entry.sha256:
                raise SnapshotValidationError(f"Hash mismatch for {file_entry.path}")
            records = self._records(file_path, file_entry.format)
            if len(records) != file_entry.row_count:
                raise SnapshotValidationError(f"Row count mismatch for {file_entry.path}")
            for record in records:
                event = CanonicalTraceabilityEvent.model_validate(record)
                if event.snapshot_id != manifest.snapshot_id:
                    raise SnapshotValidationError(
                        f"Event {event.event_id} belongs to {event.snapshot_id}, "
                        f"not manifest {manifest.snapshot_id}"
                    )
                all_events.append(event)
        return SnapshotBundle(manifest=manifest, events=all_events, root=snapshot_root)

    @staticmethod
    def _records(path: Path, file_format: str) -> list[dict]:
        if file_format == "jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if file_format == "csv":
            with path.open("r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                for field in ("input_lots", "output_lots", "evidence_refs", "raw_payload"):
                    if field in row and isinstance(row[field], str):
                        row[field] = json.loads(row[field])
            return rows
        raise SnapshotValidationError(f"Unsupported snapshot format: {file_format}")
