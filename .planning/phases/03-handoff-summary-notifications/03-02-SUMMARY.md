---
phase: 03-handoff-summary-notifications
plan: 02
subsystem: call_log
tags: [call-log, persistence, summary, llm, sqlite, tdd, notif-01, notif-02]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: TenantConfig (model field), aiosqlite patterns, schema.sql idempotency
  - phase: 02-booking-calendar-faq
    provides: reservations table (FK target), ReservationRepository pattern, seed_demo
  - phase: 03-plan-01
    provides: outcome='trasferito' flow state (handled by _determine_outcome Rule 1)
provides:
  - call_logs SQLite table with 5-value outcome CHECK (NOTIF-01, D-06, D-08)
  - CallLogRepository.write() — parameterized INSERT + lastrowid (T-03-SQLI)
  - _determine_outcome(state) — flow-state → taxonomy derivation (D-06)
  - generate_summary(tenant, transcript, outcome) — LLM Italian summary (NOTIF-02, D-05)
affects: [phase-03-plan-03, phase-03-plan-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CallLogRepository mirrors TenantRepository init_db() + ReservationRepository INSERT/lastrowid"
    - "_determine_outcome: 5-priority logic (explicit > confirmed_event_id > faq_answered > booking_slot-only > default faq)"
    - "generate_summary: direct anthropic.AsyncAnthropic SDK call (not via FlowManager — torn down post-runner)"
    - "PII-safe except: logs only type(exc).__name__; never transcript/name/phone (T-03-PII)"

key-files:
  created:
    - src/call_log/__init__.py
    - src/call_log/repository.py
    - src/call_log/summary.py
    - tests/test_call_log.py
    - tests/test_summary.py
  modified:
    - src/db/schema.sql

key-decisions:
  - "Task 2 implemented generate_summary alongside _determine_outcome in summary.py (both naturally in same file); test_summary.py went GREEN in Task 2 rather than Task 3 — no functional impact, all tests pass"
  - "CallLogRepository.write() uses cursor.lastrowid (not SELECT last_insert_rowid()) — direct aiosqlite cursor property, matches execute() return value"
  - "transcript_json stored with ensure_ascii=False so Italian characters survive the round-trip"
  - "generate_summary uses tenant.model exclusively — no hardcoded competing model id (CLAUDE.md constraint, A2)"

# Metrics
duration: ~6 min
completed: 2026-06-27
---

# Phase 3 Plan 02: Call Log Persistence + Summary Summary

**`call_logs` SQLite table, `CallLogRepository.write()` with parameterized SQL, `_determine_outcome` flow-state derivation, and PII-safe `generate_summary` via direct Anthropic SDK — the persistence and summary building blocks for the end-of-call hook (Plan 03-03).**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-27T11:53:59Z
- **Completed:** 2026-06-27T12:00:41Z
- **Tasks:** 3 of 3 complete
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments

- `src/db/schema.sql` extended with `call_logs` table: `id`, `tenant_id` (FK), `started_at/ended_at/created_at` ISO timestamps, `duration_secs`, `outcome TEXT NOT NULL CHECK(outcome IN ('prenotato','faq','trasferito','abbandonato','fallito'))`, `transcript_json TEXT NOT NULL` (Postgres-JSONB-compatible), `summary_text`, `reservation_id` (FK to reservations), `google_event_id`, `transfer_number`, `channel_sent`; plus `idx_call_logs_tenant` on `(tenant_id, started_at)`. Schema validates against a fresh `:memory:` SQLite DB.
- `CallLogRepository` (`src/call_log/repository.py`): `init_db()` (reads shared schema.sql, idempotent) and `write(*)` that inserts one row and returns `cursor.lastrowid`. All SQL parameterized with `?` (T-03-SQLI); `transcript_json` serialized via `json.dumps(ensure_ascii=False)`.
- `_determine_outcome(state: dict) -> str` (`src/call_log/summary.py`): implements the 5-priority logic from RESEARCH Pattern 5. Correctly handles the `outcome='trasferito'` state set by Plan 03-01's `handle_transfer_call`.
- `generate_summary(tenant, transcript, outcome)` (`src/call_log/summary.py`): direct `anthropic.AsyncAnthropic().messages.create()` call (not via FlowManager — torn down after `runner.run()`). Uses `tenant.model` (no hardcoded id), API key via `os.getenv("ANTHROPIC_API_KEY")` (T-03-KEY). Exception path logs only `type(exc).__name__` (T-03-PII) and returns `"Riepilogo non disponibile (esito: {outcome})."`.
- **14 new tests** (9 in test_call_log.py, 5 in test_summary.py), all GREEN. Full suite: **91 passed, 1 skipped** — no regression.

## Task Commits

1. **Task 1: Failing call_log/summary tests + call_logs schema (RED)** — `8774aed` (test)
2. **Task 2: CallLogRepository.write() + _determine_outcome + generate_summary (GREEN)** — `58858c2` (feat)
3. **Task 3: generate_summary verification** — covered by Task 2 commit (see Deviations)

## Files Created/Modified

- `src/db/schema.sql` — appended call_logs table DDL + idx_call_logs_tenant index.
- `src/call_log/__init__.py` — package marker.
- `src/call_log/repository.py` — `CallLogRepository` with `init_db()` + `write()`.
- `src/call_log/summary.py` — `_determine_outcome` + `generate_summary`.
- `tests/test_call_log.py` — 9 tests: row round-trip, CHECK constraint rejection, JSON Italian chars, 6 _determine_outcome cases.
- `tests/test_summary.py` — 5 tests: mocked success, exception fallback, PII-safe log, tenant.model forwarding, env key.

## Decisions Made

- **generate_summary in Task 2:** Both `_determine_outcome` and `generate_summary` naturally belong in `summary.py`. Implementing them together in Task 2 is cleaner than creating a half-file and adding to it in Task 3. All tests pass in both files.
- **cursor.lastrowid:** aiosqlite's `cursor.lastrowid` is the idiomatic way to retrieve the last insert rowid from an `execute()` call. The alternative `SELECT last_insert_rowid()` is an additional round-trip.
- **`ensure_ascii=False`:** Italian characters (à, è, ì, ò, ù) must survive the JSON round-trip to be readable in notification bodies and summaries.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] generate_summary implemented in Task 2 instead of Task 3**
- **Found during:** Task 2 (creating summary.py)
- **Issue:** The plan split `_determine_outcome` (Task 2) and `generate_summary` (Task 3) into separate implementation tasks for the same file. Implementing both functions together is structurally natural and produces a complete, coherent module.
- **Fix:** Created the full `summary.py` with both functions in Task 2. Task 3 became a verification step (no additional code needed).
- **Files modified:** src/call_log/summary.py
- **Impact:** Test_summary.py went GREEN in Task 2 rather than Task 3. All TDD gate commits are present: test commit (8774aed) before feat commit (58858c2). No functional scope creep.

