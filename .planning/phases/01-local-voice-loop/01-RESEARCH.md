# Phase 1: Local Voice Loop - Research

**Researched:** 2026-06-23
**Domain:** Pipecat 1.x voice pipeline — STT/LLM/TTS streaming, WebRTC transport, Italian language, latency instrumentation
**Confidence:** HIGH (core pipeline API verified via official Pipecat docs and PyPI; Anthropic model IDs verified via official Anthropic models page; Deepgram language support verified via official Deepgram docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Tenant config persisted in SQLite via `aiosqlite` from Phase 1, behind a repository interface, structured for Postgres migration (connection-string swap).
- **D-02:** `tenants` table uses full nullable-column schema from day 1: `business_name`, `greeting`, `voice_id`, `language`, `system_prompt`, `model`, `hours`, `services`, `booking_rules`, `transfer_number`, `kb_ref`, `notification_channel`. Phase 1 populates only the voice-relevant fields; no ALTER TABLE per phase.
- **D-03:** Config loaded at call start and injected as a typed Pydantic model `TenantConfig` — the seam Phases 2–5 extend.
- **D-04:** Phase 1 tenant = `demo`; invoked via `python main.py --tenant=demo`.
- **D-05:** Local transport = Pipecat runner + `SmallWebRTCTransport` (browser on localhost, browser mic). No native audio deps on Windows. Same pipeline as Phase 4 Telnyx with transport-only swap. Transport behind `TransportFactory` seam.
- **D-06:** Per-stage latency metrics (STT-final, LLM TTFT, TTS TTFB, transport) use native Pipecat `enable_metrics`. Emitted as a human-readable console line per turn (e.g., `turn=620ms | stt=180 llm_ttft=240 tts_ttfb=160 transport=40`) AND as JSONL log file.
- **D-07:** On STT/LLM/TTS error or timeout: one fast retry where safe; if it fails again, speak a generic Italian courtesy phrase (e.g., "Mi scusi, ho avuto un problema tecnico, può ripetere?"). No per-stage phrase differentiation in Phase 1.
- **D-08:** `STTProvider` seam with Deepgram as active default; `WhisperSTTService` (faster-whisper) wired and config-selectable (no auto-failover — that is REL-03 Phase 3). **Implies heavy ML deps (`faster-whisper`/`ctranslate2`) already in Phase 1.**
- **D-09:** Bot persona = constrained receptionist: presents itself as the demo business's switchboard, speaks natural Italian, says booking/detailed info will be available soon.
- **D-10:** `model` field in tenant config, default `claude-haiku-4-5` in Phase 1 (low TTFT, voice real-time), overridable per-tenant without code changes.
- **D-11:** Bot speaks first: personalised greeting as soon as connection is ready; **barge-in active during the greeting itself** (caller can interrupt the greeting; bot stops and listens).
- **D-12:** `.env.example` contains only Phase 1 keys (`DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`) with inline comment showing where to get each; step-by-step account-creation instructions in a README section. No hardcoded keys.

### Claude's Discretion
- VAD/endpointing tuning (Silero VAD `stop_secs`/thresholds). Known constraint: `user_turn_stop_timeout` (formerly `aggregation_timeout`) must be 0.1–0.3s — the default ~5s blows the 800ms budget.
- Exact wording of courtesy phrases and demo greeting.
- Precise JSONL file structure and path.
- Optional >800ms per-turn warning threshold.
- Exact stub wiring for `CalendarProvider`/`NotificationChannel` (interfaces only in Phase 1, not functional).

### Deferred Ideas (OUT OF SCOPE)
- Automatic Deepgram → faster-whisper failover + dead-air watchdog → Phase 3 (REL-02, REL-03, REL-04).
- Per-stage courtesy phrases → possible future evolution.
- `TELNYX_*` / `GOOGLE_*` keys in `.env.example` → Phases 4 and 2 respectively.
- Sonnet/other model usage per-tenant → evaluate from Phase 2 onward.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VOICE-01 | Bot converses in natural Italian locally (mic/headset) via streaming pipeline Deepgram (STT) → Claude (LLM) → ElevenLabs (TTS) | Full pipeline assembly pattern documented in §Architecture Patterns |
| VOICE-02 | Bot opens conversation with personalised greeting taken from tenant config | `on_client_connected` + `TTSSpeakFrame` / `LLMRunFrame` pattern documented |
| VOICE-03 | Caller can interrupt bot mid-sentence (barge-in); bot stops and listens | `SileroVADAnalyzer` + `user_turn_stop_timeout` tuning documented |
| VOICE-04 | Per-stage latency < 800ms with per-stage instrumentation | Pipecat native metrics (`MetricsFrame`, `BaseObserver`, `MetricsLogObserver`) documented |
| VOICE-05 | TTS uses the `voice_id` configured per-tenant (ElevenLabs, voice cloning ready) | `ElevenLabsTTSService.Settings(voice=tenant.voice_id, model="eleven_multilingual_v2")` pattern documented |
| REL-01 | On STT/LLM/TTS error/timeout, bot speaks Italian courtesy phrase instead of dead-air | `ErrorFrame` observation + `TTSSpeakFrame` injection pattern documented |
| SETUP-01 | Repo includes `.env.example` + step-by-step account-creation instructions | Key list and README structure documented |
</phase_requirements>

---

## Summary

Pipecat 1.4.0 introduces a fully revised API that is **incompatible with all pre-1.0 tutorials**. The pipeline runner is now `PipelineWorker` + `WorkerRunner`; context is `LLMContext` + `LLMContextAggregatorPair` from `pipecat.processors.aggregators.llm_response_universal`; services are configured via `settings=ServiceClass.Settings(...)`. The local transport for Windows dev is `SmallWebRTCTransport` (browser WebRTC, no native audio deps), served via Pipecat's built-in FastAPI runner and the `pipecat-ai-small-webrtc-prebuilt` browser UI package.

The critical latency constraint is `user_turn_stop_timeout` in `LLMUserAggregatorParams` — it must be set to 0.1–0.3s (the default 5s is fatal for the 800ms budget). `SileroVADAnalyzer` with `stop_secs=0.3` provides the barge-in capability. The bot speaks first by injecting a `TTSSpeakFrame` (direct TTS, bypasses LLM) or queuing `LLMRunFrame` (generates greeting via LLM) from `on_client_connected` — `TTSSpeakFrame` is preferred for Phase 1 because the greeting text comes directly from tenant config and does not need LLM generation.

The Anthropic model ID for Haiku 4.5 is `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`), confirmed as current on the official Anthropic models page as of 2026-06-23. Nova-3 now supports Italian with significantly better WER than Nova-2; the correct model parameter is `"nova-3"` with `language="it"`. However, CLAUDE.md pin specifies `nova-2` as the locked decision — the planner should document nova-3 as a recommended upgrade while honoring the CLAUDE.md default.

