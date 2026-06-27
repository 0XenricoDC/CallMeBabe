# Phase 3: Handoff + Summary + Notifications — Research

**Researched:** 2026-06-27
**Domain:** Pipecat 1.4.0 provider-failover, Flows 1.3.0 global functions, async notifications, end-of-call logging
**Confidence:** HIGH (core Pipecat mechanisms verified via official API reference and source); MEDIUM (faster-whisper lazy-load latency on CPU — no Windows-specific benchmark found); MEDIUM (notification channels — aiosmtplib + python-telegram-bot confirmed on PyPI, patterns from official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Transfer stub behind `TelephonyProvider.transfer(number)` seam. Local path: courtesy phrase + log intent + clean shutdown; esito `trasferito`. Fase 4 replaces stub.
- **D-02:** Transfer is a **global function** in Pipecat Flows (HAND-04) — invocable from any node (greeting/booking/faq), including mid-flow.
- **D-03:** Trigger automatici — non-italiano → transfer; incertezza/fuori-ambito → transfer; FAQ-non-trovata → offre transfer.
- **D-04:** `transfer()` carries warm-ready context payload (chi chiama, cosa voleva, stato flow). Local path: assembled and logged. Fase 4 uses for real warm transfer.
- **D-05:** Summary = 2-3 frasi LLM in italiano + structured block (esito, prenotazione, Calendar ID). Full transcript in `call_log` DB, NOT pasted into notification body.
- **D-06:** Outcome taxonomy: `prenotato` / `faq` / `trasferito` / `abbandonato` / `fallito`. Derived from flow final state + DB records.
- **D-07:** Summary ALWAYS sent at call end regardless of outcome — owner sees every call.
- **D-08:** New table `call_logs` required (absent from current schema). Structured for Postgres migration.
- **D-09:** All four channels behind `NotificationChannel` interface (`async send(subject, body)`). Channel chosen per-tenant from config.
- **D-10:** Depth — `log` REAL (default/fallback); `telegram` REAL (testable now); `email` SMTP code written; `sms`/`whatsapp` code written (tested in Fase 4+). `.env.example` updated.
- **D-11:** Demo tenant default = `log` (+ `telegram` if token in `.env`).
- **D-12:** Faster-whisper STT fallback: **lazy-load** (NOT loaded at startup). First Deepgram failure triggers switch. Trade-off: first-switch latency, mitigated with smaller model.
- **D-13:** Escalation: faster-whisper also fails → courtesy phrase + transfer. Esito `fallito`.
- **D-14:** Dead-air watchdog: T1 → re-prompt ("È ancora in linea?"); T2 → recovery/transfer. T1/T2 exact values = Claude's Discretion.

### Claude's Discretion
- Wording of courtesy phrases (STT switch, re-prompt, handoff, FAQ-not-found offer)
- Numeric thresholds T1/T2 (D-14 watchdog); retry/timeout count before "persistent failure" (D-12/D-13)
- Exact `call_logs` schema (column names, transcript format TEXT vs turns table)
- Precise mid-call STT switch mechanism in Pipecat 1.4.0
- Summary LLM model (Haiku vs Sonnet), prompt, length
- Non-Italian detection mechanism (STT confidence / LLM judgement)
- Concrete SMS/WhatsApp provider (Telnyx Messaging / Twilio / Meta)

### Deferred Ideas (OUT OF SCOPE)
- Real Telnyx transfer mechanics (SIP REFER / Dial+Bridge, 8kHz) → Fase 4
- SMS/WhatsApp real testing (requires account/number) → Fase 4+
- Multi-tenant credential isolation → Fase 5
- Real warm transfer with operator briefing → Fase 4
- Fine-tuning fallback thresholds on real phone path → Fase 4
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HAND-01 | Bot transfers to operator on caller request | Global transfer tool + TelephonyProvider stub (D-01/D-02) |
| HAND-02 | Bot transfers when uncertain / out-of-scope | System prompt instruction + global tool availability |
| HAND-03 | Non-Italian caller → immediate transfer | LLM recognizes non-Italian in greeting node, calls transfer tool |
| HAND-04 | Transfer available from any flow point | `FlowManager(global_functions=[...])` — verified Flows 1.3.0 |
| NOTIF-01 | Call log written at end (transcript, outcome, reservation) | `call_logs` table + `CallLogRepository` after `runner.run()` |
| NOTIF-02 | Textual summary generated (transcript + outcome + reservation) | LLM call (Haiku) after pipeline ends, before notification |
| NOTIF-03 | Summary sent via `NotificationChannel` abstraction | `NotificationChannel.send()` called with outcome-prefixed subject |
| NOTIF-04 | Email/SMS/WhatsApp/Telegram + log implemented | Four concrete channel classes behind existing interface |
| NOTIF-05 | Notification channel chosen per-tenant from config | `tenant.notification_channel` field already in `TenantConfig` |
| REL-02 | Persistent provider failure → transfer to operator | `ErrorFallbackObserver` extended: after escalation threshold, transfer |
| REL-03 | Faster-whisper STT fallback active | `ServiceSwitcher([deepgram, lazy_whisper], ServiceSwitcherStrategyFailover)` |
| REL-04 | Dead-air watchdog triggers recovery/transfer | `LLMUserAggregatorParams(user_idle_timeout=T1)` + `on_user_turn_idle` |
</phase_requirements>

---

## Summary

Phase 3 adds three orthogonal capabilities on top of the Phase 2 local pipeline: (1) a global operator-transfer function invocable from any Flows node, (2) an end-of-call summary + multi-channel notification system, and (3) a full provider-failure degradation chain (courtesy → STT fallback → transfer) plus a dead-air watchdog.

All three capabilities are supported directly by Pipecat 1.4.0 and Flows 1.3.0 APIs, verified via official API reference and source inspection. The main implementation decisions are:

- **STT failover**: `ServiceSwitcher([deepgram_stt, lazy_whisper_stt], ServiceSwitcherStrategyFailover)` replaces the standalone `stt` slot in the pipeline. A custom `LazyWhisperSTTService` subclass defers model load to first use, honoring D-12.
- **Dead-air watchdog**: Pipecat's built-in `LLMUserAggregatorParams(user_idle_timeout=)` on `aggregators.user()` + `on_user_turn_idle` event, with an `IdleHandler` escalation pattern (re-prompt → transfer).
- **Global transfer**: `FlowManager(global_functions=[transfer_schema])` — confirmed by FlowManager source in 1.3.0.
- **End-of-call hook**: code immediately after `await runner.run()` in `bot()`, wrapped in `try/finally` to guarantee execution regardless of outcome.
- **Notification channels**: `log` (zero-dep, default), `telegram` (direct HTTP via aiohttp already in pipecat), `email` (aiosmtplib 5.1.2), `sms`/`whatsapp` (stub behind interface, Telnyx or Twilio).

**Primary recommendation:** Build in this wave order: (W1) global transfer tool + stub + `call_logs` schema; (W2) dead-air watchdog + STT failover chain + extended `ErrorFallbackObserver`; (W3) end-of-call summary generation + notification channels.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Global transfer tool (HAND-04) | Conversation Orchestration (Flows) | Domain / TelephonyProvider interface | Transfer logic lives in a `FlowsFunctionSchema` handler; TelephonyProvider stub is the domain seam |
| Non-Italian detection (HAND-03) | LLM / Flows — greeting node | STT (transcript language) | LLM judges the transcript and calls the global transfer tool |
| Dead-air watchdog (REL-04) | Pipeline / Aggregator | Bot.py event handler | `LLMUserAggregatorParams.user_idle_timeout` is a pipeline-layer mechanism |
| STT failover (REL-03) | Pipeline (ServiceSwitcher) | ErrorFallbackObserver / Domain | Frame routing is pipeline-level; courtesy phrase via observer |
| Persistent-failure escalation (REL-02) | Pipeline observer (ErrorFallbackObserver) | TelephonyProvider stub | Escalation counter lives in the observer |
| End-of-call summary / log (NOTIF-01/02) | Domain (CallLogRepository + LLM call) | Bot.py post-runner hook | Runs after `runner.run()` returns — not pipeline-level |
| Notification dispatch (NOTIF-03/04/05) | Domain (NotificationChannel impls) | Config (per-tenant channel selection) | Concrete channels behind existing interface |

---

## Standard Stack

### Core (all already installed; no new pip installs for pipeline changes)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pipecat-ai` | 1.4.0 | `ServiceSwitcher`, `ServiceSwitcherStrategyFailover`, `LLMUserAggregatorParams.user_idle_timeout`, `TTSSpeakFrame`, `EndWorkerFrame`, `UserIdleTimeoutUpdateFrame` | Owner-fixed. Verified PyPI 1.4.0 ships all required classes. |
| `pipecat-ai-flows` | 1.3.0 | `FlowManager(global_functions=[...])` for cross-node transfer tool | Owner-fixed. `global_functions` confirmed in FlowManager API reference for 1.3.0. |
| `pipecat-ai[whisper]` | faster-whisper ~=1.2.1 | `WhisperSTTService` (or custom `LazyWhisperSTTService`) for Italian STT fallback | Owner-fixed. Already declared in extras. |

### Supporting (new package installs for notification channels)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `aiosmtplib` | 5.1.2 | Async SMTP email notifications | `email` channel. Drop-in `await aiosmtplib.send(msg, ...)`. |
| `python-telegram-bot` | 22.8 | Telegram Bot API (async, Python >=3.10) | `telegram` channel. Or use direct `aiohttp` HTTP if already imported. |
| `aiohttp` | already in pipecat | Direct HTTP to Telegram Bot API without extra dep | Telegram channel alternative (simpler, no new install). |

**Note on Telegram:** `aiohttp` is already a transitive dependency of `pipecat-ai`. A 10-line `aiohttp.ClientSession().post(BOT_API_URL, ...)` covers the end-of-call notification use case without installing `python-telegram-bot`. Recommend this for Phase 3 to minimize dependencies; `python-telegram-bot` is better for webhook/polling bots (Phase 5 admin panel if ever needed).

**Version verification (PyPI, 2026-06-27):**
```
pip index versions aiosmtplib       → 5.1.2 (latest)
pip index versions python-telegram-bot → 22.8 (latest)
pip index versions pipecat-ai       → 1.4.0 (latest)
pip index versions pipecat-ai-flows → 1.3.0 (latest)
```
[VERIFIED: PyPI registry — all four packages confirmed at listed versions]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `aiosmtplib` | `smtplib` (stdlib sync) | `smtplib` blocks the event loop — never in async bot code |
| Direct `aiohttp` Telegram | `python-telegram-bot` | PTB adds polling/webhook infra; overkill for one `sendMessage` at call end |
| `ServiceSwitcherStrategyFailover` | Manual `ManuallySwitchServiceFrame` from observer | Failover is automatic on ErrorFrame — less code; manual gives more control but requires plumbing |
| `user_idle_timeout` in aggregator | Custom `asyncio.Task` watchdog | Built-in is simpler and battle-tested; custom task is needed only if you want to detect "no TTS output" specifically (see Watchdog section) |

**Installation (new dependencies only):**
```bash
pip install "aiosmtplib>=5.1.2"
# python-telegram-bot OPTIONAL — skip if using direct aiohttp for Telegram
pip install "python-telegram-bot>=22.8"
```

---

## Package Legitimacy Audit

> slopcheck was installed but blocked from execution by sandbox rules. Manual verification performed via PyPI registry age, download counts, and official GitHub repositories.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `aiosmtplib` | PyPI | 10 yrs (first 2016) | 130M+ total, ~18M/month | github.com/cole/aiosmtplib | [OK by age/downloads] | Approved |
| `python-telegram-bot` | PyPI | 10+ yrs | Very high (10+ yr project) | github.com/python-telegram-bot/python-telegram-bot | [OK by age/source] | Approved (optional) |
| `ServiceSwitcher` (pipecat-ai) | ships in pipecat-ai 1.4.0 | — | — | — | N/A (already installed) | Approved |
| `WhisperSTTService` (pipecat-ai[whisper]) | extra in pipecat-ai 1.4.0 | — | — | — | N/A (already declared) | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none

**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable at CLI level (sandbox restriction); manual verification used instead. Both new packages have 10+ year histories, official GitHub repos, and high download counts — low risk.*

---

## Architecture Patterns

### System Architecture Diagram

```
Caller (mic/WebRTC)
        |
        v InputAudioRawFrame
transport.input()
        |
        v
ServiceSwitcher([deepgram_stt, lazy_whisper_stt],
                strategy=ServiceSwitcherStrategyFailover)
     +-[Deepgram] <--(active)
     +-[LazyWhisper] <--(standby; model loaded on first activation)
        | on ErrorFrame from Deepgram → auto-switches → queues courtesy TTSSpeakFrame
        |
        v TranscriptionFrame
aggregators.user()  <── user_idle_timeout=T1 → fires on_user_turn_idle
        | on_user_turn_idle(1) → re-prompt TTSSpeakFrame
        | on_user_turn_idle(2) → transfer + EndWorkerFrame
        |
        v LLMMessagesFrame
llm (AnthropicLLMService)
        | tool calls: transfer_call (global), collect_booking, confirm_booking, faq_lookup, ...
        |
        v LLMTextFrame
tts (ElevenLabsTTSService)
        |
        v TTSAudioRawFrame
transport.output()
        |
aggregators.assistant()

ErrorFallbackObserver (PipelineWorker observer):
  ErrorFrame → retry slot → (persistent) courtesy phrase
  persistent count >= threshold → enqueue transfer + log outcome='fallito'

--- after runner.run() returns ---
_determine_outcome(flow_manager.state) → outcome string
_assemble_transcript(context.messages)  → list[dict]
_generate_summary(llm_service, transcript, outcome) → 2-3 frasi IT
CallLogRepository.write(tenant_id, outcome, transcript_json, summary)
notification_channel = NotificationChannelFactory.create(tenant.notification_channel)
await notification_channel.send(subject, body)
```

### Recommended Project Structure (Phase 3 additions)

```
src/
├── pipeline/
│   ├── build.py           # extend: add user_idle_timeout to LLMUserAggregatorParams
│   ├── fallback.py        # extend: ErrorFallbackObserver escalation + transfer threshold
│   └── stt_switcher.py    # NEW: LazyWhisperSTTService + build_stt_switcher()
├── flows/
│   ├── nodes.py           # extend: build_transfer_schema, add global_functions hint
│   └── functions.py       # extend: build_transfer_schema + handle_transfer_call
├── telephony/
│   ├── base.py            # NEW: TelephonyProvider protocol (transfer(number) → None)
│   └── stub.py            # NEW: LocalTransferStub (log + close)
├── notifications/
│   ├── base.py            # existing NotificationChannel ABC (rename/move from interfaces/)
│   ├── log_channel.py     # NEW: LogNotificationChannel (writes to call_log)
│   ├── telegram_channel.py # NEW: TelegramNotificationChannel (aiohttp direct)
│   ├── email_channel.py   # NEW: EmailNotificationChannel (aiosmtplib)
│   ├── sms_channel.py     # NEW: SMSNotificationChannel (stub / Telnyx Messaging)
│   └── factory.py         # NEW: create_channel(name, tenant_config) → NotificationChannel
├── call_log/
│   ├── repository.py      # NEW: CallLogRepository (aiosqlite, parameterized SQL)
│   └── summary.py         # NEW: generate_summary(llm, transcript, outcome) → str
├── db/
│   └── schema.sql         # extend: ADD TABLE call_logs
└── bot.py                 # extend: global_functions, watchdog hook, post-runner summary
```

### Pattern 1: ServiceSwitcher for STT Failover (REL-03)

**What:** Replace the single `stt` processor in the pipeline with a `ServiceSwitcher` wrapping Deepgram (primary) and `LazyWhisperSTTService` (backup). The failover strategy automatically switches on non-fatal `ErrorFrame` from the active service.

**When to use:** Whenever two services of the same type need automatic failover on error.

**Import:**
```python
# Source: https://docs.pipecat.ai/api-reference/server/utilities/service-switchers/service-switcher
from pipecat.pipeline.service_switcher import (
    ServiceSwitcher,
    ServiceSwitcherStrategyFailover,
)
from pipecat.frames.frames import ManuallySwitchServiceFrame
```

**Example — build_stt_switcher():**
```python
# Source: reference-server.pipecat.ai/en/latest/_modules/pipecat/pipeline/service_switcher.html
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transcriptions.language import Language

def build_stt_switcher(worker_ref_holder):
    deepgram_stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramSTTService.Settings(
            model="nova-2",          # CLAUDE.md: nova-2 for Italian
            language=Language.IT,
            smart_format=True,
        ),
    )
    # LazyWhisperSTTService: defers WhisperModel() until first transcription (D-12)
    whisper_stt = LazyWhisperSTTService(
        device="cpu",
        compute_type="int8",        # D-12: int8 to reduce RAM + first-load time
        settings=LazyWhisperSTTService.Settings(
            model=Model.LARGE_V3_TURBO,  # CLAUDE.md: LARGE or LARGE_V3_TURBO for IT
            language=Language.IT,
        ),
    )
    stt_switcher = ServiceSwitcher(
        services=[deepgram_stt, whisper_stt],
        strategy_type=ServiceSwitcherStrategyFailover,
    )

    @stt_switcher.strategy.event_handler("on_service_switched")
    async def _on_stt_switched(strategy, service):
        # Queue courtesy phrase through the worker (which must be set after worker creation)
        if worker_ref_holder.worker is not None:
            await worker_ref_holder.worker.queue_frames([
                TTSSpeakFrame(
                    text="Un momento, sto risolvendo un problema tecnico...",
                    append_to_context=False,
                )
            ])

    return stt_switcher
```

**Pipeline placement:**
```python
# In build_pipeline(), replace standalone `stt` with the switcher
pipeline = Pipeline([
    transport.input(),
    stt_switcher,           # replaces `stt`
    aggregators.user(),
    llm,
    tts,
    transport.output(),
    aggregators.assistant(),
])
```

**CRITICAL — LazyWhisperSTTService implementation:**
```python
# Source: reference-server.pipecat.ai/en/stable/_modules/pipecat/services/whisper/stt.html
# Standard WhisperSTTService calls self._load() (→ WhisperModel()) in __init__ — EAGER.
# LazyWhisperSTTService overrides _load() to no-op, defers to first transcription.
from pipecat.services.whisper.stt import WhisperSTTService, Model
import asyncio

class LazyWhisperSTTService(WhisperSTTService):
    """Defers faster-whisper model download/load until first transcription (D-12)."""

    def _load(self) -> None:
        """No-op: model will be loaded on first _run_stt call."""
        pass

    async def _run_stt(self, audio: bytes):
        if self._model is None:
            # Load model in thread pool so event loop stays responsive
            # First call incurs 5–15s delay on CPU (LARGE_V3_TURBO ~1.5GB)
            self._model = await asyncio.to_thread(
                __import__("faster_whisper", fromlist=["WhisperModel"]).WhisperModel,
                self._settings.model,
                device=self._device,
                compute_type=self._compute_type,
            )
        # Delegate to parent transcription logic
        async for frame in super()._run_stt(audio):
            yield frame
```

**Why `_run_stt` may need further adjustment:** the parent `WhisperSTTService._run_stt()` calls `self._model.transcribe(...)` directly. If the parent's method signature differs in 1.4.0, adjust the delegation call to match. Verify at implementation time by reading `src/pipecat/services/whisper/stt.py` in the installed venv.

### Pattern 2: Global Transfer Tool (HAND-04)

**What:** A `FlowsFunctionSchema` passed to `FlowManager(global_functions=[...])` that is automatically appended to every node's functions list, making transfer invocable from any point in the flow.

**Verified mechanism (FlowManager 1.3.0 source):**
```python
# From _set_node() in pipecat_flows/manager.py:
# functions_list = self._global_functions + node_config.get("functions", [])
```
Global functions are PREPENDED to node-specific ones, so they take priority in the LLM's function list.

**`global_functions` was introduced in Flows 0.0.22** (Nov 2024) and is present in 1.3.0. [VERIFIED: FlowManager API reference + source]

**Example — build_transfer_schema() + handler:**
```python
# Source: reference-flows.pipecat.ai/en/stable/_modules/pipecat_flows/manager.html
from pipecat_flows import FlowsFunctionSchema, FlowManager

def build_transfer_schema() -> FlowsFunctionSchema:
    return FlowsFunctionSchema(
        name="transfer_call",
        description=(
            "Trasferisci la chiamata a un operatore umano. "
            "Usa quando il cliente lo richiede esplicitamente, "
            "quando parla una lingua diversa dall'italiano, "
            "quando la richiesta è fuori dal tuo ambito, "
            "o quando non riesci ad aiutare."
        ),
        properties={
            "reason": {
                "type": "string",
                "description": "Motivo del trasferimento (es. 'richiesta_cliente', 'lingua_non_supportata', 'fuori_ambito').",
            },
        },
        required=["reason"],
        handler=handle_transfer_call,
    )

async def handle_transfer_call(args: dict, fm: FlowManager) -> tuple[dict, None]:
    """Transfer stub — local path (D-01, D-04, HAND-04).

    Security (T-injection): transfer_number resolved from TRUSTED config only,
    never from caller-supplied args. See PITFALLS.md §Security.
    """
    from pipecat.frames.frames import EndWorkerFrame, FrameDirection, TTSSpeakFrame

    tenant = fm.state.get("tenant")
    transfer_number = (tenant.transfer_number if tenant else None) or "operatore"
    reason = args.get("reason", "richiesta_cliente")

    # Assemble warm-ready payload (D-04) — used by Fase 4 for real warm transfer
    warm_payload = {
        "transfer_number": transfer_number,
        "reason": reason,
        "booking_slot": fm.state.get("booking_slot"),
        "customer": fm.state.get("customer"),
        "confirmed_event_id": fm.state.get("confirmed_event_id"),
    }
    fm.state["transfer_payload"] = warm_payload
    fm.state["transfer_reason"] = reason
    fm.state["outcome"] = "trasferito"

    # Speak handoff phrase BEFORE ending pipeline (D-01 courtesy)
    await fm.worker.queue_frames([
        TTSSpeakFrame(
            text="La metto in contatto con un operatore, resti in linea.",
            append_to_context=False,
        )
    ])
    # Clean shutdown — EndWorkerFrame upstream terminates pipeline (D-01 stub)
    await fm.worker.queue_frame(EndWorkerFrame(), FrameDirection.UPSTREAM)
    return {"transferred": True, "to": transfer_number}, None
```

**Wiring in bot.py:**
```python
# In setup_flow(), add global_functions parameter
flow_manager = FlowManager(
    llm=llm,
    context_aggregator=aggregators,
    worker=worker,
    global_functions=[build_transfer_schema()],   # HAND-04 — new in Phase 3
)
```

### Pattern 3: Dead-Air Watchdog (REL-04)

**What:** Pipecat 1.4.0 ships a built-in idle-user detection mechanism via `LLMUserAggregatorParams(user_idle_timeout=T1)`. The timer starts after `BotStoppedSpeakingFrame` and resets on any user or bot speaking event. At expiry, `on_user_turn_idle` fires.

**Verified mechanism:** [VERIFIED: docs.pipecat.ai/guides/fundamentals/detecting-user-idle]

```python
# Source: docs.pipecat.ai/guides/fundamentals/detecting-user-idle
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.frames.frames import EndWorkerFrame, FrameDirection, TTSSpeakFrame, LLMMessagesAppendFrame

# In build_pipeline() / build_user_aggregator_params(), add user_idle_timeout:
aggregators = LLMContextAggregatorPair(
    context,
    user_params=LLMUserAggregatorParams(
        vad_enabled=True,
        aggregation_timeout=0.2,   # keep existing low timeout
        user_idle_timeout=6.0,     # T1 = 6s (D-14 planning default)
    ),
)
```

**Escalation handler (in bot.py, after setup_flow):**
```python
# Source: docs.pipecat.ai/guides/fundamentals/detecting-user-idle (adapted)
class _DeadAirHandler:
    def __init__(self):
        self._count = 0

    def reset(self):
        self._count = 0

    async def on_idle(self, aggregator):
        self._count += 1
        if self._count == 1:
            # T1 expired → gentle re-prompt (D-14)
            await aggregator.push_frame(
                LLMMessagesAppendFrame(
                    [{"role": "developer",
                      "content": "L'utente è silenzioso. Chiedi gentilmente 'È ancora in linea?'"}],
                    run_llm=True,
                )
            )
            # Extend to T2 (total silence ~T1+T2 before transfer)
            # T2 = 8s extra → after re-prompt, next idle fires at T2
        else:
            # T2 expired → escalation: transfer (D-14)
            flow_manager.state["outcome"] = "fallito"
            await aggregator.push_frame(
                TTSSpeakFrame(
                    text="Non riesco a sentirla, la passo a un operatore.",
                    append_to_context=False,
                )
            )
            await aggregator.push_frame(EndWorkerFrame(), FrameDirection.UPSTREAM)

dead_air_handler = _DeadAirHandler()

@aggregators.user().event_handler("on_user_turn_idle")
async def _on_user_turn_idle(aggregator):
    await dead_air_handler.on_idle(aggregator)

@aggregators.user().event_handler("on_user_turn_started")
async def _on_user_turn_started(aggregator, strategy):
    dead_air_handler.reset()
```

**Note on T1/T2 semantics:** The `user_idle_timeout` is a single value. After re-prompt (count=1), if the user stays silent another T1 seconds, the event fires again (count=2 → transfer). Effective total silent time before transfer ≈ T1 + T1 = 2×T1. To make T2 ≠ T1, update the timeout dynamically after re-prompt:
```python
# After re-prompt, increase timeout to T2 for second escalation
await worker.queue_frame(UserIdleTimeoutUpdateFrame(timeout=8.0))  # T2
```
[VERIFIED: `UserIdleTimeoutUpdateFrame` confirmed in Pipecat API ref]

**Recommended values (D-14 Claude's Discretion):**
- T1 = 6s (re-prompt)
- T2 = 8s (after re-prompt, escalation)

**Important limitation:** The `user_idle_timeout` timer starts only after the BOT stops speaking. If the bot never gets to speak (TTS failure), this timer does not engage — but in that case, the `ErrorFallbackObserver` escalation (Pattern 4) handles it.

### Pattern 4: Persistent-Failure Escalation (REL-02)

**What:** Extend the existing `ErrorFallbackObserver` to count per-source errors. After N consecutive errors from the same source (after `ServiceSwitcher` has already switched STT), the observer queues a transfer and terminates the call.

**Extension plan (builds on existing `fallback.py`):**
```python
# Extend ErrorFallbackObserver in fallback.py
# Add threshold (e.g., 3 consecutive errors from ANY single source → escalate)
_ESCALATION_THRESHOLD = 3

async def on_push_frame(self, data: FramePushed) -> None:
    # ... existing retry-slot logic ...
    # Add: after retry slot exhausted, count escalation hits
    if count >= _ESCALATION_THRESHOLD:
        self._retry_counts[src_name] = 0
        # Only escalate if not already transferring
        if not self._escalated:
            self._escalated = True
            self._flow_manager.state["outcome"] = "fallito"
            await self.worker.queue_frames([
                TTSSpeakFrame(
                    text="Mi scusi, sto riscontrando problemi tecnici. La trasferisco a un operatore.",
                    append_to_context=False,
                ),
                EndWorkerFrame(),  # upstream direction
            ])
```

### Pattern 5: End-of-Call Summary Hook (NOTIF-01/02)

**What:** After `await runner.run()` returns in `bot()`, the pipeline is fully stopped. Run cleanup in a `try/finally` to guarantee execution regardless of how the call ended (normal, transfer, error, disconnect).

**Why NOT `on_client_disconnected`:** The `on_client_disconnected` handler fires mid-shutdown (pipeline may still be draining). Code after `runner.run()` runs in a clean single-awaited context. [VERIFIED: behavior confirmed by examining `bot.py` + Pipecat lifecycle docs]

```python
# In bot(), after runner = WorkerRunner(...) / runner.run():
try:
    await runner.run()
finally:
    # Summary + notification always runs (D-07 — every call, every outcome)
    outcome = _determine_outcome(flow_manager.state)
    transcript = list(context.messages)           # context.messages is the source of truth
    summary_text = await _generate_summary(tenant, transcript, outcome)
    log_id = await call_log_repo.write(
        tenant_id=tenant.id,
        started_at=call_start_time,
        outcome=outcome,
        transcript_json=transcript,
        summary_text=summary_text,
        reservation_id=flow_manager.state.get("reservation_id"),
        google_event_id=flow_manager.state.get("confirmed_event_id"),
        transfer_number=flow_manager.state.get("transfer_payload", {}).get("transfer_number"),
    )
    channel = NotificationChannelFactory.create(tenant.notification_channel, tenant)
    subject = f"Chiamata {datetime.now(ROME_TZ).strftime('%d/%m %H:%M')} — {outcome.capitalize()}"
    await channel.send(subject=subject, body=summary_text)
```

**`_determine_outcome()` logic:**
```python
def _determine_outcome(state: dict) -> str:
    if state.get("outcome"):          # explicit override (transfer, fallito, etc.)
        return state["outcome"]
    if state.get("confirmed_event_id"):
        return "prenotato"
    if state.get("faq_answered"):
        return "faq"
    if state.get("booking_slot") and not state.get("confirmed_event_id"):
        return "abbandonato"          # matches D-18 bozza behavior
    return "faq"                      # default if no booking attempted
```

**`_generate_summary()` — LLM call:**
```python
# Use existing llm service (AnthropicLLMService) or raw anthropic SDK
# Model: claude-haiku-4-5 (low TTFT, adequate for 2-3 sentence summary)
# NOTE: model id tagged [ASSUMED] — verify at build time (see CLAUDE.md warning)
async def _generate_summary(tenant: TenantConfig, transcript: list, outcome: str) -> str:
    # Build a condensed text transcript (user/assistant turns only)
    turns = [
        f"{'Cliente' if m['role']=='user' else 'Bot'}: {m.get('content','')}"
        for m in transcript
        if m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
    ]
    transcript_text = "\n".join(turns[-20:])   # last 20 turns to stay within tokens

    prompt = (
        f"Sei un assistente che riassume chiamate per il titolare di {tenant.business_name}.\n"
        f"Esito della chiamata: {outcome}.\n\n"
        f"Trascrizione:\n{transcript_text}\n\n"
        "Scrivi un riassunto in italiano di 2-3 frasi brevi: chi ha chiamato (se noto), "
        "cosa voleva, e com'è andata a finire. Sii conciso e professionale."
    )
    # Direct Anthropic SDK call (not via FlowManager which is torn down)
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = await client.messages.create(
        model=tenant.model or "claude-haiku-4-5",   # [ASSUMED: verify model id at build]
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
```

### Pattern 6: Notification Channels

#### `LogNotificationChannel` (default, zero-dep)
```python
# Writes to call_logs — the log is written by the repository; this channel
# can simply log to loguru or return immediately (the call_log IS the log).
class LogNotificationChannel(NotificationChannel):
    async def send(self, subject: str, body: str) -> None:
        from loguru import logger
        logger.info(f"[CALL LOG] {subject}\n{body}")
```

#### `TelegramNotificationChannel` (direct aiohttp — no extra dep)
```python
# Source: core.telegram.org/bots/api#sendmessage
# aiohttp is already in pipecat's transitive deps
import aiohttp

class TelegramNotificationChannel(NotificationChannel):
    def __init__(self, token: str, chat_id: str):
        # Security: token from env, never from caller input (T-injection)
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, subject: str, body: str) -> None:
        text = f"*{subject}*\n\n{body}"
        payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            async with session.post(self._url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    from loguru import logger
                    logger.warning(f"Telegram sendMessage failed: {resp.status}")
```

**How to get a Telegram bot token:**
1. Message @BotFather on Telegram → `/newbot` → copy the token
2. Send a message to the bot from your account
3. `GET https://api.telegram.org/bot{TOKEN}/getUpdates` → find `chat.id`
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

#### `EmailNotificationChannel` (aiosmtplib)
```python
# Source: aiosmtplib.readthedocs.io/en/latest/usage.html
import aiosmtplib
from email.message import EmailMessage

class EmailNotificationChannel(NotificationChannel):
    def __init__(self, host: str, port: int, user: str, password: str, to: str, from_: str):
        self._host, self._port, self._user = host, port, user
        self._password, self._to, self._from = password, to, from_

    async def send(self, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = self._to
        msg["Subject"] = subject
        msg.set_content(body)
        await aiosmtplib.send(
            msg,
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,   # Security: from env, never from caller
        )
```

#### `SMSNotificationChannel` (stub — Telnyx Messaging API shape)
```python
# Stub only in Phase 3; Telnyx Messaging API or Twilio in Phase 4+
class SMSNotificationChannel(NotificationChannel):
    async def send(self, subject: str, body: str) -> None:
        from loguru import logger
        logger.info(f"[SMS STUB] Would send to {self._to}: {subject}\n{body}")
```

#### `NotificationChannelFactory`
```python
def create_channel(name: str | None, tenant: TenantConfig) -> NotificationChannel:
    name = (name or "log").lower()
    if name == "telegram":
        return TelegramNotificationChannel(
            token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        )
    if name == "email":
        return EmailNotificationChannel(
            host=os.getenv("SMTP_HOST", ""),
            port=int(os.getenv("SMTP_PORT", "587")),
            user=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            to=os.getenv("SMTP_TO", ""),
            from_=os.getenv("SMTP_FROM", ""),
        )
    if name in ("sms", "whatsapp"):
        return SMSNotificationChannel(...)
    return LogNotificationChannel()   # fallback/default
```

### Anti-Patterns to Avoid

- **Anti-pattern — eager WhisperSTTService in pipeline:** Instantiating `WhisperSTTService` at pipeline build time loads the 800MB+ model immediately, blocking startup for 5-15s on CPU. Use `LazyWhisperSTTService`.
- **Anti-pattern — transfer_number from caller args:** Never read the target number from `args` in the transfer handler. Read exclusively from `fm.state["tenant"].transfer_number` (T-injection prevention, PITFALLS §Security).
- **Anti-pattern — summary in on_client_disconnected:** The disconnect handler fires during pipeline shutdown (racy). Run summary/notification in `finally:` after `runner.run()` returns.
- **Anti-pattern — full transcript in notification body:** Keep the notification body to the 2-3 sentence LLM summary. Full transcript goes to `call_logs`. (D-05)
- **Anti-pattern — global functions NOT passed to FlowManager:** Current `bot.py` creates `FlowManager(llm=llm, context_aggregator=aggregators, worker=worker)` — `global_functions` must be added in Phase 3 or the transfer tool is invisible from booking/faq nodes.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| STT failover routing | Custom frame interceptor that tries to redirect audio bytes | `ServiceSwitcher` + `ServiceSwitcherStrategyFailover` from pipecat.pipeline | ServiceSwitcher handles filter gates, error propagation, metadata frames, keepalive — all underdocumented edge cases |
| Async SMTP | `smtplib` with `asyncio.run_coroutine_threadsafe` | `aiosmtplib.send()` | smtplib blocks; threading in async context is fragile |
| Idle/dead-air timer | Custom `asyncio.Task` checking frame timestamps | `LLMUserAggregatorParams(user_idle_timeout=...)` + `on_user_turn_idle` | Built-in integrates with the VAD/turn lifecycle correctly — custom timers miss the "during TTS" suppression |
| Conversation transcript | Re-building from custom log | `context.messages` (the `LLMContext` messages list) | Context is the canonical source; already maintained by the aggregators |

**Key insight:** Pipecat 1.4.0's `ServiceSwitcher` and the `LLMUserAggregator`'s idle mechanism were built specifically for production voice-agent reliability — use them rather than building parallel solutions that miss integration points.

---

## call_logs Schema (D-08)

**Design principles:** single TEXT column for transcript JSON (Postgres-compatible as TEXT/JSONB on migration), not a separate turns table (avoids join complexity for a per-call-log read). Outcome stored as TEXT with CHECK constraint (mirrors the `status` pattern in `reservations`). All FKs nullable (`reservations.id`, `transfer_number`) for non-booking outcomes.

```sql
-- Phase 3 addition to schema.sql
-- call_logs: one row per completed call (NOTIF-01, D-06, D-08).
-- transcript_json: JSON array of {role, content} messages from context.messages.
-- outcome: tassonomia D-06 — prenotato/faq/trasferito/abbandonato/fallito.
-- Postgres-migration note: transcript_json maps 1:1 to JSONB; no schema change.
CREATE TABLE IF NOT EXISTS call_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id         TEXT NOT NULL REFERENCES tenants(id),
    started_at        TEXT NOT NULL,              -- ISO 8601 call start time (Europe/Rome)
    ended_at          TEXT NOT NULL DEFAULT (datetime('now')),
    duration_secs     INTEGER,                    -- (ended_at - started_at) in seconds
    outcome           TEXT NOT NULL
                        CHECK(outcome IN ('prenotato','faq','trasferito','abbandonato','fallito')),
    transcript_json   TEXT NOT NULL,              -- JSON array [{role, content}, ...]
    summary_text      TEXT,                       -- 2-3 frasi LLM (D-05), NULL if gen failed
    reservation_id    INTEGER REFERENCES reservations(id),   -- set for 'prenotato'
    google_event_id   TEXT,                       -- shortcut for notification display
    transfer_number   TEXT,                       -- resolved number for 'trasferito'
    channel_sent      TEXT,                       -- notification channel name used
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_call_logs_tenant
    ON call_logs(tenant_id, started_at);
```

**`CallLogRepository` pattern** (matching `TenantRepository` style):
```python
# src/call_log/repository.py
import json
import aiosqlite
from pathlib import Path

class CallLogRepository:
    def __init__(self, db_path: str = "centralino.db"):
        self._db_path = db_path

    async def write(
        self, *, tenant_id: str, started_at: str, outcome: str,
        transcript_json: list, summary_text: str | None = None,
        reservation_id: int | None = None, google_event_id: str | None = None,
        transfer_number: str | None = None, channel_sent: str | None = None,
    ) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO call_logs
                  (tenant_id, started_at, outcome, transcript_json,
                   summary_text, reservation_id, google_event_id,
                   transfer_number, channel_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id, started_at, outcome,
                    json.dumps(transcript_json, ensure_ascii=False),  # T-02-07: no PII filter yet
                    summary_text, reservation_id, google_event_id,
                    transfer_number, channel_sent,
                ),
            )
            await db.commit()
            return cursor.lastrowid
```

**PII note:** The `transcript_json` column stores the full conversation including caller name and phone. Access should be restricted to the tenant owner. In Phase 5, add a retention policy and access-control review. For Phase 3, write the column as-is (consistent with the existing `reservations.name`/`reservations.phone` pattern). [ASSUMED: no explicit PII retention requirement specified for Phase 3 — confirm with owner if needed]

---

## Common Pitfalls

### Pitfall 1: WhisperSTTService Eager Model Load Blocks Startup
**What goes wrong:** `WhisperSTTService()` in `__init__` calls `self._load()` → `WhisperModel(model_name, device, compute_type)` synchronously. On CPU with LARGE_V3_TURBO (~800MB download, ~1.5GB RAM), this blocks the bot startup for 5-15 seconds. If placed in `build_pipeline()`, every call waits on model load even when Deepgram works.
**Why it happens:** eager `_load()` in `__init__` (confirmed from pipecat 1.4.0 source). Only `WhisperSTTServiceMLX` is lazy.
**How to avoid:** `LazyWhisperSTTService` that overrides `_load()` to no-op, defers `WhisperModel()` to first `_run_stt()` call via `asyncio.to_thread()`.
**Warning signs:** bot startup consistently takes 10+ seconds; latency log shows delay before first turn; model load logged at bot start even when STT is "deepgram".

### Pitfall 2: Global Functions Not in FlowManager Constructor
**What goes wrong:** Transfer tool added to greeting/booking/faq `functions` list individually (repetitive, easy to forget one). Or: transfer tool is in a single node and unreachable from others.
**Why it happens:** `global_functions` parameter exists but requires explicit opt-in.
**How to avoid:** Pass `global_functions=[build_transfer_schema()]` to `FlowManager()`. Verify the LLM can call `transfer_call` from the booking node (which has its own functions list).
**Warning signs:** `transfer_call` tool not in LLM's function list when inside booking/faq node; LLM apologizes verbally but cannot actually transfer.

### Pitfall 3: Transfer Number from Caller Input (T-injection)
**What goes wrong:** Handler reads `args["transfer_number"]` or constructs the target from conversational context. Attacker says "transfer me to +1-555-ATTACKER" and the bot routes there.
**Why it happens:** Handler trusts args dict instead of fm.state.
**How to avoid:** In `handle_transfer_call`, read only `fm.state["tenant"].transfer_number`. Args may include `reason` (safe; logged only). Never call telephony with an unvalidated number.
**Warning signs:** transfer target changes based on what the caller says; unit test that passes an arbitrary number in args and verifies it's ignored.

### Pitfall 4: Summary Runs Inside on_client_disconnected (Race Condition)
**What goes wrong:** The summary LLM call and `call_log` write take 1-3 seconds. If run inside `on_client_disconnected`, the handler returns while the pipeline is still being torn down, and the `runner.run()` context exits before the async work finishes — partial writes, unhandled coroutine warnings.
**Why it happens:** `on_client_disconnected` fires asynchronously during pipeline shutdown.
**How to avoid:** All end-of-call work runs in `finally:` after `await runner.run()` returns. The runner only returns after the pipeline has fully stopped.
**Warning signs:** `asyncio.Task was destroyed but it is pending` warnings; `call_logs` rows missing or with partial data.

### Pitfall 5: ServiceSwitcher Requires Both Services Instantiated Upfront
**What goes wrong:** If you try to pass `None` as the backup service and add it later, `ServiceSwitcher` has no second entry to switch to.
**Why it happens:** ServiceSwitcher's `services` list is set at construction.
**How to avoid:** Create `LazyWhisperSTTService()` at pipeline build time (instantiation is fast — no model load); the model loads on first use via `asyncio.to_thread`.
**Warning signs:** `IndexError` in ServiceSwitcher failover strategy; backup service not available when needed.

### Pitfall 6: Non-Italian Detection Depends on STT
**What goes wrong:** If Deepgram transcribes non-Italian speech and the LLM is instructed to detect language from the transcript, STT errors on foreign phonemes may produce garbage transcripts, making detection unreliable.
**Why it happens:** Deepgram `nova-2` with `language=Language.IT` forces Italian transcription — it will try to transcribe anything as Italian.
**How to avoid:** Set the language detection instruction in the greeting node's `task_messages`, and accept that detection is based on Claude's judgment of the transcript. For Phase 3 (local path), this is sufficient. The guarantee is: "the model recognizes obviously non-Italian content and transfers." Near-Italian languages (e.g., Spanish) may not be caught reliably — acceptable for v1.
**Warning signs:** Non-Italian callers are not transferred; Spanish-speaking test generates Italian-looking transcript.

### Pitfall 7: Whisper WebSocket Keepalive Not Needed (Whisper is Offline)
**What goes wrong:** You add `keepalive_timeout` to `WhisperSTTService` (which has no WebSocket connection) thinking it prevents connection drops.
**Why it happens:** Keepalive is for WebSocket-based STT services (Deepgram, etc.). `WhisperSTTService` runs locally via `faster-whisper` — no network connection, no keepalive needed.
**How to avoid:** Only set `keepalive_timeout` on `DeepgramSTTService` if needed. WhisperSTTService configuration is `device` + `compute_type` + `settings` only.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_run_stt()` delegation in `LazyWhisperSTTService` works by calling `super()._run_stt(audio)` with `self._model` pre-set | Pattern 1 / STT Switcher | If parent class structure differs, lazy wrapper needs adjustment — low risk, verify at implementation |
| A2 | Model: `claude-haiku-4-5` is the correct current Haiku model id for summary generation | Pattern 5 / Summary | Wrong model id → API error; verify against Anthropic API dashboard at build time |
| A3 | `asyncio.to_thread()` for `WhisperModel()` call doesn't deadlock or conflict with pipecat's event loop | Pattern 1 / Lazy load | Edge case: if faster-whisper internally uses thread-local state, isolation may vary — test first transcription carefully |
| A4 | `context.messages` is a plain Python list readable after `runner.run()` completes | Pattern 5 / End-of-call | If the context object is cleared on pipeline shutdown, transcript is lost — verify by inspecting `LLMContext` class in venv |
| A5 | First-switch latency for LARGE_V3_TURBO CPU int8 on a Windows dev laptop is 5-15s | Standard Stack | Could be 30+ seconds on very slow hardware — user would hear dead air during load; mitigate with pre-load option or smaller model if too slow |
| A6 | `EndWorkerFrame()` with `FrameDirection.UPSTREAM` correctly terminates the pipeline when pushed from a FlowsFunctionSchema handler | Pattern 2 / Transfer | If the direction flag doesn't propagate correctly from a tool handler, pipeline won't stop — test with the local WebRTC path |
| A7 | PII in `transcript_json` column: no explicit retention policy requirement for Phase 3 | call_logs schema | If owner/regulator requires transcript deletion after N days, a retention task must be added — confirm with owner |

---

## Open Questions

1. **LARGE_V3_TURBO vs LARGE for Italian quality on CPU int8**
   - What we know: Both support Italian with `language=Language.IT`; LARGE_V3_TURBO is ~5x faster with comparable accuracy; int8 reduces RAM by ~40%
   - What's unclear: Italian WER difference between LARGE and LARGE_V3_TURBO in practice on phone-quality audio
   - Recommendation: Start with LARGE_V3_TURBO int8 (CLAUDE.md allows both); if Italian accuracy is insufficient in testing, switch to LARGE

2. **`context.messages` content after pipeline shutdown**
   - What we know: `LLMContext.messages` is documented as a list of `{role, content}` dicts; updated by aggregators
   - What's unclear: whether the context object is gc'd or reset when `runner.run()` returns
   - Recommendation: Test in Wave 1 by printing `context.messages` after `runner.run()` returns; if empty, cache messages in a list during `on_push_frame`

3. **LLM call for summary — reuse existing `llm` service or fresh SDK call**
   - What we know: `AnthropicLLMService` is optimized for streaming pipeline use; post-run, the service object is still in scope
   - What's unclear: whether `AnthropicLLMService` supports a one-shot `messages.create`-style call outside the pipeline context
   - Recommendation: Use `anthropic.AsyncAnthropic().messages.create()` directly (raw SDK) for the summary — simpler, no frame overhead, predictable

4. **Telegram aiohttp vs python-telegram-bot**
   - What we know: aiohttp is already a dep; python-telegram-bot adds retry/rate-limit handling
   - Recommendation: Use direct aiohttp for Phase 3 (simpler, no new dep); add python-telegram-bot only if rate limiting becomes an issue

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11/3.12 | pipecat-ai 1.4.0 | Must verify | — | Install 3.11 if missing |
| `pipecat-ai` | All pipeline patterns | Already installed | 1.4.0 | — |
| `pipecat-ai[whisper]` / `faster-whisper` | LazyWhisperSTTService | Needs install/verify | ~=1.2.1 (via extra) | Without whisper extra: STT fallback unavailable |
| `aiosmtplib` | EmailNotificationChannel | Available on PyPI | 5.1.2 | Skip email channel in Phase 3 |
| Telegram bot token | TelegramNotificationChannel | User must create via @BotFather | — | Fall back to `log` channel |
| SMTP credentials | EmailNotificationChannel | User must supply | — | Fall back to `log` channel |

**Missing dependencies with no fallback:**
- `pipecat-ai[whisper]` extras must be installed (`pip install "pipecat-ai[whisper]"`) for REL-03 to function. Without it, `WhisperSTTService` import fails.

**Missing dependencies with fallback:**
- Telegram token / SMTP credentials: channels degrade to `log` (D-11 default).

---

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — this section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing, from Phase 1/2) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/ -x -q --tb=short` |
| Full suite command | `pytest tests/ -v --tb=long` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HAND-01 | Caller says "transfer me" → transfer tool called, outcome=trasferito | unit + manual | `pytest tests/test_transfer.py -x` | ❌ Wave 0 |
| HAND-02 | LLM uncertainty → transfer (instructed via system prompt) | manual | — | N/A |
| HAND-03 | Non-Italian utterance in greeting node → transfer tool called | manual + unit | `pytest tests/test_transfer.py::test_non_italian -x` | ❌ Wave 0 |
| HAND-04 | Transfer tool is in LLM's functions list at booking/faq node | unit | `pytest tests/test_transfer.py::test_global_function_visible -x` | ❌ Wave 0 |
| NOTIF-01 | call_log row written after every call end | unit | `pytest tests/test_call_log.py -x` | ❌ Wave 0 |
| NOTIF-02 | Summary text is 2-3 sentences Italian, non-empty | unit (mock LLM) + manual | `pytest tests/test_summary.py -x` | ❌ Wave 0 |
| NOTIF-03 | NotificationChannel.send() called with correct subject/body | unit (mock channel) | `pytest tests/test_notification.py -x` | ❌ Wave 0 |
| NOTIF-04 | All four channel classes instantiate without error | unit | `pytest tests/test_notification.py::test_channels -x` | ❌ Wave 0 |
| NOTIF-05 | Log channel used when config=log; telegram when config=telegram | unit | `pytest tests/test_notification.py::test_factory -x` | ❌ Wave 0 |
| REL-02 | N consecutive errors → transfer queued, outcome=fallito | unit (inject ErrorFrame) | `pytest tests/test_fallback.py::test_escalation -x` | ❌ Wave 0 |
| REL-03 | Deepgram ErrorFrame → ServiceSwitcher activates Whisper | unit (mock switcher) | `pytest tests/test_stt_switcher.py -x` | ❌ Wave 0 |
| REL-04 | user_idle_timeout fires → re-prompt at count=1, transfer at count=2 | unit (inject idle event) | `pytest tests/test_watchdog.py -x` | ❌ Wave 0 |

**SC verification approaches:**

| SC | How to Test on LOCAL Path |
|----|--------------------------|
| SC1 (transfer from any node) | During live test: say "Voglio parlare con una persona" at greeting, mid-booking read-back, and during FAQ — all three should trigger transfer_call and speak the handoff phrase |
| SC2 (summary notification) | After any call, check console log (`log` channel) and/or Telegram (if token set) for a message with correct subject format `Chiamata DD/MM HH:MM — Outcome` |
| SC3 (Deepgram → Whisper) | Set `DEEPGRAM_API_KEY=invalid` → bot should speak courtesy phrase + continue with Whisper (first response may take 10-20s on CPU) |
| SC4 (persistent failure → transfer) | Set `DEEPGRAM_API_KEY=invalid` AND break Whisper (e.g., `device="cuda"` on a CPU-only machine) → after retry threshold, bot speaks courtesy phrase and sends EndWorkerFrame |
| SC5 (dead-air watchdog) | Start a call, don't speak for 6s → bot re-prompts; don't speak for another 8s → bot transfers |

**Forcing provider failures on local path:**
- Deepgram failure: `export DEEPGRAM_API_KEY=xxx_invalid` before starting
- Whisper failure: pass `device="cuda"` on CPU-only machine OR set `Model.LARGE` on a machine with insufficient RAM (OOM → exception in `asyncio.to_thread`)
- LLM failure: `export ANTHROPIC_API_KEY=xxx_invalid`
- TTS failure: `export ELEVENLABS_API_KEY=xxx_invalid`

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q --tb=short`
- **Per wave merge:** `pytest tests/ -v --tb=long`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_transfer.py` — covers HAND-01/03/04
- [ ] `tests/test_call_log.py` — covers NOTIF-01, CallLogRepository
- [ ] `tests/test_summary.py` — covers NOTIF-02
- [ ] `tests/test_notification.py` — covers NOTIF-03/04/05, NotificationChannelFactory
- [ ] `tests/test_stt_switcher.py` — covers REL-03, ServiceSwitcher failover
- [ ] `tests/test_watchdog.py` — covers REL-04, idle handler escalation
- [ ] `tests/test_fallback.py` — extend existing (NOTIF-01 base) to cover REL-02 escalation path

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A (no user auth in this phase) |
| V3 Session Management | partial | Call session scoped to `bot()` coroutine; no cross-call state |
| V4 Access Control | yes | Transfer/notification numbers resolved from `tenant.transfer_number` / env vars ONLY; never from caller-supplied args (T-injection) |
| V5 Input Validation | yes | `outcome` CHECK constraint in schema; `call_log` parameterized SQL |
| V6 Cryptography | no | No keys generated in this phase; channels use existing env vars |
| V7 Error Handling / Logging | yes | `ErrorFrame.error` NEVER logged (existing `fallback.py` constraint); summary LLM call exception must not log PII |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Transfer number injection via caller speech | Tampering | `handle_transfer_call` reads `fm.state["tenant"].transfer_number` — zero influence from `args` |
| Notification target injection (email/phone via caller) | Tampering | Channel targets from env vars only; `NotificationChannelFactory` receives `tenant` config, never caller input |
| PII in exception logs (caller name/phone in summary error) | Information Disclosure | `try/except` in summary generation must not log the `transcript_json` or caller fields on error |
| call_logs transcript as PII store | Information Disclosure | Access limited to tenant owner via notification; Postgres-ready for future row-level security |
| Telegram bot token in env | Elevation of Privilege | `TELEGRAM_BOT_TOKEN` via `.env` (gitignored); never hardcoded; added to `.env.example` as placeholder |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pre-1.0 `PipelineTask` + `PipelineRunner` | `PipelineWorker` + `WorkerRunner` | pipecat 1.0.0 (2026-04) | APIs renamed; old tutorials break |
| Provider-specific context (`OpenAILLMContext`) | `LLMContext` + `LLMContextAggregatorPair` | pipecat 1.0.0 | Universal context across providers |
| Manual STT error → branch code | `ServiceSwitcher` + `ServiceSwitcherStrategyFailover` | pipecat ~0.0.105+ | Automatic failover built-in |
| `task=` in FlowManager | `worker=` in FlowManager | pipecat-ai-flows 1.2.0 | `task` deprecated, removed in future |
| `global_functions` not available | `FlowManager(global_functions=[...])` | pipecat-ai-flows 0.0.22 | Cross-node tools without node-by-node repetition |
| `params=InputParams(...)` style | `settings=ServiceClass.Settings(...)` | pipecat ~0.0.105 | Old kwargs deprecated; settings object is canonical |

**Deprecated/outdated:**
- `task=` parameter in FlowManager: deprecated since Flows 1.2.0, use `worker=`.
- `model=`, `params=InputParams(...)` flat kwargs in service constructors: deprecated since pipecat 0.0.105; use `settings=Service.Settings(...)` exclusively.
- `DISTIL_MEDIUM_EN` / `DISTIL_LARGE_V2`: English-only models — silently produce garbage on Italian (CLAUDE.md "What NOT to Use").

---

## Sources

### Primary (HIGH confidence)
- `reference-flows.pipecat.ai/en/stable/_modules/pipecat_flows/manager.html` — FlowManager source including `global_functions` parameter, `_set_node()` merge logic, `initialize()` method. Confirmed `global_functions` present in 1.3.0.
- `reference-server.pipecat.ai/en/stable/_modules/pipecat/services/whisper/stt.html` — WhisperSTTService `__init__` + `_load()` source. Confirmed eager model loading in standard service; `WhisperSTTServiceMLX._load()` is a no-op (lazy). LARGE_V3_TURBO confirmed in Model enum.
- `docs.pipecat.ai/guides/fundamentals/detecting-user-idle` — `LLMUserAggregatorParams.user_idle_timeout`, `on_user_turn_idle` event, `IdleHandler` escalation pattern, `UserIdleTimeoutUpdateFrame`. Confirmed built-in mechanism.
- `docs.pipecat.ai/api-reference/server/utilities/service-switchers/service-switcher` — ServiceSwitcher constructor, `ServiceSwitcherStrategyFailover`, `on_service_switched` event, `ManuallySwitchServiceFrame`. Imports confirmed.
- `reference-server.pipecat.ai/en/latest/_modules/pipecat/pipeline/service_switcher.html` — ServiceSwitcher source confirming failover rotates on ErrorFrame, event propagation.
- PyPI registry (pip index versions) — `pipecat-ai==1.4.0`, `pipecat-ai-flows==1.3.0`, `aiosmtplib==5.1.2` all confirmed current versions (2026-06-27).

### Secondary (MEDIUM confidence)
- `aiosmtplib.readthedocs.io/en/latest/usage.html` — aiosmtplib `send()` function, STARTTLS config, authentication. Version 5.1.2 confirmed.
- `core.telegram.org/bots/api` — Telegram Bot API `sendMessage` endpoint, `chat_id` + `text` params.
- `pypi.org/project/aiosmtplib/` + `pypi.org/project/python-telegram-bot/` — first-publish dates, download stats, GitHub repos for package legitimacy.

### Tertiary (LOW confidence)
- GitHub benchmark issue #1030 (SYSTRAN/faster-whisper) — GPU-only benchmarks; CPU latency estimate for LARGE_V3_TURBO (5-15s) is extrapolated from GPU data and community reports — NOT measured on Windows. [ASSUMED]
- Web community reports on WhisperSTTService first-activation latency on CPU — estimate; actual value on target machine may differ.

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — all libraries confirmed on PyPI at stated versions; pipecat APIs verified via official API reference and source
- Architecture: HIGH — ServiceSwitcher, global_functions, idle timeout all verified directly in pipecat/flows sources and official docs
- Faster-whisper lazy load pattern: MEDIUM — approach is sound (based on MLX variant's `_load()` no-op), but parent class `_run_stt` delegation needs verification at implementation time
- CPU load latency for LARGE_V3_TURBO: LOW — no Windows-specific benchmark; estimate based on model size and community reports
- End-of-call summary hook: HIGH — `finally:` after `runner.run()` is a standard Python pattern; confirmed pipecat `runner.run()` returns after pipeline stops

**Research date:** 2026-06-27
**Valid until:** 2026-07-27 (stable pipecat 1.4.0 / Flows 1.3.0 APIs; notification channel patterns are standard)
