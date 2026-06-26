-- Tenant configuration schema (D-02: full nullable-aware schema from day 1).
-- Phase 1 populates only the voice-relevant fields; no ALTER TABLE per phase.
-- Structured for a clean Postgres migration (connection-string swap only) — D-01.
--
-- Phase 2 additions (Plan 02-01):
--   - calendar_id column added to tenants (D-11)
--   - reservations table (D-22)
--   - kb_documents + kb_chunks FTS5 tables (D-06, D-07)
--
-- Dev DB migration note (D-11 / Pitfall 5):
--   The Phase 1 dev DB predates calendar_id. To migrate a local dev database,
--   run: ALTER TABLE tenants ADD COLUMN calendar_id TEXT;
--   Or simply delete centralino.db and re-seed: python -m src.db.seed_demo
--   (The ALTER is NOT included here to preserve idempotency on re-run — running
--   ALTER TABLE on a table that already has the column raises OperationalError.)

CREATE TABLE IF NOT EXISTS tenants (
    id              TEXT PRIMARY KEY,
    business_name   TEXT NOT NULL,
    greeting        TEXT NOT NULL,
    voice_id        TEXT NOT NULL,
    language        TEXT DEFAULT 'it',
    system_prompt   TEXT NOT NULL,
    model           TEXT DEFAULT 'claude-haiku-4-5',
    hours           TEXT,
    services        TEXT,
    booking_rules   TEXT,
    transfer_number TEXT,
    kb_ref          TEXT,
    notification_channel TEXT,
    calendar_id     TEXT
);

-- Reservations: authoritative capacity source (D-22).
-- status IN ('confermata', 'bozza') — bozza for drafts/abandoned bookings (D-18).
-- google_event_id is NULL until a Calendar write succeeds (BOOK-05 gating).
-- covers > 0 CHECK prevents zero-person reservations.
CREATE TABLE IF NOT EXISTS reservations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       TEXT NOT NULL REFERENCES tenants(id),
    slot_date       TEXT NOT NULL,
    slot_time       TEXT NOT NULL,
    covers          INTEGER NOT NULL CHECK(covers > 0),
    name            TEXT NOT NULL,
    phone           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'bozza' CHECK(status IN ('confermata', 'bozza')),
    google_event_id TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Index for capacity check queries and slot lookup (BOOK-02, SC3).
CREATE INDEX IF NOT EXISTS idx_res_slot ON reservations(tenant_id, slot_date, slot_time, status);

-- KB document metadata (D-06, D-07).
CREATE TABLE IF NOT EXISTS kb_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT NOT NULL,
    filename    TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- KB full-text search virtual table (D-07, FAQ-01, FAQ-03).
-- FTS5 virtual tables do NOT support PRIMARY KEY, UNIQUE, or external indexes.
-- tenant_id UNINDEXED: used as a WHERE filter, not tokenized for search.
-- tokenize = "unicode61": handles Italian accented characters correctly.
CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks USING fts5(
    tenant_id UNINDEXED,
    doc_id    UNINDEXED,
    chunk_id  UNINDEXED,
    content,
    tokenize  = "unicode61"
);
