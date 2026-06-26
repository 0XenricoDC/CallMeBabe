"""Shared pytest fixtures for Phase 1 and Phase 2.

Provides:
- `tenant`: a demo TenantConfig (no DB needed) for fast unit tests
- `repo` / `seeded_repo`: a temp-file TenantRepository (schema + demo seed)
- `mock_stt` / `mock_llm` / `mock_tts`: service placeholders so pipeline tests in
  Plan 02 never hit live APIs

Phase 2 additions (Plan 02-01):
- `reservation_repo`: a temp-file ReservationRepository with schema initialized
- `kb_fts`: a temp-file SQLiteFTSKnowledgeBase with schema initialized
- `in_memory_calendar`: an InMemoryCalendarProvider instance (no network)
- `seeded_kb`: kb_fts with demo KB chunks ingested for isolation/search tests
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.config.repository import TenantRepository
from src.config.tenant_config import TenantConfig
from src.db.seed_demo import build_demo_tenant, seed_demo_tenant


@pytest.fixture
def tenant() -> TenantConfig:
    """A ready-made demo TenantConfig (no DB access)."""
    return build_demo_tenant()


@pytest.fixture
async def repo(tmp_path) -> TenantRepository:
    """An initialised (empty) TenantRepository backed by a temp-file DB."""
    db_path = str(tmp_path / "centralino_test.db")
    r = TenantRepository(db_path=db_path)
    await r.init_db()
    return r


@pytest.fixture
async def seeded_repo(repo) -> TenantRepository:
    """A TenantRepository with the demo tenant seeded."""
    await seed_demo_tenant(repo)
    return repo


@pytest.fixture
def mock_stt() -> MagicMock:
    """Placeholder STT service (Plan 02 wires the real DeepgramSTTService)."""
    m = MagicMock(name="MockSTTService")
    m.model = "nova-2"
    m.language = "it"
    return m


@pytest.fixture
def mock_llm(tenant) -> MagicMock:
    """Placeholder LLM service (Plan 02 wires the real AnthropicLLMService)."""
    m = MagicMock(name="MockLLMService")
    m.model = tenant.model
    m.system_instruction = tenant.system_prompt
    return m


@pytest.fixture
def mock_tts(tenant) -> MagicMock:
    """Placeholder TTS service (Plan 02 wires the real ElevenLabsTTSService)."""
    m = MagicMock(name="MockTTSService")
    m.voice = tenant.voice_id
    m.model = "eleven_turbo_v2_5"
    m.language = "it"
    return m


# ---------------------------------------------------------------------------
# Phase 2 fixtures (Plan 02-01 — Wave 0)
# ---------------------------------------------------------------------------


@pytest.fixture
async def reservation_repo(tmp_path):
    """An initialised ReservationRepository backed by a temp-file DB.

    The schema is initialized via TenantRepository.init_db() (shared schema.sql),
    which creates the reservations table alongside tenants/kb_documents/kb_chunks.
    """
    from src.booking.repository import ReservationRepository

    db_path = str(tmp_path / "centralino_test.db")
    # Initialize the full schema (including reservations table) via TenantRepository
    tenant_repo = TenantRepository(db_path=db_path)
    await tenant_repo.init_db()
    return ReservationRepository(db_path=db_path)


@pytest.fixture
async def kb_fts(tmp_path):
    """A SQLiteFTSKnowledgeBase backed by a temp-file DB with schema initialized."""
    from src.kb.fts import SQLiteFTSKnowledgeBase

    db_path = str(tmp_path / "centralino_test.db")
    # Initialize the full schema (including kb_chunks FTS5 table) via TenantRepository
    tenant_repo = TenantRepository(db_path=db_path)
    await tenant_repo.init_db()
    return SQLiteFTSKnowledgeBase(db_path=db_path)


@pytest.fixture
def in_memory_calendar():
    """An InMemoryCalendarProvider instance (no network calls, for unit tests)."""
    from src.calendar.memory_provider import InMemoryCalendarProvider

    return InMemoryCalendarProvider()


@pytest.fixture
async def seeded_kb(kb_fts, tmp_path):
    """A SQLiteFTSKnowledgeBase with demo KB chunks ingested for two tenants.

    Provides data isolation tests (FAQ-03/T-3): tenant 'demo' and 'other_tenant'
    have distinct, non-overlapping chunks so cross-tenant leakage is detectable.
    """
    import aiosqlite

    db_path = kb_fts._db_path
    demo_chunks = [
        ("demo", "menu.txt", "0", "Pasta al pomodoro: 12 euro. Margherita: 10 euro."),
        ("demo", "menu.txt", "1", "Orari: lunedì chiuso, martedì-domenica 12-15 e 19-23."),
        ("demo", "info.txt", "0", "Indirizzo: Via Roma 1, Milano. Tel: 02 1234567."),
    ]
    other_chunks = [
        ("other_tenant", "info.txt", "0", "Questo è contenuto dell'altro tenant che non deve apparire."),
        ("other_tenant", "menu.txt", "0", "Pizza margherita speciale solo per l'altro tenant."),
    ]
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT INTO kb_chunks(tenant_id, doc_id, chunk_id, content) VALUES (?,?,?,?)",
            demo_chunks + other_chunks,
        )
        await db.commit()
    return kb_fts
