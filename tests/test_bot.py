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
    1. Patches build_pipeline and TenantRepository so no real I/O occurs.
    2. Patches PipelineWorker to capture queue_frames calls.
    3. Patches WorkerRunner so run() returns immediately.
    4. Calls bot() with a fake SmallWebRTCRunnerArguments whose cli_args.tenant == "demo".
    5. Asserts that queue_frames was called with a TTSSpeakFrame whose text == tenant.greeting.
    """
    from pipecat.frames.frames import TTSSpeakFrame

    # --- Spy worker to capture queue_frames calls ---
    queued_frames: list = []

    mock_worker = MagicMock(name="MockPipelineWorker")

    async def _queue_frames(frames):
        queued_frames.extend(frames)

    mock_worker.queue_frames = _queue_frames

    # --- Fake runner (returns immediately) ---
    mock_runner = MagicMock(name="MockWorkerRunner")
    mock_runner.add_workers = AsyncMock()
    mock_runner.run = AsyncMock()

    # --- Fake runner_args ---
    import argparse
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    from pipecat.runner.types import SmallWebRTCRunnerArguments

    cli_args = argparse.Namespace(tenant="demo")
    mock_webrtc_conn = MagicMock(name="WebRTCConnection")
    # cli_args is on the parent RunnerArguments base class; set it as an attribute
    # after construction (this is how the runner sets it before calling bot()).
    runner_args = SmallWebRTCRunnerArguments(webrtc_connection=mock_webrtc_conn)
    runner_args.cli_args = cli_args

    # --- Mock pipeline build (no real services) ---
    mock_pipeline = MagicMock(name="MockPipeline")
    from pipecat.processors.aggregators.llm_context import LLMContext
    mock_context = MagicMock(spec=LLMContext, name="MockContext")

    with (
        patch("src.bot.TransportFactory") as MockTransportFactory,
        patch("src.bot.TenantRepository") as MockRepo,
        patch("src.bot.build_pipeline", return_value=(mock_pipeline, mock_context)),
        patch("src.bot.PipelineWorker", return_value=mock_worker),
        patch("src.bot.WorkerRunner", return_value=mock_runner),
    ):
        # Make TransportFactory.create_webrtc_transport return a mock transport
        mock_transport = MagicMock(name="MockTransport")
        MockTransportFactory.return_value.create_webrtc_transport.return_value = mock_transport

        # Make TenantRepository().get_tenant("demo") return our test tenant
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_tenant.return_value = tenant
        MockRepo.return_value = mock_repo_instance

        from src.bot import bot
        await bot(runner_args)

    # Assert queue_frames was called at least once
    assert queued_frames, (
        "queue_frames was never called — on_client_connected must queue a TTSSpeakFrame"
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
