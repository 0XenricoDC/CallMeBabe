"""Tests for CalendarProvider implementations — InMemoryCalendarProvider (BOOK-04, BOOK-05).

Covers:
- InMemoryCalendarProvider.create_event returns a non-empty string event id (BOOK-04)
- check_availability returns False for overlapping events (BOOK-04 / availability logic)

Wave 0 state: RED — src/calendar/memory_provider.py does not exist yet.
These tests will fail with ImportError until Plan 02-02 creates the module.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from zoneinfo import ZoneInfo

from src.calendar.memory_provider import InMemoryCalendarProvider  # RED: does not exist yet

ROME_TZ = ZoneInfo("Europe/Rome")


def _dt(date_str: str, time_str: str) -> datetime:
    """Build a timezone-aware Europe/Rome datetime for test slots."""
    return datetime.fromisoformat(f"{date_str}T{time_str}:00").replace(tzinfo=ROME_TZ)


async def test_create_event_returns_id(in_memory_calendar: InMemoryCalendarProvider):
    """BOOK-04: InMemoryCalendarProvider.create_event returns a non-empty string event id."""
    start = _dt("2025-07-08", "20:00")
    end = _dt("2025-07-08", "20:30")

    event_id = await in_memory_calendar.create_event(
        tenant_id="demo",
        start=start,
        end=end,
        title="Prenotazione - Rossi (2p)",
        details="Tel: 3471234567 | via Centralino AI",
    )

    assert isinstance(event_id, str), (
        f"create_event must return a str event id; got {type(event_id)}"
    )
    assert event_id, (
        "create_event must return a non-empty string id. "
        "The event id gates BOOK-05 tool-result confirmation."
    )


async def test_check_availability_overlap(in_memory_calendar: InMemoryCalendarProvider):
    """BOOK-04: check_availability returns False when an overlapping event exists.

    Creates an event at 20:00-20:30, then checks availability for 20:15-20:45.
    The windows overlap → should report unavailable (False).
    """
    # Create an event occupying 20:00-20:30
    await in_memory_calendar.create_event(
        tenant_id="demo",
        start=_dt("2025-07-08", "20:00"),
        end=_dt("2025-07-08", "20:30"),
        title="Prenotazione - Rossi (2p)",
    )

    # Check a window that overlaps: 20:15-20:45
    is_available = await in_memory_calendar.check_availability(
        tenant_id="demo",
        start=_dt("2025-07-08", "20:15"),
        end=_dt("2025-07-08", "20:45"),
    )

    assert not is_available, (
        "check_availability must return False when an overlapping event exists. "
        "Got True — the InMemoryCalendarProvider is not detecting overlaps correctly."
    )


async def test_check_availability_no_overlap(in_memory_calendar: InMemoryCalendarProvider):
    """check_availability returns True when no overlapping event exists."""
    # Create an event at 20:00-20:30
    await in_memory_calendar.create_event(
        tenant_id="demo",
        start=_dt("2025-07-08", "20:00"),
        end=_dt("2025-07-08", "20:30"),
        title="Prenotazione - Rossi (2p)",
    )

    # Check a non-overlapping window: 21:00-21:30
    is_available = await in_memory_calendar.check_availability(
        tenant_id="demo",
        start=_dt("2025-07-08", "21:00"),
        end=_dt("2025-07-08", "21:30"),
    )

    assert is_available, (
        "check_availability must return True when there are no overlapping events."
    )


async def test_tenant_isolation_in_calendar(in_memory_calendar: InMemoryCalendarProvider):
    """InMemoryCalendarProvider isolates events by tenant_id (D-10)."""
    # Create an event for 'demo' at 20:00-20:30
    await in_memory_calendar.create_event(
        tenant_id="demo",
        start=_dt("2025-07-08", "20:00"),
        end=_dt("2025-07-08", "20:30"),
        title="Demo event",
    )

    # The same window for 'other_tenant' must report available (no cross-tenant contamination)
    is_available = await in_memory_calendar.check_availability(
        tenant_id="other_tenant",
        start=_dt("2025-07-08", "20:00"),
        end=_dt("2025-07-08", "20:30"),
    )

    assert is_available, (
        "check_availability must return True for other_tenant when only 'demo' has an event. "
        "Calendar events must be isolated by tenant_id (D-10)."
    )
