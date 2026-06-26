# Phase 2: Booking + Calendar + FAQ - Pattern Map

**Mapped:** 2026-06-25
**Files analyzed:** 14 new/modified files
**Analogs found:** 12 / 14 (2 have no close codebase analog — use RESEARCH.md patterns)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/db/schema.sql` | config | batch | `src/db/schema.sql` itself | self (extend) |
| `src/config/tenant_config.py` | model | CRUD | `src/config/tenant_config.py` itself | self (extend) |
| `src/config/repository.py` | repository | CRUD | `src/config/repository.py` itself | self (extend) |
| `src/interfaces/calendar_provider.py` | interface | request-response | `src/interfaces/notification_channel.py` | role-match |
| `src/calendar/google_provider.py` | service | request-response | `src/pipeline/factory.py` (STTProvider/DeepgramProvider) | role-match |
| `src/calendar/memory_provider.py` | service | request-response | `src/interfaces/notification_channel.py` (stub ABC) | role-match |
| `src/booking/repository.py` | repository | CRUD | `src/config/repository.py` | exact |
| `src/booking/date_parser.py` | utility | transform | none | no analog |
| `src/kb/fts.py` | service | CRUD | `src/config/repository.py` (aiosqlite + parameterized SQL) | data-flow-match |
| `src/kb/ingest.py` | utility | batch | `src/db/seed_demo.py` | role-match |
| `src/flows/nodes.py` | service | event-driven | `src/pipeline/build.py` (pipeline assembly) | data-flow-match |
| `src/flows/functions.py` | service | event-driven | `src/pipeline/fallback.py` (async frame handlers) | partial-match |
| `src/pipeline/build.py` | service | event-driven | `src/pipeline/build.py` itself | self (extend) |
| `src/db/seed_demo.py` | utility | batch | `src/db/seed_demo.py` itself | self (extend) |

---

## Pattern Assignments

### `src/db/schema.sql` (config — extend)

**Analog:** `src/db/schema.sql` (self)

**Current pattern** (lines 1-19) — extend this file, do not replace it:
```sql
-- Tenant configuration schema (D-02: full nullable-aware schema from day 1).
-- Phase 1 populates only the voice-relevant fields; no ALTER TABLE per phase.
-- Structured for a clean Postgres migration (connection-string swap only) — D-01.

