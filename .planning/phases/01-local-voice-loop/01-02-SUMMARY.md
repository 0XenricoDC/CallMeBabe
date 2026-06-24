---
phase: 01-local-voice-loop
plan: 02
subsystem: voice-pipeline
tags: [pipecat, deepgram, anthropic, elevenlabs, silero-vad, webrtc, barge-in, italian, streaming]

# Dependency graph
requires:
  - phase: 01-01
    provides: "TenantConfig (Pydantic) + TenantRepository.get_tenant (aiosqlite); demo tenant seed; venv with pipecat 1.4.0 stack; pytest harness + RED stubs"
provides:
  - "Runnable bot: `python main.py --tenant=demo` serves WebRTC UI at localhost:7860/prebuilt/ and holds a streaming Italian conversation"
  - "build_pipeline(transport, tenant) — streaming Deepgram→Claude→ElevenLabs assembly with Pipecat 1.x imports only"
  - "TransportFactory seam (SmallWebRTCTransport now; Phase 4 Telnyx swap point)"
  - "STTProvider seam (DeepgramProvider default, WhisperProvider config-selectable, no auto-failover)"
  - "Greeting-on-connect via make_greeting_handler — bot speaks first, barge-in active during greeting (D-11)"
  - "Sub-budget turn timing: VAD stop_secs=0.3, user_turn_stop_timeout=0.2"
  - "Windows clone-and-run: UTF-8 stdout fix so pipecat runner banner doesn't crash cp1252 consoles"
affects: [01-03 latency-observers, Phase 2 booking-flow, Phase 3 transfer/fallback, Phase 4 telnyx-transport]

# Tech tracking
tech-stack:
  added:
    - "DeepgramSTTService (nova-2, language=it, endpointing=400, interim_results)"
    - "AnthropicLLMService (model from tenant config, default claude-haiku-4-5, max_tokens=1024)"
    - "ElevenLabsTTSService (voice_id per-tenant, eleven_multilingual_v2, language=it)"
    - "SileroVADAnalyzer + VADParams (barge-in)"
    - "SmallWebRTCTransport + Pipecat runner (browser WebRTC, no native audio deps)"
  patterns:
    - "TransportFactory seam — transport-only swap for Phase 4 Telnyx, pipeline unchanged (D-05)"
    - "STTProvider ABC + get_stt_provider(config_key) selector, no auto-failover (D-08)"
    - "Factory helpers (build_vad_params/build_user_aggregator_params/build_tts_service) for isolated unit assertions"
    - "make_greeting_handler(worker, tenant) factory so greeting handler is unit-testable without the runner lifecycle"
    - "Pipecat 1.x exact submodule import paths verified against the installed venv"

key-files:
  created:
    - "src/pipeline/__init__.py — pipeline package"
    - "src/pipeline/factory.py — STTProvider seam, TransportFactory, VAD/aggregator/TTS helpers"
    - "src/pipeline/build.py — build_pipeline() streaming assembly"
    - "src/bot.py — async bot(runner_args), make_greeting_handler, greeting-on-connect wiring"
    - "main.py — runner entry point, --tenant arg, Windows UTF-8 fix"
  modified:
    - "tests/test_pipeline.py — 4 tests GREEN (xfail removed)"
    - "tests/test_bot.py — test_greeting_injected GREEN (xfail removed)"

key-decisions:
  - "Pipecat 1.4.0 submodule paths differ from RESEARCH stubs: AnthropicLLMService from pipecat.services.anthropic.llm; ElevenLabsTTSService from pipecat.services.elevenlabs.tts; SmallWebRTCTransport from pipecat.transports.smallwebrtc.transport"
  - "make_greeting_handler factory pattern — testable greeting handler decoupled from runner lifecycle"
  - "user_turn_stop_timeout=0.2 + VAD stop_secs=0.3 both explicitly set (Pitfall 1/3); default 5s would blow the 800ms budget"
  - "nova-2 kept (CLAUDE.md lock); nova-3 Italian upgrade surfaced as a config comment only (Open Question 3)"
  - "Windows UTF-8 stdout reconfigure in main.py so the pipecat emoji startup banner does not crash cp1252 consoles (clone-and-run)"

