---
phase: 03-handoff-summary-notifications
plan: 03
subsystem: notifications
tags: [notifications, channels, factory, end-of-call-hook, telegram, email, smtp, aiohttp, notif-03, notif-04, notif-05]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: NotificationChannel ABC seam (src/interfaces/notification_channel.py), TenantConfig (notification_channel field)
  - phase: 03-plan-01
    provides: outcome='trasferito' flow state + transfer_payload (consumed by end-of-call hook)
  - phase: 03-plan-02
    provides: CallLogRepository.write(), _determine_outcome(state), generate_summary(tenant, transcript, outcome)
provides:
  - Four concrete NotificationChannel impls (log REAL, telegram REAL, email code-complete, sms/whatsapp stub) — D-09, D-10
  - NotificationChannelFactory.create_channel(name, tenant) — per-tenant channel selection (NOTIF-05, D-11)
  - End-of-call try/finally hook in bot.py — dispatches a summary notification for EVERY call and outcome (NOTIF-03, D-07)
  - .env.example extended with Telegram + SMTP credential placeholders + setup steps (SETUP-01)
affects: [phase-03-plan-04, phase-04-telnyx, phase-05-multi-tenant]

# Tech tracking
tech-stack:
  added:
    - "aiosmtplib>=5.1.2 (email channel; STARTTLS SMTP send)"
  patterns:
    - "NotificationChannelFactory mirrors get_stt_provider: name->branch dispatch with LogNotificationChannel fallback (D-11)"
    - "Channel credentials sourced ONLY via os.getenv in the factory; channel objects never read env themselves (T-03-NINJ)"
    - "End-of-call hook as try/finally around runner.run() — guarantees dispatch for every outcome (D-07)"
    - "PII-safe except in every channel: logs type(exc).__name__ (+ HTTP status for telegram) only, never subject/body (T-03-LOGPII)"

key-files:
  created:
    - src/notifications/__init__.py
    - src/notifications/log_channel.py
    - src/notifications/telegram_channel.py
    - src/notifications/email_channel.py
    - src/notifications/sms_channel.py
    - src/notifications/factory.py
    - tests/test_notification.py
  modified:
    - .env.example
    - src/bot.py

key-decisions:
  - "create_channel reads creds via os.getenv only; unknown/None channel name falls back to LogNotificationChannel (D-11)"
  - "End-of-call try/finally fires for EVERY call/outcome (D-07); order: _determine_outcome -> generate_summary -> CallLogRepository.write -> create_channel -> channel.send"
  - "channel.send failure inside finally is caught + logged by type only — call shutdown never blocked (T-03-FIN)"
  - "ROME_TZ uses a fixed UTC+1 timedelta (no pytz/zoneinfo dep in Phase 3); Phase 4+ may upgrade to zoneinfo.ZoneInfo('Europe/Rome') for DST"
  - "transcript captured from build.context.messages with fallback to cached list if context torn down post-runner (A4)"

requirements-completed: [NOTIF-03, NOTIF-04, NOTIF-05]

# Metrics
duration: ~10min
completed: 2026-06-27
---

# Phase 3 Plan 03: Notification Channels + End-of-Call Hook Summary

**Four `NotificationChannel` concrete channels (log REAL, telegram REAL via aiohttp, email via aiosmtplib code-complete, sms/whatsapp stub) behind a `NotificationChannelFactory`, wired into an end-of-call `try/finally` hook in `bot.py` that — for every call and every outcome — determines the outcome, generates the Italian summary, writes the call_log row, and dispatches the notification on the tenant's configured channel.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-27T14:02:00Z (approx)
- **Completed (automated tasks):** 2026-06-27T14:12:00Z
- **Tasks:** 2 of 3 complete (Task 3 = live human-verify SC2, PENDING)
- **Files modified:** 9 (7 created, 2 modified)

## Accomplishments

- **Four channel classes** behind the existing `NotificationChannel` ABC, each importing only the ABC (never each other):
  - `LogNotificationChannel` — zero-dependency default; writes `[CALL LOG] {subject}\n{body}` via loguru (D-10 REAL default).
  - `TelegramNotificationChannel(token, chat_id)` — posts to the Bot API `sendMessage` endpoint via `aiohttp.ClientSession` with a 10s timeout; on non-200 logs the status code only, never the body (D-10 REAL).
  - `EmailNotificationChannel(host, port, user, password, to, from_)` — sends an `email.message.EmailMessage` via `aiosmtplib.send(..., start_tls=True)` (code-complete; tested with mocked SMTP, live test when keys arrive).
  - `SMSNotificationChannel` — Phase 3 stub: logs `[SMS STUB]` at DEBUG and makes NO external API call (also serves the `whatsapp` channel name).
