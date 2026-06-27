# Phase 3: Handoff + Summary + Notifications — Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 23 (16 new, 7 modified)
**Analogs found:** 23 / 23

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/pipeline/stt_switcher.py` | utility | failover | `src/pipeline/factory.py` | role-match |
| `src/telephony/base.py` | interface | request-response | `src/interfaces/calendar_provider.py` | exact |
| `src/telephony/stub.py` | service (stub) | request-response | `src/calendar/memory_provider.py` | exact |
| `src/notifications/log_channel.py` | service | event-driven | `src/calendar/memory_provider.py` | role-match |
| `src/notifications/telegram_channel.py` | service | request-response | `src/calendar/memory_provider.py` | role-match |
| `src/notifications/email_channel.py` | service | request-response | `src/calendar/memory_provider.py` | role-match |
| `src/notifications/sms_channel.py` | service (stub) | request-response | `src/calendar/memory_provider.py` | role-match |
| `src/notifications/factory.py` | utility/factory | transform | `src/pipeline/factory.py` | role-match |
| `src/call_log/repository.py` | repository | CRUD | `src/booking/repository.py` | exact |
| `src/call_log/summary.py` | service | request-response | `src/flows/functions.py` | role-match |
| `src/bot.py` *(modified)* | entrypoint | request-response | `src/bot.py` (self) | exact |
| `src/pipeline/build.py` *(modified)* | config/utility | request-response | `src/pipeline/build.py` (self) | exact |
| `src/pipeline/fallback.py` *(modified)* | middleware/observer | event-driven | `src/pipeline/fallback.py` (self) | exact |
| `src/flows/functions.py` *(modified)* | service | event-driven | `src/flows/functions.py` (self) | exact |
| `src/flows/nodes.py` *(modified)* | config | event-driven | `src/flows/nodes.py` (self) | exact |
| `src/db/schema.sql` *(modified)* | migration | CRUD | `src/db/schema.sql` (self) | exact |
| `tests/test_transfer.py` | test | — | `tests/test_observers.py` | role-match |
| `tests/test_call_log.py` | test | — | `tests/test_repository.py` | exact |
| `tests/test_summary.py` | test | — | `tests/test_observers.py` | role-match |
| `tests/test_notification.py` | test | — | `tests/test_observers.py` | role-match |
| `tests/test_stt_switcher.py` | test | — | `tests/test_observers.py` | role-match |
| `tests/test_watchdog.py` | test | — | `tests/test_observers.py` | role-match |

---

## Pattern Assignments

### `src/pipeline/stt_switcher.py` (NEW — utility, failover)

**Analog:** `src/pipeline/factory.py`

**Imports pattern** (lines 1–27 of factory.py):
```python
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.whisper.stt import Model, WhisperSTTService
from pipecat.transcriptions.language import Language
# NEW — these are Phase 3 additions:
from pipecat.pipeline.service_switcher import (
    ServiceSwitcher,
    ServiceSwitcherStrategyFailover,
)
from pipecat.frames.frames import TTSSpeakFrame

from src.config.tenant_config import TenantConfig
```

**Core pattern to copy — WhisperProvider** (factory.py lines 79–96):
```python
class WhisperProvider(STTProvider):
    def create_service(self) -> WhisperSTTService:
        return WhisperSTTService(
            settings=WhisperSTTService.Settings(
                model=Model.LARGE_V3_TURBO,
                language=Language.IT,
                no_speech_prob=0.4,
            ),
        )
