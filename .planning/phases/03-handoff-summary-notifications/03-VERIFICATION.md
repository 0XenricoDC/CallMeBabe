---
phase: 03-handoff-summary-notifications
verified: 2026-06-27T00:00:00Z
status: gaps_found
score: 18/19 code-level must-haves verified (1 partial — CR-01)
re_verification:
  previous_status: null
  previous_score: null
gaps:
  - truth: "After every call ends, a notification is dispatched via the tenant's configured channel, for every outcome (D-07)"
    status: partial
    reason: >-
      CR-01 (confirmed in code): in the end-of-call finally hook the summary
      generation, call_log DB write, and channel.send() share one try-block.
      channel.send() runs AFTER call_log_repo.write(). On a foreseeable DB error
      (aiosqlite "database is locked" under concurrent multi-tenant writes, or
      json.dumps raising on non-serializable context blocks) control jumps to the
      outer except (bot.py:519) which only logs the exception type — the owner
      notification is never attempted. Per CLAUDE.md the end-of-call summary IS
      the product's core value, so this drops the goal-critical deliverable on a
      transient DB fault. The happy path works; the "for EVERY call" guarantee
      does not hold under the documented failure modes.
    artifacts:
      - path: "src/bot.py:476-517"
        issue: >-
          channel.send() is inside the same try as call_log_repo.write(); a
          write() exception bypasses notification dispatch entirely.
      - path: "src/bot.py:482"
        issue: >-
          transcript = list(build.context.messages) is passed unsanitized to
          json.dumps (WR-08); a non-serializable content block raises and, via
          the shared try, drops both the call_log row and the notification.
    missing:
      - "Decouple notification dispatch from the call_log persistence step so a DB write failure cannot suppress the owner summary (generate summary first; persist in its own try/except; notify in a separate try/except that runs regardless of DB outcome)."
      - "Sanitize/normalize the transcript to plain {role, content} string dicts before json.dumps (reuse the isinstance(content, str) filter generate_summary already applies) and wrap serialization defensively."
human_verification:
  - test: "SC1 — Transfer from any node (live mic, python main.py --tenant=demo)"
    expected: >-
      (a) At greeting say 'Voglio parlare con una persona' -> bot speaks 'La metto
      in contatto con un operatore, resti in linea.' and ends the call; (b) mid-booking
      say 'Mi passi un operatore' -> transfer fires; (c) FAQ-not-found -> bot offers
      operator, on accept transfer fires; (d) speak English at greeting -> transfer
      (HAND-03); (e) logged transfer number equals tenant.transfer_number, never the
      spoken content.
    why_human: "Requires live mic + STT/LLM/TTS round-trip; spoken intent routing cannot be exercised by code inspection."
  - test: "SC2 — End-of-call notification for every outcome (live mic)"
    expected: >-
      Complete a booking then hang up: console [CALL LOG] shows subject 'Chiamata
      DD/MM HH:MM — Prenotato' + 2-3 sentence Italian summary (NOT full transcript);
      centralino.db call_logs has one row outcome='prenotato', transcript_json + summary_text
      set, google_event_id present. Repeat hanging up mid-booking -> outcome='abbandonato',
      notification still sent.
    why_human: "Requires a live call lifecycle and DB inspection; the dispatch path runs only at real call shutdown."
  - test: "SC3 — Deepgram -> faster-whisper failover without dropping the call (live, forced failure)"
    expected: >-
      Set DEEPGRAM_API_KEY=invalid, run, speak: bot says 'Un momento, sto risolvendo
      un problema tecnico...' then continues on faster-whisper (first response 10-20s
      while model lazy-loads). The call is NOT dropped.
    why_human: "Requires forcing a provider failure on a live audio path; ServiceSwitcher failover + lazy model load only observable at runtime."
  - test: "SC4 — Persistent failure -> courtesy + transfer, outcome fallito, no long dead-air (live, forced failure)"
    expected: >-
      Set DEEPGRAM_API_KEY=invalid AND force Whisper to fail (e.g. device=cuda on a
      CPU box). After the escalation threshold the bot speaks 'Mi scusi, sto riscontrando
      problemi tecnici. La trasferisco a un operatore.' and ends; call_logs outcome='fallito',
      no dead-air beyond a few seconds.
    why_human: "Requires a sustained live forced-failure session to exercise the escalation ladder end-to-end."
  - test: "SC5 — Dead-air watchdog re-prompt then transfer (live)"
    expected: >-
      Start a normal call, stay silent ~6s -> bot re-prompts 'È ancora in linea?';
      stay silent another ~8s -> bot says 'Non riesco a sentirla, la passo a un operatore.'
      and transfers (outcome 'fallito').
    why_human: "VAD-driven idle timers (T1/T2) only fire on a live audio stream with real silence."
  - test: "Lazy-load-at-startup check (D-12)"
    expected: "Confirm faster-whisper is NOT loaded at startup when Deepgram is healthy — no model-load delay/log before the first turn."
    why_human: "Startup timing/log observation requires running the bot process."
