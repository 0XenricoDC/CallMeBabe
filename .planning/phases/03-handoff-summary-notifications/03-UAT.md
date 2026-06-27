---
status: partial
phase: 03-handoff-summary-notifications
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md, 03-04-SUMMARY.md]
started: 2026-06-27T00:00:00Z
updated: 2026-06-27T00:00:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing stopped after Test 4 — 2 blocker issues found (SC2 notification routing, SC3/SC4 failover); proceeding to diagnosis + gap closure. Tests 5 (SC4, blocked on SC3 fix), 6 (SC5 dead-air), 7 (CR-01) deferred — re-test after fixes land.]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running bot and clear ephemeral state. `python main.py --tenant=demo` boots with no errors, call_logs schema applies cleanly, faster-whisper is NOT loaded at startup (no startup model-load delay; D-12 lazy), and the personalized Italian greeting plays on connect.
result: pass
note: "User confirmed greeting + response + full booking with correct data (name, surname, party size, phone) written to Google Calendar."

### 2. SC1 — Transfer from any node
expected: A caller is transferred to the operator's configured number from ANY point. Verify all four triggers: (a) say "Voglio parlare con una persona" at the greeting → handoff phrase then clean end; (b) say "Mi passi un operatore" mid-booking → transfer fires; (c) ask the FAQ something not in the KB → bot offers operator → "Sì" → transfer; (d) speak English/non-Italian at the greeting → transfer. In every case the logged transfer number equals the demo tenant's configured transfer_number, never a value you spoke, and flow outcome is `trasferito`.
result: pass
note: "Approved by owner. Phase-3 constraint acknowledged: transfer is the LocalTransferStub (logs intent + handoff phrase + outcome trasferito + clean shutdown); a real PSTN ring to the operator number arrives with Telnyx in Phase 4 via the same TelephonyProvider seam. Demo transfer_number set to placeholder +39 351 000 0000 for the test."

### 3. SC2 — End-of-call summary + notification, every call & outcome
expected: After every call ends, the owner receives a summary via the tenant's configured channel. (a) Complete a booking → console `[CALL LOG] Chiamata DD/MM HH:MM — Prenotato` + a 2-3 sentence Italian summary (NOT the raw transcript); exactly one new call_logs row with outcome `prenotato`, transcript_json, summary_text, and the Google event id. (b) Hang up mid-flow (abandoned) → notification STILL dispatched, outcome `abbandonato` (D-07 "always send"). Subject format is `Chiamata DD/MM HH:MM — <Outcome>` with correct Italian (Europe/Rome) local time.
result: issue
reported: "Added Telegram credentials to .env but received no Telegram message after a completed booking."
severity: major
root_cause: "Demo tenant notification_channel is None in DB → create_channel() falls back to LogNotificationChannel, so the summary went to the console log, not Telegram. The factory dispatches to a SINGLE channel only; the D-11 demo default 'log (+telegram if token present)' multi-send was never implemented, so Telegram creds in .env have no effect unless notification_channel is explicitly set to 'telegram'."

### 4. SC3 — Deepgram failure → courtesy + faster-whisper failover, call uninterrupted
expected: Set `DEEPGRAM_API_KEY=invalid`, run the bot, and speak. The bot speaks a courtesy phrase ("Un momento, sto risolvendo un problema tecnico...") then continues the SAME call using faster-whisper (first whisper response may take 10-20s on CPU during lazy model load). The call is NOT dropped and the conversation proceeds.
result: issue
reported: "With an invalid DEEPGRAM_API_KEY the bot gave no response at all; logs show repeating '401, body: Websocket initialized with invalid credentials.' No courtesy phrase, no failover to faster-whisper."
severity: blocker
root_cause: "ServiceSwitcherStrategyFailover does not switch on a Deepgram WebSocket auth/connection failure (401). build_stt_switcher() wires the switcher + on_service_switched courtesy handler, but a persistent connection-level 401 is not surfaced/handled as the failover trigger the strategy acts on, so it never activates LazyWhisperSTTService and never fires the courtesy phrase. Automated test_stt_switcher.py passes because it simulates the switch rather than a real 401 connection error — matches the verifier's 'unconfirmable by code inspection' note for SC3."

### 5. SC4 — Persistent failure → courtesy + transfer (outcome fallito), no long dead-air
expected: Force both Deepgram AND faster-whisper to fail (e.g. invalid Deepgram key + break the whisper path). After the escalation threshold (~3 retry cycles) the bot speaks a courtesy phrase ("Mi scusi, sto riscontrando problemi tecnici. La trasferisco a un operatore.") and transfers to the operator, ending cleanly. The call_logs row shows outcome `fallito`, and there is no dead-air period longer than a few seconds.
result: [pending]

### 6. SC5 — Dead-air watchdog: silence → re-prompt → recovery/transfer
expected: With a healthy setup, stay silent after the greeting (~6s, T1). The bot re-prompts ("È ancora in linea?"). Remain silent (~8s more, T2). The bot speaks a recovery/handoff phrase ("Non riesco a sentirla, la passo a un operatore.") and ends the call. The call_logs row shows outcome `fallito`.
result: [pending]

### 7. CR-01 fix — notification survives a call-log DB write failure
expected: Verify the code-review fix (CR-01): force the call_logs write to fail (e.g. make the DB read-only / lock it / point at an unwritable path) and complete a normal call. The owner notification is STILL dispatched (summary delivered on the configured channel) even though persistence failed — i.e. the notification is no longer coupled to the DB write. Shutdown is not blocked and only the exception type is logged.
result: [pending]

## Summary

total: 7
passed: 2
issues: 2
pending: 3
skipped: 0

## Gaps

- truth: "After every call ends, the business owner receives a summary via the channel configured for their account (D-11 demo default: log + telegram if token present)."
  status: failed
  reason: "User reported: added Telegram credentials but received no message after a completed booking. Root cause: demo tenant notification_channel is None → defaults to log channel; the D-11 'demo default log (+telegram if token present)' multi-send is not implemented, so .env Telegram creds never trigger a Telegram dispatch."
  severity: major
  test: 3
  artifacts: [src/notifications/factory.py, src/bot.py]
  missing: ["Multi-channel demo default: when notification_channel is unset/log and TELEGRAM_BOT_TOKEN is present, also dispatch via Telegram (D-11)"]

- truth: "Forcing a Deepgram STT failure mid-call causes the bot to speak a courtesy phrase and switch to the faster-whisper fallback without interrupting the call (SC3, REL-03)."
  status: failed
  reason: "User reported: invalid DEEPGRAM_API_KEY → bot gave NO response; logs repeat '401 Websocket initialized with invalid credentials.' No courtesy phrase, no failover. ServiceSwitcherStrategyFailover does not switch on a Deepgram WebSocket auth/connection failure (401); the failover trigger is not raised/handled for connection-level errors, so LazyWhisperSTTService is never activated."
  severity: blocker
  test: 4
  artifacts: [src/pipeline/stt_switcher.py, src/pipeline/build.py, src/pipeline/fallback.py]
  missing: ["Failover must trigger on Deepgram connection/auth (401) and persistent transcription errors — not only on a simulated switch; verify the real error path drives ServiceSwitcherStrategyFailover and the on_service_switched courtesy phrase fires"]