- **`NotificationChannelFactory.create_channel(name, tenant)`** mirrors `get_stt_provider`: lowercases the name, dispatches `telegram`/`email`/`sms`/`whatsapp` to the matching class, and falls back to `LogNotificationChannel` for `log`/unknown/`None` (D-11). All credentials read via `os.getenv` inside the factory only (T-03-NINJ).
- **End-of-call hook in `bot.py`:** `runner.run()` is now wrapped in `try/finally`. The `finally` block (runs for EVERY call/outcome, D-07) computes `outcome = _determine_outcome(flow_manager.state)`, builds the transcript from `build.context.messages` (with a cached fallback per A4), generates the summary, writes the `call_logs` row (with `reservation_id`, `google_event_id`, `transfer_number` from `transfer_payload`, and `channel_sent`), then dispatches the notification with subject `Chiamata DD/MM HH:MM — <Outcome>` and the summary (not the transcript) as the body. The dispatch is wrapped so a channel failure logs by type only and never blocks shutdown (T-03-FIN).
- **`.env.example`** extended with a Phase 3 notifications section: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (with @BotFather + `getUpdates` setup steps), all six `SMTP_*` placeholders, and an SMS/WhatsApp stub note. Demo default documented as `log` (+ telegram if token present, D-11).
- **12 new tests** (`tests/test_notification.py`): 8 channel tests (instantiation + awaitable send; telegram/email patched so no network; SMS asserts no `aiohttp.ClientSession` call) + 4 factory tests (log/telegram/unknown/None dispatch). Full suite: **103 passed, 1 skipped** — no regression.

## Task Commits

1. **Task 1: Failing notification tests + four channel impls (RED)** — `9a20172` (test)
2. **Task 2: NotificationChannelFactory + .env.example + end-of-call hook (GREEN)** — `74bc0c9` (feat)
3. **Task 3: Live verify end-of-call notification (SC2)** — NOT EXECUTED (blocking human-verify checkpoint, deferred — see Pending Human Verification)

**STATE update commit:** `9ef63db` (docs: paused at SC2 checkpoint)

## Files Created/Modified

- `src/notifications/__init__.py` — package marker for the notifications channels.
- `src/notifications/log_channel.py` — `LogNotificationChannel` (loguru, default/fallback).
- `src/notifications/telegram_channel.py` — `TelegramNotificationChannel` (aiohttp Bot API, 10s timeout, status-only error log).
- `src/notifications/email_channel.py` — `EmailNotificationChannel` (aiosmtplib STARTTLS, code-complete).
- `src/notifications/sms_channel.py` — `SMSNotificationChannel` (Phase 3 stub, no external API).
- `src/notifications/factory.py` — `create_channel(name, tenant)` with os.getenv creds + LogNotificationChannel fallback.
- `tests/test_notification.py` — 12 tests (8 channels + 4 factory).
- `.env.example` — Phase 3 notifications credential section + setup comments.
- `src/bot.py` — try/finally around `runner.run()`; end-of-call hook (outcome → summary → call_log → notify); `_ROME_TZ` constant; new imports.

## Decisions Made

- **Factory env-only creds (T-03-NINJ):** `create_channel` resolves all tokens/SMTP creds via `os.getenv`; the `tenant` arg selects only the channel *name*. Channel objects never read env themselves — zero routing influence from caller args or the transcript.
- **try/finally for D-07:** Wrapping `runner.run()` in `try/finally` guarantees the notification fires even if the runner raises, satisfying "owner sees every call".
- **Nested guard for T-03-FIN:** `channel.send` is wrapped in an inner try/except, and the whole hook in an outer try/except — a channel or DB error logs by type only and never crashes call shutdown.
- **Fixed UTC+1 ROME_TZ:** Avoids adding pytz/zoneinfo as a Phase 3 dependency; documented as a Phase 4+ upgrade point for DST accuracy.

## Deviations from Plan

### Auto-fixed Issues

None — both automated tasks executed as written. The plan's Task 1 (RED) and Task 2 (GREEN) followed the TDD gate exactly: `test(03-03)` commit `9a20172` precedes `feat(03-03)` commit `74bc0c9`.

**Total deviations:** 0
**Impact on plan:** None. No scope creep.

## Known Stubs

