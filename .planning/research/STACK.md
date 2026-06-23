# Stack Research

**Domain:** Self-hosted multi-tenant AI voice telephony receptionist (Italian) — Pipecat voice pipeline
**Researched:** 2026-06-23
**Confidence:** HIGH (all versions and import paths verified against Context7 `/pipecat-ai/docs` and live PyPI as of June 2026)

> Scope note: The core providers (Pipecat, Deepgram, Anthropic Claude, ElevenLabs, Telnyx, Google Calendar, SQLite→Postgres, faster-whisper) are FIXED owner decisions. This file verifies CURRENT versions, exact Pipecat classes/imports, env vars, and Italian-language config — it does not propose alternatives to the core choices. "Alternatives" and "What NOT to Use" sections cover only *supporting* choices and version traps.

---

## CRITICAL VERSION NOTE — read first

Pipecat shipped a **major rewrite at v1.0**. As of June 2026 PyPI shows:

- `pipecat-ai` **1.4.0** (released 2026-06-17) — the old `0.0.x` series (0.0.108, March 2026) is the *pre-1.0* line.
- `pipecat-ai-flows` **1.3.0** (released 2026-06-18) — the Flows add-on, also bumped to 1.x to match.

The 1.x API differs from most older tutorials/training data. The verified 1.x surface used below:
- Pipeline runner is `PipelineWorker` + `WorkerRunner` (older code used `PipelineTask` + `PipelineRunner`).
- Context is `LLMContext` + `LLMContextAggregatorPair` from `pipecat.processors.aggregators.llm_response_universal` (older code used provider-specific `OpenAILLMContext` etc.).
- Services are configured with a `settings=ServiceClass.Settings(...)` object; the older flat kwargs (`model=`, `params=InputParams(...)`) are **deprecated as of 0.0.105** but still accepted.

