"""Convenience re-export of the demo seed (canonical implementation: src/db/seed_demo.py)."""

from src.db.seed_demo import (
    DEMO_BUSINESS_NAME,
    DEMO_GREETING,
    DEMO_SYSTEM_PROMPT,
    build_demo_tenant,
    seed_demo_tenant,
)

__all__ = [
    "DEMO_BUSINESS_NAME",
    "DEMO_GREETING",
    "DEMO_SYSTEM_PROMPT",
    "build_demo_tenant",
    "seed_demo_tenant",
]
