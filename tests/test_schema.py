"""Schema migration tests for Phase 2 (Plan 02-01).

Covers:
- tenants table has the new calendar_id column (D-11)
- reservations, kb_documents, kb_chunks tables exist after schema init
- All new tables use IF NOT EXISTS (idempotent on re-run — Pitfall 5)
"""

from __future__ import annotations

import pytest

from src.config.repository import TenantRepository


@pytest.fixture
async def repo(tmp_path) -> TenantRepository:
    """An initialised TenantRepository backed by a temp-file DB."""
    db_path = str(tmp_path / "test_schema.db")
    r = TenantRepository(db_path=db_path)
    await r.init_db()
    return r


async def test_calendar_id_column(repo: TenantRepository):
    """D-11: calendar_id column exists on the tenants table after schema migration."""
    columns = await repo.table_columns("tenants")
    assert "calendar_id" in columns, (
        f"calendar_id column missing from tenants table. "
        f"Found columns: {columns}. "
        "Ensure schema.sql CREATE TABLE includes calendar_id TEXT."
    )


async def test_phase2_tables_exist(repo: TenantRepository):
    """Phase 2 tables (reservations, kb_documents, kb_chunks) are created by schema init."""
    import aiosqlite

    db_path = repo._db_path
    async with aiosqlite.connect(db_path) as db:
        # Query sqlite_master for all table and virtual table entries
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'shadow') "
            "UNION SELECT name FROM sqlite_master WHERE tbl_name IN "
            "('kb_chunks') AND type = 'table'"
        ) as cur:
            rows = await cur.fetchall()
        all_names = {r[0] for r in rows}

        # Also check for the FTS5 virtual table (stored in sqlite_master with type='table')
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE name IN "
            "('reservations', 'kb_documents', 'kb_chunks')"
        ) as cur:
            rows2 = await cur.fetchall()
        found_tables = {r[0] for r in rows2}

    assert "reservations" in found_tables, (
        f"reservations table missing. Found: {found_tables}. "
        "Ensure schema.sql has CREATE TABLE IF NOT EXISTS reservations."
    )
    assert "kb_documents" in found_tables, (
        f"kb_documents table missing. Found: {found_tables}. "
        "Ensure schema.sql has CREATE TABLE IF NOT EXISTS kb_documents."
    )
    assert "kb_chunks" in found_tables, (
        f"kb_chunks virtual table missing. Found: {found_tables}. "
        "Ensure schema.sql has CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks USING fts5(...)."
    )


async def test_schema_idempotent(tmp_path):
    """Schema init can run twice without error (IF NOT EXISTS idempotency — Pitfall 5)."""
    db_path = str(tmp_path / "test_idempotent.db")
    repo = TenantRepository(db_path=db_path)

    # First init
    await repo.init_db()
    # Second init must not raise (no bare ALTER TABLE, only IF NOT EXISTS)
    await repo.init_db()

    columns = await repo.table_columns("tenants")
    assert "calendar_id" in columns


async def test_reservations_schema(repo: TenantRepository):
    """reservations table has all required columns (D-22)."""
    columns = await repo.table_columns("reservations")
    required = {
        "id", "tenant_id", "slot_date", "slot_time", "covers",
        "name", "phone", "status", "google_event_id", "notes", "created_at",
    }
    missing = required - set(columns)
    assert not missing, (
        f"reservations table is missing columns: {missing}. Found: {columns}"
    )


async def test_tenant_config_accepts_calendar_id(repo: TenantRepository):
    """TenantConfig(**dict(row)) succeeds for rows that include calendar_id (1:1 mapping)."""
    from src.config.tenant_config import TenantConfig
    from src.db.seed_demo import seed_demo_tenant

    await seed_demo_tenant(repo)
    tenant = await repo.get_tenant("demo")

    assert isinstance(tenant.calendar_id, (str, type(None))), (
        "calendar_id must be Optional[str] — TenantConfig(**dict(row)) must accept it"
    )
    # Phase 2 fields are now non-null in the seeded demo tenant
    assert tenant.hours == "12:00-15:00, 19:00-23:00"
    assert tenant.services == "Cucina italiana, pizzeria, vini naturali"
    assert tenant.booking_rules == '{"slot_duration_min": 30, "max_covers_per_slot": 40}'
    assert tenant.kb_ref == "data/tenants/demo_trattoria/kb"