---

# Phase 3: Handoff, Summary & Notifications Verification Report

**Phase Goal:** Every call ends with a logged record and a summary sent to the business owner on their preferred channel; any call can be transferred to a human operator from any point; and every provider failure degrades gracefully through courtesy phrases, a faster-whisper STT fallback, and ultimately a transfer to the operator rather than dead air.

**Verified:** 2026-06-27
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

The phase decomposes into four sub-goals, each backed by a plan. Code-level
artifacts and wiring are substantially complete and the full automated suite is
green (115 passed, 1 skipped — the API-key-gated model-id check). However:

1. **CR-01 is a real, code-level blocker** against the goal's central clause
   ("a summary sent to the business owner ... every call"). The notification can
   be silently dropped when the DB write fails because both share one try-block.
   This is actionable without any human testing and must be fixed.
2. **The five live success criteria (SC1–SC5) are unverified.** Every
   behavioral guarantee in the goal — transfer-from-anywhere, summary-on-every-call,
   STT failover, persistent-failure transfer, dead-air watchdog — was deferred to
   owner manual testing and cannot be confirmed by code inspection.

### Observable Truths

| # | Plan | Truth | Status | Evidence |
|---|------|-------|--------|----------|
| 1 | 01 | Caller requesting a human is transferred from the greeting node | ✓ VERIFIED (code) | `build_transfer_schema()` registered via `FlowManager(global_functions=[...])` (bot.py:207); reachable from greeting. Live routing = SC1. |
| 2 | 01 | Non-Italian speaker is transferred (HAND-03) | ✓ VERIFIED (code) | transfer_call schema Italian description instructs use on non-Italian input (functions.py:500-537). Live = SC1(d). |
| 3 | 01 | Transfer works mid-booking and from FAQ node (HAND-04) | ✓ VERIFIED (code) | global_functions makes transfer_call available on every node without per-node import; FAQ node role_message offers it (nodes.py:168). |
| 4 | 01 | Bot transfers when uncertain/out-of-scope instead of inventing (HAND-02) | ✓ VERIFIED (code) | FAQ-not-found sets `faq_transfer_offered=True` + `offer_transfer=True` (functions.py:491-492); schema covers fuori_ambito. |
| 5 | 01 | Transfer target is tenant config, never caller-supplied | ✓ VERIFIED | `handle_transfer_call` reads `fm.state["tenant"].transfer_number` only (functions.py:566-572); grep confirms zero `args["transfer_number"]` reads. |
| 6 | 01 | Transferred call: outcome 'trasferito' + warm payload + handoff phrase + clean shutdown | ✓ VERIFIED (code) | functions.py:577-610 assembles payload, sets outcome, queues TTSSpeakFrame + EndWorkerFrame, calls LocalTransferStub. |
| 7 | 02 | One call_logs row with tenant_id, outcome, transcript, optional refs | ✓ VERIFIED | schema.sql:80-95 + `CallLogRepository.write()` parameterized INSERT (repository.py:84-105). |
| 8 | 02 | outcome always one of prenotato/faq/trasferito/abbandonato/fallito | ✓ VERIFIED | CHECK constraint (schema.sql:86-87); `_determine_outcome` maps state (summary.py:22-56). |
| 9 | 02 | 2-3 sentence Italian summary per call; full transcript stays in DB | ✓ VERIFIED | `generate_summary` direct Anthropic SDK, Italian prompt, last ~20 turns (summary.py:59-110); body = summary, transcript persisted separately. |
| 10 | 02 | Summary never logs PII on failure, returns safe fallback | ✓ VERIFIED | except logs `type(exc).__name__` only; returns "Riepilogo non disponibile (esito: ...)" (summary.py:112-120). |
| 11 | 03 | Notification dispatched on configured channel for every outcome (D-07) | ⚠️ PARTIAL | finally hook wires outcome→summary→write→send (bot.py:466-517), BUT CR-01: a DB-write exception skips channel.send entirely. See Gaps. |
| 12 | 03 | Subject 'Chiamata DD/MM HH:MM — <Outcome>'; body = summary not transcript | ✓ VERIFIED | bot.py:505-510 builds exact subject; `channel.send(subject, summary_text)`. |
| 13 | 03 | channel=log→Log; =telegram→Telegram; demo default log | ✓ VERIFIED | `create_channel` name dispatch with LogNotificationChannel fallback (factory.py:49-70). |
| 14 | 03 | Four channels behind NotificationChannel interface, instantiate without error | ✓ VERIFIED | log/telegram/email/sms modules each subclass the ABC; 12 tests pass. |
| 15 | 03 | Channel destinations only from env/config, never caller input | ✓ VERIFIED | factory reads os.getenv only; channels store ctor args; tenant selects name only (factory.py:51-67). |
| 16 | 04 | Persistent Deepgram failure → courtesy + faster-whisper, call uninterrupted | ✓ VERIFIED (code) | `build_stt_switcher` ServiceSwitcher([deepgram, lazy_whisper], failover) + on_service_switched courtesy frame (stt_switcher.py:135-207); in pipeline STT slot (build.py:113-121). Live = SC3. |
| 17 | 04 | faster-whisper lazy-loaded, not at startup | ✓ VERIFIED | `LazyWhisperSTTService._load()` no-op; model loads in `run_stt` via asyncio.to_thread (stt_switcher.py:62-101). Live = SC3/D-12 check. |
| 18 | 04 | Persistent STT/TTS failure → courtesy + transfer, outcome fallito, no dead-air | ✓ VERIFIED (code) | `ErrorFallbackObserver` escalation _ESCALATION_THRESHOLD=3, idempotent, sets outcome='fallito' + courtesy + EndWorkerFrame (fallback.py:121-142). Live = SC4. |
| 19 | 04 | Silence T1 re-prompt; continued silence T2 recovery/transfer | ✓ VERIFIED (code) | `user_idle_timeout=T1=6.0` (factory.py:163); `_DeadAirHandler`: count1 re-prompt + raise to T2=8.0, count2 outcome='fallito' + EndWorkerFrame (bot.py:64-144, 440-448). Live = SC5. |

