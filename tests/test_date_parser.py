"""Tests for Italian date/time parsing — parse_italian_date (D-16).

Covers:
- "oggi", "domani", and "8 luglio" parse to timezone-aware Europe/Rome datetimes (D-16)
- Gibberish / unparseable input returns None (defensive handling)

Wave 0 state: RED — src/booking/date_parser.py does not exist yet.
These tests will fail with ImportError until Plan 02-02 creates the module.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from zoneinfo import ZoneInfo

from src.booking.date_parser import normalize_future_date, parse_italian_date

ROME_TZ = ZoneInfo("Europe/Rome")


def test_italian_dates():
    """D-16: parse_italian_date handles 'oggi', 'domani', and absolute dates in Europe/Rome.

    All returned datetimes must be timezone-aware with tzinfo for Europe/Rome.
    Pitfall 7: naive datetimes shift bookings by 1-2h across DST boundaries.
    """
    oggi_dt = parse_italian_date("oggi")
    assert oggi_dt is not None, (
        "parse_italian_date('oggi') must return a datetime; got None. "
        "Ensure dateparser is configured with LANGUAGES=['it'] and TIMEZONE='Europe/Rome'."
    )
    assert isinstance(oggi_dt, datetime), (
        f"parse_italian_date('oggi') must return a datetime object; got {type(oggi_dt)}"
    )
    assert oggi_dt.tzinfo is not None, (
        "parse_italian_date('oggi') must return a timezone-aware datetime. "
        "Got a naive datetime — ensure RETURN_AS_TIMEZONE_AWARE=True in PARSE_SETTINGS. "
        "Naive datetimes cause DST-related booking shifts (Pitfall 7)."
    )

    domani_dt = parse_italian_date("domani")
    assert domani_dt is not None, (
        "parse_italian_date('domani') must return a datetime; got None."
    )
    assert domani_dt.tzinfo is not None, (
        "parse_italian_date('domani') must return a timezone-aware datetime (Pitfall 7)."
    )

    luglio_dt = parse_italian_date("8 luglio")
    assert luglio_dt is not None, (
        "parse_italian_date('8 luglio') must return a datetime; got None. "
        "Absolute Italian month names must be recognized by the Italian locale."
    )
    assert luglio_dt.tzinfo is not None, (
        "parse_italian_date('8 luglio') must return a timezone-aware datetime (Pitfall 7)."
    )
    assert luglio_dt.month == 7, (
        f"parse_italian_date('8 luglio') must resolve to month 7 (luglio = July); got month {luglio_dt.month}"
    )
    assert luglio_dt.day == 8, (
        f"parse_italian_date('8 luglio') must resolve to day 8; got day {luglio_dt.day}"
    )


def test_unparseable_returns_none():
    """D-16: parse_italian_date returns None for gibberish / unparseable input.

    The caller is responsible for prompting the user to rephrase.
    This test ensures None is returned rather than raising an exception.
    """
    result = parse_italian_date("zxqwjkpineapplexqzw8734!@#")
    assert result is None, (
        f"parse_italian_date must return None for unparseable input; got {result!r}. "
        "The caller uses None as a signal to re-prompt the user."
    )


def test_normalize_future_date_bumps_past_year():
    """A date in the past is rolled forward to its nearest future occurrence.

    The LLM emits ISO dates with no notion of "now" and routinely picks a past
    year; normalize_future_date corrects that server-side (PREFER_DATES_FROM=future).
    """
    today = date(2026, 6, 26)
    # Past year, day/month still ahead in the year → same month/day, year bumped to 2026.
    assert normalize_future_date("2025-07-08", today=today) == "2026-07-08"
    # Past year AND day/month already gone this year → bumped to next year.
    assert normalize_future_date("2024-01-05", today=today) == "2027-01-05"


def test_normalize_future_date_leaves_future_untouched():
    """A date already today-or-later is returned unchanged."""
    today = date(2026, 6, 26)
    assert normalize_future_date("2026-06-26", today=today) == "2026-06-26"  # today
    assert normalize_future_date("2026-12-31", today=today) == "2026-12-31"  # future


def test_normalize_future_date_handles_garbage():
    """Unparseable input is returned unchanged (never raises)."""
    assert normalize_future_date("not-a-date") == "not-a-date"
    assert normalize_future_date("") == ""


def test_normalize_future_date_leap_day():
    """29 Feb in a past leap year snaps cleanly into a future year (no crash)."""
    today = date(2026, 6, 26)
    # 2024-02-29 is past; nearest future leap day handling must not raise.
    result = normalize_future_date("2024-02-29", today=today)
    assert date.fromisoformat(result) >= today


def test_absolute_date_with_time():
    """D-16: parse_italian_date handles date + time strings (e.g. '8 luglio alle 20').

    The result must be timezone-aware and preserve the parsed time component.
    """
    result = parse_italian_date("8 luglio alle 20")
    if result is not None:
        assert result.tzinfo is not None, (
            "parse_italian_date must return timezone-aware datetime even for date+time strings."
        )
        assert result.month == 7
        assert result.day == 8
        assert result.hour == 20
