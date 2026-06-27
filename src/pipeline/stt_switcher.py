"""STT ServiceSwitcher — LazyWhisperSTTService + build_stt_switcher() (REL-03, D-12).

Provides:
- `LazyWhisperSTTService`: subclass of WhisperSTTService that defers model load to
  the first transcription call via asyncio.to_thread (D-12). No 1.5GB model download
  at startup; only activated when Deepgram fails.
- `WorkerRefHolder`: simple mutable holder for the PipelineWorker reference, used to
  break the circular dependency between pipeline build and worker creation.
- `build_stt_switcher(worker_ref_holder)`: assembles a ServiceSwitcher([deepgram, whisper],
  strategy=ServiceSwitcherStrategyFailover) and registers an on_service_switched handler
  that queues a courtesy TTSSpeakFrame through the worker.

Security (T-02-KEY): DEEPGRAM_API_KEY read only via os.getenv; never logged.
Security (V7 / T-03-LOG): ErrorFrame.error never logged; only sanitized service name used.

CLAUDE.md constraints:
- settings=ServiceClass.Settings(...) only — never flat kwargs.
- Model.LARGE_V3_TURBO + Language.IT for Italian; int8 for CPU efficiency (D-12).
- No keepalive on WhisperSTTService (no WebSocket — local inference only, Pitfall 7).
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

from pipecat.frames.frames import Frame, TTSSpeakFrame
from pipecat.pipeline.service_switcher import (
    ServiceSwitcher,
    ServiceSwitcherStrategyFailover,
)
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.whisper.stt import Model, WhisperSTTService
from pipecat.transcriptions.language import Language


# ---------------------------------------------------------------------------
# LazyWhisperSTTService (D-12 — no eager load at pipeline startup)
# ---------------------------------------------------------------------------

class LazyWhisperSTTService(WhisperSTTService):
    """faster-whisper Italian STT that defers model load to the first transcription.

    Standard WhisperSTTService calls self._load() in __init__, which downloads and
    loads the full WhisperModel (~1.5GB) synchronously — blocking bot startup for
    5-15 seconds on CPU (Pitfall 1). This subclass overrides _load() to a no-op so
    the model is not loaded at pipeline build time.

    On the first call to run_stt(), the model is loaded via asyncio.to_thread() so
    the event loop stays responsive. Subsequent calls reuse the loaded model.

    D-12 trade-off: first-switch latency (5-15s CPU, LARGE_V3_TURBO int8) is
    acceptable — degraded-mode call is preferable to dead-air (SC3). T-03-DOS
    accepted in the threat register.

    CLAUDE.md: always use settings=WhisperSTTService.Settings(...); never flat kwargs.
    CLAUDE.md: Model.LARGE_V3_TURBO + Language.IT; English-only models will mistranscribe.
    No keepalive= parameter (Whisper is local/offline — no WebSocket, Pitfall 7).
    """

    def _load(self) -> None:
        """No-op: model load is deferred to first run_stt() call (D-12).

        The parent's _load() calls WhisperModel(...) synchronously in __init__,
        blocking startup. Overriding to a no-op ensures self._model stays None
        until the first real transcription request arrives.
        """
        # Intentional no-op — self._model stays None (set to None by parent __init__
        # before calling _load). The actual load happens in run_stt() below.

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Lazy-load the Whisper model on first call, then transcribe.

        On first invocation (self._model is None), loads WhisperModel via
        asyncio.to_thread() so the event loop remains responsive during the
        potentially slow model load. Subsequent calls skip the load.

        Args:
            audio: Raw 16-bit PCM audio bytes.

        Yields:
            TranscriptionFrame on success, or ErrorFrame on failure.
        """
        if self._model is None:
            # Load model in a thread pool — keeps the async event loop unblocked.
            # First call may take 5-15s on CPU (LARGE_V3_TURBO ~1.5GB, int8).
            # D-12: trade-off accepted; degraded mode > dead-air (SC3, T-03-DOS).
            from faster_whisper import WhisperModel as _WhisperModel

            model_name = self._settings.model  # Model enum value or string
            self._model = await asyncio.to_thread(
                _WhisperModel,
                model_name,
                device=self._device,
                compute_type=self._compute_type,
            )

        # Delegate to the parent's transcription logic now that model is loaded.
        async for frame in super().run_stt(audio):
            yield frame


