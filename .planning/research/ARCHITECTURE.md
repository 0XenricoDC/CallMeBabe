# Architecture Research

**Domain:** Self-hosted, multi-tenant AI voice telephony receptionist ("Centralino AI") built on Pipecat + Pipecat Flows
**Researched:** 2026-06-23
**Confidence:** HIGH (Pipecat pipeline/transport/Flows verified via Context7 + official docs; multi-tenant config-injection pattern is MEDIUM — synthesized from Pipecat primitives, not a single canonical reference)

## Standard Architecture

The system is **one Pipecat engine** (a single Python process / pipeline definition) where every tenant is a **CONFIG record** loaded at call start. Nothing about a client is hardcoded — the greeting, voice, hours, services, booking rules, transfer number, knowledge base, and notification channel are all data injected into the same pipeline.

The architecture has four concentric layers:

1. **Transport edge** — abstracted I/O. Local audio (M1) or Telnyx WebSocket (M4) behind one interface.
2. **Voice pipeline** — the Pipecat processor chain (STT → context → LLM+tools → TTS).
3. **Conversation orchestration** — Pipecat Flows (booking / FAQ / handoff nodes) + tool/function handlers.
4. **Domain services & data** — config loader, calendar provider, notification channel, RAG/KB, persistence (SQLite-now / Postgres-ready).

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         TRANSPORT EDGE (swappable)                     │
│  ┌────────────────────┐   ┌──────────────────────┐                     │
│  │ LocalAudioTransport│   │ Telnyx WS Transport  │  ← same interface   │
│  │  (M1: mic/cuffie)  │   │ (M4: real calls, 8kHz│    BaseTransport     │
│  └─────────┬──────────┘   │ PCMU, TelnyxSerializer)                     │
│            │              └──────────┬───────────┘                     │
├────────────┴─────────────────────────┴───────────────────────────────┤
│                       VOICE PIPELINE (Pipecat)                         │
│  transport.input → STT → ctx.user → LLM(+tools) → TTS → transport.out  │
│   (audio frame)   (Deepgram)        (Claude)    (ElevenLabs) │  ↑ VAD  │
│                   ↑ faster-whisper fallback        │         │ barge-in│
│                                    └ ctx.assistant ┘         │ (Interr-│
│                                                              │ uptFrame)│
├──────────────────────────────────────────────────────────────────────┤
│                  CONVERSATION ORCHESTRATION (Pipecat Flows)            │
│  FlowManager ── nodes: [greeting] → [booking] → [faq] → [handoff/end]  │
│       │  each node = role/task messages + only-the-tools-it-needs      │
│       └─ function handlers return (result, next_node)                  │
├──────────────────────────────────────────────────────────────────────┤
│                      DOMAIN SERVICES (interfaces)                      │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────┐ ┌────────────┐  │
│  │ConfigLoader│ │CalendarProvider│ │NotificationChannel│ │ KB / RAG  │  │
│  │(per-tenant)│ │(GoogleCalendar)│ │(Email/SMS/WA/TG/log)│(per-tenant)│  │
│  └─────┬──────┘ └──────┬───────┘ └────────┬─────────┘ └─────┬──────┘  │
├────────┴───────────────┴──────────────────┴─────────────────┴─────────┤
│                    PERSISTENCE (SQLite now → Postgres-ready)           │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ tenants  │  │ reservations │  │ call_logs│  │ kb_documents/chunks│  │
│  └──────────┘  └──────────────┘  └──────────┘  └──────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Transport (interface)** | Move raw audio in/out; signal call lifecycle (start/end). Hides whether source is mic or phone. | `LocalAudioTransport` (M1); `FastAPIWebsocketTransport` + `TelnyxFrameSerializer` (M4). Both yield/consume `InputAudioRawFrame` / `TTSAudioRawFrame`. |
| **STT processor** | Audio frames → `TranscriptionFrame`. Streaming + VAD-driven. | Deepgram (IT), with `faster-whisper` self-hosted as drop-in fallback. |
| **Context aggregator** | Maintain conversation history (user + assistant + tool calls/results). | Pipecat `context_aggregator.user()` / `.assistant()`. Stores function calls automatically. |
| **LLM service** | Context → streaming text + tool/function calls. The "brain." | Anthropic Claude with tool calling. |
| **TTS processor** | Text frames → `TTSAudioRawFrame`. | ElevenLabs (IT voice, per-tenant `voice_id`, cloning-ready). |
| **FlowManager (Flows)** | Drive the conversation as a node graph; expose only the tools each node needs; manage `flow_manager.state`. | `pipecat-ai-flows`; nodes for greeting/booking/FAQ/handoff. |
| **ConfigLoader** | At call start, resolve tenant (by called number / device) → load CONFIG record → build initial node, system prompt, voice_id, hours, rules, KB handle, notification channel. | Repository over SQLite/JSON; returns a `TenantConfig` dataclass. |
| **CalendarProvider (interface)** | Check availability/capacity; create reservation event. | `GoogleCalendarProvider` real impl; `InMemoryCalendarProvider` for tests. |
| **NotificationChannel (interface)** | Send end-of-call summary to owner via chosen channel. | Email/SMTP, SMS/WhatsApp, Telegram, log. Selected per-tenant. |
| **KB / RAG** | Per-tenant FAQ retrieval invoked as an LLM tool. | SQLite FTS5 (M3 start) → optional embeddings/vector later. Returns top-k chunks. |
| **Persistence** | Store tenants, reservations, call logs, KB. | SQLAlchemy over SQLite now; same models target Postgres. |

