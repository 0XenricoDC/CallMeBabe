"""Verify Anthropic model IDs used in Phase 2 against the live API.

This test resolves RESEARCH Open Question 1 (OQ1): the model IDs recorded in
STATE.md (claude-haiku-4-5 for the default path, claude-sonnet-4-6 for the
booking path) are MEDIUM-confidence per CLAUDE.md. This test confirms them
against the live Anthropic models API.

When ANTHROPIC_API_KEY is not set (e.g. CI without keys), the test is skipped
so the suite stays green. When the key IS set, the test must pass — any model
ID mismatch means the SUMMARY must record the corrected ID.
"""

from __future__ import annotations

import os

import pytest


# Model IDs used in Phase 2 (from STATE.md Accumulated Context, D-10/D-19)
HAIKU_MODEL_ID = "claude-haiku-4-5"    # D-10: default model for voice turns
SONNET_MODEL_ID = "claude-sonnet-4-6"  # D-19: booking path (better tool-calling)

_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_HAS_KEY = bool(_API_KEY)


@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set — skipping live model ID verification")
def test_booking_and_default_model_ids_exist():
    """OQ1: Verify both Phase 2 model IDs are present in the Anthropic models list.

    Uses the synchronous Anthropic client so this test works without asyncio.
    The test asserts that claude-haiku-4-5 and claude-sonnet-4-6 exist in the
    list returned by client.models.list(). If either is absent, the assertion
    failure message shows which ID was not found so the SUMMARY can record the
    corrected ID for downstream plans (02-02, 02-03, etc.).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=_API_KEY)

    # Fetch all available model IDs from the live API
    models_page = client.models.list()
    available_ids = {m.id for m in models_page.data}

    # The list() endpoint may return paginated results; gather all pages
    # (in practice Anthropic returns all models on the first page, but
    # iterate to be safe).
    while models_page.has_next_page():
        models_page = models_page.get_next_page()
        available_ids.update(m.id for m in models_page.data)

    assert HAIKU_MODEL_ID in available_ids, (
        f"Default model '{HAIKU_MODEL_ID}' not found in Anthropic model list. "
        f"Available models: {sorted(available_ids)}. "
        "Update HAIKU_MODEL_ID in this test and record the corrected ID in the SUMMARY."
    )
    assert SONNET_MODEL_ID in available_ids, (
        f"Booking model '{SONNET_MODEL_ID}' not found in Anthropic model list. "
        f"Available models: {sorted(available_ids)}. "
        "Update SONNET_MODEL_ID in this test and record the corrected ID in the SUMMARY."
    )
