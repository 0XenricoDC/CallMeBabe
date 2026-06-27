---
phase: 03-handoff-summary-notifications
plan: 04
subsystem: reliability
tags: [stt-failover, service-switcher, lazy-whisper, escalation, dead-air-watchdog, rel-02, rel-03, rel-04]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: ErrorFallbackObserver (REL-01) + retry-slot logic, build_user_aggregator_params, PipelineWorker/observer wiring
  - phase: 03-plan-01
    provides: transfer seam + outcome state pattern (outcome set in flow_manager.state, EndWorkerFrame UPSTREAM)
  - phase: 03-plan-03
    provides: end-of-call try/finally hook that consumes outcome='fallito' for the notification
provides:
  - LazyWhisperSTTService (deferred model load, D-12) + build_stt_switcher() (REL-03)
  - ServiceSwitcher([deepgram, lazy_whisper], failover) in the pipeline STT slot
  - ErrorFallbackObserver escalation -> outcome='fallito' + courtesy + EndWorkerFrame (REL-02/D-13)
  - Dead-air watchdog (_DeadAirHandler): T1 re-prompt -> T2 transfer (REL-04/D-14)
  - WorkerRefHolder circular-dep helper for the STT-switch courtesy phrase
affects: [phase-04-telnyx]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ServiceSwitcher([primary, lazy_backup], ServiceSwitcherStrategyFailover) for STT auto-failover (REL-03)"
    - "Lazy service: override _load() to no-op + lazy-load model in run_stt() via asyncio.to_thread (D-12)"
    - "WorkerRefHolder: mutable holder for PipelineWorker ref (same circular-dep break as ErrorFallbackObserver.worker)"
    - "Idempotent escalation guard (_escalated bool) so transfer fires exactly once"
    - "Dead-air watchdog: user_idle_timeout=T1 + on_user_turn_idle handler; UserIdleTimeoutUpdateFrame raises to T2 after re-prompt"

key-files:
  created:
    - src/pipeline/stt_switcher.py
    - tests/test_stt_switcher.py
    - tests/test_watchdog.py
    - tests/test_fallback.py
  modified:
    - src/pipeline/build.py
    - src/pipeline/fallback.py
    - src/pipeline/factory.py
    - src/bot.py
    - tests/test_pipeline.py

key-decisions:
  - "LazyWhisperSTTService overrides _load() to no-op + lazy-loads WhisperModel in run_stt() via asyncio.to_thread (D-12); _model is None after construction"
  - "_ESCALATION_THRESHOLD=3 retry-slot cycles before transfer; _escalated guard makes escalation idempotent (REL-02/D-13)"
  - "Dead-air T1=6.0s / T2=8.0s (D-14 Claude's Discretion); UserIdleTimeoutUpdateFrame(T2) after re-prompt so the two windows are distinct"
  - "WorkerRefHolder breaks the circular dep so the on_service_switched courtesy phrase can queue through the worker after worker creation"
  - "ErrorFrame.error never logged in escalation path (V7/T-03-LOG preserved); all courtesy/escalation phrases are static (no PII)"

requirements-completed: [REL-02, REL-03, REL-04]

# Metrics
duration: ~20min
completed: 2026-06-27
---

# Phase 3 Plan 04: Graceful-Degradation Ladder Summary

**STT `ServiceSwitcher` (Deepgram primary -> lazy faster-whisper fallback, D-12) that speaks a courtesy phrase and keeps the call alive on Deepgram failure (REL-03); an extended `ErrorFallbackObserver` that escalates after 3 retry-slot cycles to a courtesy transfer with `outcome='fallito'` (REL-02); and a dead-air `_DeadAirHandler` watchdog that re-prompts at T1=6s and transfers at T2=8s (REL-04) — all wired into `bot.py` reusing the 03-01 transfer/outcome seam and the 03-03 end-of-call hook.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-27T14:25:00Z (approx)
- **Completed (automated tasks):** 2026-06-27T14:45:00Z
- **Tasks:** 3 of 4 complete (Task 4 = live human-verify SC3/SC4/SC5, PENDING)
- **Files modified:** 9 (4 created, 5 modified)