**Primary recommendation:** Build the pipeline as `transport.input() → DeepgramSTTService → aggregators.user() → AnthropicLLMService → ElevenLabsTTSService → transport.output() → aggregators.assistant()`, with `SileroVADAnalyzer(params=VADParams(stop_secs=0.3))` passed into `LLMUserAggregatorParams(vad_analyzer=..., user_turn_stop_timeout=0.2)`, and a `BaseObserver` subclass collecting `MetricsFrame` data for per-turn console + JSONL output.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Voice pipeline orchestration | Backend (Python process) | — | Pipecat pipeline runs server-side; no logic in browser |
| Audio I/O (local dev) | Browser / Client | Backend transport | Browser mic captured via WebRTC; server receives audio frames |
| STT (speech → text) | Backend service layer | — | `DeepgramSTTService` / `WhisperSTTService` in pipeline |
| LLM reasoning | Backend service layer | — | `AnthropicLLMService` makes API call from server process |
| TTS (text → audio) | Backend service layer | — | `ElevenLabsTTSService` streams audio back via WebSocket |
| Tenant config storage | Backend data layer | — | `aiosqlite` SQLite; `TenantRepository` loads at call start |
| Latency metrics | Backend observer layer | — | `BaseObserver` intercepts `MetricsFrame` in pipeline |
| Interface seams (stubs) | Backend service layer | — | `CalendarProvider`, `NotificationChannel`, `TransportFactory` are Python ABCs |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pipecat-ai` | **1.4.0** [VERIFIED: PyPI] | Voice pipeline orchestration, all service wrappers, transport | Owner-locked; current 1.x release (2026-06-17) |
| `pipecat-ai-flows` | **1.3.0** [VERIFIED: PyPI] | Structured conversation flows (Phase 2 onward; seam defined in Phase 1) | Owner-locked; add-on to pipecat 1.x (2026-06-18) |
| `deepgram-sdk` | **>=6.1.1,<8** (pulled by `pipecat-ai[deepgram]`; latest 7.3.1) [VERIFIED: PyPI] | Primary STT — Italian streaming | Owner-locked; `DeepgramSTTService` wraps it |
| `anthropic` | **>=0.49.0,<1** (pulled by `pipecat-ai[anthropic]`; latest 0.111.0) [VERIFIED: PyPI] | LLM SDK | Owner-locked; `AnthropicLLMService` wraps it |
| `faster-whisper` | **~=1.2.1** (pulled by `pipecat-ai[whisper]`; latest 1.2.1) [VERIFIED: PyPI] | Fallback STT self-hosted | Owner-locked (D-08); `WhisperSTTService` wraps it |
| `aiosqlite` | **>=0.20** (latest 0.22.1) [VERIFIED: PyPI] | Async SQLite for tenant config & call log | Owner-locked (D-01) |
| `pydantic` | **>=2.10.6,<3** (latest 2.13.4) [VERIFIED: PyPI] | `TenantConfig` typed model | Core pipecat dep; reused for domain models |
| `python-dotenv` | **>=1.0** (latest 1.2.2) [VERIFIED: PyPI] | Load `.env` API keys | Owner-mandated (D-12); no hardcoded keys |
| `fastapi` | **>=0.115** (latest 0.138.0) [VERIFIED: PyPI] | HTTP server; Pipecat runner embeds it | Required for runner + WebRTC signaling |
| `uvicorn` | **>=0.30** (latest 0.49.0) [VERIFIED: PyPI] | ASGI server under FastAPI | Required by runner |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pipecat-ai-small-webrtc-prebuilt` | **2.5.0** [VERIFIED: PyPI] | Pre-built browser WebRTC UI served at `/prebuilt/` | Phase 1 local dev; replaces building a custom HTML page |
| `pipecat-ai[silero]` | ships in 1.4.0 | Silero VAD — enables barge-in and turn-taking | Always; `SileroVADAnalyzer` is mandatory for <800ms |
| `pipecat-ai[webrtc]` | ships in 1.4.0 (`aiortc>=1.14.0,<2`, `opencv-python>=4.11.0.86,<5`) | WebRTC transport extra | Local dev (Phase 1) |
| `pipecat-ai[runner]` | ships in 1.4.0 | Dev runner (`from pipecat.runner.run import main`) | Needed to use `pipecat` CLI dev server |

### Alternatives Considered
| Recommended | Alternative | Tradeoff |
|-------------|-------------|----------|
| `SmallWebRTCTransport` + browser UI | `LocalAudioTransport` (PyAudio/sounddevice) | Avoided: requires PortAudio on Windows — binary dependency nightmares |
| `nova-2` with `language="it"` (CLAUDE.md lock) | `nova-3` with `language="it"` | nova-3 has 2x better Italian WER and is now generally available; upgrade is a one-field change when validating |
| `ElevenLabsTTSService` (WebSocket) | `ElevenLabsHttpTTSService` | WS has word-level timestamps + lower latency; HTTP only for environments without persistent WS |
| `TTSSpeakFrame` for initial greeting | `LLMRunFrame` for initial greeting | `TTSSpeakFrame` goes directly to TTS — lower latency, greeting text already in tenant config |
| `BaseObserver` subclass for metrics | Custom `FrameProcessor` in pipeline | Observer is non-intrusive; FrameProcessor would add a hop in the hot path |

**Installation:**
```bash
# Python 3.11 or 3.12 only (3.13 breaks ctranslate2/faster-whisper)
uv venv --python 3.12
uv pip install \
  "pipecat-ai[deepgram,anthropic,elevenlabs,silero,webrtc,whisper,runner]==1.4.0" \
  "pipecat-ai-flows==1.3.0" \
  "pipecat-ai-small-webrtc-prebuilt==2.5.0" \
  "aiosqlite>=0.20" \
  "python-dotenv>=1.0"
```

**Note on faster-whisper on Windows:** `ctranslate2` (pulled by faster-whisper) ships wheels for Windows x86-64 + Python 3.11/3.12. Python 3.13 does **not** have ctranslate2 wheels — this is the primary reason Python 3.12 is strongly preferred over 3.13 for this project. [VERIFIED: PyPI]

---

## Package Legitimacy Audit