**Pin exact versions** (`pipecat-ai==1.4.0`, `pipecat-ai-flows==1.3.0`) and follow current docs at docs.pipecat.ai, not training memory.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | **3.11 or 3.12** | Runtime | `pipecat-ai` 1.4.0 requires `>=3.11`. Use 3.11/3.12 (3.13 not yet broadly validated across the audio/ML deps like `faster-whisper`/`ctranslate2`). FIXED ecosystem. |
| **pipecat-ai** | **1.4.0** | Voice-agent orchestration pipeline | Owner-fixed. The 1.x line is the current, actively-developed framework for real-time STT→LLM→TTS pipelines with VAD/barge-in. |
| **pipecat-ai-flows** | **1.3.0** | Structured conversation flows (booking flow, FAQ routing) | Owner-fixed. Add-on package (note: PyPI name is `pipecat-ai-flows`, the *import* is `pipecat_flows`). Provides `FlowManager` + node graph so each step (date→time→party size→name→phone) exposes only the tools it needs. |
| **deepgram-sdk** | **>=6.1.1,<8** (pulled by `pipecat-ai[deepgram]`) | Primary STT (Italian, streaming) | Owner-fixed. `DeepgramSTTService` wraps it. Low-latency interim results + finalize-on-VAD. |
| **anthropic** | **>=0.49.0,<1** (pulled by `pipecat-ai[anthropic]`) | LLM "brain" with tool calling | Owner-fixed. `AnthropicLLMService` wraps the async SDK; native function/tool calling integrates with Pipecat Flows. |
| **ElevenLabs (via `pipecat-ai[elevenlabs]`)** | service ships in pipecat 1.4.0 (no extra pip dep — uses core `websockets`/`aiohttp`) | TTS (Italian, per-client voice cloning) | Owner-fixed. `ElevenLabsTTSService` (WebSocket, streaming, lowest latency) with `eleven_multilingual_v2` + per-client `voice_id`. |
| **Telnyx (via `pipecat.serializers.telnyx`)** | serializer + transport ship in pipecat 1.4.0 (no extra pip dep — uses core `websockets`) | Telephony (Italian geographic numbers) | Owner-fixed. `TelnyxFrameSerializer` over a WebSocket transport implements Telnyx Media Streaming. Abstract behind your own `TelephonyProvider` interface so Twilio (`TwilioFrameSerializer`) swaps in. |
| **faster-whisper** | **~=1.2.1** (pulled by `pipecat-ai[whisper]`) | Self-hosted STT fallback | Owner-fixed. `WhisperSTTService` runs faster-whisper locally (CPU/CUDA) for provider-independence if Deepgram fails. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pipecat-ai[silero]` (Silero VAD) | ships in 1.4.0 (extra is empty, model downloaded at runtime) | Voice activity detection → enables barge-in & turn-taking | Always. `SileroVADAnalyzer` is passed into `LLMUserAggregatorParams`. Required for the <800ms / interruption requirements. |
| `pipecat-ai[webrtc]` (`aiortc>=1.14.0,<2`, `opencv-python>=4.11.0.86,<5`) | per pipecat 1.4.0 extras | Local browser/WebRTC testing transport (Milestone 1: mic/headset) | Use for local dev before telephony is wired. `SmallWebRTCTransport` / runner WebRTC. |
| `fastapi` + `uvicorn` | FastAPI `>=0.115`, uvicorn `>=0.30` | HTTP/WebSocket server that Telnyx connects its media stream to | Required for Telnyx telephony. `FastAPIWebsocketTransport` + `FastAPIWebsocketParams`. |
| `google-api-python-client` + `google-auth-oauthlib` + `google-auth-httplib2` | `google-api-python-client>=2.x` | Real Google Calendar integration behind `CalendarProvider` | Booking phase. Service-account or OAuth per-tenant calendar. |
| `python-dotenv` | `>=1.0` | Load `.env` (all API keys; no hardcoding) | Always. |
| `pydantic` | `>=2.10.6,<3` (core pipecat dep) | Tenant config models / settings validation | Reuse for the per-client config records (multi-tenant). |
| `aiosqlite` | `>=0.20` | Async SQLite access for config/call-log persistence | v1 persistence. Code structured so the same repository interface targets Postgres (`asyncpg`/SQLAlchemy) later. |
| SMTP (`aiosmtplib`), Telegram (`python-telegram-bot` or raw Bot API), SMS/WhatsApp (Telnyx Messaging API / Twilio / Meta WhatsApp) | latest | Multi-channel notification layer (per-client) | End-of-call summary dispatch. Abstract behind a `NotificationChannel` interface. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` (or `pip` + venv) | Dependency management / fast installs | `uv` is the current standard for Pipecat projects; resolves the heavy ML deps quickly. |
| Pipecat **runner** (`pipecat-ai[runner]`) | Local dev runner with auto transport selection | `from pipecat.runner.run import main` + `create_transport`; lets one bot file serve WebRTC (local) and telephony (prod). |
| `ruff` + `mypy` | Lint / type-check | Standard for a typed async Python codebase. |
| ngrok / cloudflared | Expose local WebSocket for Telnyx media streaming during dev | Telnyx needs a public `wss://` URL to stream audio to your dev box. |

---

## Exact Pipecat integration surface (1.x)

### STT — Deepgram (primary, Italian)
```python
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transcriptions.language import Language

stt = DeepgramSTTService(
    api_key=os.getenv("DEEPGRAM_API_KEY"),
    settings=DeepgramSTTService.Settings(
        model="nova-2",          # nova-2 has broad multilingual incl. Italian; nova-3 defaults English-centric
        language=Language.IT,    # Italian
        smart_format=True,
        punctuate=True,
        interim_results=True,    # low-latency partials for barge-in
    ),
)
```
Italian notes (HIGH confidence): Deepgram default model is `nova-3-general` / default language `Language.EN`. **You must set `language` to Italian explicitly.** For Italian, `nova-2` is the safe, well-supported choice; verify `nova-3` Italian coverage against Deepgram's current model/language matrix before switching. `language="multi"` enables multilingual auto-detect, but v1 is Italian-only so pin `IT` for best accuracy. Telephony audio is 8kHz μ-law — Pipecat/Deepgram handle the rate via the transport; no manual resample needed.

