"""Tests for greeting-on-connect behaviour (VOICE-02 / D-11).

These tests were RED stubs in Plan 01-01. Plan 01-02 removes the xfail markers
and implements the behaviour being asserted here.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.config.tenant_config import TenantConfig


# ---------------------------------------------------------------------------
# VOICE-02 / D-11: bot queues greeting frame on client connect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_greeting_injected(tenant: TenantConfig):
    """VOICE-02 / D-11: on_client_connected queues a TTSSpeakFrame with tenant greeting.

    The test:
    1. Imports make_greeting_handler from src.bot (the testable unit).
    2. Calls make_greeting_handler(worker, tenant) to get the coroutine handler.
    3. Invokes the handler directly (simulating a client connect event).
    4. Asserts queue_frames was called with a TTSSpeakFrame whose text == tenant.greeting.
    """
    from pipecat.frames.frames import TTSSpeakFrame

    # --- Spy worker to capture queue_frames calls ---
    queued_frames: list = []

    mock_worker = MagicMock(name="MockPipelineWorker")

    async def _queue_frames(frames):
        queued_frames.extend(frames)

    mock_worker.queue_frames = _queue_frames

    # --- Invoke the greeting handler factory ---
    from src.bot import make_greeting_handler

    handler = make_greeting_handler(mock_worker, tenant)

    # Simulate the on_client_connected event: handler receives (transport, client)
    mock_transport = MagicMock(name="MockTransport")
    mock_client = MagicMock(name="MockWebRTCClient")
    await handler(mock_transport, mock_client)

    # Assert queue_frames was called at least once
    assert queued_frames, (
        "queue_frames was never called — make_greeting_handler must queue a TTSSpeakFrame"
    )

    # Find the TTSSpeakFrame with the greeting text
    greeting_frames = [
        f for f in queued_frames
        if isinstance(f, TTSSpeakFrame) and f.text == tenant.greeting
    ]
    assert greeting_frames, (
        f"No TTSSpeakFrame with text == {tenant.greeting!r} was queued. "
        f"Queued frames: {queued_frames}"
    )