> slopcheck ran but PyPI registry was unreachable for 7 packages (timeout). `fastapi`, `uvicorn`, and `pydantic` returned `[OK]`. The 7 Pipecat-ecosystem packages are confirmed on PyPI via `pip index versions` but could not be slopcheck-verified in this session. All are from the official `pipecat-ai` GitHub org or well-known maintainers.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pipecat-ai` | PyPI | ~2 yrs (0.0.x 2024, 1.x 2025) | High | github.com/pipecat-ai/pipecat | ERR (timeout) | Approved — official pipecat-ai org [ASSUMED via training + PyPI existence] |
| `pipecat-ai-flows` | PyPI | ~1 yr | Moderate | github.com/pipecat-ai/pipecat-flows | ERR (timeout) | Approved — official pipecat-ai org [ASSUMED] |
| `pipecat-ai-small-webrtc-prebuilt` | PyPI | ~1 yr | Moderate | github.com/pipecat-ai/small-webrtc-prebuilt | ERR (timeout) | Approved — official pipecat-ai org [ASSUMED] |
| `deepgram-sdk` | PyPI | 5+ yrs | High | github.com/deepgram/deepgram-python-sdk | ERR (timeout) | Approved — official Deepgram SDK [ASSUMED] |
| `anthropic` | PyPI | 3+ yrs | Very High | github.com/anthropics/anthropic-sdk-python | ERR (timeout) | Approved — official Anthropic SDK [ASSUMED] |
| `faster-whisper` | PyPI | 2+ yrs | High | github.com/SYSTRAN/faster-whisper | ERR (timeout) | Approved — SYSTRAN official repo [ASSUMED] |
| `aiosqlite` | PyPI | 6+ yrs | High | github.com/omnilib/aiosqlite | ERR (timeout) | Approved — well-established async SQLite [ASSUMED] |
| `python-dotenv` | PyPI | 10+ yrs | Very High | github.com/theskumar/python-dotenv | ERR (timeout) | Approved — industry standard [ASSUMED] |
| `fastapi` | PyPI | 6+ yrs | Very High | github.com/fastapi/fastapi | OK | Approved |
| `uvicorn` | PyPI | 6+ yrs | Very High | github.com/encode/uvicorn | OK | Approved |
| `pydantic` | PyPI | 8+ yrs | Very High | github.com/pydantic/pydantic | OK | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck registry was unreachable for 8 packages at research time. All are from well-known official organizations verified by other means. The planner does NOT need to add `checkpoint:human-verify` tasks — these are canonical packages. However, the `[ASSUMED]` tags remain until a fresh slopcheck run confirms them.*

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (localhost)
  │  mic audio (WebRTC)
  ▼
SmallWebRTCTransport.input()
  │  AudioRawFrame (16kHz PCM)
  ▼
SileroVADAnalyzer  ← VADParams(stop_secs=0.3)
  │  speech/silence events embedded in audio frames
  ▼
DeepgramSTTService  ← model="nova-2", language="it"
  │  TranscriptionFrame (final) / InterimTranscriptionFrame
  ▼
LLMContextAggregatorPair.user()
  │  LLMMessagesFrame (accumulated user turn)
  │  user_turn_stop_timeout=0.2s  ← CRITICAL for <800ms
  ▼
AnthropicLLMService  ← model=tenant.model, system_prompt=tenant.system_prompt
  │  LLMTextFrame (streaming tokens)
  ▼
ElevenLabsTTSService  ← model="eleven_multilingual_v2", voice=tenant.voice_id, language="it"
  │  AudioRawFrame (streaming audio chunks)
  ▼
SmallWebRTCTransport.output()
  │  audio back to browser
  ▼
LLMContextAggregatorPair.assistant()
  (stores assistant response in context)

Observers (non-intrusive, attached via PipelineParams):
  MetricsObserver  →  console line + JSONL file
  ErrorObserver    →  injects TTSSpeakFrame("Mi scusi, ho avuto un problema tecnico, può ripetere?")
```

### Recommended Project Structure
```
src/
├── main.py                  # entry point — CLI arg --tenant, loads config, starts runner
├── bot.py                   # async def bot(runner_args) — pipeline assembly
├── config/
│   ├── tenant_config.py     # TenantConfig Pydantic model
│   └── repository.py        # TenantRepository — aiosqlite CRUD, DB init
├── pipeline/
│   ├── factory.py           # TransportFactory + STTProvider factory
│   ├── observers.py         # MetricsObserver, ErrorObserver (BaseObserver subclasses)
│   └── fallback.py          # courtesy phrase injection logic
├── interfaces/
│   ├── calendar_provider.py # CalendarProvider ABC (stub — Phase 1)
│   └── notification_channel.py  # NotificationChannel ABC (stub — Phase 1)
├── db/
│   └── schema.sql           # CREATE TABLE tenants ... (full nullable schema)
├── .env.example
└── README.md
```

### Pattern 1: Pipeline Assembly (Pipecat 1.x)
**What:** Construct the streaming voice pipeline with correct import paths and settings API.
**When to use:** Core pipeline — this is the only pattern for Phase 1.
**Example:**
```python
# Source: docs.pipecat.ai/pipecat/learn/your-first-agent + official service docs
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.anthropic import AnthropicLLMService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport

async def build_pipeline(transport: SmallWebRTCTransport, tenant: TenantConfig):
    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramSTTService.Settings(
            model="nova-2",      # CLAUDE.md lock; upgrade to nova-3 when validating
            language="it",
            endpointing=300,     # 300ms silence → end-of-utterance signal to Deepgram
            interim_results=True,
            smart_format=False,
        ),
    )
    llm = AnthropicLLMService(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        settings=AnthropicLLMService.Settings(
            model=tenant.model or "claude-haiku-4-5-20251001",
            system_instruction=tenant.system_prompt,
        ),
    )
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsTTSService.Settings(
            voice=tenant.voice_id,
            model="eleven_multilingual_v2",
            language="it",
        ),
    )
    context = LLMContext()
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.7,
                    start_secs=0.2,
                    stop_secs=0.3,
                    min_volume=0.6,
                )
            ),
            user_turn_stop_timeout=0.2,  # CRITICAL: default 5s blows 800ms budget
        ),
    )
    pipeline = Pipeline([
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])
    return pipeline, context
```

### Pattern 2: Bot Speaks First (Greeting on Connection)
**What:** Inject the tenant greeting when the WebRTC client connects, with barge-in active immediately.
**When to use:** On every new connection; greeting text comes from `TenantConfig.greeting`.
**Example:**
```python
# Source: docs.pipecat.ai + pipecat frames reference
from pipecat.frames.frames import TTSSpeakFrame

@transport.event_handler("on_client_connected")
async def on_client_connected(transport, webrtc_connection):
    # TTSSpeakFrame goes directly to TTS — no LLM round-trip, lowest latency
    # append_to_context=True adds greeting to conversation history
    await worker.queue_frames([
        TTSSpeakFrame(text=tenant.greeting, append_to_context=True)
    ])
    # SileroVAD is already running — barge-in is active during the greeting
```

