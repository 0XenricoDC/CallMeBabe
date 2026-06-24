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
    # Patch all three external services so no network I/O happens.
    with (
        patch("src.pipeline.build.DeepgramSTTService") as MockSTT,
        patch("src.pipeline.build.AnthropicLLMService") as MockLLM,
        patch("src.pipeline.build.ElevenLabsTTSService") as MockTTS,
        patch("src.pipeline.build.SileroVADAnalyzer") as MockVAD,
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

        from src.pipeline.build import build_pipeline

        transport = _make_mock_transport()
        result = build_pipeline(transport, tenant)

        # Must return a 2-tuple (pipeline, context)
        assert isinstance(result, tuple), "build_pipeline must return (pipeline, context)"
        assert len(result) == 2
        pipeline, ctx = result

        # Pipeline and context must be the mocked instances
        assert pipeline is mock_pipeline
        assert ctx is mock_ctx

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
# VOICE-05: ElevenLabsTTSService uses per-tenant voice_id + eleven_multilingual_v2
# ---------------------------------------------------------------------------

def test_tts_voice_id(tenant: TenantConfig):
    """VOICE-05: the TTS service uses voice_id from tenant config."""
    from src.pipeline.factory import build_tts_service

    with patch("src.pipeline.factory.ElevenLabsTTSService") as MockTTS:
        mock_tts = MagicMock(name="TTSInstance")
        MockTTS.return_value = mock_tts

        tts = build_tts_service(tenant)

    assert tts is mock_tts

    # Inspect the Settings object passed to ElevenLabsTTSService
    MockTTS.assert_called_once()
    _, kwargs = MockTTS.call_args
    settings = kwargs.get("settings")
    assert settings is not None, "ElevenLabsTTSService must be called with settings="
    assert settings.voice == tenant.voice_id, (
        f"TTS voice must equal tenant.voice_id ({tenant.voice_id!r}); got {settings.voice!r}"
    )
    assert settings.model == "eleven_multilingual_v2", (
        f"TTS model must be 'eleven_multilingual_v2'; got {settings.model!r}. "
        "Non-multilingual models silently ignore language=it (CLAUDE.md / Pitfall)."
    )