CREATE TABLE IF NOT EXISTS tenants (
    id              TEXT PRIMARY KEY,
    business_name   TEXT NOT NULL,
    ...
    kb_ref          TEXT,
    notification_channel TEXT
);
```

**Phase 2 additions to copy into the file:**
- Add `calendar_id TEXT` column to `tenants` CREATE TABLE definition (D-11). Because the dev DB already exists from Phase 1, also emit `ALTER TABLE tenants ADD COLUMN calendar_id TEXT;` wrapped in a migration comment (RESEARCH.md Pitfall 5: ALTER on existing table with column present throws; document the "delete DB and re-seed" dev path).
- Append `reservations` table with columns: `id`, `tenant_id` (FK→tenants), `slot_date` (TEXT ISO date), `slot_time` (TEXT HH:MM), `covers` (INTEGER NOT NULL CHECK >0), `name`, `phone`, `status` (TEXT DEFAULT 'bozza', CHECK IN ('confermata','bozza')), `google_event_id` (nullable), `notes` (nullable), `created_at` (DEFAULT datetime('now')).
- Append `CREATE INDEX IF NOT EXISTS idx_res_slot ON reservations(tenant_id, slot_date, slot_time, status)`.
- Append `kb_documents` table: `id`, `tenant_id`, `filename`, `ingested_at`.
- Append `CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks USING fts5(tenant_id UNINDEXED, doc_id UNINDEXED, chunk_id UNINDEXED, content, tokenize = "unicode61")`. Note: FTS5 virtual tables have NO PRIMARY KEY, UNIQUE, or external indexes (RESEARCH.md Pitfall 6 / §Schema note).

---

### `src/config/tenant_config.py` (model — extend)

**Analog:** `src/config/tenant_config.py` (self)

**Current import + class pattern** (lines 1-52) — copy the exact style:
```python
"""Typed tenant configuration model (D-03)."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, field_validator

class TenantConfig(BaseModel):
    """Fields mirror the `tenants` SQLite table 1:1 so a row can be unpacked:
       TenantConfig(**dict(row))
    """
    id: str
    ...
    kb_ref: Optional[str] = None
    notification_channel: Optional[str] = None

    @field_validator("voice_id")
    @classmethod
    def _voice_id_must_be_non_empty(cls, v: str) -> str:
        ...
```

**Phase 2 addition — single new field** (after `kb_ref`):
```python
    kb_ref: Optional[str] = None
    notification_channel: Optional[str] = None
    calendar_id: Optional[str] = None  # Google Calendar id for this tenant (D-11)
```

No validator needed (nullable, no format constraint in v1). The 1:1 mapping means `TenantConfig(**dict(row))` will pick up `calendar_id` automatically once the column exists in the DB.

---

### `src/config/repository.py` (repository — extend for upsert)

**Analog:** `src/config/repository.py` (self, exact)

**Pattern to replicate** — the `upsert_tenant` INSERT OR REPLACE must be updated to include `calendar_id` in both the column list and the VALUES tuple. Copy the exact style of the existing method (lines 53-80):

```python
async def upsert_tenant(self, tenant: TenantConfig) -> None:
    async with aiosqlite.connect(self._db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO tenants (
                id, business_name, greeting, voice_id, language, system_prompt,
                model, hours, services, booking_rules, transfer_number,
                kb_ref, notification_channel, calendar_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant.id, tenant.business_name, tenant.greeting, tenant.voice_id,
                tenant.language, tenant.system_prompt, tenant.model, tenant.hours,
                tenant.services, tenant.booking_rules, tenant.transfer_number,
                tenant.kb_ref, tenant.notification_channel, tenant.calendar_id,
            ),
        )
        await db.commit()
```

Also update `table_columns` test reference (EXPECTED_COLUMNS in `tests/test_repository.py`) to add `"calendar_id"`.

---

### `src/interfaces/calendar_provider.py` (interface — extend)

**Analog:** `src/interfaces/notification_channel.py` (role-match, same ABC stub pattern)

**Existing notification_channel pattern** (lines 1-19):
```python
"""NotificationChannel interface seam (Phase 3 — end-of-call summary dispatch).
...
"""
from __future__ import annotations
from abc import ABC, abstractmethod

class NotificationChannel(ABC):
    """A per-tenant outbound notification channel (Phase 3 seam)."""

    @abstractmethod
    async def send(self, subject: str, body: str) -> None:
        """Deliver a notification..."""
        raise NotImplementedError
```

**Current `calendar_provider.py` stub** (lines 1-31) already follows this pattern; Phase 2 extends the signatures to include `tenant_id`:

```python
# EXTEND check_availability and create_event signatures to add tenant_id:
@abstractmethod
async def check_availability(
    self, tenant_id: str, start: datetime, end: datetime
) -> bool:
    """Return True if the [start, end) window is free for this tenant."""
    raise NotImplementedError

@abstractmethod
async def create_event(
    self,
    tenant_id: str,
    start: datetime,
    end: datetime,
    title: str,
    details: str | None = None,
) -> str:
    """Create a calendar event and return its provider event id."""
    raise NotImplementedError
```

---

### `src/calendar/google_provider.py` (service, request-response)

**Analog:** `src/pipeline/factory.py` — `DeepgramProvider` class (lines 51-68), same pattern: ABC implementation behind an interface, `os.getenv` for keys, `settings=` style config, docstring with pitfall notes.

**Imports pattern** (copy from factory.py):
```python
from __future__ import annotations
import asyncio
import os
from functools import partial
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from google.oauth2 import service_account

from src.interfaces.calendar_provider import CalendarProvider
from src.config.tenant_config import TenantConfig
```

**Interface implementation pattern** (copy ABC + os.getenv style from DeepgramProvider):
```python
class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar backend using a single global service account (D-09/D-12)."""

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self) -> None:
        # Security (T-02-KEY): credential path via env only; never logged.
        cred_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not cred_path:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON env var not set")
        credentials = service_account.Credentials.from_service_account_file(
            cred_path, scopes=self.SCOPES
        )
        self._service = build("calendar", "v3", credentials=credentials)

    async def check_availability(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> bool:
        # NOTE: this is SECONDARY to the DB transactional check (Pitfall 7).
        # freebusy is for display only — never use as authoritative capacity gate.
        ...

    async def create_event(
        self, tenant_id: str, start: datetime, end: datetime,
        title: str, details: str | None = None
    ) -> str:
        # CRITICAL: wrap blocking Google API call in run_in_executor (RESEARCH §Pitfall 4)
        loop = asyncio.get_running_loop()
        body = {
            "summary": title,
            "description": details or "",
            "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Rome"},
            "end":   {"dateTime": end.isoformat(),   "timeZone": "Europe/Rome"},
        }
        result = await loop.run_in_executor(
            None,
            partial(self._service.events().insert(
                calendarId=tenant_config.calendar_id, body=body
            ).execute)
        )
        return result["id"]  # real event_id — drives Flows gating (BOOK-05)