### Pattern 3: Per-Turn Latency Observer
**What:** Collect `MetricsFrame` data per turn; emit console line + JSONL.
**When to use:** Attached to `PipelineWorker` via `PipelineParams(observers=[...])`.
**Example:**
```python
# Source: docs.pipecat.ai/api-reference/server/utilities/observers/observer-pattern
import json, time
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import TTFBMetricsData, ProcessingMetricsData

class LatencyObserver(BaseObserver):
    def __init__(self, jsonl_path: str):
        self._jsonl_path = jsonl_path
        self._turn_start: float = 0.0
        self._stt_ms = self._llm_ttft_ms = self._tts_ttfb_ms = 0

    async def on_push_frame(self, data: FramePushed):
        if not isinstance(data.frame, MetricsFrame):
            return
        for metric in data.frame.data:
            src = data.source.lower()
            val_ms = int(metric.value * 1000)
            if isinstance(metric, TTFBMetricsData):
                if "deepgram" in src or "stt" in src:
                    self._stt_ms = val_ms
                elif "anthropic" in src or "llm" in src:
                    self._llm_ttft_ms = val_ms
                elif "elevenlabs" in src or "tts" in src:
                    self._tts_ttfb_ms = val_ms
            elif isinstance(metric, ProcessingMetricsData) and "transport" in src:
                pass  # transport processing captured separately if needed

    async def on_turn_ended(self, turn_duration_ms: int):
        line = (f"turn={turn_duration_ms}ms | "
                f"stt={self._stt_ms} llm_ttft={self._llm_ttft_ms} "
                f"tts_ttfb={self._tts_ttfb_ms}")
        print(line)
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "turn_ms": turn_duration_ms,
            "stt_ms": self._stt_ms,
            "llm_ttft_ms": self._llm_ttft_ms,
            "tts_ttfb_ms": self._tts_ttfb_ms,
        }
        with open(self._jsonl_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        if turn_duration_ms > 800:
            print(f"  [WARN] Turn exceeded 800ms budget!")
        self._stt_ms = self._llm_ttft_ms = self._tts_ttfb_ms = 0

# Attach to PipelineWorker:
worker = PipelineWorker(
    pipeline,
    params=PipelineParams(
        enable_metrics=True,
        enable_usage_metrics=True,
        observers=[LatencyObserver("logs/latency.jsonl")],
    ),
)
```

**Note on `on_turn_ended`:** The `BaseObserver` documented API includes `on_push_frame` and `on_process_frame`. Turn-boundary detection may require combining with `TurnTrackingObserver` from `pipecat.observers.turn_tracking_observer` or hooking `BotStoppedSpeakingFrame`. The exact hook for "turn ended" is `[ASSUMED]` — verify against Pipecat 1.4.0 source during implementation.

### Pattern 4: Error Fallback — Courtesy Phrase
**What:** Intercept `ErrorFrame` and inject Italian courtesy phrase to avoid dead-air.
**When to use:** Any STT/LLM/TTS service error or timeout (REL-01).
**Example:**
```python
# Source: pipecat ErrorFrame docs + BaseObserver pattern
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.frames.frames import ErrorFrame, TTSSpeakFrame

COURTESY_PHRASE = "Mi scusi, ho avuto un problema tecnico, può ripetere?"

class ErrorFallbackObserver(BaseObserver):
    def __init__(self, worker):
        self._worker = worker
        self._retry_counts: dict[str, int] = {}

    async def on_push_frame(self, data: FramePushed):
        if isinstance(data.frame, ErrorFrame) and not data.frame.fatal:
            src = data.source
            count = self._retry_counts.get(src, 0)
            if count < 1:  # D-07: one retry before courtesy phrase
                self._retry_counts[src] = count + 1
                # retry is handled by service internally for most cases
                # if service does NOT auto-retry, queue a service reset here
            else:
                self._retry_counts[src] = 0
                await self._worker.queue_frames([
                    TTSSpeakFrame(text=COURTESY_PHRASE, append_to_context=False)
                ])
```

**Note:** Service-level retry behavior varies by service implementation. The exact retry hook (whether Pipecat services auto-retry internally or require explicit re-queuing) is `[ASSUMED]` — verify during Wave 0. For Phase 1, a simpler approach may be: observer fires courtesy phrase on any non-fatal `ErrorFrame` without retry logic, since the user can speak again naturally.

### Pattern 5: Runner + SmallWebRTC Server Setup
**What:** Wire the Pipecat runner with `SmallWebRTCTransport` and the prebuilt browser UI.
**When to use:** `main.py` entry point.
**Example:**
```python
# Source: docs.pipecat.ai/api-reference/server/utilities/runner/guide.md
# and reference-server.pipecat.ai/en/latest/_modules/pipecat/runner/run.html
from pipecat.runner.run import main
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport
from pipecat.transports.base_transport import TransportParams
from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

async def bot(runner_args: RunnerArguments):
    if isinstance(runner_args, SmallWebRTCRunnerArguments):
        transport = SmallWebRTCTransport(
            webrtc_connection=runner_args.webrtc_connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )
    # ... build and run pipeline
    tenant_id = runner_args.cli_args.tenant  # from --tenant=demo
    tenant = await repo.get_tenant(tenant_id)
    pipeline, context = await build_pipeline(transport, tenant)
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, ...))
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()

if __name__ == "__main__":
    main()  # starts FastAPI server; serves /prebuilt/ UI at localhost:7860
```

The Pipecat dev runner auto-mounts `SmallWebRTCPrebuiltUI` and exposes `/api/offer` for WebRTC signaling. Browser connects to `http://localhost:7860/prebuilt/`.

### Pattern 6: TenantRepository (aiosqlite)
**What:** Async repository to load `TenantConfig` from SQLite by tenant ID.
**When to use:** Called at the start of each `bot()` invocation.
**Example:**
```python
# Source: aiosqlite docs (aiosqlite.omnilib.dev) + Pydantic v2 docs
import aiosqlite
from pydantic import BaseModel
from typing import Optional

class TenantConfig(BaseModel):
    id: str
    business_name: str
    greeting: str
    voice_id: str
    language: str = "it"
    system_prompt: str
    model: str = "claude-haiku-4-5-20251001"
    hours: Optional[str] = None
    services: Optional[str] = None
    booking_rules: Optional[str] = None
    transfer_number: Optional[str] = None
    kb_ref: Optional[str] = None
    notification_channel: Optional[str] = None

class TenantRepository:
    def __init__(self, db_path: str = "centralino.db"):
        self._db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    business_name TEXT NOT NULL,
                    greeting TEXT NOT NULL,
                    voice_id TEXT NOT NULL,
                    language TEXT DEFAULT 'it',
                    system_prompt TEXT NOT NULL,
                    model TEXT DEFAULT 'claude-haiku-4-5-20251001',
                    hours TEXT,
                    services TEXT,
                    booking_rules TEXT,
                    transfer_number TEXT,
                    kb_ref TEXT,
                    notification_channel TEXT
                )
            """)
            await db.commit()

    async def get_tenant(self, tenant_id: str) -> TenantConfig:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tenants WHERE id = ?", (tenant_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    raise ValueError(f"Tenant not found: {tenant_id}")
                return TenantConfig(**dict(row))
```