## Recommended Project Structure

```
centralino/
├── app/
│   ├── main.py                  # entrypoint: wires transport + pipeline + flow per call
│   ├── engine/
│   │   ├── pipeline.py          # builds the Pipecat Pipeline from a TenantConfig
│   │   ├── runner.py            # PipelineTask / PipelineRunner lifecycle, fallbacks
│   │   └── fallbacks.py         # courtesy phrases, STT/LLM/TTS failure → transfer
│   ├── transport/
│   │   ├── base.py              # TransportFactory protocol (build(config) -> transport)
│   │   ├── local.py             # LocalAudioTransport factory (M1)
│   │   └── telnyx.py            # Telnyx WS + serializer factory (M4)
│   ├── flows/
│   │   ├── nodes.py             # build_greeting / build_booking / build_faq / build_handoff / build_end
│   │   ├── functions.py         # FlowsFunctionSchema + handlers (collect_*, check_availability, book, faq_lookup, transfer)
│   │   └── prompts.py           # role/task message templates (filled from config)
│   ├── config/
│   │   ├── models.py            # TenantConfig dataclass
│   │   ├── loader.py            # resolve tenant + load config at call start
│   │   └── onboarding.py        # CLI / mini-panel to add a tenant (no code change)
│   ├── calendar/
│   │   ├── base.py              # CalendarProvider protocol
│   │   ├── google.py            # GoogleCalendarProvider
│   │   └── memory.py            # test/dev impl
│   ├── notifications/
│   │   ├── base.py              # NotificationChannel protocol
│   │   ├── email.py  sms.py  whatsapp.py  telegram.py  log.py
│   │   └── factory.py           # channel-by-name selector
│   ├── kb/
│   │   ├── base.py              # KnowledgeBase protocol (search(tenant, query) -> chunks)
│   │   ├── fts.py               # SQLite FTS5 impl
│   │   └── ingest.py            # load per-tenant KB docs → chunks
│   ├── persistence/
│   │   ├── db.py                # engine/session (SQLite URL now, Postgres-ready)
│   │   ├── models.py            # SQLAlchemy: Tenant, Reservation, CallLog, KbDocument, KbChunk
│   │   └── repositories.py      # data access; no raw SQL in business code
│   └── observability/
│       └── logging.py           # latency tracing, turn metrics
├── data/
│   ├── tenants/<slug>/kb/       # per-tenant knowledge base sources
│   └── centralino.db            # SQLite (gitignored)
├── tests/
├── .env.example                 # all keys placeholdered (Deepgram, ElevenLabs, Anthropic, later Telnyx)
└── pyproject.toml
```

### Structure Rationale

- **`engine/` vs `flows/`:** `engine/` owns the *mechanical* pipeline (frames, processors, lifecycle); `flows/` owns the *conversational* logic (nodes, tools). Keeping them apart means you can change the booking script without touching pipeline wiring.
- **`transport/base.py` first:** the swappability requirement (local→Telnyx→Twilio) is honored by defining the factory protocol before any concrete impl, so M1 builds against the interface and M4 just adds a file.
- **`calendar/`, `notifications/`, `kb/` each have `base.py`:** every external integration sits behind a Protocol so the LLM tool handlers depend on interfaces, not vendors.
- **`config/` is central, not scattered:** the entire multi-tenant promise lives here. A new client = one row + one KB folder, no edits elsewhere.
- **`persistence/repositories.py`:** business code never writes SQL; swapping SQLite→Postgres is a connection-string + migration change, not a rewrite.

## Architectural Patterns

### Pattern 1: Config-Injected Single Engine (multi-tenant by configuration)

**What:** One pipeline definition. At call start, `ConfigLoader` resolves the tenant (by dialed number in M4, by a `--tenant` flag in M1) and returns a `TenantConfig`. `engine/pipeline.py` consumes that config to set the TTS `voice_id`, the system/role prompt (name, greeting, hours, services, booking rules), the transfer number, the KB handle, and the notification channel. The *code* is identical for every tenant.

**When to use:** Always, here. It is the core architectural constraint.

**Trade-offs:** (+) Onboarding is data-only; zero deploy per client. (+) One code path to test/harden. (−) Config schema must be disciplined — a missing field must fail loudly with a safe default, never crash mid-call.

**Example:**
```python
def build_pipeline(cfg: TenantConfig, transport) -> Pipeline:
    stt = DeepgramSTTService(language="it", api_key=...)
    llm = AnthropicLLMService(model=..., system=render_system_prompt(cfg))
    tts = ElevenLabsTTSService(voice_id=cfg.voice_id, language="it")
    ctx = LLMContext(messages=[], tools=tool_schemas_for(cfg))
    agg = LLMContextAggregatorPair(ctx)
    return Pipeline([
        transport.input(), stt, agg.user(),
        llm, tts, transport.output(), agg.assistant(),
    ])
```

### Pattern 2: Transport Factory behind a Protocol (telephony abstraction)

**What:** A `TransportFactory` protocol with `build(cfg) -> BaseTransport`. M1 ships `LocalAudioTransport`; M4 adds Telnyx (`FastAPIWebsocketTransport` + `TelnyxFrameSerializer`, 8kHz PCMU). Both produce/consume the same Pipecat audio frames, so the pipeline downstream is unchanged. Swapping to Twilio later = one more factory file.

**When to use:** Any I/O edge that must change between milestones/vendors.

**Trade-offs:** (+) Pipeline and Flows never import a vendor SDK. (+) M1 is fully testable with no telephony account. (−) Telephony adds real concerns (codec/sample-rate 8kHz, call-control IDs, DTMF, transfer mechanics) the local transport doesn't exercise — keep an integration test seam.

**Example:**
```python
class TransportFactory(Protocol):
    def build(self, cfg: TenantConfig, *, websocket=None) -> BaseTransport: ...

# local.py  -> LocalAudioTransport(...)
# telnyx.py -> FastAPIWebsocketTransport(websocket, params=...serializer=TelnyxFrameSerializer(...))
```

### Pattern 3: Flows-as-State-Machine with Per-Node Tools

**What:** Pipecat Flows models the conversation as a graph of nodes. Each node carries `role_message` (persona, set once) + `task_messages` (the one job for this node) + only the `functions` that node needs. Function handlers do the work (DB write, calendar call, KB lookup) and return `(result, next_node)`. This avoids one monolithic prompt with all tools (which causes hallucination / wrong tool calls).

**Nodes for this domain:**
- `greeting` — speak personalized greeting, classify intent → branch to booking / faq / handoff.
- `booking` — collect date, time, party-size/service, name, phone; tool `check_availability` then `create_reservation`; on success → `end`/summary.
- `faq` — tool `faq_lookup(query)` hits per-tenant KB (RAG); answer; loop or branch.
- `handoff` — tool `transfer_call(number)` on explicit request, low confidence, or non-Italian caller.
- `end` — emit summary, trigger notification, close.

