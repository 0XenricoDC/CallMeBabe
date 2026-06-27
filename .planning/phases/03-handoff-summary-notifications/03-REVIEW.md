---
phase: 03-handoff-summary-notifications
reviewed: 2026-06-27T00:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - src/bot.py
  - src/call_log/__init__.py
  - src/call_log/repository.py
  - src/call_log/summary.py
  - src/db/schema.sql
  - src/flows/functions.py
  - src/flows/nodes.py
  - src/notifications/__init__.py
  - src/notifications/email_channel.py
  - src/notifications/factory.py
  - src/notifications/log_channel.py
  - src/notifications/sms_channel.py
  - src/notifications/telegram_channel.py
  - src/pipeline/build.py
  - src/pipeline/factory.py
  - src/pipeline/fallback.py
  - src/pipeline/stt_switcher.py
  - src/telephony/__init__.py
  - src/telephony/base.py
  - src/telephony/stub.py
  - tests/test_call_log.py
  - tests/test_fallback.py
  - tests/test_notification.py
  - tests/test_pipeline.py
  - tests/test_stt_switcher.py
  - tests/test_summary.py
  - tests/test_transfer.py
  - tests/test_watchdog.py
findings:
  critical: 1
  warning: 8
  info: 8
  total: 17
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-27
**Depth:** standard
**Files Reviewed:** 24 (source + tests)
**Status:** issues_found

## Summary

Phase 3 adds the end-of-call hook (transcript → summary → call-log row → owner
notification), the multi-channel notification layer, the global transfer
function, STT failover, the error-fallback observer, and the dead-air watchdog.

Security posture is good on the items the brief flagged: no hardcoded secrets
(all keys via `os.getenv`), transfer/notification targets are resolved
exclusively from trusted config/env (never caller input — `handle_transfer_call`
ignores `args["transfer_number"]`), SQL is fully parameterized in
`CallLogRepository`, and the `try/finally` shutdown hook catches all exceptions
and logs only `type(exc).__name__`.

However the end-of-call hook has an ordering defect that silently drops the
product's core deliverable (the owner summary) on a foreseeable DB error, plus
several state fields the schema documents are never actually populated
(`reservation_id`, `faq_answered`), a DST timezone bug in call timestamps, an
unenforced foreign-key configuration, and several tests whose assertions are
tautologically true (they do not test what they claim).

## Critical Issues

### CR-01: Owner notification is silently dropped when the call-log DB write fails

**File:** `src/bot.py:476-517`
**Issue:** Inside the end-of-call `finally` block, summary generation, the DB
write, and the notification dispatch all share one `try`. The notification
(`channel.send`) runs *after* `call_log_repo.write(...)`. If `write()` raises —
which is foreseeable: this is multi-tenant SQLite (`aiosqlite`) and concurrent
calls writing the same file produce `database is locked` / `OperationalError`,
and `json.dumps(transcript)` can also raise on non-serializable content blocks —
control jumps to the outer `except` (line 519) which only logs the exception
type. The notification is never attempted. Per CLAUDE.md the end-of-call summary
to the owner is the core value of the product; losing it on a transient DB
error defeats the feature while leaving no operator-visible trace beyond an
exception class name.
**Fix:** Decouple the notification from the persistence step so a DB failure
cannot suppress the owner summary:
```python
# generate summary first (already PII-safe with its own fallback)
summary_text = await generate_summary(tenant, transcript, outcome)

# persist — failure here must NOT block the notification
try:
    call_log_repo = CallLogRepository(db_path=repo_path)
    await call_log_repo.init_db()
    await call_log_repo.write(...)
except Exception as db_exc:  # noqa: BLE001
    logger.error(f"call_log write failed for tenant {tenant.id!r}: {type(db_exc).__name__}")

# notify — runs regardless of the DB outcome
try:
    channel = create_channel(tenant.notification_channel, tenant)
    await channel.send(subject, summary_text)
except Exception as ch_exc:  # noqa: BLE001
    logger.error(f"Notification dispatch failed for tenant {tenant.id!r}: {type(ch_exc).__name__}")
```

## Warnings

### WR-01: `reservation_id` is never written to flow state, so `call_logs.reservation_id` is always NULL

**File:** `src/bot.py:494`, `src/flows/functions.py:278-363`
**Issue:** `bot.py` reads `flow_manager.state.get("reservation_id")` for the
call-log row, and `schema.sql:90` documents that column as "set for
'prenotato'". But `handle_confirm_booking` captures `res_id` locally
(`ok, res_id = await repo.try_reserve_slot(...)`) and never stores it in
`fm.state`. The FK link from `call_logs` to `reservations` is therefore lost on
every confirmed booking.
**Fix:** In `handle_confirm_booking`, after a successful confirm, set
`fm.state["reservation_id"] = res_id` alongside `fm.state["confirmed_event_id"]`.

### WR-02: Call timestamps are off by one hour during Italian DST

