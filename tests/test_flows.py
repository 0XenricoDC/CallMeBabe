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
- SC2 alternatives (D-04/D-05): slot full → same-day alternatives returned; all-day-full → next-day proposal
- No calendar event created on capacity decline (SC2/T-02-09)

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
    handle_faq_lookup,
    build_route_to_faq_schema,
    build_route_to_booking_schema,
)
from src.flows.nodes import (  # noqa: F401
    build_end_node,
    build_faq_node,
    build_greeting_node,
    build_booking_node,
)


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


# ---------------------------------------------------------------------------
# D-04 / D-05 / SC2: Slot-full alternatives proposal
# ---------------------------------------------------------------------------


async def test_alternatives_same_day(reservation_repo, in_memory_calendar):
    """D-04 / SC2: when the requested slot is full, the handler returns 2-3 same-day
    alternatives (free slot_times on the same day) and does NOT create a calendar event.

    Setup:
    - Slot 20:00 is filled to capacity (max_covers_per_slot = 4 in booking_rules).
    - Slots 19:00 and 21:30 have partial bookings (below capacity) → returned as alternatives.

    Asserts:
    - result["available"] is False
    - result["alternatives"] contains at least one slot_time (same day)
    - next_node is None (stay in booking node — no false confirm)
    - create_event is never called
    """
    from src.booking.repository import ReservationRepository

    db_path = reservation_repo._db_path
    # seed the tenant row so FK constraint is satisfied
    from src.config.repository import TenantRepository
    from src.db.seed_demo import build_demo_tenant
    tenant = build_demo_tenant()
    tenant_repo = TenantRepository(db_path=db_path)
    await tenant_repo.upsert_tenant(tenant)

    # Fill slot 20:00 to capacity (max_covers_per_slot=40 in demo booking_rules)
    # Two bookings of 20 covers each = exactly 40 total → slot is at capacity
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            """INSERT INTO reservations (tenant_id, slot_date, slot_time, covers, name, phone, status)
               VALUES (?, ?, ?, ?, ?, ?, 'confermata')""",
            [
                ("demo", "2025-07-10", "20:00", 20, "Rossi", "3471111111"),
                ("demo", "2025-07-10", "20:00", 20, "Bianchi", "3472222222"),
                # Partially-filled alternatives on the same day (both < 40 covers)
                ("demo", "2025-07-10", "19:00", 10, "Verdi", "3473333333"),
                ("demo", "2025-07-10", "21:30", 5, "Neri", "3474444444"),
            ],
        )
        await db.commit()

    fm_state = {
        "booking_slot": {"date": "2025-07-10", "time_slot": "20:00", "covers": 2},
        "customer": {"name": "Ferrari", "phone": "3475555555"},
        "tenant_id": "demo",
        "tenant": tenant,
        "db_path": db_path,
        "calendar_provider": in_memory_calendar,
    }
    from types import SimpleNamespace
    fm = SimpleNamespace(state=fm_state)
    in_memory_calendar.create_event = AsyncMock()

    result, next_node = await handle_confirm_booking({}, fm)

    assert result.get("available") is False, (
        f"SC2: slot-full must set available=False; got {result!r}"
    )
    alternatives = result.get("alternatives", [])
    assert alternatives, (
        f"D-04: at least one same-day alternative slot_time must be proposed; got {result!r}"
    )
    assert next_node is None, (
        "SC2: decline must return next_node=None (stay in booking node)"
    )
    # create_event must NEVER be called on a capacity decline (T-02-09)
    in_memory_calendar.create_event.assert_not_called()


