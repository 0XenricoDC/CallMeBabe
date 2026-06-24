"""Pipeline factory — TransportFactory seam and STTProvider seam (D-05, D-08).

Provides:
- `STTProvider` ABC with `DeepgramProvider` (default) and `WhisperProvider` implementations.
- `get_stt_provider(config_key)` selector — no auto-failover (D-08; failover is Phase 3).
- `TransportFactory` — builds `SmallWebRTCTransport` (Phase 1); Phase 4 swaps for Telnyx.
- Helper functions used by unit tests to assert VAD/aggregator/TTS params in isolation.

Security (T-02-KEY): API keys read only via `os.getenv`; never logged or passed to console.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregatorParams
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.whisper.stt import Model, WhisperSTTService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from src.config.tenant_config import TenantConfig

# ---------------------------------------------------------------------------
# STTProvider seam (D-08)
# ---------------------------------------------------------------------------
# nova-3 now supports Italian with significantly better WER than nova-2.
# CLAUDE.md locks nova-2 as the default for Phase 1 stability. To upgrade,
# set model="nova-3" via tenant config or a global env var in a later phase.
_DEEPGRAM_MODEL = "nova-2"  # CLAUDE.md lock; upgrade to nova-3 when validating


class STTProvider(ABC):
    """Abstract STT backend selector.

    Phase 1 has two implementations: `DeepgramProvider` (default) and
    `WhisperProvider` (self-hosted fallback, config-selectable). No auto-failover
    — that is REL-03, Phase 3.
    """

    @abstractmethod
    def create_service(self):
        """Return a configured Pipecat STT service instance."""


class DeepgramProvider(STTProvider):
    """Deepgram nova-2 Italian streaming STT (primary, D-08)."""

    def create_service(self) -> DeepgramSTTService:
        # Security (T-02-KEY): key via env only, never logged.
        return DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            settings=DeepgramSTTService.Settings(
                model=_DEEPGRAM_MODEL,
                language="it",
                # Pitfall 8: Italian needs longer endpointing than English default.
                # 400ms is the starting point; tune down if utterances feel truncated.
                endpointing=400,
                interim_results=True,  # enables streaming transcription
                smart_format=False,    # cleaner raw text for LLM
                punctuate=True,
            ),
        )


class WhisperProvider(STTProvider):
    """faster-whisper large-v3-turbo self-hosted STT (fallback, D-08).

    NOTE: First run downloads ~1.5GB model from HuggingFace Hub. Pre-download with:
        python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo')"
    (documented in README § Setup).
    """

    def create_service(self) -> WhisperSTTService:
        # CLAUDE.md: must use LARGE_V3_TURBO with Language.IT; English-only models
        # (DISTIL_MEDIUM_EN, DISTIL_LARGE_V2) will mistranscribe Italian.
        return WhisperSTTService(
            settings=WhisperSTTService.Settings(
                model=Model.LARGE_V3_TURBO,
                language=Language.IT,
                no_speech_prob=0.4,
            ),
        )


_STT_PROVIDERS: dict[str, type[STTProvider]] = {
    "deepgram": DeepgramProvider,
    "whisper": WhisperProvider,
}


def get_stt_provider(config_key: str = "deepgram") -> STTProvider:
    """Return the STTProvider instance for the given config_key.

    Valid keys: ``"deepgram"`` (default), ``"whisper"``.
    No auto-failover — switching is explicit via config (D-08).
    """
    cls = _STT_PROVIDERS.get(config_key)
    if cls is None:
        raise ValueError(
            f"Unknown STT provider: {config_key!r}. Valid: {list(_STT_PROVIDERS)}"
        )
    return cls()


# ---------------------------------------------------------------------------
# VAD / aggregator helpers (tested in isolation by test_pipeline.py)
# ---------------------------------------------------------------------------

def build_vad_params() -> VADParams:
    """Return the VAD parameters used for barge-in (VOICE-03, D-11).

    stop_secs=0.3: after 300ms of silence the VAD declares end-of-speech.
    This is the primary barge-in signal — it is distinct from
    `user_turn_stop_timeout` (Pitfall 3).
    """
    return VADParams(
        confidence=0.7,
        start_secs=0.2,
        stop_secs=0.3,
        min_volume=0.6,
    )


def build_user_aggregator_params() -> LLMUserAggregatorParams:
    """Return LLMUserAggregatorParams with the CRITICAL timeout fix (VOICE-04).

    user_turn_stop_timeout=0.2: after VAD detects silence, the aggregator waits
    only 0.2s before submitting the transcript to the LLM. Default is 5.0s —
    that alone blows the 800ms latency budget (Pitfall 1).
    """
    vad = SileroVADAnalyzer(params=build_vad_params())
    return LLMUserAggregatorParams(
        vad_analyzer=vad,
        user_turn_stop_timeout=0.2,  # CRITICAL: default 5s blows 800ms budget
    )


def build_tts_service(tenant: TenantConfig) -> ElevenLabsTTSService:
    """Return an ElevenLabsTTSService configured for the tenant's voice (VOICE-05).

    Security (T-02-KEY): API key via env only; voice_id from validated TenantConfig.
    """
    # CLAUDE.md / Pitfall: must use a multilingual model with language="it".
    # Non-multilingual models silently ignore the language parameter.
    return ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsTTSService.Settings(
            voice=tenant.voice_id,
            model="eleven_multilingual_v2",
            language="it",
            stability=0.5,
            similarity_boost=0.75,
            speed=1.0,
        ),
    )


# ---------------------------------------------------------------------------
# TransportFactory (D-05) — Phase 4 swaps SmallWebRTC for Telnyx here
# ---------------------------------------------------------------------------

class TransportFactory:
    """Creates the audio transport for the current deployment environment.

    Phase 1: `SmallWebRTCTransport` (browser WebRTC, no native audio deps).
    Phase 4: swap to Telnyx (`TelnyxFrameSerializer` + `FastAPIWebsocketTransport`)
             by subclassing or replacing this factory — the pipeline is unchanged.
    """

    @staticmethod
    def create_webrtc_transport(webrtc_connection) -> SmallWebRTCTransport:
        """Return a configured SmallWebRTCTransport for local dev (Phase 1)."""
        return SmallWebRTCTransport(
            webrtc_connection=webrtc_connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )
