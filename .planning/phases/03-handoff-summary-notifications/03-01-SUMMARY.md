---
phase: 03-handoff-summary-notifications
plan: 01
subsystem: telephony
tags: [pipecat-flows, global-functions, transfer, telephony-seam, handoff]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: TenantConfig (transfer_number field), PipelineWorker, FlowManager wiring
  - phase: 02-booking-calendar-faq
    provides: FlowsFunctionSchema handler convention, FAQ node + handle_faq_lookup, booking flow state
provides:
  - TelephonyProvider ABC seam (src/telephony/base.py) for Phase 4 real SIP/Dial
  - LocalTransferStub concrete impl (log-only, no PII)
  - Global transfer_call Flows function invocable from any node (HAND-04)
  - Automatic transfer triggers: explicit request, non-Italian, out-of-scope, FAQ-not-found offer
  - outcome='trasferito' flow state + warm-ready context payload (D-04)
affects: [phase-04-telnyx, summary-notifications, call-log]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TelephonyProvider seam: ABC in base.py + concrete stub in stub.py (mirrors CalendarProvider)"
    - "Global Flows function via FlowManager(global_functions=[...]) — single wiring point, reachable from every node"
    - "T-injection guard: routing target resolved ONLY from trusted tenant config, never from caller tool args"

key-files:
  created:
    - src/telephony/__init__.py
    - src/telephony/base.py
    - src/telephony/stub.py
    - tests/test_transfer.py
  modified:
    - src/flows/functions.py
    - src/flows/nodes.py
    - src/bot.py

key-decisions:
  - "transfer_number resolved exclusively from fm.state['tenant'].transfer_number; args carry only a safe 'reason' (T-03-INJ)"
  - "Handler (not the stub) owns frame side-effects: TTSSpeakFrame handoff phrase + EndWorkerFrame UPSTREAM"
  - "FrameDirection imported from pipecat.processors.frame_processor (NOT pipecat.frames.frames) in 1.4.0"
  - "Transfer wired once via global_functions; nodes do not import the transfer schema (HAND-04)"

patterns-established:
  - "Pattern: telephony seam (base ABC + log-only stub) ready for Phase 4 swap with no conversational-logic change"
  - "Pattern: global Flows function for cross-node capabilities"
  - "Pattern: warm-ready payload assembly (D-04) stored in flow state for downstream real warm transfer"

requirements-completed: [HAND-01, HAND-02, HAND-03, HAND-04]

# Metrics
duration: ~25min
completed: 2026-06-27
---

# Phase 3 Plan 01: Transfer-from-anywhere Summary

**Global `transfer_call` Pipecat Flows function (wired via `FlowManager(global_functions=...)`) reachable from greeting/booking/FAQ, backed by a `TelephonyProvider` seam with a log-only local stub; resolves the operator number from tenant config only, speaks a handoff phrase, records `outcome='trasferito'`, and ends the call cleanly.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-27T13:05:00Z (approx)
- **Completed (automated tasks):** 2026-06-27T13:30:00Z
- **Tasks:** 2 of 3 complete (Task 3 = live human-verify, PENDING)
- **Files modified:** 7 (4 created, 3 modified)

## Accomplishments

- `TelephonyProvider` ABC seam (`src/telephony/base.py`) with `async transfer(number, context)`; docstring mandates trusted-config-only number resolution (T-injection guard). Phase 4 swaps the impl behind this interface with no conversational-logic change.
- `LocalTransferStub` (`src/telephony/stub.py`) — logs transfer intent only (number + reason); never logs caller PII (T-03-LOG). No real telephony API call.
- `build_transfer_schema()` + `handle_transfer_call()` (`src/flows/functions.py`) — global `transfer_call` function: resolves `transfer_number` exclusively from `fm.state['tenant'].transfer_number`, assembles warm-ready payload (D-04), sets `outcome='trasferito'`, queues handoff `TTSSpeakFrame` + `EndWorkerFrame` UPSTREAM, and calls the stub seam.
- FAQ-not-found offer: `handle_faq_lookup` not-found branch now sets `faq_transfer_offered=True` and returns `offer_transfer=True`; FAQ node `role_message` extended to offer `transfer_call` with `reason='fuori_ambito'` (D-03).
- `bot.py` wires `FlowManager(global_functions=[build_transfer_schema()])` — transfer reachable from any node (HAND-04) with a single wiring point.
- Full automated suite green: **77 passed, 1 skipped** (the skip is the API-key-gated model-id check).

## Task Commits

1. **Task 1: Failing transfer tests + TelephonyProvider seam (RED)** - `01242cc` (test)
2. **Task 2: Global transfer function + FAQ offer + global_functions wiring (GREEN)** - `dcd1bcb` (feat)
3. **Task 3: Live verify transfer from any node (SC1)** - NOT EXECUTED (blocking human-verify checkpoint, deferred — see Pending Human Verification)

**STATE update commit:** `25b7823` (docs: paused at Task 3 checkpoint)

