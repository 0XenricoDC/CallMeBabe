"""Seed the Phase 1 `demo` tenant (D-04, D-09, D-10).

The demo tenant is a constrained-receptionist persona (D-09): it presents itself
as the demo business's switchboard, speaks natural Italian, and says that booking
and detailed info will be available soon (it never promises what does not exist).

Run standalone to seed the default DB:
    python -m src.db.seed_demo
"""

from __future__ import annotations

import asyncio
import os

from src.config.repository import TenantRepository
from src.config.tenant_config import TenantConfig

# D-09: constrained-receptionist system prompt (from 01-RESEARCH.md §Demo System Prompt).
DEMO_SYSTEM_PROMPT = """Sei l'assistente vocale automatico di {business_name}.
Rispondi SEMPRE in italiano naturale e professionale.
Ti presenti come centralino automatico dell'attivita.
Se ti chiedono di prenotare o di avere informazioni dettagliate su servizi/prezzi/orari,
rispondi educatamente che questa funzionalita sara disponibile a breve.
Non inventare informazioni. Sii cordiale e conciso — sei in una conversazione telefonica.
Se il chiamante non parla italiano, scusati e proponi di richiamare con un operatore."""

DEMO_BUSINESS_NAME = "Ristorante Da Mario"

# D-11: bot speaks first with a personalised Italian greeting.
DEMO_GREETING = (
    "Buongiorno, ha chiamato il Ristorante Da Mario, sono l'assistente vocale. "
    "Come posso aiutarla?"
)

# Pitfall 5: voice_id must be non-empty. Read from env, fall back to the RESEARCH
# default Italian-capable ElevenLabs voice. Never hardcoded as a secret.
_DEFAULT_VOICE_ID = "ErXwobaYiN019PkySvjV"


def build_demo_tenant() -> TenantConfig:
    """Construct the demo TenantConfig (no DB access)."""
    voice_id = os.getenv("DEMO_VOICE_ID", _DEFAULT_VOICE_ID) or _DEFAULT_VOICE_ID
    return TenantConfig(
        id="demo",
        business_name=DEMO_BUSINESS_NAME,
        greeting=DEMO_GREETING,
        voice_id=voice_id,
        language="it",
        system_prompt=DEMO_SYSTEM_PROMPT.format(business_name=DEMO_BUSINESS_NAME),
        model="claude-haiku-4-5",  # D-10
    )


async def seed_demo_tenant(repo: TenantRepository) -> TenantConfig:
    """Insert (or replace) the demo tenant into the given repository."""
    tenant = build_demo_tenant()
    await repo.upsert_tenant(tenant)
    return tenant


async def _main() -> None:
    repo = TenantRepository()
    await repo.init_db()
    tenant = await seed_demo_tenant(repo)
    print(f"Seeded demo tenant: {tenant.id} ({tenant.business_name})")


if __name__ == "__main__":
    asyncio.run(_main())
