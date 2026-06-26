"""Typed tenant configuration model (D-03).

`TenantConfig` is the seam that Phases 2-5 extend. Phase 1 populates only the
voice-relevant fields; the booking/FAQ/notification fields are nullable and
filled in later phases without a schema change (D-02).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class TenantConfig(BaseModel):
    """A single tenant's runtime configuration, loaded at call start.

    Fields mirror the `tenants` SQLite table (src/db/schema.sql) 1:1 so a row can
    be unpacked directly into this model: ``TenantConfig(**dict(row))``.
    """

    id: str
    business_name: str
    greeting: str
    voice_id: str
    language: str = "it"
    system_prompt: str
    # D-10: default Claude Haiku 4.5 for low TTFT in real-time voice; per-tenant overridable.
    model: str = "claude-haiku-4-5"
    hours: Optional[str] = None
    services: Optional[str] = None
    booking_rules: Optional[str] = None
    transfer_number: Optional[str] = None
    kb_ref: Optional[str] = None
    notification_channel: Optional[str] = None
    calendar_id: Optional[str] = None  # Google Calendar id for this tenant (D-11)

    @field_validator("voice_id")
    @classmethod
    def _voice_id_must_be_non_empty(cls, v: str) -> str:
        """Pitfall 5: an empty voice_id makes ElevenLabs fall back to a default
        English voice — wrong language and persona. Reject empty/whitespace."""
        if v is None or not str(v).strip():
            raise ValueError("voice_id must be a non-empty string")
        return v

    @field_validator("model")
    @classmethod
    def _model_must_be_non_empty(cls, v: str) -> str:
        """A blank model would silently break the LLM service; fall back is the default."""
        if v is None or not str(v).strip():
            raise ValueError("model must be a non-empty string")
        return v
