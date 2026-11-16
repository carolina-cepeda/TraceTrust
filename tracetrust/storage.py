"""SQLite persistence adapter for the analytical read model.

SQLite keeps the MVP self-contained. The repository boundary is intentionally
the same one used by the filesystem adapter, so PostgreSQL can replace this
adapter without changing application services or the API.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .application import FilesystemAnalysisRepository
from .graph import TraceGraphArtifact
from .ingestion import SnapshotBundle
from .models import Finding, ReconciliationMatch, TrustAssessment


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id TEXT PRIMARY KEY,
  manifest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  snapshot_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_json TEXT NOT NULL,
  PRIMARY KEY (snapshot_id, event_id)
);
CREATE TABLE IF NOT EXISTS matches (
  match_id TEXT PRIMARY KEY,
  match_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
  finding_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL,
  finding_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trust_assessments (
  assessment_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  assessment_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graphs (
  snapshot_id TEXT PRIMARY KEY,
  graph_json TEXT NOT NULL
);
"""


class SQLiteAnalysisRepository:
    """Read analytical artifacts from the local SQLite read model."""

    def __init__(self, database: str | Path):
        self.database = str(database)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def snapshot(self) -> SnapshotBundle:
        from .models import SnapshotManifest, CanonicalTraceabilityEvent

        with closing(self._connect()) as connection:
            row = connection.execute("SELECT manifest_json FROM snapshots ORDER BY snapshot_id LIMIT 1").fetchone()
            if row is None:
                raise FileNotFoundError("No snapshot stored")
            manifest = SnapshotManifest.model_validate_json(row["manifest_json"])
            event_rows = connection.execute(
                "SELECT event_json FROM events WHERE snapshot_id = ? ORDER BY event_id",
                (manifest.snapshot_id,),
            ).fetchall()
            events = [CanonicalTraceabilityEvent.model_validate_json(item["event_json"]) for item in event_rows]
            return SnapshotBundle(manifest=manifest, events=events, root=Path(self.database).resolve().parent)

    def matches(self) -> list[ReconciliationMatch]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT match_json FROM matches ORDER BY match_id").fetchall()
            return [ReconciliationMatch.model_validate_json(row["match_json"]) for row in rows]

    def findings(self) -> list[Finding]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT finding_json FROM findings ORDER BY finding_id").fetchall()
            return [Finding.model_validate_json(row["finding_json"]) for row in rows]

    def assessments(self) -> list[TrustAssessment]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT assessment_json FROM trust_assessments ORDER BY entity_id").fetchall()
            return [TrustAssessment.model_validate_json(row["assessment_json"]) for row in rows]

    def graph(self) -> TraceGraphArtifact:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT graph_json FROM graphs LIMIT 1").fetchone()
            if row is None:
                raise FileNotFoundError("No graph stored")
            return TraceGraphArtifact.model_validate_json(row["graph_json"])


def persist_analysis(source_root: str | Path, database: str | Path) -> None:
    """Materialize a prepared filesystem analysis into SQLite."""
    source = FilesystemAnalysisRepository(source_root)
    snapshot = source.snapshot()
    matches, findings = source.matches(), source.findings()
    assessments, graph = source.assessments(), source.graph()
    database_path = Path(database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            connection.executescript(SCHEMA)
            connection.execute("DELETE FROM snapshots")
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM matches")
            connection.execute("DELETE FROM findings")
            connection.execute("DELETE FROM trust_assessments")
            connection.execute("DELETE FROM graphs")
            connection.execute("INSERT INTO snapshots VALUES (?, ?)",
                               (snapshot.manifest.snapshot_id, snapshot.manifest.model_dump_json()))
            connection.executemany(
                "INSERT INTO events VALUES (?, ?, ?)",
                [(event.snapshot_id, event.event_id, event.model_dump_json()) for event in snapshot.events],
            )
            connection.executemany("INSERT INTO matches VALUES (?, ?)",
                                   [(match.match_id, match.model_dump_json()) for match in matches])
            connection.executemany(
                "INSERT INTO findings VALUES (?, ?, ?)",
                [(finding.finding_id, finding.snapshot_id, finding.model_dump_json()) for finding in findings],
            )
            connection.executemany(
                "INSERT INTO trust_assessments VALUES (?, ?, ?, ?)",
                [(assessment.assessment_id, assessment.snapshot_id, assessment.entity_id,
                  assessment.model_dump_json()) for assessment in assessments],
            )
            connection.execute("INSERT INTO graphs VALUES (?, ?)",
                               (snapshot.manifest.snapshot_id, graph.model_dump_json()))
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    persist_analysis(args.source_root, args.database)
    print(json.dumps({"database": str(args.database), "status": "persisted"}, indent=2))


if __name__ == "__main__":
    main()