patterns-established:
  - "Streaming pipeline order: transport.input → stt → user-agg → llm → tts → transport.output → assistant-agg"
  - "API keys read only via os.getenv inside service constructors; never logged (T-02-KEY)"
  - "Greeting via TTSSpeakFrame (direct-to-TTS, append_to_context=True), not LLMRunFrame — lowest latency, no LLM round-trip"

requirements-completed: [VOICE-01, VOICE-02, VOICE-03, VOICE-05]

# Metrics
duration: ~25min
completed: 2026-06-24
---

# Phase 1 Plan 02: Local Voice Loop Summary

**The thinnest end-to-end working voice slice — a runnable `python main.py --tenant=demo` bot that serves the browser WebRTC UI, speaks the demo tenant's personalised Italian greeting on connect, holds a streaming Deepgram→Claude→ElevenLabs Italian conversation with sub-budget turn timing, and supports barge-in (including interrupting the greeting itself), all behind the TransportFactory + STTProvider seams.**

## Performance

- **Duration:** ~25 min (excluding the live human-verify gate)
- **Started:** 2026-06-24T08:25Z (approx)
- **Completed:** 2026-06-24T14:50Z (live smoke approved by user; UTF-8 fix applied)
- **Tasks:** 3 (2 automated TDD tasks + 1 human-verify live smoke)
- **Files created:** 5 (+2 test files de-xfailed)

## Accomplishments

- **VOICE-01:** Streaming Deepgram→Claude→ElevenLabs Italian pipeline assembled via `build_pipeline()` in the canonical Pipecat 1.x order, using only 1.x imports (no `PipelineTask`/`OpenAILLMContext`/flat kwargs).
- **VOICE-02 / D-11:** Bot speaks first — `on_client_connected` queues a `TTSSpeakFrame(text=tenant.greeting, append_to_context=True)`; barge-in is active during the greeting because Silero VAD is already running.
- **VOICE-03:** Barge-in via `SileroVADAnalyzer(VADParams(stop_secs=0.3))`; confirmed live (bot stops and listens when interrupted mid-sentence).
- **VOICE-05:** TTS uses the per-tenant ElevenLabs `voice_id` with `eleven_multilingual_v2` + `language=it`; confirmed live (voice matches configured `voice_id`).
- **Seams:** `TransportFactory` (Phase 4 Telnyx swap point) and `STTProvider` ABC with `DeepgramProvider` default + `WhisperProvider` config-selectable (D-08, no auto-failover).
- **Latency guards:** `user_turn_stop_timeout=0.2` (Pitfall 1 fix) and VAD `stop_secs=0.3` explicitly set so the 5s default cannot blow the 800ms budget.
- **Windows clone-and-run:** UTF-8 stdout fix so the bundled pipecat runner emoji banner no longer crashes cp1252 consoles.

## Task Commits

1. **Task 1 (TDD): TransportFactory + STTProvider seam + streaming pipeline** — `7129f3f` (test, RED) → `202d1df` (feat, GREEN)
2. **Task 2 (TDD): bot() + main.py runner wiring + greeting-on-connect** — `deec573` / `2211631` (test, RED) → `bd71b1c` (feat, GREEN)
3. **Task 3 (checkpoint:human-verify): live smoke** — approved by user in browser (greeting auto-plays in Italian, conversation works, barge-in interrupts the bot). No code commit for the gate itself.
   - **Post-gate fix:** `f1b864e` (fix) — Windows UTF-8 stdout so the runner banner doesn't crash startup.

Interim STATE commit: `c9265ae` (chore, Tasks 1-2 checkpoint).

_Plan metadata commit follows this SUMMARY._

## Files Created/Modified