```

**Error handling pattern** (copy from factory.py and fallback.py): raise domain exceptions (ValueError) for missing config; let Google API exceptions propagate to the handler in `src/flows/functions.py` where they are caught and return `{"error": ..., "available": False}, None` (stays in booking node).

---

### `src/calendar/memory_provider.py` (service, request-response)

**Analog:** `src/interfaces/notification_channel.py` (role-match — minimal ABC implementation)

**Pattern:** Minimal in-memory implementation behind the same interface for tests. Copy the ABC implementation style:

```python
from __future__ import annotations
from datetime import datetime
from src.interfaces.calendar_provider import CalendarProvider

class InMemoryCalendarProvider(CalendarProvider):
    """In-memory CalendarProvider for tests (D-12). No real network calls."""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._next_id: int = 1

    async def check_availability(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> bool:
        for ev in self._events:
            if ev["tenant_id"] == tenant_id and ev["start"] < end and ev["end"] > start:
                return False
        return True

    async def create_event(
        self, tenant_id: str, start: datetime, end: datetime,
        title: str, details: str | None = None
    ) -> str:
        event_id = f"mem-{self._next_id}"
        self._next_id += 1
        self._events.append({
            "tenant_id": tenant_id, "start": start, "end": end,
            "title": title, "details": details, "id": event_id,
        })
        return event_id
```

---

### `src/booking/repository.py` (repository, CRUD)

**Analog:** `src/config/repository.py` — **exact match**: same `aiosqlite` pattern, same `_SCHEMA_PATH` sentinel, same `async with aiosqlite.connect()` per-method context manager, same parameterized SQL style.

**Imports pattern** (lines 1-18 of `src/config/repository.py`):
```python
"""Async SQLite repository for reservations (D-22).

Security (T-01-SQLI): tenant_id reaches the DB from call-session context;
every query is parameterized — never f-string/format into SQL.
"""
from __future__ import annotations
from pathlib import Path
import aiosqlite

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
```

**Class skeleton** (copy `TenantRepository` style):
```python
class ReservationRepository:
    """Persistence for reservations — check-and-insert + status transitions (D-22)."""

    def __init__(self, db_path: str = "centralino.db") -> None:
        self._db_path = db_path
```

**Core CRUD pattern — check-and-insert** (copy `async with aiosqlite.connect()` + `BEGIN IMMEDIATE` from RESEARCH.md §Pattern 3):
```python
    async def try_reserve_slot(
        self, tenant_id: str, slot_date: str, slot_time: str,
        covers: int, name: str, phone: str, limit: int,
        notes: str | None = None,
    ) -> tuple[bool, int | None]:
        """Atomically check capacity and insert draft reservation (BEGIN IMMEDIATE).
        Returns (success, reservation_id | None).
        Uses BEGIN IMMEDIATE to prevent double-booking race (PITFALL 7, SC3).
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                async with db.execute(
                    """SELECT COALESCE(SUM(covers), 0) FROM reservations
                       WHERE tenant_id = ? AND slot_date = ? AND slot_time = ?
                       AND status = 'confermata'""",
                    (tenant_id, slot_date, slot_time),
                ) as cur:
                    row = await cur.fetchone()
                current_covers = row[0] if row else 0
                if current_covers + covers > limit:
                    await db.execute("ROLLBACK")
                    return False, None
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

**Status-update pattern** (copy the parameterized `UPDATE` from `upsert_tenant`):
```python
    async def confirm_reservation(
        self, reservation_id: int, google_event_id: str
    ) -> None:
        """Update draft→confirmed once Calendar write succeeds (BOOK-05 gating)."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE reservations SET status='confermata', google_event_id=?"
                " WHERE id=? AND status='bozza'",
                (google_event_id, reservation_id),
            )
            await db.commit()
