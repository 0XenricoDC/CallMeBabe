"""Tests for STT ServiceSwitcher + LazyWhisperSTTService (REL-03 / Plan 03-04).

Task 1 coverage:
- LazyWhisperSTTService: _model is None after construction (no eager load).
- build_stt_switcher(): returns a ServiceSwitcher with two services and a failover strategy.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
    """REL-03: build_stt_switcher() must return a ServiceSwitcher instance."""
    from pipecat.pipeline.service_switcher import ServiceSwitcher

    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    with (
        patch("src.pipeline.stt_switcher.DeepgramSTTService") as MockDeepgram,
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
    ):
        MockDeepgram.return_value = MagicMock(name="DeepgramSTT")
        MockWhisper.return_value = MagicMock(name="LazyWhisperSTT")

        stt_switcher = build_stt_switcher(holder)

    assert isinstance(stt_switcher, ServiceSwitcher), (
        "build_stt_switcher() must return a ServiceSwitcher instance (REL-03)."
    )


def test_build_stt_switcher_has_two_services():
    """REL-03: build_stt_switcher() must return a switcher with exactly two services."""
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    with (
        patch("src.pipeline.stt_switcher.DeepgramSTTService") as MockDeepgram,
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
    ):
        mock_deepgram = MagicMock(name="DeepgramSTT")
        mock_whisper = MagicMock(name="LazyWhisperSTT")
        MockDeepgram.return_value = mock_deepgram
        MockWhisper.return_value = mock_whisper

        stt_switcher = build_stt_switcher(holder)

    assert len(stt_switcher._services) == 2, (
        "ServiceSwitcher must have exactly two services: [deepgram, lazy_whisper] (REL-03)."
    )


def test_build_stt_switcher_strategy_is_failover():
    """REL-03: build_stt_switcher() must use ServiceSwitcherStrategyFailover."""
    from pipecat.pipeline.service_switcher import ServiceSwitcherStrategyFailover

    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()

    with (
        patch("src.pipeline.stt_switcher.DeepgramSTTService") as MockDeepgram,
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
    ):
        MockDeepgram.return_value = MagicMock(name="DeepgramSTT")
        MockWhisper.return_value = MagicMock(name="LazyWhisperSTT")

        stt_switcher = build_stt_switcher(holder)

    assert isinstance(stt_switcher._strategy, ServiceSwitcherStrategyFailover), (
        "ServiceSwitcher strategy must be ServiceSwitcherStrategyFailover (REL-03)."
    )


def test_build_stt_switcher_deepgram_api_key_from_env():
    """Security (T-02-KEY): DeepgramSTTService must receive api_key from os.getenv only."""
    from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher

    holder = WorkerRefHolder()
    captured_deepgram_kwargs = {}

    def _capture_deepgram(*args, **kwargs):
        captured_deepgram_kwargs.update(kwargs)
        m = MagicMock(name="DeepgramSTT")
        return m

    with (
        patch("src.pipeline.stt_switcher.DeepgramSTTService", side_effect=_capture_deepgram),
        patch("src.pipeline.stt_switcher.LazyWhisperSTTService") as MockWhisper,
        patch("src.pipeline.stt_switcher.os.getenv", return_value="test-dg-key") as mock_env,
    ):
        MockWhisper.return_value = MagicMock(name="LazyWhisperSTT")
        build_stt_switcher(holder)

    assert "api_key" in captured_deepgram_kwargs, "DeepgramSTTService must receive api_key kwarg."
    assert captured_deepgram_kwargs["api_key"] == "test-dg-key", (
        "api_key must come from os.getenv (not hardcoded)."
    )