### Pattern 7: STTProvider Interface Seam
**What:** Switchable STT backend selectable by config, no auto-failover.
**When to use:** Factory function selects Deepgram or Whisper based on tenant/global config.
**Example:**
```python
# Source: training knowledge [ASSUMED] — standard ABC pattern
from abc import ABC, abstractmethod
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.whisper.stt import WhisperSTTService, Model
from pipecat.transcriptions.language import Language

class STTProvider(ABC):
    @abstractmethod
    def create_service(self) -> object:
        pass

class DeepgramProvider(STTProvider):
    def create_service(self):
        return DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            settings=DeepgramSTTService.Settings(
                model="nova-2", language="it",
                endpointing=300, interim_results=True,
            ),
        )

class WhisperProvider(STTProvider):
    def create_service(self):
        return WhisperSTTService(
            settings=WhisperSTTService.Settings(
                model=Model.LARGE_V3_TURBO,
                language=Language.IT,
                no_speech_prob=0.4,
            ),
        )

def get_stt_provider(config_key: str = "deepgram") -> STTProvider:
    return {"deepgram": DeepgramProvider, "whisper": WhisperProvider}[config_key]()
```

### Anti-Patterns to Avoid
- **`PipelineTask` + `PipelineRunner` imports:** These are pre-1.0 patterns. Pipecat 1.x uses `PipelineWorker` + `WorkerRunner`. Importing the old names causes `ImportError` or silently uses deprecated code paths.
- **`OpenAILLMContext` or provider-specific context classes:** Use `LLMContext` from `pipecat.processors.aggregators.llm_context`. Provider-specific context imports are removed in 1.x.
- **Flat service kwargs (`model=..., params=InputParams(...)`):** Deprecated as of 0.0.105; use `settings=ServiceClass.Settings(...)`.
- **`DISTIL_MEDIUM_EN` or `DISTIL_LARGE_V2` Whisper models:** English-only; will mistranscribe Italian. Use `Model.LARGE_V3_TURBO` with `Language.IT`.
- **ElevenLabs `language="it"` with a non-multilingual model:** Silently ignored. Always use `eleven_multilingual_v2` or another multilingual model with Italian.
- **Deepgram default model (`nova-3-general`) without `language="it"`:** Defaults to English — Italian recognition fails.
- **`user_turn_stop_timeout` left at default (5.0s):** Adds 5 seconds of silence wait before the LLM is triggered — budget is already over before the LLM even starts.
- **Skipping `SileroVADAnalyzer`:** No barge-in, no turn-taking, violates VOICE-03 and the <800ms requirement.
- **Installing pip package `pipecat-flows`:** Wrong name. Install `pipecat-ai-flows`; import as `pipecat_flows`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebRTC signaling + audio transport | Custom WebSocket audio bridge | `SmallWebRTCTransport` + runner | ICE negotiation, DTLS, SRTP, codec handling — thousands of edge cases |
| Voice activity detection | Energy-based VAD | `SileroVADAnalyzer` (Silero ONNX) | Model-based VAD is 10x more reliable; energy VAD breaks on background noise |
| Streaming STT → LLM context aggregation | Custom frame accumulator | `LLMContextAggregatorPair` | Handles partial transcripts, barge-in state, context history, turn boundaries |
| Pipeline error observation | Try/catch in each service | `BaseObserver` + `ErrorFrame` | Centralized; doesn't pollute hot-path; works uniformly across all services |
| Async SQLite | `sqlite3` + `asyncio.run_in_executor` | `aiosqlite` | Purpose-built async bridge; correct connection reuse semantics |
| Per-turn latency collection | `time.time()` probes in pipeline | Pipecat `MetricsFrame` + `PipelineParams(enable_metrics=True)` | Already measured by framework at exact service boundaries; no instrumentation code in hot path |

**Key insight:** The Pipecat pipeline frame model handles everything from audio transport to context management to barge-in interruption. Building any of these from scratch would take weeks and miss dozens of edge cases (partial transcripts, overlapping turns, audio buffer underflows, WebRTC reconnections).

---

## Common Pitfalls

### Pitfall 1: `user_turn_stop_timeout` Default Destroys Latency
**What goes wrong:** With the default `user_turn_stop_timeout=5.0s`, after the user stops speaking the pipeline waits 5 full seconds before sending the transcript to the LLM. The first response is 5+ seconds, which appears as an unresponsive bot.
**Why it happens:** The default is generous to accommodate slow transcription services and users who think mid-sentence. For a real-time voice agent it is catastrophic.
**How to avoid:** Set `user_turn_stop_timeout=0.2` in `LLMUserAggregatorParams`. Start at 0.2s; increase to 0.3s if users get cut off before finishing sentences.
**Warning signs:** First turn takes 5–6 seconds; subsequent turns feel instant. If you see this pattern, check this parameter first.

### Pitfall 2: Pipecat 1.x Imports Break on Pre-1.0 Tutorial Code
**What goes wrong:** Copying code from any tutorial, blog post, or GitHub example from before mid-2025 gives `ImportError` because `PipelineTask`, `PipelineRunner`, `OpenAILLMContext`, and `InputParams` no longer exist at those import paths.
**Why it happens:** Pipecat had a major breaking-change 1.0 release that renamed core classes.
**How to avoid:** Only use import paths from `docs.pipecat.ai` (1.x docs) or `reference-server.pipecat.ai`. Treat any code with `PipelineTask` or `OpenAILLMContext` as incompatible.
**Warning signs:** `ImportError: cannot import name 'PipelineTask' from 'pipecat.pipeline.task'`.

### Pitfall 3: VAD `stop_secs` vs `user_turn_stop_timeout` Confusion
**What goes wrong:** Setting `VADParams(stop_secs=0.2)` and thinking barge-in and turn-end are both configured. Actually `stop_secs` controls the VAD model's voice/silence boundary; `user_turn_stop_timeout` controls how long the aggregator waits after VAD says "silent" before submitting to LLM. Both must be tuned.
**How to avoid:** Set both: `VADParams(stop_secs=0.3)` and `LLMUserAggregatorParams(user_turn_stop_timeout=0.2)`. The VAD detects silence; the aggregator decides when the turn is complete.

### Pitfall 4: Python 3.13 Breaks ctranslate2 (faster-whisper dep)
**What goes wrong:** `pip install faster-whisper` on Python 3.13 fails with "no matching distribution" because `ctranslate2` has no 3.13 wheels yet.
**Why it happens:** `ctranslate2` (the CTranslate2 C++ inference engine) ships binary wheels; 3.13 wheels were not available as of research date.
**How to avoid:** Use Python 3.12 (or 3.11). The virtual env must be created with `--python 3.12` explicitly.
**Warning signs:** `ERROR: Could not find a version that satisfies the requirement ctranslate2`.

### Pitfall 5: ElevenLabs Voice ID Not Set → Default Voice
**What goes wrong:** If `voice_id` is empty/None in tenant config, `ElevenLabsTTSService` falls back to a default English voice — wrong language, wrong persona.
**How to avoid:** Validate `TenantConfig` with Pydantic `field(...)` that requires `voice_id` to be non-empty. Add a `demo` voice_id to the seed SQL.