- `src/pipeline/__init__.py` — pipeline package marker.
- `src/pipeline/factory.py` — `STTProvider` ABC + `DeepgramProvider`/`WhisperProvider`; `get_stt_provider()`; `TransportFactory.create_webrtc_transport()`; `build_vad_params()` (stop_secs=0.3), `build_user_aggregator_params()` (user_turn_stop_timeout=0.2), `build_tts_service()` (voice_id/eleven_multilingual_v2). nova-3 upgrade surfaced as a comment only.
- `src/pipeline/build.py` — `build_pipeline(transport, tenant)` → `(pipeline, context)`; assembles transport.input → stt → user-agg → llm → tts → transport.output → assistant-agg with `LLMContext` + `LLMContextAggregatorPair`.
- `src/bot.py` — `async def bot(runner_args)` (reads `--tenant`, loads `TenantConfig`, builds transport+pipeline, runs `PipelineWorker` via `WorkerRunner`); `make_greeting_handler(worker, tenant)` factory; `on_client_connected` greeting wiring.
- `main.py` — `--tenant` argparse arg passed to `pipecat.runner.run.main(parser=...)`; `.env` loaded before service imports; Windows UTF-8 stdout fix at top.
- `tests/test_pipeline.py` — `test_pipeline_builds`, `test_vad_params`, `test_aggregator_timeout`, `test_tts_voice_id` GREEN (xfail removed).
- `tests/test_bot.py` — `test_greeting_injected` GREEN (xfail removed).

## Decisions Made

- **Submodule import paths:** The RESEARCH §interfaces stubs (`from pipecat.services.anthropic import AnthropicLLMService`, `pipecat.transports.network.small_webrtc`) do not resolve in the installed 1.4.0 wheel. Correct paths verified against the venv: `pipecat.services.anthropic.llm`, `pipecat.services.elevenlabs.tts`, `pipecat.transports.smallwebrtc.transport`.
- **make_greeting_handler factory:** Extracted so the greeting handler can be unit-tested by direct invocation, decoupled from the WorkerRunner lifecycle (which the test mocks out).
- **Greeting via TTSSpeakFrame:** Direct-to-TTS (no LLM round-trip) since the greeting is a fixed string in tenant config — lowest latency (RESEARCH Pattern 2).
- **nova-2 retained:** CLAUDE.md locks nova-2; nova-3 Italian WER improvement documented as a config-comment upgrade path only (Open Question 3 resolution).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected Pipecat 1.4.0 submodule import paths**
- **Found during:** Task 1
- **Issue:** Plan/RESEARCH `<interfaces>` listed `from pipecat.services.anthropic import AnthropicLLMService` and `pipecat.transports.network.small_webrtc`, which raise `ImportError`/`ModuleNotFoundError` in the installed 1.4.0 wheel.
- **Fix:** Discovered and used the actual paths: `pipecat.services.anthropic.llm.AnthropicLLMService`, `pipecat.services.elevenlabs.tts.ElevenLabsTTSService`, `pipecat.transports.smallwebrtc.transport.SmallWebRTCTransport`.
- **Files modified:** src/pipeline/factory.py, src/pipeline/build.py, src/bot.py
- **Verification:** All imports load; full test suite green.
- **Committed in:** `202d1df`, `bd71b1c`

**2. [Rule 1 - Bug] Windows UTF-8 stdout — pipecat runner emoji banner crashed startup**
- **Found during:** Task 3 (live smoke on Windows 10)
- **Issue:** `python main.py --tenant=demo` crashed with `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f680'` inside `pipecat/runner/run.py` `_print_startup_message` → `print("🚀 Bot ready!")`. Windows consoles default to cp1252; the bot only ran with `PYTHONUTF8=1`. This breaks the README "clone & run" goal.
- **Fix:** Reconfigured `sys.stdout`/`sys.stderr` to UTF-8 at the top of `main.py` (before any pipecat import or print), guarded by `sys.platform == "win32"` and a try/except so non-Windows and non-reconfigurable streams are unaffected.
- **Files modified:** main.py
- **Verification:** `python -c "import main"` renders the pipecat unicode banner without crashing; `sys.stdout.encoding == "utf-8"`. User confirmed the bot runs without `PYTHONUTF8=1`.
- **Committed in:** `f1b864e`

