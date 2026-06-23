"""CalendarProvider interface seam (Phase 2 — booking).

Defined now so the booking phase adds a concrete implementation (e.g. Google
Calendar) *behind* this interface rather than restructuring code. Not functional
in Phase 1 — abstract stub only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class CalendarProvider(ABC):
    """Calendar backend for reservations/appointments (Phase 2 seam)."""

    @abstractmethod
    async def check_availability(self, start: datetime, end: datetime) -> bool:
        """Return True if the [start, end) window is free."""
        raise NotImplementedError

    @abstractmethod
    async def create_event(
        self,
        start: datetime,
        end: datetime,
        title: str,
        details: str | None = None,
    ) -> str:
        """Create a calendar event and return its provider event id."""
        raise NotImplementedError
