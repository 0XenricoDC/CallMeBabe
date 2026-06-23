# Project Research Summary

**Project:** CallMeBabe — Centralino AI
**Domain:** Self-hosted multi-tenant AI voice telephony receptionist for Italian SMBs
**Researched:** 2026-06-23
**Confidence:** HIGH (stack and architecture verified against live sources; features MEDIUM-HIGH; pitfalls MEDIUM-HIGH)

## Executive Summary

CallMeBabe is a fully self-hosted, multi-tenant AI voice receptionist targeting Italian small businesses (restaurants, hotels/B&Bs, medical and dental practices). The product thesis is stack ownership: no per-minute platform markup, no vendor lock-in, GDPR-friendly, and a single code base that serves every client through configuration records rather than code forks. The recommended build approach centers on Pipecat 1.4.0 as the voice-pipeline orchestration layer (STT → LLM + tools → TTS), Pipecat Flows 1.3.0 for structured conversation state machines, Deepgram for Italian STT, Anthropic Claude for the LLM brain with tool calling, ElevenLabs for per-client cloned Italian TTS, Telnyx for telephony (WebSocket media streaming, not SIP), Google Calendar for real booking writes, and SQLite/aiosqlite now behind a repository interface that targets Postgres later.

The build is structured as five milestones ordered by dependency: a local voice loop first (M1), then structured booking and calendar integration (M2), then FAQ/RAG, human handoff, and end-of-call summaries (M3), then real telephony via Telnyx (M4), and finally multi-tenant config hardening and onboarding tooling (M5). This inside-out dependency order is critical: the transport abstraction, config-injection pattern, and interface boundaries defined in M1 are what make M4 a transport-layer swap and M5 a data-layer addition rather than rewrites. Skipping the interface discipline early is the highest-cost architectural risk.

The top risks are latency (the default `aggregation_timeout` alone exceeds the 800ms per-turn budget before any real work is done), barge-in reliability on the WebSocket/Telnyx path (where output-audio writes can starve the VAD input thread), and booking correctness (Google Calendar has no atomic check-and-reserve, and Claude will fabricate confirmations if not structurally gated by tool results via Pipecat Flows). All three are addressable by design decisions made in M1 and M2 — but they become expensive to retrofit later. The streaming-from-the-start requirement and the Flows gating requirement are non-negotiable from the first milestone.

---

## Key Findings

### Recommended Stack

The entire stack is owner-fixed. This research confirmed current versions, exact import paths against Pipecat 1.x (which underwent a major API rewrite at 1.0 — most tutorials and training data describe the incompatible 0.0.x line), Italian-language configuration for each provider, and the exact integration surface used in the codebase.

The most important version-level finding: Pipecat 1.4.0 uses `PipelineWorker` + `WorkerRunner` (not `PipelineTask` + `PipelineRunner`), `LLMContext` + `LLMContextAggregatorPair` from `pipecat.processors.aggregators.llm_response_universal` (not provider-specific context classes), and `settings=ServiceClass.Settings(...)` (flat kwargs deprecated since 0.0.105). Copying any pre-1.0 Pipecat tutorial or documentation verbatim will break. Flows is a separate package: install `pipecat-ai-flows`, import as `pipecat_flows`.

**Core technologies:**
- **Python 3.11 / 3.12:** Required by pipecat-ai 1.4.0; 3.13 not validated against faster-whisper/ctranslate2 deps.
- **pipecat-ai 1.4.0:** Voice-agent pipeline orchestration (STT → LLM → TTS with VAD/barge-in); the 1.x line is the current, actively-maintained API.
- **pipecat-ai-flows 1.3.0:** Structured conversation node graph; keeps each step isolated to only its relevant tools, preventing wrong tool calls and hallucinated confirmations.
- **Deepgram (nova-2, `language=Language.IT`):** Primary streaming STT. Must explicitly set `language` and `model` — defaults are English/nova-3-general, which silently fails on Italian.
- **Anthropic Claude (Sonnet-class, `pipecat.services.llm.anthropic`):** LLM brain with native tool calling; enable `prompt_caching` for per-tenant system prompts.
- **ElevenLabs (`eleven_multilingual_v2`, WebSocket streaming, per-tenant `voice_id`):** Italian TTS with voice cloning. The `language` param only works on multilingual models.
- **Telnyx (`TelnyxFrameSerializer` + `FastAPIWebsocketTransport`):** Telephony via WebSocket media streaming (8kHz PCMU), not SIP.
- **faster-whisper ~=1.2.1 (`Model.LARGE`, `language=Language.IT`):** Self-hosted STT fallback. Avoid DISTIL_* models — English-only.
- **Silero VAD (`SileroVADAnalyzer`):** Required for barge-in and turn-taking.
- **FastAPI + uvicorn:** WebSocket server receiving Telnyx media streams.
- **aiosqlite / SQLAlchemy:** Persistence behind a repository interface; Postgres-ready by connection-string change.

