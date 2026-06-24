"""Tests for pipeline observers (VOICE-04 metrics, REL-01 error fallback).

Plan 03 — implements and de-xfails these tests.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs to replicate Pipecat frame/observer data structures in tests
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


# ---------------------------------------------------------------------------
# Task 1: LatencyObserver
# ---------------------------------------------------------------------------

def test_latency_observer(tmp_path):
    """VOICE-04 / D-06: LatencyObserver emits per-turn console line + JSONL record.

    Feed synthetic MetricsFrames with TTFBMetricsData whose `.processor` carries
    the REAL service names the live pipeline emits (DeepgramSTTService#0,
    AnthropicLLMService#0, ElevenLabsTTSService#0), then call _flush_turn() and
    assert routing + JSONL output. Routing is on `metric.processor`, not
    `data.source.name` (the live-bug root cause).
    """
    from pipecat.frames.frames import MetricsFrame
    from pipecat.metrics.metrics import TTFBMetricsData

    from src.pipeline.observers import LatencyObserver

    jsonl_path = str(tmp_path / "latency.jsonl")
    observer = LatencyObserver(jsonl_path)

    # Use the ACTUAL service processor names the live pipeline emits (verified).
    stt_metric = TTFBMetricsData(processor="DeepgramSTTService#0", value=0.180)
    stt_frame = MetricsFrame(data=[stt_metric])
    stt_push = _FakeFramePushed(source=_FakeProcessor("DeepgramSTTService#0"), frame=stt_frame)

    llm_metric = TTFBMetricsData(processor="AnthropicLLMService#0", value=0.240)
    llm_frame = MetricsFrame(data=[llm_metric])
    llm_push = _FakeFramePushed(source=_FakeProcessor("AnthropicLLMService#0"), frame=llm_frame)

    tts_metric = TTFBMetricsData(processor="ElevenLabsTTSService#0", value=0.160)
    tts_frame = MetricsFrame(data=[tts_metric])
    tts_push = _FakeFramePushed(source=_FakeProcessor("ElevenLabsTTSService#0"), frame=tts_frame)

    async def _run():
        await observer.on_push_frame(stt_push)
        await observer.on_push_frame(llm_push)
        await observer.on_push_frame(tts_push)
        # Simulate turn end: 620ms total
        observer._flush_turn(turn_ms=620)

    asyncio.run(_run())

    # --- Assert JSONL record ---
    assert os.path.exists(jsonl_path), "JSONL file must be created"
    lines = open(jsonl_path).read().strip().splitlines()
    assert len(lines) == 1, f"Expected 1 JSONL line, got {len(lines)}"
    record = json.loads(lines[0])
    assert record["turn_ms"] == 620
    assert record["stt_ms"] == 180
    assert record["llm_ttft_ms"] == 240
    assert record["tts_ttfb_ms"] == 160
    assert "ts" in record


def test_latency_observer_warns_over_budget(tmp_path, capsys):
    """VOICE-04 / D-06: LatencyObserver prints a [WARN] line when turn_ms > 800."""
    from src.pipeline.observers import LatencyObserver

    jsonl_path = str(tmp_path / "latency_warn.jsonl")
    observer = LatencyObserver(jsonl_path)

    observer._flush_turn(turn_ms=950)

    captured = capsys.readouterr()
    assert "[WARN]" in captured.out, "Expected [WARN] in stdout for over-budget turn"
    assert "800" in captured.out, "Warning must mention the 800ms budget"


def test_latency_observer_console_line(tmp_path, capsys):
    """D-06: The console line matches `turn=...ms | stt=... llm_ttft=... tts_ttfb=...`."""
    from src.pipeline.observers import LatencyObserver

    jsonl_path = str(tmp_path / "latency_line.jsonl")
    observer = LatencyObserver(jsonl_path)
    observer._stt_ms = 180
    observer._llm_ttft_ms = 240
    observer._tts_ttfb_ms = 160
    observer._flush_turn(turn_ms=620)

    captured = capsys.readouterr()
    line = captured.out.splitlines()[0]
    assert "turn=620ms" in line
    assert "stt=180" in line
    assert "llm_ttft=240" in line
    assert "tts_ttfb=160" in line
    assert "|" in line


class _FakeTurnTrackingObserver:
    """Minimal stand-in for pipecat's TurnTrackingObserver.

    Captures the handler registered via `event_handler("on_turn_ended")` and lets
    the test fire it, exactly as the real observer does at the end of a turn.
    """

    def __init__(self):
        self._handlers = {}

    def event_handler(self, name):
        def decorator(fn):
            self._handlers[name] = fn
            return fn

        return decorator

    async def fire(self, name, *args):
        await self._handlers[name](self, *args)


def test_latency_observer_real_flow(tmp_path, capsys):
    """REGRESSION (live bug): the full real flow must emit a line + JSONL.

    Reproduces the live integration the unit tests previously missed:
      1. MetricsFrames routed by `metric.processor` (real service names).
      2. Turn end driven by TurnTrackingObserver's `on_turn_ended` event (NOT by a
         raw frame inside on_push_frame), wired via `register_turn_end`.

    The previous implementation never reached `_flush_turn` live; this test fails
    against that version and passes against the fixed one.
    """
    from pipecat.frames.frames import MetricsFrame
    from pipecat.metrics.metrics import TTFBMetricsData

    from src.pipeline.observers import LatencyObserver

    jsonl_path = str(tmp_path / "latency_real.jsonl")
    observer = LatencyObserver(jsonl_path)

    turn_tracker = _FakeTurnTrackingObserver()
    observer.register_turn_end(turn_tracker)

    def _metrics_push(processor, value):
        metric = TTFBMetricsData(processor=processor, value=value)
        frame = MetricsFrame(data=[metric])
        return _FakeFramePushed(source=_FakeProcessor("some-downstream-processor"), frame=frame)

    async def _run():
        # Metrics arrive during the turn (note: source name is a DOWNSTREAM processor,
        # proving routing must use metric.processor, not data.source.name).
        await observer.on_push_frame(_metrics_push("DeepgramSTTService#0", 0.150))
        await observer.on_push_frame(_metrics_push("AnthropicLLMService#0", 0.300))
        await observer.on_push_frame(_metrics_push("ElevenLabsTTSService#0", 0.120))
        # Turn ends — TurnTrackingObserver fires on_turn_ended(turn, duration_secs, interrupted)
        await turn_tracker.fire("on_turn_ended", 1, 0.570, False)

    asyncio.run(_run())

    # The line must have been printed AND the JSONL populated.
    captured = capsys.readouterr()
    assert "turn=570ms" in captured.out, f"Expected live turn line, got: {captured.out!r}"

    assert os.path.exists(jsonl_path)
    lines = open(jsonl_path).read().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["turn_ms"] == 570
    assert record["stt_ms"] == 150
    assert record["llm_ttft_ms"] == 300
    assert record["tts_ttfb_ms"] == 120


def test_latency_observer_survives_bad_frame(tmp_path):
    """REGRESSION (live bug, LEAD 1): on_push_frame must NOT raise on a malformed frame.

    The WorkerObserver proxy has no try/except around on_push_frame; an exception
    would kill the observer for the whole session. A MetricsFrame whose `data` is
    None (or a metric missing fields) must be swallowed without raising, and a
    subsequent valid frame must still be routed.
    """
    from pipecat.frames.frames import MetricsFrame
    from pipecat.metrics.metrics import TTFBMetricsData

    from src.pipeline.observers import LatencyObserver

    jsonl_path = str(tmp_path / "latency_bad.jsonl")
    observer = LatencyObserver(jsonl_path)

    # A MetricsFrame with data=None would make `for metric in frame.data` raise.
    bad_frame = MetricsFrame(data=None)  # type: ignore[arg-type]
    bad_push = _FakeFramePushed(source=_FakeProcessor("x"), frame=bad_frame)

    good_metric = TTFBMetricsData(processor="DeepgramSTTService#0", value=0.200)
    good_frame = MetricsFrame(data=[good_metric])
    good_push = _FakeFramePushed(source=_FakeProcessor("x"), frame=good_frame)

    async def _run():
        # Must not raise.
        await observer.on_push_frame(bad_push)
        # Observer must still be functional afterwards.
        await observer.on_push_frame(good_push)
        observer._flush_turn(turn_ms=400)

    asyncio.run(_run())

    record = json.loads(open(jsonl_path).read().strip().splitlines()[0])
    assert record["stt_ms"] == 200, "Observer must keep routing after a malformed frame"


# ---------------------------------------------------------------------------
# Task 2: ErrorFallbackObserver
# ---------------------------------------------------------------------------

EXPECTED_COURTESY = "Mi scusi, ho avuto un problema tecnico, può ripetere?"


def test_error_fallback():
    """REL-01 / D-07: a non-fatal ErrorFrame triggers the Italian courtesy phrase.

    Uses a spy worker to capture queued frames.
    """
    from pipecat.frames.frames import ErrorFrame, TTSSpeakFrame

    from src.pipeline.fallback import COURTESY_PHRASE, ErrorFallbackObserver

    assert COURTESY_PHRASE == EXPECTED_COURTESY, (
        f"Unexpected courtesy phrase: {COURTESY_PHRASE!r}"
    )

    spy_frames: list = []

    class _SpyWorker:
        async def queue_frames(self, frames):
            spy_frames.extend(frames)

    worker = _SpyWorker()
    observer = ErrorFallbackObserver(worker)

    # Simulate first non-fatal ErrorFrame from a service source
    err_frame = ErrorFrame(error="service timeout", fatal=False)
    push = _FakeFramePushed(
        source=_FakeProcessor("deepgram-stt"),
        frame=err_frame,
    )

    async def _run():
        # D-07: one retry slot — first ErrorFrame → retry slot consumed
        await observer.on_push_frame(push)
        # Second ErrorFrame from the same source → courtesy phrase queued
        await observer.on_push_frame(push)

    asyncio.run(_run())

    # After two ErrorFrames from same source, at least one TTSSpeakFrame with courtesy phrase
    speak_frames = [f for f in spy_frames if isinstance(f, TTSSpeakFrame)]
    assert len(speak_frames) >= 1, (
        "Expected at least one TTSSpeakFrame after repeated non-fatal errors"
    )
    assert speak_frames[0].text == EXPECTED_COURTESY, (
        f"TTSSpeakFrame text must be the courtesy phrase, got: {speak_frames[0].text!r}"
    )


def test_error_fallback_fatal_ignored():
    """D-07: fatal ErrorFrames must NOT trigger the courtesy phrase."""
    from pipecat.frames.frames import ErrorFrame, TTSSpeakFrame

    from src.pipeline.fallback import ErrorFallbackObserver

    spy_frames: list = []

    class _SpyWorker:
        async def queue_frames(self, frames):
            spy_frames.extend(frames)

    worker = _SpyWorker()
    observer = ErrorFallbackObserver(worker)

    fatal_frame = ErrorFrame(error="unrecoverable error", fatal=True)
    push = _FakeFramePushed(source=_FakeProcessor("some-service"), frame=fatal_frame)

    asyncio.run(observer.on_push_frame(push))

    speak_frames = [f for f in spy_frames if isinstance(f, TTSSpeakFrame)]
    assert len(speak_frames) == 0, "Fatal ErrorFrame must NOT trigger courtesy phrase"


def test_error_fallback_no_secret_leak(tmp_path, capsys):
    """V7 / T-03-LOG: ErrorFallbackObserver must not log raw error object or API keys.

    Simulates an ErrorFrame whose error string contains a fake API key, then
    asserts the key does not appear in stdout/stderr.
    """
    from pipecat.frames.frames import ErrorFrame

    from src.pipeline.fallback import ErrorFallbackObserver

    spy_frames: list = []

    class _SpyWorker:
        async def queue_frames(self, frames):
            spy_frames.extend(frames)

    worker = _SpyWorker()
    observer = ErrorFallbackObserver(worker)

    # Error string that looks like it contains an API key fragment
    FAKE_KEY = "sk-ant-api03-SUPERSECRETKEY1234567890"
    err_frame = ErrorFrame(error=f"HTTP 401 Unauthorized: {FAKE_KEY}", fatal=False)
    push = _FakeFramePushed(source=_FakeProcessor("anthropic-llm"), frame=err_frame)

    async def _run():
        await observer.on_push_frame(push)
        await observer.on_push_frame(push)

    asyncio.run(_run())

    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out, "API key fragment must not appear in stdout"
    assert FAKE_KEY not in captured.err, "API key fragment must not appear in stderr"