```
`LazyWhisperSTTService` subclasses `WhisperSTTService`, overrides `_load()` to be a no-op, and defers `WhisperModel()` to the first `_run_stt()` call via `asyncio.to_thread()`. Do NOT copy the eager `__init__` path.

**Security pattern — API key via env only** (factory.py lines 59–60):
```python
# Security (T-02-KEY): key via env only, never logged.
api_key=os.getenv("DEEPGRAM_API_KEY"),
```

**Error / no-secrets rule** (fallback.py lines 11–16):
```python
# Security (V7 / T-03-LOG):
#   - The raw ErrorFrame.error string is NEVER printed or logged.
#   - The sanitized `source.name` (service class name, no key) is all that is used.
```

---

### `src/telephony/base.py` (NEW — interface, request-response)

**Analog:** `src/interfaces/calendar_provider.py`

**Full interface pattern** (calendar_provider.py lines 1–53):
```python
"""CalendarProvider interface seam (Phase 2 — booking).

Defined now so the booking phase adds a concrete implementation (e.g. Google
Calendar) *behind* this interface rather than restructuring code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class CalendarProvider(ABC):
    """Calendar backend for reservations/appointments (Phase 2 seam).

    All methods are tenant-scoped: the provider maps tenant_id → calendar_id
    internally ...  Callers never supply a raw calendar identifier —
    only tenant_id from the session context (T-03).
    """

    @abstractmethod
    async def check_availability(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def create_event(
        self, tenant_id: str, start: datetime, end: datetime,
        title: str, details: str | None = None,
    ) -> str:
        raise NotImplementedError
```

Copy structure exactly. `TelephonyProvider` exposes one abstract method: `async transfer(number: str, context: dict) -> None`. Docstring must note: number is ALWAYS from trusted config (T-injection), never caller args.

---

### `src/telephony/stub.py` (NEW — service stub, request-response)

**Analog:** `src/calendar/memory_provider.py`

**Concrete stub pattern** (memory_provider.py lines 1–65):
```python
"""InMemoryCalendarProvider — in-memory CalendarProvider for tests (D-12).

No real network calls; events are stored in a list and scoped by tenant_id.
Use this in unit tests and local development ...
"""

from __future__ import annotations

from datetime import datetime

from src.interfaces.calendar_provider import CalendarProvider


class InMemoryCalendarProvider(CalendarProvider):
    """In-memory CalendarProvider for tests (D-12).

    No real network calls.  Events are isolated by tenant_id (D-10).
    Event ids follow the pattern ``mem-<n>`` (e.g. ``mem-1``, ``mem-2``).
    """

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._next_id: int = 1

    async def create_event(self, tenant_id: str, ...) -> str:
        event_id = f"mem-{self._next_id}"
        self._next_id += 1
        self._events.append({...})
        return event_id
```

`LocalTransferStub` imports from `src/telephony/base.py`, implements `TelephonyProvider`, and **logs the transfer intent only** — it does NOT call a real telephony API. The frame side-effects (`TTSSpeakFrame` courtesy phrase + `EndWorkerFrame`) are queued by `handle_transfer_call` in `src/flows/functions.py` (the handler owns frame work, per 03-01 Task 2 + RESEARCH.md Pattern 2), not by the stub.

---

### `src/notifications/log_channel.py` (NEW — service, event-driven)
### `src/notifications/telegram_channel.py` (NEW — service, request-response)
### `src/notifications/email_channel.py` (NEW — service, request-response)
### `src/notifications/sms_channel.py` (NEW — service stub, request-response)

**Analog (ABC being implemented):** `src/interfaces/notification_channel.py`

**Interface to implement** (notification_channel.py lines 1–19):
```python
"""NotificationChannel interface seam (Phase 3 — end-of-call summary dispatch)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    """A per-tenant outbound notification channel (Phase 3 seam)."""

    @abstractmethod
    async def send(self, subject: str, body: str) -> None:
        """Deliver a notification (e.g. end-of-call summary) to the recipient."""
        raise NotImplementedError
```

**Concrete-impl structure to copy** (memory_provider.py pattern):
```python
from __future__ import annotations
from src.interfaces.notification_channel import NotificationChannel


class LogNotificationChannel(NotificationChannel):
    """Zero-dependency fallback — writes to loguru. Default for local/demo (D-11)."""

    async def send(self, subject: str, body: str) -> None:
        from loguru import logger
        logger.info(f"[CALL LOG] {subject}\n{body}")
```

**Security rule for all channel impls:**
- `__init__` params come from env vars only — never from caller/args (T-injection)
- Exception handlers must NOT log `subject`/`body` (potential PII)
- Pattern from `flows/functions.py` lines 334–340:
```python
    except Exception as exc:
        # PII (phone/name) is intentionally NOT logged (T-02-07).
        logger.error(
            f"Calendar create_event failed for tenant {tenant_id!r}: "
            f"{type(exc).__name__}: {exc}"   # type + message only, no args payload
        )
        return {"available": False, "error": "calendario non disponibile"}, None
```

**SMS/WhatsApp stub pattern** — same shape as `LogNotificationChannel` but logs `[SMS STUB]` and does NOT call any external API in Phase 3.

---

### `src/notifications/factory.py` (NEW — utility/factory, transform)

**Analog:** `src/pipeline/factory.py` — `get_stt_provider()` and `_STT_PROVIDERS` dict

**Factory pattern to copy** (factory.py lines 99–116):
```python
_STT_PROVIDERS: dict[str, type[STTProvider]] = {
    "deepgram": DeepgramProvider,
    "whisper": WhisperProvider,
}


