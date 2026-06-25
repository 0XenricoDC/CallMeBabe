---
phase: 2
slug: booking-calendar-faq
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-25
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `02-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23.x (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds (in-memory calendar + SQLite; no live Google calls in CI) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Requirement | Behavior | Threat Ref | Test Type | Automated Command | File Exists | Status |
|-------------|----------|------------|-----------|-------------------|-------------|--------|
| D-11 | tenants table has `calendar_id` column after schema migration | — | unit | `pytest tests/test_schema.py::test_calendar_id_column -x` | ❌ W0 (extends test_setup.py) | ⬜ pending |
| BOOK-01 | Collect all booking fields in `flow_manager.state` | — | unit | `pytest tests/test_flows.py::test_booking_field_collection -x` | ❌ W0 | ⬜ pending |
| BOOK-02 | Capacity check prevents over-booking (sum covers < limit) | — | unit | `pytest tests/test_reservation_repo.py::test_capacity_check -x` | ❌ W0 | ⬜ pending |
| BOOK-02 / SC3 | Two concurrent bookings on same slot → exactly one confirms (`BEGIN IMMEDIATE`) | T-2 race | integration | `pytest tests/test_reservation_repo.py::test_concurrent_booking -x` | ❌ W0 | ⬜ pending |
| BOOK-03 | Read-back node does not call `create_event` before confirm | — | unit | `pytest tests/test_flows.py::test_readback_gating -x` | ❌ W0 | ⬜ pending |
| BOOK-04 | `create_event` returns a real event_id (InMemory) | — | unit | `pytest tests/test_calendar_provider.py::test_create_event_returns_id -x` | ❌ W0 | ⬜ pending |
| BOOK-05 | Confirmation node only reachable with real event_id | — | unit | `pytest tests/test_flows.py::test_confirm_only_after_event_id -x` | ❌ W0 | ⬜ pending |
| BOOK-05 | Failed calendar write does NOT confirm | T-1 hallucinated confirm | unit | `pytest tests/test_flows.py::test_no_confirm_on_calendar_failure -x` | ❌ W0 | ⬜ pending |
| BOOK-06 | Confirmed reservation persisted with `status='confermata'` + `google_event_id` | — | unit | `pytest tests/test_reservation_repo.py::test_insert_confirmed -x` | ❌ W0 | ⬜ pending |
| FAQ-01 | `faq_lookup` returns top-k chunks from FTS5 table | — | unit | `pytest tests/test_kb_fts.py::test_faq_lookup -x` | ❌ W0 | ⬜ pending |
| FAQ-02 | Empty FTS5 result returns found=False (no hallucination) | T-1 | unit | `pytest tests/test_kb_fts.py::test_faq_not_found -x` | ❌ W0 | ⬜ pending |
| FAQ-03 | `faq_lookup` only returns chunks for the queried tenant_id | T-3 cross-tenant | unit | `pytest tests/test_kb_fts.py::test_tenant_isolation -x` | ❌ W0 | ⬜ pending |
| D-16 | `parse_italian_date` parses "oggi"/"domani"/"8 luglio" in Europe/Rome | — | unit | `pytest tests/test_date_parser.py::test_italian_dates -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_schema.py::test_calendar_id_column` — extends existing schema/setup test (D-11)
- [ ] `tests/test_flows.py` — booking flow: field collection, read-back gating, tool-result-gated confirmation, calendar-failure → no confirm (BOOK-01, BOOK-03, BOOK-05)
- [ ] `tests/test_reservation_repo.py` — capacity check, concurrent booking, confirmed insert (BOOK-02, BOOK-06, SC3)
- [ ] `tests/test_calendar_provider.py` — InMemoryCalendarProvider interface (BOOK-04, BOOK-05)
- [ ] `tests/test_kb_fts.py` — FTS5 lookup, not-found, tenant isolation (FAQ-01, FAQ-02, FAQ-03)
- [ ] `tests/test_date_parser.py` — Italian date parsing (D-16)
- [ ] Extend `tests/conftest.py` — add `reservation_repo`, `kb_fts`, `in_memory_calendar` fixtures
- [ ] Add deps to `pyproject.toml`: `google-api-python-client>=2.190.0,<3`, `google-auth>=2.50.0,<3`, `google-auth-httplib2>=0.2.0`, `dateparser>=1.4.0,<2`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Google Calendar event appears in the demo tenant's calendar | BOOK-04, SC1 | Requires a live Google Calendar shared with the service-account email; not run in CI (InMemory covers logic) | Configure `GOOGLE_SERVICE_ACCOUNT_JSON` + demo `calendar_id`; place a voice/end-to-end booking; confirm the event with correct title/description appears only after verbal confirmation |
| End-to-end Italian voice booking via WebRTC | SC1 | Real STT/LLM/TTS conversational behavior + barge-in cannot be fully asserted in unit tests | Run the dev WebRTC transport; complete a reservation by voice; verify read-back, capacity decline + alternatives, and FAQ grounding behave per CONTEXT specifics |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
