---
phase: quick-260629-tkr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_summary.py
  - src/call_log/summary.py
autonomous: true
requirements: [D-06, D-07]

must_haves:
  truths:
    - "A call with confirmed_event_id set is reported as 'prenotato' even when a later watchdog/observer set state['outcome']='fallito'."
    - "A call with confirmed_event_id set AND explicit outcome='trasferito' is reported as 'trasferito' (deliberate handoff surfaced to owner)."
    - "A call with confirmed_event_id and no explicit outcome is reported as 'prenotato'."
    - "All pre-existing outcome rules (explicit override with no event, faq_answered, booking_slot-without-event, default) are unchanged."
    - "The full pytest suite passes green."
  artifacts:
    - path: "src/call_log/summary.py"
      provides: "_determine_outcome with corrected priority ordering"
      contains: "def _determine_outcome"
    - path: "tests/test_summary.py"
      provides: "Regression tests for confirmed-booking outcome precedence"
      contains: "confirmed_event_id"
  key_links:
    - from: "src/bot.py:514"
      to: "src/call_log/summary.py:_determine_outcome"
      via: "outcome = _determine_outcome(flow_manager.state)"
      pattern: "_determine_outcome"
---

<objective>
Fix the outcome-determination bug where a genuinely confirmed booking is wrongly reported as 'fallito'.

Root cause (confirmed live): `_determine_outcome` gives Rule 1 (explicit `state['outcome']`)
priority over Rule 2 (`confirmed_event_id` → 'prenotato'). After a booking confirms, the
dead-air watchdog (T2) or error observer can set `state['outcome'] = 'fallito'`, which then
buries a successful booking (verified: call_logs id=2 has outcome='fallito' but a populated
google_event_id).

Purpose: Owners must receive accurate end-of-call outcomes — a confirmed Google Calendar
booking must never be downgraded to 'fallito'/'abbandonato' by a later watchdog event.
Output: Corrected priority ordering in `_determine_outcome` plus regression tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@src/call_log/summary.py

<interfaces>
<!-- Current (buggy) priority in src/call_log/summary.py:_determine_outcome -->
<!-- Rule 1: if state.get("outcome"): return state["outcome"]   <-- this buries 'prenotato' -->
<!-- Rule 2: if state.get("confirmed_event_id"): return "prenotato" -->
<!-- Rule 3: if state.get("faq_answered"): return "faq" -->
<!-- Rule 4: if state.get("booking_slot") and not confirmed_event_id: return "abbandonato" -->
<!-- Rule 5: return "faq" -->

<!-- Consumed by src/bot.py:514 (end-of-call hook), DO NOT modify bot.py: -->
<!--   outcome = _determine_outcome(flow_manager.state) -->

<!-- Existing _determine_outcome tests live in tests/test_call_log.py (lines 172-216); -->
<!-- they must STILL pass after the fix. New regression tests go in tests/test_summary.py. -->