## Files Created/Modified

- `src/telephony/__init__.py` - Package marker for the telephony seam.
- `src/telephony/base.py` - `TelephonyProvider` ABC; `async transfer(number, context)`.
- `src/telephony/stub.py` - `LocalTransferStub` — log-only local transfer (no PII).
- `tests/test_transfer.py` - HAND-01/03/04 unit coverage + stub PII test (5 tests).
- `src/flows/functions.py` - `build_transfer_schema()`, `handle_transfer_call()`; FAQ-not-found transfer offer.
- `src/flows/nodes.py` - FAQ node `role_message` extended to offer operator transfer.
- `src/bot.py` - `FlowManager(global_functions=[build_transfer_schema()])` wiring + import.

## Decisions Made

- **T-injection guard (T-03-INJ):** transfer target read only from trusted tenant config; `args` supplies only a logged `reason`. Unit-test `test_transfer_uses_config_number_not_args` asserts a malicious arg is ignored.
- **Frame side-effects in the handler, not the stub:** keeps the stub a pure domain seam; the handler owns `TTSSpeakFrame` + `EndWorkerFrame`.
- **Single global wiring point:** transfer added via `global_functions`; nodes never import the transfer schema (HAND-04).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected `FrameDirection` import path**
- **Found during:** Task 2 (running the GREEN test pass)
- **Issue:** The plan/research examples imported `FrameDirection` from `pipecat.frames.frames`, but in pipecat 1.4.0 it lives in `pipecat.processors.frame_processor`. The original import raised `ImportError`, blocking all transfer tests.
- **Fix:** Split the import — `EndWorkerFrame, TTSSpeakFrame` from `pipecat.frames.frames`; `FrameDirection` from `pipecat.processors.frame_processor`. Verified via venv inspection.
- **Files modified:** src/flows/functions.py
- **Verification:** `python -m pytest tests/test_transfer.py -q` → 5 passed; full suite 77 passed/1 skipped.
- **Committed in:** dcd1bcb (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking import correction)
**Impact on plan:** Necessary to make the code import and tests run. No scope creep. The corrected import is the verified-correct path for pipecat 1.4.0.

## Issues Encountered

- None beyond the `FrameDirection` import path (documented as a deviation above).

## Pending Human Verification (SC1 — BLOCKING, NOT YET DONE)

**Task 3 is a blocking `checkpoint:human-verify` gate that was DEFERRED.** The owner could not run the live mic test in this session. SC1 is therefore **pending manual owner testing** — it is NOT marked passed. The automated portion (Tasks 1-2) is fully complete and green; the live behavioral guarantee still requires the owner to run these 5 spoken scenarios with `python main.py --tenant=demo`:

1. **Explicit request (HAND-01):** At the greeting, say "Voglio parlare con una persona." → bot speaks "La metto in contatto con un operatore, resti in linea." and ends the call; console logs the transfer intent toward the configured `transfer_number`.
2. **Mid-booking (HAND-04, SC1):** Begin a booking, then during the read-back say "Mi passi un operatore." → transfer fires mid-booking-flow.
3. **FAQ-not-found offer (D-03):** In the FAQ flow ask something not in the KB → bot offers "...vuole che la passi a un operatore?"; accept → transfer fires.
4. **Non-Italian (HAND-03):** Speak a sentence in English/another language at the greeting → bot transfers.
5. **Config-number integrity:** Confirm the logged transfer number equals the tenant's configured `transfer_number`, never anything spoken by the caller.

**Acceptance (to be confirmed by owner):** all five spoken scenarios trigger the handoff phrase and a clean shutdown; the logged transfer target equals `tenant.transfer_number`.

Phase verification should surface SC1 as an outstanding human-verification item until the owner confirms.

## User Setup Required

None - no external service configuration required for this plan. (Live verification uses the existing local WebRTC `python main.py --tenant=demo` path.)

## Next Phase Readiness

- Code-complete and green for downstream plans in Phase 3 (summary/notifications, watchdog/STT-failover): the `outcome='trasferito'` state and `transfer_payload` are available for the end-of-call summary hook.
- The `TelephonyProvider` seam is ready for Phase 4 to replace `LocalTransferStub` with a real SIP/Dial implementation without touching conversational logic.
- **Blocker/concern:** SC1 live verification remains PENDING (owner to run the 5 spoken scenarios above).

## Self-Check: PASSED (automated)

Created files verified present and commits verified in git history. Live SC1 checkpoint is explicitly recorded as PENDING human verification (not a self-check failure — the automated scope passed).

- FOUND: src/telephony/base.py, src/telephony/stub.py, src/telephony/__init__.py, tests/test_transfer.py
- FOUND commits: 01242cc (RED), dcd1bcb (GREEN), 25b7823 (STATE)
- Automated tests: 77 passed, 1 skipped

---
*Phase: 03-handoff-summary-notifications*
*Completed (automated tasks): 2026-06-27 — SC1 live verification pending*
