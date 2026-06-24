---
phase: 01-local-voice-loop
plan: 03
subsystem: observability
tags: [pipecat, observers, metrics, ttfb, latency, error-fallback, elevenlabs, italian, jsonl]

# Dependency graph
requires:
  - phase: 01-02
    provides: "Runnable PipelineWorker (Deepgram→Claude→ElevenLabs) with enable_metrics=True; TransportFactory/STTProvider seams; greeting-on-connect; bot()/main.py runner"
provides:
  - "LatencyObserver — per-turn console line + JSONL (response_ms = stt+llm_ttft+tts_ttfb), [WARN] when response latency > 800ms (VOICE-04 / D-06)"
  - "ErrorFallbackObserver — non-fatal ErrorFrame → single Italian courtesy phrase, one retry slot, no secret leakage (REL-01 / D-07)"
  - "Correct pipecat 1.4.0 observer wiring: observers passed via PipelineWorker(observers=[...]); turn-end via worker.turn_tracking_observer.on_turn_ended"
  - "logs/latency.jsonl per-turn timing log for downstream latency optimisation analysis"
  - "Opt-in LATENCY_DEBUG summary (push_calls/metrics_frames_seen) for attachment diagnosis"
affects: [Phase 2 booking-flow, Phase 3 transfer/fallback, future latency-optimisation pass]

# Tech tracking
tech-stack:
  added:
    - "LatencyObserver(BaseObserver) — routes TTFBMetricsData by metric.processor"
    - "ErrorFallbackObserver(BaseObserver) — courtesy phrase on ErrorFrame"
    - "TurnTrackingObserver.on_turn_ended event hook (built-in, enable_turn_tracking=True)"
  patterns:
    - "Custom observers attach via PipelineWorker(observers=[...]) — NOT PipelineParams"
    - "Metrics routing on metric.processor (service name), not data.source.name"
    - "Defensive on_push_frame (try/except) — WorkerObserver proxy has none"
    - "Response-latency budget (sum of per-stage TTFB), turn_ms as context only"

key-files:
  created:
    - "src/pipeline/observers.py — LatencyObserver (per-turn line + JSONL, 800ms warn, turn-end via TurnTrackingObserver)"
    - "src/pipeline/fallback.py — ErrorFallbackObserver + COURTESY_PHRASE (REL-01, D-07, V7-safe)"
  modified:
    - "src/bot.py — observers passed to PipelineWorker(observers=[...]); register_turn_end wiring; error_observer.worker patched post-construction"
    - "src/pipeline/factory.py — TTS model eleven_turbo_v2_5 + Language.IT (honors language, kills warning)"
    - "src/db/seed_demo.py — load_dotenv() in _main() so DEMO_VOICE_ID is honored"
    - "tests/test_observers.py — full latency + fallback + attachment regression suite (de-xfailed)"
    - "tests/test_pipeline.py — TTS model assertion updated to eleven_turbo_v2_5 + language=it"
    - "tests/conftest.py — mock_tts model updated"

key-decisions:
  - "Custom observers MUST be passed via PipelineWorker(observers=[...]); PipelineParams has no observers field and silently drops the kwarg"
  - "Turn-end driven by built-in TurnTrackingObserver.on_turn_ended, not inferred from a raw frame in on_push_frame"
  - "Metrics routed on metric.processor (service name) with TTS checked first to avoid the 'stt' substring inside 'ElevenLabsTTSService'"
  - "Budget = response latency (stt+llm_ttft+tts_ttfb), not total turn duration"
  - "TTS switched to eleven_turbo_v2_5 — only flash/turbo v2_5 honor the language code in pipecat 1.4.0"

patterns-established:
  - "Observer attachment surface in pipecat 1.4.0: PipelineWorker(observers=[...]) → WorkerObserver proxy → on_push_frame"
  - "All observer hot-path code wrapped in try/except (proxy task dies on unhandled exception)"
  - "Diagnostics opt-in via env flag at loguru DEBUG, never print, never raw error/secret (V7)"

requirements-completed: [VOICE-04, REL-01]

# Metrics
duration: ~3h (incl. 4 live-verify iterations)
completed: 2026-06-24
---

# Phase 1 Plan 03: Per-Stage Latency Instrumentation + Error-Fallback Courtesy Phrase Summary

