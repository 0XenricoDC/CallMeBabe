"""Async SQLite repository for call logs (NOTIF-01, D-06, D-08).

Security (T-03-SQLI): every query is parameterized with ? — never f-string or
.format() into SQL. transcript_json is serialized via json.dumps (not interpolated).

Pattern: mirrors TenantRepository (src/config/repository.py) for init_db +
_SCHEMA_PATH, and ReservationRepository (src/booking/repository.py) for the
INSERT + last_insert_rowid pattern.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

# schema.sql lives at src/db/schema.sql, two levels up from this module's package.
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


class CallLogRepository:
    """Persistence for per-call logs — one row per completed call (D-08, NOTIF-01).

    Writes the full transcript, outcome taxonomy value, summary text, and optional
    reservation/event refs to the call_logs table. All SQL is parameterized
    (T-03-SQLI). The transcript_json column stores the raw JSON array as TEXT
    (Postgres-compatible as JSONB on migration, no schema change needed — D-08).
    """

    def __init__(self, db_path: str = "centralino.db") -> None:
        self._db_path = db_path

    async def init_db(self) -> None:
        """Create all tables from src/db/schema.sql (idempotent).

        Mirrors TenantRepository.init_db() — reads the shared schema.sql and
        runs executescript. Safe to call multiple times (IF NOT EXISTS guards).
        """
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()

    async def write(
        self,
        *,
        tenant_id: str,
        started_at: str,
        outcome: str,
        transcript_json: list,
        summary_text: str | None = None,
        reservation_id: int | None = None,
        google_event_id: str | None = None,
        transfer_number: str | None = None,
        channel_sent: str | None = None,
    ) -> int:
        """Insert one call_logs row and return its rowid.

        Args:
            tenant_id:       Tenant identifier (must exist in tenants table).
            started_at:      ISO 8601 call start timestamp (Europe/Rome tz).
            outcome:         One of prenotato/faq/trasferito/abbandonato/fallito (D-06).
            transcript_json: List of {role, content} dicts from context.messages.
            summary_text:    2-3 sentence Italian summary (D-05); None if gen failed.
            reservation_id:  FK to reservations.id for 'prenotato' outcome.
            google_event_id: Google Calendar event id (shortcut for notifications).
            transfer_number: Resolved operator number for 'trasferito' outcome.
            channel_sent:    Notification channel name used (e.g. 'log', 'telegram').

        Returns:
            The rowid of the newly inserted row (last_insert_rowid()).

        Raises:
            aiosqlite.IntegrityError: if outcome is not in the five-value taxonomy
                (D-06 CHECK constraint) or tenant_id does not exist (FK constraint).

        Security (T-03-SQLI): all values bound via ? — transcript_json is serialized
        with json.dumps(ensure_ascii=False), never interpolated as a string.
        """
        serialized_transcript = json.dumps(transcript_json, ensure_ascii=False)

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO call_logs
                  (tenant_id, started_at, outcome, transcript_json,
                   summary_text, reservation_id, google_event_id,
                   transfer_number, channel_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    started_at,
                    outcome,
                    serialized_transcript,
                    summary_text,
                    reservation_id,
                    google_event_id,
                    transfer_number,
                    channel_sent,
                ),
            )
            await db.commit()
            return cursor.lastrowid
