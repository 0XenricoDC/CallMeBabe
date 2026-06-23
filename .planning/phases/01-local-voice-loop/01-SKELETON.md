# Walking Skeleton — Centralino AI

**Phase:** 1
**Generated:** 2026-06-23

## Capability Proven End-to-End

> One sentence: the smallest user-visible capability that exercises the full stack.

Running `python main.py --tenant=demo` loads the `demo` tenant from SQLite, opens a browser WebRTC page at `localhost:7860/prebuilt/`, and the bot speaks its personalized Italian greeting and holds a natural spoken conversation (Deepgram STT → Claude LLM → ElevenLabs TTS) that the developer can interrupt mid-sentence.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / Runtime | Python **3.12** (venv) | `pipecat-ai` 1.4.0 requires `>=3.11`; `ctranslate2`/`faster-whisper` (D-08) have **no 3.13 wheels** — 3.12 is the only valid version on this machine (system has 3.9 + 3.13). |
| Orchestration | `pipecat-ai` **1.4.0** + `pipecat-ai-flows` **1.3.0** | Owner-locked. 1.x API: `PipelineWorker` + `WorkerRunner`, `LLMContext` + `LLMContextAggregatorPair`, `settings=Service.Settings(...)`. Flows seam present but unused until Phase 2. |
| Local transport | Pipecat runner + `SmallWebRTCTransport`, prebuilt UI at `/prebuilt/` (D-05) | No native audio deps on Windows. Same pipeline body that Phase 4 reuses for Telnyx — transport-only swap behind `TransportFactory`. |
| STT | `DeepgramSTTService` (`nova-2`, `language="it"`) active default; `WhisperSTTService` (`LARGE_V3_TURBO`, `Language.IT`) config-selectable, no auto-failover (D-08) | Owner-locked. `STTProvider` ABC is the seam. nova-3 Italian upgrade surfaced as a config-only note (CLAUDE.md locks nova-2). |
| LLM | `AnthropicLLMService`, model from `TenantConfig.model`, default `claude-haiku-4-5` (D-10) | Low TTFT for the <800ms budget; per-tenant overridable without code changes. |
| TTS | `ElevenLabsTTSService` (`eleven_multilingual_v2`, `language="it"`, `voice=tenant.voice_id`) (D-05/VOICE-05) | Italian multilingual model; per-tenant `voice_id` ready for voice cloning. |
| Data layer | SQLite via `aiosqlite` behind `TenantRepository` (D-01) | Async, parameterized queries. Full nullable `tenants` schema from day 1 (D-02); Postgres migration = connection-string swap. |
| Config seam | `TenantConfig` (Pydantic v2) loaded at call start (D-03) | The typed seam Phases 2–5 extend; no per-phase ALTER TABLE. |
| Latency instrumentation | Native Pipecat `enable_metrics` + `BaseObserver` subclass → console line + JSONL (D-06) | Per-turn `turn=…ms | stt=… llm_ttft=… tts_ttfb=…`; no probes in the hot path. |
| Fallback | `ErrorFrame`-observing `BaseObserver` injects a single generic Italian courtesy phrase (D-07, REL-01) | No per-stage phrases, no auto-failover in Phase 1 (that is Phase 3). |
| Directory layout | `src/` with `config/`, `pipeline/`, `interfaces/`, `db/`; `tests/`; `main.py` entry | Feature/layer folders behind interface seams so later phases add files, not restructure. |
| Secrets | All keys via `.env` (`python-dotenv`); `.env.example` + README setup (D-12, SETUP-01) | No hardcoded keys; only last-4 chars ever logged (V7). |

## Stack Touched in Phase 1

- [x] Project scaffold (Python 3.12 venv, deps install, `pyproject.toml` + pytest runner, lint-ready src layout)
- [x] Routing — Pipecat runner FastAPI server exposing `/prebuilt/` + WebRTC `/api/offer`
- [x] Database — real SQLite read (`TenantRepository.get_tenant`) AND real write (`init_db` + seed `demo` row)
- [x] UI — browser WebRTC mic page wired to the live STT→LLM→TTS pipeline
- [x] Run command — `python main.py --tenant=demo` exercises the full stack locally

## Out of Scope (Deferred to Later Slices)

> Anything that is *not* in the skeleton. Be explicit — this prevents future phases from re-litigating Phase 1's minimalism.

- Pipecat Flows booking flow, Google Calendar write, capacity check (Phase 2)
- FAQ / RAG over per-tenant knowledge base (Phase 2)
- Operator transfer / global handoff function (Phase 3)
- **Automatic** Deepgram→faster-whisper failover + dead-air watchdog (Phase 3) — Phase 1 wires Whisper as a manual config choice only
- Per-stage / differentiated courtesy phrases (future) — Phase 1 uses one generic phrase
- Multi-channel notifications, end-of-call summary/log dispatch (Phase 3)
- Telnyx telephony / 8kHz phone path (Phase 4)
- Onboarding CLI, tenant_id-scoped isolation, encrypted per-tenant credential store (Phase 5)
- `TELNYX_*` / `GOOGLE_*` keys in `.env.example` (added in Phases 4 / 2)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: Voice booking via Pipecat Flows → real Google Calendar write (behind `CalendarProvider`) + per-tenant RAG FAQ
- Phase 3: Operator handoff + end-of-call summary via `NotificationChannel` + full provider-failure fallback chain (auto Whisper failover, dead-air watchdog)
- Phase 4: Telnyx inbound calls — swap transport behind `TransportFactory`, DID→tenant routing, verify all M1–M3 behavior on the 8kHz path
- Phase 5: Multi-tenant isolation + onboarding CLI + encrypted per-tenant credential store; Postgres-ready persistence