def get_stt_provider(config_key: str = "deepgram") -> STTProvider:
    """Return the STTProvider instance for the given config_key.

    Valid keys: ``"deepgram"`` (default), ``"whisper"``.
    """
    cls = _STT_PROVIDERS.get(config_key)
    if cls is None:
        raise ValueError(
            f"Unknown STT provider: {config_key!r}. Valid: {list(_STT_PROVIDERS)}"
        )
    return cls()
```

`NotificationChannelFactory.create(name, tenant)` maps `"log"/"telegram"/"email"/"sms"/"whatsapp"` → channel instance. Reads credentials from `os.getenv()` only. Falls back to `LogNotificationChannel` on unknown name (D-11 default).

---

### `src/call_log/repository.py` (NEW — repository, CRUD)

**Analog:** `src/booking/repository.py` (INSERT + lastrowid pattern) and `src/config/repository.py` (init_db + schema path pattern)

**Init + schema path pattern** (config/repository.py lines 20–35):
```python
# schema.sql lives at src/db/schema.sql, one level up from this module's package.
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


class TenantRepository:
    def __init__(self, db_path: str = "centralino.db"):
        self._db_path = db_path

    async def init_db(self) -> None:
        """Create the tenants table from src/db/schema.sql (idempotent)."""
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()
```

**INSERT + lastrowid pattern** (booking/repository.py lines 78–105):
```python
async with aiosqlite.connect(self._db_path) as db:
    await db.execute("BEGIN IMMEDIATE")
    try:
        await db.execute(
            """INSERT INTO reservations
               (tenant_id, slot_date, slot_time, covers, name, phone, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, 'bozza', ?)""",
            (tenant_id, slot_date, slot_time, covers, name, phone, notes),
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            row = await cur.fetchone()
        return True, row[0] if row else None
    except Exception:
        await db.execute("ROLLBACK")
        raise
```

`CallLogRepository.write()` uses the same `async with aiosqlite.connect(self._db_path) as db` + `await db.execute(INSERT ..., (...))` + `await db.commit()` + `SELECT last_insert_rowid()` pattern. All SQL parameterized with `?` — never f-strings (T-01-SQLI). Path to schema: `Path(__file__).resolve().parents[1] / "db" / "schema.sql"`.

---

### `src/call_log/summary.py` (NEW — service, request-response)

**Analog:** `src/flows/functions.py` — async handler with try/except + PII safety

**PII-safe error handling pattern** (functions.py lines 330–340):
```python
    except Exception as exc:
        # Calendar write failed — stay in booking node, no false confirmation (T-02-04).
        # PII (phone/name) is intentionally NOT logged (T-02-07). ...
        logger.error(
            f"Calendar create_event failed for tenant {tenant_id!r}: "
            f"{type(exc).__name__}: {exc}"
        )
        return {"available": False, "error": "calendario non disponibile"}, None
```

`generate_summary(tenant, transcript, outcome)` must:
1. Build condensed transcript text from the last N turns (no raw context object after shutdown)
2. Make a direct `anthropic.AsyncAnthropic().messages.create()` call — NOT via FlowManager (torn down)
3. Model: verify `claude-haiku-4-5` at build time (tagged `[ASSUMED]` in research)
4. Wrap in try/except; on failure return a safe fallback string — do NOT log the transcript contents (PII)
5. API key from `os.getenv("ANTHROPIC_API_KEY")` only

---

### `src/bot.py` *(modified — entrypoint, request-response)*

**Analog (base to extend):** `src/bot.py` itself

**FlowManager constructor to extend** (bot.py lines 101–106):
```python
    flow_manager = FlowManager(
        llm=llm,
        context_aggregator=aggregators,
        worker=worker,
        # Phase 3 ADD: global_functions=[build_transfer_schema()]
    )
```

**Event handler registration pattern** (bot.py lines 310–321):
```python
    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(transport_obj, client):
        # Only save draft if booking is in progress and not yet confirmed (D-18)
        if (
            flow_manager.state.get("booking_slot")
            and not flow_manager.state.get("confirmed_event_id")
        ):
            handler = make_abandonment_handler(
                flow_manager, reservation_repo, calendar_provider
            )
            await handler()
```

**runner.run() wrap pattern** (bot.py lines 327–329) — Phase 3 wraps in try/finally:
```python
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
    # Phase 3 ADD: try/finally block here — see Pattern 5 in RESEARCH.md
```

**Watchdog wiring** — after `setup_flow()` returns, register event handlers on `build.aggregators.user()`:
```python
    @build.aggregators.user().event_handler("on_user_turn_idle")
    async def _on_user_turn_idle(aggregator):
        await dead_air_handler.on_idle(aggregator)

    @build.aggregators.user().event_handler("on_user_turn_started")
    async def _on_user_turn_started(aggregator, strategy):
        dead_air_handler.reset()
```

**Circular dependency pattern for observer** (bot.py lines 246–268):
```python
    error_observer = ErrorFallbackObserver(worker=None)  # patched below
    worker = PipelineWorker(
        pipeline,
        observers=[latency_observer, error_observer],
        ...
    )
    error_observer.worker = worker  # resolve circular reference
```
`ErrorFallbackObserver` in Phase 3 also needs `flow_manager` reference (for escalation state). Patch `error_observer.flow_manager = flow_manager` after `flow_manager` is created.

---

### `src/pipeline/build.py` *(modified — config/utility, request-response)*

**Analog (base to extend):** `src/pipeline/build.py` itself

**Pipeline assembly to change** (build.py lines 109–117):
```python
    pipeline = Pipeline([
        transport.input(),
        stt,                      # Phase 3: replace with stt_switcher
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])
```

**Aggregator construction to extend** (build.py lines 101–104):
```python
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=build_user_aggregator_params(),
        # Phase 3: build_user_aggregator_params() must accept user_idle_timeout=T1
    )