### Pitfall 6: faster-whisper LARGE_V3_TURBO Downloads ~1.5GB Model on First Run
**What goes wrong:** First time `WhisperSTTService` starts, it downloads the large-v3-turbo model from HuggingFace Hub (~1.5GB). This hangs silently if there's no internet, or takes minutes and looks like the bot is frozen.
**How to avoid:** Pre-download the model explicitly in setup docs: `python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo')"`. Document this in README setup steps.

### Pitfall 7: TTSSpeakFrame After EndFrame is Swallowed
**What goes wrong:** If the pipeline ends (EndFrame) before the `TTSSpeakFrame` audio is fully flushed, the courtesy phrase or greeting is silently dropped.
**Why it happens:** `EndFrame` causes the transport to close before TTS completes playback.
**How to avoid:** For pipeline teardown, always flush TTS before sending `EndFrame`. For greeting injection, use `worker.queue_frames()` which respects pipeline ordering.

### Pitfall 8: Deepgram Italian Endpointing Too Aggressive
**What goes wrong:** Italian has longer average syllable duration than English. With Deepgram's default endpointing (300ms silence), short pauses in natural Italian speech (e.g., commas, listed items) trigger premature end-of-utterance, cutting users off mid-sentence.
**How to avoid:** Start with `endpointing=500` (500ms) for Italian and tune down. Watch for truncated transcripts in the console.

---

## Code Examples

### Full Service Configuration Cheatsheet
```python
# Source: docs.pipecat.ai/server/services/stt/deepgram (VERIFIED)
stt_deepgram = DeepgramSTTService(
    api_key=os.getenv("DEEPGRAM_API_KEY"),
    settings=DeepgramSTTService.Settings(
        model="nova-2",        # CLAUDE.md lock; nova-3 has better Italian WER
        language="it",
        endpointing=400,       # ms of silence → utterance end (start here for Italian)
        interim_results=True,  # enables streaming transcription
        smart_format=False,    # cleaner raw text for LLM
        punctuate=True,
    ),
)

# Source: docs.pipecat.ai/server/services/llm/anthropic (VERIFIED)
llm_anthropic = AnthropicLLMService(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    settings=AnthropicLLMService.Settings(
        model="claude-haiku-4-5-20251001",  # VERIFIED: platform.claude.com/docs/models
        system_instruction=tenant.system_prompt,
        max_tokens=1024,  # keep low for voice — long responses kill latency
    ),
)

# Source: docs.pipecat.ai/server/services/tts/elevenlabs (VERIFIED)
tts_elevenlabs = ElevenLabsTTSService(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
    settings=ElevenLabsTTSService.Settings(
        voice=tenant.voice_id,
        model="eleven_multilingual_v2",
        language="it",
        stability=0.5,         # voice consistency — adjust per voice_id
        similarity_boost=0.75, # voice clarity
        speed=1.0,             # 1.0 = normal; valid WebSocket range 0.7–1.2
    ),
)

# Source: docs.pipecat.ai/server/services/stt/whisper (VERIFIED)
stt_whisper = WhisperSTTService(
    settings=WhisperSTTService.Settings(
        model=Model.LARGE_V3_TURBO,
        language=Language.IT,
        no_speech_prob=0.4,
    ),
)
```

### Demo System Prompt
```python
# Demo tenant system prompt (D-09: constrained receptionist persona)
DEMO_SYSTEM_PROMPT = """Sei l'assistente vocale automatico di {business_name}.
Rispondi SEMPRE in italiano naturale e professionale.
Ti presenti come centralino automatico dell'attività.
Se ti chiedono di prenotare o di avere informazioni dettagliate su servizi/prezzi/orari,
rispondi educatamente che questa funzionalità sarà disponibile a breve.
Non inventare informazioni. Sii cordiale e conciso — sei in una conversazione telefonica.
Se il chiamante non parla italiano, scusati e proponi di richiamare con un operatore."""
```

### `.env.example` Content
```bash
# Deepgram API Key — create account at https://console.deepgram.com
# Free tier: 12,000 minutes/year
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# Anthropic API Key — create account at https://console.anthropic.com
# Billing required; Claude Haiku 4.5: $1/MTok input, $5/MTok output
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# ElevenLabs API Key — create account at https://elevenlabs.io
# Free tier: 10,000 characters/month
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# ElevenLabs Voice ID for demo tenant — find at elevenlabs.io/voice-library
# Recommended Italian voice: "Antoni" (ID: ErXwobaYiN019PkySvjV) or browse Italian voices
DEMO_VOICE_ID=ErXwobaYiN019PkySvjV
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `PipelineTask` + `PipelineRunner` | `PipelineWorker` + `WorkerRunner` | Pipecat 1.0 (early 2025) | All pre-1.0 tutorials are broken; must use new class names |
| `OpenAILLMContext` / provider-specific context | `LLMContext` + `LLMContextAggregatorPair` (universal) | Pipecat 1.0 | Single context works across providers; enables runtime LLM switching |
| Flat service kwargs `model=...`, `params=InputParams(...)` | `settings=ServiceClass.Settings(...)` | Pipecat 0.0.105 (deprecated), 1.0 (enforced) | Clean typed settings; old style still works with deprecation warning |
| `LocalAudioTransport` (PortAudio/sounddevice) | `SmallWebRTCTransport` + browser | Pipecat 1.x | No native audio deps; browser mic; same transport seam as telephony |
| Deepgram `nova-2` for Italian | Deepgram `nova-3` for Italian | Late 2024 / early 2025 | nova-3 now supports Italian with significantly better WER |
| `aggregation_timeout` parameter | `user_turn_stop_timeout` in `LLMUserAggregatorParams` | Pipecat 0.0.x → 1.x API rename | Default changed too (was ~1s in 0.0.x; now 5.0s in 1.x) |

**Deprecated/outdated:**
- `pipecat-flows` pip name: Wrong. Install `pipecat-ai-flows`, import `pipecat_flows`.
- `InputParams` / `TTSParams` style constructors: Replaced by nested `.Settings` class pattern.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `on_turn_ended` is a valid `BaseObserver` hook or can be replicated via `TurnTrackingObserver` | Architecture Patterns §3 | Per-turn latency log may need different event hook; console line format still achievable but wiring changes |
| A2 | Service-level `ErrorFrame` retry: services may auto-retry internally; pattern assumes application-level observer intercepts non-fatal errors | Architecture Patterns §4 | Retry logic may need to be implemented differently if services raise exceptions rather than emitting ErrorFrames |
| A3 | `worker.queue_frames([TTSSpeakFrame(...)])` is the correct API on `PipelineWorker` (vs `PipelineTask.queue_frames` in 0.0.x) | Pattern 2 (greeting) | If `PipelineWorker` uses different method name, greeting injection breaks — verify in Wave 0 |
| A4 | `SmallWebRTCPrebuiltUI` auto-mount happens via Pipecat runner; `main()` handles it without manual FastAPI route setup | Pattern 5 (runner) | May need manual `app.mount("/prebuilt", SmallWebRTCPrebuiltUI)` in FastAPI app |
| A5 | `FramePushed.source` contains service class name (e.g., "deepgram", "anthropic") as substring — used to route metrics to correct buckets | Pattern 3 (observer) | Source naming convention may differ; observer logic needs verification via debug print in Wave 0 |
| A6 | 8 Pipecat-ecosystem packages (`pipecat-ai`, `pipecat-ai-flows`, etc.) are legitimate — slopcheck registry was unreachable at research time | Package Legitimacy Audit | Low risk: all confirmed via pip index versions + official org attribution; slopcheck confirmation is belt-and-suspenders |
| A7 | `endpointing=400` (400ms) is a reasonable Italian-language starting point for Deepgram | Pitfall 8, Code Examples | May need adjustment; 300ms may work fine, or 500ms may be needed — tune during dev |

---

## Open Questions (RESOLVED)

> All four items below are framework-API/empirical uncertainties, not planning blockers. Each is resolved with a concrete default plus a Wave 0 in-task verification step (written into the corresponding plan task actions). None gate planning.

1. **`BaseObserver.on_turn_ended` — does it exist?**
   - What we know: `BaseObserver` has `on_push_frame`, `on_process_frame`, `on_pipeline_started`.
   - What's unclear: Whether there is a dedicated "turn ended" hook or if this must be inferred from `BotStoppedSpeakingFrame` in `on_push_frame`.
   - Recommendation: In Wave 0, add a debug observer that prints all frame types flowing through; identify the right hook. Fall back to intercepting `BotStoppedSpeakingFrame` if needed.
   - **RESOLVED:** Use `BotStoppedSpeakingFrame` detection in `on_push_frame` as the primary turn-end signal; verify/swap to a dedicated `TurnTrackingObserver` hook during Wave 0 (Plan 01-03 Task 1 debug-observer step). Latency observer does not block on this — both paths emit the same per-turn line.

2. **`worker.queue_frames()` exact API on `PipelineWorker`**
   - What we know: `PipelineTask.queue_frames()` existed in 0.0.x. `PipelineWorker` is the 1.x replacement.
   - What's unclear: Whether `PipelineWorker` exposes the same `queue_frames()` method or uses a different approach (e.g., via the bus).
   - Recommendation: Check `reference-server.pipecat.ai/en/stable/api/pipecat.pipeline.worker.html` during Wave 0 task.
   - **RESOLVED:** Use `worker.queue_frames()` for the greeting `TTSSpeakFrame`; if the method name differs in 1.4.0, fall back to pipeline-bus injection. Verified in Plan 01-02 Task 2 before reliance (flagged `[ASSUMED]` in the task action).

3. **nova-3 Italian status at implementation time**
   - What we know: As of 2026-06-23, nova-3 supports Italian with better WER than nova-2 (verified via Deepgram docs). CLAUDE.md locks to nova-2.
   - What's unclear: Whether the project owner wants to use nova-3 given the verified improvement.
   - Recommendation: Planner should create a task to swap `model="nova-2"` → `model="nova-3"` as an explicit upgrade task. It is a one-line change.
   - **RESOLVED:** Honor the CLAUDE.md `nova-2` lock for Phase 1. The nova-3 Italian improvement is surfaced as a config comment in `factory.py` (`# nova-3 now supports Italian with lower WER — owner may opt in`), no code gate. Owner decides in a later phase.