```

**Alternative slot query** (same aiosqlite pattern, pure SELECT):
```python
    async def find_available_slots(
        self, tenant_id: str, slot_date: str, limit_per_slot: int, count: int = 3
    ) -> list[str]:
        """Find up to `count` slot_times on slot_date with remaining capacity (D-04)."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                """SELECT slot_time, COALESCE(SUM(covers), 0) as booked
                   FROM reservations
                   WHERE tenant_id=? AND slot_date=? AND status='confermata'
                   GROUP BY slot_time
                   HAVING booked < ?
                   ORDER BY slot_time
                   LIMIT ?""",
                (tenant_id, slot_date, limit_per_slot, count),
            ) as cur:
                rows = await cur.fetchall()
        return [r[0] for r in rows]
```

---

### `src/booking/date_parser.py` (utility, transform)

**Analog:** None in codebase. Use RESEARCH.md §Pattern 5 directly.

**Pattern from RESEARCH.md** (Pattern 5 — copy verbatim):
```python
"""Italian date/time parsing for the booking flow (D-16).

Uses `dateparser` 1.4.1 with Italian locale.
PITFALL 7 (RESEARCH.md): always pass RETURN_AS_TIMEZONE_AWARE=True + TIMEZONE=Europe/Rome
or returned datetime will be naive and bookings shift by 1-2h across DST.

Security: user text goes through dateparser, not eval/exec — no injection risk.
"""
from __future__ import annotations
from datetime import datetime
import dateparser
from zoneinfo import ZoneInfo

ROME_TZ = ZoneInfo("Europe/Rome")

PARSE_SETTINGS = {
    "LANGUAGES": ["it"],
    "TIMEZONE": "Europe/Rome",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PREFER_DATES_FROM": "future",
    "PREFER_DAY_OF_MONTH": "first",
}

def parse_italian_date(text: str) -> datetime | None:
    """Parse Italian natural language date/time to a timezone-aware datetime.

    Returns None if the text cannot be parsed (caller should prompt user to rephrase).
    Import at module level (not inside handler) to amortize cold-start latency (RESEARCH §OQ4).
    """
    result = dateparser.parse(text, settings=PARSE_SETTINGS)
    return result  # timezone-aware Europe/Rome, or None
```

---

### `src/kb/fts.py` (service, CRUD)

**Analog:** `src/config/repository.py` (data-flow-match: same `aiosqlite` + parameterized SQL, same `async with aiosqlite.connect()` per-method pattern).

**Imports pattern** (copy from `src/config/repository.py` lines 1-18):
```python
"""SQLite FTS5 knowledge-base retrieval (D-07, FAQ-01, FAQ-03).