**When to use:** Any deterministic, multi-step task (booking, intake). Free-form chat would be the wrong tool.

**Trade-offs:** (+) Focused prompts = fewer wrong tool calls, higher reliability. (+) State (`flow_manager.state`) carries collected slots across nodes. (−) More upfront design than a single prompt; (−) intent branching from `greeting` needs care to avoid dead-ends — always provide a handoff escape.

**Example:**
```python
async def check_and_book(args: FlowArgs, fm: FlowManager) -> tuple[dict, NodeConfig]:
    slot = fm.state["slot"]
    if not await calendar.is_available(fm.state["tenant"], slot):
        return {"available": False}, build_booking_node()      # re-ask
    res = await calendar.create(fm.state["tenant"], slot, fm.state["customer"])
    fm.state["reservation"] = res
    return {"available": True, "id": res.id}, build_end_node()
```

### Pattern 4: RAG as a Tool, not in the hot path

**What:** FAQ retrieval is exposed as an LLM function (`faq_lookup`) the model calls *only when it needs facts*, rather than retrieving on every turn. Start with **SQLite FTS5 keyword search** over per-tenant chunks (no embedding latency, no extra infra) — adequate for small business FAQ (hours, address, services, prices). Upgrade to embeddings/vector only if keyword recall proves insufficient.

**When to use:** Per-tenant factual Q&A with a small, mostly-static KB.

**Trade-offs:** (+) FTS5 adds ~negligible latency and ships inside SQLite — critical for the <800ms budget. (+) Per-tenant isolation is a `WHERE tenant_id = ?`. (−) Keyword search misses paraphrase; mitigate by storing question/answer pairs and letting the LLM rephrase the query. (−) If you later add embeddings, pre-fetch/cache to avoid 50–300ms vector lookups blowing the latency budget.

## Data Flow

### Per-Turn Audio Flow (downstream primary, upstream for interruptions)

```
Caller speaks
    ↓ (InputAudioRawFrame)
transport.input → STT(Deepgram) → context.user → LLM(Claude, +tools) → TTS(ElevenLabs) → transport.output
                                                       │
                                          (may emit ToolCallFrame → handler:
                                           check_availability / create_reservation /
                                           faq_lookup / transfer_call) → result back into context
                                                       ↓
                                          context.assistant (records reply + tool results)

Barge-in: caller starts speaking while bot talks
    → VAD detects → InterruptionFrame propagates UPSTREAM → pending TTS/LLM frames discarded → new turn begins
```

### Call Lifecycle / Config Flow

```
Inbound call (Telnyx) OR `python main.py --tenant=trattoria` (local)
    ↓
resolve tenant (dialed number → tenant_id | CLI flag)
    ↓
ConfigLoader.load(tenant_id) → TenantConfig {name, greeting, voice_id, hours, services,
                                             booking_rules, transfer_number, kb_handle, notify_channel}
    ↓
build_pipeline(cfg, transport)  +  FlowManager(initial=build_greeting(cfg))
    ↓
conversation runs (nodes + tools)
    ↓
on end: assemble summary (transcript + outcome + reservation?)
    → persist CallLog
    → NotificationChannel.send(owner, summary)   # channel from cfg
```

### Key Data Flows

1. **Booking write:** booking node → `check_availability` (CalendarProvider, capacity vs booking_rules) → `create_reservation` (Google Calendar event + `reservations` row) → summary → notification.
2. **FAQ retrieval:** faq node → `faq_lookup(query)` → KB.search(tenant_id, query) [FTS5] → top-k chunks into context → grounded answer.
3. **Handoff:** any node → `transfer_call(cfg.transfer_number)` on request / low confidence / non-Italian → telephony transport executes transfer.
4. **Fallback:** STT/LLM/TTS error → `fallbacks.py` speaks courtesy phrase → retry once → if still failing, transfer to human.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 tenant / few concurrent calls (M1–M5) | Single process, SQLite, FTS5 KB. Fine. One worker per call. |
| Several tenants / tens of concurrent calls | Move to Postgres (already abstracted via repositories), run multiple pipeline workers behind the Telnyx WS endpoint, connection-pool the DB. |
| Many tenants / high concurrency | Horizontal: stateless workers (config loaded per call), Postgres + read replicas, shared cache for hot TenantConfig + KB chunks, per-tenant rate limits on vendor APIs. |