## Accomplishments

- **`src/pipeline/stt_switcher.py` (NEW):**
  - `LazyWhisperSTTService(WhisperSTTService)` — overrides `_load()` to a no-op so the ~1.5GB model is NOT loaded at startup (Pitfall 1); overrides `run_stt()` to lazy-load `WhisperModel` via `asyncio.to_thread()` on the first transcription call (D-12). `_model` is `None` after construction. Uses `settings=WhisperSTTService.Settings(model=Model.LARGE_V3_TURBO, language=Language.IT, ...)` (CLAUDE.md), `device="cpu"`, `compute_type="int8"`, no keepalive (Pitfall 7).
  - `WorkerRefHolder` — mutable holder for the `PipelineWorker` ref (breaks the circular dep, same pattern as `ErrorFallbackObserver.worker`).
  - `build_stt_switcher(holder)` — returns `ServiceSwitcher(services=[deepgram_nova2_IT, lazy_whisper_LV3T_int8], strategy_type=ServiceSwitcherStrategyFailover)` and registers `on_service_switched` to queue a static courtesy `TTSSpeakFrame` ("Un momento, sto risolvendo un problema tecnico...") through the worker. `DEEPGRAM_API_KEY` via `os.getenv` only (T-02-KEY).
- **`src/pipeline/fallback.py` (escalation, REL-02/D-13):** Extended `ErrorFallbackObserver` with `flow_manager=None`, `_escalated=False`, `_escalation_counts` dict, and module constant `_ESCALATION_THRESHOLD=3`. After each exhausted retry-slot cycle the escalation counter increments; on reaching the threshold (and not already escalated) it sets `flow_manager.state["outcome"]="fallito"` and queues `[TTSSpeakFrame("Mi scusi, sto riscontrando problemi tecnici. La trasferisco a un operatore.", append_to_context=False), EndWorkerFrame()]` exactly once. V7/T-03-LOG preserved — `ErrorFrame.error` is never logged; the escalation phrase is static.
- **`src/pipeline/build.py` (REL-03):** Replaced the standalone Deepgram `stt` with `build_stt_switcher(worker_ref_holder)` in the Pipeline STT slot; `BuildResult` now exposes `stt_switcher` and `worker_ref_holder`. Removed unused imports.
- **`src/pipeline/factory.py` (REL-04):** `build_user_aggregator_params()` now passes `user_idle_timeout=6.0` (T1) alongside the existing `user_turn_stop_timeout=0.2` (800ms budget preserved). Added `_WATCHDOG_T1=6.0` / `_WATCHDOG_T2=8.0` constants.
- **`src/bot.py` (wiring):**
  - Patches `build.worker_ref_holder.worker = worker` (REL-03 courtesy phrase) and `error_observer.flow_manager = flow_manager` (REL-02 outcome) after their dependencies exist.
  - Added `_DeadAirHandler` class (REL-04/D-14): `on_idle` count==1 pushes a re-prompt `LLMMessagesAppendFrame(run_llm=True)` and raises the idle timeout to T2 via `UserIdleTimeoutUpdateFrame`; count==2 sets `outcome='fallito'`, pushes a `TTSSpeakFrame` + `EndWorkerFrame` UPSTREAM. `reset()` zeroes the counter.
  - Registers `on_user_turn_idle` and `on_user_turn_started` handlers on `build.aggregators.user()` after `setup_flow()` returns.
- **Tests:** `tests/test_stt_switcher.py` (5), `tests/test_watchdog.py` (3), `tests/test_fallback.py` (4) added; `tests/test_pipeline.py` updated to patch `build_stt_switcher` at its new import site. Full suite: **115 passed, 1 skipped** (the skip is the API-key-gated model-id check) — no regression.