Security (T-01-SQLI): all queries use parameterized MATCH ? — never f-string user text
into FTS5 SQL. FTS5 sanitizes the bound parameter (RESEARCH §Pitfall 6).
"""
from __future__ import annotations
import aiosqlite
```

**Core query pattern** (copy `async with aiosqlite.connect()` + `async with db.execute()` from `TenantRepository.get_tenant`, lines 43-51):
```python
class SQLiteFTSKnowledgeBase:
    def __init__(self, db_path: str = "centralino.db") -> None:
        self._db_path = db_path

    async def search(
        self, tenant_id: str, query: str, top_k: int = 3
    ) -> list[str]:
        """Return top-k text chunks matching query for this tenant (FAQ-03: tenant-scoped).

        Returns empty list when no chunks match (FAQ-02: caller handles not-found case).
        """
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                """SELECT content FROM kb_chunks
                   WHERE tenant_id = ? AND kb_chunks MATCH ?
                   ORDER BY rank LIMIT ?""",
                (tenant_id, query, top_k),
            ) as cur:
                rows = await cur.fetchall()
        return [r[0] for r in rows]
```

---

### `src/kb/ingest.py` (utility, batch)

**Analog:** `src/db/seed_demo.py` (role-match: same async batch-write pattern, `asyncio.run(_main())`, `repo.init_db()` guard, `await db.executemany()` for bulk insert).

**Pattern from `src/db/seed_demo.py`** (lines 55-78):
```python
async def seed_demo_tenant(repo: TenantRepository) -> TenantConfig:
    """Insert (or replace) the demo tenant into the given repository."""
    tenant = build_demo_tenant()
    await repo.upsert_tenant(tenant)
    return tenant

async def _main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    repo = TenantRepository()
    await repo.init_db()
    ...

if __name__ == "__main__":
    asyncio.run(_main())
```

**Phase 2 ingest pattern:**
```python
"""KB ingest — load data/tenants/<slug>/kb/*.txt → kb_chunks FTS5 (D-07).

Run standalone to (re-)ingest a tenant's KB:
    python -m src.kb.ingest --tenant=demo_trattoria
"""
from __future__ import annotations
import asyncio
import os
import aiosqlite

async def ingest_kb_files(
    db_path: str, tenant_id: str, kb_dir: str, chunk_size: int = 300
) -> int:
    """Read .txt files from kb_dir, split, insert into kb_chunks. Returns chunk count."""
    chunks = []
    for fname in os.listdir(kb_dir):
        if not fname.endswith(".txt"):
            continue
        text = open(os.path.join(kb_dir, fname), encoding="utf-8").read()
        for i, chunk in enumerate(_split_into_chunks(text, chunk_size)):
            chunks.append((tenant_id, fname, str(i), chunk))
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT INTO kb_chunks(tenant_id, doc_id, chunk_id, content) VALUES (?,?,?,?)",
            chunks,
        )
        await db.commit()
    return len(chunks)
```

---

### `src/flows/nodes.py` (service, event-driven)

**Analog:** `src/pipeline/build.py` (data-flow-match: assembles Pipecat components, returns a structured object, uses per-tenant config, follows the same import style from pipecat packages).

**Imports pattern** (copy `from __future__ import annotations` + pipecat imports style from `build.py` lines 1-36):
```python
"""Pipecat Flows node builders — greeting / booking / faq / end nodes (D-13).

Each builder returns a NodeConfig dict. Nodes expose only the tools they need
(greeting: none; booking: collect + confirm; faq: faq_lookup; end: none).

CRITICAL (from RESEARCH.md §Pattern 1, verified against pipecat_flows 1.3.0 source):
- NodeConfig uses `role_message` (str), NOT deprecated `role_messages` (list)
- `functions` list contains FlowsFunctionSchema instances from src/flows/functions.py
- `respond_immediately=True` (default) — LLM runs as soon as node is set
"""
from __future__ import annotations
from pipecat_flows import FlowsFunctionSchema, NodeConfig
from src.config.tenant_config import TenantConfig
```

**Assembly pattern** (copy `build_pipeline` function structure from `build.py` lines 39-98 — function that takes config and returns a structured object):
```python
def build_greeting_node(tenant: TenantConfig) -> NodeConfig:
    """Opening node — no booking tools exposed; LLM greets + routes to booking or faq."""
    return {
        "name": "greeting",
        "role_message": (
            f"Sei la receptionist di {tenant.business_name}. "
            "Dai del Lei. Parla in italiano naturale. Risposte brevi."
        ),
        "task_messages": [
            {
                "role": "user",
                "content": (
                    "Accogli il cliente e chiedi come puoi aiutarlo. "
                    "Se vuole prenotare, usa collect_booking_info. "
                    "Se fa domande, usa faq_lookup."
                )
            }
        ],
        "functions": [],  # no tools at greeting — prevents stray tool calls
    }

def build_booking_node(tenant: TenantConfig) -> NodeConfig:
    """Booking data-collection node (D-13). Only booking tools exposed."""
    from src.flows.functions import (
        build_collect_booking_schema, build_confirm_booking_schema
    )
    return {
        "name": "booking",
        "role_message": (
            f"Sei la receptionist di {tenant.business_name}. Stai raccogliendo "
            "i dati per una prenotazione. Dai del Lei. Risposte brevi. "
            "Non confermare mai una prenotazione senza il risultato dello strumento."
        ),
        "task_messages": [
            {
                "role": "user",
                "content": (
                    "Raccogli data, ora, numero persone, nome e telefono. "
                    "Dopo aver raccolto tutti i dati, rileggili per conferma. "
                    "Rileggi il numero cifra per cifra. "
                    "Solo dopo conferma vocale, chiama confirm_booking."
                )
            }
        ],
        "functions": [
            build_collect_booking_schema(),
            build_confirm_booking_schema(),
        ],
    }
```

**Per-node model override** (add `pre_actions` to booking node — RESEARCH.md §Pattern 2, Option B):
```python
        "pre_actions": [{"type": "switch_llm_to_sonnet"}],
        # Handled by a registered pre_action handler in setup_flow (functions.py)
```

---

### `src/flows/functions.py` (service, event-driven)

**Analog:** `src/pipeline/fallback.py` (partial-match: same `async def handler(...)` pattern, same try/except error handling, same `worker.queue_frames` async call style).

**Error handling pattern** (copy from `fallback.py` lines 54-81):
```python
# Pattern: early return on non-actionable case; use domain exceptions not raw Exception
# Pattern: never log secrets or user PII in except clauses
try:
    event_id = await calendar_provider.create_event(...)
except Exception:
    # Calendar unavailable — stay in booking node, let LLM offer to retry
    return {"available": False, "error": "calendario non disponibile"}, None
```

**Handler signature pattern** (RESEARCH.md §Pattern 1, verified from pipecat_flows 1.3.0 source):
```python
from pipecat_flows import FlowArgs, FlowManager, FlowsFunctionSchema

async def handle_collect_booking_info(args: FlowArgs, fm: FlowManager):
    """Store booking fields in flow_manager.state (BOOK-01)."""
    fm.state["booking_slot"] = {
        "date": args["date"],
        "time_slot": args["time_slot"],
        "covers": args["covers"],
    }
    fm.state["customer"] = {
        "name": args["name"],
        "phone": args["phone"],
    }
    # Stay in booking node to do read-back
    return {"collected": True}, None

async def handle_confirm_booking(args: FlowArgs, fm: FlowManager):
    """Capacity check → Calendar write → DB persist → transition to end node (BOOK-02..06)."""
    from src.flows.nodes import build_end_node
    slot = fm.state.get("booking_slot")
    customer = fm.state.get("customer")
    tenant: TenantConfig = fm.state.get("tenant")

    # 1. Capacity check in DB (authoritative — NOT Calendar, PITFALL 7)
    available, alternatives = await check_capacity(
        fm.state["db_path"], tenant, slot
    )
    if not available:
        return {"available": False, "alternatives": alternatives}, None

    # 2. Insert draft reservation (BEGIN IMMEDIATE, SC3)
    ok, res_id = await reservation_repo.try_reserve_slot(...)
    if not ok:
        return {"available": False, "error": "slot esaurito"}, None

    # 3. Write to Google Calendar (projection)
    try:
        event_id = await calendar_provider.create_event(
            tenant_id=tenant.id, start=slot_start, end=slot_end,
            title=f"Prenotazione - {customer['name']} ({slot['covers']}p)",
            details=f"Tel: {customer['phone']} | via Centralino AI",
        )
    except Exception:
        return {"available": False, "error": "calendario non disponibile"}, None

    # 4. Confirm in DB (only reached if Calendar write succeeded — BOOK-05 gating)
    await reservation_repo.confirm_reservation(res_id, event_id)
    fm.state["confirmed_event_id"] = event_id

    # 5. Transition to end node — spoken confirmation text lives ONLY there
    return {"event_id": event_id, "status": "confirmed"}, build_end_node()
```

**FlowsFunctionSchema builder** (RESEARCH.md §Pattern 1):
```python
def build_collect_booking_schema() -> FlowsFunctionSchema:
    return FlowsFunctionSchema(
        name="collect_booking_info",
        description="Salva i dati della prenotazione raccolti",
        properties={
            "date":      {"type": "string", "description": "Data ISO 8601"},
            "time_slot": {"type": "string", "description": "Ora HH:MM"},
            "covers":    {"type": "integer", "description": "Numero persone"},
            "name":      {"type": "string", "description": "Nome cliente"},
            "phone":     {"type": "string", "description": "Telefono cliente"},
        },
        required=["date", "time_slot", "covers", "name", "phone"],
        handler=handle_collect_booking_info,
    )
```

---

### `src/pipeline/build.py` (service, event-driven — extend)

**Analog:** `src/pipeline/build.py` (self)

**Current `build_pipeline` signature and return** (lines 39-98) stays intact. Phase 2 adds FlowManager initialization **after** the PipelineWorker starts (RESEARCH.md §Code Examples — `setup_flow`). The pipeline list itself does NOT change (no new processor added; FlowManager hooks into the existing `llm` and `context_aggregator` references).

**Phase 2 extension points** in `bot.py` (not `build.py`) — see `src/bot.py` pattern:
```python
# In bot.py, after worker creation:
from src.flows.nodes import build_greeting_node
from pipecat_flows import FlowManager

flow_manager = FlowManager(
    llm=llm,                     # the llm reference returned from build_pipeline
    context_aggregator=aggregators,  # the aggregators pair
    worker=worker,               # NOT deprecated 'task=' (RESEARCH.md §Anti-Patterns)
)
flow_manager.state["tenant_id"] = tenant.id
flow_manager.state["tenant"] = tenant
flow_manager.state["db_path"] = repo._db_path

initial_node = build_greeting_node(tenant)
await flow_manager.initialize(initial_node)
```

**Return value extension:** `build_pipeline` should return `(pipeline, context, llm, aggregators)` so `bot.py` can wire `FlowManager` without re-importing services. Alternatively, expose `llm` and `aggregators` as named attributes. The planner should choose the cleanest seam; the simplest is a `BuildResult` dataclass.

---

### `src/db/seed_demo.py` (utility, batch — extend)

**Analog:** `src/db/seed_demo.py` (self)

**Current build_demo_tenant pattern** (lines 41-52) — extend to add Phase 2 fields:
```python
def build_demo_tenant() -> TenantConfig:
    return TenantConfig(
        id="demo",
        ...,
        # Phase 2 additions (D-01, D-03, D-06, D-11):
        hours="12:00-15:00, 19:00-23:00",
        services="Cucina italiana, pizzeria, vini naturali",
        booking_rules='{"slot_duration_min": 30, "max_covers_per_slot": 40}',
        kb_ref="data/tenants/demo_trattoria/kb",
        calendar_id=os.getenv("GOOGLE_CALENDAR_ID_DEMO"),  # nullable in dev
    )
```

---

## Shared Patterns

### aiosqlite Repository Pattern
**Source:** `src/config/repository.py` (lines 24-91)
**Apply to:** `src/booking/repository.py`, `src/kb/fts.py`

```python
# Per-method connection (not a shared connection pool) — safe for concurrent
# async calls because SQLite file-level locking handles serialization.
async with aiosqlite.connect(self._db_path) as db:
    db.row_factory = aiosqlite.Row        # for dict-like row access when needed
    async with db.execute(
        "SELECT ... WHERE id = ?", (param,)  # ALWAYS parameterized
    ) as cursor:
        row = await cursor.fetchone()
    await db.commit()                      # only after write operations
```

### Parameterized SQL Security
**Source:** `src/config/repository.py` (lines 6-9) + `tests/test_repository.py` (lines 73-79)
**Apply to:** Every SQL-using module in Phase 2

```python
# Security (T-01-SQLI): every user-supplied value goes through ? parameter binding.
# Never f-string, .format(), or concatenate tenant_id, slot fields, or query text into SQL.
# Test verification pattern (copy from test_repository.py lines 73-79):
source = inspect.getsource(ReservationRepository)
assert "WHERE tenant_id = ?" in source
assert ".format(" not in source
assert 'f"SELECT' not in source
```

### ABC Interface Stub Pattern
**Source:** `src/interfaces/notification_channel.py` (lines 1-19) + `src/interfaces/calendar_provider.py` (lines 1-31)
**Apply to:** Any new protocol/interface defined in `src/interfaces/`

```python
from __future__ import annotations
from abc import ABC, abstractmethod

class SomeProvider(ABC):
    """Phase N seam — concrete implementations live in src/<domain>/."""

    @abstractmethod
    async def method(self, ...) -> ReturnType:
        """Docstring with what the implementation must guarantee."""
        raise NotImplementedError
```

### os.getenv Key Access
**Source:** `src/pipeline/build.py` (lines 64, 74) + `src/pipeline/factory.py` (lines 56, 147)
**Apply to:** `src/calendar/google_provider.py`, any module reading env vars

```python
# Security (T-02-KEY): API keys read only via os.getenv; never logged.
import os
api_key = os.getenv("SOME_API_KEY")   # returns None if absent — validate explicitly
cred_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not cred_path:
    raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON env var not set")
```

### Module-Level Docstring Convention
**Source:** Every existing source file
**Apply to:** Every new Phase 2 module

```python
"""One-line summary (requirement refs in parens).

Multi-line explanation if needed.

Security (<tag>): brief note on the security boundary this module owns.
"""
from __future__ import annotations
```

### pytest Fixture Pattern
**Source:** `tests/conftest.py` (lines 21-68)
**Apply to:** `tests/conftest.py` (extend), all new test files

```python
@pytest.fixture
async def repo(tmp_path) -> TenantRepository:
    """An initialised (empty) repository backed by a temp-file DB."""
    db_path = str(tmp_path / "centralino_test.db")
    r = TenantRepository(db_path=db_path)
    await r.init_db()
    return r
```

New fixtures to add to `tests/conftest.py`:
- `reservation_repo(tmp_path)` — same pattern as `repo`, returns `ReservationRepository`
- `kb_fts(tmp_path)` — returns `SQLiteFTSKnowledgeBase` with schema initialized
- `in_memory_calendar()` — returns `InMemoryCalendarProvider()`
- `seeded_kb(kb_fts, tmp_path)` — loads demo KB text files and ingests them

### Test File Structure
**Source:** `tests/test_repository.py` (lines 1-123)
**Apply to:** All new `tests/test_*.py` files

```python
"""Tests for <module> (<requirement refs>).

Covers:
- <bullet list of what is tested>
"""
import pytest
from src.<module> import SomeClass

@pytest.fixture
async def subject(tmp_path):
    ...

async def test_<behavior>(subject):
    """<req id>: one-sentence description."""
    result = await subject.method(...)
    assert result == expected
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/booking/date_parser.py` | utility | transform | No date-parsing utility exists in the codebase. Use RESEARCH.md §Pattern 5 (dateparser 1.4.1 with PARSE_SETTINGS verbatim). |
| `src/flows/nodes.py` / `src/flows/functions.py` | service | event-driven | No Pipecat Flows usage exists yet. Use RESEARCH.md §Pattern 1 (NodeConfig builders + FlowsFunctionSchema + handler signature) as the primary reference. The closest structural analog for the assembly pattern is `src/pipeline/build.py`. |

---

## Metadata

**Analog search scope:** `src/` (all 15 Python files + 1 SQL file read in full)
**Files scanned:** 16 source files, 7 test files
**Pattern extraction date:** 2026-06-25