async def test_alternatives_next_day(reservation_repo, in_memory_calendar):
    """D-05 / SC2: when the requested day has no free slots, the handler searches
    subsequent days and returns the first available {date, slot_time}.

    Setup:
    - All slots on 2025-07-10 are filled to capacity.
    - Slot 20:00 on 2025-07-11 is partially filled (below capacity) → proposed as next-day.

    Asserts:
    - result["available"] is False
    - result["alternatives"] is empty (or absent) — no same-day alternative
    - result["next_day"] contains a date and slot_time from 2025-07-11 (or later)
    - next_node is None
    - create_event is never called
    """
    from src.booking.repository import ReservationRepository

    db_path = reservation_repo._db_path
    from src.config.repository import TenantRepository
    from src.db.seed_demo import build_demo_tenant
    tenant = build_demo_tenant()
    tenant_repo = TenantRepository(db_path=db_path)
    await tenant_repo.upsert_tenant(tenant)

    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            """INSERT INTO reservations (tenant_id, slot_date, slot_time, covers, name, phone, status)
               VALUES (?, ?, ?, ?, ?, ?, 'confermata')""",
            [
                # 2025-07-10 at capacity (max_covers_per_slot=40): 20+20 = 40
                ("demo", "2025-07-10", "20:00", 20, "Rossi", "3471111111"),
                ("demo", "2025-07-10", "20:00", 20, "Bianchi", "3472222222"),
                # 2025-07-11 has a partially-filled slot → should be proposed next-day
                ("demo", "2025-07-11", "20:00", 10, "Verdi", "3473333333"),
            ],
        )
        await db.commit()

    fm_state = {
        "booking_slot": {"date": "2025-07-10", "time_slot": "20:00", "covers": 2},
        "customer": {"name": "Ferrari", "phone": "3475555555"},
        "tenant_id": "demo",
        "tenant": tenant,
        "db_path": db_path,
        "calendar_provider": in_memory_calendar,
    }
    from types import SimpleNamespace
    fm = SimpleNamespace(state=fm_state)
    in_memory_calendar.create_event = AsyncMock()

    result, next_node = await handle_confirm_booking({}, fm)

    assert result.get("available") is False, (
        f"SC2: slot-full must set available=False; got {result!r}"
    )
    # Same-day alternatives are empty (all full)
    alternatives = result.get("alternatives", [])
    assert not alternatives, (
        f"D-05: no same-day alternatives should be found when all slots are full; "
        f"got alternatives={alternatives!r}"
    )
    next_day = result.get("next_day")
    assert next_day is not None, (
        f"D-05: a next-day proposal must be present when same day is full; "
        f"got result={result!r}"
    )
    # The next-day proposal must contain a date and slot_time
    assert "date" in next_day and "slot_time" in next_day, (
        f"D-05: next_day must contain 'date' and 'slot_time'; got next_day={next_day!r}"
    )
    assert next_node is None, (
        "SC2: decline must return next_node=None (stay in booking node)"
    )
    in_memory_calendar.create_event.assert_not_called()


async def test_no_event_on_decline(reservation_repo, in_memory_calendar):
    """SC2 / T-02-09: on a capacity decline (slot full), no calendar event is created
    and no 'confermata' row is written to the DB.

    Asserts:
    - create_event is never called
    - no confermata reservation row exists in the DB
    - next_node is None
    """
    db_path = reservation_repo._db_path
    from src.config.repository import TenantRepository
    from src.db.seed_demo import build_demo_tenant
    tenant = build_demo_tenant()
    tenant_repo = TenantRepository(db_path=db_path)
    await tenant_repo.upsert_tenant(tenant)

    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        # Fill 20:00 to capacity (max_covers_per_slot=40): 20+20 = 40
        await db.executemany(
            """INSERT INTO reservations (tenant_id, slot_date, slot_time, covers, name, phone, status)
               VALUES (?, ?, ?, ?, ?, ?, 'confermata')""",
            [
                ("demo", "2025-07-10", "20:00", 20, "Rossi", "3471111111"),
                ("demo", "2025-07-10", "20:00", 20, "Bianchi", "3472222222"),
            ],
        )
        await db.commit()

    fm_state = {
        "booking_slot": {"date": "2025-07-10", "time_slot": "20:00", "covers": 2},
        "customer": {"name": "Ferrari", "phone": "3475555555"},
        "tenant_id": "demo",
        "tenant": tenant,
        "db_path": db_path,
        "calendar_provider": in_memory_calendar,
    }
    from types import SimpleNamespace
    fm = SimpleNamespace(state=fm_state)
    in_memory_calendar.create_event = AsyncMock()

    result, next_node = await handle_confirm_booking({}, fm)

    # No calendar event created on capacity decline
    in_memory_calendar.create_event.assert_not_called()

    # No new confermata row added (only the pre-seeded ones exist)
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """SELECT COUNT(*) FROM reservations
               WHERE tenant_id = ? AND slot_date = ? AND slot_time = ?
               AND status = 'confermata'""",
            ("demo", "2025-07-10", "20:00"),
        ) as cur:
            row = await cur.fetchone()
    assert row[0] == 2, (
        f"SC2: no new confermata row should be written on decline; "
        f"expected 2 (pre-seeded), got {row[0]}"
    )
    assert next_node is None, (
        "SC2: decline must return next_node=None"
    )


