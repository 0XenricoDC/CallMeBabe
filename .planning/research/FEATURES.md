# Feature Research

**Domain:** Self-hosted AI voice telephony receptionist (inbound calls) for small Italian businesses — restaurants, hotels/B&B, medical/dental practices ("Centralino AI")
**Researched:** 2026-06-23
**Confidence:** MEDIUM-HIGH (HIGH on table-stakes call behaviors and booking/handoff patterns, verified across multiple vendors + Pipecat docs; MEDIUM on Italian-specific nuances and exact capacity-logic patterns, which are vendor-described rather than spec-grade)

## Feature Landscape

This research maps the inbound voice-receptionist domain onto the project's locked stack (Pipecat + Pipecat Flows, Deepgram STT, Claude LLM w/ tool calling, ElevenLabs TTS, Telnyx telephony, Google Calendar, multi-channel notifications) and its 5-milestone build order:

1. **M1** — Local Pipecat agent (mic/headphones) conversing in natural Italian
2. **M2** — Booking flow + capacity check + Google Calendar write + RAG FAQ
3. **M3** — Human handoff/transfer + end-of-call log/summary + owner notification
4. **M4** — Telnyx telephony (real inbound Italian calls)
5. **M5** — Multi-tenant config + onboarding CLI/panel + per-client voice cloning

Across every commercial product surveyed (Retell, Synthflow, Vapi, Bland, Yelp Host, voiceOne, HuskyVoice, RingCentral, Imagicle, GoTo, myAIfrontdesk, Loman, Canary), the same core capability set recurs. The differences are in depth (integration breadth, analytics, multi-language) — not in the fundamental "answer, converse, book, route, summarize" loop.

### Table Stakes (Users Expect These)

Missing any of these and the product does not function as a receptionist. A caller will immediately perceive it as broken or "robotic."

