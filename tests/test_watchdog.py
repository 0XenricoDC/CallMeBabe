"""Tests for the dead-air watchdog handler (REL-04 / Plan 03-04).

SC5: silence triggers re-prompt at T1, then recovery/transfer at T2.

The _DeadAirHandler class (defined in src.bot) is a pure-Python state machine
so it can be tested without running the full pipeline.

RED state: handler does not exist yet (Task 1). Turns GREEN in Task 3.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs for aggregator and worker
# ---------------------------------------------------------------------------

class _SpyAggregator:
    """Minimal aggregator spy that captures push_frame calls."""

    def __init__(self):
        self.pushed_frames: list = []

    async def push_frame(self, frame, direction=None):
        self.pushed_frames.append((frame, direction))


class _SpyWorker:
    """Minimal worker spy that captures queue_frame calls."""

    def __init__(self):
        self.queued_frames: list = []

    async def queue_frame(self, frame, direction=None):
        self.queued_frames.append((frame, direction))


# ---------------------------------------------------------------------------
# Tests for _DeadAirHandler
# ---------------------------------------------------------------------------

def test_dead_air_handler_first_idle_reprompts():
    """REL-04 / SC5 (T1): first on_user_turn_idle must send a gentle re-prompt.

    The re-prompt is an LLMMessagesAppendFrame (or TTSSpeakFrame) that instructs
    the LLM to ask 'È ancora in linea?'. The call must NOT terminate (no EndWorkerFrame).
    """
    from pipecat.frames.frames import EndWorkerFrame

    from src.bot import _DeadAirHandler

    aggregator = _SpyAggregator()
    worker = _SpyWorker()
    flow_manager = MagicMock()
    flow_manager.state = {}

    handler = _DeadAirHandler(flow_manager=flow_manager, worker=worker)

    async def _run():
        await handler.on_idle(aggregator)

    asyncio.run(_run())

    # After first idle, at least one frame should be pushed (re-prompt)
    assert len(aggregator.pushed_frames) > 0 or len(worker.queued_frames) > 0, (
        "First on_user_turn_idle must push a re-prompt frame."
    )

    # No EndWorkerFrame yet — call must continue
    all_frames = [f for f, _ in aggregator.pushed_frames + worker.queued_frames]
    end_frames = [f for f in all_frames if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) == 0, (
        "First idle must NOT terminate the call (no EndWorkerFrame after T1 re-prompt)."
    )


def test_dead_air_handler_second_idle_sets_outcome_fallito():
    """REL-04 / SC5 (T2): second on_user_turn_idle must set outcome='fallito' + EndWorkerFrame.

    After the re-prompt, continued silence triggers recovery:
    - flow_manager.state['outcome'] is set to 'fallito'
    - An EndWorkerFrame is queued (call terminates)
    """
    from pipecat.frames.frames import EndWorkerFrame

    from src.bot import _DeadAirHandler

    aggregator = _SpyAggregator()
    worker = _SpyWorker()
    flow_manager = MagicMock()
    flow_manager.state = {}

    handler = _DeadAirHandler(flow_manager=flow_manager, worker=worker)

    async def _run():
        # First idle — re-prompt
        await handler.on_idle(aggregator)
        # Second idle — escalation
        await handler.on_idle(aggregator)

    asyncio.run(_run())

    # outcome must be 'fallito'
    assert flow_manager.state.get("outcome") == "fallito", (
        "Second on_user_turn_idle must set flow_manager.state['outcome'] = 'fallito'."
    )

    # EndWorkerFrame must have been queued (call terminates)
    all_frames = [f for f, _ in aggregator.pushed_frames + worker.queued_frames]
    end_frames = [f for f in all_frames if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) >= 1, (
        "Second on_user_turn_idle must queue an EndWorkerFrame to terminate the call."
    )


def test_dead_air_handler_reset_zeroes_count():
    """REL-04: reset() must zero the idle counter so the next idle is a re-prompt again.

    If the user spoke (on_user_turn_started), the counter resets and the next
    silence starts fresh from T1.
    """
    from pipecat.frames.frames import EndWorkerFrame

    from src.bot import _DeadAirHandler

    aggregator = _SpyAggregator()
    worker = _SpyWorker()
    flow_manager = MagicMock()
    flow_manager.state = {}

    handler = _DeadAirHandler(flow_manager=flow_manager, worker=worker)

    async def _run():
        # First idle — re-prompt
        await handler.on_idle(aggregator)
        # User speaks — reset
        handler.reset()
        # Second idle (now count==1 again, NOT count==2) — must re-prompt, not escalate
        await handler.on_idle(aggregator)

    asyncio.run(_run())

    # After reset, second idle should NOT set 'fallito'
    assert flow_manager.state.get("outcome") != "fallito", (
        "After reset(), the next idle must be a re-prompt (count==1), not an escalation."
    )

    # No EndWorkerFrame after the reset idle
    all_frames = [f for f, _ in aggregator.pushed_frames + worker.queued_frames]
    end_frames = [f for f in all_frames if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) == 0, (
        "reset() must zero the counter; subsequent idle at count==1 must not terminate."
    )
