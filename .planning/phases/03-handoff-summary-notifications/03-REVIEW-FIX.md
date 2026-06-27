---
phase: 03-handoff-summary-notifications
fixed_at: 2026-06-27T00:00:00Z
review_path: .planning/phases/03-handoff-summary-notifications/03-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-06-27
**Source review:** .planning/phases/03-handoff-summary-notifications/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (CR-01 + WR-01..WR-08)
- Fixed: 9
- Skipped: 0

All fixes were applied in an isolated git worktree, verified with `python -c ast.parse`
syntax checks and the relevant pytest modules, and committed atomically. After all
fixes the full suite was re-run: **115 passed, 1 skipped** (matching the pre-fix
baseline — no regressions).

## Fixed Issues

### CR-01: Owner notification silently dropped when the call-log DB write fails

**Files modified:** `src/bot.py`
**Commit:** b4d02c1
**Applied fix:** Restructured the end-of-call `finally` hook into three independent
stages instead of one shared `try`: (1) build summary inputs (outcome/transcript/
summary) under a guarded `try` that falls back to a safe summary, (2) persist the
call log in its own `try` that logs only the exception type on failure, (3) dispatch
the owner notification in its own `try` that **runs regardless of the DB outcome**.
A foreseeable `database is locked` / serialization error during `write()` can no
longer suppress the owner summary, which CLAUDE.md identifies as the product's core
deliverable. All exception handlers continue to log only `type(exc).__name__`
(T-03-LOGPII). **Requires human verification:** this is a control-flow/error-handling
change with no direct automated test exercising the DB-failure-then-notify path;
please confirm the three-stage ordering behaves as intended under a real persistence
failure.

### WR-01: `reservation_id` never written to flow state (call_logs.reservation_id always NULL)

**Files modified:** `src/flows/functions.py`
**Commit:** dbcbddd
**Applied fix:** In `handle_confirm_booking`, after a successful confirm, store
`fm.state["reservation_id"] = res_id` alongside `fm.state["confirmed_event_id"]`, so
the `call_logs` row's FK to `reservations` is populated on every confirmed booking.

### WR-02: Call timestamps off by one hour during Italian DST

**Files modified:** `src/bot.py`
**Commit:** 267ad1f
**Applied fix:** Replaced the fixed `timezone(offset=timedelta(hours=1))` shortcut
with `ZoneInfo("Europe/Rome")` (matching `src/flows/nodes.py`), and cleaned up the
now-unused `timedelta`/`timezone` imports. `started_at` and the notification subject
are now DST-correct. Verified `import src.bot` succeeds with `zoneinfo`.

### WR-03: Declared foreign keys not enforced (no `PRAGMA foreign_keys = ON`)

**Files modified:** `src/call_log/repository.py`
**Commit:** 6ccab78
**Applied fix:** Added `await db.execute("PRAGMA foreign_keys = ON")` after each
`aiosqlite.connect(...)` in `init_db()` and `write()`, so the documented
`IntegrityError` on an unknown `tenant_id`/`reservation_id` is actually raised.
Confirmed the existing tests still pass (their fixture seeds the `demo` tenant).

### WR-04: `_cached_messages` transcript fallback never populated (dead safety net)

**Files modified:** `src/bot.py`
**Commit:** 60e3af9
**Applied fix:** Snapshot the message list with
`_cached_messages = list(build.context.messages)` before `runner.run()` (while the
context is known-good) and corrected the misleading comment that claimed an in-`finally`
refresh that never happened. The `list(build.context.messages) or _cached_messages`
fallback now degrades to a real snapshot instead of an empty list.

### WR-05: `build_booking_node` crashes on `None` tenant

**Files modified:** `src/flows/nodes.py`
**Commit:** b8a6bdf
**Applied fix:** Made the builder null-safe like its siblings — signature changed to
`tenant: TenantConfig | None = None` and `business_name = tenant.business_name if
tenant else "la nostra struttura"`, so a `None` tenant from
`handle_route_to_booking` degrades gracefully instead of raising `AttributeError`
mid-call.

### WR-06: Telegram notifications silently dropped by Markdown parsing

**Files modified:** `src/notifications/telegram_channel.py`
**Commit:** 258d131
**Applied fix:** Removed `parse_mode: "Markdown"` and the `*...*` markup; the summary
is now sent as plain text. LLM-generated Italian containing `_`, `*`, or `[` can no
longer produce an HTTP 400 that loses the owner's summary. Notification tests pass.

### WR-07: Several tests assert tautologies

**Files modified:** `tests/test_call_log.py`, `tests/test_transfer.py`
**Commit:** 928b3e3
**Applied fix:** Tightened three inert assertions:
- `test_outcome_check_constraint`: `assert exc_info.type is sqlite3.IntegrityError`
  (was `issubclass(..., (sqlite3.IntegrityError, Exception))` — always true). Verified
  the CHECK violation raises exactly `sqlite3.IntegrityError`.
- `test_transcript_json_stores_array`: now asserts the literal accented char `"È"` is
  present **and** `"\\u00c8"` (its escape) is absent, directly exercising
  `ensure_ascii=False`. (Adapted from the review's suggested `"è"`: the fixture's
  accented char is the capital `È`/U+00C8, not lowercase `è`.)
- `test_local_transfer_stub_no_pii_in_log`: `assert "333" not in full_log`
  unconditionally (was `... or "transfer" in full_log.lower()` — always true). Safe
  because the stub only ever logs the operator number `+39 02 111222`.

### WR-08: End-of-call hook serializes full raw context, which can abort logging

**Files modified:** `src/bot.py`
**Commit:** f729724
**Applied fix:** Added a module-level `_sanitize_transcript()` helper that normalizes
context messages to plain `{role, content}` string dicts (mirroring the filter
`generate_summary` applies) and used it at the `write()` call. A non-serializable
tool-use/result block can no longer make `json.dumps` raise and drop the call-log row.
Full suite re-run green after this change.

---

_Fixed: 2026-06-27_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