**Two non-intrusive `BaseObserver`s on the existing PipelineWorker: a LatencyObserver that logs per-turn response latency (`response=Xms | stt=.. llm_ttft=.. tts_ttfb=..`) to console + `logs/latency.jsonl` and warns over the 800ms budget, and an ErrorFallbackObserver that speaks a single Italian courtesy phrase on any non-fatal provider error instead of going silent — both verified live with real API round-trips.**

## Performance

- **Duration:** ~3h (3 automated tasks committed quickly; the bulk was four live-verify iterations that surfaced real integration bugs)
- **Completed:** 2026-06-24
- **Tasks:** 4 (3 automated TDD/auto + 1 blocking human-verify live gate)
- **Files created:** 2 (observers.py, fallback.py); 5 modified

## Accomplishments

- **VOICE-04 / D-06 (verified live):** Per-stage TTFB latency captured from native Pipecat metrics and emitted both as a per-turn console line and a JSONL record. Real measured numbers from the live session (`logs/latency.jsonl`): warm turns `response≈1.7s` (stt≈530–740, llm_ttft≈786–882, tts_ttfb≈270–325), cold-start first turn `response≈3.3s` (llm_ttft 2311). Routing correct (TTFB elevenlabsttsservice→tts etc.), no stt/tts collision.
- **REL-01 / D-07 (verified live):** With an invalidated Anthropic key, the bot speaks "Mi scusi, ho avuto un problema tecnico, può ripetere?" instead of dead-air. One generic phrase, one retry slot, no secret leakage.
- **Correct observer wiring discovered and locked:** custom observers attach via `PipelineWorker(observers=[...])`; the previous `PipelineParams(observers=[...])` silently dropped them.
- **Live diagnostics path:** `LATENCY_DEBUG=1` opt-in summary (push_calls/metrics_frames_seen) was the instrument that pinpointed the root cause (push_calls=0).

## Task Commits

1. **Task 1 (TDD): LatencyObserver** — `cddb71e` (test RED) → `d4589ae` (feat GREEN)
2. **Task 2 (TDD): ErrorFallbackObserver** — `b1e2806` (feat GREEN; tests in the same RED commit)
3. **Task 3 (auto): wire observers into worker** — `96bcf41` (initial, later corrected)
4. **Task 4 (checkpoint:human-verify): live smoke** — approved live by the user after the fixes below.

**Live-verification fixes (deviations, see below):** `32f31fd`, `f95f27c`, `d81a41c`, `23e0cf2`, `7804d91`, and the root-cause fix `7804d91`.

_Plan metadata commit follows this SUMMARY._

## Files Created/Modified

- `src/pipeline/observers.py` — `LatencyObserver`: routes `TTFBMetricsData` by `metric.processor`; turn-end via `register_turn_end(worker.turn_tracking_observer)` on `on_turn_ended`; prints `response=Xms | stt=.. llm_ttft=.. tts_ttfb=.. (turn=Yms)`, appends JSONL `{ts,turn_ms,response_ms,stt_ms,llm_ttft_ms,tts_ttfb_ms}`, `[WARN]` when `response_ms>800`; defensive try/except; opt-in `LATENCY_DEBUG` summary.
- `src/pipeline/fallback.py` — `ErrorFallbackObserver` + `COURTESY_PHRASE`; non-fatal `ErrorFrame` → one retry slot per source → `TTSSpeakFrame(courtesy)`; never logs the raw error or `*_API_KEY` (V7).
- `src/bot.py` — `PipelineWorker(pipeline, observers=[latency, error], params=PipelineParams(enable_metrics=True, enable_usage_metrics=True))`; `error_observer.worker` patched post-construction; `latency.register_turn_end(worker.turn_tracking_observer)`.
- `src/pipeline/factory.py` — TTS `model="eleven_turbo_v2_5"`, `language=Language.IT`.
- `src/db/seed_demo.py` — `load_dotenv()` at the start of `_main()`.
- `tests/test_observers.py` — latency routing/format/budget, real-flow + bad-frame regressions, observer-attachment regressions, fallback + no-secret-leak.

## Decisions Made

