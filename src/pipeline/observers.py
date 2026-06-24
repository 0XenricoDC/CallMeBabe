"""Pipeline observers — non-intrusive metric collection and turn-end instrumentation.

Observers attach to `PipelineWorker` via `PipelineParams(observers=[...])` and receive
every frame that flows through the pipeline without being inserted in the hot-path.

Implements:
  - LatencyObserver: D-06 — per-turn console line + JSONL log (VOICE-04)
  - BotStoppedSpeakingFrame detection as turn-end signal (Open Question 1 resolution)

Security (T-03-LOG / T-03-JSONL):
  - LatencyObserver writes only timing integers + timestamp to the JSONL file — no PII.
  - No raw ErrorFrame or API-key values are logged here (see fallback.py for that boundary).
"""

from __future__ import annotations

import json
import os
import time

from pipecat.frames.frames import BotStoppedSpeakingFrame, MetricsFrame
from pipecat.metrics.metrics import TTFBMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed

LATENCY_BUDGET_MS = 800  # D-06: over-budget warning threshold


class LatencyObserver(BaseObserver):
    """Collect per-stage TTFB metrics and emit a human-readable line + JSONL on each turn.

    Metrics routing (Assumption A5 — source.name contains service class substring):
      - "deepgram" or "stt" in source.name → stt_ms
      - "anthropic" or "llm" in source.name → llm_ttft_ms
      - "elevenlabs" or "tts" in source.name → tts_ttfb_ms

    Turn-end signal (Open Question 1 resolution): BotStoppedSpeakingFrame marks the
    moment the bot finishes speaking — a reliable proxy for "turn complete" that does
    not require a dedicated `on_turn_ended` hook (which is absent from BaseObserver 1.4.0).
    The wall-clock elapsed from the first MetricsFrame in the turn is used as turn_ms.

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
        self._turn_start: float | None = None  # monotonic start of current turn

    async def on_push_frame(self, data: FramePushed) -> None:
        """Route MetricsFrames into per-stage buckets; detect turn end."""
        frame = data.frame

        # --- Accumulate per-stage TTFB from MetricsFrame ---
        if isinstance(frame, MetricsFrame):
            if self._turn_start is None:
                self._turn_start = time.monotonic()

            # `data.source` is a FrameProcessor object; use .name for routing.
            src_name: str = getattr(data.source, "name", "") or ""
            src_lower = src_name.lower()

            for metric in frame.data:
                if not isinstance(metric, TTFBMetricsData):
                    continue
                val_ms = int(metric.value * 1000)
                if "deepgram" in src_lower or "stt" in src_lower:
                    self._stt_ms = val_ms
                elif "anthropic" in src_lower or "llm" in src_lower:
                    self._llm_ttft_ms = val_ms
                elif "elevenlabs" in src_lower or "tts" in src_lower:
                    self._tts_ttfb_ms = val_ms

        # --- Use BotStoppedSpeakingFrame as turn-end signal (Open Question 1) ---
        elif isinstance(frame, BotStoppedSpeakingFrame):
            if self._turn_start is not None:
                elapsed_ms = int((time.monotonic() - self._turn_start) * 1000)
            else:
                # Fallback: no turn start recorded (edge case at startup)
                elapsed_ms = 0
            self._flush_turn(turn_ms=elapsed_ms)

    def _flush_turn(self, turn_ms: int) -> None:
        """Emit the console line + JSONL record and reset accumulators.

        This method is also called directly by unit tests (bypassing the async
        observer lifecycle) to exercise the output path in isolation.

        Args:
            turn_ms: Total turn duration in milliseconds (wall-clock or provided by tests).
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
        self._turn_start = None