4. **ElevenLabs voice_id for demo tenant**
   - What we know: The `.env.example` needs a real voice_id; ElevenLabs pre-made Italian voices exist.
   - What's unclear: Which specific Italian voice to use as the demo default.
   - Recommendation: Use "Antoni" (ElevenLabs pre-made Italian-capable male voice) or "Serena" for female. Owner should validate voice quality.
   - **RESOLVED:** Use a `DEMO_VOICE_ID` env var in `.env.example` with a documented pre-made Italian-capable default; owner validates voice quality during the Plan 01-02/01-03 live-smoke checkpoint before Phase 2.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | `pipecat-ai`, `faster-whisper`/`ctranslate2` | ✗ (system has 3.9 + 3.13) | 3.9.13 / 3.13.1 | Must install 3.12 via pyenv/official installer — no fallback |
| Node.js | Dev tools only (not required for bot) | ✓ | v23.3.0 | — |
| `uv` package manager | Fast installs (recommended) | — | unknown | Use `pip` + `venv` instead |
| Deepgram API key | STT | ✗ | — | Whisper fallback (requires model download) |
| Anthropic API key | LLM | ✗ | — | None — bot cannot function |
| ElevenLabs API key | TTS | ✗ | — | None — bot cannot function |
| ngrok / cloudflared | Not needed in Phase 1 (local WebRTC, no Telnyx) | — | — | — |

**Missing dependencies with no fallback:**
- **Python 3.12** — system has 3.13.1 and 3.9.13, neither suitable. The plan MUST include a "Install Python 3.12 and create venv" task as Wave 0 step 1.
- **API keys (Deepgram, Anthropic, ElevenLabs)** — all three required for full end-to-end test. Phase 1 gate (success criterion 1) requires all three.

**Missing dependencies with fallback:**
- Deepgram → `WhisperSTTService` (if Deepgram key unavailable, select `stt_provider=whisper` in config; requires faster-whisper model download)

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (standard Python; no framework installed yet) |
| Config file | `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` — Wave 0 |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VOICE-01 | Pipeline assembles without exception | unit | `pytest tests/test_pipeline.py::test_pipeline_builds -x` | ❌ Wave 0 |
| VOICE-01 | STT → LLM → TTS frame flow propagates | integration | `pytest tests/test_pipeline.py::test_frame_flow -x` | ❌ Wave 0 |
| VOICE-02 | Greeting injected on connect | unit | `pytest tests/test_bot.py::test_greeting_injected -x` | ❌ Wave 0 |
| VOICE-03 | Barge-in: VAD configured with correct stop_secs | unit | `pytest tests/test_pipeline.py::test_vad_params -x` | ❌ Wave 0 |
| VOICE-04 | `user_turn_stop_timeout` is ≤ 0.3s | unit | `pytest tests/test_pipeline.py::test_aggregator_timeout -x` | ❌ Wave 0 |
| VOICE-04 | LatencyObserver emits metrics line | unit | `pytest tests/test_observers.py::test_latency_observer -x` | ❌ Wave 0 |
| VOICE-05 | TTS uses `voice_id` from tenant config | unit | `pytest tests/test_pipeline.py::test_tts_voice_id -x` | ❌ Wave 0 |
| REL-01 | ErrorFrame triggers courtesy phrase | unit | `pytest tests/test_observers.py::test_error_fallback -x` | ❌ Wave 0 |
| SETUP-01 | `.env.example` contains all 3 required keys | unit | `pytest tests/test_setup.py::test_env_example -x` | ❌ Wave 0 |
| D-01/D-02 | TenantRepository loads demo tenant from SQLite | unit | `pytest tests/test_repository.py::test_load_demo_tenant -x` | ❌ Wave 0 |
| D-02 | tenants table has all nullable columns | unit | `pytest tests/test_repository.py::test_schema_columns -x` | ❌ Wave 0 |
| SUCCESS-1 | End-to-end: `main.py --tenant=demo` runs (smoke) | smoke | Manual — requires live API keys | Manual only |
| SUCCESS-2 | Barge-in works in browser (live mic) | e2e | Manual — requires live API keys + browser | Manual only |
| SUCCESS-3 | Latency log shows < 800ms turns | e2e | Manual — verify JSONL file during live test | Manual only |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q` (unit tests only, < 5 seconds)
- **Per wave merge:** `pytest tests/ -v --tb=short` (full unit + integration)
- **Phase gate:** Full suite green + manual smoke test before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pipeline.py` — covers VOICE-01, VOICE-03, VOICE-04, VOICE-05
- [ ] `tests/test_bot.py` — covers VOICE-02
- [ ] `tests/test_observers.py` — covers VOICE-04 (metrics), REL-01 (error fallback)
- [ ] `tests/test_repository.py` — covers D-01, D-02 (SQLite schema + CRUD)
- [ ] `tests/test_setup.py` — covers SETUP-01 (.env.example validation)
- [ ] `tests/conftest.py` — shared fixtures (mock transport, mock tenant config, mock API clients)
- [ ] Framework install: `uv pip install pytest pytest-asyncio` — Wave 0 prerequisite

