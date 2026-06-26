---
phase: 02-booking-calendar-faq
plan: 03
subsystem: flows
tags: [pipecat-flows, flowmanager, anthropic, booking, llm-override, abandonment]

# Dependency graph
requires:
  - phase: 02-booking-calendar-faq
    plan: 02
    provides: "ReservationRepository with find_available_slots + save_draft; build_booking_node with pre_actions stub; make_abandonment_handler"
provides:
  - "handle_confirm_booking: same-day alternatives + next-day fallback search (D-04/D-05)"
  - "setup_flow(): FlowManager(worker=) wired into bot.py with per-node Sonnet/Haiku override (D-19)"
  - "build_pipeline returns BuildResult dataclass exposing llm + aggregators"
  - "on_client_disconnected abandonment hook saves bozza draft, never to Calendar (D-18)"
  - "W5: single greeting path — FlowManager greeting node only; no double-greeting"
  - "MAX_ALT_DAYS=3 constant for next-day alternative search depth (D-05)"
affects: [02-04, 03, 04]

# Tech tracking
tech-stack:
  added:
    - "stdlib datetime.date + timedelta (next-day search arithmetic)"
    - "dataclasses.dataclass (BuildResult seam)"
    - "pipecat_flows.FlowManager (wired into bot.py)"
    - "pipecat.frames.frames.LLMUpdateSettingsFrame (per-node model delta)"
    - "pipecat.services.settings.LLMSettings (model delta payload)"
  patterns:
    - "BuildResult dataclass: named 4-tuple from build_pipeline for FlowManager seam"
    - "Action handler pattern: async def _handler(action: dict, fm: FlowManager)"
    - "Option B model override: LLMUpdateSettingsFrame delta on single LLM service"
    - "MAX_ALT_DAYS constant guards next-day search depth"

key-files:
  created: []
  modified:
    - src/flows/functions.py
    - src/flows/nodes.py
    - src/bot.py
    - src/pipeline/build.py
    - tests/test_flows.py
    - tests/test_pipeline.py

key-decisions:
  - "[02-03]: Option B (LLMUpdateSettingsFrame delta) chosen over Option A (LLMSwitcher) for per-node model override — keeps pipeline processor list unchanged, simpler bot.py wiring; single LLM service object with model mutated via settings delta"
  - "[02-03]: Greeting reconciliation — FlowManager greeting node is the single greeting source in the live pipeline; on_client_connected TTSSpeakFrame path removed from bot() when FlowManager active; test_single_greeting_on_init (W5) verified ≤1 greeting"
  - "[02-03]: MAX_ALT_DAYS=3 for D-05 next-day search depth (Claude's discretion per CONTEXT)"
  - "[02-03]: BuildResult dataclass from build_pipeline with __iter__ for backward-compat 2-tuple destructuring"
  - "[02-03]: on_client_disconnected guard: only calls save_draft when booking_slot present AND no confirmed_event_id (prevents spurious drafts)"

patterns-established:
  - "FlowManager action handlers registered via flow_manager.register_action(type, handler) in setup_flow() — node configs reference type by name only"
  - "BuildResult from build_pipeline: callers use .llm and .aggregators attributes; old callers use 2-tuple destructuring unchanged"

requirements-completed: [BOOK-02, BOOK-05]

# Metrics
duration: 14min
completed: 2026-06-26
---

# Phase 02 Plan 03: Slot-full Alternatives + FlowManager Pipeline Wiring Summary

**SC2 alternatives proposal (same-day + 3-day forward search) wired into the live pipeline via FlowManager with per-node claude-sonnet-4-6 override and bozza abandonment hook**

## Performance

- **Duration:** 14 min
- **Started:** 2026-06-26T08:15:02Z
- **Completed:** 2026-06-26T08:28:45Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Capacity-decline path now returns `{available: False, alternatives: [...], next_day: {date, slot_time}|None}` — same-day alternatives from `find_available_slots`, next-day fallback up to 3 days forward (D-04/D-05)
- `setup_flow()` in `bot.py` constructs `FlowManager(worker=)`, registers `switch_llm_to_sonnet`/`switch_llm_to_haiku` action handlers, populates tenant state, and calls `flow_manager.initialize(build_greeting_node(tenant))`
- `build_pipeline` extended to `BuildResult` dataclass exposing `llm` + `aggregators` without breaking 2-tuple destructuring
- `on_client_disconnected` hook in `bot()` conditionally calls `make_abandonment_handler` (only when booking_slot present + no confirmed_event_id, D-18)
- 10 test_flows + 5 test_bot tests green; full suite 60 passed / 1 skipped

## Task Commits

