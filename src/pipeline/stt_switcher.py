"""STT ServiceSwitcher — FailoverDeepgramSTTService + LazyWhisperSTTService + build_stt_switcher().

Plans 03-04 and 03-06 (REL-02, REL-03, SC3, SC4).

Provides:
- `FailoverDeepgramSTTService`: DeepgramSTTService subclass with a connection-health monitor
  task that surfaces connect-time 401/auth failures (and mid-call drops) via push_error so
  the ServiceSwitcher can fail over to faster-whisper (SC3). Previously, the
  _connection_handler catch-all swallowed these errors and retried silently — no ErrorFrame
  was produced and failover never fired.
- `LazyWhisperSTTService`: subclass of WhisperSTTService that defers model load to
  the first transcription call via asyncio.to_thread (D-12). Load failures are yielded as
  non-fatal ErrorFrames (not raised) so they surface symmetrically to the switcher (SC4).
- `WorkerRefHolder`: mutable holder for PipelineWorker + FlowManager references, used to
  break the circular dependency between pipeline build and worker/flow creation.
- `build_stt_switcher(worker_ref_holder)`: assembles a ServiceSwitcher([deepgram, whisper],
  strategy=ServiceSwitcherStrategyFailover) with:
    - on_service_switched: queues courtesy TTSSpeakFrame (SC3, call continues)
    - SC4 escalation: after _ESCALATION_THRESHOLD switches, sets outcome='fallito' + queues
      EndWorkerFrame exactly once (shared guard via flow_manager.state['_stt_escalated']).

Security (T-02-KEY): DEEPGRAM_API_KEY read only via os.getenv; never logged.
Security (V7 / T-03-LOG): ErrorFrame.error and raw provider error strings never logged;
  only static sanitized strings used in push_error and courtesy phrases.

CLAUDE.md constraints:
- settings=ServiceClass.Settings(...) only — never flat kwargs.
- Model.LARGE_V3_TURBO + Language.IT for Italian; English-only models will mistranscribe.
- No keepalive on WhisperSTTService (no WebSocket — local inference only, Pitfall 7).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import AsyncGenerator

from loguru import logger

from pipecat.frames.frames import EndWorkerFrame, ErrorFrame, Frame, TTSSpeakFrame
from pipecat.pipeline.service_switcher import (
    ServiceSwitcher,
    ServiceSwitcherStrategyFailover,
)
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.whisper.stt import Model, WhisperSTTService
from pipecat.transcriptions.language import Language


# ---------------------------------------------------------------------------
# Health-monitor constants (importable for test monkeypatching — D-12/T-03-DOS)
# ---------------------------------------------------------------------------

# Seconds to wait after start() before the first health check.
# Grace period lets the connection attempt proceed before we declare it dead.
# Default 3.0s; tests monkeypatch to a tiny value (0.01s) for speed.
_STT_HEALTH_GRACE: float = 3.0

# Seconds between health checks once the grace period has elapsed.
# On each tick, if _connection_ready is still not set, push_error is called
# so the ServiceSwitcher re-fails-over or keeps the current active service.
# Default 2.0s; tests monkeypatch to a tiny value (0.01s) for speed.
_STT_ERROR_INTERVAL: float = 2.0


# ---------------------------------------------------------------------------
# FailoverDeepgramSTTService (SC3/SC4 real-error-path fix — 03-06)
# ---------------------------------------------------------------------------

class FailoverDeepgramSTTService(DeepgramSTTService):
    """DeepgramSTTService with a connection-health monitor that surfaces failures via push_error.

    ROOT CAUSE (verified in pipecat 1.4.0 deepgram/stt.py):
    `_connection_handler()` catches connect-time errors (e.g. 401 invalid key) in a broad
    `except Exception as e: logger.warning(...)` block and retries forever WITHOUT calling
    push_error. So no ErrorFrame is produced — the ServiceSwitcher never fails over and the
    ErrorFallbackObserver never escalates, leaving the caller in dead air (SC3/SC4 gap).

    FIX: override start()/stop()/cancel() to run a background task that polls
    `_connection_ready` (the asyncio.Event set by the parent when the WebSocket connect
    succeeds, cleared on disconnect/retry). While it is persistently NOT set, we call
    `push_error(..., fatal=False)` on an interval so a non-fatal ErrorFrame (processor=self)
    is pushed UPSTREAM, reaching `ServiceSwitcher.push_frame → strategy.handle_error`.

    Interval-based (not one-shot): if round-robin returns to a still-dead Deepgram, the
    monitor keeps firing push_error on each tick so failover can fire again.

    Security (T-02-KEY): api_key read only via os.getenv; never included in push_error.
    Security (V7 / T-03-LOG): push_error message is a static sanitized string — no key,
        no raw exception, no provider error detail.
    CLAUDE.md: settings=DeepgramSTTService.Settings(...) only; nova-2 + Italian.
    """

    # Ref to the ServiceSwitcher strategy, wired by build_stt_switcher() after the
    # switcher exists (SC3 live-bug fix, 2026-07-04). While another service is active,
    # the monitor stays silent: its ErrorFrames would be dropped by the switcher filter
    # anyway, but ErrorFallbackObserver sees every push (observers fire before
    # filtering) and would escalate + EndWorkerFrame a call whose failover SUCCEEDED.
    # None (e.g. standalone use) → gate disabled, monitor always pushes.
    _switcher_strategy = None

    async def start(self, frame) -> None:  # frame: StartFrame
        """Start Deepgram STT and launch the connection-health monitor task.

        The monitor runs as a background task via self.create_task() so the event
        loop stays responsive. It is cancelled in stop()/cancel().
        """
        await super().start(frame)
        self._monitor_task = self.create_task(self._failover_monitor())

    async def stop(self, frame) -> None:  # frame: EndFrame
        """Stop Deepgram STT and cancel the health-monitor task."""
        if getattr(self, "_monitor_task", None) is not None:
            await self.cancel_task(self._monitor_task)
            self._monitor_task = None
        await super().stop(frame)

    async def cancel(self, frame) -> None:  # frame: CancelFrame
        """Cancel Deepgram STT and cancel the health-monitor task."""
        if getattr(self, "_monitor_task", None) is not None:
            await self.cancel_task(self._monitor_task)
            self._monitor_task = None
        await super().cancel(frame)

    async def _failover_monitor(self) -> None:
        """Monitor _connection_ready; call push_error when persistently not ready.

        Algorithm:
        1. Wait _STT_HEALTH_GRACE seconds (give the initial connect attempt time).
        2. Loop every _STT_ERROR_INTERVAL seconds:
           - If _connection_ready.is_set(): connection is up — no action.
           - If NOT set: connection is down (covers 401/auth and mid-call drops).
             Call push_error with a static sanitized message so the switcher can
             fail over.

        The loop is cancelled when stop() or cancel() is called.

        Security (T-02-KEY/V7/T-03-LOG): error_msg is a static string — no API key,
            no provider error text, no exception detail.
        """
        await asyncio.sleep(_STT_HEALTH_GRACE)
        while True:
            if not self._connection_ready.is_set() and self._is_active_stt():
                # Static message only — NEVER log the api_key or raw error (T-02-KEY/V7).
                await self.push_error("Deepgram STT connection unavailable", fatal=False)
            await asyncio.sleep(_STT_ERROR_INTERVAL)

    def _is_active_stt(self) -> bool:
        """Return True if this service is the switcher's active STT (or no switcher wired).

        Evaluated per monitor tick: after failover to whisper this returns False (monitor
        silent — no stale ErrorFrame spam toward ErrorFallbackObserver, SC3); if the
        strategy round-robins back to a still-dead Deepgram it returns True again, so the
        monitor resumes push_error and failover/SC4 escalation keep working.
        """
        strategy = getattr(self, "_switcher_strategy", None)
        return strategy is None or strategy.active_service is self


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

    If the model load fails (e.g. CUDA unavailable, disk error), an ErrorFrame is
    YIELDED rather than raised. This makes the failure visible to process_generator
    (which surfaces yielded ErrorFrames via push_error_frame to the ServiceSwitcher),
    enabling symmetric SC4 escalation when BOTH STT services are down.

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

        If the model load fails for any reason (CUDA unavailable, disk error, etc.),
        a non-fatal ErrorFrame is YIELDED (not raised) so process_generator in
        ai_service.py can surface it to the ServiceSwitcher via push_error_frame.
        This makes whisper load failures symmetric with Deepgram connect failures
        for SC4 escalation when both STT services are down.

        Security (V7 / T-03-LOG): error string in the yielded ErrorFrame is a static
            sanitized string — no exception detail, no raw error message.

        Args:
            audio: Raw 16-bit PCM audio bytes.

        Yields:
            TranscriptionFrame on success, or non-fatal ErrorFrame on load failure.
        """
        if self._model is None:
            # Load model in a thread pool — keeps the async event loop unblocked.
            # First call may take 5-15s on CPU (LARGE_V3_TURBO ~1.5GB, int8).
            # D-12: trade-off accepted; degraded mode > dead-air (SC3, T-03-DOS).
            # Live-debug 2026-07-04: the load may contact HuggingFace Hub — with a
            # flaky network it can stall here, so log start/end for visibility.
            logger.debug("[WHISPER] first request — loading model (10-20s on CPU)...")
            t0 = time.monotonic()
            try:
                from faster_whisper import WhisperModel as _WhisperModel

                model_name = self._settings.model  # Model enum value or string
                self._model = await asyncio.to_thread(
                    _WhisperModel,
                    model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                )
            except Exception:
                # Security (V7/T-03-LOG): do NOT log the raw exception — it may contain
                # system paths, stack traces, or other non-PII-but-sensitive detail.
                # Yield a non-fatal ErrorFrame so process_generator surfaces it to the
                # ServiceSwitcher (handle_error path) rather than crashing the generator.
                logger.warning("[WHISPER] model load FAILED after {:.1f}s — yielding ErrorFrame",
                               time.monotonic() - t0)
                yield ErrorFrame(error="Whisper STT unavailable", fatal=False)
                return
            logger.debug("[WHISPER] model ready in {:.1f}s", time.monotonic() - t0)

        # Delegate to the parent's transcription logic now that model is loaded.
        # V7/T-03-LOG: log only sizes/timing — never the transcribed text (PII).
        logger.debug("[WHISPER] transcribing segment ({} bytes)...", len(audio))
        t1 = time.monotonic()
        async for frame in super().run_stt(audio):
            yield frame
        logger.debug("[WHISPER] segment done in {:.1f}s", time.monotonic() - t1)