## Known Stubs

None — `CallLogRepository.write()` is a real parameterized INSERT (not a stub). `generate_summary` makes a real Anthropic SDK call (mocked only in tests). No placeholder values flow to UI rendering.

## Threat Flags

No new security surface beyond what the plan's threat model covers (T-03-SQLI, T-03-PII, T-03-KEY, T-03-PIIDB). All three mitigate-disposition threats have been addressed:
- T-03-SQLI: parameterized `?` in all SQL; transcript via json.dumps (verified in tests).
- T-03-PII: except path logs only `type(exc).__name__`; test_generate_summary_fallback_no_pii_logged asserts no PII leaks.
- T-03-KEY: `api_key=os.getenv("ANTHROPIC_API_KEY")`; test_generate_summary_key_from_env asserts the env value is forwarded.

T-03-PIIDB (transcript stored as-is) is accepted per the threat register — retention/access-control deferred to Phase 5 (A7).

## Self-Check: PASSED

Files verified present:
- FOUND: src/call_log/__init__.py
- FOUND: src/call_log/repository.py
- FOUND: src/call_log/summary.py
- FOUND: tests/test_call_log.py
- FOUND: tests/test_summary.py
- FOUND: src/db/schema.sql (call_logs table + index appended)

Commits verified in git history:
- FOUND: 8774aed (RED — test)
- FOUND: 58858c2 (GREEN — feat)

Test results: 91 passed, 1 skipped (full suite green)
Schema: executescript on fresh sqlite DB → OK
