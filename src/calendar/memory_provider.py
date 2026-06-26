"""InMemoryCalendarProvider — in-memory CalendarProvider for tests (D-12).

No real network calls; events are stored in a list and scoped by tenant_id.
Use this in unit tests and local development before a real Google credential
is available.
"""

from __future__ import annotations

from datetime import datetime

from src.interfaces.calendar_provider import CalendarProvider


class InMemoryCalendarProvider(CalendarProvider):
    """In-memory CalendarProvider for tests (D-12).

    No real network calls.  Events are isolated by tenant_id (D-10).
    Event ids follow the pattern ``mem-<n>`` (e.g. ``mem-1``, ``mem-2``).
    """

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._next_id: int = 1

    async def check_availability(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> bool:
        """Return False if any existing event for this tenant overlaps [start, end).

        Overlap condition: existing.start < end AND existing.end > start.
        Returns True when no event overlaps (slot is free).
        """
        for ev in self._events:
            if ev["tenant_id"] == tenant_id and ev["start"] < end and ev["end"] > start:
                return False
        return True

    async def create_event(
        self,
        tenant_id: str,
        start: datetime,
        end: datetime,
        title: str,
        details: str | None = None,
    ) -> str:
        """Create an in-memory event and return a unique non-empty string id.

        The returned id (e.g. ``mem-1``) satisfies the BOOK-05 gating requirement:
        it is a real, non-empty string so the booking handler can transition to
        the end node.
        """
        event_id = f"mem-{self._next_id}"
        self._next_id += 1
        self._events.append(
            {
                "tenant_id": tenant_id,
                "start": start,
                "end": end,
                "title": title,
                "details": details,
                "id": event_id,
            }
        )
        return event_id