### LLM — Anthropic Claude (tool calling)
```python
from pipecat.services.llm.anthropic import AnthropicLLMService

llm = AnthropicLLMService(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    settings=AnthropicLLMService.Settings(
        model="claude-sonnet-4-5-20250929",   # verify current model id at call-build time
        system_instruction="Sei il centralino telefonico di {business}. Parla solo italiano...",
        max_tokens=1024,
        enable_prompt_caching=True,           # cache the per-tenant system prompt / KB
    ),
)
```
Notes: import path is `pipecat.services.llm.anthropic` in 1.x. Tool calling is wired via Pipecat Flows function schemas (`FlowsFunctionSchema` / direct functions) or `register_function`. Use Sonnet-class for latency; confirm the exact current `claude-...` model id when building (model ids change — do not hardcode from memory without checking).

### TTS — ElevenLabs (Italian, per-client voice cloning)
```python
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.transcriptions.language import Language

tts = ElevenLabsTTSService(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
    settings=ElevenLabsTTSService.Settings(
        voice=client_config.voice_id,     # per-tenant cloned voice_id
        model="eleven_multilingual_v2",   # REQUIRED for the language param to take effect
        language=Language.IT,
        stability=0.5,
        similarity_boost=0.8,
        speed=1.0,
    ),
)
```
Italian notes (HIGH confidence): The `language` parameter is **only honored on multilingual models** — `eleven_multilingual_v2` (or the current `eleven_turbo_v2_5`/`flash` multilingual variants for lower latency) must be used; non-multilingual models silently ignore `language`. Per-client cloning = create a voice in the ElevenLabs dashboard/API, store its `voice_id` in the tenant config, pass as `voice=`. Prefer the **WebSocket** `ElevenLabsTTSService` (streaming) over `ElevenLabsHttpTTSService` for low latency; the HTTP variant exists and needs an `aiohttp_session=`.

### Telephony — Telnyx (behind your interface)
```python
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport, FastAPIWebsocketParams,
)
from pipecat.runner.utils import parse_telephony_websocket

transport_type, call_data = await parse_telephony_websocket(websocket)
serializer = TelnyxFrameSerializer(
    stream_id=call_data["stream_id"],
    outbound_encoding="PCMU",
    inbound_encoding="PCMU",
    call_control_id=call_data["call_control_id"],
    api_key=os.getenv("TELNYX_API_KEY"),
)
transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,
        serializer=serializer,
    ),
)
```
How Telnyx connects (HIGH confidence): Telnyx uses **WebSocket media streaming, not raw SIP, into Pipecat.** Telnyx terminates the PSTN call and (via TeXML / Call Control) opens a **bidirectional WebSocket** to your FastAPI endpoint, streaming **8kHz PCMU (μ-law)** audio frames. `TelnyxFrameSerializer` decodes/encodes those frames and DTMF; `call_control_id` + `api_key` enable auto-hang-up and call-control actions (e.g. transfer to human). Your `TelephonyProvider` interface wraps serializer choice so swapping in `TwilioFrameSerializer` (`pipecat.serializers.twilio`) needs no business-logic changes. SIP/SIP-trunk is *not* the Pipecat integration path here.

### STT fallback — faster-whisper (self-hosted)
```python
from pipecat.services.whisper.stt import WhisperSTTService, Model
from pipecat.transcriptions.language import Language

stt_fallback = WhisperSTTService(
    device="cuda",            # or "cpu" / "auto"
    compute_type="float16",   # "int8" for CPU
    settings=WhisperSTTService.Settings(
        model=Model.LARGE,    # large-v3 for best Italian; DISTIL_* are English-only
        language=Language.IT,
    ),
)
```
Notes: `WhisperSTTService` is faster-whisper (`faster-whisper~=1.2.1`, ctranslate2 backend), fully local. For Italian choose `Model.LARGE` (large-v3) or `LARGE_V3_TURBO` — **avoid `DISTIL_MEDIUM_EN`/`DISTIL_LARGE_V2`, which are English-only.** GPU (`cuda`+`float16`) strongly recommended to stay near the latency budget; CPU+`int8` works but is slower. Wrap Deepgram and Whisper behind a common `STTProvider` so the fallback is a config switch.

