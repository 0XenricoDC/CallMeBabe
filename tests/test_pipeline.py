"""Tests for the voice pipeline — VOICE-01, VOICE-03, VOICE-04, VOICE-05.

These tests were RED stubs in Plan 01-01. Plan 01-02 removes the xfail markers
and implements the behaviour being asserted here.

All tests mock the Pipecat service constructors so no live API calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.config.tenant_config import TenantConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_transport():
    """Return a mock transport whose .input() and .output() are MagicMocks."""
    transport = MagicMock(name="MockSmallWebRTCTransport")
    transport.input.return_value = MagicMock(name="TransportInput")
    transport.output.return_value = MagicMock(name="TransportOutput")
    return transport


# ---------------------------------------------------------------------------
# VOICE-01: pipeline assembles without exception
# ---------------------------------------------------------------------------

def test_pipeline_builds(tenant: TenantConfig):
    """VOICE-01: build_pipeline(transport, tenant) returns a Pipeline + LLMContext."""
    # Patch external services at the point of import (factory.py and build.py)
    # so no network I/O or missing-API-key errors occur.
    with (
        patch("src.pipeline.factory.DeepgramSTTService") as MockSTT,
        patch("src.pipeline.build.AnthropicLLMService") as MockLLM,
        patch("src.pipeline.factory.ElevenLabsTTSService") as MockTTS,
        patch("src.pipeline.factory.SileroVADAnalyzer") as MockVAD,
        patch("src.pipeline.build.Pipeline") as MockPipeline,
        patch("src.pipeline.build.LLMContextAggregatorPair") as MockAggregators,
        patch("src.pipeline.build.LLMContext") as MockContext,
    ):
        MockSTT.return_value = MagicMock(name="STTInstance")
        MockLLM.return_value = MagicMock(name="LLMInstance")
        MockTTS.return_value = MagicMock(name="TTSInstance")
        MockVAD.return_value = MagicMock(name="VADInstance")
        mock_pipeline = MagicMock(name="PipelineInstance")
        MockPipeline.return_value = mock_pipeline
        mock_ctx = MagicMock(name="LLMContextInstance")
        MockContext.return_value = mock_ctx
        mock_agg_pair = MagicMock(name="AggPairInstance")
        mock_agg_pair.user.return_value = MagicMock(name="UserAgg")
        mock_agg_pair.assistant.return_value = MagicMock(name="AssistantAgg")
        MockAggregators.return_value = mock_agg_pair

        from src.pipeline.build import BuildResult, build_pipeline

        transport = _make_mock_transport()
        result = build_pipeline(transport, tenant)

        # Must return a BuildResult with pipeline, context, llm, aggregators
        # (Plan 02-03: extended from 2-tuple to expose llm/aggregators for FlowManager wiring)
        assert isinstance(result, BuildResult), (
            f"build_pipeline must return a BuildResult; got {type(result)}"
        )
        # Supports 2-tuple destructuring for backward compatibility
        pipeline, ctx = result

        # Pipeline and context must be the mocked instances
        assert pipeline is mock_pipeline
        assert ctx is mock_ctx

        # llm and aggregators also exposed (FlowManager seam — D-19)
        assert result.llm is not None
        assert result.aggregators is not None

        # Pipeline constructor must have been called once with a list
        MockPipeline.assert_called_once()
        call_args = MockPipeline.call_args[0][0]  # first positional arg = processor list
        assert isinstance(call_args, list), "Pipeline must receive a list of processors"
        assert len(call_args) >= 7, "Pipeline must have at least 7 stages"


# ---------------------------------------------------------------------------
# VOICE-03: Silero VAD configured with correct stop_secs for barge-in
# ---------------------------------------------------------------------------

def test_vad_params():
    """VOICE-03: SileroVADAnalyzer is configured with stop_secs == 0.3 (barge-in)."""
    from src.pipeline.factory import build_vad_params

    params = build_vad_params()

    # stop_secs must be exactly 0.3 (as per plan and CONTEXT D-08 / Pitfall 3)
    assert params.stop_secs == 0.3, (
        f"stop_secs must be 0.3 for barge-in; got {params.stop_secs}"
    )
    # Confidence and start_secs sanity checks
    assert 0.0 < params.confidence <= 1.0
    assert params.start_secs <= 0.5


# ---------------------------------------------------------------------------
# VOICE-04: user_turn_stop_timeout <= 0.3s (Pitfall 1)
# ---------------------------------------------------------------------------

def test_aggregator_timeout():
    """VOICE-04: user_turn_stop_timeout <= 0.3s (default 5s blows 800ms budget)."""
    from src.pipeline.factory import build_user_aggregator_params

    with patch("src.pipeline.factory.SileroVADAnalyzer"):
        params = build_user_aggregator_params()

    assert params.user_turn_stop_timeout <= 0.3, (
        f"user_turn_stop_timeout must be <= 0.3s; got {params.user_turn_stop_timeout}. "
        "Default 5.0s destroys latency budget (Pitfall 1)."
    )


# ---------------------------------------------------------------------------
# VOICE-05: ElevenLabsTTSService uses per-tenant voice_id + eleven_turbo_v2_5
# ---------------------------------------------------------------------------

def test_tts_voice_id(tenant: TenantConfig):
    """VOICE-05: the TTS service uses voice_id from tenant config."""
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
    from src.pipeline.factory import build_tts_service

    # We mock the ElevenLabsTTSService constructor itself but keep the real
    # Settings dataclass so we can inspect the settings object that was built.
    real_Settings = ElevenLabsTTSService.Settings
    captured: list = []

    def _mock_tts_init(self, **kwargs):
        captured.append(kwargs)

    with patch.object(ElevenLabsTTSService, "__init__", _mock_tts_init):
        # build_tts_service will construct a Settings(...) and pass it as kwarg
        # The mock __init__ captures the kwargs but returns None (no network call).
        try:
            tts = build_tts_service(tenant)
        except Exception:
            pass  # __init__ returns None; attribute access after may raise

    assert captured, "ElevenLabsTTSService.__init__ was not called"
    kwargs = captured[0]
    settings = kwargs.get("settings")
    assert settings is not None, "ElevenLabsTTSService must be called with settings= kwarg"
    assert isinstance(settings, real_Settings), (
        f"settings must be an ElevenLabsTTSService.Settings instance; got {type(settings)}"
    )
    assert settings.voice == tenant.voice_id, (
        f"TTS voice must equal tenant.voice_id ({tenant.voice_id!r}); got {settings.voice!r}"
    )
    assert settings.model == "eleven_turbo_v2_5", (
        f"TTS model must be 'eleven_turbo_v2_5'; got {settings.model!r}. "
        "Only eleven_flash_v2_5 / eleven_turbo_v2_5 honor the language code in "
        "pipecat 1.4.0 (ELEVENLABS_MULTILINGUAL_MODELS); the old eleven_multilingual_v2 "
        "silently ignores language=it and logs a warning."
    )
    # The Italian language code must be applied (resolves to 'it').
    lang = settings.language
    lang_value = getattr(lang, "value", lang)
    assert lang_value == "it", (
        f"TTS language must resolve to Italian ('it'); got {lang!r}."
    )
