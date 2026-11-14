-- TraceTrust phase 1: export queries for the currently implemented TRACOP schema.
-- Execute using a dedicated PostgreSQL role with SELECT-only grants.
-- Do not export the raw identifiers/result set directly into the TraceTrust repo:
-- pseudonymize provider/user IDs and generalize location in the exporter first.
-- Run all statements in one REPEATABLE READ, READ ONLY transaction for a consistent snapshot.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- Categories: preserve the hierarchy and source timestamps.
SELECT id, name, parent_id, depth, created_at, updated_at, deleted_at
FROM catalog.categories
ORDER BY id;

-- Products: attributes are JSON and require allowlist review before export.
-- Initial export omits attributes/search_text to avoid uncontrolled free-form content.
SELECT id, category_id, name, unit, created_at, updated_at, deleted_at
FROM catalog.products
ORDER BY id;

-- Lots: provider_id is a source identifier used only to create a stable pseudonym.
-- Coordinates are deliberately omitted. Export raw UUID only to restricted staging.
SELECT id, provider_id, product_id, quantity::text AS quantity, unit,
       available_from, available_until, status, version, created_at, updated_at, deleted_at
FROM catalog.lots
ORDER BY id;

-- Resolve only the public geography and role. Exclude names, phones, descriptions,
-- exact profile coordinates, channel identifiers, and all authentication fields.
SELECT u.id AS provider_source_id, u.role, p.municipality, p.department
FROM identity.users AS u
LEFT JOIN identity.provider_profiles AS p ON p.user_id = u.id
WHERE u.role IN ('producer', 'supplier')
ORDER BY u.id;

-- Photo evidence metadata only; media_ref is intentionally excluded.
SELECT id, lot_id, state, position, content_type, size_bytes, created_at, deleted_at
FROM catalog.lot_photos
ORDER BY lot_id, position, id;

-- Sync log is restricted to supported catalog entities. Payload is intentionally
-- omitted from the initial export; occurred_at/server_seq/op remain useful metadata.
SELECT server_seq, entity, entity_id, op, owner_user_id, occurred_at
FROM sync.change_log
WHERE entity IN ('category', 'product', 'lot')
ORDER BY server_seq;

-- Outbox payload is open JSON and may contain arbitrary content. Export metadata only
-- in phase 1; payload allowlisting requires source-code review and a separate contract.
SELECT id, aggregate, type, created_at, published_at
FROM shared.outbox_events
ORDER BY created_at, id;

-- Record source coverage in the manifest (run in the same transaction).
SELECT min(server_seq) AS min_server_seq, max(server_seq) AS max_server_seq,
       count(*) AS row_count
FROM sync.change_log;

COMMIT;