### Scaling Priorities

1. **First bottleneck — latency budget (<800ms), not throughput.** Concurrency is cheap (each call is its own async worker); the risk is per-turn latency from serial STT→LLM→TTS + any RAG/calendar call. Fix: keep RAG as FTS5 (in-process), stream LLM→TTS, cache TenantConfig at call start, avoid synchronous calendar calls on the speaking path (confirm, then write).
2. **Second bottleneck — SQLite write contention** once multiple concurrent calls write reservations/logs. Fix: migrate to Postgres (already structured for it).

## Anti-Patterns

### Anti-Pattern 1: Per-client code branches / forks

**What people do:** `if tenant == "trattoria_x": greeting = ...` or a separate pipeline file per client.
**Why it's wrong:** Violates the core constraint; onboarding becomes a deploy; testing surface explodes.
**Do this instead:** Everything client-specific is a field in `TenantConfig` loaded from DB. New client = new row + KB folder.

### Anti-Pattern 2: Vendor SDKs imported in business/flow logic

**What people do:** Call `telnyx`, `google.oauth`, or `elevenlabs` directly inside flow handlers.
**Why it's wrong:** Locks business logic to a vendor; breaks the swap-to-Twilio / swap-channel requirement; un-testable without live accounts.
**Do this instead:** Depend on `TransportFactory`, `CalendarProvider`, `NotificationChannel`, `KnowledgeBase` protocols. Concrete impls live behind `base.py`.

### Anti-Pattern 3: One giant LLM prompt with every tool

**What people do:** Single system prompt listing book/cancel/faq/transfer tools and all rules.
**Why it's wrong:** Causes wrong-tool calls and hallucinated slots — exactly what Pipecat Flows exists to prevent.
**Do this instead:** Flows nodes, each exposing only the tools it needs, with focused task messages.

### Anti-Pattern 4: Synchronous RAG/vector lookup on every turn

**What people do:** Query an embedding store before every LLM call.
**Why it's wrong:** 50–300ms per lookup blows the <800ms budget for non-FAQ turns.
**Do this instead:** RAG as an on-demand tool (LLM decides when), FTS5 in-process to start; embeddings only if recall demands it, with caching/pre-fetch.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Deepgram (STT) | Pipecat `DeepgramSTTService`, streaming, `language="it"` | `faster-whisper` self-hosted fallback behind same processor slot. |
| Anthropic Claude (LLM) | Pipecat LLM service with tool calling; tools = Flows function schemas | Context aggregator stores tool calls/results automatically. |
| ElevenLabs (TTS) | Pipecat `ElevenLabsTTSService`, per-tenant `voice_id`, IT | Cloning-ready; voice_id is config, not code. |
| Telnyx (telephony, M4) | `FastAPIWebsocketTransport` + `TelnyxFrameSerializer`, 8kHz mono PCMU, `call_control_id`/`stream_id` | Behind `TransportFactory`. Twilio = sibling serializer/transport later. |
| Google Calendar | `GoogleCalendarProvider` impl of `CalendarProvider` (OAuth) | Real from the booking milestone; availability + event create. |
| Email/SMS/WhatsApp/Telegram | `NotificationChannel` impls, selected per-tenant by name | `log` channel as zero-dependency default/fallback. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Transport ↔ Pipeline | Pipecat frames (`InputAudioRawFrame`/`TTSAudioRawFrame`) | Pipeline never knows the transport vendor. |
| Pipeline ↔ Flows | LLM tool calls ↔ function handlers; `flow_manager.state` for slots | Handlers return `(result, next_node)`. |
| Flows ↔ Domain services | Direct calls to Protocol interfaces (calendar/KB/notify) | No vendor imports in handlers. |
| Services ↔ Persistence | Repository methods (no raw SQL upstream) | SQLite→Postgres = connection + migration only. |
| ConfigLoader ↔ everything | Provides `TenantConfig` at call start | Single source of per-tenant truth. |