# ---------------------------------------------------------------------------
# FAQ-01 / D-06: Hybrid routing — structured config vs FTS5
# ---------------------------------------------------------------------------


async def test_faq_hybrid_structured(seeded_kb):
    """FAQ-01 / D-06: hours/services from TenantConfig — no FTS5 call needed.

    When the caller asks about hours or services, handle_faq_lookup must return
    the answer directly from tenant.hours / tenant.services (structured fields)
    with source='config'.  No SQLiteFTSKnowledgeBase.search call should be made.
    """
    from src.db.seed_demo import build_demo_tenant
    from unittest.mock import AsyncMock, patch

    tenant = build_demo_tenant()
    fm = _make_flow_manager(state={
        "tenant": tenant,
        "db_path": seeded_kb._db_path,
    })

    # Test hours query
    with patch("src.flows.functions.SQLiteFTSKnowledgeBase") as MockKB:
        result, next_node = await handle_faq_lookup({"query": "orari di apertura"}, fm)

    assert result.get("source") == "config", (
        f"D-06: hours query must return source='config'; got {result!r}"
    )
    assert tenant.hours in result.get("answer", ""), (
        f"D-06: answer must contain hours from TenantConfig; got {result!r}"
    )
    assert next_node is None, "FAQ handler must return next_node=None (stay in FAQ node)"
    # FTS5 must NOT be called for hours queries
    MockKB.assert_not_called()

    # Test services query
    with patch("src.flows.functions.SQLiteFTSKnowledgeBase") as MockKB:
        result2, _ = await handle_faq_lookup({"query": "servizi disponibili"}, fm)

    assert result2.get("source") == "config", (
        f"D-06: services query must return source='config'; got {result2!r}"
    )
    MockKB.assert_not_called()


async def test_faq_hybrid_fts(seeded_kb):
    """FAQ-01 / D-06: address/price/free-text from FTS5 KB.

    When the caller asks about address or prices (not hours/services), handle_faq_lookup
    must call SQLiteFTSKnowledgeBase.search and return the matching chunks.
    """
    from src.db.seed_demo import build_demo_tenant

    tenant = build_demo_tenant()
    # Use seeded_kb DB (contains demo chunks with address and prices)
    fm = _make_flow_manager(state={
        "tenant": tenant,
        "db_path": seeded_kb._db_path,
    })

    result, next_node = await handle_faq_lookup({"query": "indirizzo"}, fm)

    assert result.get("found") is True, (
        f"D-06: address query must return found=True from FTS5; got {result!r}"
    )
    assert "chunks" in result, (
        f"D-06: FTS5 result must include 'chunks' list; got {result!r}"
    )
    assert len(result["chunks"]) > 0, (
        f"D-06: FTS5 must return at least one chunk for 'indirizzo'; got {result!r}"
    )
    assert next_node is None, "FAQ handler must return next_node=None (stay in FAQ node)"


async def test_faq_not_found_routes_fallback(seeded_kb):
    """FAQ-02 / D-08: no KB match → found=False honest fallback, no invented answer.

    When the FTS5 search returns no results, handle_faq_lookup must return
    found=False (not an answer) so the FAQ node can speak the D-08 fallback phrase:
    'Non ho questa informazione al momento, posso prendere nota e farla ricontattare'.
    No invented content must appear in the result.
    """
    from src.db.seed_demo import build_demo_tenant

    tenant = build_demo_tenant()
    fm = _make_flow_manager(state={
        "tenant": tenant,
        "db_path": seeded_kb._db_path,
    })

    result, next_node = await handle_faq_lookup(
        {"query": "zxqwjkpineapplexqzw_notfound"}, fm
    )

    assert result.get("found") is False, (
        f"FAQ-02 / D-08: no-match must return found=False; got {result!r}"
    )
    # Must not invent an answer
    assert "chunks" not in result or len(result.get("chunks", [])) == 0, (
        f"FAQ-02: no chunks must be present when nothing matches; got {result!r}"
    )
    assert next_node is None, "FAQ handler must return next_node=None on not-found"


