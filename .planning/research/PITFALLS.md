# Pitfalls Research

**Domain:** Self-hosted real-time AI voice telephony receptionist (Pipecat + Deepgram IT STT + Claude tool-calling + ElevenLabs TTS + Telnyx), multi-tenant, Italian SMBs
**Researched:** 2026-06-23
**Confidence:** MEDIUM-HIGH (Pipecat/latency/telephony/failover findings verified across official docs + multiple production write-ups; Italian-STT-specific WER and ElevenLabs-consent numbers are MEDIUM/LOW where noted)

> Phase map (from milestone context):
> **M1** = local agent (mic/headset, STT→LLM→TTS, Italian, greeting, barge-in, fallbacks) ·
> **M2** = booking flow + capacity check + Google Calendar + RAG FAQ ·
> **M3** = human handoff + end-of-call summary/notifications ·
> **M4** = Telnyx real telephony (inbound IT numbers, media streaming) ·
> **M5** = multi-tenant config (per-client records, onboarding CLI/panel).

---

## Critical Pitfalls

### Pitfall 1: The `aggregation_timeout` silent 1-second tax (latency budget blown before you start)

**What goes wrong:**
Pipecat's LLM user-aggregator waits `aggregation_timeout` seconds after the user stops before forwarding the transcript to the LLM. The v0.0.57+ default (~1.0s) adds a full second to **every** turn. With an 800ms total budget, a single config default doubles your latency. Production write-ups report this is the single largest source of "the bot feels slow" complaints — more than STT/LLM/TTS combined.

**Why it happens:**
It's a default buried in the aggregator, not in your pipeline code. It exists to coalesce fragmented final transcripts, but most teams never see it until they instrument per-stage timings. Easy to mistake the lag for "the LLM being slow."

**How to avoid:**
- Lower `aggregation_timeout` aggressively (teams report 0.1–0.3s) and rely on Deepgram endpointing / Pipecat Smart Turn for turn boundaries instead.
- Instrument **per-stage** latency from day one: STT-final, LLM TTFT, TTS TTFB, transport. Don't measure only end-to-end — you can't fix what you can't attribute.
- Budget reference (WebRTC/local): STT finalize 50–100ms, LLM TTFT 100–200ms, TTS TTFB 50–80ms, transport 20–50ms → ~220–430ms. Phone (PSTN) adds 150–700ms transport, so on Telnyx you have far less slack and the timeout tax becomes fatal.

**Warning signs:**
Bot reliably responds ~1s after you stop talking even on trivial replies; end-to-end latency is ~1s higher than the sum of measured component latencies.

**Phase to address:** M1 (set + verify the timeout while building the local pipeline; lock in per-stage instrumentation).

---

### Pitfall 2: Non-streaming / waterfall pipeline (waiting for full transcript → full LLM response → full audio)

**What goes wrong:**
The naive build waits for the **complete** final transcript, sends it, waits for the **complete** LLM response, then synthesizes the **complete** audio. Each handoff is a serialized wait. This "waterfall" easily produces 2–4s responses and is the default mental model most people start with.

**Why it happens:**
It's the simplest thing to wire up and it works in a demo. Streaming requires LLM token streaming + TTS sentence/word chunking + frame-based concurrency, which feels like premature optimization until you hear the lag on a real call.

**How to avoid:**
- Stream at **every** stage: Deepgram streaming STT, Claude streaming tokens, ElevenLabs streaming TTS. Start TTS on the first sentence/clause, not the full message.
- Use ElevenLabs Flash v2.5 (~75ms TTFB) for the conversational path; reserve higher-quality models for non-latency-critical spots (greeting can be pre-rendered).
- Use ElevenLabs websocket input with `auto_mode=true` so generation triggers automatically instead of waiting on a chunk schedule.
- Pre-render/cache the per-client greeting audio — don't pay TTS latency on the first impression.

**Warning signs:**
TTS only starts speaking after the LLM has fully finished; first audio byte arrives >1s after STT-final; greeting takes 4–5s on first call.

**Phase to address:** M1 (architect streaming from the start — retrofitting streaming into a waterfall is a rewrite).

---

### Pitfall 3: Barge-in broken because output audio starves the input/VAD thread (WebSocket transport)

