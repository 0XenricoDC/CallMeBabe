"""Tests for the tenant config layer (D-01, D-02, D-03).

Covers:
- TenantRepository loads the demo tenant from SQLite as a typed TenantConfig
- The tenants table exposes all 12 nullable-aware columns
- get_tenant uses a parameterized query (WHERE id = ?) and raises ValueError on miss
- TenantConfig rejects an empty voice_id (Pitfall 5)
"""

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.repository import TenantRepository
from src.config.seed_demo import seed_demo_tenant
from src.config.tenant_config import TenantConfig

# All 12 columns the schema must expose (D-02 — full nullable schema from day 1)
EXPECTED_COLUMNS = {
    "id",
    "business_name",
    "greeting",
    "voice_id",
    "language",
    "system_prompt",
    "model",
    "hours",
    "services",
    "booking_rules",
    "transfer_number",
    "kb_ref",
    "notification_channel",
}


@pytest.fixture
async def seeded_repo(tmp_path):
    """A TenantRepository backed by a temp-file DB, schema initialised + demo seeded."""
    db_path = str(tmp_path / "test_centralino.db")
    repo = TenantRepository(db_path=db_path)
    await repo.init_db()
    await seed_demo_tenant(repo)
    return repo


async def test_load_demo_tenant(seeded_repo):
    """get_tenant('demo') returns a typed TenantConfig with voice fields populated."""
    tenant = await seeded_repo.get_tenant("demo")

    assert isinstance(tenant, TenantConfig)
    assert tenant.id == "demo"
    assert tenant.business_name
    assert tenant.greeting
    assert tenant.voice_id
    assert tenant.system_prompt
    assert tenant.language == "it"


async def test_schema_columns(seeded_repo):
    """The tenants table exposes all 12 nullable-aware columns (D-02)."""
    columns = await seeded_repo.table_columns("tenants")
    assert set(columns) == EXPECTED_COLUMNS


async def test_get_tenant_uses_parameterized_query(seeded_repo):
    """A non-existent id raises ValueError (not a SQL error); SQL uses WHERE id = ?."""
    with pytest.raises(ValueError):
        await seeded_repo.get_tenant("does-not-exist")

    # Static guard: the repository source must use a parameterized query and must NOT
    # interpolate tenant_id into the SQL string via f-string or .format().
    source = inspect.getsource(TenantRepository)
    assert "WHERE id = ?" in source
    assert ".format(" not in source
    # No f-string SQL containing the tenant_id placeholder
    assert 'f"SELECT' not in source
    assert "f'SELECT" not in source


def test_voice_id_required():
    """Constructing TenantConfig with an empty/whitespace voice_id raises (Pitfall 5)."""
    base = dict(
        id="x",
        business_name="X",
        greeting="Ciao",
        system_prompt="Sei un assistente.",
    )
    with pytest.raises(ValidationError):
        TenantConfig(voice_id="", **base)
    with pytest.raises(ValidationError):
        TenantConfig(voice_id="   ", **base)

    # A valid voice_id constructs fine and language defaults to "it"
    ok = TenantConfig(voice_id="abc123", **base)
    assert ok.language == "it"
    assert ok.model  # default model present


def test_schema_sql_file_exists():
    """src/db/schema.sql exists and declares CREATE TABLE IF NOT EXISTS tenants (D-02)."""
    schema = Path(__file__).resolve().parents[1] / "src" / "db" / "schema.sql"
    assert schema.exists()
    text = schema.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS tenants" in text


def test_interface_seams_importable():
    """CalendarProvider and NotificationChannel exist as importable ABC stubs."""
    from abc import ABC

    from src.interfaces.calendar_provider import CalendarProvider
    from src.interfaces.notification_channel import NotificationChannel

    assert issubclass(CalendarProvider, ABC)
    assert issubclass(NotificationChannel, ABC)
    # They are abstract — cannot be instantiated directly
    with pytest.raises(TypeError):
        CalendarProvider()
    with pytest.raises(TypeError):
        NotificationChannel()
