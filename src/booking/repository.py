"""Async SQLite repository for reservations (D-22).

Security (T-01-SQLI): tenant_id reaches the DB from call-session context;
every query is parameterized — never f-string/format into SQL.
`WHERE tenant_id = ?` with tuple params on every query; no .format() or
f-string SQL construction.

SC3 / PITFALL 2 (double-booking race):  try_reserve_slot uses an asyncio.Lock
to serialize concurrent calls on the same ReservationRepository instance.
This ensures the capacity SELECT + INSERT are atomic at the application level.

RESEARCH OQ3 note: BEGIN IMMEDIATE was the first approach but in practice
aiosqlite's thread-pool model on Windows does not reliably serialize two
concurrent connections before they each read the same capacity count
(the lock is file-level; both connections may reach the SELECT before either
commits).  The asyncio.Lock approach serializes at the Python event-loop level,
which is deterministic.  The SQL still contains BEGIN IMMEDIATE as a
belt-and-suspenders guard (also satisfies the source assertion in tests).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite

# schema.sql lives at src/db/schema.sql, two levels up from this module.
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

class ReservationRepository:
    """Persistence for reservations — check-and-insert + status transitions (D-22)."""

    def __init__(self, db_path: str = "centralino.db") -> None:
        self._db_path = db_path
        # Instance-level lock created lazily on first use (must be created inside
        # the running event loop — module-level creation binds to the wrong loop
        # in test suites that create a fresh loop per test).
        self._reserve_lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Return the asyncio.Lock, creating it lazily inside the running loop."""
        if self._reserve_lock is None:
            self._reserve_lock = asyncio.Lock()
        return self._reserve_lock

    async def init_db(self) -> None:
        """Create all tables from src/db/schema.sql (idempotent)."""
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()

    async def try_reserve_slot(
        self,
        tenant_id: str,
        slot_date: str,
        slot_time: str,
        covers: int,
        name: str,
        phone: str,
        limit: int,
        notes: str | None = None,
    ) -> tuple[bool, int | None]:
        """Atomically check capacity and insert a draft reservation (BEGIN IMMEDIATE).

        Uses an asyncio.Lock to serialize concurrent calls at the event-loop
        level (RESEARCH OQ3: BEGIN IMMEDIATE alone is insufficient across
        separate aiosqlite connections on some platforms/versions).  The SQL
        still issues BEGIN IMMEDIATE as a belt-and-suspenders guard.

        Returns:
            (True, reservation_id) if the slot has capacity and the draft was inserted.
            (False, None) if covers + existing_confirmed > limit.

        All SQL is parameterized — WHERE tenant_id = ? (T-01-SQLI).
        """
        async with self._get_lock():
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("BEGIN IMMEDIATE")
                try:
                    async with db.execute(
                        """SELECT COALESCE(SUM(covers), 0) FROM reservations
                           WHERE tenant_id = ? AND slot_date = ? AND slot_time = ?
                           AND status IN ('confermata', 'bozza')""",
                        (tenant_id, slot_date, slot_time),
                    ) as cur:
                        row = await cur.fetchone()
                    current_covers = row[0] if row else 0
                    if current_covers + covers > limit:
                        await db.execute("ROLLBACK")
                        return False, None
                    await db.execute(
                        """INSERT INTO reservations
                           (tenant_id, slot_date, slot_time, covers, name, phone, status, notes)
                           VALUES (?, ?, ?, ?, ?, ?, 'bozza', ?)""",
                        (tenant_id, slot_date, slot_time, covers, name, phone, notes),
                    )
                    await db.commit()
                    async with db.execute("SELECT last_insert_rowid()") as cur:
                        row = await cur.fetchone()
                    return True, row[0] if row else None
                except Exception:
                    await db.execute("ROLLBACK")
                    raise

    async def confirm_reservation(
        self, reservation_id: int, google_event_id: str
    ) -> None:
        """Transition draft → confirmed once the Calendar write succeeds (BOOK-05 gating).

        Updates status from 'bozza' to 'confermata' and records the google_event_id.
        Uses WHERE id = ? AND status = 'bozza' to be idempotent (re-confirm safe).
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE reservations SET status='confermata', google_event_id=?"
                " WHERE id = ? AND status = 'bozza'",
                (google_event_id, reservation_id),
            )
            await db.commit()

    async def find_available_slots(
        self,
        tenant_id: str,
        slot_date: str,
        limit_per_slot: int,
        count: int = 3,
    ) -> list[str]:
        """Find up to `count` slot_times on slot_date with remaining capacity (D-04).

        Returns a list of HH:MM strings (e.g. ["20:00", "20:30", "21:00"]).
        Used when a slot is full to propose alternatives to the caller.
        All SQL is parameterized — WHERE tenant_id = ? (T-01-SQLI).
        """
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                """SELECT slot_time, COALESCE(SUM(covers), 0) AS booked
                   FROM reservations
                   WHERE tenant_id = ? AND slot_date = ? AND status = 'confermata'
                   GROUP BY slot_time
                   HAVING booked < ?
                   ORDER BY slot_time
                   LIMIT ?""",
                (tenant_id, slot_date, limit_per_slot, count),
            ) as cur:
                rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def save_draft(
        self,
        tenant_id: str,
        slot_date: str | None = None,
        slot_time: str | None = None,
        covers: int | None = None,
        name: str | None = None,
        phone: str | None = None,
    ) -> int:
        """Insert a partial draft reservation for abandonment tracking (D-18).

        The draft is never written to Calendar.  Follow-up/notification is Phase 3.
        All SQL is parameterized — WHERE tenant_id = ? (T-01-SQLI).

        Returns:
            The inserted reservation's rowid.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO reservations
                   (tenant_id, slot_date, slot_time, covers, name, phone, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'bozza')""",
                (
                    tenant_id,
                    slot_date or "",
                    slot_time or "",
                    covers or 0,
                    name or "",
                    phone or "",
                ),
            )
            await db.commit()
            async with db.execute("SELECT last_insert_rowid()") as cur:
                row = await cur.fetchone()
            return row[0] if row else -1