```

**STT provider call to replace** (build.py lines 80–81):
```python
    stt_provider = get_stt_provider(os.getenv("STT_PROVIDER", "deepgram"))
    stt = stt_provider.create_service()
    # Phase 3: replace with build_stt_switcher() from stt_switcher.py
```

---

### `src/pipeline/fallback.py` *(modified — middleware/observer, event-driven)*

**Analog (base to extend):** `src/pipeline/fallback.py` itself

**Existing retry-slot logic** (fallback.py lines 54–81):
```python
    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if not isinstance(frame, ErrorFrame):
            return
        if frame.fatal:
            return
        # Sanitized source name only — never log the error string (V7 / T-03-LOG).
        src_name: str = getattr(data.source, "name", "unknown-service") or "unknown-service"
        count = self._retry_counts.get(src_name, 0)
        if count < 1:
            self._retry_counts[src_name] = count + 1
        else:
            self._retry_counts[src_name] = 0
            await self.worker.queue_frames(
                [TTSSpeakFrame(text=COURTESY_PHRASE, append_to_context=False)]
            )
```

Phase 3 extends `__init__` with:
- `self.flow_manager = None` (set by bot.py after FlowManager creation)
- `self._escalated: bool = False`
- `_ESCALATION_THRESHOLD = 3` (module-level constant)

After the retry-slot block, add escalation:
```python
        # Phase 3 addition — after retry slot exhausted, track escalation
        # (src_name counter already reset to 0 above)
        # escalation_count is separate from _retry_counts
        esc_count = self._escalation_counts.get(src_name, 0) + 1
        self._escalation_counts[src_name] = esc_count
        if esc_count >= _ESCALATION_THRESHOLD and not self._escalated:
            self._escalated = True
            if self.flow_manager is not None:
                self.flow_manager.state["outcome"] = "fallito"
            await self.worker.queue_frames([
                TTSSpeakFrame(
                    text="Mi scusi, sto riscontrando problemi tecnici. La trasferisco a un operatore.",
                    append_to_context=False,
                ),
                EndWorkerFrame(),
            ])
```

Security: `ErrorFrame.error` is NEVER logged — this constraint is in lines 11–16 and must be preserved in all extensions.

---

### `src/flows/functions.py` *(modified — service, event-driven)*

**Analog (base to extend):** `src/flows/functions.py` itself

**FlowsFunctionSchema builder pattern** (functions.py lines 86–125):
```python
def build_collect_booking_schema() -> FlowsFunctionSchema:
    return FlowsFunctionSchema(
        name="collect_booking_info",
        description="...",
        properties={
            "field_name": {
                "type": "string",
                "description": "...",
            },
        },
        required=["field_name"],
        handler=handle_collect_booking_info,
    )
```

**Handler signature and return convention** (functions.py lines 183–221):
```python
async def handle_collect_booking_info(args: dict, fm) -> tuple[dict, None]:
    """..."""
    # Read from fm.state — NEVER from args for tenant-scoped values (T-02-06)
    tenant: TenantConfig | None = fm.state.get("tenant")
    tenant_id: str = fm.state.get("tenant_id", "")
    # ...
    return {"collected": True, "readback": readback}, None  # None = stay in current node
