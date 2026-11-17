"""PostgreSQL writer for the normalized TraceTrust schema.

The psycopg dependency is optional so local development can continue using
SQLite. Production deployments install ``tracetrust[postgres]``.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .application import FilesystemAnalysisRepository


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "tracetrust-postgres" / "001_initial.sql"


def _json(value: Any):
    from psycopg.types.json import Jsonb
    return Jsonb(value)


def persist_analysis(database_url: str, source_root: str | Path) -> str:
    """Persist one prepared analysis run transactionally and idempotently."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install tracetrust[postgres] to use the PostgreSQL adapter") from exc

    source = FilesystemAnalysisRepository(source_root)
    snapshot = source.snapshot()
    matches, findings = source.matches(), source.findings()
    assessments, graph = source.assessments(), source.graph()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema)
            cursor.execute(
                """INSERT INTO tt_snapshots(snapshot_id, source_system, extracted_at, schema_version,
                   exporter_version, manifest) VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (snapshot_id) DO UPDATE SET source_system=EXCLUDED.source_system,
                   extracted_at=EXCLUDED.extracted_at, schema_version=EXCLUDED.schema_version,
                   exporter_version=EXCLUDED.exporter_version, manifest=EXCLUDED.manifest""",
                (snapshot.manifest.snapshot_id, snapshot.manifest.source_system, snapshot.manifest.extracted_at,
                 snapshot.manifest.schema_version, snapshot.manifest.exporter_version,
                 _json(snapshot.manifest.model_dump(mode="json"))),
            )
            for file_entry in snapshot.manifest.files:
                cursor.execute(
                    """INSERT INTO tt_snapshot_files(snapshot_id,path,format,row_count,sha256,min_server_seq,max_server_seq)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_id,path) DO UPDATE SET
                       format=EXCLUDED.format,row_count=EXCLUDED.row_count,sha256=EXCLUDED.sha256,
                       min_server_seq=EXCLUDED.min_server_seq,max_server_seq=EXCLUDED.max_server_seq""",
                    (snapshot.manifest.snapshot_id, file_entry.path, file_entry.format, file_entry.row_count,
                     file_entry.sha256, file_entry.min_server_seq, file_entry.max_server_seq),
                )
            for event in snapshot.events:
                cursor.execute(
                    """INSERT INTO tt_events(snapshot_id,event_id,source_system,source_record_id,event_type,
                       occurred_at,original_timestamp,actor_id,organization_id,quantity,original_quantity,unit,location,raw_payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (snapshot_id,event_id) DO UPDATE SET raw_payload=EXCLUDED.raw_payload,
                       quantity=EXCLUDED.quantity, occurred_at=EXCLUDED.occurred_at""",
                    (event.snapshot_id, event.event_id, event.source_system, event.source_record_id,
                     event.event_type.value, event.timestamp, event.original_timestamp, event.actor,
                     event.organization, event.quantity, event.original_quantity, event.unit, event.location,
                     _json(event.raw_payload)),
                )
                for lot_id, role in [(lot, "input") for lot in event.input_lots] + [(lot, "output") for lot in event.output_lots]:
                    cursor.execute("INSERT INTO tt_lots(snapshot_id,lot_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                                   (event.snapshot_id, lot_id))
                    cursor.execute("""INSERT INTO tt_event_lots(snapshot_id,event_id,lot_id,role) VALUES (%s,%s,%s,%s)
                                      ON CONFLICT DO NOTHING""", (event.snapshot_id, event.event_id, lot_id, role))
                for evidence in event.evidence_refs:
                    cursor.execute("""INSERT INTO tt_evidence(snapshot_id,evidence_id,source_system,evidence_type)
                                      VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                                   (evidence.snapshot_id, evidence.source_record_id, evidence.source_system, evidence.evidence_type))
                    cursor.execute("""INSERT INTO tt_event_evidence(snapshot_id,event_id,evidence_id) VALUES (%s,%s,%s)
                                      ON CONFLICT DO NOTHING""", (event.snapshot_id, event.event_id, evidence.source_record_id))
            for match in matches:
                properties = {"components": [component.model_dump(mode="json") for component in match.components],
                              "candidate_reasons": match.candidate_reasons}
                cursor.execute(
                    """INSERT INTO tt_reconciliation_relations(match_id,left_snapshot_id,left_event_id,right_snapshot_id,
                       right_event_id,status,relation_kind,score,algorithm_version,properties) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (match_id) DO UPDATE SET score=EXCLUDED.score,status=EXCLUDED.status,properties=EXCLUDED.properties""",
                    (match.match_id, match.left_snapshot_id, match.left_event_id, match.right_snapshot_id,
                     match.right_event_id, match.status.value, match.relation_kind.value, match.score,
                     match.algorithm_version, _json(properties)),
                )
            for finding in findings:
                cursor.execute(
                    """INSERT INTO tt_findings(finding_id,snapshot_id,rule_id,severity,entity_ids,source_event_ids,finding_values,explanation,algorithm_version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (finding_id) DO UPDATE SET finding_values=EXCLUDED.finding_values,
                       severity=EXCLUDED.severity,explanation=EXCLUDED.explanation""",
                    (finding.finding_id, finding.snapshot_id, finding.rule_id, finding.severity.value,
                     _json(finding.entity_ids), _json(finding.source_event_ids), _json(finding.values),
                     finding.explanation, finding.algorithm_version),
                )
            for assessment in assessments:
                cursor.execute(
                    """INSERT INTO tt_trust_assessments(snapshot_id,entity_id,score,uncapped_score,factors,critical_penalties,explanation,algorithm_version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_id,entity_id,algorithm_version) DO UPDATE SET
                       score=EXCLUDED.score,uncapped_score=EXCLUDED.uncapped_score,factors=EXCLUDED.factors""",
                    (assessment.snapshot_id, assessment.entity_id, assessment.score, assessment.uncapped_score,
                     _json([factor.model_dump(mode="json") for factor in assessment.factors]),
                     _json(assessment.critical_penalties), assessment.explanation, assessment.algorithm_version),
                )
            cursor.execute(
                "INSERT INTO tt_analysis_runs(run_id,snapshot_id,pipeline_version,status,started_at,finished_at,metrics) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (run_id, snapshot.manifest.snapshot_id, "pipeline-v1", "succeeded", started_at,
                 datetime.now(timezone.utc), _json({"events": len(snapshot.events), "matches": len(matches),
                                                     "findings": len(findings), "graph_nodes": len(graph.nodes)})),
            )
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_url")
    parser.add_argument("source_root", type=Path)
    args = parser.parse_args()
    print(json.dumps({"run_id": persist_analysis(args.database_url, args.source_root)}, indent=2))


if __name__ == "__main__":
    main()