| Feature | Why Expected | Complexity | Milestone | Notes |
|---------|--------------|------------|-----------|-------|
| Natural low-latency conversation (STT→LLM→TTS) in Italian | A receptionist that lags or sounds robotic destroys trust on the first sentence. Industry target is <800ms end-to-end (best-in-class ~510-600ms). | HIGH | M1 | Pipecat handles the pipeline; tuning Deepgram (it-IT model), Claude streaming, and ElevenLabs streaming to stay under budget is the hard part. Use streaming everywhere. |
| Barge-in / interruption handling | Humans interrupt. If the bot keeps talking over the caller, it feels broken. | HIGH | M1 | Pipecat has native VAD + Smart Turn v3 turn detection + barge-in. Tune VAD/endpointing per message type — do NOT use one global threshold. Test false-positive (stops on noise) and false-negative (won't stop) separately. |
| Per-client personalized greeting | "Grazie per aver chiamato [Ristorante X]" is the minimum personalization. Generic greeting = obviously a bot farm. | LOW | M1 (static) / M5 (per-tenant) | Trivial as a config string injected into the first node/system prompt. Becomes a tenant field in M5. |
| Graceful fallback phrases on STT/LLM/TTS failure or low confidence | Dead air or garbled audio is the #1 way callers realize they're abandoned. | MEDIUM | M1 (phrases) / M3 (transfer fallback) | Standard set: "Scusi, non ho capito bene, può ripetere?" on low STT confidence; bridging filler ("Un attimo, controllo...") while LLM/tool runs; on repeated failure → transfer (M3). Validate/sanitize STT output (strip [INAUDIBLE], min length) before acting. |
| Structured reservation/appointment capture | The core action. Collect date, time, party-size-or-service, name, phone. | MEDIUM | M2 | Pipecat Flows is purpose-built for this (sequential nodes, gated tools, state outside context window). The reservation example collects party size, date, time, contact details. |
| Availability / capacity check BEFORE confirming | Confirming a booking you can't honor is worse than no bot. "First request wins; offer alternatives." | MEDIUM-HIGH | M2 | Must check business hours, slot/table capacity, buffers, blocked times before writing. For restaurants, party-size logic (can 2x4-tops seat 8?) is the subtle part. Implement as a `CalendarProvider` query + capacity rules from tenant config. |
| Real calendar write (Google Calendar) | A booking that doesn't land in the owner's actual calendar is theatre. Owner explicitly wants real writes, not a placeholder. | MEDIUM | M2 | OAuth2 + Calendar API; ~1-2h to wire one calendar. Behind `CalendarProvider` interface per constraints. Avoid double-booking via read-then-write with the API as source of truth. |
| FAQ answering from per-client knowledge base (RAG) | Callers ask hours, address, services, prices far more often than they book. Hallucinated answers are dangerous (wrong hours, wrong price). | MEDIUM | M2 | Simple RAG grounds answers in tenant KB (hours, address, services, prices). Keep KB structured (FAQ pairs, markdown with clear headings retrieve best). For small KBs, even full-context injection may beat vector search. |
| Human handoff / transfer to a configurable number | When the bot can't help (uncertainty, out-of-scope, explicit request, non-Italian caller), it must reach a person. A confidently-wrong bot is worse than a transfer. | MEDIUM-HIGH | M3 (logic) / M4 (real telephony transfer) | Triggers: explicit request ("mi passi un operatore"), low LLM confidence, out-of-scope, non-Italian detected. Always honor explicit requests immediately, no friction. Real transfer needs Telnyx (SIP REFER / Dial) in M4; M3 builds the decision logic + announcement. |
| End-of-call log + summary | Owner needs to know what happened on every call (outcome, transcript, any booking). | MEDIUM | M3 | Generate within seconds of call end: caller intent, outcome, reservation details, transcript. Claude can summarize the transcript. |
| Owner notification of the summary (configurable channel) | A summary nobody reads is useless. Push it to where the owner lives (email/SMS/WhatsApp/Telegram). | MEDIUM | M3 (channel) / M5 (per-tenant choice) | Multi-channel layer behind an interface; channel chosen per tenant. Email/SMTP is the simplest first channel; Telegram bot is cheap; SMS/WhatsApp adds cost/provider deps. |
| Booking confirmation back to caller (spoken) | Caller must hear the booking read back and confirmed before hanging up. Reduces no-shows and errors. | LOW | M2 | Read back date/time/party/name; ask "confermo?" before writing. Part of the Flows confirmation node. |
| Multi-tenant config (client = a config record, not code) | The entire architecture premise. New client = new row, never a deploy. | HIGH | M5 | Tenant record: name, greeting, voice_id, hours, services/menu, booking rules, transfer number, KB, notification channel. Routing key = the dialed Telnyx number → tenant. |
| Onboarding path for a new client (CLI/mini panel) | Without it, "multi-tenant" is theoretical — someone must be able to add a client without touching code. | MEDIUM | M5 | CLI is sufficient for v1; validates the config schema. SQLite/JSON store now, structured for Postgres later. |

### Differentiators (Competitive Advantage)

These set the product apart. They align with the Core Value: fully self-hosted, owned stack, real end-to-end Italian call handling without per-client code.

| Feature | Value Proposition | Complexity | Milestone | Notes |
|---------|-------------------|------------|-----------|-------|
| Fully self-hosted / owned stack (no Synthflow/Vapi) | Data sovereignty, no per-minute platform markup ($0.25-0.33/min real cost on aggregator platforms), full control of the pipeline. This IS the product thesis. | HIGH | All | Differentiator vs every managed platform. Cost and control are the pitch to a technical owner; also GDPR-friendly for IT medical practices. |
| Per-client voice cloning (ElevenLabs `voice_id`) | Each business gets a distinct brand voice — a real B&B owner's voice, a clinic's chosen tone. Most cheap aggregators give stock voices only. | MEDIUM | M5 | Just a `voice_id` field per tenant once the TTS layer is parameterized. ElevenLabs clones from minutes of audio. Get explicit consent for cloned voices (GDPR/likeness). |
| STT provider fallback (faster-whisper self-hosted) | Resilience + independence from a single cloud STT vendor; can degrade gracefully if Deepgram is down. | MEDIUM | post-M1 / M4 | Predisposed per constraints. faster-whisper as self-hosted backstop. Multi-provider failover is a known production pattern. |
| Telephony abstraction (Telnyx now, Twilio-swappable) | Avoids vendor lock-in on the carrier; protects business logic from carrier API churn. | MEDIUM | M4 | Behind an interface per constraints. Telnyx gives Italian geographic numbers + SIP REFER transfer. |
| Non-Italian caller → automatic transfer (instead of bad multilingual) | Honest scoping: rather than fake multilingual that fails, route to a human. Feels MORE professional than a bot stumbling in broken English. | LOW-MEDIUM | M3 | Detect non-Italian from STT language signal / early turns, then transfer. Cheap to implement, high trust payoff. |
| Warm transfer with structured context briefing | Human picks up a one-line briefing (intent, what's collected, sentiment) instead of a cold dead-end. Reduces caller re-explanation; cuts abandonment up to ~40% vs clunky handoff. | MEDIUM-HIGH | M3+/M4 | True warm transfer (AI briefs human live) is harder over telephony; a "whisper" or a pushed summary note is a pragmatic middle ground. Cold transfer is the MVP; warm is the upgrade. |
| Per-tenant booking rules engine (hours, buffers, capacity, party-size logic) | Real restaurants/clinics have non-trivial rules (lunch service windows, per-service durations, table combinations, provider-specific calendars). Encoding these well = bookings the owner can actually honor. | HIGH | M2 (basic) / later (rich) | Start simple (hours + slot capacity); layer party-size/table-combination and per-provider calendars as differentiators. |
| Outcome analytics from summaries (booking conversion, transfer rate) | Rising transfer rate signals KB/script gaps; conversion shows ROI. Owners love seeing "the bot booked N tables this week." | LOW-MEDIUM | post-M3 | Falls out of the call-log data almost for free; aggregate later. |

### Anti-Features (Commonly Requested, Often Problematic)

Documented to prevent scope creep. Several are already Out of Scope in PROJECT.md — reinforced here with the reasoning so they don't get re-added.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multilingual conversation | "Serve international tourists / non-Italian patients." | Doubles the failure surface (per-language STT/TTS/prompt tuning, language detection mid-call, hallucinated translations). Erodes the v1 reliability focus. Already Out of Scope. | Detect non-Italian → transfer to human operator. More reliable and feels professional. |
| Outbound calling (reminders, campaigns) | "Reduce no-shows with reminder calls." | Different consent/regulatory regime (cold-call rules, opt-out), different dialer infra, different failure modes. A whole second product. Already Out of Scope. | v1 is inbound-only. If reminders are wanted, send them as text via the existing notification layer, not calls. |
| In-call payments / card capture | "Take a deposit to secure the booking." | PCI-DSS scope, fraud liability, STT mishearing card digits, GDPR/medical sensitivity. Massive compliance burden for a v1. Already Out of Scope. | Send a payment link via the notification/confirmation channel post-call, or collect at the venue. |
| Full EHR/PMS/POS write integration | "Write straight into our clinic/restaurant system." | Each vendor = a bespoke, fragile integration; auth nightmares; multi-tenant explosion. Google Calendar already gives the core "real write." | `CalendarProvider` interface keeps the door open; ship Google Calendar only in v1. Add specific PMS/POS later per demand. |
| Sentiment/prosody-based frustration escalation | "Transfer angry callers automatically." | Prosody detection is unreliable, language-specific, and adds latency. False escalations annoy; missed ones look worse. | Use explicit-request + low-LLM-confidence + repeated-failure triggers (deterministic, debuggable). Add sentiment later if data justifies it. |
| Open-ended "ask me anything" chit-chat | "Make it feel human / handle anything." | Unbounded LLM = off-script loops, hallucinated promises, lost booking state. Synthflow-class products break exactly here (mid-booking topic change loops to start). | Pipecat Flows guardrails: constrain to greeting / book / FAQ / transfer. Out-of-scope → transfer. |
| Real-time WebRTC web widget / app | "Also let people talk to it on the website." | Different transport, UX, and auth surface; dilutes the phone-receptionist focus. | Phone-first (Telnyx) for v1. Web is a later channel if validated. |
| Web admin dashboard with rich UI (in v1) | "Owners want a pretty panel." | UI work is a time sink that doesn't validate the core call loop. | CLI / minimal panel for onboarding in M5; rich dashboard is v2 once the engine is proven. |
| Postgres from day one | "We'll need to scale." | Premature ops complexity before product-market fit. Already Out of Scope as a starting point. | SQLite/JSON now; code structured behind a data layer so the Postgres migration is mechanical later. |

## Feature Dependencies

```
Natural low-latency Italian conversation (M1)
    └──requires──> STT (Deepgram it-IT) + LLM (Claude streaming) + TTS (ElevenLabs streaming)
    └──requires──> Barge-in / turn detection (Pipecat VAD + Smart Turn)

Reservation/appointment capture (M2)
    └──requires──> Conversation engine (M1)
    └──requires──> Pipecat Flows (structured nodes + tool calling)
    └──requires──> Availability/capacity check
                       └──requires──> CalendarProvider (Google Calendar read)
                       └──requires──> Per-tenant booking rules (hours/capacity/buffers)
    └──requires──> Calendar write (Google Calendar write)
    └──enhanced-by──> Spoken booking read-back + confirmation

FAQ via RAG (M2)
    └──requires──> Conversation engine (M1)
    └──requires──> Per-client knowledge base store

Human handoff / transfer (M3 logic, M4 real)
    └──requires──> Transfer decision logic (explicit / low-confidence / out-of-scope / non-Italian)
    └──requires──> Telnyx SIP REFER/Dial (real transfer) ......... (M4)
    └──enhanced-by──> Warm transfer context briefing

End-of-call summary + owner notification (M3)
    └──requires──> Full transcript capture (from STT log)
    └──requires──> Summary generation (Claude)
    └──requires──> Notification layer (channel abstraction)

Real inbound calls (M4)
    └──requires──> Telephony abstraction + Telnyx impl
    └──requires──> Dialed-number → tenant routing (couples to M5 multi-tenant)

Multi-tenant config (M5)
    └──unlocks──> Per-tenant: greeting, voice_id (voice cloning), hours, services/menu,
                  booking rules, transfer number, KB, notification channel
    └──requires──> Onboarding CLI/panel + config schema + data store
    └──depends-on──> Every prior feature being parameterized (not hardcoded)

Per-client voice cloning (M5) ──requires──> TTS layer parameterized by voice_id
STT fallback (faster-whisper) ──enhances──> Conversation reliability (M1+)
```

### Dependency Notes

- **Capacity check must precede calendar write:** Writing first then validating risks confirmed-but-unhonorable bookings. Read availability → apply tenant rules → confirm with caller → write.
- **Multi-tenant (M5) depends on everything being parameterized first:** Each earlier milestone should read its values from a config object (even a single hardcoded tenant in M1-M4), so M5 is "swap the source to the DB," not a rewrite. Build M1-M4 against a tenant-config struct from the start.
- **Real transfer (M4) gates warm-transfer richness:** M3 can build and test transfer decision logic locally (decide + announce + log), but the actual call bridge needs Telnyx. Cold transfer is the MVP; warm/whisper is the upgrade once telephony exists.
- **Dialed-number routing couples M4 and M5:** The Telnyx inbound number is the natural tenant key. M4 can ship single-tenant; the routing abstraction should anticipate the M5 lookup.
- **Non-Italian transfer reuses the M3 handoff path:** It is not a separate feature — it is one more trigger feeding the existing transfer logic. Cheap once handoff exists.

## MVP Definition

### Launch With (v1) — aligns to M1–M5

- [ ] Low-latency natural Italian conversation with barge-in — the product is nothing without this (M1)
- [ ] Per-client greeting + graceful fallback phrases — minimum personalization + no dead air (M1)
- [ ] Structured booking flow (date/time/party-or-service/name/phone) via Pipecat Flows (M2)
- [ ] Availability/capacity check + real Google Calendar write behind `CalendarProvider` (M2)
- [ ] Spoken booking confirmation / read-back (M2)
- [ ] RAG FAQ on per-client KB (hours, address, services, prices) (M2)
- [ ] Human transfer to configurable number on request / uncertainty / out-of-scope / non-Italian (M3 logic, M4 real)
- [ ] End-of-call log + summary (transcript, outcome, reservation) (M3)
- [ ] Owner notification via configurable channel (email/SMS/WhatsApp/Telegram/log) (M3)
- [ ] Real inbound Italian calls via Telnyx behind telephony interface (M4)
- [ ] Multi-tenant config (client = config record) + onboarding CLI (M5)
- [ ] Per-client voice cloning via ElevenLabs `voice_id` (M5)

### Add After Validation (v1.x)

- [ ] STT fallback (faster-whisper self-hosted) — add when Deepgram reliability/cost becomes a concern
- [ ] Warm transfer with structured context briefing/whisper — upgrade once cold transfer proves the path
- [ ] Outcome analytics (booking conversion, transfer rate) from accumulated summaries — add once enough call data exists
- [ ] Richer booking rules (table-combination party-size logic, per-provider calendars, per-service durations) — add as real clients reveal their rules
- [ ] Minimal web onboarding panel (over the CLI) — when onboarding volume justifies it

### Future Consideration (v2+)

- [ ] Twilio telephony implementation (interface already abstracts it) — only if Telnyx becomes limiting
- [ ] Postgres migration — when concurrency/scale demands it
- [ ] Specific PMS/POS/EHR integrations beyond Google Calendar — per concrete client demand
- [ ] Web/app voice channel — only after phone-first is validated

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Low-latency Italian conversation + barge-in | HIGH | HIGH | P1 |
| Per-client greeting | HIGH | LOW | P1 |
| Graceful fallback phrases | HIGH | MEDIUM | P1 |
| Structured booking flow (Pipecat Flows) | HIGH | MEDIUM | P1 |
| Availability/capacity check | HIGH | MEDIUM-HIGH | P1 |
| Google Calendar write | HIGH | MEDIUM | P1 |
| Spoken booking confirmation | HIGH | LOW | P1 |
| RAG FAQ on per-client KB | HIGH | MEDIUM | P1 |
| Human transfer (configurable number) | HIGH | MEDIUM-HIGH | P1 |
| Non-Italian → transfer | MEDIUM | LOW | P1 |
| End-of-call summary | HIGH | MEDIUM | P1 |
| Owner notification (configurable channel) | HIGH | MEDIUM | P1 |
| Real inbound calls (Telnyx) | HIGH | HIGH | P1 |
| Multi-tenant config | HIGH | HIGH | P1 |
| Onboarding CLI | MEDIUM | MEDIUM | P1 |
| Per-client voice cloning | MEDIUM | LOW-MEDIUM | P1 (M5) |
| STT fallback (faster-whisper) | MEDIUM | MEDIUM | P2 |
| Warm transfer briefing | MEDIUM | MEDIUM-HIGH | P2 |
| Outcome analytics | MEDIUM | LOW-MEDIUM | P2 |
| Rich booking-rules engine | MEDIUM | HIGH | P2 |
| Web onboarding panel | LOW-MEDIUM | MEDIUM | P3 |
| Twilio telephony | LOW (now) | MEDIUM | P3 |
| Postgres migration | LOW (now) | MEDIUM | P3 |

**Priority key:** P1 = must have for launch (v1, distributed across M1–M5) · P2 = should have, add when possible (v1.x) · P3 = nice to have, future (v2+)

## Competitor Feature Analysis

| Feature | Managed platforms (Synthflow / Vapi / Retell / Bland) | Vertical SMB tools (Yelp Host / voiceOne / HuskyVoice / Loman) | Our Approach |
|---------|---------------------------|-------------------------------|--------------|
| Stack ownership | Hosted, per-minute markup, vendor lock-in | Hosted, vertical-tuned | Fully self-hosted, owned pipeline (core differentiator) |
| Barge-in / turn-taking | Tunable (Vapi strong) | Abstracted away | Pipecat native VAD + Smart Turn, tuned per message type |
| Booking flow | Generic; can loop on off-script changes | Vertical (party size, waitlist, callback) | Pipecat Flows guardrails; restaurant + clinic vertical fields |
| Capacity logic | Calendar conflict only | Real table/party-size logic (HuskyVoice) | Per-tenant rules; start hours+slots, grow to party-size logic |
| Calendar write | Google/Cal.com/Calendly connectors | POS/PMS write | Google Calendar real write behind `CalendarProvider` |
| FAQ / KB | RAG, sometimes knowledge graph | URL/menu-doc ingestion | Simple per-client RAG (hours/address/services/prices) |
| Human handoff | Cold + warm + conference | Transfer to staff | Cold (MVP) → warm/whisper; non-Italian trigger |
| Summaries/notifications | Email + CRM sync (HubSpot/Salesforce) | SMS/WhatsApp to team | Multi-channel layer, per-tenant choice (email/SMS/WhatsApp/Telegram/log) |
| Multi-tenant | White-label agency dashboards (Synthflow) | Per-location config | Client = config record; CLI onboarding; no code per client |
| Voice cloning | Stock + cloning (varies) | Mostly stock | Per-client ElevenLabs `voice_id` |
| Italian support | RingCentral/Imagicle/GoTo multilingual incl. IT | Varies | Italian-first, intentionally single-language (non-IT → transfer) |

## Sources

- Retell AI — Best AI Voice Platforms for Virtual Receptionists: https://www.retellai.com/blog/best-ai-voice-platforms-virtual-receptionists
- Restaurant Technology News — How Voice AI Is Changing Phone Reservations: https://restauranttechnologynews.com/2025/12/how-voice-ai-is-changing-the-way-restaurants-handle-phone-reservations/
- Hamming AI — Voice Agent Interruption Handling Runbook (barge-in, backchannels, turn detection): https://hamming.ai/resources/voice-agent-interruption-handling-runbook
- Future AGI — Voice AI Barge-In and Turn-Taking Implementation Guide: https://futureagi.com/blog/voice-ai-barge-in-turn-taking-2026/
- Pipecat Flows (GitHub): https://github.com/pipecat-ai/pipecat-flows
- Daily.co — Why Your Voice Agent Needs Structure with Pipecat Flows: https://www.daily.co/blog/beyond-the-context-window-why-your-voice-agent-needs-structure-with-pipecat-flows/
- Famulor — AI Voice Agent Call Transfer to a Human (2026 Guide): https://www.famulor.io/blog/ai-voice-agent-call-transfer-to-a-human-the-2026-guide
- Telnyx — AI-to-Human Handoff for Voice AI Agents: https://telnyx.com/resources/ai-to-human-handoff-voice-ai
- LiveKit — The Handoff Pattern for Voice Agents That Replaces IVR Menus: https://livekit.com/blog/handoff-pattern-voice-agents
- Ainora — AI Voice Agent + Google Calendar Integration: https://ainora.lt/blog/ai-voice-agent-google-calendar-integration
- HuskyVoice — AI Restaurant Reservation & Table Booking: https://www.huskyvoice.ai/ai-restaurant-reservation-and-table-booking
- MindStudio — Voice Agents, ElevenLabs, RAG, and Calendar Booking: https://www.mindstudio.ai/blog/voice-agents-business-elevenlabs-rag-calendar-booking
- Regal.ai — RAG Playbook: Structuring Scalable Knowledge Bases: https://www.regal.ai/blog/rag-playbook-structuring-knowledge-bases
- Webfuse — Top 5 Voice AI Agent Failures and How to Fix Them: https://www.webfuse.com/blog/top-5-voice-ai-agent-failures-and-how-to-fix-them
- AssemblyAI — How to Add Automatic LLM Fallbacks to Your Voice Pipeline: https://www.assemblyai.com/blog/how-to-add-automatic-llm-fallbacks-to-voice-pipeline
- ElevenLabs — Agents / Voice Cloning (multi-tenant, per-client voice): https://elevenlabs.io/agents
- RingCentral / Imagicle / GoTo — Italian-language receptionist + per-location greetings (table-stakes confirmation): https://www.imagicle.com/en/products/ai-virtual-receptionist/
- Telnyx — Voice API / SIP REFER call transfer: https://telnyx.com/release-notes/transfer-calls-with-sip-refer-live

---
*Feature research for: self-hosted AI voice telephony receptionist for small Italian businesses*
*Researched: 2026-06-23*