### Expected Features

**Must have (table stakes) — v1 M1–M5:**
- Low-latency natural Italian conversation with barge-in (<800ms end-to-end)
- Per-client personalized greeting
- Graceful fallback phrases on STT/LLM/TTS failure or low confidence
- Structured booking flow (date / time / party-or-service / name / phone) via Pipecat Flows
- Availability/capacity check before any confirmation
- Real Google Calendar write behind `CalendarProvider`
- Spoken booking read-back and confirmation before writing
- RAG FAQ on per-client knowledge base (hours, address, services, prices)
- Human handoff/transfer on explicit request, low confidence, out-of-scope, or non-Italian caller
- End-of-call log and summary (transcript, outcome, reservation details)
- Owner notification via configurable channel (email/SMS/WhatsApp/Telegram)
- Real inbound Italian calls via Telnyx behind telephony interface
- Multi-tenant config (client = config record) and onboarding CLI

**Should have (differentiators) — v1.x after validation:**
- STT provider fallback to faster-whisper (self-hosted resilience)
- Warm transfer with structured context briefing
- Outcome analytics from accumulated call-log data
- Richer booking-rules engine (party-size/table-combination logic)

**Defer to v2+:**
- Multilingual conversation (detect non-Italian → transfer to human instead)
- Twilio telephony (interface abstracted; add only if Telnyx becomes limiting)
- Postgres migration (add when concurrency demands it)
- Specific PMS/POS/EHR integrations
- Web/app voice channel
- Outbound calling, in-call payments (separate compliance burdens, out of scope)

### Architecture Approach

The system is one Pipecat engine where every tenant is a CONFIG record loaded at call start. Four concentric layers: (1) swappable transport edge, (2) Pipecat processor chain (STT → context → LLM+tools → TTS), (3) Pipecat Flows state machine (greeting → booking → FAQ → handoff/end), (4) domain-service interfaces (CalendarProvider, NotificationChannel, KnowledgeBase, ConfigLoader) with Protocol-based implementations. Every external integration is behind a `base.py` protocol. New client = new DB row + KB folder, never a deploy.

**Major components:**
1. **Transport (interface)** — `LocalAudioTransport` (M1), `FastAPIWebsocketTransport + TelnyxFrameSerializer` (M4); both produce/consume identical Pipecat frames.
2. **Voice pipeline** — `transport.input → STT → context.user → LLM+tools → TTS → transport.output` with Silero VAD enabling barge-in via `InterruptionFrame`.
3. **FlowManager** — node graph; each node has `role_message` + `task_messages` + only its relevant tools; handlers return `(result, next_node)`.
4. **ConfigLoader** — resolves tenant (dialed number in M4, CLI flag in M1) → `TenantConfig` → consumed by `build_pipeline()`.
5. **CalendarProvider (interface)** — `GoogleCalendarProvider` for real availability and event creation; `InMemoryCalendarProvider` for tests.
6. **KnowledgeBase (interface)** — SQLite FTS5 keyword search per tenant; vector store only if keyword recall proves insufficient.
7. **NotificationChannel (interface)** — email/SMS/WhatsApp/Telegram/log implementations selected per-tenant.
8. **Persistence (SQLAlchemy)** — `tenants`, `reservations`, `call_logs`, `kb_documents/chunks`; SQLite now, Postgres by connection-string change.