**3. [Structural] make_greeting_handler factory + test-shape refinement**
- **Issue:** The original RED test attempted to drive the full `bot()` coroutine, but the greeting fires inside an `on_client_connected` event that never triggers when the runner's `run()` is mocked.
- **Fix:** Extracted `make_greeting_handler(worker, tenant)` so the test invokes the handler directly and asserts the queued `TTSSpeakFrame`. The `test_tts_voice_id` assertion was also reshaped to patch `ElevenLabsTTSService.__init__` (preserving the real `Settings` dataclass) so the constructed `voice`/`model` can be inspected.
- **Files modified:** src/bot.py, tests/test_bot.py, tests/test_pipeline.py
- **Committed in:** `2211631`, `bd71b1c`, `202d1df`

---

**Total deviations:** 3 (1 blocking import-path fix, 1 Windows runtime bug, 1 structural test/factory refinement)
**Impact on plan:** All necessary for correctness and clone-and-run on Windows. No scope creep — the pipeline shape and tenant seams are exactly as planned.

## Issues Encountered

- **Mock leakage on patched service classes:** Patching `ElevenLabsTTSService` wholesale made `Settings()` return a MagicMock, so `settings.voice` was un-assertable. Resolved by patching only `__init__` and keeping the real `Settings` dataclass for inspection.

## UAT Note for Plan 01-03 (latency instrumentation)

During the live smoke, the user perceived **"a bit of latency on Claude's side"** while the bot was responding. This is an observation only — Plan 01-03 (per-stage latency instrumentation: STT-final, LLM TTFT, TTS TTFB, transport via native Pipecat `enable_metrics`, D-06) **must measure** this against the <800ms budget. **Do NOT attempt to optimise latency in this plan (01-02)** — `enable_metrics=True` is already set on the `PipelineWorker` so the observer in 01-03 can read the metrics frames directly.

## Known Stubs

- `tests/test_observers.py` (`test_latency_observer`, `test_error_fallback`) remain intentional `xfail` RED stubs owned by **Plan 01-03** (latency observer + error fallback). Not in this plan's scope.
- `WhisperProvider` is wired and config-selectable but inactive by default (D-08); first use downloads ~1.5GB model (documented in README). No auto-failover until Phase 3 (REL-03).

## User Setup Required

None new — the 3 Phase 1 keys (`DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`) + `DEMO_VOICE_ID` from `.env.example` (Plan 01-01) are sufficient. Seed the demo tenant with `python -m src.db.seed_demo` if not already seeded, then `python main.py --tenant=demo`.

## Next Phase Readiness

- The streaming voice loop is live and confirmed in-browser (VOICE-01/02/03/05). Plan 01-03 can now attach the `LatencyObserver` (D-06) and `ErrorFallbackObserver` (REL-01) to the existing `PipelineWorker` (metrics already enabled) and turn the remaining `tests/test_observers.py` stubs GREEN.
- TransportFactory + STTProvider seams are in place for Phase 4 (Telnyx) and the Whisper fallback path.

## Self-Check: PASSED

- All 6 created files verified present on disk (main.py, src/bot.py, src/pipeline/{factory,build,__init__}.py, 01-02-SUMMARY.md).
- All task commits verified in git log: `7129f3f`, `202d1df` (Task 1 RED→GREEN); `deec573`, `2211631`, `bd71b1c` (Task 2 RED→GREEN); `f1b864e` (Windows UTF-8 fix).
- `.venv/Scripts/python -m pytest -q` → **14 passed, 2 xfailed (Plan 03 stubs), 0 failures.**

---
*Phase: 01-local-voice-loop*
*Completed: 2026-06-24*
