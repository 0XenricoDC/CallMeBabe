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

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.service_switcher import ServiceSwitcher
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.anthropic.llm import AnthropicLLMService

from src.config.tenant_config import TenantConfig
from src.pipeline.factory import (
    build_tts_service,
    build_user_aggregator_params,
)
from src.pipeline.stt_switcher import WorkerRefHolder, build_stt_switcher


@dataclass
class BuildResult:
    """Named container for build_pipeline output (Plan 02-03 FlowManager seam).

    Exposes llm and aggregators so bot.py can wire FlowManager without
    re-instantiating services.  Keeps backward compatibility: callers that
    previously destructured ``(pipeline, context)`` can add ``, _`` or
    switch to attribute access.

    Phase 03-04 additions:
    - stt_switcher: the ServiceSwitcher in the STT pipeline slot (REL-03).
    - worker_ref_holder: WorkerRefHolder whose .worker must be set after PipelineWorker
      creation (same circular-dep pattern as ErrorFallbackObserver).
    """

    pipeline: Pipeline
    context: LLMContext
    llm: AnthropicLLMService
    aggregators: LLMContextAggregatorPair
    stt_switcher: ServiceSwitcher = None  # type: ignore[assignment]
    worker_ref_holder: WorkerRefHolder = None  # type: ignore[assignment]

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
    # --- STT switcher (REL-03: Deepgram primary → LazyWhisperSTTService fallback) ---
    # Phase 03-04 replaces the standalone stt with a ServiceSwitcher that auto-fails
    # over to faster-whisper on persistent Deepgram errors (D-12 lazy load, SC3).
    # worker_ref_holder.worker is patched after PipelineWorker creation in bot.py
    # (circular-dep pattern, same as ErrorFallbackObserver).
    worker_ref_holder = WorkerRefHolder()
    stt_switcher = build_stt_switcher(worker_ref_holder)

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
    # Phase 03-04: stt_switcher replaces standalone `stt` in the STT slot (REL-03).
    pipeline = Pipeline([
        transport.input(),        # raw PCM audio frames from client
        stt_switcher,             # ServiceSwitcher([deepgram, lazy_whisper], failover)
        aggregators.user(),       # accumulates transcript; stops on VAD silence / timeout
        llm,                      # TranscriptionFrame → streaming LLMTextFrame tokens
        tts,                      # LLMTextFrame → streaming AudioRawFrame chunks
        transport.output(),       # audio chunks back to client
        aggregators.assistant(),  # records assistant response in context history
    ])

    return BuildResult(
        pipeline=pipeline,
        context=context,
        llm=llm,
        aggregators=aggregators,
        stt_switcher=stt_switcher,
        worker_ref_holder=worker_ref_holder,
    )
