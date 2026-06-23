-- Tenant configuration schema (D-02: full nullable-aware schema from day 1).
-- Phase 1 populates only the voice-relevant fields; no ALTER TABLE per phase.
-- Structured for a clean Postgres migration (connection-string swap only) — D-01.

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
    notification_channel TEXT
);