**Score:** 18/19 code-level truths verified; 1 PARTIAL (#11, CR-01). All behavioral guarantees additionally pending live verification (SC1–SC5).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/telephony/base.py` | TelephonyProvider ABC | ✓ VERIFIED | ABC with async `transfer(number, context)`; T-injection docstring. |
| `src/telephony/stub.py` | LocalTransferStub log-only | ✓ VERIFIED | Logs number+reason only, no PII, no real API. |
| `src/flows/functions.py` | transfer schema + handler + FAQ offer | ✓ VERIFIED | build_transfer_schema (500), handle_transfer_call (540), FAQ not-found offer (491). |
| `src/db/schema.sql` | call_logs table + index | ✓ VERIFIED | CREATE TABLE + 5-value CHECK + idx_call_logs_tenant (80-98). |
| `src/call_log/repository.py` | CallLogRepository.write parameterized | ✓ VERIFIED | Parameterized INSERT, json.dumps(ensure_ascii=False), lastrowid. |
| `src/call_log/summary.py` | generate_summary + _determine_outcome | ✓ VERIFIED | Both present; PII-safe; tenant.model used. |
| `src/notifications/factory.py` | create_channel | ✓ VERIFIED | name dispatch + Log fallback. |
| `src/notifications/telegram_channel.py` | Telegram via aiohttp | ✓ VERIFIED | sendMessage, 10s timeout, status-only error log. ⚠️ WR-06 Markdown risk. |
| `src/bot.py` | end-of-call try/finally hook | ⚠️ WIRED w/ defect | finally present (466) but CR-01 ordering defect (476-517). |
| `src/pipeline/stt_switcher.py` | LazyWhisper + build_stt_switcher | ✓ VERIFIED | Present; lazy load; failover. |
| `src/pipeline/fallback.py` | escalation → transfer | ✓ VERIFIED | _ESCALATION_THRESHOLD, _escalated guard, outcome=fallito. |
| Test files (transfer/call_log/summary/notification/stt_switcher/watchdog/fallback) | unit coverage | ✓ PRESENT | All collected; suite 115 passed, 1 skipped. ⚠️ WR-07 some tautological assertions. |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| bot.py setup_flow | FlowManager(global_functions=[build_transfer_schema()]) | global_functions param | ✓ WIRED (bot.py:207) |
| handle_transfer_call | fm.state['tenant'].transfer_number | trusted config read, never args | ✓ WIRED (functions.py:568-572) |
| build.py Pipeline | build_stt_switcher() in STT slot | ServiceSwitcher slot | ✓ WIRED (build.py:84,115) |
| build_user_aggregator_params | user_idle_timeout=T1 | watchdog timer | ✓ WIRED (factory.py:163) |
| fallback escalation | flow_manager.state['outcome']='fallito' + EndWorkerFrame | persistent-failure transfer | ✓ WIRED (fallback.py:131,141) |
| bot.py finally | CallLogRepository.write + generate_summary + channel.send | post runner.run() hook | ⚠️ WIRED but CR-01 shared-try defect |
| factory | tenant.notification_channel | per-tenant selection | ✓ WIRED (bot.py:504) |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| HAND-01 (transfer on request) | 03-01 | ✓ code / ⏳ SC1 | transfer_call global fn; behavioral pending SC1. |
| HAND-02 (transfer when uncertain/out-of-scope) | 03-01 | ✓ code / ⏳ SC1 | FAQ-not-found offer + schema fuori_ambito. |
| HAND-03 (non-Italian → transfer) | 03-01 | ✓ code / ⏳ SC1 | schema description; pending live. |
| HAND-04 (transfer from any point) | 03-01 | ✓ VERIFIED | global_functions single wiring point. |
| NOTIF-01 (call log written) | 03-02 | ✓ VERIFIED | call_logs table + repository. |
| NOTIF-02 (textual summary) | 03-02 | ✓ VERIFIED | generate_summary. |
| NOTIF-03 (summary sent via NotificationChannel) | 03-03 | ⚠️ PARTIAL | wired; CR-01 can drop it; live SC2 pending. |
| NOTIF-04 (Email/SMS/WhatsApp/Telegram/log channels) | 03-03 | ✓ VERIFIED | four channels (sms/whatsapp = intentional Phase 3 stub per D-10; email code-complete). |
| NOTIF-05 (per-tenant channel) | 03-03 | ✓ VERIFIED | factory reads tenant.notification_channel. |
| REL-02 (persistent failure → transfer) | 03-04 | ✓ code / ⏳ SC4 | escalation observer; pending live. |
| REL-03 (faster-whisper fallback) | 03-04 | ✓ code / ⏳ SC3 | ServiceSwitcher failover; pending live. |
| REL-04 (dead-air watchdog) | 03-04 | ✓ code / ⏳ SC5 | idle timer + _DeadAirHandler; pending live. |

All 12 declared requirement IDs are accounted for in both PLAN frontmatter and the codebase. REQUIREMENTS.md still marks these "Pending" — consistent with live verification not yet complete. No orphaned IDs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/bot.py | 476-517 | Notification + DB write share one try; send after write | 🛑 Blocker (CR-01) | Owner summary silently dropped on DB error — defeats core deliverable. |
| src/bot.py | 482 | Unsanitized `list(build.context.messages)` → json.dumps | ⚠️ Warning (WR-08) | Non-serializable block raises, compounding CR-01. |
| src/bot.py | 53 | `_ROME_TZ = timezone(+1h)` fixed offset | ⚠️ Warning (WR-02) | Timestamps/subjects off by 1h during DST (review date is DST). |
| src/bot.py | 458-461,482 | `_cached_messages` set once to [] then never populated | ⚠️ Warning (WR-04) | Dead fallback; transcript silently empty if context torn down. |
| src/flows/functions.py (confirm booking) | — | reservation_id never written to fm.state | ⚠️ Warning (WR-01) | call_logs.reservation_id always NULL; FK link lost. |
| src/call_log/repository.py | 34-43 | No `PRAGMA foreign_keys = ON` | ⚠️ Warning (WR-03) | Declared FKs unenforced; docstring IntegrityError claim false. |
| src/flows/nodes.py build_booking_node | 71-105 | Dereferences tenant.business_name without None guard | ⚠️ Warning (WR-05) | Latent AttributeError mid-call if tenant is None. |
| src/notifications/telegram_channel.py | 53-57 | parse_mode=Markdown on LLM text | ⚠️ Warning (WR-06) | Unbalanced markup → HTTP 400 → Telegram summary dropped. |
| tests (call_log/transfer) | various | Tautological assertions | ⚠️ Warning (WR-07) | Tests pass regardless of behavior under test. |
| src/call_log/summary.py:48 + flows | — | `faq_answered` read but never set | ℹ️ Info (IN-01) | _determine_outcome rule 3 unreachable; correct only by coincidence. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Schema executes on fresh sqlite | executescript on :memory: | clean per SUMMARY + schema read | ✓ PASS (inspected) |
| Full unit suite | python -m pytest tests/ -q | 115 passed, 1 skipped (per SUMMARY 03-04) | ✓ PASS (reported) |
| Live STT/transfer/notification/watchdog | requires mic + forced failures | — | ? SKIP → human (SC1–SC5) |

Note: live behaviors were not executed by the verifier (no mic / forced-failure session available); routed to human verification.

### Human Verification Required

Six items (SC1–SC5 plus the lazy-load startup check) are listed in frontmatter
`human_verification`. These were intentionally deferred by the owner ("Defer &
continue") and are recorded as PENDING in every SUMMARY and STATE.md. They are
the behavioral confirmation of the phase goal and cannot be closed by code
inspection.

### Gaps Summary

One actionable code-level gap blocks the phase:

- **CR-01 (truth #11 / NOTIF-03, D-07):** The end-of-call hook couples
  notification dispatch to the call_log DB write inside a single try-block, with
  `channel.send()` running after `write()`. A foreseeable `aiosqlite`
  `database is locked`/`OperationalError` under concurrent multi-tenant writes —
  or a `json.dumps` failure on a non-serializable context block (WR-08) — jumps
  to the outer except and the owner notification is never sent. Because the
  summary-to-owner is the product's core value (CLAUDE.md), this fails the goal's
  "a summary sent ... every call" clause under realistic conditions. Fix:
  generate the summary first, persist in its own try/except, and dispatch the
  notification in a separate try/except that runs regardless of DB outcome; also
  sanitize the transcript before serialization (addresses WR-08).

Beyond CR-01, eight review warnings (WR-01..08) and several info items are noted
above. They do not individually block the goal but should be triaged — WR-02
(DST timestamps), WR-04 (dead transcript cache), and WR-06 (Telegram Markdown
drop) are the most likely to surface in production and partially overlap CR-01's
"summary reaches the owner" concern.

**Recommendation:** Fix CR-01 (and WR-08) at code level, then run the SC1–SC5
live verification session. Do not mark the phase goal achieved until both the
code blocker is closed and the live success criteria are confirmed by the owner.

---

_Verified: 2026-06-27_
_Verifier: Claude (gsd-verifier)_
