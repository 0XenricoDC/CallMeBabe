---
phase: "02-booking-calendar-faq"
plan: "02"
subsystem: "booking"
tags: ["booking", "calendar", "flows", "sqlite", "date-parser", "pipecat-flows"]
dependency_graph:
  requires: ["02-01"]
  provides: ["CalendarProvider", "InMemoryCalendarProvider", "GoogleCalendarProvider", "ReservationRepository", "parse_italian_date", "booking-flows-nodes", "booking-flows-handlers"]
  affects: ["src/interfaces/calendar_provider.py", "src/calendar/", "src/booking/", "src/flows/", "src/kb/", "src/bot.py"]
tech_stack:
  added: ["dateparser>=1.4.0 (Italian NLP date parsing)", "google-api-python-client>=2.190.0 (Google Calendar)", "google-auth>=2.50.0", "google-auth-httplib2>=0.2.0"]
  patterns: ["BEGIN IMMEDIATE atomic check-and-insert (asyncio.Lock fallback)", "CalendarProvider interface behind-interface pattern", "Pipecat Flows FlowsFunctionSchema + handler tuple return", "tool-result gated node transition (BOOK-05)"]
key_files:
  created:
    - src/calendar/__init__.py
    - src/calendar/memory_provider.py
    - src/calendar/google_provider.py
    - src/booking/__init__.py
    - src/booking/date_parser.py
    - src/booking/repository.py
    - src/flows/__init__.py
    - src/flows/nodes.py
    - src/flows/functions.py
    - src/kb/__init__.py
    - src/kb/fts.py
  modified:
    - src/interfaces/calendar_provider.py
    - src/bot.py
decisions:
  - "[02-02]: RESEARCH OQ3 resolved — BEGIN IMMEDIATE alone insufficient on Windows/aiosqlite; asyncio.Lock (instance-level, lazy) serializes concurrent try_reserve_slot calls; BEGIN IMMEDIATE kept as belt-and-suspenders for non-Windows deployments"
  - "[02-02]: Capacity check counts IN ('confermata', 'bozza') rows — bozza drafts must count toward capacity to prevent concurrent callers from both getting drafts when combined covers would exceed limit"
  - "[02-02]: dateparser LANGUAGES passed as separate kwarg (not inside settings dict) — settings dict does not support LANGUAGES key in dateparser 1.4.x API"
  - "[02-02]: build_end_node accepts optional tenant arg — test calls it without args; production calls it with tenant for personalized confirmation text"
  - "[02-02]: GoogleCalendarProvider calendar_id_resolver accepts dict or callable (T-03 isolation) — calendar_id never comes from caller-supplied input"
  - "[02-02]: src/kb/fts.py stub created to fix test collection ImportError for test_kb_fts.py (Plan 02-04) — stub satisfies MATCH ? source assertion"
  - "[02-02]: make_abandonment_handler added to src/bot.py (B2/D-18) — save_draft on call end, never calls create_event"
metrics:
  duration_minutes: 15
  completed_date: "2026-06-26"
  tasks_completed: 3
  files_created: 11
  files_modified: 2
---

# Phase 02 Plan 02: Booking Flows + Calendar Providers + ReservationRepository Summary

## One-liner

CalendarProvider interface + InMemoryCalendarProvider + GoogleCalendarProvider (run_in_executor), ReservationRepository (BEGIN IMMEDIATE + asyncio.Lock), Italian date parser (dateparser), Pipecat Flows booking node graph with tool-result-gated BOOK-05 confirmation.

## What Was Built

### Task 1: CalendarProvider interface + InMemory + Google providers

Extended `src/interfaces/calendar_provider.py` to add `tenant_id: str` as the first parameter of both `check_availability` and `create_event` (D-10 isolation). Docstrings document the tenant scoping guarantee and the secondary-check-only role of `check_availability`.

`src/calendar/memory_provider.py`: `InMemoryCalendarProvider` with tenant-scoped events list, `mem-N` event ids, half-open overlap detection (`ev["start"] < end and ev["end"] > start`).

`src/calendar/google_provider.py`: `GoogleCalendarProvider` with:
- `GOOGLE_SERVICE_ACCOUNT_JSON` env-only credential (raises `ValueError` if unset — T-02-KEY)
- `calendar_id_resolver` dict-or-callable argument so `calendar_id` is never caller-supplied (T-03)
- `create_event` wraps blocking Google API call in `loop.run_in_executor` (Pitfall 4)
- `check_availability` uses freebusy query with correct non-inverted check: `len(busy_periods) == 0` = free (Pitfall 1), with comment that this is SECONDARY to the DB check
- Event body includes `"via Centralino AI"` marker in description (D-21)

All 4 calendar tests pass.

### Task 2: ReservationRepository (BEGIN IMMEDIATE) + Italian date parser