- **Observer attachment:** via `PipelineWorker(observers=[...])`. `PipelineParams` (Pydantic) has no `observers` field and silently discards the kwarg.
- **Turn-end signal:** the built-in `TurnTrackingObserver.on_turn_ended` (reliable across barge-in/timeouts), not a raw frame in `on_push_frame`.
- **Metrics routing key:** `metric.processor` (the originating service name), per the official `MetricsLogObserver`.
- **Budget semantics:** `<800ms` applies to response latency (`stt+llm_ttft+tts_ttfb`), with `turn_ms` kept as context only.
- **TTS model:** `eleven_turbo_v2_5` — only `eleven_flash_v2_5`/`eleven_turbo_v2_5` are in pipecat 1.4.0's `ELEVENLABS_MULTILINGUAL_MODELS`, so only they honor `language=it`.

## Deviations from Plan

All discovered during the live human-verify gate (Task 4). Each was a real integration bug invisible to the original unit tests (green in isolation, broken integrated).

### Auto-fixed Issues

**1. [Rule 1 - Bug] PipelineParams has no `observers` field — observers never attached (ROOT CAUSE)**
- **Found during:** Task 4 (live). Diagnostics showed `push_calls=0`, `metrics_frames_seen=0` — `on_push_frame` never fired.
- **Issue:** Observers were passed via `PipelineParams(observers=[...])`; `PipelineParams` is a Pydantic model with no `observers` field, so the kwarg was silently dropped. Neither LatencyObserver nor ErrorFallbackObserver was registered with the `WorkerObserver` proxy — breaking BOTH deliverables. The worker's own `turn_tracking_observer` kept working only because the worker appends it to the internal list directly.
- **Fix:** Pass observers via the dedicated `PipelineWorker(observers=[...])` kwarg (verified against the 1.4.0 `PipelineWorker.__init__` signature and `WorkerObserver(observers=...)`).
- **Verification:** `test_custom_observers_attached_to_worker` (builds a real worker, asserts the observer is in `worker._observer._observers`) + `test_pipeline_params_has_no_observers_field` guard; live `push_calls=26423`.
- **Committed in:** `7804d91`

**2. [Rule 1 - Bug] Turn-end via on_push_frame never reached _flush_turn live**
- **Found during:** Task 4 (live). `logs/latency.jsonl` never populated despite a completed turn.
- **Issue:** Inferring turn end from `BotStoppedSpeakingFrame` inside `on_push_frame` was unreliable.
- **Fix:** Drive turn end from the built-in `TurnTrackingObserver.on_turn_ended` event via `register_turn_end`.
- **Verification:** `test_latency_observer_real_flow`; live JSONL accumulates one record per turn.
- **Committed in:** `32f31fd`

**3. [Rule 1 - Bug] Substring collision: "ElevenLabsTTSService" contains "stt"**
- **Found during:** Task 1 (caught by the updated real-name test) and confirmed live.
- **Issue:** `"ElevenLabsTTSService".lower()` contains `stt` (…lab[s+tts]ervice); a naive `"stt" in proc` misrouted TTS metrics into the STT bucket.
- **Fix:** Route on vendor names + `ttsservice`/`sttservice`/`llmservice` tokens, TTS checked first.
- **Verification:** `test_latency_observer` with real service names; live routing correct.
- **Committed in:** `32f31fd`

**4. [Rule 2 - Missing Critical] on_push_frame exception killed the observer for the session**
- **Found during:** Source review for Task 4 (LEAD 1).
- **Issue:** `WorkerObserver._proxy_task_handler` calls `await observer.on_push_frame(data)` with no try/except — one exception kills that observer's proxy task for the whole session.
- **Fix:** Wrap the `on_push_frame` body in try/except; log only `type(exc).__name__` at DEBUG (no frame contents/secrets, V7).
- **Verification:** `test_latency_observer_survives_bad_frame` (MetricsFrame with `data=None` must not raise and must not disable later routing).
- **Committed in:** `32f31fd`

**5. [Rule 1 - Bug] Budget semantics: turn_ms vs response latency**
- **Found during:** Task 4 (live). Records showed `turn_ms` 8000–28000ms — useless as a <800ms check.
- **Issue:** `turn_ms` includes the user's speaking time; the D-06 budget is the response latency.
- **Fix:** Compute `response_ms = stt+llm_ttft+tts_ttfb`; apply `[WARN]` to it; keep `turn_ms` as context; record both in JSONL.
- **Verification:** `test_latency_observer_no_warn_when_response_under_budget` (large turn_ms + sub-800 response must not warn).
- **Committed in:** `23e0cf2`