## Build Order (aligned to the 5 milestones)

The dependency graph is **inside-out**: interfaces + pipeline first, then progressively richer nodes and real integrations. Each milestone is independently demoable (project's "stop and let me test it" gate).

```
M1 ─ Core voice loop (LOCAL)        → M2 ─ Structured booking + Calendar
   transport/base.py + local.py        flows/nodes(booking) + functions
   engine/pipeline.py (STT→LLM→TTS)     calendar/base.py + google.py
   config/models + loader (1 tenant)    persistence: reservations
   .env.example, fallbacks, barge-in    booking_rules + capacity check
        │                                      │
        ▼                                      ▼
M3 ─ FAQ via RAG + Notifications     M4 ─ Real telephony (Telnyx)
   kb/base.py + fts.py (FTS5)           transport/telnyx.py (same interface)
   flows/nodes(faq, handoff)            handoff/transfer_call real
   notifications/base + channels        8kHz/PCMU, call lifecycle
   call_logs + end-of-call summary      end-to-end real inbound call
        │                                      │
        └──────────────┬───────────────────────┘
                       ▼
        M5 ─ Multi-tenant hardening
           config/onboarding.py (CLI/mini-panel)
           per-tenant KB folders, notification channel per tenant
           Postgres-ready review, fallback/latency tuning
```

**Why this order (dependencies):**
- **M1 must define `transport/base.py` and `config/loader` even with one tenant**, because M4 (Telnyx) and M5 (onboarding) only *add* impls behind those seams — they don't rewrite. Defining the interfaces in M1 is what makes "config not code" real.
- **Booking (M2) before FAQ (M3):** booking is the core value and exercises Flows + an external interface (Calendar) end-to-end, validating the tool-handler pattern before adding RAG.
- **FAQ/notifications (M3) before telephony (M4):** all conversational logic and summaries should be proven on the cheap local transport before introducing real-call complexity (codecs, transfer, call IDs).
- **Telnyx (M4) is a pure transport swap** by design — if M1's abstraction is right, M4 adds `telnyx.py` and wires the WS endpoint, nothing downstream changes.
- **Multi-tenant onboarding (M5) last:** the schema and config-injection exist from M1; M5 makes adding tenants a UX/CLI task and hardens fallbacks/latency across the board.

## Sources

- Pipecat pipeline & processors (Context7 `/websites/pipecat_ai`): https://docs.pipecat.ai/pipecat/learn/pipeline , https://docs.pipecat.ai/pipecat/learn/overview — HIGH
- Function calling / context aggregation: https://docs.pipecat.ai/pipecat/learn/function-calling , https://docs.pipecat.ai/pipecat/learn/context-management — HIGH
- Interruptions / barge-in (`InterruptionFrame`, speech-input): https://docs.pipecat.ai/pipecat/learn/speech-input , https://docs.pipecat.ai/api-reference/server/frames/system-frames — HIGH
- Telnyx transport & serializer (8kHz PCMU): https://docs.pipecat.ai/api-reference/server/services/serializers/telnyx — HIGH
- Pipecat Flows (nodes, FlowManager, FlowsFunctionSchema, `(result, next_node)` handlers, restaurant_reservation example): https://docs.pipecat.ai/pipecat-flows/guides/quickstart , https://github.com/pipecat-ai/pipecat-flows — HIGH
- Flows rationale (avoid monolithic prompts): https://www.daily.co/blog/beyond-the-context-window-why-your-voice-agent-needs-structure-with-pipecat-flows/ — MEDIUM
- RAG latency budget for voice agents: https://arxiv.org/html/2603.02206v1 , https://blog.codeminer42.com/technical-challenges-in-building-voice-agents/ — MEDIUM
- Multi-tenant config-injection pattern: synthesized from Pipecat primitives (per-call config build) — MEDIUM (no single canonical source)

---
*Architecture research for: self-hosted multi-tenant Pipecat voice receptionist*
*Researched: 2026-06-23*
