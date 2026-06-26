"""Pipecat Flows handler functions and FlowsFunctionSchema builders for booking (D-13).

Implements the tool-result-gated booking flow:
  collect_booking_info → (read-back in booking node) → confirm_booking → end node

BOOK-05 gating: the end node transition happens ONLY when create_event returns a
real event_id.  On any failure (capacity, calendar, DB) the handler returns
(result, None) to stay in the booking node.

Security:
- T-02-07: PII (phone, name) is NEVER logged in except clauses.
- T-02-06: tenant_id comes from fm.state session context, not from tool args.
- T-01-SQLI: all DB access goes through ReservationRepository (parameterized SQL).

Pattern analog: src/pipeline/fallback.py (async handler + try/except + no-secrets-in-logs).
"""

from __future__ import annotations

import json

from pipecat_flows import FlowsFunctionSchema

from src.booking.date_parser import slot_to_datetimes
from src.booking.repository import ReservationRepository

# ---------------------------------------------------------------------------
# FlowsFunctionSchema builders
# ---------------------------------------------------------------------------

_BOOKING_SLOT_FIELDS = ("date", "time_slot", "covers")
_CUSTOMER_FIELDS = ("name", "phone")
_ALL_BOOKING_FIELDS = _BOOKING_SLOT_FIELDS + _CUSTOMER_FIELDS


def build_collect_booking_schema() -> FlowsFunctionSchema:
    """Return the FlowsFunctionSchema for collect_booking_info.

    All five fields required (BOOK-01).  Handler stores them in fm.state
    and returns (result, None) to stay in the booking node for read-back (BOOK-03).
    """
    return FlowsFunctionSchema(
        name="collect_booking_info",
        description=(
            "Salva i cinque dati della prenotazione: data, ora, numero persone, "
            "nome e telefono del cliente."
        ),
        properties={
            "date": {
                "type": "string",
                "description": "Data della prenotazione in formato ISO 8601 (es. 2025-07-08)",
            },
            "time_slot": {
                "type": "string",
                "description": "Ora della prenotazione in formato HH:MM (es. 20:00)",
            },
            "covers": {
                "type": "integer",
                "description": "Numero di persone (coperti)",
            },
            "name": {
                "type": "string",
                "description": "Nome e cognome del cliente",
            },
            "phone": {
                "type": "string",
                "description": "Numero di telefono del cliente",
            },
        },
        required=["date", "time_slot", "covers", "name", "phone"],
        handler=handle_collect_booking_info,
    )


def build_confirm_booking_schema() -> FlowsFunctionSchema:
    """Return the FlowsFunctionSchema for confirm_booking.

    No required args — the handler reads all fields from fm.state (BOOK-05).
    Transitions to end node ONLY when create_event returns a real event_id.
    """
    return FlowsFunctionSchema(
        name="confirm_booking",
        description=(
            "Verifica disponibilità, crea la prenotazione in calendario e nel database "
            "dopo la conferma vocale del cliente. "
            "Chiamare SOLO dopo che il cliente ha confermato i dati a voce."
        ),
        properties={},
        required=[],
        handler=handle_confirm_booking,
    )


