---
phase: 03-handoff-summary-notifications
plan: "05"
subsystem: notifications
gap_closure: SC2
tags: [notifications, multi-channel, telegram, tdd, security]
dependency_graph:
  requires: [03-03]
  provides: [SC2-gap-closure, D-11-demo-default-multi-send]
  affects: [src/notifications, src/bot.py (no change — hook already calls create_channel)]
tech_stack:
  added: [MultiNotificationChannel composite pattern]
  patterns: [per-channel failure isolation, env-only destination resolution]
key_files:
  created:
    - src/notifications/multi_channel.py
  modified:
    - src/notifications/factory.py
    - tests/test_notification.py
decisions:
  - "[03-05] MultiNotificationChannel uses public .channels list attribute for testability; factory tests inspect channel types via {type(c) for c in ch.channels}"
  - "[03-05] Demo-default multi-send gated on BOTH env vars non-empty; missing TELEGRAM_CHAT_ID alone prevents telegram leg (T-03-NINJ: never invent a destination)"
  - "[03-05] Existing test_factory_log_channel + test_factory_none_falls_back_to_log hardened with patch.dict to explicitly clear Telegram vars; they now test stable no-token behavior regardless of developer .env"
metrics:
  duration_seconds: 203
  completed_date: "2026-06-29"
  tasks_completed: 2
  tasks_pending_human: 1
  files_modified: 3
---

# Phase 03 Plan 05: SC2 Gap Closure — Demo-Default Multi-Send Summary

**One-liner:** `MultiNotificationChannel` composite routes end-of-call summaries to log + Telegram when both env vars are present; `create_channel()` demo-default auto-selects it (D-11).

## What Was Built

Gap SC2 closed: when the demo tenant's `notification_channel` is `None`/`log` AND both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in `.env`, the factory now returns `MultiNotificationChannel([LogNotificationChannel(), TelegramNotificationChannel(...)])` so the call summary is dispatched to BOTH the console log AND Telegram.

### `src/notifications/multi_channel.py` (new)

`MultiNotificationChannel(NotificationChannel)` composite:

- Constructor takes `channels: list[NotificationChannel]`, stored as `self.channels` (public for test introspection).
- `async def send(subject, body)` iterates all channels; each is wrapped in a `try/except Exception` — one channel failure never blocks the others (T-03-FIN).
- On failure: `logger.error(f"... {type(exc).__name__} in {type(channel).__name__} ...")` — never logs subject/body (T-03-LOGPII).
- Module docstring documents D-11 purpose and T-03-NINJ/T-03-LOGPII/T-03-FIN posture.

### `src/notifications/factory.py` (updated)

Demo-default branch (when `normalized` is `""` or `"log"`):
1. Reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` via `os.getenv` (env only — T-03-NINJ).
2. If **both** are non-empty: returns `MultiNotificationChannel([LogNotificationChannel(), TelegramNotificationChannel(token=..., chat_id=...)])`.
3. If either is absent/empty: returns `LogNotificationChannel()` only — no crash.

Explicit branches (`"telegram"`, `"email"`, `"sms"`) are unchanged — single-channel.

### `tests/test_notification.py` (updated)

**5 new RED→GREEN tests:**
- `test_multi_channel_is_notification_channel_subclass`
- `test_multi_channel_send_delivers_to_all_wrapped_channels`
- `test_multi_channel_isolates_per_channel_failures`
- `test_factory_none_both_telegram_vars_returns_multi_log_plus_telegram`
- `test_factory_log_both_telegram_vars_returns_multi`

**3 new stability tests** (pass in both RED and GREEN):
- `test_factory_none_no_telegram_token_returns_log_only`
- `test_factory_none_token_present_but_no_chat_id_returns_log_only`
- `test_factory_explicit_telegram_remains_single_channel`

**2 existing tests hardened** with explicit Telegram env var patching:
- `test_factory_log_channel` — now patches `TELEGRAM_BOT_TOKEN=""` and `TELEGRAM_CHAT_ID=""`
- `test_factory_none_falls_back_to_log` — same; tests the no-token fallback path reliably

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | `693be4b` | test(03-05): failing tests for MultiNotificationChannel + demo-default |
| 2 (GREEN) | `70c0736` | feat(03-05): MultiNotificationChannel + factory demo-default multi-send |

## Test Results

```
tests/test_notification.py: 20 passed (was 15 before this plan)
Full suite: 123 passed, 1 skipped, 0 failures
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Correctness] Hardened two existing factory tests against Telegram env vars**

- **Found during:** Task 1 (RED) analysis
- **Issue:** `test_factory_log_channel` and `test_factory_none_falls_back_to_log` did not patch Telegram env vars. After GREEN implementation, a developer running tests with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set in their shell would see those tests fail (returning `MultiNotificationChannel` instead of `LogNotificationChannel`). Pytest does not auto-load `.env`, so this is a risk only in shells with exported env vars, but it must be addressed for test correctness.
- **Fix:** Added `patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}, clear=False)` to both tests.
- **Files modified:** `tests/test_notification.py`
- **Commit:** `693be4b` (RED commit — these changes committed with the RED tests)

## Checkpoint: Human Verification Required

**Task 3** is a `checkpoint:human-verify` gate. The automated code + tests are complete. Live end-to-end verification is pending.

**What to verify:**
1. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`; leave demo tenant's `notification_channel` unset.
2. Run `python main.py --tenant=demo`, complete (or abandon) one call, hang up.
3. Confirm console `[CALL LOG] Chiamata DD/MM HH:MM — <Outcome>` AND same summary arrives via Telegram.
4. Remove `TELEGRAM_BOT_TOKEN` from `.env`, repeat: confirm `[CALL LOG]` still appears, no crash (log-only fallback).

## Known Stubs

None — `MultiNotificationChannel` and `create_channel()` demo-default are fully wired; no hardcoded empty values or placeholders in the notification path.

## Threat Flags

No new network endpoints, auth paths, or schema changes introduced. The factory's demo-default branch adds a code path that constructs `TelegramNotificationChannel` from env — this is an existing surface (the `"telegram"` branch already did this). The new surface is:

| Flag | File | Description |
|------|------|-------------|
| threat_flag: automatic-channel-activation | src/notifications/factory.py | Telegram is now activated automatically for the demo default when both env vars are non-empty — no explicit opt-in by the tenant config. Mitigated: both vars required; factory is sole env reader (T-03-NINJ); per-channel isolation (T-03-FIN). |

## Self-Check: PASSED

Files exist:
- `src/notifications/multi_channel.py` — confirmed created
- `src/notifications/factory.py` — confirmed updated
- `tests/test_notification.py` — confirmed updated

Commits exist:
- `693be4b` — RED test commit
- `70c0736` — GREEN feat commit
