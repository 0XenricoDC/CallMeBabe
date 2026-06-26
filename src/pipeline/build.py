"""Pipeline assembly — build_pipeline(transport, tenant) (VOICE-01).

Assembles the streaming voice pipeline in the canonical Pipecat 1.x order:
  transport.input() → STT → aggregators.user() → LLM → TTS → transport.output()
  → aggregators.assistant()

All imports use Pipecat 1.x paths only. Forbidden patterns (CLAUDE.md):
  - PipelineTask / PipelineRunner (pre-1.0 names)
  - OpenAILLMContext / provider-specific context
  - Flat service kwargs (model=..., params=InputParams(...))

Security (T-02-KEY): API keys read only via `os.getenv`; never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

from src.config.tenant_config import TenantConfig
from src.pipeline.factory import (
    build_tts_service,
    build_user_aggregator_params,
    get_stt_provider,
)


@dataclass
class BuildResult:
    """Named container for build_pipeline output (Plan 02-03 FlowManager seam).

    Exposes llm and aggregators so bot.py can wire FlowManager without
    re-instantiating services.  Keeps backward compatibility: callers that
    previously destructured ``(pipeline, context)`` can add ``, _`` or
    switch to attribute access.
    """

    pipeline: Pipeline
    context: LLMContext
    llm: AnthropicLLMService
    aggregators: LLMContextAggregatorPair

    def __iter__(self):
        """Support tuple-like destructuring: ``pipeline, context = build_pipeline(...)``."""
        return iter((self.pipeline, self.context))


def build_pipeline(transport, tenant: TenantConfig) -> BuildResult:
    """Assemble and return a BuildResult for one call session.

    Args:
        transport: A `SmallWebRTCTransport` (Phase 1) or Telnyx transport (Phase 4).
                   Must expose `.input()` and `.output()` processor methods.
        tenant:    The validated `TenantConfig` for this tenant/call.

    Returns:
        A ``BuildResult`` with attributes ``pipeline``, ``context``, ``llm``,
        and ``aggregators``.  Supports 2-tuple destructuring for backward compat:
        ``pipeline, context = build_pipeline(transport, tenant)``

    Pipeline order (RESEARCH §Architecture Patterns Pattern 1):
        transport.input() → stt → aggregators.user() → llm → tts
        → transport.output() → aggregators.assistant()
    """
    # --- STT (D-08: Deepgram default; Whisper config-selectable) ---
    # nova-3 has better Italian WER but CLAUDE.md locks nova-2 for Phase 1.
    # To enable nova-3: set STT_PROVIDER_MODEL=nova-3 in env (future enhancement).
    stt_provider = get_stt_provider(os.getenv("STT_PROVIDER", "deepgram"))
    stt = stt_provider.create_service()

    # --- LLM (D-10: model from tenant config, default claude-haiku-4-5) ---
    # Security (T-02-KEY): API key via env only; system_prompt from validated TenantConfig.
    llm = AnthropicLLMService(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        settings=AnthropicLLMService.Settings(
            model=tenant.model or "claude-haiku-4-5",
            system_instruction=tenant.system_prompt,
            max_tokens=1024,  # keep low for voice — long responses kill latency
        ),
    )

    # --- TTS (VOICE-05: per-tenant voice_id, eleven_multilingual_v2) ---
    tts = build_tts_service(tenant)

    # --- Context + aggregators ---
    # LLMContext accumulates conversation history across turns.
    # LLMContextAggregatorPair wraps it into user/assistant processor nodes.
    context = LLMContext()
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=build_user_aggregator_params(),
    )

    # --- Pipeline assembly ---
    # Order is mandatory: audio in → speech-to-text → LLM → text-to-speech → audio out
    # aggregators.assistant() must trail output() to capture the full TTS response.
    pipeline = Pipeline([
        transport.input(),        # raw PCM audio frames from client
        stt,                      # speech → TranscriptionFrame
        aggregators.user(),       # accumulates transcript; stops on VAD silence / timeout
        llm,                      # TranscriptionFrame → streaming LLMTextFrame tokens
        tts,                      # LLMTextFrame → streaming AudioRawFrame chunks
        transport.output(),       # audio chunks back to client
        aggregators.assistant(),  # records assistant response in context history
    ])

    return BuildResult(pipeline=pipeline, context=context, llm=llm, aggregators=aggregators)
