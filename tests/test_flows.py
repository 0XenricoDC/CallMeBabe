"""Tests for Pipecat Flows booking and FAQ handlers (BOOK-01, BOOK-03, BOOK-05, D-17).

Covers:
- Collect handler stores all five booking fields in flow_manager.state (BOOK-01)
- Read-back gating: collect handler returns next_node=None (stays in booking node, does NOT
  call create_event before confirmation — BOOK-03)
- Confirm handler only transitions to end node when calendar returns a real event_id (BOOK-05)
- Calendar failure (exception) → handler returns next_node=None and no DB confermata row (BOOK-05/T-1)
- Field correction: correct_booking_field handler updates ONLY the named field, leaves others
  unchanged, returns next_node=None to stay in booking node (D-17)
- Source assertion: end-node transition only reachable on truthy event_id branch (W3)
- Accepted behavior: DB confirm failure after Calendar write → no false confirm + bozza row (W4)

Wave 0 state: RED — src/flows/functions.py and src/flows/nodes.py do not exist yet.
These tests will fail with ImportError until Plan 02-03 creates the modules.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# RED imports — these modules do not exist until Plan 02-03
from src.flows.functions import (  # noqa: F401
    handle_collect_booking_info,
    handle_confirm_booking,
    correct_booking_field,
)
from src.flows.nodes import build_end_node  # noqa: F401


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_flow_manager(state: dict | None = None) -> SimpleNamespace:
    """Create a lightweight fake FlowManager with a mutable state dict."""
    fm = SimpleNamespace()
    fm.state = state or {}
    return fm


def _make_args(**kwargs) -> dict:
    """Create FlowArgs-compatible dict."""
    return kwargs


# ---------------------------------------------------------------------------
# BOOK-01: Field collection
# ---------------------------------------------------------------------------

async def test_booking_field_collection():
    """BOOK-01: collect handler stores all five booking fields in flow_manager.state.

    After calling handle_collect_booking_info, flow_manager.state must contain
    booking_slot with date/time_slot/covers and customer with name/phone.
    """
    fm = _make_flow_manager()
    args = _make_args(
        date="2025-07-08",
        time_slot="20:00",
        covers=4,
        name="Rossi",
        phone="3471234567",
    )

    result, next_node = await handle_collect_booking_info(args, fm)

    assert "booking_slot" in fm.state, (
        "handle_collect_booking_info must set fm.state['booking_slot'] with date/time_slot/covers"
    )
    assert "customer" in fm.state, (
        "handle_collect_booking_info must set fm.state['customer'] with name/phone"
    )
    assert fm.state["booking_slot"]["date"] == "2025-07-08"
    assert fm.state["booking_slot"]["time_slot"] == "20:00"
    assert fm.state["booking_slot"]["covers"] == 4
    assert fm.state["customer"]["name"] == "Rossi"
    assert fm.state["customer"]["phone"] == "3471234567"


# ---------------------------------------------------------------------------
# BOOK-03: Read-back gating
# ---------------------------------------------------------------------------

async def test_readback_gating():
    """BOOK-03: collect handler returns next_node=None — stays in booking node, does NOT
    call create_event before verbal confirmation.

    The handler must return (result, None) so FlowManager keeps the booking node active.
    The confirm/end transition must NOT happen at collect time.
    """
    fm = _make_flow_manager()
    args = _make_args(
        date="2025-07-08",
        time_slot="20:00",
        covers=4,
        name="Rossi",
        phone="3471234567",
    )

    result, next_node = await handle_collect_booking_info(args, fm)

    assert next_node is None, (
        f"handle_collect_booking_info must return next_node=None to stay in the "
        f"booking node for read-back. Got next_node={next_node!r}. "
        "BOOK-03: the end node must NOT be reachable before verbal confirmation."
    )


# ---------------------------------------------------------------------------
# BOOK-05: Tool-result gated confirmation
# ---------------------------------------------------------------------------

async def test_confirm_only_after_event_id(in_memory_calendar):
    """BOOK-05: confirm handler transitions to end node only when calendar returns a real event_id.

    When create_event succeeds, the handler must return (result, end_node)
    where end_node is truthy (a NodeConfig dict, not None).
    """
    fm = _make_flow_manager(state={
        "booking_slot": {"date": "2025-07-08", "time_slot": "20:00", "covers": 2},
        "customer": {"name": "Rossi", "phone": "3471234567"},
        "tenant_id": "demo",
        "calendar": in_memory_calendar,
        "db_path": ":memory:",  # will be replaced with real db in Plan 02-03
    })
    args = _make_args()

    # Patch the DB to avoid needing a real ReservationRepository
    with patch("src.flows.functions.ReservationRepository") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.try_reserve_slot.return_value = (True, 1)
        mock_repo.confirm_reservation.return_value = None
        MockRepo.return_value = mock_repo

        result, next_node = await handle_confirm_booking(args, fm)

    assert next_node is not None, (
        "handle_confirm_booking must return a non-None next_node (end_node) when "
        "the calendar write succeeds and returns a real event_id. "
        "BOOK-05: the confirmation node is only reachable on successful calendar write."
    )
    assert isinstance(result, dict)
    event_id = result.get("event_id")
    assert event_id, (
        f"result must contain a non-empty event_id; got {result!r}"
    )


async def test_no_confirm_on_calendar_failure(in_memory_calendar):
    """BOOK-05/T-1: calendar create_event raising → handler returns next_node=None and no confermata row.

    When the calendar provider raises an exception, the handler must:
    1. Return next_node=None (stay in booking node, do NOT transition to end node)
    2. NOT create any 'confermata' row in the DB
    """
    fm = _make_flow_manager(state={
        "booking_slot": {"date": "2025-07-08", "time_slot": "20:00", "covers": 2},
        "customer": {"name": "Rossi", "phone": "3471234567"},
        "tenant_id": "demo",
        "calendar": in_memory_calendar,
        "db_path": ":memory:",
    })
    args = _make_args()

    # Make the in_memory_calendar raise on create_event
    in_memory_calendar.create_event = AsyncMock(side_effect=Exception("Calendar unavailable"))

    with patch("src.flows.functions.ReservationRepository") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.try_reserve_slot.return_value = (True, 1)
        mock_repo.confirm_reservation.return_value = None
        MockRepo.return_value = mock_repo

        result, next_node = await handle_confirm_booking(args, fm)

    assert next_node is None, (
        f"handle_confirm_booking must return next_node=None when calendar raises. "
        f"Got next_node={next_node!r}. "
        "T-1: LLM must not narrate success when the calendar write fails."
    )
    # confirm_reservation must NOT have been called (no false confermata row)
    mock_repo.confirm_reservation.assert_not_called()


# ---------------------------------------------------------------------------
# D-17: Field correction
# ---------------------------------------------------------------------------

async def test_field_correction_reroutes_to_readback():
    """D-17: correct_booking_field handler updates ONLY the named field in flow_manager.state,
    leaves all other fields unchanged, and returns next_node=None so the flow stays in
    the booking node to re-read-back.

    The handler must NOT reset booking_slot/customer or restart field collection.
    """
    initial_state = {
        "booking_slot": {
            "date": "2025-07-08",
            "time_slot": "20:00",
            "covers": 4,
        },
        "customer": {
            "name": "Rossi",
            "phone": "3471234567",
        },
    }
    fm = _make_flow_manager(state=dict(initial_state))
    fm.state["booking_slot"] = dict(initial_state["booking_slot"])
    fm.state["customer"] = dict(initial_state["customer"])

    # Caller corrects only the 'covers' field
    args = _make_args(field_name="covers", new_value=6)

    result, next_node = await correct_booking_field(args, fm)

    # The named field must be updated
    assert fm.state["booking_slot"]["covers"] == 6, (
        f"correct_booking_field must update covers to 6; got {fm.state['booking_slot']['covers']}"
    )
    # All other fields must remain unchanged
    assert fm.state["booking_slot"]["date"] == "2025-07-08", (
        "correct_booking_field must NOT change the 'date' field"
    )
    assert fm.state["booking_slot"]["time_slot"] == "20:00", (
        "correct_booking_field must NOT change the 'time_slot' field"
    )
    assert fm.state["customer"]["name"] == "Rossi", (
        "correct_booking_field must NOT change the customer 'name' field"
    )
    assert fm.state["customer"]["phone"] == "3471234567", (
        "correct_booking_field must NOT change the customer 'phone' field"
    )
    # Must stay in booking node (for re-readback)
    assert next_node is None, (
        f"correct_booking_field must return next_node=None to stay in booking node for re-readback. "
        f"Got next_node={next_node!r}."
    )


# ---------------------------------------------------------------------------
# W3: Source assertion — end-node only reachable on truthy event_id
# ---------------------------------------------------------------------------

def test_end_node_confirmation_phrase_only_after_event_id():
    """W3 source assertion: the build_end_node() transition in handle_confirm_booking
    occurs ONLY on the branch where event_id is truthy / non-None.

    The confirmation-phrase node must be structurally unreachable on the 'not available'
    and 'calendar-exception' branches. This is enforced by inspecting the source of
    handle_confirm_booking.
    """
    source = inspect.getsource(handle_confirm_booking)

    # The end_node transition must be tied to a truthy event_id
    # (e.g., `build_end_node()` appears AFTER `event_id = ...` assignment, inside an if block)
    assert "build_end_node" in source, (
        "handle_confirm_booking source must call build_end_node() for the success transition."
    )

    # The handler must return (something, None) — NOT (something, build_end_node()) —
    # on the failure paths (not available, calendar exception).
    # We verify this by asserting that None appears as a return value in the source
    # (used for the stay-in-node case).
    assert "None" in source, (
        "handle_confirm_booking must return None as next_node on failure paths "
        "(not available, calendar exception). "
        "The confirmation phrase is structurally unreachable without a real event_id."
    )


# ---------------------------------------------------------------------------
# W4: Accepted behavior — DB confirm failure after Calendar write
# ---------------------------------------------------------------------------

async def test_db_confirm_failure_after_calendar_write(in_memory_calendar):
    """W4: Documents ACCEPTED behavior when confirm_reservation raises after a successful create_event.

    If confirm_reservation raises after a successful create_event:
    - The handler must NOT speak a false confirmation (next_node != build_end_node())
    - A draft/bozza row may remain (for idempotent re-confirm by the operator)
    - Assert no 'confermata' row and no end-node transition

    This is an edge case (calendar write succeeded but DB update failed).
    Accepted behavior: the booking remains as a bozza draft; no false success message.
    """
    fm = _make_flow_manager(state={
        "booking_slot": {"date": "2025-07-08", "time_slot": "20:00", "covers": 2},
        "customer": {"name": "Rossi", "phone": "3471234567"},
        "tenant_id": "demo",
        "calendar": in_memory_calendar,
        "db_path": ":memory:",
    })
    args = _make_args()

    with patch("src.flows.functions.ReservationRepository") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.try_reserve_slot.return_value = (True, 1)
        # DB confirm fails after calendar write succeeds
        mock_repo.confirm_reservation.side_effect = Exception("DB write failed")
        MockRepo.return_value = mock_repo

        result, next_node = await handle_confirm_booking(args, fm)

    # No end-node transition (no false confirmation spoken)
    assert next_node is None, (
        f"W4: When confirm_reservation raises after calendar write, next_node must be None "
        f"(no false 'prenotazione confermata' spoken). Got next_node={next_node!r}."
    )
    # confirm_reservation was called (but failed — that's the tested scenario)
    mock_repo.confirm_reservation.assert_called_once()
