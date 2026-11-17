-- TraceTrust canonical relational schema.
-- The graph is a rebuildable projection; PostgreSQL is the audit source of truth.

CREATE TABLE IF NOT EXISTS tt_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    exporter_version TEXT NOT NULL,
    manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tt_snapshot_files (
    snapshot_id TEXT NOT NULL REFERENCES tt_snapshots(snapshot_id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('jsonl', 'csv')),
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    min_server_seq BIGINT,
    max_server_seq BIGINT,
    PRIMARY KEY (snapshot_id, path)
);

CREATE TABLE IF NOT EXISTS tt_events (
    snapshot_id TEXT NOT NULL REFERENCES tt_snapshots(snapshot_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('production', 'transfer', 'receipt', 'transformation', 'split', 'merge')),
    occurred_at TIMESTAMPTZ NOT NULL,
    original_timestamp TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity >= 0),
    original_quantity TEXT NOT NULL,
    unit TEXT NOT NULL,
    location TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    PRIMARY KEY (snapshot_id, event_id),
    UNIQUE (snapshot_id, source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS tt_lots (
    snapshot_id TEXT NOT NULL REFERENCES tt_snapshots(snapshot_id) ON DELETE CASCADE,
    lot_id TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, lot_id)
);

CREATE TABLE IF NOT EXISTS tt_event_lots (
    snapshot_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    lot_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('input', 'output')),
    PRIMARY KEY (snapshot_id, event_id, lot_id, role),
    FOREIGN KEY (snapshot_id, event_id) REFERENCES tt_events(snapshot_id, event_id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id, lot_id) REFERENCES tt_lots(snapshot_id, lot_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tt_evidence (
    snapshot_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS tt_event_evidence (
    snapshot_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, event_id, evidence_id),
    FOREIGN KEY (snapshot_id, event_id) REFERENCES tt_events(snapshot_id, event_id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id, evidence_id) REFERENCES tt_evidence(snapshot_id, evidence_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tt_reconciliation_relations (
    relation_id BIGSERIAL PRIMARY KEY,
    match_id TEXT NOT NULL UNIQUE,
    left_snapshot_id TEXT NOT NULL,
    left_event_id TEXT NOT NULL,
    right_snapshot_id TEXT NOT NULL,
    right_event_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('match', 'review', 'non_match')),
    relation_kind TEXT NOT NULL CHECK (relation_kind IN ('RECORDED', 'DERIVED', 'INFERRED')),
    score NUMERIC NOT NULL CHECK (score >= 0 AND score <= 1),
    algorithm_version TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (left_snapshot_id, left_event_id) REFERENCES tt_events(snapshot_id, event_id),
    FOREIGN KEY (right_snapshot_id, right_event_id) REFERENCES tt_events(snapshot_id, event_id)
);

CREATE TABLE IF NOT EXISTS tt_findings (
    finding_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES tt_snapshots(snapshot_id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
    entity_ids JSONB NOT NULL,
    source_event_ids JSONB NOT NULL,
    finding_values JSONB NOT NULL,
    explanation TEXT NOT NULL,
    algorithm_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tt_trust_assessments (
    snapshot_id TEXT NOT NULL REFERENCES tt_snapshots(snapshot_id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    score NUMERIC NOT NULL CHECK (score >= 0 AND score <= 100),
    uncapped_score NUMERIC NOT NULL CHECK (uncapped_score >= 0 AND uncapped_score <= 100),
    factors JSONB NOT NULL,
    critical_penalties JSONB NOT NULL,
    explanation TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, entity_id, algorithm_version)
);

CREATE TABLE IF NOT EXISTS tt_analysis_runs (
    run_id UUID PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES tt_snapshots(snapshot_id) ON DELETE CASCADE,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_tt_events_snapshot_time ON tt_events(snapshot_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_tt_events_source_record ON tt_events(source_system, source_record_id);
CREATE INDEX IF NOT EXISTS idx_tt_event_lots_lot ON tt_event_lots(snapshot_id, lot_id, role);
CREATE INDEX IF NOT EXISTS idx_tt_event_evidence_event ON tt_event_evidence(snapshot_id, event_id);
CREATE INDEX IF NOT EXISTS idx_tt_relations_left ON tt_reconciliation_relations(left_snapshot_id, left_event_id);
CREATE INDEX IF NOT EXISTS idx_tt_relations_right ON tt_reconciliation_relations(right_snapshot_id, right_event_id);
CREATE INDEX IF NOT EXISTS idx_tt_findings_snapshot_severity ON tt_findings(snapshot_id, severity);
CREATE INDEX IF NOT EXISTS idx_tt_runs_snapshot_started ON tt_analysis_runs(snapshot_id, started_at DESC);
