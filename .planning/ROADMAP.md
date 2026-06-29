# Roadmap: Centralino AI

## Overview

Five milestones build the system inside-out, matching the dependency graph of the stack. The local voice loop (M1) locks in every architectural decision that is expensive to retrofit — streaming, barge-in, latency instrumentation, interface seams. Booking and FAQ (M2) exercise those seams with real external integrations. Handoff, summaries, and notifications (M3) close the safe-exit loop before telephony adds codec and transfer complexity. Telnyx real-call telephony (M4) is then a pure transport-layer swap. Multi-tenant hardening and onboarding tooling (M5) completes the "new client = new config row" promise. Each milestone is a hard stop-and-test gate: the next phase does not start until the owner validates the current one.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Local Voice Loop** - Italian conversational agent working locally on mic/headset with streaming pipeline, barge-in, personalized greeting, and latency instrumentation (completed 2026-06-24)
- [x] **Phase 2: Booking + Calendar + FAQ** - Structured Pipecat Flows booking with real Google Calendar write, capacity check, spoken read-back/confirm gating, and per-tenant RAG FAQ
 (completed 2026-06-26)
- [x] **Phase 3: Handoff + Summary + Notifications** - Operator transfer from any point, end-of-call log and summary, multi-channel owner notification, full provider-failure fallback chain with dead-air watchdog (code complete 2026-06-27; verification gaps_found — see 03-VERIFICATION.md) (completed 2026-06-29)
- [ ] **Phase 4: Telnyx Telephony** - Real inbound Italian calls via Telnyx, DID-to-tenant routing, all M1-M3 behaviors verified on the 8kHz phone path
- [ ] **Phase 5: Multi-Tenant + Onboarding** - Full per-client config isolation, tenant_id-scoped persistence, onboarding CLI, and per-client credential store

## Phase Details

### Phase 1: Local Voice Loop