**File:** `src/bot.py:53` (`_ROME_TZ = timezone(offset=timedelta(hours=1))`),
used at `src/bot.py:456` and `src/bot.py:506`
**Issue:** A fixed UTC+1 offset is wrong for ~7 months of the year (Italy is
UTC+2 under DST). The review date itself (2026-06-27) is during DST, so
`started_at` stored in `call_logs` and the human-readable notification subject
both show a time one hour earlier than reality. This is also inconsistent with
`src/flows/nodes.py:27` which correctly uses `ZoneInfo("Europe/Rome")` for the
booking node's "today" calculation — the same call can compute two different
"current" hours.
**Fix:** Use `from zoneinfo import ZoneInfo; _ROME_TZ = ZoneInfo("Europe/Rome")`
as `nodes.py` already does; drop the fixed-offset shortcut.

### WR-03: Declared foreign keys are not enforced (no `PRAGMA foreign_keys = ON`)

**File:** `src/call_log/repository.py:34-43`, `src/db/schema.sql:82,90`
**Issue:** `call_logs.tenant_id` and `call_logs.reservation_id` declare
`REFERENCES`, and `write()`'s docstring (lines 74-76) claims an
`IntegrityError` is raised "if ... tenant_id does not exist (FK constraint)".
SQLite disables FK enforcement by default and nothing in `init_db`/`write`
issues `PRAGMA foreign_keys = ON`, so a call log can be written for a
non-existent tenant and the documented behavior never occurs. (The CHECK
constraint on `outcome` is enforced regardless, so only the FK claim is false.)
**Fix:** Execute `await db.execute("PRAGMA foreign_keys = ON")` after each
`aiosqlite.connect(...)` in the repository, or remove the FK-enforcement claim
from the docstring if enforcement is intentionally deferred.

### WR-04: `_cached_messages` transcript fallback is never populated (dead safety net)

**File:** `src/bot.py:458-461,482`
**Issue:** The comment promises "We update this cache inside the finally block
using the live context if available (A4)", but `_cached_messages` is assigned
`[]` once and never written again. The fallback
`list(build.context.messages) or _cached_messages` therefore degrades to an
empty list whenever the context has been torn down — the exact scenario the
cache was meant to cover — and the summary/transcript silently become empty.
**Fix:** Populate the cache while the context is known-good (e.g. immediately
before `runner.run()` and/or refresh it during the run), or remove the dead
variable and its misleading comment.

### WR-05: `build_booking_node` crashes on `None` tenant while sibling builders are null-safe

**File:** `src/flows/nodes.py:71-105`, called from `src/flows/functions.py:667-673`
**Issue:** `build_faq_node` and `build_end_node` accept `tenant: TenantConfig | None`
and guard the `None` case, but `build_booking_node(tenant)` dereferences
`tenant.business_name` unconditionally. `handle_route_to_booking` passes
`fm.state.get("tenant")`, which is typed/treated as possibly `None` elsewhere; if
it is ever `None`, the booking transition raises `AttributeError` mid-call
instead of degrading gracefully. The inconsistency is a latent crash.
**Fix:** Make `build_booking_node` null-safe the same way the other builders are:
`business_name = tenant.business_name if tenant else "la nostra struttura"`.

### WR-06: Telegram notifications can be silently dropped by Markdown parsing

**File:** `src/notifications/telegram_channel.py:53-71`
**Issue:** The summary is sent with `parse_mode: "Markdown"`. LLM-generated
Italian summaries routinely contain characters Telegram treats as Markdown
(`_`, `*`, `[`). Unbalanced markup makes the Bot API return HTTP 400; the code
logs a warning and returns, so the owner never receives that call's summary.
**Fix:** Send as plain text (omit `parse_mode`) or escape the body for
MarkdownV2 before sending.

### WR-07: Several tests assert tautologies and do not test what their names claim

**File:** `tests/test_call_log.py:116-118,154`, `tests/test_transfer.py:202-204`
**Issue:**
- `test_outcome_check_constraint` asserts
  `issubclass(exc_info.type, (sqlite3.IntegrityError, Exception))` — every
  exception subclasses `Exception`, so this branch is always true and the test
  would pass even if an unrelated error were raised.
- `test_transcript_json_stores_array` asserts
  `"è" in raw or json.loads(raw)[1]["content"].count("?") >= 1`; the fixture
  content ends in "?", so the right operand is always true and the
  `ensure_ascii=False` guarantee is never actually exercised.
- `test_local_transfer_stub_no_pii_in_log` asserts
  `"333" not in full_log or "transfer" in full_log.lower()`; the stub always
  logs the word "transfer", so this PII check can never fail.
**Fix:** Tighten the assertions: assert `exc_info.type is sqlite3.IntegrityError`
(or `aiosqlite.IntegrityError`); assert `"è" in raw` (and that the escaped form
`\\u00e8` is absent); assert the raw phone digits are absent unconditionally
(`assert "333 1234567" not in full_log`).

### WR-08: End-of-call hook serializes the full raw context, which can abort logging

