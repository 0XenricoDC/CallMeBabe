"""Async SQLite repository for tenant configuration (D-01).

`TenantRepository` is the persistence seam. It is deliberately DB-agnostic at the
call-site level (init_db / get_tenant) so the same interface can target Postgres
later via a connection-string swap, with no domain-logic change.

Security (T-01-SQLI): tenant_id reaches the DB from an untrusted CLI arg, so every
query is parameterized — `WHERE id = ?` with a tuple param. Never f-string/format
tenant_id into SQL.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from src.config.tenant_config import TenantConfig

# schema.sql lives at src/db/schema.sql, one level up from this module's package.
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


class TenantRepository:
    """Loads (and seeds) tenant configuration rows from SQLite."""

    def __init__(self, db_path: str = "centralino.db"):
        self._db_path = db_path

    async def init_db(self) -> None:
        """Create the tenants table from src/db/schema.sql (idempotent)."""
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()

    async def get_tenant(self, tenant_id: str) -> TenantConfig:
        """Load a tenant by id as a typed TenantConfig.

        Uses a strictly parameterized query. Raises ValueError (not a SQL error)
        when no row matches, so callers see a clean domain failure.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tenants WHERE id = ?", (tenant_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    raise ValueError(f"Tenant not found: {tenant_id}")
                return TenantConfig(**dict(row))

    async def upsert_tenant(self, tenant: TenantConfig) -> None:
        """Insert or replace a tenant row (used by the demo seed)."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO tenants (
                    id, business_name, greeting, voice_id, language, system_prompt,
                    model, hours, services, booking_rules, transfer_number,
                    kb_ref, notification_channel
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant.id,
                    tenant.business_name,
                    tenant.greeting,
                    tenant.voice_id,
                    tenant.language,
                    tenant.system_prompt,
                    tenant.model,
                    tenant.hours,
                    tenant.services,
                    tenant.booking_rules,
                    tenant.transfer_number,
                    tenant.kb_ref,
                    tenant.notification_channel,
                ),
            )
            await db.commit()

    async def table_columns(self, table: str) -> list[str]:
        """Return the column names of a table (used by schema tests)."""
        # `table` is a trusted internal identifier (test/maintenance use), not user
        # input; PRAGMA table_info does not accept a bound parameter for the table name.
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                rows = await cursor.fetchall()
                # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
                return [r[1] for r in rows]
