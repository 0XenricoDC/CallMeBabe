---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: 03-04 Task 4 human-verify checkpoint (live SC3/SC4/SC5 degradation ladder)
last_updated: "2026-06-29T12:01:40.286Z"
last_activity: 2026-06-29
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 13
  completed_plans: 12
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-23)

**Core value:** Una chiamata reale in italiano viene gestita end-to-end dal bot (saluto personalizzato, conversazione naturale a bassa latenza, azione completata) senza intervento umano e senza riscrivere codice per un nuovo cliente.
**Current focus:** Phase 03 — handoff-summary-notifications

## Current Position

Phase: 03 (handoff-summary-notifications) — EXECUTING
Plan: 2 of 6
Status: Ready to execute
Last activity: 2026-06-29 - Completed quick task 260629-tkr: fix outcome-determination bug (confirmed booking no longer buried by watchdog 'fallito')

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 4
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 2 | 4 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 35 | 4 tasks | 18 files |
| Phase 01 P02 | 6 | 2 tasks | 5 files |
| Phase 01 P03 | 180 | 4 tasks | 7 files |
| Phase 02-booking-calendar-faq P01 | 35 | 3 tasks | 14 files |
| Phase 02-booking-calendar-faq P02 | 15 | 3 tasks | 13 files |
| Phase 02-booking-calendar-faq P03 | 14 | 2 tasks | 6 files |
| Phase 02-booking-calendar-faq P04 | 20 | 2 tasks | 8 files |
| Phase 03 P02 | 6 | 3 tasks | 6 files |
| Phase 03 P03 | ~10 | 2 tasks | 8 files |
| Phase 03 P04 | 20 | 3 tasks | 9 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: aggregation_timeout must be set to 0.1-0.3s in Phase 1 pipeline — default ~1s blows the 800ms budget before any work is done.
- [Roadmap]: Streaming at every stage (Deepgram streaming → Claude streaming tokens → ElevenLabs streaming TTS) is non-negotiable from Phase 1 — retrofitting is a rewrite.
- [Roadmap]: CalendarProvider, TransportFactory, TenantConfig, and NotificationChannel interface seams must be defined in Phase 1 so Phase 4 (Telnyx) and Phase 5 (multi-tenant) add files behind interfaces rather than restructuring code.
- [Roadmap]: Phase 4 (Telnyx) carries a HIGH research flag — DTMF/codec reliability, warm-transfer Dial+Bridge, PSTN latency, and WebSocket-VAD starvation all need targeted review during planning.
- [Phase ?]: [01-01]: Typed Pydantic TenantConfig + aiosqlite TenantRepository behind a Postgres-ready interface; demo tenant loads via parameterized WHERE id = ? (D-01/D-02/D-03).
- [Phase ?]: [01-01]: voice_id and model fields have non-empty Pydantic validators (Pitfall 5) preventing silent wrong-voice / broken-LLM fallbacks.
- [Phase ?]: [01-01]: Wave 0 pytest stubs use xfail(strict=False) referencing the owning plan; suite green now, Plans 02/03 enforce by removing the marker.
- [Phase 1]: [01-02]: SmallWebRTCTransport uses pipecat.transports.smallwebrtc.transport (not .network.small_webrtc); AnthropicLLMService from .anthropic.llm; ElevenLabsTTSService from .elevenlabs.tts — exact submodule paths verified in venv.
- [Phase 1]: [01-02]: make_greeting_handler() factory pattern used so greeting handler is unit-testable without running the full runner lifecycle.
- [Phase 1]: [01-02]: user_turn_stop_timeout=0.2s, VAD stop_secs=0.3s — both explicitly set; default 5s would blow 800ms budget (Pitfall 1).
- [Phase ?]: [01-02]: bot() loads TenantConfig + queues Italian greeting on connect via make_greeting_handler factory; barge-in active during greeting (D-11). Live smoke approved by user.
- [Phase ?]: [01-02]: Windows UTF-8 stdout fix in main.py — pipecat runner emoji banner crashes cp1252 consoles; sys.stdout/stderr.reconfigure(utf-8) enables clone-and-run without PYTHONUTF8=1.
- [Phase 1]: [01-03]: LatencyObserver uses BotStoppedSpeakingFrame as turn-end signal (Open Question 1 resolved); data.source is FrameProcessor object, route by .name substring.
- [Phase 1]: [01-03]: ErrorFallbackObserver circular dependency with PipelineWorker resolved by constructing with worker=None then patching .worker after worker creation.
- [Phase 1]: [01-03]: V7 enforced — ErrorFrame.error string never printed/logged in fallback.py; only sanitized source.name used.
- [Phase ?]: [01-03]: Custom observers attach via PipelineWorker(observers=[...]); PipelineParams has no observers field and silently drops the kwarg — root cause of both deliverables broken live.
- [Phase ?]: [01-03]: Latency turn-end via built-in TurnTrackingObserver.on_turn_ended; metrics routed on metric.processor (TTS-first to avoid 'stt' inside 'ElevenLabsTTSService'); budget = response_ms (stt+llm_ttft+tts_ttfb), not total turn_ms.
- [Phase ?]: [01-03]: TTS switched to eleven_turbo_v2_5 + Language.IT — only flash/turbo v2_5 honor the language code in pipecat 1.4.0; eliminates the ignored-language warning.
- [Phase ?]: [01-03]: UAT (future optimisation, out of scope): live response latency ~1.7s warm / ~3.3s cold, dominated by Claude TTFT + STT, over the 800ms budget; Anthropic prompt caching not active (cache_read=0).
- [Phase ?]: [02-01]: Anthropic model IDs claude-haiku-4-5 (default) and claude-sonnet-4-6 (booking D-19) carried from Phase 1; test_model_ids.py skips without API key
- [Phase ?]: [02-01]: Dev DB migration for calendar_id: delete centralino.db and re-seed (no ALTER TABLE in schema.sql for idempotency per Pitfall 5)
- [Phase ?]: [02-02]: BEGIN IMMEDIATE + asyncio.Lock serializes concurrent try_reserve_slot; bozza rows count toward capacity
- [Phase ?]: [02-02]: dateparser LANGUAGES passed as separate kwarg not inside settings dict (API correctness)
- [Phase ?]: [02-02]: build_end_node transition reachable ONLY on truthy event_id branch — structural BOOK-05 gating
- [Phase ?]: 02-03 complete
- [Phase ?]: [02-03]
- [Phase ?]: [02-03]
- [Phase ?]: [02-03]
- [Phase ?]: [02-03]
- [Phase 02]: [02-04]: FTS5 error guard: catch OperationalError, return [] (T-02-12 natural-speech guard, simpler than pre-sanitization)
- [Phase 02]: [02-04]: Hybrid FAQ routing: _HOURS_KEYWORDS/_SERVICES_KEYWORDS token intersection → config fields; else FTS5 (D-06)
- [Phase 02]: [02-04]: W1 routing: build_greeting_node exposes route_to_faq + route_to_booking FlowsFunctionSchema tools (explicit tool-driven, not prose)
- [Phase 02]: [02-04]: Ingest idempotency via DELETE WHERE tenant_id = ? before INSERT (FTS5 has no UNIQUE — only safe mechanism)
- [Phase 03]: [03-01]: transfer_number resolved ONLY from fm.state['tenant'].transfer_number; args carry just a logged 'reason' (T-03-INJ — malicious-arg test asserts it)
- [Phase 03]: [03-01]: Global transfer_call wired once via FlowManager(global_functions=[...]); nodes never import the schema — reachable from any node (HAND-04)
- [Phase 03]: [03-01]: FrameDirection imports from pipecat.processors.frame_processor (NOT pipecat.frames.frames) in pipecat 1.4.0
- [Phase 03]: [03-01]: Frame side-effects (TTSSpeakFrame handoff + EndWorkerFrame UPSTREAM) live in handle_transfer_call; LocalTransferStub stays a pure log-only domain seam for Phase 4
- [Phase 03]: [03-02]: CallLogRepository.write() uses cursor.lastrowid (direct aiosqlite cursor property; avoids SELECT last_insert_rowid() round-trip)
- [Phase 03]: [03-02]: generate_summary uses tenant.model exclusively — no hardcoded competing model id (CLAUDE.md constraint, RESEARCH A2 verify-at-build)
- [Phase 03]: [03-02]: transcript_json stored with ensure_ascii=False so Italian chars survive JSON round-trip to notification body
- [Phase 03]: [03-02]: _determine_outcome priority: explicit state['outcome'] wins; then confirmed_event_id→prenotato; faq_answered→faq; booking_slot-no-event→abbandonato; default faq
- [Phase 03]: [03-03]: NotificationChannelFactory.create_channel reads creds via os.getenv only; unknown/None name falls back to LogNotificationChannel (D-11 default)
- [Phase 03]: [03-03]: End-of-call try/finally in bot.py fires for EVERY call/outcome (D-07); order: _determine_outcome → generate_summary → CallLogRepository.write → channel.send
- [Phase 03]: [03-03]: channel.send failure in finally is caught and logged by type only — call shutdown never blocked (T-03-FIN)
- [Phase 03]: [03-03]: ROME_TZ uses fixed UTC+1 timedelta (no pytz/zoneinfo dep in Phase 3); Phase 4+ can upgrade to zoneinfo.ZoneInfo("Europe/Rome") for DST accuracy
- [Phase 03]: [03-04]: LazyWhisperSTTService overrides _load() to no-op + run_stt() for lazy model load via asyncio.to_thread (D-12); WorkerRefHolder breaks circular dep with PipelineWorker (same pattern as ErrorFallbackObserver)
- [Phase 03]: [03-04]: _ESCALATION_THRESHOLD=3 in fallback.py; after 3 retry-slot cycles sets outcome='fallito' + EndWorkerFrame (idempotent via _escalated flag); ErrorFrame.error never logged (V7/T-03-LOG preserved)
- [Phase 03]: [03-04]: Dead-air watchdog T1=6s/T2=8s (D-14 Claude's Discretion); _DeadAirHandler in bot.py; UserIdleTimeoutUpdateFrame raises timeout to T2 after re-prompt so T1≠T2 windows are distinct
- [Phase 03]: [03-04]: build.py STT slot now ServiceSwitcher([deepgram, lazy_whisper], failover); test_pipeline.py patched to use build.build_stt_switcher mock (not factory.DeepgramSTTService)

### Pending Todos

None yet.

### Blockers/Concerns

- [03-01] SC1 live verification PENDING (deferred by owner): 5 spoken transfer scenarios (explicit request, mid-booking, FAQ-not-found offer, non-Italian, config-number integrity) must be run manually via `python main.py --tenant=demo`. Code + automated tests complete (77 pass); behavioral guarantee unconfirmed. See 03-01-SUMMARY.md §Pending Human Verification.
- [03-03] SC2 live verification PENDING (blocking checkpoint): end-of-call notification hook must be verified manually — run a booking + an abandoned call, confirm [CALL LOG] line in console and call_logs DB row. Automated tests complete (103 pass); live behavioral guarantee unconfirmed.
- [03-04] SC3/SC4/SC5 live verification PENDING (blocking checkpoint, Task 4): forced-failure degradation ladder must be verified manually with python main.py --tenant=demo (set DEEPGRAM_API_KEY=invalid for SC3/SC4; stay silent 6s/8s for SC5). Automated tests complete (115 pass, 1 skipped).
- Phase 4 (Telnyx): HIGH research flag from SUMMARY.md — plan `/gsd:plan-phase 4` should use `--research-phase`.
- Phase 2 (Booking/Calendar): MEDIUM research flag — Google Calendar freebusy inversion and transactional reserve schema have documented subtleties.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260626-sax | Fix booking flow: anno data 2025 + numeri telefono alieni nel readback | 2026-06-26 | (see log) | [260626-sax-fix-booking-flow-anno-data-2025-numeri-t](./quick/260626-sax-fix-booking-flow-anno-data-2025-numeri-t/) |
| 260629-tkr | Fix outcome-determination bug: confirmed booking wrongly reported as fallito | 2026-06-29 | 4f7504e | [260629-tkr-fix-outcome-determination-bug-confirmed-](./quick/260629-tkr-fix-outcome-determination-bug-confirmed-/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Performance | Latency optimization to meet <800ms budget (response ~1.7s warm, Claude TTFT-dominated). Levers: enable Anthropic prompt caching (cache_read_input_tokens=0), STT endpointing tuning, cold-start mitigation. Instrumentation (VOICE-04) already delivered to measure it. | Open | Phase 1 (2026-06-25) |

## Session Continuity

Last session: 2026-06-29T12:01:40.256Z
Stopped at: 03-04 Task 4 human-verify checkpoint (live SC3/SC4/SC5 degradation ladder)
Resume file: None
