"""Shared pytest fixtures for Phase 1.

Provides:
- `tenant`: a demo TenantConfig (no DB needed) for fast unit tests
- `repo` / `seeded_repo`: a temp-file TenantRepository (schema + demo seed)
- `mock_stt` / `mock_llm` / `mock_tts`: service placeholders so pipeline tests in
  Plan 02 never hit live APIs
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