### Critical Pitfalls

1. **`aggregation_timeout` default (~1.0s) blows the latency budget** — lower to 0.1–0.3s in M1 and instrument per-stage latency from the start.
2. **Non-streaming (waterfall) pipeline** — architect streaming at every stage in M1; retrofitting is a rewrite.
3. **Barge-in broken on WebSocket transport** — synchronous output-audio writes starve the VAD input thread (Pipecat issue #2460); use non-blocking output audio; re-verify on Telnyx/WebSocket path in M4.
4. **Claude hallucinating booking confirmations** — use Pipecat Flows to gate: confirmation phrase executes only after `create_event` returns a real event ID.
5. **Google Calendar double-booking (no atomic reserve)** — maintain authoritative slot/capacity in your own DB with transactional check-and-insert; Calendar is the projection, not the lock.
6. **Italian STT errors on booking-critical fields** — always read back date/time/party/name/phone before writing; use Deepgram keyterm prompting for local proper nouns.
7. **Multi-tenant config bleed** — resolve tenant from inbound DID into an immutable session context; filter every config/KB/DB read by `tenant_id` at the source; design this boundary from M1.

---

## Implications for Roadmap

### Phase 1: Local Voice Loop (M1)

**Rationale:** All downstream milestones depend on a working streaming STT → LLM → TTS pipeline. This is where the most expensive architectural decisions lock in (streaming, VAD, `aggregation_timeout`, interface boundaries). Getting these wrong requires a rewrite.

**Delivers:** Working Italian conversational voice agent (mic/headset), barge-in, per-client greeting, graceful fallback phrases. All interface seams defined: `TransportFactory`, `TenantConfig`, `ConfigLoader`.

**Addresses:** Low-latency Italian conversation with barge-in, per-client greeting, graceful fallback phrases.

**Avoids:** `aggregation_timeout` default (set 0.1–0.3s immediately), waterfall pipeline (stream at every stage from day one), barge-in/VAD starvation (non-blocking output audio), Italian STT config (nova-2 + Language.IT + smart_format + keyterm prompting), secrets mishandling (.env.example from commit one), concurrency-model design (1 process = 1 session).

**Research flag:** None — Pipecat 1.x patterns fully documented in STACK.md with exact import paths.

---

### Phase 2: Booking Flow + Calendar + FAQ (M2)

**Rationale:** Core business value. Exercises Pipecat Flows end-to-end (structural gating that prevents hallucinated confirmations), real external integration (Google Calendar), transactional capacity model, and RAG/KB schema needed for M5.

**Delivers:** Structured booking via Pipecat Flows nodes, availability/capacity check, real Google Calendar write, spoken read-back and confirmation, RAG FAQ on per-tenant KB (SQLite FTS5). `CalendarProvider` and `KnowledgeBase` protocols fully implemented.

**Addresses:** Structured reservation capture, availability check, Google Calendar write, spoken booking confirmation, RAG FAQ.

**Avoids:** Hallucinated confirmations (Flows gating), Calendar double-booking (own-DB transactional reserve + unique slot constraint + Europe/Rome timezone), RAG inventing facts (structured config fields for high-stakes facts; strict grounding instruction).

**Research flag:** MEDIUM — Google Calendar freebusy-to-availability inversion and transactional capacity model have documented subtleties. Consider a targeted spike on the transactional reserve schema.

---

### Phase 3: Handoff, Summaries, and Notifications (M3)

**Rationale:** Closes the "safe exit" loop every earlier node depends on. Must be proven on the local transport before M4 adds telephony complexity. Cold transfer is MVP; warm transfer is the upgrade.

**Delivers:** Transfer decision logic (explicit / low-confidence / out-of-scope / non-Italian), end-of-call summary (Claude over transcript), call log persistence, `NotificationChannel` implementations, provider-failure fallback chain (courtesy phrase → faster-whisper STT switch → transfer-on-fail).

**Addresses:** Human handoff, non-Italian caller → transfer, end-of-call log, owner notification, STT provider fallback.

**Avoids:** Silent provider failures (dead-air watchdog + circuit breakers + faster-whisper fallback), cold transfer with no context (warm transfer upgrade path defined).

**Research flag:** None — SMTP, Telegram Bot API, and Telnyx Messaging are standard patterns.

---

### Phase 4: Telnyx Telephony (M4)

**Rationale:** By design, this is a transport-layer swap: `telnyx.py` is added to `transport/`; no pipeline or flow logic changes. Real telephony introduces a new failure class that must be re-tested explicitly even though M1–M3 passed on the local path.

**Delivers:** Real inbound Italian calls over Telnyx numbers, dialed-number → tenant routing, call lifecycle management, real SIP REFER cold transfer, end-to-end inbound call with booking and notification.

**Addresses:** Real inbound Italian calls via Telnyx behind telephony interface.

**Avoids:** Telnyx codec/DTMF issues (RFC 2833, `audio_out_sample_rate=8000` only, prefer STT+read-back over DTMF), Smart Turn v3 8kHz bug (do NOT set `audio_in_sample_rate=8000`), WebSocket barge-in starvation re-verified on phone path, cross-region latency (co-locate near Italy/EU), concurrency (1 process = 1 session under real concurrent inbound).

**Research flag:** HIGH — Telnyx media streaming, call-control API, warm-transfer Dial+Bridge composition, and PSTN-specific latency tuning all have documented gotchas absent from the local path. Recommend `--research-phase` during planning.

---

### Phase 5: Multi-Tenant Hardening + Onboarding (M5)

**Rationale:** Config-injection and `tenant_id` filtering are in place from M1; M5 makes adding a new tenant a data-only operation and hardens isolation, per-tenant credentials, and voice-cloning consent. Last phase because it is assembly, not invention.

**Delivers:** Onboarding CLI validating and inserting new tenant config records, per-client KB folder ingestion, per-tenant notification channel selection, per-client ElevenLabs `voice_id` with documented consent gate, encrypted per-tenant credentials, isolation test (two simultaneous DIDs never crossing), latency and fallback tuning review.

**Addresses:** Multi-tenant config, onboarding CLI, per-client voice cloning.

**Avoids:** Multi-tenant config bleed (immutable session tenant context, mandatory `tenant_id` filter, explicit isolation tests), voice cloning consent/quality (GDPR/biometric + ElevenLabs ToS; validate clone on 8kHz phone codec), per-tenant credential sprawl (encrypted per-tenant store, least-privilege Calendar scope).

**Research flag:** MEDIUM — per-tenant credential encryption patterns and GDPR Article 9 consent requirements for voice cloning for Italian medical practices may need a targeted legal/technical spike.

---

### Phase Ordering Rationale

- Interfaces before implementations: `TransportFactory`, `TenantConfig`, `CalendarProvider`, `NotificationChannel`, `KnowledgeBase` protocols defined in M1–M2. M4 and M5 add files behind interfaces, not structural changes.
- Streaming is non-negotiable in M1: the waterfall anti-pattern is never acceptable for the conversational path.
- Booking (M2) before FAQ/Handoff (M3): booking validates the Flows tool-gating pattern end-to-end before adding RAG and handoff.
- All conversational logic proven locally (M1–M3) before telephony (M4): the Telnyx path reintroduces 8kHz, codec, async DTMF, and WebSocket-VAD risks simultaneously.
- Multi-tenant (M5) last: M5 is hardening and UX tooling on top of already-working config injection.

### Research Flags

Needs `--research-phase` during planning:
- **Phase 4 (Telnyx telephony):** HIGH — DTMF/codec reliability, warm-transfer Dial+Bridge, PSTN latency profiling, Telnyx media-streaming WebSocket specifics.
- **Phase 2 (booking/calendar):** MEDIUM — Google Calendar freebusy inversion and transactional reserve schema.

Standard patterns (skip research-phase):
- **Phase 1:** Pipecat 1.x fully documented with exact code in STACK.md.
- **Phase 3:** Notification channel integrations are standard well-documented patterns.
- **Phase 5:** Config injection already in place; M5 is hardening + CLI.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions, import paths, and Italian-language config verified against Context7 `/pipecat-ai/docs` and live PyPI June 2026. Only gap: exact current Anthropic model ID and nova-3 Italian parity — verify at build time. |
| Features | MEDIUM-HIGH | Table-stakes features and dependency order verified across multiple vendor write-ups and official Pipecat/Telnyx docs. Italian-specific UX nuances (backchannels, noisy environments) are MEDIUM. |
| Architecture | HIGH (pipeline/transport/Flows); MEDIUM (multi-tenant config-injection) | Pipecat patterns verified via Context7 + official docs. Config-injection multi-tenant pattern synthesized from Pipecat primitives — no single canonical reference, but primitives are verified. |
| Pitfalls | MEDIUM-HIGH | Most pitfalls verified across official docs + production write-ups. `aggregation_timeout` and barge-in/VAD findings are HIGH (confirmed in Pipecat issue tracker and production guides). Specific Italian STT WER numbers are MEDIUM. |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact current Anthropic Claude model ID:** Verify at build time from the Anthropic console; do not hardcode from memory.
- **Deepgram nova-3 Italian parity:** Nova-3 Italian added January 2026; verify current matrix before deciding between nova-2 (safe) and nova-3.
- **Telnyx warm-transfer Dial+Bridge API:** Cold transfer (SIP REFER) is documented. Warm transfer needs targeted API review during M4 planning.
- **GDPR Article 9 and voice cloning consent for Italian medical practices:** Cloned voices are biometric data under GDPR; consent process and retention policy need legal review for studi medici/dentistici clients.
- **Italian proper-noun STT accuracy on realistic audio:** Aggregate WER numbers do not reflect accuracy on surnames, street names, and menu items. Plan a STT accuracy test with a realistic Italian caller test set before M4.

---

## Sources

### Primary (HIGH confidence)

- Context7 `/pipecat-ai/docs` — Pipecat 1.x pipeline, transport, Flows, STT/LLM/TTS services, Telnyx serializer, barge-in/InterruptionFrame, function calling, context management
- PyPI `pipecat-ai` 1.4.0 (2026-06-17) and `pipecat-ai-flows` 1.3.0 (2026-06-18) — exact versions, Python requirements, dependency pins
- GitHub `pipecat-ai/pipecat` `pyproject.toml` — confirmed extras/dep pins
- ElevenLabs official docs — latency optimization, Flash/IVC, `optimizeStreamingLatency`, telephony region latency
- Pipecat GitHub Issue #2460 — WebSocket transport barge-in/VAD thread starvation
- Telnyx media streaming + DTMF/codecs official docs — RFC 2833, out-of-order DTMF, L16, codec selection

### Secondary (MEDIUM-HIGH confidence)

- Pipecat in Production (Luong Hong Thuan) — `aggregation_timeout` tax, 1-process-per-session, memory leak, silent provider failures, Smart Turn v3 8kHz bug
- Telnyx — AI-to-human handoff, voice AI delay causes, cold vs warm transfer, SIP REFER
- Famulor / LiveKit / Hamming AI — human handoff patterns, barge-in/turn-detection runbooks
- HuskyVoice / MindStudio / Ainora — restaurant capacity logic, Google Calendar integration, voice agent RAG
- Retell AI / Webfuse / AssemblyAI — voice AI failure patterns, LLM fallback, STT reliability
- WorkOS / Scalekit — multi-tenant AI agent secrets management and config-bleed isolation patterns
- Deepgram nova-3 Italian support announcement (Jan 2026)

### Secondary (MEDIUM confidence)

- Google Calendar double-booking community reports (Vapi community, Slotflow) — no atomic reserve, freebusy inversion
- Voice AI pipeline latency budget (Chanl) — per-stage budget figures
- RAG grounding in voice agents (Gladia, Retell) — grounding necessary-not-sufficient, KB governance
- Claude tool-hallucination rate study (arXiv 2412.04141) — ~9% base rate
- RAG latency for voice (arXiv 2603.02206) — latency constraints on real-time RAG retrieval

---
*Research completed: 2026-06-23*
*Ready for roadmap: yes*