- **`SMSNotificationChannel`** is an intentional Phase 3 stub (D-10): it logs `[SMS STUB]` and makes no external API call. The real provider (Telnyx Messaging or Twilio) is deferred to Phase 4+ per the plan and CONTEXT.md "Deferred Ideas". This is documented intent, not an unfinished feature — `log` and `telegram` are the REAL testable channels for Phase 3.
- **`EmailNotificationChannel`** is code-complete but not live-tested in Phase 3 (D-10: "SMTP code written, tested when keys arrive"). It is fully wired and unit-tested with mocked `aiosmtplib.send`; live verification requires owner SMTP credentials.

## Threat Flags

No new security surface beyond the plan's threat model. All four mitigate-disposition threats are addressed:
- **T-03-NINJ:** channel targets (chat_id, SMTP_TO, token) read only from env via the factory; `tenant` config selects the channel name; zero influence from caller args (verified by `test_factory_*` patching env).
- **T-03-LOGPII:** every channel except handler logs `type(exc).__name__` (+ HTTP status for telegram) only — never subject/body. The bot.py hook's inner and outer guards log by type only.
- **T-03-TOK:** secrets via `.env` (gitignored); placeholders in `.env.example`; never hardcoded or logged.
- **T-03-FIN:** notification dispatch wrapped so a channel error is caught and logged; call shutdown never blocked.

## Pending Human Verification (SC2 — BLOCKING, NOT YET DONE)

**Task 3 is a blocking `checkpoint:human-verify` gate that was DEFERRED** (owner chose "Defer & continue"; live mic session not available this session). SC2 is therefore **PENDING manual owner testing** — it is NOT marked passed. The automated portion (Tasks 1-2) is fully complete and green (103 passed, 1 skipped); the live behavioral guarantee still requires the owner to run these scenarios with `python main.py --tenant=demo`:

1. **Booking flow → prenotato (NOTIF-03, D-07):** Complete a booking verbally (date, time, party size, name, phone, confirm), then hang up. Console (`log` channel) shows a `[CALL LOG]` line with subject `Chiamata DD/MM HH:MM — Prenotato` and a 2-3 sentence Italian summary (NOT the full transcript). Inspect `centralino.db` `call_logs` table: exactly one new row with `outcome='prenotato'`, `transcript_json` populated, `summary_text` set, `google_event_id` present.
2. **Abandoned call → abbandonato (D-07 always-send):** Begin a booking, then hang up mid-flow before confirming. Outcome `abbandonato`; a notification is still dispatched, and one `call_logs` row is written.
3. **(Optional) Telegram channel:** With `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env` and the demo tenant's `notification_channel=telegram`, confirm the summary message arrives in the configured Telegram chat.

**Acceptance (to be confirmed by owner):** every completed call produces exactly one `call_logs` row and one dispatched notification regardless of outcome; subject format and summary-not-transcript body confirmed; abandoned call still notifies.

Phase verification should surface SC2 as an outstanding human-verification item until the owner confirms.

## User Setup Required

- **Telegram (real testable channel, D-10/D-11):** Set `TELEGRAM_BOT_TOKEN` (from @BotFather → /newbot) and `TELEGRAM_CHAT_ID` (from `GET https://api.telegram.org/bot<TOKEN>/getUpdates` after messaging the bot) in `.env`, then set the demo tenant's `notification_channel=telegram`. Without these, the demo defaults to the `log` channel (no setup required).
- **SMTP (email channel, code-complete):** Set `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TO`, `SMTP_FROM` in `.env` when ready to live-test email. Not required for Phase 3 verification (log/telegram are the testable channels).

## Next Phase Readiness

- Code-complete and green for Plan 03-04 (watchdog / STT failover): the end-of-call hook consumes `outcome='fallito'` if set by the extended `ErrorFallbackObserver`, so escalation outcomes flow through to the notification with no additional wiring.
- The `NotificationChannel` seam + factory are ready for Phase 4 (real SMS/WhatsApp provider swap) and Phase 5 (per-tenant credential isolation) with no structural change.
- **Blocker/concern:** SC2 live verification remains PENDING (owner to run the booking + abandoned-call scenarios above).

## Self-Check: PASSED (automated)

Created files verified present and commits verified in git history. Live SC2 checkpoint is explicitly recorded as PENDING human verification (not a self-check failure — the automated scope passed).

- FOUND: src/notifications/__init__.py, log_channel.py, telegram_channel.py, email_channel.py, sms_channel.py, factory.py
- FOUND: tests/test_notification.py
- FOUND commits: 9a20172 (RED — test), 74bc0c9 (GREEN — feat), 9ef63db (STATE)
- Automated tests: 103 passed, 1 skipped (full suite green)

---
*Phase: 03-handoff-summary-notifications*
*Completed (automated tasks): 2026-06-27 — SC2 live verification pending*
