"""Tests for STT ServiceSwitcher + LazyWhisperSTTService (REL-03 / Plans 03-04, 03-06).

Plan 03-04 coverage:
- LazyWhisperSTTService: _model is None after construction (no eager load).
- build_stt_switcher(): returns a ServiceSwitcher with two services and a failover strategy.

Plan 03-06 coverage (gap closure SC3/SC4):
- FailoverDeepgramSTTService: subclass of DeepgramSTTService with connection-health monitor.
- Health monitor calls push_error when _connection_ready is persistently not set.
- Real-error-path failover: ErrorFrame from active service triggers switch + courtesy phrase.
- LazyWhisperSTTService.run_stt yields ErrorFrame (not raises) on model-load failure.
- SC4 escalation: repeated on_service_switched → outcome='fallito' + single EndWorkerFrame.
- SC4 idempotency: second batch of switches queues no further EndWorkerFrame.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Task 1: LazyWhisperSTTService — no eager model load (D-12)
# ---------------------------------------------------------------------------

def test_lazy_whisper_no_eager_load():
    """D-12 / REL-03: LazyWhisperSTTService must NOT load the Whisper model at init.

    The _model attribute must be None immediately after construction so the
    expensive (~1.5GB) model load is deferred to the first transcription call.
    """
    from src.pipeline.stt_switcher import LazyWhisperSTTService
    from pipecat.services.whisper.stt import Model
    from pipecat.transcriptions.language import Language

    # Patch WhisperModel so even if _load() were called it wouldn't block.
    with patch("faster_whisper.WhisperModel"):
        svc = LazyWhisperSTTService(
            device="cpu",
            compute_type="int8",
            settings=LazyWhisperSTTService.Settings(
                model=Model.LARGE_V3_TURBO,
                language=Language.IT,
                no_speech_prob=0.4,
            ),
        )

    # _model must be None — no eager load occurred.
    assert svc._model is None, (
        "LazyWhisperSTTService._model must be None after construction — "
        "the model must not be loaded at startup (D-12)."
    )


# ---------------------------------------------------------------------------
# Task 1: build_stt_switcher — ServiceSwitcher with failover strategy
# ---------------------------------------------------------------------------

def test_build_stt_switcher_returns_service_switcher():
    """REL-03: build_stt_switcher() must return a ServiceSwitcher instance.

    Plan 03-06: patch FailoverDeepgramSTTService (not DeepgramSTTService) since
    build_stt_switcher now constructs the subclass.
    """
    from pipecat.pipeline.service_switcher import ServiceSwitcher

    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    with (
        patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockDeepgram,
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
    ):
        MockDeepgram.return_value = MagicMock(name="FailoverDeepgramSTT")
        MockWhisper.return_value = MagicMock(name="LazyWhisperSTT")

        stt_switcher = build_stt_switcher(holder)

    assert isinstance(stt_switcher, ServiceSwitcher), (
        "build_stt_switcher() must return a ServiceSwitcher instance (REL-03)."
    )


def test_build_stt_switcher_has_two_services():
    """REL-03: build_stt_switcher() must return a switcher with exactly two services.

    Plan 03-06: patch FailoverDeepgramSTTService (not DeepgramSTTService).
    """
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    with (
        patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockDeepgram,
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
    ):
        mock_deepgram = MagicMock(name="FailoverDeepgramSTT")
        mock_whisper = MagicMock(name="LazyWhisperSTT")
        MockDeepgram.return_value = mock_deepgram
        MockWhisper.return_value = mock_whisper

        stt_switcher = build_stt_switcher(holder)

    assert len(stt_switcher._services) == 2, (
        "ServiceSwitcher must have exactly two services: [failover_deepgram, lazy_whisper] (REL-03)."
    )


def test_build_stt_switcher_strategy_is_failover():
    """REL-03: build_stt_switcher() must use ServiceSwitcherStrategyFailover.

    Plan 03-06: patch FailoverDeepgramSTTService (not DeepgramSTTService).
    """
    from pipecat.pipeline.service_switcher import ServiceSwitcherStrategyFailover

    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    with (
        patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockDeepgram,
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
    ):
        MockDeepgram.return_value = MagicMock(name="FailoverDeepgramSTT")
        MockWhisper.return_value = MagicMock(name="LazyWhisperSTT")

        stt_switcher = build_stt_switcher(holder)

    assert isinstance(stt_switcher._strategy, ServiceSwitcherStrategyFailover), (
        "ServiceSwitcher strategy must be ServiceSwitcherStrategyFailover (REL-03)."
    )


def test_build_stt_switcher_deepgram_api_key_from_env():
    """Security (T-02-KEY): FailoverDeepgramSTTService must receive api_key from os.getenv only.

    Plan 03-06: patching FailoverDeepgramSTTService instead of DeepgramSTTService since
    build_stt_switcher now constructs the subclass. The api_key is still sourced from
    os.getenv — this test verifies that the env-read path is unchanged.
    """
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()
    captured_deepgram_kwargs = {}

    def _capture_deepgram(*args, **kwargs):
        captured_deepgram_kwargs.update(kwargs)
        m = MagicMock(name="FailoverDeepgramSTT")
        return m

    with (
        patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService", side_effect=_capture_deepgram),
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
        patch("src.pipeline.stt_switcher.os.getenv", return_value="test-dg-key") as mock_env,
    ):
        MockWhisper.return_value = MagicMock(name="LazyWhisperSTT")
        build_stt_switcher(holder)

    assert "api_key" in captured_deepgram_kwargs, (
        "FailoverDeepgramSTTService must receive api_key kwarg (T-02-KEY)."
    )
    assert captured_deepgram_kwargs["api_key"] == "test-dg-key", (
        "api_key must come from os.getenv (not hardcoded)."
    )


# ---------------------------------------------------------------------------
# Helper: spy worker (mirrors _SpyWorker in test_fallback.py)
# ---------------------------------------------------------------------------

class _SpyWorker:
    """Captures frames queued via queue_frames() or queue_frame()."""

    def __init__(self):
        self.queued: list = []

    async def queue_frames(self, frames):
        self.queued.extend(frames)

    async def queue_frame(self, frame):
        self.queued.append(frame)


# ---------------------------------------------------------------------------
# Plan 03-06 / Task 1 (RED): FailoverDeepgramSTTService class checks
# ---------------------------------------------------------------------------

def test_failover_deepgram_stt_service_class_exists():
    """FailoverDeepgramSTTService must exist and be a DeepgramSTTService subclass (SC3/SC4).

    RED: ImportError — class does not exist yet.
    GREEN: class added in stt_switcher.py.
    """
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from src.pipeline.stt_switcher import FailoverDeepgramSTTService  # RED: ImportError
    assert issubclass(FailoverDeepgramSTTService, DeepgramSTTService), (
        "FailoverDeepgramSTTService must subclass DeepgramSTTService (REL-03)."
    )


def test_stt_health_monitor_constants_exist():
    """_STT_HEALTH_GRACE and _STT_ERROR_INTERVAL must be importable module constants.

    Required for test monkeypatching and for the health-monitor loop (SC3/D-12).
    RED: AttributeError — constants do not exist yet.
    GREEN: constants added to stt_switcher.py with positive values.
    """
    import src.pipeline.stt_switcher as mod
    assert hasattr(mod, "_STT_HEALTH_GRACE"), (
        "_STT_HEALTH_GRACE constant missing from stt_switcher (needed for health monitor grace period)."
    )
    assert hasattr(mod, "_STT_ERROR_INTERVAL"), (
        "_STT_ERROR_INTERVAL constant missing from stt_switcher (needed for health monitor interval)."
    )
    assert mod._STT_HEALTH_GRACE > 0, "_STT_HEALTH_GRACE must be a positive number."
    assert mod._STT_ERROR_INTERVAL > 0, "_STT_ERROR_INTERVAL must be a positive number."


def test_failover_monitor_calls_push_error_when_connection_not_ready():
    """Health monitor: push_error called when _connection_ready stays unset past grace.

    When Deepgram fails to connect (e.g. 401 invalid key), _connection_ready is never set.
    The health-monitor task must detect this and call push_error so the ServiceSwitcher
    can fail over to faster-whisper (SC3 real-error path).

    Security (T-02-KEY/V7/T-03-LOG): the error message is static — no key, no raw exception.

    RED: ImportError on FailoverDeepgramSTTService.
    GREEN: _failover_monitor() coroutine calls push_error within grace+interval seconds.
    """
    from src.pipeline.stt_switcher import FailoverDeepgramSTTService  # RED: ImportError
    import src.pipeline.stt_switcher as mod

    # Create a bare instance without running __init__ so no network calls are made.
    svc = object.__new__(FailoverDeepgramSTTService)
    svc._connection_ready = asyncio.Event()  # intentionally NOT set (simulates 401 case)
    push_error_spy = AsyncMock()
    svc.push_error = push_error_spy

    async def _run():
        # Monkeypatch constants to tiny values so test runs in < 0.2s
        with patch.object(mod, "_STT_HEALTH_GRACE", 0.01), \
             patch.object(mod, "_STT_ERROR_INTERVAL", 0.01):
            task = asyncio.create_task(svc._failover_monitor())
            await asyncio.sleep(0.08)  # wait for grace + several intervals
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())
    push_error_spy.assert_called(), (
        "_failover_monitor must call push_error when _connection_ready is not set (SC3 real path)."
    )


def test_failover_monitor_silent_when_not_active_service():
    """SC3 live-bug regression: monitor must NOT push_error when Deepgram is not active.

    Live failure (2026-07-04): with an invalid Deepgram key, the monitor kept calling
    push_error every _STT_ERROR_INTERVAL even AFTER the switcher had failed over to
    whisper. The ServiceSwitcher filter drops those frames, but ErrorFallbackObserver
    sees every push (observers fire before filtering) — after 3 courtesy cycles it
    escalated with EndWorkerFrame and killed a call whose failover had SUCCEEDED.

    Contract: when a switcher strategy is wired (svc._switcher_strategy) and its
    active_service is NOT this instance, the monitor must stay silent.

    RED: monitor has no active-service gate — push_error fires anyway.
    GREEN: monitor checks the strategy and skips push_error while inactive.
    """
    from src.pipeline.stt_switcher import FailoverDeepgramSTTService
    import src.pipeline.stt_switcher as mod

    svc = object.__new__(FailoverDeepgramSTTService)
    svc._connection_ready = asyncio.Event()  # NOT set — connection is down
    push_error_spy = AsyncMock()
    svc.push_error = push_error_spy

    # Strategy says another service (whisper) is active.
    strategy = MagicMock(name="strategy")
    strategy.active_service = MagicMock(name="whisper")
    svc._switcher_strategy = strategy

    async def _run():
        with patch.object(mod, "_STT_HEALTH_GRACE", 0.01), \
             patch.object(mod, "_STT_ERROR_INTERVAL", 0.01):
            task = asyncio.create_task(svc._failover_monitor())
            await asyncio.sleep(0.08)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())
    push_error_spy.assert_not_called(), (
        "_failover_monitor must NOT push_error while another service is active — "
        "stale error spam drives ErrorFallbackObserver to kill a healthy failover call (SC3)."
    )


def test_failover_monitor_resumes_when_service_active_again():
    """SC4 preserved: when the strategy re-activates Deepgram, the monitor pushes again.

    Round-robin can switch BACK to a still-dead Deepgram (whisper error → next service).
    The monitor must then resume push_error so the switcher can fail over again and the
    SC4 switch counter keeps climbing toward escalation.

    GREEN: gate is evaluated per tick — active again → push_error fires.
    """
    from src.pipeline.stt_switcher import FailoverDeepgramSTTService
    import src.pipeline.stt_switcher as mod

    svc = object.__new__(FailoverDeepgramSTTService)
    svc._connection_ready = asyncio.Event()  # NOT set
    push_error_spy = AsyncMock()
    svc.push_error = push_error_spy

    strategy = MagicMock(name="strategy")
    strategy.active_service = svc  # Deepgram is the active service
    svc._switcher_strategy = strategy

    async def _run():
        with patch.object(mod, "_STT_HEALTH_GRACE", 0.01), \
             patch.object(mod, "_STT_ERROR_INTERVAL", 0.01):
            task = asyncio.create_task(svc._failover_monitor())
            await asyncio.sleep(0.08)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())
    push_error_spy.assert_called(), (
        "_failover_monitor must resume push_error when the strategy re-activates this service."
    )


# ---------------------------------------------------------------------------
# Plan 03-06 / Task 1 (RED): build_stt_switcher uses FailoverDeepgramSTTService
# ---------------------------------------------------------------------------

def test_build_stt_switcher_uses_failover_deepgram_stt_service():
    """build_stt_switcher must use FailoverDeepgramSTTService as the primary STT (SC3/SC4).

    RED: AttributeError — patching FailoverDeepgramSTTService fails (not in module yet).
    GREEN: build_stt_switcher constructs FailoverDeepgramSTTService (not plain DeepgramSTTService).
    """
    from pipecat.pipeline.service_switcher import ServiceSwitcher
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    # In RED: patch raises AttributeError because FailoverDeepgramSTTService doesn't exist.
    with patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockFDSS, \
         patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockLWSS:
        fake_deepgram = MagicMock(name="FailoverDeepgramSTT")
        fake_deepgram.queue_frame = AsyncMock()
        fake_whisper = MagicMock(name="LazyWhisperSTT")
        fake_whisper.queue_frame = AsyncMock()
        MockFDSS.return_value = fake_deepgram
        MockLWSS.return_value = fake_whisper

        switcher = build_stt_switcher(holder)

    assert MockFDSS.called, (
        "build_stt_switcher must construct FailoverDeepgramSTTService (SC3/SC4 — not plain DeepgramSTTService)."
    )
    assert isinstance(switcher, ServiceSwitcher)


def test_build_stt_switcher_wires_strategy_ref_into_deepgram():
    """build_stt_switcher must give the Deepgram service a ref to the switcher strategy.

    The FailoverDeepgramSTTService health monitor needs strategy.active_service to
    know whether it is still the active STT (SC3 live-bug fix — see
    test_failover_monitor_silent_when_not_active_service).

    RED: build_stt_switcher never sets _switcher_strategy.
    GREEN: deepgram_stt._switcher_strategy is stt_switcher.strategy after build.
    """
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    with patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockFDSS, \
         patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockLWSS:
        fake_deepgram = MagicMock(name="fake_deepgram")
        fake_deepgram.queue_frame = AsyncMock()
        fake_whisper = MagicMock(name="fake_whisper")
        fake_whisper.queue_frame = AsyncMock()
        MockFDSS.return_value = fake_deepgram
        MockLWSS.return_value = fake_whisper

        stt_switcher = build_stt_switcher(holder)

    assert fake_deepgram._switcher_strategy is stt_switcher.strategy, (
        "build_stt_switcher must wire the switcher strategy into the Deepgram service "
        "so the health monitor can gate push_error on active_service (SC3)."
    )


def test_real_errorframe_path_triggers_failover_and_courtesy_phrase():
    """SC3: ErrorFrame from active service (real error path) → switch + courtesy phrase.

    This exercises the real ServiceSwitcher.push_frame → strategy.handle_error path
    (not a simulated switch). Replaces the prior simulated-switch-only coverage.

    RED: AttributeError — patching FailoverDeepgramSTTService fails.
    GREEN: strategy.handle_error fires on_service_switched; handler queues courtesy phrase.
    """
    from pipecat.frames.frames import ErrorFrame, TTSSpeakFrame
    from src.pipeline.stt_switcher import WorkerRefHolder, _SWITCH_COURTESY_PHRASE, build_stt_switcher

    holder = WorkerRefHolder()
    spy = _SpyWorker()
    holder.worker = spy

    # In RED: patch raises AttributeError.
    with patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockFDSS, \
         patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockLWSS:
        fake_deepgram = MagicMock(name="fake_deepgram")
        fake_deepgram.name = "FailoverDeepgramSTT"
        fake_deepgram.queue_frame = AsyncMock()
        fake_whisper = MagicMock(name="fake_whisper")
        fake_whisper.name = "LazyWhisperSTT"
        fake_whisper.queue_frame = AsyncMock()
        MockFDSS.return_value = fake_deepgram
        MockLWSS.return_value = fake_whisper

        stt_switcher = build_stt_switcher(holder)

    strategy = stt_switcher.strategy
    active = strategy.active_service  # fake_deepgram

    # Feed a non-fatal error from the ACTIVE service — the REAL error path the switcher uses.
    err = ErrorFrame(error="401 auth failed", fatal=False)
    err.processor = active

    async def _run():
        await strategy.handle_error(err)

    asyncio.run(_run())

    # Active service must have switched to whisper
    assert strategy.active_service is not active, (
        "ServiceSwitcher must switch active service on non-fatal ErrorFrame from active service (SC3)."
    )
    # Courtesy phrase must have been queued (SC3)
    tts_frames = [f for f in spy.queued if isinstance(f, TTSSpeakFrame)]
    assert len(tts_frames) >= 1, (
        "on_service_switched handler must queue a courtesy TTSSpeakFrame (SC3)."
    )
    assert any(_SWITCH_COURTESY_PHRASE in f.text for f in tts_frames), (
        f"Courtesy phrase must contain '{_SWITCH_COURTESY_PHRASE}'."
    )


# ---------------------------------------------------------------------------
# Plan 03-06 / Task 1 (RED): LazyWhisperSTTService.run_stt error yield
# ---------------------------------------------------------------------------

def test_lazy_whisper_run_stt_yields_error_frame_on_load_failure():
    """run_stt must yield a non-fatal ErrorFrame (not raise) when WhisperModel fails to load.

    process_generator (ai_service.py) pushes YIELDED ErrorFrames via push_error_frame but
    does NOT catch a RAISED exception. If run_stt raises, the error never reaches the
    ServiceSwitcher and SC4 never fires. Yielding ErrorFrame makes the failure symmetric
    with the Deepgram path.

    Security (V7/T-03-LOG): ErrorFrame.error is a static sanitized string — no exception detail.

    RED: run_stt currently lets asyncio.to_thread failure propagate as a raised exception.
    GREEN: run_stt catches the exception and yields ErrorFrame(error=..., fatal=False).
    """
    from pipecat.frames.frames import ErrorFrame
    from pipecat.services.whisper.stt import Model
    from pipecat.transcriptions.language import Language
    from src.pipeline.stt_switcher import LazyWhisperSTTService

    # Create the service normally (patching WhisperModel so _load() no-op doesn't try to import)
    with patch("faster_whisper.WhisperModel"):
        svc = LazyWhisperSTTService(
            device="cpu",
            compute_type="int8",
            settings=LazyWhisperSTTService.Settings(
                model=Model.LARGE_V3_TURBO,
                language=Language.IT,
                no_speech_prob=0.4,
            ),
        )
    svc._model = None  # ensure lazy state (should already be None from _load no-op)

    async def _run():
        frames = []
        # Patch asyncio.to_thread to simulate a model-load failure
        with patch("asyncio.to_thread", side_effect=RuntimeError("model load failed")):
            async for f in svc.run_stt(b"\x00" * 100):
                if f is not None:
                    frames.append(f)
        return frames

    # RED: asyncio.run() raises RuntimeError because run_stt propagates the exception.
    # GREEN: asyncio.run() returns [ErrorFrame(...)].
    frames = asyncio.run(_run())

    error_frames = [f for f in frames if isinstance(f, ErrorFrame)]
    assert len(error_frames) >= 1, (
        "run_stt must yield at least one ErrorFrame when WhisperModel fails to load "
        "(not raise an exception out of the generator) — SC4 symmetric error surfacing."
    )
    assert all(not f.fatal for f in error_frames), (
        "Yielded ErrorFrame must be non-fatal so ServiceSwitcher can handle it."
    )


# ---------------------------------------------------------------------------
# Plan 03-06 / Task 1 (RED): SC4 escalation via repeated on_service_switched
# ---------------------------------------------------------------------------

def test_sc4_escalation_fires_on_repeated_failover():
    """SC4: after _ESCALATION_THRESHOLD on_service_switched events, escalate exactly once.

    When all STT services are flapping/dead (repeated failover), the on_service_switched
    handler must escalate: set flow_manager.state['outcome']='fallito' and queue exactly
    one EndWorkerFrame. The call must not have prolonged dead-air.

    RED: AttributeError — patching FailoverDeepgramSTTService fails;
         AND even if test ran, the current on_service_switched has no escalation logic.
    GREEN: escalation fires after _ESCALATION_THRESHOLD switches.
    """
    from pipecat.frames.frames import EndWorkerFrame, ErrorFrame
    from src.pipeline.fallback import _ESCALATION_THRESHOLD
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()
    spy = _SpyWorker()
    holder.worker = spy
    fake_fm = type("_FM", (), {"state": {}})()
    holder.flow_manager = fake_fm  # patched after FlowManager creation (bot.py pattern)

    # In RED: patch raises AttributeError.
    with patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockFDSS, \
         patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockLWSS:
        fake_deepgram = MagicMock(name="fake_deepgram")
        fake_deepgram.name = "FailoverDeepgramSTT"
        fake_deepgram.queue_frame = AsyncMock()
        fake_whisper = MagicMock(name="fake_whisper")
        fake_whisper.name = "LazyWhisperSTT"
        fake_whisper.queue_frame = AsyncMock()
        MockFDSS.return_value = fake_deepgram
        MockLWSS.return_value = fake_whisper

        stt_switcher = build_stt_switcher(holder)

    strategy = stt_switcher.strategy

    async def _run():
        # Drive _ESCALATION_THRESHOLD on_service_switched events via real handle_error.
        # Each call feeds the error from the *currently active* service, so the switcher
        # always has a valid reason to switch (round-robins between fake_deepgram/fake_whisper).
        for _ in range(_ESCALATION_THRESHOLD):
            active = strategy.active_service
            err = ErrorFrame(error="persistent failure", fatal=False)
            err.processor = active
            await strategy.handle_error(err)

    asyncio.run(_run())

    assert fake_fm.state.get("outcome") == "fallito", (
        f"After {_ESCALATION_THRESHOLD} failover switches, "
        "on_service_switched handler must set outcome='fallito' (SC4)."
    )
    end_frames = [f for f in spy.queued if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) == 1, (
        f"Escalation must queue exactly one EndWorkerFrame (SC4 no dead-air); "
        f"got {len(end_frames)}."
    )


def test_sc4_escalation_idempotent_via_shared_guard():
    """SC4: a second batch of failover switches queues no further EndWorkerFrame.

    After the first escalation, the shared guard (flow_manager.state['_stt_escalated'])
    prevents additional EndWorkerFrames from being queued — even with more switches.

    RED: AttributeError — patching FailoverDeepgramSTTService fails.
    GREEN: shared guard set on first escalation; subsequent switches don't re-fire.
    """
    from pipecat.frames.frames import EndWorkerFrame, ErrorFrame
    from src.pipeline.fallback import _ESCALATION_THRESHOLD
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()
    spy = _SpyWorker()
    holder.worker = spy
    fake_fm = type("_FM", (), {"state": {}})()
    holder.flow_manager = fake_fm

    with patch("src.pipeline.stt_switcher.FailoverDeepgramSTTService") as MockFDSS, \
         patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockLWSS:
        fake_deepgram = MagicMock(name="fake_deepgram")
        fake_deepgram.name = "FailoverDeepgramSTT"
        fake_deepgram.queue_frame = AsyncMock()
        fake_whisper = MagicMock(name="fake_whisper")
        fake_whisper.name = "LazyWhisperSTT"
        fake_whisper.queue_frame = AsyncMock()
        MockFDSS.return_value = fake_deepgram
        MockLWSS.return_value = fake_whisper

        stt_switcher = build_stt_switcher(holder)

    strategy = stt_switcher.strategy

    async def _run():
        # 2× threshold — escalation should still fire exactly once
        for _ in range(_ESCALATION_THRESHOLD * 2):
            active = strategy.active_service
            err = ErrorFrame(error="persistent failure", fatal=False)
            err.processor = active
            await strategy.handle_error(err)

    asyncio.run(_run())

    end_frames = [f for f in spy.queued if isinstance(f, EndWorkerFrame)]
    assert len(end_frames) == 1, (
        f"SC4 escalation must be idempotent — exactly one EndWorkerFrame after "
        f"{_ESCALATION_THRESHOLD * 2} switches; got {len(end_frames)}."
    )