```

`build_transfer_schema()` + `handle_transfer_call()` follow this exact pattern.

**Security constraint for transfer handler** — critical difference from other handlers (T-injection):
```python
async def handle_transfer_call(args: dict, fm) -> tuple[dict, None]:
    # NEVER read transfer_number from args — only from trusted tenant config
    tenant = fm.state.get("tenant")
    transfer_number = (tenant.transfer_number if tenant else None) or "operatore"
    # args["reason"] is safe (logged only, no routing use)
    reason = args.get("reason", "richiesta_cliente")
```

**FAQ handler extension** — in `handle_faq_lookup()`, on the `found=False` branch, set a state flag:
```python
    # Phase 3: signal that transfer offer should be made (D-03 / D-08)
    fm.state["faq_transfer_offered"] = True
    return {"found": False, "offer_transfer": True}, None
```

---

### `src/flows/nodes.py` *(modified — config, event-driven)*

**Analog (base to extend):** `src/flows/nodes.py` itself

**Node builder pattern** (nodes.py lines 30–68):
```python
def build_greeting_node(tenant: TenantConfig) -> dict:
    from src.flows.functions import (
        build_route_to_faq_schema,
        build_route_to_booking_schema,
    )
    return {
        "name": "greeting",
        "role_message": "...",
        "task_messages": [{"role": "user", "content": "..."}],
        "functions": [
            build_route_to_faq_schema(),
            build_route_to_booking_schema(),
        ],
    }
```

**FAQ node `role_message` to extend** (nodes.py lines 155–165):
```python
        "role_message": (
            f"Sei la receptionist di {business_name}. "
            "...REGOLA DI GROUNDING (FAQ-02)... "
            "Se lo strumento restituisce found=false, ammetti onestamente di non avere "
            "quella informazione e offri di prendere nota: "
            "'Non ho questa informazione al momento, posso prendere nota e farla ricontattare.' "
            "Non inventare mai dati (D-08)."
            # Phase 3: add after the above line:
            # "Oppure, se il cliente preferisce, puoi proporgli di parlare con un operatore: "
            # "usa lo strumento transfer_call con reason='fuori_ambito'."
        ),
```

`global_functions` is wired in `bot.py`, NOT in node builders — nodes do not need to import the transfer schema.

---

### `src/db/schema.sql` *(modified — migration, CRUD)*

**Analog (base to extend):** `src/db/schema.sql` itself

**Existing table/index pattern** (schema.sql lines 38–53):
```sql
CREATE TABLE IF NOT EXISTS reservations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       TEXT NOT NULL REFERENCES tenants(id),
    slot_date       TEXT NOT NULL,
    slot_time       TEXT NOT NULL,
    covers          INTEGER NOT NULL CHECK(covers > 0),
    name            TEXT NOT NULL,
    phone           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'bozza' CHECK(status IN ('confermata', 'bozza')),
    google_event_id TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_res_slot ON reservations(tenant_id, slot_date, slot_time, status);
```

`call_logs` follows this exact pattern: `IF NOT EXISTS`, all FKs with `REFERENCES`, a `CHECK` constraint on `outcome` for the five-value taxonomy (D-06), `TEXT NOT NULL DEFAULT (datetime('now'))` for timestamps, `INDEX IF NOT EXISTS`. Full schema from RESEARCH.md §call_logs Schema is the authoritative spec.

---

### Test Files

**Analog for all new test files:** `tests/test_observers.py` and `tests/test_repository.py`

**Async test function declaration pattern** (test_observers.py):
```python
import pytest

async def test_error_fallback_courtesy_phrase(tmp_path):
    """REL-01: second ErrorFrame from same source → courtesy phrase queued."""
    from src.pipeline.fallback import ErrorFallbackObserver
    ...
```

**pytest.ini_options** — all test files use `pytest-asyncio` (already configured in `pyproject.toml`). No `@pytest.mark.asyncio` needed on each test if `asyncio_mode = "auto"` is set.

**Fake frame/observer stubs pattern** (test_observers.py lines 20–35):
```python
@dataclass
class _FakeProcessor:
    """Minimal FrameProcessor stand-in whose .name is a plain string."""
    name: str


@dataclass
class _FakeFramePushed:
    """FramePushed stand-in."""
    source: _FakeProcessor
    frame: object
    destination: object = None
    direction: object = None
    timestamp: int = 0
