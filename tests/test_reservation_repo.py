"""Tests for ReservationRepository — capacity check, concurrent booking, persistence (BOOK-02, BOOK-06, SC3).

Covers:
- Capacity check rejects when new covers + existing covers exceeds slot limit (BOOK-02)
- confirm_reservation sets status='confermata' and records google_event_id (BOOK-06)
- Two concurrent bookings on the same slot where one would exceed the limit:
  exactly one succeeds (SC3/T-2 race — BEGIN IMMEDIATE prevents double-booking)
- Source-assertion: parameterized SQL only (T-02-01 SQL injection prevention)

Wave 0 state: RED — src/booking/repository.py does not exist yet.
These tests will fail with ImportError until Plan 02-02 creates the module.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from src.booking.repository import ReservationRepository  # RED: does not exist yet


async def test_capacity_check(reservation_repo: ReservationRepository):
    """BOOK-02: capacity check rejects a reservation when covers would exceed the slot limit.

    Inserts a confirmed reservation for 38 covers, then attempts to insert 4 more.
    The slot limit is 40 (from demo tenant booking_rules). Sum 38 + 4 = 42 > 40 → reject.
    """
    # Seed a confirmed reservation taking 38 covers in this slot
    async with __import__("aiosqlite").connect(reservation_repo._db_path) as db:
        await db.execute(
            """INSERT INTO reservations
               (tenant_id, slot_date, slot_time, covers, name, phone, status, google_event_id)
               VALUES (?, ?, ?, ?, ?, ?, 'confermata', 'evt-existing')""",
            ("demo", "2025-07-08", "20:00", 38, "Verdi", "0281234567"),
        )
        await db.commit()

    # Attempt to reserve 4 more covers (38 + 4 = 42 > 40 limit)
    success, res_id = await reservation_repo.try_reserve_slot(
        tenant_id="demo",
        slot_date="2025-07-08",
        slot_time="20:00",
        covers=4,
        name="Bianchi",
        phone="0281234568",
        limit=40,
    )

    assert not success, (
        "try_reserve_slot must return False when covers + existing > limit. "
        "The slot has 38 confirmed covers; adding 4 would exceed the limit of 40."
    )
    assert res_id is None, "reservation_id must be None when the reservation is rejected"


async def test_insert_confirmed(reservation_repo: ReservationRepository):
    """BOOK-06: confirm_reservation transitions status to 'confermata' and records google_event_id."""
    import aiosqlite

    # First, insert a draft reservation via try_reserve_slot
    success, res_id = await reservation_repo.try_reserve_slot(
        tenant_id="demo",
        slot_date="2025-07-09",
        slot_time="20:00",
        covers=2,
        name="Rossi",
        phone="3471234567",
        limit=40,
    )

    assert success, "try_reserve_slot must succeed for an empty slot within capacity"
    assert res_id is not None, "reservation_id must be set on successful insert"

    # Confirm the reservation with a real google_event_id (simulates Calendar write)
    await reservation_repo.confirm_reservation(res_id, google_event_id="gcal-evt-abc123")

    # Verify the DB row was updated correctly
    async with aiosqlite.connect(reservation_repo._db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status, google_event_id FROM reservations WHERE id = ?", (res_id,)
        ) as cur:
            row = await cur.fetchone()

    assert row is not None, f"No reservation row found for id={res_id}"
    assert row["status"] == "confermata", (
        f"status must be 'confermata' after confirm_reservation; got {row['status']!r}"
    )
    assert row["google_event_id"] == "gcal-evt-abc123", (
        f"google_event_id must be set after confirm_reservation; got {row['google_event_id']!r}"
    )


async def test_concurrent_booking(reservation_repo: ReservationRepository):
    """SC3/T-2: two concurrent bookings on the SAME slot where one exceeds the limit.

    Uses asyncio.gather to run two try_reserve_slot calls simultaneously.
    The slot limit is 30; each booking requests 20 covers (20 + 20 = 40 > 30).
    Exactly one must succeed (BEGIN IMMEDIATE ensures atomic check-and-insert).
    """
    slot_kwargs = dict(
        tenant_id="demo",
        slot_date="2025-07-10",
        slot_time="20:00",
        covers=20,
        name="Concurrent",
        phone="0000000000",
        limit=30,
    )

    result1, result2 = await asyncio.gather(
        reservation_repo.try_reserve_slot(**slot_kwargs),
        reservation_repo.try_reserve_slot(**slot_kwargs),
    )

    successes = [r[0] for r in [result1, result2] if r[0]]
    assert len(successes) == 1, (
        f"Exactly one concurrent booking must succeed (BEGIN IMMEDIATE prevents double-booking). "
        f"Results: {result1}, {result2}. "
        f"Both succeeded: concurrent double-booking race is broken."
    )


def test_reservation_repo_parameterized():
    """T-02-01: ReservationRepository uses only parameterized SQL (no injection vectors).

    Source-assertion: inspect the source to confirm:
    - Queries use WHERE tenant_id = ? (not string interpolation)
    - No .format( into SQL strings
    - No f"SELECT or f'SELECT (no f-string SQL)
    """
    source = inspect.getsource(ReservationRepository)

    assert "WHERE tenant_id = ?" in source, (
        "ReservationRepository must use parameterized WHERE tenant_id = ? "
        "(not string interpolation). Required for T-02-01 SQL injection prevention."
    )
    assert ".format(" not in source, (
        "ReservationRepository must not use .format( to build SQL strings. "
        "Use parameterized ? placeholders only."
    )
    assert 'f"SELECT' not in source, (
        "ReservationRepository must not use f-strings to build SELECT queries. "
        "Use parameterized ? placeholders only."
    )
    assert "f'SELECT" not in source, (
        "ReservationRepository must not use f-strings to build SELECT queries. "
        "Use parameterized ? placeholders only."
    )
