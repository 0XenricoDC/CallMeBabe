"""GoogleCalendarProvider — Google Calendar backend using a service account (D-09, D-12).

Security (T-02-KEY): the service-account credential path is read from the
GOOGLE_SERVICE_ACCOUNT_JSON environment variable; it is never logged.

D-10 isolation: tenant_id → calendar_id is resolved from a caller-supplied
resolver (dict or callable) so the raw calendar_id never reaches untrusted
caller code (T-03).  In production this resolver is populated from
TenantConfig.calendar_id loaded from the DB.

PITFALL 4: the Google API client is synchronous (httplib2/requests).  Every
blocking call is wrapped in loop.run_in_executor so the asyncio event loop
(and therefore VAD, barge-in, TTS) keeps running during the network write.

PITFALL 1 / freebusy inversion: the freebusy response contains a 'busy' list
of occupied time ranges.  An *empty* busy list means FREE; a *non-empty* list
means BUSY.  check_availability returns True when busy_periods == [].
NOTE: this check is SECONDARY to the DB transactional check — never use
check_availability as the authoritative capacity gate (BEGIN IMMEDIATE is).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from functools import partial
from typing import Callable, Union

from googleapiclient.discovery import build
from google.oauth2 import service_account

from src.interfaces.calendar_provider import CalendarProvider


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar backend using a single global service account (D-09/D-12).

    Resolves tenant_id → calendar_id via a caller-supplied resolver so no raw
    calendar identifier reaches untrusted input (T-03, D-10).

    Args:
        calendar_id_resolver: either a ``dict[tenant_id, calendar_id]`` or a
            callable ``(tenant_id: str) -> str`` that returns the calendar_id
            for a given tenant.  In production, populate this from
            TenantConfig.calendar_id rows loaded via TenantRepository.
    """

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(
        self,
        calendar_id_resolver: Union[dict, Callable[[str], str], None] = None,
    ) -> None:
        # Security (T-02-KEY): credential path via env only; never logged.
        cred_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not cred_path:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON env var not set — "
                "provide the path to the service-account JSON file"
            )
        credentials = service_account.Credentials.from_service_account_file(
            cred_path, scopes=self.SCOPES
        )
        self._service = build("calendar", "v3", credentials=credentials)
        self._resolver = calendar_id_resolver

    def _resolve_calendar_id(self, tenant_id: str) -> str:
        """Map tenant_id → calendar_id using the configured resolver."""
        if self._resolver is None:
            raise ValueError(
                f"No calendar_id resolver configured for tenant '{tenant_id}'"
            )
        if callable(self._resolver):
            return self._resolver(tenant_id)
        # dict resolver
        cal_id = self._resolver.get(tenant_id)
        if not cal_id:
            raise ValueError(f"No calendar_id found for tenant '{tenant_id}'")
        return cal_id

    async def check_availability(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> bool:
        """Return True if the [start, end) window is free for this tenant.

        Uses Google Calendar freebusy.query (SECONDARY to the DB check — Pitfall 1).
        busy[] being EMPTY means FREE; busy[] being NON-EMPTY means BUSY.
        This is NOT the authoritative capacity gate — BEGIN IMMEDIATE in the DB is.
        """
        calendar_id = self._resolve_calendar_id(tenant_id)
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": "Europe/Rome",
            "items": [{"id": calendar_id}],
        }
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            partial(self._service.freebusy().query(body=body).execute),
        )
        calendar_info = result["calendars"].get(calendar_id, {})
        busy_periods = calendar_info.get("busy", [])
        # CORRECT inversion (Pitfall 1): empty busy = FREE slot
        return len(busy_periods) == 0

    async def create_event(
        self,
        tenant_id: str,
        start: datetime,
        end: datetime,
        title: str,
        details: str | None = None,
    ) -> str:
        """Create a Google Calendar event and return its real event id.

        The Google API client is synchronous; the blocking call is wrapped in
        run_in_executor so the asyncio event loop (VAD, barge-in, TTS) keeps
        running during the network write (Pitfall 4).

        The event description includes 'via Centralino AI' marker (D-21).
        start/end carry timeZone='Europe/Rome' so DST is handled correctly.

        Returns:
            A non-empty string Google event id — used to gate BOOK-05 confirmation.

        Raises:
            Any Google API exception if the write fails (caller catches and stays
            in the booking node, no false confirmation is spoken).
        """
        calendar_id = self._resolve_calendar_id(tenant_id)
        body = {
            "summary": title,
            "description": details or "via Centralino AI",
            "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Rome"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Europe/Rome"},
        }
        loop = asyncio.get_running_loop()
        # CRITICAL: wrap blocking call in run_in_executor (Pitfall 4)
        result = await loop.run_in_executor(
            None,
            partial(
                self._service.events()
                .insert(calendarId=calendar_id, body=body)
                .execute
            ),
        )
        # result["id"] is the real Google event id — drives BOOK-05 gating
        return result["id"]