**6. [Rule 1 - Bug] ElevenLabs language code ignored on eleven_multilingual_v2**
- **Found during:** Task 4 (live log warning).
- **Issue:** `"Language code [it] not applied... eleven_flash_v2_5, eleven_turbo_v2_5"`. The old default isn't in pipecat 1.4.0's `ELEVENLABS_MULTILINGUAL_MODELS`, so Italian was silently ignored.
- **Fix:** `model="eleven_turbo_v2_5"`, `language=Language.IT` (field name verified as `model`). Warning gone; turbo is also lower-latency.
- **Verification:** updated `test_tts_voice_id`; live warning disappeared.
- **Committed in:** `f95f27c`

**7. [Rule 1 - Bug] seed_demo ignored DEMO_VOICE_ID (no .env loaded)**
- **Found during:** Task 4 (workflow repeatability).
- **Issue:** `python -m src.db.seed_demo` read `os.getenv("DEMO_VOICE_ID")` but never loaded `.env`, always falling back to the default voice.
- **Fix:** `load_dotenv()` at the start of `_main()` (run-time, not import-time, so test fixtures keep the pure default).
- **Verification:** no-env → default; env set → honored.
- **Committed in:** `d81a41c`

---

**Total deviations:** 7 auto-fixed (5 bugs, 1 missing-critical, plus the budget-semantics correction). The root cause (#1) affected both deliverables.
**Impact on plan:** All necessary for correctness and for the deliverables to function live. No scope creep — the pipeline body was never changed; everything attaches via observers exactly as planned. The deviations are valuable learnings about pipecat 1.4.0's observer/metrics surface.

## Issues Encountered

- **Green-in-isolation, broken-integrated:** the original unit tests exercised `_flush_turn`/`on_push_frame` with synthetic frames and passed, while the live pipeline never invoked the observers. Resolved by adding integration-level regression tests (observer attachment to a real worker; real-flow turn-end + metrics).
- The diagnostic cycle (instrument → live run → real DEBUG lines → fix) was essential; guessing would not have found the `PipelineParams` silent-drop.

## UAT / Optimisation Note (OUT OF SCOPE for 01-03 — future optimisation pass)

The instrumentation this plan delivered now makes the latency budget measurable, and the live data shows the bot is **over the <800ms budget at steady state**:

- **Response latency ≈ 1.7s warm**, **≈ 3.3s cold-start** (first turn).
- **Dominated by Claude TTFT** (~786–882ms warm, 2311ms cold) and **STT** (~530–740ms); TTS TTFB is healthy (~270–325ms).
- **Levers identified from the data (NOT implemented here):**
  - (a) **Anthropic prompt caching is NOT active** (`cache_read_input_tokens=0`) — enabling it on the system prompt should cut LLM TTFT.
  - (b) **Cold-start** penalty on the first turn.
  - (c) Evaluate model/streaming choices for STT and LLM.

Plan 01-03's scope was to **deliver the measurement**, which it did; the actual optimisation is a future pass (the owner already flagged "a bit of latency on Claude's side" in 01-02 UAT).

## Known Stubs

None. The two observers are fully wired and live-verified. `tests/test_observers.py` xfail stubs from Plan 01 are now implemented and green.

## User Setup Required

None new — the three Phase 1 keys + `DEMO_VOICE_ID` from `.env.example` are sufficient. `LATENCY_DEBUG=1` is an optional diagnostic env flag.

## Next Phase Readiness

- VOICE-04 and REL-01 complete and live-verified — Phase 1's cross-cutting observability and resilience are in place.
- `logs/latency.jsonl` provides the data foundation for the future latency-optimisation pass (prompt caching, cold-start).
- Observer wiring pattern (`PipelineWorker(observers=[...])`) and the metric-routing/turn-end conventions are established for any future per-stage instrumentation.

## Self-Check: PASSED

- All created/modified files verified present on disk (observers.py, fallback.py, bot.py, factory.py, seed_demo.py, 01-03-SUMMARY.md).
- All task + deviation commits verified in git log: `cddb71e`, `d4589ae`, `b1e2806`, `96bcf41`, `32f31fd`, `f95f27c`, `d81a41c`, `23e0cf2`, `7804d91`, `724ddae`.
- `.venv/Scripts/python -m pytest -q` → 25 passed, 0 xfailed, 0 failures.

---
*Phase: 01-local-voice-loop*
*Completed: 2026-06-24*
