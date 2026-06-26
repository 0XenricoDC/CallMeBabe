"""Italian date/time parsing for the booking flow (D-16).

Uses `dateparser` 1.4.1 with Italian locale.
PITFALL 7 (RESEARCH.md): always pass RETURN_AS_TIMEZONE_AWARE=True + TIMEZONE=Europe/Rome
or returned datetime will be naive and bookings shift by 1-2h across DST.

Security: user text goes through dateparser, not eval/exec — no injection risk.

`dateparser` is imported at module level (not inside a handler) to amortize
cold-start latency — loading the locale data on first import can take ~0.5s
(RESEARCH §OQ4).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import dateparser  # imported at module level — amortizes cold start (RESEARCH §OQ4)
from zoneinfo import ZoneInfo

ROME_TZ = ZoneInfo("Europe/Rome")

PARSE_SETTINGS: dict = {
    "TIMEZONE": "Europe/Rome",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PREFER_DATES_FROM": "future",
    "PREFER_DAY_OF_MONTH": "first",
}

# Languages are passed as a separate argument to dateparser.parse (not in settings dict)
_LANGUAGES = ["it"]


def parse_italian_date(text: str) -> datetime | None:
    """Parse Italian natural language date/time to a timezone-aware datetime.

    Handles relative ("oggi", "domani", "dopodomani") and absolute
    ("8 luglio", "8 luglio 2025", "8 luglio alle 20") Italian dates.
    Returns None if the text cannot be parsed (caller should prompt the
    user to rephrase, e.g. 'Potrebbe dirmi la data in modo diverso?').

    All returned datetimes are timezone-aware in Europe/Rome (ROME_TZ).
    Pitfall 7: naive datetimes would shift bookings by 1-2h across DST.
    """
    result = dateparser.parse(text, languages=_LANGUAGES, settings=PARSE_SETTINGS)
    return result  # timezone-aware Europe/Rome, or None if unparseable


def slot_to_datetimes(
    slot_date: str, slot_time: str, duration_min: int
) -> tuple[datetime, datetime]:
    """Combine ISO date (YYYY-MM-DD) + HH:MM time into tz-aware start/end datetimes.

    Args:
        slot_date: ISO date string, e.g. "2025-07-08".
        slot_time: HH:MM time string, e.g. "20:00".
        duration_min: booking slot duration in minutes (from booking_rules).

    Returns:
        (start, end) as timezone-aware Europe/Rome datetimes.

    The returned datetimes are used for the Google Calendar event body
    (start/end with timeZone='Europe/Rome' so DST is handled correctly).
    """
    dt_str = f"{slot_date}T{slot_time}:00"
    start = datetime.fromisoformat(dt_str).replace(tzinfo=ROME_TZ)
    end = start + timedelta(minutes=duration_min)
    return start, end