**File:** `src/bot.py:482-502`, `src/call_log/repository.py:81`
**Issue:** `transcript = list(build.context.messages)` is passed straight to
`json.dumps(..., ensure_ascii=False)` in `write()`. Unlike `generate_summary`
(which defensively filters to `isinstance(content, str)` turns), the repository
serializes whatever the context holds. If any message carries a
non-JSON-serializable object (tool-use/result blocks, frames), `json.dumps`
raises and — combined with CR-01's shared `try` — drops the call log and the
notification. Even after CR-01 is fixed, the log row is lost.
**Fix:** Normalize/sanitize the transcript to plain `{role, content}` string
dicts before persisting (reuse the same filter `generate_summary` applies), and
wrap serialization defensively.

## Info

### IN-01: `faq_answered` is read but never set — `_determine_outcome` rule 3 is unreachable

**File:** `src/call_log/summary.py:47-48`, `src/flows/functions.py:442-492`
**Issue:** `_determine_outcome` branches on `state.get("faq_answered")`, but no
code path ever assigns `faq_answered` (the FAQ handler sets
`faq_transfer_offered` instead). The rule is dead; a successful FAQ falls through
to the rule-5 default which is also `"faq"`, so the outcome is correct only by
coincidence and "answered" vs "no booking attempted" can never be distinguished.
**Fix:** Set `fm.state["faq_answered"] = True` in `handle_faq_lookup` on a
successful config/KB answer, or remove the unreachable rule.

### IN-02: `call_logs.duration_secs` is never computed; `ended_at` is UTC while `started_at` is Rome-local

**File:** `src/db/schema.sql:84-85`, `src/call_log/repository.py:45-105`
**Issue:** `duration_secs` is declared but never written (always NULL).
Separately, `ended_at` defaults to SQLite `datetime('now')` (UTC, no offset)
while `started_at` is written as a Rome-offset ISO string, so any future
duration computation across the two columns would be wrong.
**Fix:** Either compute and store `duration_secs` from a monotonic call timer,
or store both timestamps in the same timezone basis; drop the column if unused.

### IN-03: `make_greeting_handler` is dead code

**File:** `src/bot.py:278-308`
**Issue:** The factory is fully implemented and documented but never registered
in `bot()` (the greeting now comes from the FlowManager greeting node). It is
unused production code that can drift out of sync.
**Fix:** Remove it, or add a comment-referenced test that pins its
backward-compat intent.

### IN-04: Private-attribute access couples `bot.py` to `TenantRepository` internals

**File:** `src/bot.py:388`
**Issue:** `repo_path = repo._db_path if hasattr(repo, "_db_path") else "centralino.db"`
reaches into a private attribute and silently falls back to a different default
DB path if it is ever renamed — meaning call logs could be written to a
different database than tenant config reads from, with no error.
**Fix:** Expose a public `db_path` property on `TenantRepository` and use it.

### IN-05: Watchdog timer constants are duplicated across modules

**File:** `src/bot.py:61` (`_WATCHDOG_T2`) and `src/pipeline/factory.py:143-144`
(`_WATCHDOG_T1`/`_WATCHDOG_T2`)
**Issue:** `_WATCHDOG_T2 = 8.0` is defined independently in two files; the
comment admits it "mirrors factory.py". Divergent edits would desynchronize T2
between the aggregator config and the escalation handler.
**Fix:** Define the watchdog timers once (e.g. in `factory.py`) and import them
into `bot.py`.

### IN-06: `LogNotificationChannel` persists PII summaries to plaintext logs

**File:** `src/notifications/log_channel.py:36`
**Issue:** As the default channel it logs `subject` + `body` at INFO. The body
is the LLM summary, which by design names the caller. This is the channel's
purpose, but combined with the project-wide "no PII in logs" stance it means PII
lives in plaintext application logs whenever the default channel is used. Worth
an explicit decision/retention note rather than an implicit default.
**Fix:** Document the PII-in-logs tradeoff for the default channel, or route the
summary to a dedicated restricted log sink.

### IN-07: Redundant local re-imports

**File:** `src/bot.py:103-108` (re-imports `TTSSpeakFrame` already imported at
line 24), `src/flows/functions.py:455,639,671` (re-import `TenantConfig`
per-handler)
**Issue:** Symbols already imported at module top are re-imported inside
functions. Harmless but noisy; the local `TTSSpeakFrame` re-import shadows the
module-level one for no reason.
**Fix:** Drop the redundant local imports where the symbol is already at module
scope.

### IN-08: Cross-module import of a private function

**File:** `src/bot.py:35`
**Issue:** `from src.call_log.summary import _determine_outcome` imports a
leading-underscore (private-by-convention) symbol across package boundaries,
which `tests/test_call_log.py` also does. If it is part of the module's public
contract it should not be underscore-prefixed.
**Fix:** Rename to `determine_outcome` and export it via `call_log/__init__.py`.

---

_Reviewed: 2026-06-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
