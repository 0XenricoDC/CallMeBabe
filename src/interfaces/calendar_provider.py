"""CalendarProvider interface seam (Phase 2 — booking).

Defined now so the booking phase adds a concrete implementation (e.g. Google
Calendar) *behind* this interface rather than restructuring code.

D-10: Tenant isolation — every method takes `tenant_id` as the first parameter
so the provider resolves the per-tenant calendar internally; callers never supply
a raw calendar_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class CalendarProvider(ABC):
    """Calendar backend for reservations/appointments (Phase 2 seam).

    All methods are tenant-scoped: the provider maps tenant_id → calendar_id
    internally (e.g. from TenantConfig.calendar_id).  Callers never supply
    a raw calendar identifier — only tenant_id from the session context (T-03).
    """

    @abstractmethod
    async def check_availability(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> bool:
        """Return True if the [start, end) window is free for this tenant.

        NOTE: this check is SECONDARY to the DB transactional check (BEGIN IMMEDIATE).
        It is for informational / display purposes only — never use as the
        authoritative capacity gate.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_event(
        self,
        tenant_id: str,
        start: datetime,
        end: datetime,
        title: str,
        details: str | None = None,
    ) -> str:
        """Create a calendar event for the given tenant and return its provider event id.

        The returned event id is a real, non-empty string that the booking handler
        uses to gate the spoken confirmation (BOOK-05).  An implementation MUST
        return a non-empty string on success and raise on any write failure so the
        handler can correctly stay in the booking node.
        """
        raise NotImplementedError