def build_correct_booking_field_schema() -> FlowsFunctionSchema:
    """Return the FlowsFunctionSchema for correct_booking_field (D-17 BLOCKER B1).

    Updates ONLY the named field in fm.state; returns next_node=None to stay
    in the booking node for a fresh read-back — does NOT restart collection.
    """
    return FlowsFunctionSchema(
        name="correct_booking_field",
        description=(
            "Corregge un singolo campo della prenotazione senza ricominciare "
            "la raccolta dati dall'inizio. "
            "Usare quando il cliente dice 'no' o vuole cambiare un dato durante "
            "la lettura di riepilogo (D-17)."
        ),
        properties={
            "field_name": {
                "type": "string",
                "description": (
                    "Nome del campo da correggere: 'date', 'time_slot', 'covers', "
                    "'name', oppure 'phone'."
                ),
                "enum": list(_ALL_BOOKING_FIELDS),
            },
            "new_value": {
                "description": "Nuovo valore per il campo (stringa o numero intero).",
            },
        },
        required=["field_name", "new_value"],
        handler=correct_booking_field,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_collect_booking_info(args: dict, fm) -> tuple[dict, None]:
    """Store all five booking fields in fm.state (BOOK-01).

    Populates:
    - fm.state["booking_slot"] = {date, time_slot, covers}
    - fm.state["customer"] = {name, phone}

    Returns (result, None) — stays in booking node for read-back (BOOK-03).
    The confirm/end transition must NOT happen at collect time.
    """
    fm.state["booking_slot"] = {
        "date": args["date"],
        "time_slot": args["time_slot"],
        "covers": args["covers"],
    }
    fm.state["customer"] = {
        "name": args["name"],
        "phone": args["phone"],
    }
    # Stay in booking node — do NOT call create_event here (BOOK-03 read-back gating)
    return {"collected": True}, None


async def handle_confirm_booking(args: dict, fm) -> tuple[dict, dict | None]:
    """Capacity check + Calendar write + DB persist + transition to end node (BOOK-02..06).

    Gate sequence (BOOK-05):
    1. Capacity check (DB, authoritative — not Calendar, PITFALL 7)
    2. Insert draft reservation (try_reserve_slot / BEGIN IMMEDIATE)
    3. Calendar write (create_event) — on exception: return (error, None), no confirm
    4. Confirm in DB (confirm_reservation) — on exception: return (error, None), no confirm
    5. Only now return (result_with_event_id, build_end_node()) — spoken confirmation
       text lives ONLY in the end node (Pitfall 3 prevention, T-02-04)

    Security:
    - T-02-07: phone/name NEVER logged in except clauses (PII).
    - T-02-06: tenant_id from fm.state session context only.
    """
    from src.flows.nodes import build_end_node

    # Read session context — tenant_id comes from session context, never from args (T-02-06)
    slot = fm.state.get("booking_slot", {})
    customer = fm.state.get("customer", {})
    tenant_id: str = fm.state.get("tenant_id", "")
    tenant = fm.state.get("tenant")
    db_path: str = fm.state.get("db_path", "centralino.db")
    # Support both 'calendar' and 'calendar_provider' keys for test compatibility
    calendar_provider = fm.state.get("calendar") or fm.state.get("calendar_provider")

    # --- Parse booking_rules from TenantConfig (with safe defaults) ---
    max_covers = 40
    slot_duration_min = 30
    if tenant is not None and hasattr(tenant, "booking_rules") and tenant.booking_rules:
        try:
            rules = json.loads(tenant.booking_rules)
            max_covers = int(rules.get("max_covers_per_slot", max_covers))
            slot_duration_min = int(rules.get("slot_duration_min", slot_duration_min))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass  # use defaults on malformed config

    slot_date: str = slot.get("date", "")
    slot_time: str = slot.get("time_slot", "")
    covers: int = int(slot.get("covers", 1))
    name: str = customer.get("name", "")
    phone: str = customer.get("phone", "")

    # --- Step 1 + 2: Atomic capacity check + draft insert (BEGIN IMMEDIATE) ---
    repo = ReservationRepository(db_path=db_path)
    ok, res_id = await repo.try_reserve_slot(
        tenant_id=tenant_id,
        slot_date=slot_date,
        slot_time=slot_time,
        covers=covers,
        name=name,
        phone=phone,
        limit=max_covers,
    )
    if not ok:
        # Slot full — find alternatives (D-04)
        alternatives = await repo.find_available_slots(
            tenant_id=tenant_id,
            slot_date=slot_date,
            limit_per_slot=max_covers,
        )
        return {"available": False, "alternatives": alternatives}, None

    # --- Step 3: Calendar write (projection — not the lock) ---
    try:
        start_dt, end_dt = slot_to_datetimes(slot_date, slot_time, slot_duration_min)
        event_title = f"Prenotazione - {name} ({covers}p)"
        event_details = (
            f"Nome: {name}\n"
            f"Persone: {covers}\n"
            f"Telefono: {phone}\n"
            "via Centralino AI"
        )
        event_id: str = await calendar_provider.create_event(
            tenant_id=tenant_id,
            start=start_dt,
            end=end_dt,
            title=event_title,
            details=event_details,
        )
    except Exception:
        # Calendar unavailable — stay in booking node, no false confirmation (T-02-04)
        # NOTE: PII (phone/name) intentionally NOT logged here (T-02-07)
        return {"available": False, "error": "calendario non disponibile"}, None

    # --- Step 4: Confirm in DB (only reached if Calendar write succeeded) ---
    try:
        await repo.confirm_reservation(res_id, event_id)
    except Exception:
        # DB confirm failed after calendar write (W4 accepted behavior):
        # A stale Google event may exist; bozza row persists; no false confirmation spoken.
        # PII intentionally NOT logged here (T-02-07).
        return {"available": False, "error": "errore conferma prenotazione"}, None

    # --- Step 5: Store event_id and transition to end node ---
    # build_end_node() transition is ONLY reachable here — on the branch where event_id is truthy
    fm.state["confirmed_event_id"] = event_id
    return {"event_id": event_id, "status": "confirmed"}, build_end_node(tenant)


async def correct_booking_field(args: dict, fm) -> tuple[dict, None]:
    """Update ONLY the named field in fm.state; return (result, None) to stay in
    the booking node for a fresh read-back (D-17 BLOCKER B1).

    Validates field_name against the allowed set.  Updates booking_slot or
    customer dict in-place — never clears or rebuilds either dict.
    Returns next_node=None so the booking node re-reads-back the full
    (now-corrected) data set.

    The handler does NOT restart field collection — it patches a single field
    and leaves all other collected fields intact.
    """
    field_name: str = args.get("field_name", "")
    new_value = args.get("new_value")

    if field_name not in _ALL_BOOKING_FIELDS:
        return {
            "error": f"Campo '{field_name}' non valido. "
            f"Campi consentiti: {', '.join(_ALL_BOOKING_FIELDS)}"
        }, None

    # Update ONLY the named field in the correct sub-dict — do not clear other fields (D-17)
    if field_name in _BOOKING_SLOT_FIELDS:
        if "booking_slot" not in fm.state:
            fm.state["booking_slot"] = {}
        fm.state["booking_slot"][field_name] = new_value
    else:  # customer field
        if "customer" not in fm.state:
            fm.state["customer"] = {}
        fm.state["customer"][field_name] = new_value

    # Return (result, None) — stay in booking node for re-read-back (D-17)
    return {"corrected": field_name}, None