### Pipecat Flows (booking / FAQ orchestration)
```python
from pipecat_flows import FlowManager, FlowsFunctionSchema   # import name is pipecat_flows

flow_manager = FlowManager(
    worker=worker,                       # PipelineWorker (was `task=` pre-1.x — deprecated)
    llm=llm,
    context_aggregator=context_aggregator,
    transport=transport,
    global_functions=[transfer_to_human],  # available at every node (e.g. transfer)
)

@transport.event_handler("on_client_connected")
async def _(transport, client):
    await flow_manager.initialize(create_greeting_node())
```
Packaging/versioning (HIGH confidence): Flows is a **separate package** (`pip install pipecat-ai-flows`, currently **1.3.0**) that imports as **`pipecat_flows`**. It is an add-on layered on `pipecat-ai`; keep the two in step (Flows 1.3.0 targets Pipecat 1.x). It supplies `FlowManager` and a node graph so each conversation step exposes only its relevant tools — directly serving the structured booking flow and "transfer to human from anywhere" requirement via `global_functions`.

---

## Installation

```bash
# Python 3.11 or 3.12, in a venv (uv recommended)
uv venv --python 3.12 && source .venv/bin/activate   # or: python -m venv .venv

# Core pipeline + all fixed providers (extras enable each service)
uv pip install "pipecat-ai[deepgram,anthropic,elevenlabs,silero,webrtc,whisper,runner]==1.4.0"

# Structured flows add-on
uv pip install "pipecat-ai-flows==1.3.0"

# Server (Telnyx media-stream endpoint) + supporting libs
uv pip install fastapi "uvicorn[standard]" python-dotenv aiosqlite \
    google-api-python-client google-auth-oauthlib google-auth-httplib2 \
    aiosmtplib

# Dev
uv pip install ruff mypy
```

`.env.example` keys: `DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `TELNYX_API_KEY`, plus `GOOGLE_APPLICATION_CREDENTIALS` (or per-tenant OAuth tokens), and notification creds (SMTP host/user/pass, `TELEGRAM_BOT_TOKEN`, SMS/WhatsApp keys). No keys are committed; all loaded via `python-dotenv`.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Deepgram `nova-2` Italian | Deepgram `nova-3` / `language="multi"` | Only if Deepgram's current matrix confirms nova-3 Italian parity, or if you later support mixed-language callers (out of v1 scope). |
| ElevenLabs `eleven_multilingual_v2` | `eleven_turbo_v2_5` / `flash_v2_5` (multilingual) | If TTS latency dominates the budget — turbo/flash trade a little quality for speed; both still honor `language=IT`. |
| `ElevenLabsTTSService` (WebSocket) | `ElevenLabsHttpTTSService` | Only where you cannot hold a WS (simple request/response); needs `aiohttp_session=`. WS is lower latency — default to it. |
| `WhisperSTTService` (faster-whisper) GPU | CPU `int8`, or `MLXWhisperSTTService` (Apple Silicon) | CPU for low-volume/dev; MLX only on Mac dev machines. |
| SQLite (`aiosqlite`) now | Postgres (`asyncpg`/SQLAlchemy) | At multi-instance scale or concurrent writes; keep the repository interface DB-agnostic so this is a config swap (owner-stated migration path). |
| Telnyx | Twilio (`TwilioFrameSerializer`) | Swap behind `TelephonyProvider` if Telnyx Italian number availability/pricing is worse; Pipecat supports both first-class. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Pipecat `0.0.x` tutorials / `PipelineTask` + `PipelineRunner` + `OpenAILLMContext` patterns | Pre-1.0 API. 1.x renamed to `PipelineWorker`/`WorkerRunner` and unified context (`LLMContext`/`LLMContextAggregatorPair`). Copy-pasting old code breaks. | Pipecat **1.4.0** docs at docs.pipecat.ai; the imports shown above. |
| Flat service kwargs (`model=...`, `params=InputParams(...)`) | Deprecated as of 0.0.105; noisy warnings and future removal. | `settings=ServiceClass.Settings(...)`. |
| Whisper `DISTIL_MEDIUM_EN` / `DISTIL_LARGE_V2` | English-only models — will mistranscribe Italian. | `Model.LARGE` (large-v3) or `LARGE_V3_TURBO` with `language=Language.IT`. |
| ElevenLabs non-multilingual models with `language=IT` | `language` is silently ignored; wrong pronunciation. | `eleven_multilingual_v2` (or turbo/flash multilingual). |
| Deepgram defaults (`nova-3-general`, `Language.EN`) left unchanged | Defaults to English — Italian recognition fails. | Explicit `model="nova-2"`, `language=Language.IT`. |
| Treating Telnyx as a SIP integration into Pipecat | Pipecat's Telnyx path is WebSocket media streaming (PCMU 8kHz), not a SIP endpoint. | `TelnyxFrameSerializer` + `FastAPIWebsocketTransport`. |
| Pip name `pipecat-flows` / import `pipecat-ai-flows` | Wrong on both sides. | **Install** `pipecat-ai-flows`, **import** `pipecat_flows`. |
| Skipping a VAD analyzer | No barge-in, poor turn-taking — violates the <800ms / interruption requirement. | `SileroVADAnalyzer` in `LLMUserAggregatorParams`. |

---

## Stack Patterns by Variant

**If running locally for Milestone 1 (mic/headset, no phone yet):**
- Use the `runner` + WebRTC/`SmallWebRTCTransport` transport.
- Same `stt → aggregator.user() → llm → tts → aggregator.assistant()` pipeline; only the transport differs. Telnyx is added later with no pipeline change.

**If telephony is live (Telnyx):**
- FastAPI app exposes a `wss://` endpoint; Telnyx TeXML/Call Control points the media stream at it.
- `TelnyxFrameSerializer` (PCMU 8kHz) + `FastAPIWebsocketTransport`; pipeline body unchanged.

