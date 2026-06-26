"""Tests for bot wiring and greeting behaviour (VOICE-02 / D-11, D-18, D-19, W5, B3).

Phase 1 tests:
- test_greeting_injected: VOICE-02 / D-11 — on_client_connected queues Italian greeting

Phase 2 Wave 0 stubs (RED until Plans 02-02 and 02-03 implement them):
- test_abandonment_saves_draft: B2/D-18 — cleanup hook saves bozza, never to Calendar
- test_flow_manager_wired: B3 — bot constructs FlowManager(worker=) + initializes greeting node
- test_booking_node_uses_sonnet: B3/D-19 — booking node carries Sonnet-switch pre_action
- test_single_greeting_on_init: W5 — exactly one greeting on FlowManager init (no double-greeting)
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


# ---------------------------------------------------------------------------
# Phase 2 Wave 0 stubs (RED until Plans 02-02 and 02-03 implement them)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abandonment_saves_draft(reservation_repo, in_memory_calendar):
    """B2/D-18: call-termination cleanup hook reads partial flow_manager.state for an
    UNCONFIRMED booking and calls reservation_repo.save_draft(...) writing a status='bozza'
    row that is NEVER passed to the CalendarProvider.

    Asserts:
    - save_draft is invoked with the partial fields collected so far
    - create_event is never called on the calendar provider

    Wave 0 RED: src/bot.py does not yet have a cleanup hook that does this.
    This test will fail until Plan 02-02 adds abandonment/save_draft logic.
    """
    # Import the abandonment hook — does not exist until Plan 02-02
    from src.bot import make_abandonment_handler  # RED: does not exist yet

    partial_state = {
        "booking_slot": {"date": "2025-07-08", "time_slot": "20:00", "covers": 2},
        "customer": {"name": "Rossi", "phone": "3471234567"},
        "tenant_id": "demo",
    }
    fm = MagicMock()
    fm.state = partial_state

    # Spy on the calendar provider
    in_memory_calendar.create_event = AsyncMock()

    # Spy on save_draft
    reservation_repo.save_draft = AsyncMock()

    handler = make_abandonment_handler(fm, reservation_repo, in_memory_calendar)
    await handler()

    # save_draft must be called with the partial fields
    reservation_repo.save_draft.assert_called_once()
    call_args = reservation_repo.save_draft.call_args
    assert call_args is not None, "save_draft must be called by the abandonment handler"

    # create_event must NEVER be called (drafts are not written to Calendar)
    in_memory_calendar.create_event.assert_not_called()


@pytest.mark.asyncio
async def test_flow_manager_wired(tenant: TenantConfig):
    """B3: bot() constructs a FlowManager with worker= and initializes the greeting node.

    Uses a worker double (no live APIs). Asserts:
    - FlowManager is constructed with worker=
    - flow_manager.initialize is called with the greeting NodeConfig

    Wave 0 RED: src/bot.py does not yet construct a FlowManager.
    This test will fail until Plan 02-03 wires the FlowManager in bot().
    """
    from pipecat_flows import FlowManager

    # Import setup_flow — does not exist until Plan 02-03
    from src.bot import setup_flow  # RED: does not exist yet

    mock_worker = MagicMock(name="MockPipelineWorker")
    mock_llm = MagicMock(name="MockLLMService")
    mock_aggregators = MagicMock(name="MockAggregators")

    with patch("src.bot.FlowManager") as MockFlowManager:
        mock_fm = AsyncMock(name="MockFlowManagerInstance")
        mock_fm.state = {}
        MockFlowManager.return_value = mock_fm

        await setup_flow(mock_worker, mock_llm, mock_aggregators, tenant)

    # FlowManager must be constructed with worker= (not deprecated task=)
    MockFlowManager.assert_called_once()
    kwargs = MockFlowManager.call_args.kwargs
    assert "worker" in kwargs, (
        "FlowManager must be constructed with worker= kwarg (not deprecated task=). "
        "RESEARCH.md §Anti-Patterns and §Pattern 1."
    )
    assert kwargs["worker"] is mock_worker

    # initialize must be called with an initial node
    mock_fm.initialize.assert_called_once()
    initial_node = mock_fm.initialize.call_args.args[0]
    assert isinstance(initial_node, dict), (
        f"FlowManager.initialize must receive a NodeConfig dict; got {type(initial_node)}"
    )


@pytest.mark.asyncio
async def test_booking_node_uses_sonnet(tenant: TenantConfig):
    """B3/D-19: the booking node carries the Sonnet-switch pre_action and the switcher/override
    references the verified Sonnet model id (claude-sonnet-4-6).

    Wave 0 RED: src/flows/nodes.py does not exist yet.
    This test will fail until Plan 02-03 creates build_booking_node() with the Sonnet override.
    """
    from src.flows.nodes import build_booking_node  # RED: does not exist yet

    booking_node = build_booking_node(tenant)

    assert isinstance(booking_node, dict), (
        f"build_booking_node must return a NodeConfig dict; got {type(booking_node)}"
    )

    # The booking node must have pre_actions that reference the Sonnet model override (D-19)
    pre_actions = booking_node.get("pre_actions", [])
    assert pre_actions, (
        "build_booking_node must include pre_actions for the Sonnet model switch (D-19). "
        "The booking path requires claude-sonnet-4-6 for reliable tool-calling."
    )

    # Verify the Sonnet model ID is referenced somewhere in the node config or pre_action handler
    node_str = str(booking_node)
    assert "sonnet" in node_str.lower() or "claude-sonnet-4-6" in node_str, (
        f"build_booking_node must reference claude-sonnet-4-6 in pre_actions or functions. "
        f"Got node: {booking_node!r}. "
        "D-19: the booking node switches to Sonnet for more reliable tool-calling."
    )


@pytest.mark.asyncio
async def test_single_greeting_on_init(tenant: TenantConfig):
    """W5: when the FlowManager initializes the greeting node exactly ONE greeting utterance
    is produced — no double-greeting.

    Uses a mock TTS output list to count TTSSpeakFrame emissions.
    The test will fail if the greeting is queued twice (double-greeting regression).

    Wave 0 RED: src/bot.py does not yet have FlowManager wiring.
    This test will fail until Plan 02-03 wires setup_flow in bot().
    """
    from pipecat.frames.frames import TTSSpeakFrame

    from src.bot import setup_flow  # RED: does not exist yet

    queued_frames: list = []

    mock_worker = MagicMock(name="MockPipelineWorker")

    async def _queue_frames(frames):
        queued_frames.extend(frames)

    mock_worker.queue_frames = _queue_frames
    mock_llm = MagicMock(name="MockLLMService")
    mock_aggregators = MagicMock(name="MockAggregators")

    with patch("src.bot.FlowManager") as MockFlowManager:
        mock_fm = AsyncMock(name="MockFlowManagerInstance")
        mock_fm.state = {}
        MockFlowManager.return_value = mock_fm

        await setup_flow(mock_worker, mock_llm, mock_aggregators, tenant)

    # Count TTSSpeakFrame emissions that contain the tenant greeting text
    greeting_frames = [
        f for f in queued_frames
        if isinstance(f, TTSSpeakFrame) and f.text == tenant.greeting
    ]

    assert len(greeting_frames) <= 1, (
        f"W5: exactly ONE greeting utterance must be produced on FlowManager init. "
        f"Got {len(greeting_frames)} greeting frames: {greeting_frames}. "
        "Double-greeting occurs when both make_greeting_handler and FlowManager.initialize "
        "emit the greeting — only one should fire."
    )