**Goal**: A developer (or the owner using a headset) can hold a natural Italian conversation with the bot locally, interrupt it mid-sentence, receive a personalized greeting, and see per-stage latency numbers confirming the <800ms budget is met.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05, REL-01, SETUP-01
**Success Criteria** (what must be TRUE):

  1. Running `python main.py --tenant=demo` starts an Italian conversation with a greeting taken from the tenant config, with no keys hardcoded in source (all via `.env`).
  2. A caller can interrupt the bot mid-sentence and the bot stops speaking, listens, and responds — barge-in works reliably on the local mic path.
  3. The per-stage latency log (STT-final, LLM TTFT, TTS TTFB, transport) shows each stage is within budget and the end-to-end turn is under 800ms on a clean local connection.
  4. When STT, LLM, or TTS returns an error or times out, the bot speaks a courtesy phrase in Italian instead of going silent.
  5. The repo includes `.env.example` with placeholder keys and step-by-step account-creation instructions; cloning and filling `.env` is sufficient to run the project.

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Env + scaffold + pytest stubs + tenant config (SQLite) + interface seams + .env.example (SETUP-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Streaming pipeline + greeting-first + barge-in, run via `python main.py --tenant=demo` (VOICE-01/02/03/05)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Per-stage latency log (console + JSONL) + courtesy-phrase fallback (VOICE-04, REL-01)

### Phase 2: Booking + Calendar + FAQ

**Goal**: A caller can complete a full reservation by voice in Italian — supplying date, time, party size, name, and phone number — and the booking appears in the real Google Calendar for the correct client only after the caller verbally confirms the read-back, and only if the slot is within capacity.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: BOOK-01, BOOK-02, BOOK-03, BOOK-04, BOOK-05, BOOK-06, FAQ-01, FAQ-02, FAQ-03
**Success Criteria** (what must be TRUE):

  1. A caller can complete a reservation end-to-end by voice: the bot collects all required fields, reads them back, the caller confirms, the bot writes the event to Google Calendar and verbally confirms only after receiving a real event ID.
  2. If a requested time slot is at capacity, the bot declines the booking and proposes alternatives — no calendar event is created and no false confirmation is spoken.
  3. Two concurrent booking attempts on the same slot result in exactly one confirmed booking; the second caller is told the slot is no longer available.
  4. A caller who asks about hours, address, services, or prices receives an answer grounded in that client's knowledge base; if the information is not in the KB, the bot says it will check rather than inventing an answer.
  5. Each client's FAQ answers are drawn exclusively from that client's own knowledge base — no cross-tenant content appears.

**Plans**: 4 plans
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Foundation: verify model IDs, add deps, migrate schema (calendar_id + reservations/kb_documents/kb_chunks), extend config/repo/seed, all Wave 0 test stubs + fixtures (BOOK-01..06, FAQ-01..03)

**Wave 2** *(blocked on Wave 1)*

- [x] 02-02-PLAN.md — First vertical slice: end-to-end booking happy path — CalendarProvider (InMemory + Google), ReservationRepository (BEGIN IMMEDIATE), date parser, booking Flows nodes with tool-result-gated confirm (BOOK-01..06, SC1/SC3)

**Wave 3** *(blocked on Wave 2)*

- [x] 02-03-PLAN.md — Second slice: slot-full alternatives (same-day + next-day) + FlowManager wired into the pipeline with per-node Sonnet override (BOOK-02/04/05, SC2, D-19)

**Wave 4** *(blocked on Wave 3)*

- [x] 02-04-PLAN.md — FAQ slice: FTS5 KB + ingest + faq_lookup tool + FAQ node (hybrid config/FTS5 routing, honest not-found) + demo KB + live end-of-phase verification (FAQ-01..03, SC4/SC5) [tasks 1-2 done; checkpoint awaiting human verify]
**UI hint**: yes

### Phase 3: Handoff + Summary + Notifications

**Goal**: Every call ends with a logged record and a summary sent to the business owner on their preferred channel; any call can be transferred to a human operator from any point; and every provider failure degrades gracefully through courtesy phrases, a faster-whisper STT fallback, and ultimately a transfer to the operator rather than dead air.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: HAND-01, HAND-02, HAND-03, HAND-04, NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04, NOTIF-05, REL-02, REL-03, REL-04
**Success Criteria** (what must be TRUE):

  1. A caller who says "transfer me to a person" (or speaks in a non-Italian language, or asks something the bot cannot handle) is transferred to the operator's configured number from any point in the conversation, including mid-booking-flow.
  2. After every call ends, the business owner receives a summary (transcript, outcome, reservation details if any) via the channel configured for their account — email, SMS/WhatsApp, Telegram, or log.
  3. Forcing a Deepgram STT failure mid-call causes the bot to speak a courtesy phrase and switch to the faster-whisper fallback without interrupting the call.
  4. Forcing a persistent STT or TTS failure (no recovery after retry) causes the bot to speak a courtesy phrase and transfer to the operator, with no dead-air period longer than a few seconds.
  5. A dead-air watchdog detects prolonged silence (no STT input and no TTS output) and triggers the recovery/transfer sequence automatically.

**Plans**: 6 plans (4 original + 2 gap-closure)
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Slice: transfer-from-anywhere — TelephonyProvider seam + stub, global transfer Flows function, auto-triggers (non-IT/uncertainty/FAQ-offer) (HAND-01..04, SC1)

**Wave 2** *(blocked on Wave 1)*

- [x] 03-02-PLAN.md — call_logs schema + CallLogRepository + LLM summary + outcome taxonomy (NOTIF-01/02, D-05/06/08)

**Wave 3** *(blocked on Wave 2)*

- [x] 03-03-PLAN.md — Notification channels (log/telegram/email/sms) + factory + end-of-call dispatch hook + .env.example (NOTIF-03/04/05, SC2)

**Wave 4** *(blocked on Wave 3)*

- [x] 03-04-PLAN.md — Graceful-degradation ladder: STT failover (lazy faster-whisper) + persistent-failure transfer + dead-air watchdog (REL-02/03/04, SC3/4/5)

**Gap Closure** *(from live UAT — run via `/gsd:execute-phase 3 --gaps-only`)*

- [x] 03-05-PLAN.md — GAP SC2: D-11 demo-default multi-send (log + telegram if token present) — MultiNotificationChannel + factory selection (NOTIF-03/04/05)
- [x] 03-06-PLAN.md — GAP SC3/SC4: real-error-path STT failover + escalation — FailoverDeepgramSTTService connection monitor surfaces 401/connection-down as ErrorFrame; whisper error-yield; switch-driven escalation to outcome 'fallito' (REL-02/03)

### Phase 4: Telnyx Telephony

**Goal**: A real inbound call to an Italian geographic number (Telnyx DID) is handled end-to-end by the bot: it greets the caller in Italian, handles barge-in on the 8kHz phone path, routes to the correct tenant by dialed number, completes bookings and FAQs, and transfers to a human operator when needed.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: TEL-01, TEL-02, TEL-03, TEL-04, TEL-05
**Success Criteria** (what must be TRUE):

  1. A real inbound call to a Telnyx DID reaches the bot and receives a personalized greeting for the correct tenant within a few seconds, with no code changes required to add a new DID-to-tenant mapping.
  2. Barge-in works on the live phone path: a caller can interrupt the bot mid-sentence and the bot stops and listens — verified via the Telnyx WebSocket transport.
  3. A caller can complete a full booking or FAQ interaction over a real phone call and the result (calendar event, call log, owner notification) is identical to the local-path behavior.
  4. Requesting a transfer to an operator on a real phone call successfully connects the caller to the configured operator number.
  5. Per-stage latency on the phone path (including the PSTN leg) is instrumented and the end-to-end turn time is within the target for real telephony conditions.

**Plans**: TBD

### Phase 5: Multi-Tenant + Onboarding

**Goal**: A new business client can be added to the system by running the onboarding CLI — no code changes, no redeploy — and the new tenant's calls, bookings, knowledge base, and notifications are fully isolated from every other tenant from the first call.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: TENANT-01, TENANT-02, TENANT-03, TENANT-04, TENANT-05, TENANT-06
**Success Criteria** (what must be TRUE):

  1. Running the onboarding CLI with a new client's config (name, greeting, voice_id, hours, services, booking rules, transfer number, KB folder, notification channel) creates a fully operational new tenant without modifying any source code.
  2. Two simultaneous calls to two different Telnyx DIDs never cross data: each call receives its own greeting, knowledge base answers, calendar writes, and notification channel with no leakage between tenants.
  3. Each tenant's API credentials and secrets are stored in an isolated, encrypted per-tenant store; no credential is readable from another tenant's session context.
  4. The persistence layer (tenants, reservations, call_logs, kb_documents) uses `tenant_id` as a mandatory filter on every read and write, and the schema is structured for a Postgres migration by connection-string change.
  5. A new client can be added, a test call made, and a booking confirmed in that client's Google Calendar — all without touching Python source files.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Local Voice Loop | 3/3 | Complete   | 2026-06-24 |
| 2. Booking + Calendar + FAQ | 4/4 | Complete    | 2026-06-26 |
| 3. Handoff + Summary + Notifications | 6/6 | Complete   | 2026-06-29 |
| 4. Telnyx Telephony | 0/TBD | Not started | - |
| 5. Multi-Tenant + Onboarding | 0/TBD | Not started | - |