# ---------------------------------------------------------------------------
# WorkerRefHolder — breaks circular dep between pipeline build and worker/flow
# ---------------------------------------------------------------------------

class WorkerRefHolder:
    """Mutable holder for PipelineWorker and FlowManager references.

    build_stt_switcher() is called during pipeline assembly, before the
    PipelineWorker or FlowManager exist. Both references are set after construction:

        holder = WorkerRefHolder()
        stt_switcher = build_stt_switcher(holder)
        worker = PipelineWorker(pipeline, observers=[...])
        holder.worker = worker              # resolve worker circular dep
        flow_manager = await setup_flow(...)
        holder.flow_manager = flow_manager  # resolve flow_manager circular dep (SC4)

    Plan 03-06 addition:
    - `flow_manager`: set by bot.py after FlowManager creation so the SC4 escalation
      handler can set flow_manager.state['outcome']='fallito' and the shared guard
      flow_manager.state['_stt_escalated'] = True.
    """

    def __init__(self) -> None:
        self.worker = None
        # REL-02/SC4 (Plan 03-06): set by bot.py after FlowManager creation.
        # None until patched; on_service_switched guard checks for None before use.
        self.flow_manager = None


# ---------------------------------------------------------------------------
# build_stt_switcher() — assembles ServiceSwitcher with failover strategy + SC4
# ---------------------------------------------------------------------------