## Task Commits

1. **Task 1 (RED): Failing degradation tests** — `7ed9fce` (test)
2. **Task 1 (GREEN): LazyWhisperSTTService + build_stt_switcher** — `4879e51` (feat)
3. **Task 2: Wire switcher + ErrorFallbackObserver escalation (REL-02/03)** — `fcc6615` (feat)
4. **Task 3: Dead-air watchdog (REL-04/SC5)** — `60261fd` (feat)
5. **Task 4: Live verify SC3/SC4/SC5** — NOT EXECUTED (blocking human-verify checkpoint, DEFERRED — see Pending Human Verification)

**STATE update commit:** `684ca76` (docs: paused at SC3/SC4/SC5 checkpoint)

## Files Created/Modified

- `src/pipeline/stt_switcher.py` — `LazyWhisperSTTService`, `WorkerRefHolder`, `build_stt_switcher()`.
- `src/pipeline/fallback.py` — `ErrorFallbackObserver` escalation (`_ESCALATION_THRESHOLD`, `flow_manager`, `_escalated`).
- `src/pipeline/build.py` — STT slot uses the `ServiceSwitcher`; `BuildResult` exposes `stt_switcher`/`worker_ref_holder`.
- `src/pipeline/factory.py` — `build_user_aggregator_params` adds `user_idle_timeout=T1`; `_WATCHDOG_T1/T2` constants.
- `src/bot.py` — `_DeadAirHandler` + watchdog event handlers; `worker_ref_holder.worker` and `error_observer.flow_manager` patches.
- `tests/test_stt_switcher.py` — REL-03 failover coverage (5 tests).
- `tests/test_watchdog.py` — REL-04 re-prompt/transfer/reset coverage (3 tests).
- `tests/test_fallback.py` — REL-02 escalation-threshold + idempotency coverage (4 tests).
- `tests/test_pipeline.py` — patched to mock `build_stt_switcher` at its build.py import site.

## Decisions Made

- **Lazy Whisper (D-12):** `_load()` no-op + `run_stt()` lazy-load via `asyncio.to_thread` keeps startup fast when Deepgram is healthy; trades a 5-15s first-switch latency for no dead-air (degraded mode > dropped call, SC3; T-03-DOS accepted).
- **Escalation threshold=3 + idempotent guard (REL-02/D-13):** decisive enough to avoid prolonged dead-air, generous enough to ride out transient errors; `_escalated` ensures a single transfer.
- **T1=6s / T2=8s with `UserIdleTimeoutUpdateFrame` (D-14):** the built-in `user_idle_timeout` is a single value, so the handler raises it to T2 after the re-prompt to make the two windows distinct.
- **WorkerRefHolder:** reuses the proven `worker=None` -> patch-after-creation pattern from `ErrorFallbackObserver` so the `on_service_switched` courtesy phrase can be queued through the worker.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_pipeline.py STT mock target after the build.py refactor**
- **Found during:** Task 2
- **Issue:** `test_pipeline_builds` patched `src.pipeline.factory.DeepgramSTTService`, but Task 2 replaced the standalone Deepgram STT in `build.py` with `build_stt_switcher()`. The old patch no longer intercepted STT construction, which would attempt real service init during the test.
- **Fix:** Patched `src.pipeline.build.build_stt_switcher` (and `WorkerRefHolder`) at their build.py import sites instead.
- **Files modified:** tests/test_pipeline.py
- **Verification:** `python -m pytest tests/test_pipeline.py -q` -> 4 passed.
- **Committed in:** `fcc6615` (Task 2 commit)

**Total deviations:** 1 auto-fixed (1 test-mock correction required by the planned refactor).
**Impact on plan:** None — necessary to keep the pipeline test isolated after moving STT construction into `build_stt_switcher`. No scope creep.

## Issues Encountered

- None beyond the test-mock target update (documented as a deviation above).

## Pending Human Verification (SC3 / SC4 / SC5 — BLOCKING, NOT YET DONE)