**What goes wrong:**
While the bot is speaking, the user's interruption isn't detected — `UserStartedSpeakingFrame` never fires, the bot talks over the caller, and it feels robotic. Documented Pipecat issue (#2460): synchronous output-audio writes consume the thread that should be receiving inbound audio, so server-side VAD never runs during bot speech — exactly when barge-in must work.

**Why it happens:**
WebSocket transport + blocking audio writes. The bug only surfaces *while the bot is talking*, so it passes every "ask a question, get an answer" test and fails the moment a real human interrupts.

**How to avoid:**
- Prefer **WebRTC** over WebSockets for the audio transport where you control it (Pipecat co-founder's explicit production recommendation: UDP, NAT traversal, much better interruption handling). For Telnyx telephony you're constrained to its media-streaming WebSocket, so this pitfall is highest-risk on the phone path — test barge-in there explicitly.
- Ensure non-blocking output audio (fire-and-forget via `asyncio.create_task`) so the input/VAD loop keeps running during playback.
- Verify VAD is actually processing inbound frames *during* TTS playback, not just between turns.

**Warning signs:**
You can't interrupt the bot mid-sentence; logs show "Emulating user started speaking" instead of real `UserStartedSpeakingFrame`; interruption latency >1s (target <200ms).

**Phase to address:** M1 (barge-in is a core requirement; build + test it locally). Re-verify in **M4** because Telnyx forces the WebSocket transport.

---

### Pitfall 4: VAD / endpointing false triggers and missed short utterances (Italian backchannels)

**What goes wrong:**
Two opposite failures: (a) background noise, TV, café chatter, and Italian backchannels ("mhm", "sì", "eh", "allora") trigger false interruptions that cut the bot off mid-sentence; (b) brief but meaningful replies ("sì", "no", "ok", "due") are dropped because VAD requires ~200ms minimum speech. For a receptionist, "sì"/"no"/short numbers are the most common and most critical answers.

**Why it happens:**
A single confidence threshold can't separate noise from speech across all environments, and the minimum-speech-duration guard discards exactly the short confirmations bookings depend on. Italian conversational fillers are frequent and short.

**How to avoid:**
- Tune VAD threshold + min-speech-duration for telephony (8kHz, noisy lines) rather than using clean-mic defaults.
- Evaluate Pipecat Smart Turn (semantic turn detection) instead of raw VAD-only endpointing. **But:** Smart Turn v3 silently breaks if `audio_in_sample_rate=8000` — set only `audio_out_sample_rate=8000` and let the Telnyx serializer handle upsampling (documented 51% turn-duration regression otherwise).
- Add light debounce / grammar-aware handling for yes/no/number confirmations.
- Test with realistic noisy audio + accents, not a quiet room — voice agents score far worse on realistic audio than clean text.

**Warning signs:**
Bot interrupts itself in noisy rooms; "sì"/"no"/single-digit answers get ignored or mistranscribed; turn duration drops ~50% after a sample-rate change.

**Phase to address:** M1 (basic endpointing/barge-in tuning), revisited in **M4** (telephony 8kHz, real line noise).

---

### Pitfall 5: Italian STT errors on numbers, dates, times, names, addresses (the data bookings depend on)

**What goes wrong:**
The exact fields a reservation needs — date, time, party size / service, name, phone number, address — are the hardest for STT and the costliest to get wrong. "le otto" vs "le otto e mezza", "venti" vs "venté", phone digits, surnames, and street names are easily mis-recognized. A wrong digit in a phone number or a wrong time silently corrupts the booking.

**Why it happens:**
General STT models optimize for overall WER, not for spelled digits / proper nouns. Italian dates/times have many homophone-adjacent forms. Deepgram added Italian to Nova-3 only recently (Jan 2026), and proper-noun accuracy is the known weak spot of any STT.

**How to avoid:**
- Use Deepgram Nova-3 **keyterm prompting** to bias toward expected proper nouns (the client's menu items, services, common local surnames/streets, business name).
- Capture numerics via formatting/normalization (Deepgram numerals/`smart_format`) and **always read back** critical fields ("Confermo: martedì 8 luglio, ore 20, per 4 persone, a nome Rossi, telefono …") before writing the booking. Read-back is the single most effective mitigation.
- Prefer DTMF for phone-number / digit entry on the phone path when STT confidence is low (caller types the number) — but see Pitfall 11 on DTMF codec reliability.
- Don't over-trust a single transcript for names — offer spelling ("me lo conferma lettera per lettera?") on low confidence.

**Warning signs:**
Bookings with implausible times, off-by-one party sizes, phone numbers with wrong digit counts, garbled surnames in summaries; owner complaints about wrong reservation details.

**Phase to address:** M1 (Italian STT config, numerals, read-back habit in the prompt), deepened in **M2** (booking field validation + capacity check uses these values).

---

### Pitfall 6: Claude hallucinating availability / inventing booking confirmations (LLM-as-source-of-truth)

**What goes wrong:**
The LLM "confirms" a reservation or asserts a slot is free **without** actually calling the calendar tool, or fabricates a confirmation when a tool call failed. The caller hangs up believing they have a 8pm table that was never written anywhere. ~9% of Claude tool invocations involve some hallucination in studies; for booking that's unacceptable if unguarded.

**Why it happens:**
With a big system prompt and no structural gating, the model treats "confirm the booking" as a conversational act it can perform with words. It may also narrate success optimistically after a silent tool failure.

**How to avoid:**
- **Never** let the model self-report success. The booking is confirmed only when the `CalendarProvider.create_event` tool returns a real event ID; the confirmation phrasing must be driven by that tool result, not the model's discretion.
- Use **Pipecat Flows** to gate: availability can only be asserted after a `check_availability` tool result; "confirmed" can only be said after a successful `create_event`. Keep this logic outside the context window (Flows is the control layer for exactly this).
- System prompt rule: "Mai confermare una prenotazione o una disponibilità senza il risultato dello strumento. Se lo strumento non risponde, di' che verifichi e proponi il trasferimento."
- Low temperature for the booking path; tight max tokens to avoid speculative over-talking.

**Warning signs:**
Confirmations in transcripts with no corresponding calendar event; "il tavolo è disponibile" with no preceding `check_availability` call; mismatches between summary "esito: prenotato" and the calendar.

**Phase to address:** M2 (booking flow + Flows gating + tool-result-driven confirmation). Flows scaffolding decided in M1.

---

### Pitfall 7: Google Calendar double-booking race (no atomic slot reservation)

**What goes wrong:**
The Google Calendar API has **no atomic check-and-reserve**. Two concurrent calls (two callers, or a caller + a walk-in being entered) both see the slot free and both create events → double-booking. Documented as a real, recurring failure in voice-agent + Calendar integrations. The API also returns **busy** times (freebusy), not free slots — teams that invert this incorrectly leak availability.

**Why it happens:**
"Check availability, then create event" looks atomic but isn't — there's a window between the read and the write. Single-call demo testing never exposes it.

**How to avoid:**
- Treat capacity as **your** invariant, not Google's. Maintain authoritative slot/capacity state in your own DB (the project already requires a config DB) and do the **check-and-insert in a single transaction** (optimistic locking / unique constraint on slot) — Calendar becomes the projection, not the lock.
- **Re-check availability immediately before** `create_event` to shrink (not eliminate) the window.
- Correctly interpret freebusy: explicitly verify the `busy` array is empty for the slot; apply consistent timezone (Europe/Rome) and buffer/overlap handling.
- For a restaurant, model **capacity** (covers) not just slot occupancy — multiple bookings per time are normal up to a limit.

**Warning signs:**
Two reservations on the same slot/table; intermittent (load-dependent) double-bookings; off-by-timezone bookings (UTC vs Europe/Rome); availability shown for already-full slots.

**Phase to address:** M2 (capacity model + transactional reservation + Calendar write behind `CalendarProvider`). This is the project's "verifica capienza prima di confermare" requirement — design it transactional from the start.

---

### Pitfall 8: RAG FAQ that invents hours, prices, and policies

**What goes wrong:**
The FAQ layer answers "siete aperti a Ferragosto?" or "quanto costa la visita?" with a confident, **wrong** number it pattern-matched or made up. For a receptionist, wrong hours/prices are direct business harm (lost customers, angry owners). Grounding alone is "necessary but nowhere near sufficient" — a dirty or thin KB produces wrong answers faster.

**Why it happens:**
Retrieval misses or returns weakly-relevant chunks, and the model fills the gap from training priors instead of saying "I don't know." Unstructured/stale per-client KBs make this worse.

**How to avoid:**
- Strict grounding: instruct the model to answer **only** from retrieved KB context; if the answer isn't in context, say it will check / offer transfer rather than guess.
- Put high-stakes facts (orari, prezzi, indirizzo, servizi) as **structured config fields**, not just free-text KB — answer those from config deterministically, reserve RAG for genuinely open questions.
- KB governance: per-client KB freshness/ownership; show owners exactly what their bot will say. Outdated KB = wrong answer at speed.
- Low temperature on FAQ; cite/log which chunk produced the answer for auditing.

**Warning signs:**
Bot states hours/prices that don't match config; answers questions with no matching KB chunk; owner reports "il bot ha detto una cosa sbagliata."

**Phase to address:** M2 (RAG FAQ + structured-fact fields). KB schema is part of the per-client config designed for **M5**.

---

### Pitfall 9: Silent provider failures mid-call with no ErrorFrame (the bot just goes mute)

**What goes wrong:**
Deepgram/ElevenLabs/STT can fail to initialize or drop mid-call **without emitting an `ErrorFrame`** — the bot simply goes unresponsive and the caller hears dead air. Documented: Deepgram drops ~1 in 50 calls; ElevenLabs can enter infinite reconnect loops; some STT websockets die after 60–70s of silence with no reconnection. There's no built-in graceful fallback to faster-whisper or to "let me transfer you."

**Why it happens:**
Pipecat surfaces some failures only as missing frames, not errors, so naive code has nothing to catch. Happy-path testing (short, continuous speech) never hits the 60–70s silence death or the 1-in-50 drop.

**How to avoid:**
- Wrap each provider with **health checks + circuit breakers + timeouts**. On STT failure → switch to the predisposed **faster-whisper** fallback (already a project requirement); on LLM/TTS failure → courtesy phrase ("Un momento, c'è un problema tecnico…") then **transfer to human**.
- Detect dead air explicitly (watchdog: no STT result + no TTS output for N seconds → recover/transfer) rather than relying on ErrorFrames.
- Add reconnection logic + keepalive for STT websockets; cap reconnect attempts to avoid infinite loops.
- Pattern (from production): circuit breaker → backup flow that apologizes, logs, and offers human transfer / SMS callback.

**Warning signs:**
Calls with long dead-air gaps; STT stops returning results after ~1 min of silence; ElevenLabs reconnect spam in logs; "the bot stopped responding" reports with no error logged.

**Phase to address:** M1 (fallback scaffolding: courtesy phrases, faster-whisper switch, dead-air watchdog — it's an explicit requirement). Transfer-on-failure completed in **M3**; re-test under real telephony in **M4**.

---

### Pitfall 10: One process ≠ one session (concurrency model wrong → whole service hangs)

**What goes wrong:**
Running multiple concurrent calls in one process (e.g., a `ThreadPoolExecutor` of sessions) makes the service completely unresponsive, requiring `SIGKILL`. The validated production pattern is **1 container = 1 session = 1 process**. There's also a documented v0.0.85+ memory leak (~3GB/min on Linux/K8s with Deepgram+OpenAI+ElevenLabs pipelines) that OOM-kills pods.

**Why it happens:**
Pipecat pipelines hold blocking/async state that doesn't cleanly multiplex across sessions in one process; people reach for thread pools to "save resources." The leak is version-specific and invisible in single short test calls.

**How to avoid:**
- Architect for **one session per process/worker**; scale by spawning processes/containers, not threads-in-process. Bake this into the design even for the local M1 build so M4/M5 scaling doesn't require restructuring.
- Pin/track Pipecat versions and watch release notes for the memory-leak regressions; monitor RSS per session in soak tests.
- Run a multi-minute soak/concurrency test before considering telephony "done."

**Warning signs:**
Service freezes under 2+ concurrent calls; RSS climbs steadily during a call; pods OOM-killed; need to `SIGKILL` to recover.

**Phase to address:** Design awareness in **M1**; enforced/tested in **M4** (real concurrent inbound calls) and **M5** (many tenants).

---

### Pitfall 11: Telnyx telephony gotchas — codecs, DTMF, 8kHz, transport, and transfer mechanics

**What goes wrong:**
Multiple phone-specific failures that don't exist on the local mic path:
- **DTMF unreliable** on compressed codecs: tones are destroyed by G.729/Opus; in-band DTMF gets distorted. Over websocket, DTMF events are async and can arrive **out of order**. If you use DTMF for phone-number entry (Pitfall 5 mitigation), this breaks it.
- **Codec/sample-rate:** Telnyx default is PCMU 8kHz. Using the wrong sample rate silently breaks Smart Turn (Pitfall 4). Transcoding adds latency; L16/PCM reduces it for AI.
- **Transport:** Telnyx media streaming is over **WebSocket**, re-exposing the barge-in/VAD-starvation risk (Pitfall 3).
- **Transfer mechanics:** cold transfer (SIP REFER) is the easy default; **warm transfer** (agent dials human, summarizes, bridges caller) requires Dial+Bridge call-control composition and is much more work — the project wants context-rich handoff, which implies warm.
- **Geography/latency:** keep the bot + providers co-located near Italy; cross-region hops add 50–300ms, and PSTN already costs 150–700ms.

**Why it happens:**
The local mic milestone hides all of this. Telephony reintroduces 8kHz audio, lossy codecs, async DTMF, and SIP semantics at once in M4.

**How to avoid:**
- For DTMF use **RFC 2833** (out-of-band) not in-band; treat DTMF events as possibly out-of-order; prefer STT+read-back over DTMF where codecs are lossy.
- Set `audio_out_sample_rate=8000` only; let `TwilioFrameSerializer`/Telnyx serializer handle upsampling. Prefer L16/PCM where supported to cut transcoding latency.
- Re-test barge-in, endpointing, and dead-air recovery **on the real phone path** — they were validated on WebRTC/mic in M1.
- Decide cold vs warm transfer early; warm transfer (summary before pickup) needs Dial+Bridge and call-control orchestration — budget for it.
- Co-locate compute with EU/Italy region; measure PSTN-leg latency separately.

**Warning signs:**
Missed/misread DTMF digits; barge-in that worked locally fails on calls; turn detection regresses after going to telephony; high latency only on phone; transfers drop the caller or arrive with no context.

**Phase to address:** **M4** (Telnyx integration) — but keep the telephony layer behind the abstraction (already a requirement) so Twilio swap and these tunables stay isolated. Warm-transfer + context handoff overlaps **M3** (handoff) ↔ **M4** (telephony mechanics).

---

### Pitfall 12: Voice cloning — consent, quality, and per-client `voice_id` mismanagement

**What goes wrong:**
Three failures: (a) cloning an owner's/operator's voice **without explicit documented consent** (GDPR/biometric + ElevenLabs ToS exposure in the EU); (b) poor clone quality from thin/noisy training audio (clones add 80–120ms first-byte latency and the residual quality issues are usually bad training data); (c) wrong `voice_id` served to the wrong tenant — Client A's voice on Client B's calls.

**Why it happens:**
Consent is a process, not code, so it's skipped under time pressure. Clone quality is assumed "good enough" without listening on a phone line (8kHz reveals artifacts). `voice_id` is just a config string, so a tenant-isolation bug routes it to the wrong call.

**How to avoid:**
- Require and **store** explicit consent per cloned voice before onboarding it; keep an audit record. Default to a high-quality stock Italian voice; cloning is opt-in.
- For latency-sensitive turns prefer Instant Voice Clone + Flash and `optimizeStreamingLatency` (3–4) over Professional Voice Clone; validate clone quality **on the 8kHz phone codec**, not just in the browser.
- Bind `voice_id` to the tenant config record and assert tenant→voice_id at session start (part of Pitfall 13 isolation tests).

**Warning signs:**
Robotic/artifacted clone on phone calls; latency spike only for cloned-voice clients; a client reports "that's not my voice"; no consent record on file.

**Phase to address:** Stock voice in **M1**; clone plumbing (`voice_id` per config) in **M5**; consent process is a **M5** onboarding gate.

---

### Pitfall 13: Multi-tenant config bleed — one engine serving the wrong client's data

**What goes wrong:**
Because every client is a config record on one shared engine, a missing/incorrect tenant scoping can leak Client A's greeting, hours, prices, KB, transfer number, calendar, or `voice_id` into Client B's call. Documented high-severity multi-tenant patterns: parameter injection via the inbound payload, stale in-memory tenant mappings, and credential reuse across tenants.

**Why it happens:**
The tenant is resolved once (by called number / DID) and then assumed throughout; global/singleton state or cached config from a previous call carries over. Single-tenant testing never exercises cross-tenant isolation.

**How to avoid:**
- Resolve tenant **deterministically from the inbound DID** and thread an immutable tenant context through the whole session (no globals/singletons holding per-call config).
- Every config/KB/calendar/DB read is **filtered by `tenant_id`** at the source; no query without it.
- Per-tenant credential isolation: a tenant's Google Calendar token / notification channel must never be reachable from another tenant's session.
- Add an explicit isolation test: two simultaneous calls to two different DIDs must never cross greeting, KB, voice, calendar, or transfer number.

**Warning signs:**
Wrong business name/greeting on a call; FAQ answers from another client's KB; booking written to the wrong calendar; transfer to the wrong number; values "sticking" from the previous call.

**Phase to address:** **M5** (multi-tenant) — but the **abstraction boundaries and tenant-scoped config access must be designed in M1–M2** so M5 is wiring, not a refactor. Structure code for `tenant_id` filtering from the first DB touch.

---

### Pitfall 14: Secrets / `.env` mishandling and per-tenant credential sprawl

**What goes wrong:**
API keys (Deepgram, ElevenLabs, Anthropic, Telnyx) and per-tenant Google Calendar OAuth tokens / notification credentials get hardcoded, committed, logged, or shared across tenants. GitGuardian found ~29M hardcoded secrets in public GitHub commits in 2025; a real April-2026 incident saw an agent reach prod and delete a DB via a long-lived, over-scoped token found in an unrelated file.

**Why it happens:**
"BYO API keys" + multi-tenant means many secrets per client; the easy path is one `.env` with everything, tokens that never expire, and broad scopes. With no keys available yet, placeholders can drift into real keys committed by accident.

**How to avoid:**
- Ship `.env.example` with placeholders + step-by-step key-creation docs (already a requirement); `.env` git-ignored; never log secret values.
- Per-tenant credentials stored encrypted in the config DB, scoped to that tenant, never cross-readable; design for rotation.
- Least privilege: Calendar tokens scoped to the single client's calendar; no account-wide tokens.
- Pre-commit secret scanning to catch accidental key commits before push.

**Warning signs:**
Secrets visible in repo history or logs; one shared key across all clients; tokens with no scope limits; Calendar token that can read multiple clients' calendars.

**Phase to address:** **M1** (`.env.example`, ignore rules, no-hardcoding, no-secret-logging). Per-tenant encrypted credential store hardened in **M5**.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Waterfall (non-streaming) pipeline | Fastest to a working demo | Latency rewrite; can't hit <800ms | Never for the conversational path; OK only for a throwaway spike |
| LLM self-reports booking "confirmed" | Skips tool plumbing | Phantom bookings, lost trust | Never — confirmation must be tool-result-driven |
| Calendar is the only source of truth for capacity | No extra DB | Double-booking race | Never for capacity; OK for solo-slot, very low volume only |
| High-stakes facts (hours/prices) only in free-text KB | Simple onboarding | RAG invents wrong values | Only for genuinely open FAQs; pin facts to config |
| One process, many sessions via threads | "Saves resources" | Service hangs, SIGKILL | Never — 1 process = 1 session |
| Single shared `.env` for all tenants' keys | Quick start | Credential bleed, blast radius | Only pre-multi-tenant (M1 single-client dev) |
| Skip read-back of booking fields | Shorter calls | Wrong dates/times/numbers in real bookings | Never for the phone path |
| Test only happy path / clean audio | Green tests fast | Barge-in, dead-air, DTMF, noise failures ship | Never as the only testing |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Pipecat aggregator | Leaving `aggregation_timeout≈1.0` | Lower to ~0.1–0.3s; rely on endpointing/Smart Turn |
| Pipecat Smart Turn v3 | Setting `audio_in_sample_rate=8000` | Set only `audio_out_sample_rate=8000`; let serializer upsample |
| Deepgram STT (websocket) | No reconnection; dies after 60–70s silence; ~1/50 drop | Keepalive + reconnect (capped) + dead-air watchdog |
| Deepgram Italian | Generic model, no biasing | Nova-3 + keyterm prompting (names/menu/streets) + numerals/smart_format |
| ElevenLabs | PVC + non-streaming; infinite reconnect loop | Flash + IVC + streaming/`auto_mode`; cap reconnects; pre-render greeting |
| Claude tool calling | Big prompt, no gating; trusts model to "confirm" | Pipecat Flows gating; confirm only on tool result; low temp |
| Google Calendar | Treat free/busy as slots; non-atomic check→create | Read busy[] correctly; own DB transactional reserve; re-check before write; Europe/Rome TZ |
| Telnyx DTMF | In-band DTMF on lossy codec; assume ordered events | RFC 2833; treat events as possibly out-of-order; prefer STT+read-back |
| Telnyx transport | Assume WebSocket = WebRTC interruption quality | Explicitly re-test barge-in/VAD on the phone path |
| Telnyx transfer | Assume warm transfer is built-in | Cold = SIP REFER (easy); warm = Dial+Bridge composition (build it) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `aggregation_timeout` tax | ~1s lag every turn | Lower timeout; instrument per-stage | Immediately, every call |
| Cross-region provider hops | Phone-only high latency | Co-locate bot + providers near Italy | As soon as PSTN added (M4) |
| Cold-start init (TTS/LLM/STT/transport sequential) | 3–8s before first response | Pre-warm/pre-cache greeting; parallelize init | First call after deploy/scale-up |
| Memory leak (v0.0.85+) | ~3GB/min RSS growth, OOM | Pin version; soak test; monitor RSS | Long calls / sustained load |
| Threads-per-session | Freeze under 2+ calls | 1 process = 1 session | First concurrent calls (M4/M5) |
| PVC voice clone latency | +80–120ms only for cloned clients | IVC + Flash + optimizeStreamingLatency | When clients enable cloning (M5) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Hardcoded/committed API keys | Key theft, abuse billing, data access | `.env` ignored, `.env.example` placeholders, pre-commit scanning, no secret logging |
| Per-tenant Calendar token shared/over-scoped | One client books/reads another's calendar | Encrypted per-tenant store, single-calendar scope, rotation |
| No tenant filter on config/KB/DB reads | Cross-tenant data leak | Mandatory `tenant_id` filter at source; immutable session tenant context |
| Voice cloned without consent | GDPR/biometric + ToS exposure (EU) | Stored explicit consent per voice; stock voice default; audit record |
| Logging full transcripts unprotected | PII (names, phones, health context for studi medici) leak | Minimize/redact PII in logs; access-control summaries; retention policy |
| Transfer/notification number injectable via payload | Calls/SMS routed to attacker | Resolve from trusted config by DID, never from call-supplied params |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Bot can't be interrupted | Feels robotic, callers talk over it | Working barge-in <200ms; non-blocking output audio |
| No read-back of booking details | Wrong reservations, no trust | Always confirm date/time/party/name/phone before writing |
| Confidently wrong hours/prices | Lost customers, owner anger | Ground strictly; pin facts to config; "I'll check" over guessing |
| Dead air on provider failure | Caller thinks line dropped | Courtesy phrase + fast transfer; dead-air watchdog |
| Non-Italian caller stuck with bot | Frustration, failed call | Detect non-Italian → transfer to operator (already in scope) |
| Cold transfer with no context | Human asks caller to repeat everything | Warm transfer w/ summary before pickup (M3↔M4) |
| Over-long, speculative bot replies | Slow, unnatural turns | Low temp, tight max tokens, concise persona |

## "Looks Done But Isn't" Checklist

- [ ] **Barge-in:** works in a quiet room AND while bot is mid-sentence AND over the real phone (WebSocket) path — verify `UserStartedSpeakingFrame` actually fires.
- [ ] **Latency:** per-stage instrumented (STT-final, LLM TTFT, TTS TTFB, transport), not just end-to-end; `aggregation_timeout` verified low.
- [ ] **Short answers:** "sì"/"no"/single digits are captured, not dropped by min-speech VAD.
- [ ] **Booking:** confirmation only fires on a real Calendar event ID; phantom-confirm path tested (force tool failure).
- [ ] **Double-booking:** two concurrent bookings on the same slot tested — only one succeeds; timezone is Europe/Rome.
- [ ] **FAQ:** ask something not in the KB — bot declines/transfers instead of inventing hours/prices.
- [ ] **Provider failure:** kill STT/LLM/TTS mid-call → courtesy phrase + transfer, no dead air; 60–70s silence doesn't kill STT.
- [ ] **DTMF (phone):** digits captured reliably on the real codec; out-of-order events handled.
- [ ] **Concurrency:** 2+ simultaneous calls don't freeze the service; RSS stable over a long call.
- [ ] **Multi-tenant:** two simultaneous calls to two DIDs never cross greeting/KB/voice/calendar/transfer number.
- [ ] **Secrets:** no keys in repo/logs; `.env.example` present; per-tenant tokens scoped + not cross-readable.
- [ ] **Voice clone:** consent recorded; clone validated on 8kHz phone audio; correct `voice_id` per tenant.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Waterfall pipeline shipped | HIGH | Re-architect to frame-based streaming; effectively a rewrite of the conversational path |
| Double-booking in prod | MEDIUM | Add transactional reserve + unique slot constraint; reconcile existing dupes manually; notify affected owners |
| Phantom confirmations | MEDIUM | Gate confirmation on tool result; audit transcripts vs calendar; backfill/cancel orphans |
| `aggregation_timeout` lag | LOW | Lower the parameter; re-measure |
| Barge-in/VAD starvation | MEDIUM | Switch to non-blocking output audio / WebRTC where possible; re-test phone path |
| Provider silent failure | MEDIUM | Add circuit breakers + watchdog + faster-whisper fallback + transfer-on-fail |
| Tenant config bleed | HIGH | Remove global state; thread immutable tenant context; add `tenant_id` filters + isolation tests; assume past calls may have leaked |
| Committed secret | MEDIUM | Rotate the key immediately; purge history; add pre-commit scanning |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. aggregation_timeout tax | M1 | Per-stage timings; turn lag ≈ component sum |
| 2. Waterfall pipeline | M1 | TTS starts on first clause; first-byte <1s after STT-final |
| 3. Barge-in/VAD starvation | M1 (build) / M4 (phone) | `UserStartedSpeakingFrame` fires mid-bot-speech; <200ms |
| 4. VAD false/missed triggers | M1 / M4 | Short "sì/no/numbers" captured; no self-interrupt in noise |
| 5. Italian STT numbers/names | M1 / M2 | Read-back matches; keyterm prompting on; valid phone digit counts |
| 6. Claude hallucinated availability | M2 (Flows in M1) | Confirmation only with event ID; no confirm without tool call |
| 7. Calendar double-booking | M2 | Concurrent-booking test: one wins; Europe/Rome TZ |
| 8. RAG invents hours/prices | M2 (KB schema → M5) | Out-of-KB question → decline/transfer; facts from config |
| 9. Silent provider failure | M1 (fallback) / M3 (transfer) / M4 (phone) | Kill-provider test → courtesy + transfer, no dead air |
| 10. Concurrency model | M1 (design) / M4–M5 (test) | 2+ calls stable; RSS flat over long call |
| 11. Telnyx codecs/DTMF/transfer | M4 (M3 for warm handoff) | DTMF reliable on real codec; barge-in re-verified on phone |
| 12. Voice cloning consent/quality | M5 (stock voice M1) | Consent on file; clone OK on 8kHz; right voice_id per tenant |
| 13. Multi-tenant config bleed | M5 (boundaries M1–M2) | Two-DID concurrent isolation test passes |
| 14. Secrets/.env | M1 (per-tenant store M5) | No keys in repo/logs; scoped per-tenant tokens |

## Sources

- Pipecat in Production — issues, optimization, scalable architecture (Luong Hong Thuan): https://luonghongthuan.com/en/blog/pipecat-voice-agent-production-scalable-guide/ — aggregation_timeout tax, 1-process-per-session, v0.0.85+ memory leak, silent provider failures, Smart Turn v3 8kHz bug, WebRTC-over-WebSocket. (MEDIUM-HIGH)
- Pipecat GitHub Issue #2460 — interruption handling over WebSocket / output-audio thread starvation: https://github.com/pipecat-ai/pipecat/issues/2460 (HIGH)
- Pipecat Flows — "Beyond the Context Window" (Daily): https://www.daily.co/blog/beyond-the-context-window-why-your-voice-agent-needs-structure-with-pipecat-flows/ — gating tools, context rot, structured flows. (HIGH)
- Voice AI pipeline latency budget (Chanl): https://www.channel.tel/blog/voice-ai-pipeline-stt-tts-latency-budget — per-stage budget, TTFT figures, TTS chunking. (MEDIUM)
- ElevenLabs latency optimization (official): https://elevenlabs.io/docs/eleven-api/guides/how-to/best-practices/latency-optimization — Flash, streaming, auto_mode, voice-type latency. (HIGH)
- ElevenLabs latency concepts (official): https://elevenlabs.io/docs/eleven-api/concepts/latency — PVC vs IVC, optimizeStreamingLatency, telephony region latency. (HIGH)
- Telnyx voice AI delay causes: https://telnyx.com/resources/voice-ai-delay-causes — VAD/STT/LLM/TTS/network delay ranges, legacy infra overhead. (MEDIUM)
- Telnyx media streaming + DTMF/codecs: https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming ; https://support.telnyx.com/en/articles/1130710 ; https://support.telnyx.com/en/articles/3192298 — codecs, RFC2833, out-of-order DTMF, L16. (HIGH)
- Telnyx AI-to-human handoff + transfers: https://telnyx.com/resources/ai-to-human-handoff-voice-ai ; https://telnyx.com/resources/voice-AI-agent-transfers — cold vs warm transfer, SIP REFER, Dial+Bridge. (MEDIUM-HIGH)
- Google Calendar double-booking / freebusy: https://vapi.ai/community/m/1387478334203756714 ; https://www.slotflow.dev/blog/google-calendar-api-busy-times-not-slots — no atomic reserve, busy vs slots. (MEDIUM)
- Claude reduce hallucinations (official): https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations ; tool-hallucination rate study: https://arxiv.org/pdf/2412.04141 (~9%). (HIGH / MEDIUM)
- RAG grounding / voice hallucination mitigation (Gladia, Retell, CXToday): https://www.gladia.io/blog/safety-voice-ai-hallucinations ; https://www.retellai.com/blog/the-ultimate-guide-to-ai-hallucinations-in-voice-agents-and-how-to-mitigate-them — grounding necessary-not-sufficient, KB governance. (MEDIUM)
- Deepgram Nova-3 Italian + keyterm prompting: https://deepgram.com/learn/deepgram-expands-nova-3-with-italian-turkish-norwegian-and-indonesian-support ; https://deepgram.com/learn/introducing-nova-3-speech-to-text-api — Italian (Jan 2026), keyterm prompting, numerals. (MEDIUM-HIGH)
- Voice AI failover/reliability patterns (CallSphere): https://callsphere.ai/blog/ai-voice-agent-failover-reliability-patterns — circuit breakers, active/standby, backup flow w/ SMS callback. (MEDIUM; partially via search snippet)
- faster-whisper fallback chains (Hermes Agent): https://hermes-agent.nousresearch.com/docs/user-guide/features/tts/ — local>cloud priority fallback pattern. (MEDIUM)
- Multi-tenant secrets/isolation (WorkOS, Scalekit, GitGuardian-cited): https://workos.com/blog/ai-agent-secrets-management ; https://www.scalekit.com/blog/access-control-multi-tenant-ai-agents — per-tenant key encryption, mandatory tenant_id filter, payload-injection/stale-mapping/token-reuse incidents. (MEDIUM-HIGH)

---
*Pitfalls research for: self-hosted multi-tenant Italian voice telephony receptionist (Pipecat/Deepgram/Claude/ElevenLabs/Telnyx)*
*Researched: 2026-06-23*