**If Deepgram is unavailable / provider-independence test:**
- Swap `STTProvider` implementation to `WhisperSTTService` (faster-whisper) via tenant/global config; rest of pipeline untouched.

**If scaling beyond a single node / heavier concurrency:**
- Move persistence from `aiosqlite` to Postgres (`asyncpg` + SQLAlchemy) behind the existing repository interface; no domain-logic change.

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `pipecat-ai==1.4.0` | Python `>=3.11` (use 3.11/3.12) | 3.13 unverified for the ML/audio deps; avoid for now. |
| `pipecat-ai-flows==1.3.0` | `pipecat-ai` 1.x | Keep in lockstep with the 1.x line; imports as `pipecat_flows`. |
| `pipecat-ai[anthropic]` | `anthropic>=0.49.0,<1` | SDK pinned `<1`; don't force `anthropic>=1`. |
| `pipecat-ai[deepgram]` | `deepgram-sdk>=6.1.1,<8` | |
| `pipecat-ai[whisper]` | `faster-whisper~=1.2.1` (ctranslate2) | GPU build needs matching CUDA/cuDNN for `float16`. |
| `pipecat-ai[webrtc]` | `aiortc>=1.14.0,<2`, `opencv-python>=4.11.0.86,<5` | Dev/local transport. |
| `pipecat-ai[elevenlabs]` / `[silero]` / Telnyx serializer | no extra pip deps (use core `websockets`/`aiohttp`) | Services/serializer ship inside `pipecat-ai`. |

---

## Sources

- Context7 `/pipecat-ai/docs` — Deepgram STT, ElevenLabs TTS, Anthropic LLM, Telnyx serializer + FastAPI WebSocket transport, WhisperSTTService (faster-whisper), Pipecat Flows `FlowManager`, 1.x quickstart/pipeline. **HIGH** (authoritative current docs).
- PyPI `pipecat-ai` JSON + project page — version **1.4.0** (2026-06-17), `Requires-Python >=3.11`, optional extras list, exact dependency pins (`anthropic>=0.49.0,<1`, `deepgram-sdk>=6.1.1,<8`, `faster-whisper~=1.2.1`, `aiortc>=1.14.0,<2`). **HIGH**.
- PyPI `pipecat-ai-flows` project page — version **1.3.0** (2026-06-18), `Requires-Python >=3.11`. **HIGH**.
- GitHub `pipecat-ai/pipecat/main/pyproject.toml` — confirmed extras/pins. **HIGH**.
- Model-id specifics (exact current `claude-...` id; nova-3 Italian parity) — **MEDIUM**: verify against Anthropic and Deepgram current model pages at build time; do not hardcode from memory.

---
*Stack research for: self-hosted multi-tenant Italian AI voice receptionist (Pipecat)*
*Researched: 2026-06-23*