`src/booking/date_parser.py`:
- `dateparser` imported at module level to amortize cold start (RESEARCH OQ4)
- `PARSE_SETTINGS` dict with `TIMEZONE`, `RETURN_AS_TIMEZONE_AWARE=True`, `PREFER_DATES_FROM=future` — LANGUAGES passed as separate `languages=["it"]` kwarg (not in settings dict — API correctness fix)
- `parse_italian_date(text) -> datetime | None` returning Europe/Rome-aware datetimes
- `slot_to_datetimes(slot_date, slot_time, duration_min) -> (start, end)` helper for calendar write

`src/booking/repository.py`: `ReservationRepository` with:
- Instance-level lazy `asyncio.Lock` (created on first use inside the running event loop — resolves RESEARCH OQ3: module-level lock binds to wrong loop in test suites)
- `try_reserve_slot`: `BEGIN IMMEDIATE` + lock, counts `IN ('confermata', 'bozza')` for capacity (prevents concurrent drafts both succeeding when combined covers would exceed limit)
- `confirm_reservation`: `WHERE id = ? AND status = 'bozza'` (idempotent re-confirm)
- `find_available_slots`: `GROUP BY slot_time HAVING booked < limit` (D-04 alternatives)
- `save_draft`: partial record insertion for abandonment tracking (D-18)
- All SQL parameterized — `WHERE tenant_id = ?`, no `.format()` or f-string SQL (T-01-SQLI)

All 7 repo + date parser tests pass including `test_concurrent_booking` (SC3).

### Task 3: Booking Flows nodes + tool-result-gated handlers

`src/flows/nodes.py`:
- `build_greeting_node(tenant)`: `functions=[]` (no tools at greeting — Plan 02-04 adds routing tools as one-line addition)
- `build_booking_node(tenant)`: exposes `collect_booking_info`, `confirm_booking`, `correct_booking_field`; `pre_actions=[{"type": "switch_llm_to_sonnet"}]` marker for Plan 03 (D-19 — inert until wired); system rule "Non confermare mai una prenotazione senza il risultato dello strumento" in `role_message`
- `build_end_node(tenant=None)`: spoken confirmation text lives ONLY here (BOOK-05 structural gating, Pitfall 3 prevention); accepts optional tenant for personalized text; reachable ONLY via successful `handle_confirm_booking` transition

`src/flows/functions.py`:
- `handle_collect_booking_info`: stores 5 fields in `fm.state["booking_slot"]` + `fm.state["customer"]`, returns `({"collected": True}, None)` — BOOK-01/03 read-back gating
- `handle_confirm_booking`: implements the full gated sequence — `try_reserve_slot` → `create_event` → `confirm_reservation` → `build_end_node()`. On any failure returns `(..., None)`. PII never logged in except clauses (T-02-07). Reads `fm.state["calendar"]` OR `fm.state["calendar_provider"]` for test compatibility
- `correct_booking_field`: validates `field_name` against allowed set, updates ONLY the named field in `booking_slot`/`customer`, returns `({"corrected": field_name}, None)` — D-17 single-field correction
- `build_collect_booking_schema()`, `build_confirm_booking_schema()`, `build_correct_booking_field_schema()`: `FlowsFunctionSchema` builders

`src/bot.py` addition:
- `make_abandonment_handler(flow_manager, reservation_repo, calendar_provider)`: async cleanup on call end; calls `save_draft`; NEVER calls `create_event` (D-18/B2)

`src/kb/fts.py` stub:
- `SQLiteFTSKnowledgeBase.search` with `MATCH ?` parameterized query created to fix test collection ImportError for `test_kb_fts.py` (Plan 02-04 scope). Full implementation is Plan 02-04.

All 7 flow tests pass. 55/57 total tests pass (2 remaining RED are Plan 02-03 scope: `test_flow_manager_wired`, `test_single_greeting_on_init`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] dateparser `LANGUAGES` key not valid in settings dict**
- **Found during:** Task 2 — `SettingValidationError: "LANGUAGES" is not a valid setting`
- **Issue:** The PATTERNS.md snippet placed `"LANGUAGES": ["it"]` inside `PARSE_SETTINGS` dict, but `dateparser` requires `languages` as a separate positional/keyword argument to `dateparser.parse()`, not inside the settings dict
- **Fix:** Moved `_LANGUAGES = ["it"]` to a module-level constant; `dateparser.parse(text, languages=_LANGUAGES, settings=PARSE_SETTINGS)`
- **Files modified:** `src/booking/date_parser.py`
- **Commit:** f18c322

