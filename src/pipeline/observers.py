"""Pipeline observers — non-intrusive metric collection and turn-end instrumentation.

Observers attach to `PipelineWorker` via `PipelineParams(observers=[...])` and receive
every frame that flows through the pipeline without being inserted in the hot-path.

Implements:
  - LatencyObserver: D-06 — per-turn console line + JSONL log (VOICE-04)

Turn-end signal (verified against pipecat 1.4.0 source — `worker.py` / `turn_tracking_observer.py`):
  The pipeline already runs a built-in `TurnTrackingObserver` (enabled by default via
  `enable_turn_tracking=True`) that fires an `on_turn_ended(turn_number, duration_secs,
  was_interrupted)` event. This is the RELIABLE turn boundary — it handles barge-in,
  timeouts, and interruptions. We register `_on_turn_ended` against it from bot.py rather
  than inferring turn end from a raw frame inside `on_push_frame` (which proved unreliable
  live: the bot stopped speaking but `_flush_turn` was never reached).

Metrics routing (verified against `metrics_log_observer.py`, the official reference):
  Each `MetricsData` carries a `.processor` field holding the SERVICE name that produced
  the metric (e.g. "DeepgramSTTService#0"). We route on `metric.processor`, NOT on
  `data.source.name` — `data.source` is the processor that *pushed* the frame, which may
  be a downstream processor and not the originating service.

Defensive guarantee (verified against `worker_observer.py`):
  The WorkerObserver proxy runs each observer in its own task via `_proxy_task_handler`,
  which calls `await observer.on_push_frame(data)` WITHOUT a try/except. If `on_push_frame`
  raises on any frame, that proxy task dies and the observer stops receiving ALL further
  frames for the rest of the session. We therefore wrap the entire body in try/except so a
  single unexpected frame can never silently disable latency logging.

Security (T-03-LOG / T-03-JSONL):
  - LatencyObserver writes only timing integers + timestamp to the JSONL file — no PII.
  - No raw ErrorFrame or API-key values are logged here (see fallback.py for that boundary).
"""

from __future__ import annotations

import json
import os
import time

from loguru import logger

from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import TTFBMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed

LATENCY_BUDGET_MS = 800  # D-06: over-budget warning threshold