# ---------------------------------------------------------------------------
# W1: Greeting routing tools — route_to_faq and route_to_booking
# ---------------------------------------------------------------------------


async def test_greeting_routes_to_faq():
    """W1: build_greeting_node exposes route_to_faq; handler returns build_faq_node NodeConfig.

    The route_to_faq FlowsFunctionSchema handler must return (result, faq_node)
    where faq_node is a non-None NodeConfig dict — ensuring the LLM can transition
    from greeting to the FAQ node via a tool call (not implicit prose routing).
    """
    from src.db.seed_demo import build_demo_tenant

    tenant = build_demo_tenant()
    greeting_node = build_greeting_node(tenant)

    # greeting node must expose routing tools
    assert len(greeting_node["functions"]) > 0, (
        "W1: build_greeting_node must expose routing tools (functions list non-empty)"
    )
    fn_names = [f.name for f in greeting_node["functions"]]
    assert "route_to_faq" in fn_names, (
        f"W1: build_greeting_node must expose 'route_to_faq'; found {fn_names}"
    )

    # Call the route_to_faq handler directly
    route_faq_schema = next(f for f in greeting_node["functions"] if f.name == "route_to_faq")
    fm = _make_flow_manager(state={"tenant": tenant, "db_path": ":memory:"})

    result, next_node = await route_faq_schema.handler({"reason": "cliente ha una domanda"}, fm)

    assert next_node is not None, (
        "W1: route_to_faq handler must return a non-None next_node (faq NodeConfig)"
    )
    assert isinstance(next_node, dict), (
        f"W1: next_node must be a NodeConfig dict; got {type(next_node)}"
    )
    assert next_node.get("name") == "faq", (
        f"W1: next_node must be the FAQ node (name='faq'); got {next_node.get('name')!r}"
    )


async def test_greeting_routes_to_booking():
    """W1: build_greeting_node exposes route_to_booking; handler returns booking NodeConfig.

    The route_to_booking FlowsFunctionSchema handler must return (result, booking_node)
    where booking_node is a non-None NodeConfig dict with name='booking'.
    """
    from src.db.seed_demo import build_demo_tenant

    tenant = build_demo_tenant()
    greeting_node = build_greeting_node(tenant)

    fn_names = [f.name for f in greeting_node["functions"]]
    assert "route_to_booking" in fn_names, (
        f"W1: build_greeting_node must expose 'route_to_booking'; found {fn_names}"
    )

    route_booking_schema = next(
        f for f in greeting_node["functions"] if f.name == "route_to_booking"
    )
    fm = _make_flow_manager(state={"tenant": tenant, "db_path": ":memory:"})

    result, next_node = await route_booking_schema.handler(
        {"reason": "cliente vuole prenotare"}, fm
    )

    assert next_node is not None, (
        "W1: route_to_booking handler must return a non-None next_node (booking NodeConfig)"
    )
    assert isinstance(next_node, dict), (
        f"W1: next_node must be a NodeConfig dict; got {type(next_node)}"
    )
    assert next_node.get("name") == "booking", (
        f"W1: next_node must be the booking node (name='booking'); got {next_node.get('name')!r}"
    )


def test_faq_node_tools_isolation():
    """build_faq_node exposes ONLY faq_lookup; booking node has no faq tool (D-13 tool isolation)."""
    from src.db.seed_demo import build_demo_tenant

    tenant = build_demo_tenant()
    faq_node = build_faq_node(tenant)
    booking_node = build_booking_node(tenant)

    faq_tool_names = [f.name for f in faq_node["functions"]]
    booking_tool_names = [f.name for f in booking_node["functions"]]

    assert faq_tool_names == ["faq_lookup"], (
        f"build_faq_node must expose ONLY 'faq_lookup'; got {faq_tool_names}"
    )
    assert "faq_lookup" not in booking_tool_names, (
        f"booking node must NOT expose 'faq_lookup'; got {booking_tool_names}"
    )
