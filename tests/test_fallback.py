"""Tests for ErrorFallbackObserver escalation (REL-02 / Plans 03-04, 03-06).

SC4: persistent failure -> courtesy + transfer, outcome fallito, no dead-air.

Extends the existing REL-01 retry-slot tests (in test_observers.py) with
escalation-threshold coverage.

Plan 03-04 RED state: _ESCALATION_THRESHOLD and escalation logic do not exist yet (Task 1).
Plan 03-04 GREEN: turned GREEN in Task 2.

Plan 03-06 addition: shared escalation guard
  test_shared_escalation_guard_prevents_double_endworkerframe verifies that when
  flow_manager.state['_stt_escalated'] is True (set by stt_switcher's on_service_switched
  escalation), ErrorFallbackObserver does NOT queue an additional EndWorkerFrame.
  RED: current fallback.py uses self._escalated (local flag only), ignores shared key.
  GREEN: fallback.py checks flow_manager.state.get('_stt_escalated', False).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs — mirror test_observers.py pattern
# ---------------------------------------------------------------------------

@dataclass
class _FakeProcessor:
    """Minimal FrameProcessor stand-in whose .name is a plain string."""
    name: str


@dataclass
class _FakeFramePushed:
    """FramePushed stand-in."""
    source: _FakeProcessor
    frame: object
    destination: object = None
    direction: object = None
    timestamp: int = 0


class _SpyWorker:
    """Captures frames queued via queue_frames()."""

    def __init__(self):
        self.queued: list = []

    async def queue_frames(self, frames):
        self.queued.extend(frames)


# ---------------------------------------------------------------------------
# Task 2: Escalation threshold tests (RED until Task 2 GREEN)
# ---------------------------------------------------------------------------

def test_escalation_threshold_constant_exists():
    """REL-02: _ESCALATION_THRESHOLD must be a positive integer in fallback.py."""
    from src.pipeline.fallback import _ESCALATION_THRESHOLD

    assert isinstance(_ESCALATION_THRESHOLD, int), (
        "_ESCALATION_THRESHOLD must be an integer."
    )
    assert _ESCALATION_THRESHOLD > 0, (
        "_ESCALATION_THRESHOLD must be a positive integer (>0)."
    )


def test_escalation_after_threshold_sets_outcome_fallito():
    """REL-02 / SC4: after _ESCALATION_THRESHOLD persistent errors, outcome is 'fallito'.

    The escalation fires after the retry-slot cycle has exhausted _ESCALATION_THRESHOLD
    times for the same source. Each retry-slot cycle = 2 errors (first is retry slot,
    second queues courtesy phrase). The escalation counter increments after each cycle.
    """
    from pipecat.frames.frames import EndWorkerFrame, ErrorFrame, TTSSpeakFrame

    from src.pipeline.fallback import _ESCALATION_THRESHOLD, ErrorFallbackObserver

    spy = _SpyWorker()
    fake_fm = type("_FM", (), {"state": {}})()

    observer = ErrorFallbackObserver(worker=spy)
    observer.flow_manager = fake_fm

    err_frame = ErrorFrame(error="STT timeout", fatal=False)
    push = _FakeFramePushed(source=_FakeProcessor("deepgram-stt"), frame=err_frame)

    async def _run():
        # Each retry-slot cycle exhausts after 2 ErrorFrames from same source.
        # We need to hit _ESCALATION_THRESHOLD cycles.
        for _ in range(_ESCALATION_THRESHOLD * 2):
            await observer.on_push_frame(push)

    asyncio.run(_run())

    # After reaching threshold, outcome must be 'fallito'
    assert fake_fm.state.get("outcome") == "fallito", (
        f"After {_ESCALATION_THRESHOLD} retry-slot cycles, "
        "observer must set outcome='fallito' (REL-02 / SC4)."
    )

    # EndWorkerFrame must be queued
    end_frames = [f for f in spy.queued if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) >= 1, (
        "Escalation must queue an EndWorkerFrame to terminate the call (SC4 no dead-air)."
    )


def test_escalation_fires_only_once():
    """REL-02: escalation guard (_escalated flag) prevents multiple EndWorkerFrames.

    After the first escalation, further errors from the same source must NOT
    queue additional EndWorkerFrames (idempotent via _escalated flag).
    """
    from pipecat.frames.frames import EndWorkerFrame, ErrorFrame

    from src.pipeline.fallback import _ESCALATION_THRESHOLD, ErrorFallbackObserver

    spy = _SpyWorker()
    fake_fm = type("_FM", (), {"state": {}})()

    observer = ErrorFallbackObserver(worker=spy)
    observer.flow_manager = fake_fm

    err_frame = ErrorFrame(error="persistent STT failure", fatal=False)
    push = _FakeFramePushed(source=_FakeProcessor("deepgram-stt"), frame=err_frame)

    async def _run():
        # 2× threshold — double the errors that would trigger escalation
        for _ in range(_ESCALATION_THRESHOLD * 4):
            await observer.on_push_frame(push)

    asyncio.run(_run())

    # EndWorkerFrame must appear exactly once (idempotent)
    end_frames = [f for f in spy.queued if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) == 1, (
        f"Escalation must fire exactly once (idempotent via _escalated guard); "
        f"got {len(end_frames)} EndWorkerFrame(s)."
    )


def test_escalation_observer_has_flow_manager_attribute():
    """REL-02: ErrorFallbackObserver must expose a flow_manager attribute (settable by bot.py)."""
    from src.pipeline.fallback import ErrorFallbackObserver

    spy = _SpyWorker()
    observer = ErrorFallbackObserver(worker=spy)

    # Must have the attribute and start as None
    assert hasattr(observer, "flow_manager"), (
        "ErrorFallbackObserver must have a flow_manager attribute (patched by bot.py after "
        "FlowManager creation)."
    )
    assert observer.flow_manager is None, (
        "flow_manager must default to None (patched post-construction, like .worker)."
    )


# ---------------------------------------------------------------------------
# Plan 03-06 / Task 1 (RED): shared escalation guard between switcher + observer
# ---------------------------------------------------------------------------

def test_shared_escalation_guard_prevents_double_endworkerframe():
    """Shared guard: observer must NOT fire EndWorkerFrame when switcher already escalated.

    When stt_switcher's on_service_switched handler escalates (SC4), it sets
    flow_manager.state['_stt_escalated'] = True. If ErrorFallbackObserver subsequently
    also reaches its threshold, it must check this shared key and skip its own
    EndWorkerFrame — so the call ends cleanly with exactly ONE EndWorkerFrame total.

    Security (V7/T-03-LOG): all phrases are static; no ErrorFrame.error content is used.

    RED: fallback.py uses self._escalated (local, starts False) and ignores
         flow_manager.state['_stt_escalated'], so it fires EndWorkerFrame regardless.
    GREEN: fallback.py checks flow_manager.state.get('_stt_escalated', False) before
           queuing EndWorkerFrame — skips it when the shared key is True.
    """
    from pipecat.frames.frames import EndWorkerFrame, ErrorFrame

    from src.pipeline.fallback import _ESCALATION_THRESHOLD, ErrorFallbackObserver

    spy = _SpyWorker()
    # Simulate that stt_switcher already escalated by pre-setting the shared guard key.
    fake_fm = type("_FM", (), {"state": {"_stt_escalated": True}})()

    observer = ErrorFallbackObserver(worker=spy)
    observer.flow_manager = fake_fm

    err_frame = ErrorFrame(error="STT failure", fatal=False)
    push = _FakeFramePushed(source=_FakeProcessor("deepgram-stt"), frame=err_frame)

    async def _run():
        # Drive enough errors to reach the observer's own escalation threshold
        for _ in range(_ESCALATION_THRESHOLD * 2):
            await observer.on_push_frame(push)

    asyncio.run(_run())

    # Observer must NOT queue EndWorkerFrame — switcher already escalated via shared key.
    end_frames = [f for f in spy.queued if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) == 0, (
        "Shared guard: ErrorFallbackObserver must not queue an EndWorkerFrame when "
        "flow_manager.state['_stt_escalated'] is already True (SC4 idempotency across "
        f"both escalation mechanisms). Got {len(end_frames)} EndWorkerFrame(s)."
    )
