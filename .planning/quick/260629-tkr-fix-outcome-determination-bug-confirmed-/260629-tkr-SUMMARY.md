---
phase: quick-260629-tkr
plan: 01
subsystem: call_log
tags: [bug-fix, outcome-determination, tdd, d-06]
dependency_graph:
  requires: []
  provides: [correct-outcome-determination-for-confirmed-bookings]
  affects: [src/call_log/summary.py, tests/test_summary.py]
tech_stack:
  added: []
  patterns: [TDD RED-GREEN, priority-rule reorder]
key_files:
  created: []
  modified:
    - src/call_log/summary.py
    - tests/test_summary.py
decisions:
  - "confirmed_event_id check now precedes generic explicit-outcome check; only 'trasferito' beats it"
  - "Rule 1 split into two: trasferito-specific (Rule 1) and other explicit outcomes (Rule 3)"
metrics:
  duration_minutes: ~5
  completed: "2026-06-29"
  tasks_completed: 2
  files_modified: 2
---

# Quick Task 260629-tkr: Fix Outcome Determination Bug (Confirmed Booking Buried) Summary

**One-liner:** Reordered `_determine_outcome` priority so a watchdog-set 'fallito'/'abbandonato' can never bury a confirmed Google Calendar booking; added four regression tests covering the precedence rules.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Add failing regression tests (TDD RED) | 290ac70 | tests/test_summary.py |
| 2 | Reorder `_determine_outcome` priority (TDD GREEN) | 4f7504e | src/call_log/summary.py |

## What Was Built

**Root cause confirmed:** `_determine_outcome` in `src/call_log/summary.py` had Rule 1 as "any explicit `state['outcome']` wins". After a booking was confirmed, the dead-air watchdog (T2) or `ErrorFallbackObserver` could write `state['outcome'] = 'fallito'`, which Rule 1 returned — burying the `confirmed_event_id`. Verified live: `call_logs id=2` had `outcome='fallito'` but a populated `google_event_id`.

**Fix:** Surgically reordered the six priority rules in `_determine_outcome` only. No changes to `src/bot.py`, watchdog logic, or any other file.

New priority order (D-06):
1. `outcome == 'trasferito'` — deliberate handoff always surfaces to owner, even over a confirmed booking
2. `confirmed_event_id` present — confirmed Google Calendar event can never be downgraded
3. Any other explicit `state['outcome']` — e.g. 'fallito' when no booking was confirmed
4. `faq_answered` truthy — FAQ outcome
5. `booking_slot` without event — abbandonato (D-18 bozza behavior)
6. Default — faq

## Verification

- `_determine_outcome({"confirmed_event_id": "evt", "outcome": "fallito"})` → `"prenotato"` ✓
- `_determine_outcome({"confirmed_event_id": "evt", "outcome": "trasferito"})` → `"trasferito"` ✓
- `_determine_outcome({"confirmed_event_id": "evt"})` → `"prenotato"` ✓
- `_determine_outcome({"confirmed_event_id": "evt", "outcome": "abbandonato"})` → `"prenotato"` ✓
- No changes to `src/bot.py`; watchdog/observer logic untouched ✓
- Full `python -m pytest`: **127 passed, 1 skipped** ✓

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

RED gate: `test(quick-260629-tkr-01)` commit `290ac70` — 4 tests written, 2 failing (tests 1 and 4 as specified)
GREEN gate: `fix(quick-260629-tkr-01)` commit `4f7504e` — all 4 tests pass; full suite green

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. Change is internal outcome taxonomy logic only.

## Self-Check: PASSED

- `src/call_log/summary.py` exists and contains `def _determine_outcome` with corrected rules ✓
- `tests/test_summary.py` contains `confirmed_event_id` regression tests ✓
- Commit `290ac70` exists (test RED) ✓
- Commit `4f7504e` exists (fix GREEN) ✓
- `python -m pytest`: 127 passed, 1 skipped ✓