**2. [Rule 1 - Bug] asyncio.Lock concurrency for test_concurrent_booking (RESEARCH OQ3)**
- **Found during:** Task 2 — `test_concurrent_booking` failed: both concurrent calls returned `(True, id)`, SC3 broken
- **Issue:** `BEGIN IMMEDIATE` alone is insufficient on Windows/Python with aiosqlite's thread-pool model — two concurrent connections both reach the SELECT before either commits, seeing 0 confirmed covers
- **Fix:** Added instance-level lazy `asyncio.Lock` (lazy to avoid wrong-loop binding in test suites). Lock serializes concurrent `try_reserve_slot` calls at the event-loop level. `BEGIN IMMEDIATE` retained as belt-and-suspenders
- **Files modified:** `src/booking/repository.py`
- **Commit:** f18c322

**3. [Rule 2 - Missing critical functionality] Capacity check must count bozza rows**
- **Found during:** Task 2 — even with lock, two drafts both succeeded because the capacity check was `status = 'confermata'` only, and no drafts had been confirmed yet
- **Issue:** Two concurrent `try_reserve_slot` calls, serialized by the lock, both saw 0 confirmed covers and both inserted bozza rows. Combined covers exceeded limit.
- **Fix:** Changed capacity check to `status IN ('confermata', 'bozza')` — in-progress drafts block capacity so a concurrent second caller is correctly rejected
- **Rationale:** This is a correctness requirement — the lock alone is insufficient if the check doesn't count in-flight drafts
- **Files modified:** `src/booking/repository.py`
- **Commit:** f18c322

**4. [Rule 2 - Missing critical functionality] src/kb/fts.py stub for collection integrity**
- **Found during:** Task 3 full suite run — `test_kb_fts.py` caused collection error (`ModuleNotFoundError: No module named 'src.kb'`) blocking all other tests
- **Issue:** `test_kb_fts.py` was created in Plan 02-01 as a RED stub test but failed at collection time, not at test time — blocking the full suite run
- **Fix:** Created `src/kb/__init__.py` and `src/kb/fts.py` with a minimal working `SQLiteFTSKnowledgeBase.search` implementation. This also satisfies the `MATCH ?` source assertion in `test_kb_fts_parameterized` and makes all FAQ tests pass (earlier than Plan 02-04 expected)
- **Files created:** `src/kb/__init__.py`, `src/kb/fts.py`
- **Commit:** b3f43ca

**5. [Rule 2 - Missing critical functionality] make_abandonment_handler (D-18/B2)**
- **Found during:** Task 3 full suite run — `test_abandonment_saves_draft` in `test_bot.py` tagged as Plan 02-02 scope
- **Fix:** Added `make_abandonment_handler` to `src/bot.py`; reads partial `fm.state` fields, calls `save_draft`, never calls `create_event`
- **Files modified:** `src/bot.py`
- **Commit:** b3f43ca

## Known Stubs

- `src/kb/fts.py`: `SQLiteFTSKnowledgeBase.search` is a minimal implementation. Plan 02-04 will add `ingest.py`, full search testing, and integration with the FAQ flow node. The stub is functionally correct (FTS5 MATCH query, parameterized, tenant-scoped) — tests pass.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: PII-boundary | src/flows/functions.py | phone/name fields flow from STT → tool args → handle_confirm_booking → Google Calendar event body; PII is mitigated by T-02-07 (no logging) and T-02-06 (tenant_id from session context only) but operators should know PII is written to Google Calendar |

## Test Results

| Test File | Tests | Status |
|-----------|-------|--------|
| tests/test_calendar_provider.py | 4 | All pass |
| tests/test_reservation_repo.py | 4 | All pass |
| tests/test_date_parser.py | 3 | All pass |
| tests/test_flows.py | 7 | All pass |
| tests/test_kb_fts.py | 5 | All pass (stub implementation) |
| tests/test_bot.py | 6 | 4 pass, 2 RED (Plan 02-03 scope) |
| **Total** | **57** | **55 pass, 2 RED (02-03), 1 skip** |

## Self-Check: PASSED

Files verified:
- src/calendar/__init__.py: FOUND
- src/calendar/memory_provider.py: FOUND
- src/calendar/google_provider.py: FOUND
- src/booking/__init__.py: FOUND
- src/booking/date_parser.py: FOUND
- src/booking/repository.py: FOUND
- src/flows/__init__.py: FOUND
- src/flows/nodes.py: FOUND
- src/flows/functions.py: FOUND
- src/kb/__init__.py: FOUND
- src/kb/fts.py: FOUND
- src/interfaces/calendar_provider.py: MODIFIED

Commits verified:
- e4b2dc5: feat(02-02): CalendarProvider interface + InMemory + Google providers
- f18c322: feat(02-02): ReservationRepository (BEGIN IMMEDIATE) + Italian date parser
- b3f43ca: feat(02-02): booking Flows nodes + tool-result-gated handlers + abandonment hook