# ---------------------------------------------------------------------------
# WorkerRefHolder — breaks circular dep between pipeline build and worker
# ---------------------------------------------------------------------------

class WorkerRefHolder:
    """Mutable holder for the PipelineWorker reference.

    build_stt_switcher() is called during pipeline assembly, before the
    PipelineWorker exists. The worker is set after construction:

        holder = WorkerRefHolder()
        stt_switcher = build_stt_switcher(holder)
        worker = PipelineWorker(pipeline, observers=[...])
        holder.worker = worker  # resolve circular dep
    """

    def __init__(self) -> None:
        self.worker = None


# ---------------------------------------------------------------------------
# build_stt_switcher() — assembles ServiceSwitcher with failover strategy
# ---------------------------------------------------------------------------

# Italian courtesy phrase spoken while the STT switches (static, no PII, T-03-LOG).
_SWITCH_COURTESY_PHRASE = "Un momento, sto risolvendo un problema tecnico..."

# CLAUDE.md lock: nova-2 for Italian STT (same as DeepgramProvider in factory.py).
_DEEPGRAM_MODEL = "nova-2"


def build_stt_switcher(worker_ref_holder: WorkerRefHolder) -> ServiceSwitcher:
    """Build a ServiceSwitcher([deepgram, lazy_whisper], failover) for the STT slot.

    The switcher:
    - Primary: DeepgramSTTService(nova-2, Italian) — standard low-latency path.
    - Backup:  LazyWhisperSTTService(LARGE_V3_TURBO, Italian, int8) — lazy-loaded,
               activated automatically on persistent Deepgram failure (REL-03).
    - Strategy: ServiceSwitcherStrategyFailover — auto-switches on non-fatal ErrorFrame.
    - Event: on_service_switched queues a courtesy TTSSpeakFrame (static text, no PII).

    The `worker_ref_holder.worker` must be set to the PipelineWorker after it is
    created (same circular-dep pattern as ErrorFallbackObserver — see bot.py).

    Args:
        worker_ref_holder: A WorkerRefHolder whose .worker will be set post-construction.

    Returns:
        A configured ServiceSwitcher ready to slot into the pipeline in place of
        the standalone `stt` processor.

    Security (T-02-KEY): api_key sourced only from os.getenv("DEEPGRAM_API_KEY").
    """
    # --- Primary STT: Deepgram nova-2 Italian ---
    # Settings style (CLAUDE.md); api_key from env only (T-02-KEY).
    deepgram_stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramSTTService.Settings(
            model=_DEEPGRAM_MODEL,
            language="it",
            endpointing=400,        # Italian needs longer endpointing than English default
            interim_results=True,   # streaming transcription
            smart_format=False,     # cleaner raw text for LLM
            punctuate=True,
            numerals=True,          # spoken digits → numbers (phone capture)
        ),
    )

    # --- Backup STT: LazyWhisperSTTService (D-12 — no eager load) ---
    # device="cpu", compute_type="int8": balance between accuracy and memory/speed.
    # CLAUDE.md: LARGE_V3_TURBO + Language.IT; no keepalive (local/offline, Pitfall 7).
    whisper_stt = LazyWhisperSTTService(
        device="cpu",
        compute_type="int8",
        settings=WhisperSTTService.Settings(
            model=Model.LARGE_V3_TURBO,
            language=Language.IT,
            no_speech_prob=0.4,
        ),
    )

    # --- ServiceSwitcher with failover strategy ---
    stt_switcher = ServiceSwitcher(
        services=[deepgram_stt, whisper_stt],
        strategy_type=ServiceSwitcherStrategyFailover,
    )

    # --- on_service_switched: queue courtesy phrase through the worker ---
    # The worker_ref_holder.worker is None at build time; it is patched after the
    # PipelineWorker is created in bot.py (circular-dep pattern, same as error observer).
    @stt_switcher.strategy.event_handler("on_service_switched")
    async def _on_stt_switched(strategy, service) -> None:
        """Queue the STT-switch courtesy phrase when failover activates (SC3)."""
        # Security (V7 / T-03-LOG): no error details or API key logged.
        # Courtesy phrase is static — contains no PII or ErrorFrame.error content.
        if worker_ref_holder.worker is not None:
            await worker_ref_holder.worker.queue_frames([
                TTSSpeakFrame(
                    text=_SWITCH_COURTESY_PHRASE,
                    append_to_context=False,
                )
            ])

    return stt_switcher
