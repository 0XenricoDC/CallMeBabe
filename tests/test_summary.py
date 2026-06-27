"""Tests for generate_summary and _determine_outcome (NOTIF-02, D-05).

RED state (Task 1): imports from src.call_log.summary which does NOT yet
expose generate_summary — tests will FAIL/ERROR until Task 3 implements it.
_determine_outcome tests are in test_call_log.py and will also fail until
Task 2 creates summary.py.

Coverage:
- test_generate_summary_returns_nonempty_string : mocked Anthropic → non-empty string
- test_generate_summary_exception_returns_fallback : exception → safe fallback string
- test_generate_summary_fallback_no_pii_logged   : PII not leaked on exception path
- test_generate_summary_uses_tenant_model        : uses tenant.model, not hardcoded id
- test_generate_summary_key_from_env             : ANTHROPIC_API_KEY via os.getenv
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_tenant(model="claude-haiku-4-5", business_name="Ristorante Test"):
    """Minimal TenantConfig stand-in for unit tests (no DB needed)."""
    t = MagicMock()
    t.model = model
    t.business_name = business_name
    return t


SAMPLE_TRANSCRIPT = [
    {"role": "system", "content": "Sei la receptionist di Ristorante Test."},
    {"role": "assistant", "content": "Buongiorno! Posso aiutarla?"},
    {"role": "user", "content": "Vorrei un tavolo per due stasera."},
    {"role": "assistant", "content": "Certo! Che orario preferisce?"},
    {"role": "user", "content": "Alle 20:00, grazie."},
]


# ---------------------------------------------------------------------------
# Task 3 tests — RED until generate_summary is implemented
# ---------------------------------------------------------------------------

async def test_generate_summary_returns_nonempty_string():
    """NOTIF-02: generate_summary returns a non-empty string from a mocked Anthropic client.

    Mocks anthropic.AsyncAnthropic so no API key is needed. Verifies the function
    returns the model text (non-empty string) on success.
    """
    from src.call_log.summary import generate_summary  # noqa: PLC0415

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Il cliente ha prenotato un tavolo per due alle 20:00.")]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    mock_anthropic_cls = MagicMock(return_value=mock_client)

    tenant = _make_tenant()
    with patch("anthropic.AsyncAnthropic", mock_anthropic_cls):
        result = await generate_summary(
            tenant=tenant,
            transcript=SAMPLE_TRANSCRIPT,
            outcome="prenotato",
        )

    assert isinstance(result, str), "generate_summary must return a string"
    assert len(result.strip()) > 0, "generate_summary must return a non-empty string"


async def test_generate_summary_exception_returns_fallback():
    """D-05 safety: on any Anthropic exception, generate_summary returns a safe fallback.

    The fallback must be a non-empty string and must include the outcome for
    operator context. No exception must propagate to the caller.
    """
    from src.call_log.summary import generate_summary  # noqa: PLC0415

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API timeout"))

    mock_anthropic_cls = MagicMock(return_value=mock_client)

    tenant = _make_tenant()
    with patch("anthropic.AsyncAnthropic", mock_anthropic_cls):
        result = await generate_summary(
            tenant=tenant,
            transcript=SAMPLE_TRANSCRIPT,
            outcome="faq",
        )

    assert isinstance(result, str), "Fallback must be a string"
    assert len(result.strip()) > 0, "Fallback must be non-empty"
    # The fallback should include the outcome for operator context (D-05)
    assert "faq" in result.lower() or "riepilogo" in result.lower() or "disponibile" in result.lower(), (
        f"Fallback should reference the outcome or indicate unavailability. Got: {result!r}"
    )


async def test_generate_summary_fallback_no_pii_logged():
    """T-03-PII: exception path must NOT log any transcript content or caller PII.

    Verifies that when the Anthropic call fails, the loguru output does not
    contain any content from the transcript messages (PII safety, D-05).
    """
    import loguru  # noqa: PLC0415

    from src.call_log.summary import generate_summary  # noqa: PLC0415

    pii_transcript = [
        {"role": "assistant", "content": "Buongiorno!"},
        {"role": "user", "content": "Sono Mario Rossi, telefono 333-9876543."},
        {"role": "assistant", "content": "Perfetto, la prenoterò."},
    ]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("Network error"))
    mock_anthropic_cls = MagicMock(return_value=mock_client)

    captured_messages: list[str] = []

    def _sink(message):
        captured_messages.append(str(message))

    handler_id = loguru.logger.add(_sink, level="DEBUG")
    try:
        tenant = _make_tenant()
        with patch("anthropic.AsyncAnthropic", mock_anthropic_cls):
            await generate_summary(
                tenant=tenant,
                transcript=pii_transcript,
                outcome="trasferito",
            )
    finally:
        loguru.logger.remove(handler_id)

    full_log = " ".join(captured_messages)
    # PII must NOT appear in log output
    assert "Mario Rossi" not in full_log, "Caller name must NOT appear in log on exception"
    assert "333-9876543" not in full_log, "Caller phone must NOT appear in log on exception"
    # transcript content must not be logged
    assert "Sono Mario Rossi" not in full_log, "Transcript PII must NOT be logged"


async def test_generate_summary_uses_tenant_model():
    """generate_summary uses tenant.model, not a hardcoded model id.

    Verifies that the model passed to the Anthropic client matches tenant.model.
    No competing hardcoded model id should override it.
    """
    from src.call_log.summary import generate_summary  # noqa: PLC0415

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Riepilogo della chiamata.")]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_anthropic_cls = MagicMock(return_value=mock_client)

    # Use a distinctive model id so we can verify it was forwarded
    custom_model = "claude-haiku-4-5"
    tenant = _make_tenant(model=custom_model)

    with patch("anthropic.AsyncAnthropic", mock_anthropic_cls):
        await generate_summary(
            tenant=tenant,
            transcript=SAMPLE_TRANSCRIPT,
            outcome="faq",
        )

    # Verify the create call used the tenant's model
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs is not None, "messages.create must have been called"
    used_model = call_kwargs.kwargs.get("model") or (
        call_kwargs.args[0] if call_kwargs.args else None
    )
    assert used_model == custom_model, (
        f"generate_summary must use tenant.model='{custom_model}', got: {used_model!r}"
    )


async def test_generate_summary_key_from_env():
    """T-03-KEY: generate_summary reads ANTHROPIC_API_KEY only via os.getenv.

    Sets a fake env key and confirms the Anthropic client is instantiated with it.
    No key must be hardcoded in the function body.
    """
    from src.call_log.summary import generate_summary  # noqa: PLC0415

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Test summary.")]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_anthropic_cls = MagicMock(return_value=mock_client)

    fake_key = "sk-test-key-for-unit-test"
    tenant = _make_tenant()

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": fake_key}):
        with patch("anthropic.AsyncAnthropic", mock_anthropic_cls):
            await generate_summary(
                tenant=tenant,
                transcript=SAMPLE_TRANSCRIPT,
                outcome="faq",
            )

    # Confirm AsyncAnthropic was constructed with the env key
    init_kwargs = mock_anthropic_cls.call_args
    assert init_kwargs is not None, "anthropic.AsyncAnthropic must have been called"
    passed_key = init_kwargs.kwargs.get("api_key") or (
        init_kwargs.args[0] if init_kwargs.args else None
    )
    assert passed_key == fake_key, (
        f"ANTHROPIC_API_KEY from env must be passed to AsyncAnthropic. Got: {passed_key!r}"
    )