Outcome taxonomy (D-06): 'prenotato' | 'faq' | 'trasferito' | 'abbandonato' | 'fallito'
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add failing regression tests for confirmed-booking precedence</name>
  <files>tests/test_summary.py</files>
  <behavior>
    - confirmed_event_id set AND outcome='fallito' → 'prenotato' (watchdog must not bury a booking)
    - confirmed_event_id set AND outcome='trasferito' → 'trasferito' (deliberate handoff still surfaced)
    - confirmed_event_id set AND no explicit outcome → 'prenotato' (happy-path guard, unchanged)
    - confirmed_event_id set AND outcome='abbandonato' → 'prenotato' (downgrade guard)
  </behavior>
  <action>
    Append a new test section to tests/test_summary.py covering the outcome-precedence
    regression. Import `_determine_outcome` from `src.call_log.summary` inside each test
    (match the existing `# noqa: PLC0415` import style used in tests/test_call_log.py).
    Add at minimum these synchronous tests:
    (1) test_determine_outcome_confirmed_event_beats_fallito — state
        {"confirmed_event_id": "evt-9", "outcome": "fallito"} asserts == "prenotato".
    (2) test_determine_outcome_trasferito_beats_confirmed_event — state
        {"confirmed_event_id": "evt-9", "outcome": "trasferito"} asserts == "trasferito".
    (3) test_determine_outcome_confirmed_event_no_explicit_outcome — state
        {"confirmed_event_id": "evt-9"} asserts == "prenotato".
    (4) test_determine_outcome_confirmed_event_beats_abbandonato — state
        {"confirmed_event_id": "evt-9", "outcome": "abbandonato"} asserts == "prenotato".
    These are plain dict-in / string-out asserts — no mocks, no async. They MUST fail
    (tests 1 and 4) against the current buggy ordering, proving RED before Task 2.
  </action>
  <verify>
    <automated>cd "C:/Users/gaiad/OneDrive/Desktop/coding/CallMeBabe" && python -m pytest tests/test_summary.py -k "confirmed_event or trasferito_beats" -x</automated>
  </verify>
  <done>Four new tests exist; tests 1 and 4 FAIL against current code (RED), confirming the bug is reproduced.</done>
</task>

<task type="auto">
  <name>Task 2: Reorder _determine_outcome priority and run full suite</name>
  <files>src/call_log/summary.py</files>
  <action>
    Surgically reorder the priority rules in `_determine_outcome` ONLY. Do NOT touch
    `generate_summary`, and do NOT touch any watchdog/observer logic in src/bot.py.
    Preserve the existing module docstring security notes (T-03-PII, T-03-KEY) and the
    PII-safe comments — update only the docstring's "Priority" list to match the new order.

    New priority order (per D-06 required behavior):
    1. If state['outcome'] == 'trasferito' → return 'trasferito'
       (deliberate human handoff is always surfaced to the owner, even over a booking).
    2. If state.get('confirmed_event_id') → return 'prenotato'
       (a confirmed Google Calendar event must NEVER be downgraded to 'fallito'/'abbandonato'
        by a later dead-air watchdog or error observer).
    3. If state.get('outcome') → return state['outcome']
       (any other explicit override — e.g. 'fallito' when no booking — still wins).
    4. If state.get('faq_answered') → return 'faq'.
    5. If state.get('booking_slot') and not state.get('confirmed_event_id') → 'abbandonato'.
    6. Default → return 'faq'.

    Update the inline rule comments to reflect why 'trasferito' and 'confirmed_event_id'
    now precede the generic explicit-outcome check (reference the burying-a-booking bug).
  </action>
  <verify>
    <automated>cd "C:/Users/gaiad/OneDrive/Desktop/coding/CallMeBabe" && python -m pytest</automated>
  </verify>
  <done>The four new regression tests pass; the existing _determine_outcome tests in tests/test_call_log.py (explicit_override with trasferito, confirmed_event, faq_answered, booking_slot_no_event, empty_state, trasferito_from_01) still pass; the FULL pytest suite is green.</done>
</task>

</tasks>

<verification>
- `_determine_outcome({"confirmed_event_id": "evt", "outcome": "fallito"})` returns 'prenotato'.
- `_determine_outcome({"confirmed_event_id": "evt", "outcome": "trasferito"})` returns 'trasferito'.
- `_determine_outcome({"confirmed_event_id": "evt"})` returns 'prenotato'.
- No changes to src/bot.py; watchdog/observer logic untouched.
- Full `python -m pytest` run is green before commit.
</verification>

<success_criteria>
- A confirmed booking (confirmed_event_id present) is reported 'prenotato' unless an explicit
  'trasferito' handoff occurred.
- A confirmed booking is never downgraded to 'fallito' or 'abbandonato'.
- All previously-passing tests remain green; four new regression tests pass.
</success_criteria>

<output>
Create `.planning/quick/260629-tkr-fix-outcome-determination-bug-confirmed-/260629-tkr-SUMMARY.md` when done.
</output>