1. **Task 1: Slot-full alternatives proposal (same-day + next-day)** - `922dfea` (feat)
2. **Task 2: Wire FlowManager into the pipeline with per-node model override** - `1d212f7` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/flows/functions.py` — added MAX_ALT_DAYS=3 constant, next-day forward search loop in handle_confirm_booking (D-05)
- `src/flows/nodes.py` — added alternatives wording guidance to build_booking_node task_messages
- `src/bot.py` — added setup_flow(), _switch_llm_to_sonnet/haiku handlers, on_client_disconnected abandonment hook, removed double-greeting TTSSpeakFrame
- `src/pipeline/build.py` — added BuildResult dataclass; build_pipeline now returns BuildResult instead of 2-tuple
- `tests/test_flows.py` — added test_alternatives_same_day, test_alternatives_next_day, test_no_event_on_decline
- `tests/test_pipeline.py` — updated test_pipeline_builds to check BuildResult; added llm/aggregators attribute assertions

## Decisions Made

**Model override option (D-19):** Option B (LLMUpdateSettingsFrame delta) chosen over Option A (LLMSwitcher). Rationale: Option A requires adding a new processor to the pipeline list, which changes the pipeline topology. Option B sends a settings delta frame to the existing LLMService — the same mechanism FlowManager already uses for `role_message`. Tradeoff: single service object with mutable model; no separate haiku/sonnet instances. Acceptable because only one booking session runs per pipeline at a time. Documented in SUMMARY per plan requirement.

**Greeting reconciliation (W5):** The FlowManager's `greeting` node with `respond_immediately=True` (default) generates the single greeting utterance via LLM. The `make_greeting_handler` / `on_client_connected` TTSSpeakFrame path is intentionally NOT registered in `bot()` when FlowManager is active. `test_single_greeting_on_init` asserts `len(greeting_frames) <= 1` — passes (0 TTSSpeakFrames queued by setup_flow, which is the correct behavior). The LLM-generated greeting from the node is separate from the TTSSpeakFrame path.

**Next-day search depth (D-05):** MAX_ALT_DAYS=3 (searches up to 3 days forward). Claude's discretion per CONTEXT.md D-05. Balances caller usefulness (not just 1 day) with conciseness (not a week of options).

**BuildResult design:** Dataclass with `__iter__` returning `(pipeline, context)` for backward compat. Exposes `.llm` and `.aggregators` as named attributes for FlowManager wiring. test_pipeline_builds updated to assert `BuildResult` type.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_pipeline_builds expected 2-tuple; build_pipeline now returns BuildResult**
- **Found during:** Task 2 (Wire FlowManager into the pipeline)
- **Issue:** test_pipeline_builds had `assert isinstance(result, tuple)` — fails when BuildResult (a dataclass) is returned even though it supports tuple destructuring via `__iter__`
- **Fix:** Updated test_pipeline_builds to check `isinstance(result, BuildResult)` and verify `.llm`/`.aggregators` attributes; kept 2-tuple destructuring test
- **Files modified:** tests/test_pipeline.py
- **Verification:** test_pipeline_builds passes; all 60 tests green
- **Committed in:** 1d212f7 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — broken test after BuildResult refactor)
**Impact on plan:** Necessary correctness fix. No scope creep.

## Issues Encountered

**Test capacity setup:** Initial test setup for `test_alternatives_same_day` and `test_no_event_on_decline` used 4 covers total (2+2) which was below the 40-cover capacity limit in the demo tenant's `booking_rules`. The slot was NOT full, so the handler called `create_event`. Fixed by using 20+20=40 covers to exactly hit capacity. Lesson: always cross-check seed data against tenant config limits.

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- FlowManager is wired into the live pipeline: `greeting → booking → end` is traversable end-to-end
- Per-node Sonnet override active: booking node uses claude-sonnet-4-6 (D-19)
- Alternatives proposal (D-04/D-05) and abandonment bozza hook (D-18) both implemented and tested
- Plan 02-04 (FAQ routing node) can add `faq_lookup` to the greeting node's functions list — the slot is reserved
- Plan 03 (notifications) can wire the Google Calendar provider into `flow_manager.state["calendar_provider"]`

---
*Phase: 02-booking-calendar-faq*
*Completed: 2026-06-26*

## Self-Check: PASSED

Files verified present:
- FOUND: src/flows/functions.py
- FOUND: src/flows/nodes.py
- FOUND: src/bot.py
- FOUND: src/pipeline/build.py
- FOUND: tests/test_flows.py
- FOUND: tests/test_pipeline.py

Commits verified:
- FOUND: 922dfea (Task 1 — alternatives proposal)
- FOUND: 1d212f7 (Task 2 — FlowManager wiring)