**Task 4 is a blocking `checkpoint:human-verify` gate that was DEFERRED** (owner chose "Defer & continue"; live mic + forced-failure session not available). SC3/SC4/SC5 are therefore **PENDING manual owner testing** — they are NOT marked passed. The automated portion (Tasks 1-3) is fully complete and green (115 passed, 1 skipped); the live behavioral guarantees still require the owner to run these scenarios with `python main.py --tenant=demo`:

1. **SC3 (REL-03 — Deepgram -> faster-whisper, call uninterrupted):** Set `DEEPGRAM_API_KEY=invalid`, run the bot, speak. Expected: bot says "Un momento, sto risolvendo un problema tecnico..." then continues on faster-whisper (first Whisper response may take 10-20s on CPU while the model lazy-loads). The call is NOT dropped.
2. **SC4 (REL-02 — persistent failure -> courtesy + transfer, outcome fallito):** Set `DEEPGRAM_API_KEY=invalid` AND force Whisper to fail (e.g. set its device to `cuda` on a CPU-only box). After the retry/escalation threshold the bot speaks "Mi scusi, sto riscontrando problemi tecnici. La trasferisco a un operatore." and ends the call; the `call_logs` outcome is `fallito` with no dead-air longer than a few seconds.
3. **SC5 (REL-04 — dead-air watchdog):** Start a normal call (valid Deepgram key) and stay silent ~6s -> bot re-prompts "È ancora in linea?"; stay silent another ~8s -> bot says "Non riesco a sentirla, la passo a un operatore." and transfers (outcome `fallito`).
4. **Lazy-load-at-startup check (D-12):** Confirm faster-whisper is NOT loaded at startup — no model-load delay before the first turn when Deepgram is healthy (check console for absence of a Whisper model-load log at boot).

**Acceptance (to be confirmed by owner):** SC3 failover keeps the call alive with the courtesy phrase; SC4 escalates to courtesy + transfer with `outcome='fallito'` and no long dead-air; SC5 re-prompts then transfers; faster-whisper is lazy at startup.

Phase verification should surface SC3/SC4/SC5 as outstanding human-verification items until the owner confirms.

## User Setup Required

None — live verification uses the existing local WebRTC `python main.py --tenant=demo` path. SC3/SC4 require temporarily setting `DEEPGRAM_API_KEY=invalid` (and, for SC4, forcing the Whisper device to fail); revert afterward.

## Next Phase Readiness

- Phase 3 is code-complete and green across all four plans. The graceful-degradation ladder (STT failover, persistent-failure transfer, dead-air watchdog) is wired and unit-tested; `outcome='fallito'` flows through the 03-03 end-of-call hook to the notification with no extra wiring.
- The `ServiceSwitcher` STT slot and `WorkerRefHolder` pattern carry into Phase 4 (Telnyx) unchanged — the transport swaps behind `TransportFactory` while the STT failover, escalation, and watchdog logic stay put.
- **Blocker/concern:** SC3/SC4/SC5 live verification remains PENDING (owner to run the four scenarios above). Also outstanding from earlier plans: SC1 (03-01) and SC2 (03-03) live verifications.

## Self-Check: PASSED (automated)

Created files verified present and commits verified in git history. The live SC3/SC4/SC5 checkpoint is explicitly recorded as PENDING human verification (not a self-check failure — the automated scope passed).

- FOUND: src/pipeline/stt_switcher.py, tests/test_stt_switcher.py, tests/test_watchdog.py, tests/test_fallback.py
- FOUND commits: 7ed9fce (RED), 4879e51 (GREEN Task 1), fcc6615 (Task 2), 60261fd (Task 3), 684ca76 (STATE)
- Automated tests: 115 passed, 1 skipped (full suite green)

---
*Phase: 03-handoff-summary-notifications*
*Completed (automated tasks): 2026-06-27 — SC3/SC4/SC5 live verification pending*