```
Copy this pattern into `test_transfer.py`, `test_watchdog.py`, `test_fallback.py`, `test_stt_switcher.py`.

**tmp_path + init_db fixture pattern** (test_repository.py lines 39–47, conftest.py lines 33–39):
```python
@pytest.fixture
async def repo(tmp_path) -> TenantRepository:
    """An initialised (empty) TenantRepository backed by a temp-file DB."""
    db_path = str(tmp_path / "centralino_test.db")
    r = TenantRepository(db_path=db_path)
    await r.init_db()
    return r
```
`test_call_log.py` uses the same pattern with `CallLogRepository`.

**Mock pattern** (conftest.py lines 50–55):
```python
@pytest.fixture
def mock_stt() -> MagicMock:
    m = MagicMock(name="MockSTTService")
    m.model = "nova-2"
    m.language = "it"
    return m
```
`test_summary.py` mocks `anthropic.AsyncAnthropic` using `AsyncMock`.

---

## Shared Patterns

### Import Header (all new modules)
**Source:** `src/flows/functions.py` lines 1–3 and `src/pipeline/fallback.py` lines 1–3
```python
from __future__ import annotations
```
Always present. All new modules start with this.

### Loguru Logging (not stdlib logging)
**Source:** `src/flows/functions.py` line 28, `src/pipeline/observers.py` line 42
```python
from loguru import logger
```
Use `loguru.logger` exclusively. Never `import logging`.

### Security: No PII in Logs
**Source:** `src/flows/functions.py` lines 333–340, `src/pipeline/fallback.py` lines 11–16
**Apply to:** `src/call_log/summary.py`, all `src/notifications/*.py`, `src/pipeline/fallback.py` (extended)
- Exception handlers log `type(exc).__name__` and safe message only
- Never log `transcript_json`, `name`, `phone`, `body` (notification body), `ErrorFrame.error`
- `tenant_id` is safe to log; caller data is not

### Security: Parameterized SQL Only
**Source:** `src/booking/repository.py` docstring lines 1–9, `src/config/repository.py` lines 8–9
**Apply to:** `src/call_log/repository.py`
```python
# T-01-SQLI: every query is parameterized — `WHERE id = ?` with a tuple param.
# Never f-string/format user-supplied data into SQL.
```

### Security: API Keys via os.getenv Only
**Source:** `src/pipeline/factory.py` lines 9–10, `src/pipeline/build.py` lines 13–14
**Apply to:** all new `src/notifications/*.py`, `src/pipeline/stt_switcher.py`, `src/call_log/summary.py`
```python
# Security (T-02-KEY): API keys read only via `os.getenv`; never logged.
api_key=os.getenv("ANTHROPIC_API_KEY"),
```

### Seam Pattern (interface + concrete impl in separate files)
**Source:** `src/interfaces/notification_channel.py` + `src/calendar/memory_provider.py`
**Apply to:** `src/telephony/base.py` + `src/telephony/stub.py`, `src/notifications/*.py`
- ABC in `interfaces/` or new package `base.py`
- Concrete impls import only the ABC; never each other
- Factory (`factory.py`) imports all concrete impls

### Pydantic Settings Style (NOT flat kwargs)
**Source:** `src/pipeline/factory.py` lines 60–76 (DeepgramProvider)
```python
return DeepgramSTTService(
    api_key=os.getenv("DEEPGRAM_API_KEY"),
    settings=DeepgramSTTService.Settings(
        model=model,
        language="it",
        ...
    ),
)
```
`LazyWhisperSTTService` must use `settings=WhisperSTTService.Settings(...)` — never flat kwargs (CLAUDE.md "What NOT to Use").

### Observer pattern (`BaseObserver`)
**Source:** `src/pipeline/fallback.py` lines 27–81
```python
from pipecat.observers.base_observer import BaseObserver, FramePushed

class ErrorFallbackObserver(BaseObserver):
    def __init__(self, worker) -> None:
        super().__init__()
        self.worker = worker

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        ...
```
Any new observer (e.g. watchdog implemented as observer) must follow this pattern.

---

## No Analog Found

All files have analogs within the codebase. No files require falling back to RESEARCH.md patterns as the sole reference.

---

## Metadata

**Analog search scope:** `src/` (all Python modules), `tests/`, `src/db/schema.sql`
**Files scanned:** 22 source files + 14 test files + 1 SQL file
**Pattern extraction date:** 2026-06-27