class LatencyObserver(BaseObserver):
    """Collect per-stage TTFB metrics and emit a human-readable line + JSONL per turn.

    Metrics routing (verified — route on `metric.processor`, the service name):
      - TTS checked first ("ElevenLabsTTSService".lower() contains "stt" — see below)
      - elevenlabs / ttsservice → tts_ttfb_ms
      - deepgram / sttservice → stt_ms
      - anthropic / llmservice → llm_ttft_ms

    Turn-end: driven by the built-in TurnTrackingObserver's `on_turn_ended` event,
    wired in bot.py via `register_turn_end(worker.turn_tracking_observer)`. The observer
    also exposes `_flush_turn()` directly so unit tests can exercise the output path.

    JSONL schema: {ts, turn_ms, stt_ms, llm_ttft_ms, tts_ttfb_ms}  — timing integers only.
    """

    def __init__(self, jsonl_path: str) -> None:
        """Create the observer.

        Args:
            jsonl_path: Path to the JSONL file where per-turn records are appended.
                        The parent directory is created if it does not exist.
        """
        super().__init__()
        self._jsonl_path = jsonl_path
        os.makedirs(os.path.dirname(os.path.abspath(jsonl_path)), exist_ok=True)

        # Per-turn accumulators (reset in _flush_turn)
        self._stt_ms: int = 0
        self._llm_ttft_ms: int = 0
        self._tts_ttfb_ms: int = 0
        # De-dup MetricsFrames (the same frame can be observed on multiple hops)
        self._frames_seen: set[int] = set()

    async def on_push_frame(self, data: FramePushed) -> None:
        """Route MetricsFrames into per-stage buckets.

        Wrapped in try/except so an unexpected frame shape can never kill the proxy
        task that drives this observer (see module docstring — worker_observer.py).
        """
        try:
            frame = data.frame
            if not isinstance(frame, MetricsFrame):
                return

            # De-dup: the same MetricsFrame may be pushed across multiple processors.
            frame_id = getattr(frame, "id", None)
            if frame_id is not None:
                if frame_id in self._frames_seen:
                    return
                self._frames_seen.add(frame_id)

            metrics = getattr(frame, "data", None) or []
            for metric in metrics:
                if not isinstance(metric, TTFBMetricsData):
                    continue
                # `metric.processor` is the SERVICE that produced the metric
                # (verified via official MetricsLogObserver). Far more reliable
                # than data.source.name, which is the pushing processor.
                proc = (getattr(metric, "processor", "") or "").lower()
                value = getattr(metric, "value", None)
                if value is None:
                    continue
                val_ms = int(value * 1000)
                # Order matters: check vendor names + the most specific service-type
                # tokens FIRST. Note "ElevenLabsTTSService".lower() == "elevenlabsttsservice"
                # which CONTAINS the substring "stt" (…lab[s+tts]ervice) — so a naive
                # `"stt" in proc` check would misroute TTS metrics into the STT bucket.
                # We therefore branch on the vendor names and the explicit "ttsservice"/
                # "sttservice"/"llmservice" tokens rather than bare "stt"/"tts"/"llm".
                if "elevenlabs" in proc or "ttsservice" in proc or proc.endswith("tts"):
                    self._tts_ttfb_ms = val_ms
                elif "deepgram" in proc or "sttservice" in proc or proc.endswith("stt"):
                    self._stt_ms = val_ms
                elif "anthropic" in proc or "llmservice" in proc or proc.endswith("llm"):
                    self._llm_ttft_ms = val_ms
        except Exception as exc:  # pragma: no cover - defensive guard
            # Never let an observer exception disable latency logging for the session.
            # Log the exception TYPE only (no frame contents / no secrets — V7).
            logger.debug(f"LatencyObserver.on_push_frame ignored {type(exc).__name__}")

    def register_turn_end(self, turn_tracking_observer) -> None:
        """Register `_on_turn_ended` on the pipeline's built-in TurnTrackingObserver.

        Args:
            turn_tracking_observer: The worker's `turn_tracking_observer` (created
                automatically when `enable_turn_tracking=True`, the default). If it
                is None (turn tracking disabled), this is a no-op and no per-turn
                line is emitted.
        """
        if turn_tracking_observer is None:
            logger.warning(
                "LatencyObserver: turn_tracking_observer is None — per-turn latency "
                "line will not be emitted. Ensure enable_turn_tracking=True."
            )
            return

        @turn_tracking_observer.event_handler("on_turn_ended")
        async def _on_turn_ended(observer, turn_number, duration_secs, was_interrupted):
            try:
                turn_ms = int(duration_secs * 1000)
                self._flush_turn(turn_ms=turn_ms)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.debug(f"LatencyObserver turn-end ignored {type(exc).__name__}")

    def _flush_turn(self, turn_ms: int) -> None:
        """Emit the console line + JSONL record and reset accumulators.

        Called by the `on_turn_ended` event handler at runtime and directly by unit
        tests (bypassing the async observer lifecycle) to exercise the output path.

        Args:
            turn_ms: Total turn duration in milliseconds.
        """
        line = (
            f"turn={turn_ms}ms | "
            f"stt={self._stt_ms} "
            f"llm_ttft={self._llm_ttft_ms} "
            f"tts_ttfb={self._tts_ttfb_ms}"
        )
        print(line)

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "turn_ms": turn_ms,
            "stt_ms": self._stt_ms,
            "llm_ttft_ms": self._llm_ttft_ms,
            "tts_ttfb_ms": self._tts_ttfb_ms,
        }
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        if turn_ms > LATENCY_BUDGET_MS:
            print(f"  [WARN] Turn exceeded 800ms budget! ({turn_ms}ms > {LATENCY_BUDGET_MS}ms)")

        # Reset per-turn accumulators
        self._stt_ms = 0
        self._llm_ttft_ms = 0
        self._tts_ttfb_ms = 0
