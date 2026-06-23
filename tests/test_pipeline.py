"""Wave 0 stubs for the voice pipeline (VOICE-01, VOICE-03, VOICE-04, VOICE-05).

These are RED stubs: the pipeline module does not exist yet (built in Plan 02).
Each test is xfail-marked with the owning plan so the suite stays collectable and
green-on-xfail now. Plan 02 removes the marker and implements the behaviour.
"""

import pytest

PLAN_02 = "implemented in Plan 02 (pipeline assembly)"


@pytest.mark.xfail(reason=PLAN_02, strict=False)
def test_pipeline_builds(tenant):
    """VOICE-01: the streaming pipeline assembles without exception.

    TODO(Plan 02): build_pipeline(transport, tenant) returns (pipeline, context)
    with order transport.input -> stt -> user-agg -> llm -> tts -> transport.output
    -> assistant-agg.
    """
    from src.bot import build_pipeline  # noqa: F401  (module created in Plan 02)

    raise AssertionError("build_pipeline not implemented yet (Plan 02)")


@pytest.mark.xfail(reason=PLAN_02, strict=False)
def test_frame_flow(tenant):
    """VOICE-01: STT -> LLM -> TTS frame flow propagates through the pipeline.

    TODO(Plan 02): feed a TranscriptionFrame and assert an audio frame is produced.
    """
    from src.bot import build_pipeline  # noqa: F401

    raise AssertionError("frame-flow integration not implemented yet (Plan 02)")


@pytest.mark.xfail(reason=PLAN_02, strict=False)
def test_vad_params(tenant):
    """VOICE-03: SileroVADAnalyzer is configured with the tuned stop_secs for barge-in.

    TODO(Plan 02): assert VADParams(stop_secs) is in the 0.2-0.3s band.
    """
    from src.pipeline.factory import build_vad_params  # noqa: F401

    raise AssertionError("VAD params not implemented yet (Plan 02)")


@pytest.mark.xfail(reason=PLAN_02, strict=False)
def test_aggregator_timeout(tenant):
    """VOICE-04: user_turn_stop_timeout <= 0.3s (Pitfall 1 — default 5s blows budget).

    TODO(Plan 02): assert LLMUserAggregatorParams(user_turn_stop_timeout) <= 0.3.
    """
    from src.pipeline.factory import build_user_aggregator_params  # noqa: F401

    raise AssertionError("aggregator timeout not implemented yet (Plan 02)")


@pytest.mark.xfail(reason=PLAN_02, strict=False)
def test_tts_voice_id(tenant):
    """VOICE-05: the TTS service uses voice_id from tenant config (ElevenLabs).

    TODO(Plan 02): assert the constructed TTS service's voice == tenant.voice_id.
    """
    from src.bot import build_tts  # noqa: F401

    raise AssertionError("TTS voice_id wiring not implemented yet (Plan 02)")
