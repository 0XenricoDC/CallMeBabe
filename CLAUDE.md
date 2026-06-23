<!-- GSD:project-start source:PROJECT.md -->
## Project

**Centralino AI**

Assistente vocale telefonico multi-tenant per piccole attività italiane (ristoranti, hotel/B&B, studi medici/dentistici). Un solo motore self-hosted, con BYO API keys, che risponde alle chiamate in entrata in italiano naturale: prende prenotazioni/appuntamenti, risponde a FAQ pescando da una knowledge base per-cliente, trasferisce a un operatore umano quando serve, e a fine chiamata invia al titolare un riepilogo (trascrizione, esito, eventuale prenotazione). Ogni cliente è un record di configurazione, **non** una modifica al codice. Niente piattaforme tipo Synthflow/Vapi: si possiede l'intero stack.

**Core Value:** Una chiamata reale in italiano viene gestita end-to-end dal bot — saluto personalizzato, conversazione naturale a bassa latenza, azione completata (prenotazione/FAQ/trasferimento) — senza intervento umano e senza riscrivere codice per un nuovo cliente.

### Constraints

- **Tech stack**: Pipecat (Python) + Pipecat Flows per l'orchestrazione e i flussi conversazionali — scelta vincolante del titolare.
- **STT**: Deepgram in italiano, con fallback faster-whisper self-hosted predisposto — robustezza e indipendenza da un singolo provider.
- **LLM**: Anthropic Claude via API con tool calling — è il "cervello" del bot.
- **TTS**: ElevenLabs, voce italiana, predisposto per voice cloning per-cliente (`voice_id`).
- **Telefonia**: Telnyx con numeri geografici italiani, **astratto dietro un'interfaccia** per poter passare a Twilio senza riscrivere la logica.
- **Notifiche/riepilogo**: layer astratto multi-canale (Email/SMTP, SMS/WhatsApp, Telegram, log), canale configurabile per-cliente.
- **Calendario**: interfaccia `CalendarProvider`; implementazione Google Calendar reale attiva dalla fase prenotazioni (non placeholder).
- **Architettura**: un solo motore; ogni cliente = record di CONFIG, mai una modifica al codice. Multi-tenant per configurazione.
- **Persistenza**: SQLite/JSON iniziale, codice strutturato per migrare a Postgres.
- **Performance**: latenza target < 800ms end-to-end; barge-in e gestione interruzioni obbligatori.
- **Affidabilità**: fallback robusti su tutti i layer (STT/LLM/TTS) con frasi di cortesia ed eventuale trasferimento.
- **Security/Config**: tutte le chiavi API via `.env`; nessuna chiave hardcoded; tutto self-hosted.
- **Lingua**: conversazione solo in italiano; non-italiano → trasferimento operatore.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## CRITICAL VERSION NOTE — read first
- `pipecat-ai` **1.4.0** (released 2026-06-17) — the old `0.0.x` series (0.0.108, March 2026) is the *pre-1.0* line.
- `pipecat-ai-flows` **1.3.0** (released 2026-06-18) — the Flows add-on, also bumped to 1.x to match.
- Pipeline runner is `PipelineWorker` + `WorkerRunner` (older code used `PipelineTask` + `PipelineRunner`).
- Context is `LLMContext` + `LLMContextAggregatorPair` from `pipecat.processors.aggregators.llm_response_universal` (older code used provider-specific `OpenAILLMContext` etc.).
- Services are configured with a `settings=ServiceClass.Settings(...)` object; the older flat kwargs (`model=`, `params=InputParams(...)`) are **deprecated as of 0.0.105** but still accepted.
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
## Exact Pipecat integration surface (1.x)
### STT — Deepgram (primary, Italian)
### LLM — Anthropic Claude (tool calling)
### TTS — ElevenLabs (Italian, per-client voice cloning)
### Telephony — Telnyx (behind your interface)
### STT fallback — faster-whisper (self-hosted)
### Pipecat Flows (booking / FAQ orchestration)
## Installation
# Python 3.11 or 3.12, in a venv (uv recommended)
# Core pipeline + all fixed providers (extras enable each service)
# Structured flows add-on
# Server (Telnyx media-stream endpoint) + supporting libs
# Dev
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Deepgram `nova-2` Italian | Deepgram `nova-3` / `language="multi"` | Only if Deepgram's current matrix confirms nova-3 Italian parity, or if you later support mixed-language callers (out of v1 scope). |
| ElevenLabs `eleven_multilingual_v2` | `eleven_turbo_v2_5` / `flash_v2_5` (multilingual) | If TTS latency dominates the budget — turbo/flash trade a little quality for speed; both still honor `language=IT`. |
| `ElevenLabsTTSService` (WebSocket) | `ElevenLabsHttpTTSService` | Only where you cannot hold a WS (simple request/response); needs `aiohttp_session=`. WS is lower latency — default to it. |
| `WhisperSTTService` (faster-whisper) GPU | CPU `int8`, or `MLXWhisperSTTService` (Apple Silicon) | CPU for low-volume/dev; MLX only on Mac dev machines. |
| SQLite (`aiosqlite`) now | Postgres (`asyncpg`/SQLAlchemy) | At multi-instance scale or concurrent writes; keep the repository interface DB-agnostic so this is a config swap (owner-stated migration path). |
| Telnyx | Twilio (`TwilioFrameSerializer`) | Swap behind `TelephonyProvider` if Telnyx Italian number availability/pricing is worse; Pipecat supports both first-class. |
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
## Stack Patterns by Variant
- Use the `runner` + WebRTC/`SmallWebRTCTransport` transport.
- Same `stt → aggregator.user() → llm → tts → aggregator.assistant()` pipeline; only the transport differs. Telnyx is added later with no pipeline change.
- FastAPI app exposes a `wss://` endpoint; Telnyx TeXML/Call Control points the media stream at it.
- `TelnyxFrameSerializer` (PCMU 8kHz) + `FastAPIWebsocketTransport`; pipeline body unchanged.
- Swap `STTProvider` implementation to `WhisperSTTService` (faster-whisper) via tenant/global config; rest of pipeline untouched.
- Move persistence from `aiosqlite` to Postgres (`asyncpg` + SQLAlchemy) behind the existing repository interface; no domain-logic change.
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
## Sources
- Context7 `/pipecat-ai/docs` — Deepgram STT, ElevenLabs TTS, Anthropic LLM, Telnyx serializer + FastAPI WebSocket transport, WhisperSTTService (faster-whisper), Pipecat Flows `FlowManager`, 1.x quickstart/pipeline. **HIGH** (authoritative current docs).
- PyPI `pipecat-ai` JSON + project page — version **1.4.0** (2026-06-17), `Requires-Python >=3.11`, optional extras list, exact dependency pins (`anthropic>=0.49.0,<1`, `deepgram-sdk>=6.1.1,<8`, `faster-whisper~=1.2.1`, `aiortc>=1.14.0,<2`). **HIGH**.
- PyPI `pipecat-ai-flows` project page — version **1.3.0** (2026-06-18), `Requires-Python >=3.11`. **HIGH**.
- GitHub `pipecat-ai/pipecat/main/pyproject.toml` — confirmed extras/pins. **HIGH**.
- Model-id specifics (exact current `claude-...` id; nova-3 Italian parity) — **MEDIUM**: verify against Anthropic and Deepgram current model pages at build time; do not hardcode from memory.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