# Italian courtesy phrase spoken while the STT switches (static, no PII, T-03-LOG).
_SWITCH_COURTESY_PHRASE = "Un momento, sto risolvendo un problema tecnico..."

# CLAUDE.md lock: nova-2 for Italian STT (same as DeepgramProvider in factory.py).
_DEEPGRAM_MODEL = "nova-2"


def build_stt_switcher(worker_ref_holder: WorkerRefHolder) -> ServiceSwitcher:
    """Build a ServiceSwitcher([failover_deepgram, lazy_whisper], failover) for the STT slot.

    The switcher:
    - Primary: FailoverDeepgramSTTService(nova-2, Italian) — adds connection-health monitor
               that surfaces connect-time 401/auth failures via push_error (SC3 real path).
    - Backup:  LazyWhisperSTTService(LARGE_V3_TURBO, Italian, int8) — lazy-loaded,
               activated automatically on persistent Deepgram failure (REL-03/D-12).
               Load failures yield non-fatal ErrorFrames (SC4 symmetric error surfacing).
    - Strategy: ServiceSwitcherStrategyFailover — auto-switches on non-fatal ErrorFrame.
    - Events:
        on_service_switched (SC3): queues courtesy TTSSpeakFrame (call continues).
        on_service_switched (SC4): after _ESCALATION_THRESHOLD switches, sets
            outcome='fallito', queues EndWorkerFrame exactly once (shared guard via
            flow_manager.state['_stt_escalated'] so observer and switcher don't both fire).

    The `worker_ref_holder.worker` and `worker_ref_holder.flow_manager` must be set after
    the PipelineWorker and FlowManager are created in bot.py (same circular-dep pattern
    as ErrorFallbackObserver — see bot.py for the wiring).

    Args:
        worker_ref_holder: A WorkerRefHolder whose .worker and .flow_manager will be
            set post-construction.

    Returns:
        A configured ServiceSwitcher ready to slot into the pipeline in place of
        the standalone `stt` processor.

    Security (T-02-KEY): api_key sourced only from os.getenv("DEEPGRAM_API_KEY").
    """
    # Import escalation constants from fallback so D-13 value stays single-sourced.
    from src.pipeline.fallback import _ESCALATION_PHRASE, _ESCALATION_THRESHOLD

    # --- Primary STT: FailoverDeepgramSTTService (03-06: wraps Deepgram with health monitor) ---
    # Settings style (CLAUDE.md); api_key from env only (T-02-KEY).
    deepgram_stt = FailoverDeepgramSTTService(
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

    # SC3 live-bug fix (2026-07-04): the health monitor gates push_error on being the
    # active STT — see FailoverDeepgramSTTService._is_active_stt for the rationale.
    deepgram_stt._switcher_strategy = stt_switcher.strategy

    # --- Switch counter for SC4 escalation (lives in closure) ---
    # One escalation per call: the shared guard in flow_manager.state prevents both
    # the switcher and ErrorFallbackObserver from firing EndWorkerFrame (T-03-FIN).
    _switch_count = [0]  # mutable via list to allow closure mutation in Python

    # --- on_service_switched: SC3 courtesy phrase + SC4 escalation ---
    # The worker_ref_holder refs are None at build time; they are patched after the
    # PipelineWorker and FlowManager are created in bot.py (circular-dep pattern).
    @stt_switcher.strategy.event_handler("on_service_switched")
    async def _on_stt_switched(strategy, service) -> None:
        """Handle STT service switch: SC3 courtesy phrase + SC4 escalation.

        SC3 (first switch): queue the courtesy phrase so the caller hears something
        instead of dead-air while faster-whisper loads. The call continues.

        SC4 (repeated switches): when all STT services are flapping/dead (switch
        count reaches _ESCALATION_THRESHOLD), escalate exactly once — set
        outcome='fallito', queue the transfer phrase and EndWorkerFrame. The
        shared guard (flow_manager.state['_stt_escalated']) prevents a double-fire
        if ErrorFallbackObserver also reaches its threshold independently.

        Security (V7 / T-03-LOG): no error details or API key logged; all phrases
            are static strings with no ErrorFrame.error content.
        """
        _switch_count[0] += 1

        # SC3: ALWAYS queue courtesy phrase on every switch so the caller hears
        # something while the backup service activates.
        if worker_ref_holder.worker is not None:
            await worker_ref_holder.worker.queue_frames([
                TTSSpeakFrame(
                    text=_SWITCH_COURTESY_PHRASE,
                    append_to_context=False,
                )
            ])

        # SC4: when switches reach the threshold, escalate exactly once.
        if _switch_count[0] >= _ESCALATION_THRESHOLD:
            fm = worker_ref_holder.flow_manager
            if fm is not None and not fm.state.get("_stt_escalated", False):
                # Set shared guard FIRST so the observer cannot also fire (T-03-FIN).
                fm.state["outcome"] = "fallito"
                fm.state["_stt_escalated"] = True
                # Queue escalation phrase + clean shutdown (SC4 — no long dead-air).
                if worker_ref_holder.worker is not None:
                    await worker_ref_holder.worker.queue_frames([
                        TTSSpeakFrame(
                            text=_ESCALATION_PHRASE,
                            append_to_context=False,
                        ),
                        EndWorkerFrame(),
                    ])

    return stt_switcher