---

## Security Domain

> `security_enforcement` not explicitly set in config → treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No — no user auth in Phase 1 local mode | — |
| V3 Session Management | No — single local session, no tokens | — |
| V4 Access Control | No — single tenant, local only | — |
| V5 Input Validation | Yes — tenant ID from CLI arg | Pydantic TenantConfig validates all fields; CLI arg passed to parameterized SQL query |
| V6 Cryptography | No — no encryption in Phase 1 | — |
| V7 Error Handling | Yes — error messages must not leak API keys | ErrorFrame / observer must not log raw exception objects that contain API responses |
| V9 Communications | Partial — API calls to Deepgram/Anthropic/ElevenLabs use HTTPS | All three SDKs use HTTPS by default; no manual SSL config needed |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `--tenant` CLI arg | Tampering | Parameterized query (`WHERE id = ?`) — never string-format tenant_id into SQL |
| API key leakage in logs | Information Disclosure | Never log raw `os.getenv("*_API_KEY")`; log only the last 4 chars for debugging |
| Dependency confusion (pipecat-ai vs pipecat) | Tampering | Install only from official PyPI; pin versions in requirements.txt / pyproject.toml |

---

## Sources

### Primary (HIGH confidence)
- `docs.pipecat.ai/pipecat/learn/your-first-agent` — PipelineWorker, WorkerRunner, pipeline assembly, LLMContextAggregatorPair
- `docs.pipecat.ai/api-reference/server/services/stt/deepgram` — DeepgramSTTService, Settings, endpointing, language
- `docs.pipecat.ai/server/services/llm/anthropic` — AnthropicLLMService, Settings, model IDs
- `docs.pipecat.ai/server/services/tts/elevenlabs` — ElevenLabsTTSService, Settings, voice, eleven_multilingual_v2
- `docs.pipecat.ai/server/services/stt/whisper` — WhisperSTTService, Model.LARGE_V3_TURBO, Language.IT
- `docs.pipecat.ai/server/utilities/audio/silero-vad-analyzer` — SileroVADAnalyzer, VADParams, stop_secs
- `docs.pipecat.ai/pipecat/learn/speech-input` — turn detection, SileroVADAnalyzer, barge-in
- `docs.pipecat.ai/api-reference/server/utilities/observers/observer-pattern` — BaseObserver, on_push_frame, FramePushed
- `reference-server.pipecat.ai/en/stable/api/pipecat.processors.aggregators.llm_response_universal.html` — LLMContextAggregatorPair, LLMUserAggregatorParams full constructor
- `reference-server.pipecat.ai/en/stable/api/pipecat.frames.frames.html` — TTSSpeakFrame, LLMRunFrame, MetricsFrame, ErrorFrame
- `docs.pipecat.ai/api-reference/server/workers/runner.md` — WorkerRunner constructor, add_workers, run
- `reference-server.pipecat.ai/en/latest/_modules/pipecat/runner/run.html` — main(), RunnerArguments subclasses
- `docs.pipecat.ai/api-reference/server/utilities/runner/guide.md` — dev runner FastAPI server, transport_params pattern
- `docs.pipecat.ai/pipecat/fundamentals/metrics` — MetricsFrame, TTFBMetricsData, MetricsLogObserver, TurnTrackingObserver
- `platform.claude.com/docs/en/about-claude/models/overview` — claude-haiku-4-5-20251001 model ID (VERIFIED 2026-06-23)
- `developers.deepgram.com/docs/models-languages-overview` — nova-2 and nova-3 Italian support confirmed
- PyPI `pip index versions` — pipecat-ai 1.4.0, pipecat-ai-flows 1.3.0, aiosqlite 0.22.1, faster-whisper 1.2.1, deepgram-sdk 7.3.1, anthropic 0.111.0, pipecat-ai-small-webrtc-prebuilt 2.5.0 (all VERIFIED)

### Secondary (MEDIUM confidence)
- `deepgram.com/learn/deepgram-expands-nova-3-with-italian-turkish-norwegian-and-indonesian-support` — nova-3 Italian double-digit WER improvement over nova-2
- `docs.pipecat.ai/guides/features/metrics` — enable_metrics, MetricsFrame usage patterns

### Tertiary (LOW confidence)
- Training knowledge: ABC/Protocol pattern for `STTProvider`, `TransportFactory`, `CalendarProvider`, `NotificationChannel` seams — standard Python patterns, not Pipecat-specific
- Training knowledge: `aiosqlite` repository pattern — standard Python async SQLite; confirmed API via aiosqlite.omnilib.dev

---

## Metadata

**Confidence breakdown:**
- Standard stack (versions, package names): HIGH — all verified via PyPI + official docs
- Pipeline assembly (PipelineWorker, imports, pipeline order): HIGH — verified via official Pipecat docs
- VAD / barge-in parameters: HIGH (parameters documented) / MEDIUM (optimal values for Italian require empirical tuning)
- Metrics / observer pattern: HIGH (BaseObserver API verified) / MEDIUM (on_turn_ended hook exact signature assumed)
- Error fallback pattern: MEDIUM — ErrorFrame behavior documented; retry mechanism details assumed
- Anthropic model IDs: HIGH — verified via official Anthropic models page 2026-06-23
- Deepgram nova-3 Italian support: HIGH — verified via official Deepgram docs
- SQLite repository pattern: MEDIUM — standard Python; aiosqlite API verified

**Research date:** 2026-06-23
**Valid until:** 2026-07-23 (stable framework — Pipecat 1.x unlikely to introduce breaking changes within 30 days; Anthropic model IDs are pinned snapshots)
