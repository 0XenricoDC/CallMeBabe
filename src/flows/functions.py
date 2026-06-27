"""Pipecat Flows handler functions and FlowsFunctionSchema builders for booking + FAQ (D-13).

Implements the tool-result-gated booking flow:
  collect_booking_info → (read-back in booking node) → confirm_booking → end node

Also implements the hybrid FAQ flow (D-06):
  faq_lookup → structured config fields (hours/services) OR FTS5 KB search
  When nothing matches: found=False fallback (D-08, FAQ-02)

Phase 3 additions (03-01):
- build_transfer_schema() / handle_transfer_call(): global transfer function (HAND-01..04)
- handle_faq_lookup not-found branch now sets faq_transfer_offered=True (D-03)

BOOK-05 gating: the end node transition happens ONLY when create_event returns a
real event_id.  On any failure (capacity, calendar, DB) the handler returns
(result, None) to stay in the booking node.

Security:
- T-02-07: PII (phone, name) is NEVER logged in except clauses.
- T-02-06: tenant_id comes from fm.state session context, not from tool args.
- T-01-SQLI: all DB access goes through ReservationRepository (parameterized SQL).
- T-02-13: KB queries always use tenant_id from session context (never caller input).
- T-03-INJ: transfer_number resolved ONLY from fm.state["tenant"].transfer_number —
  NEVER from caller-supplied args (T-injection prevention, PITFALLS §Security).
- T-03-LOG: only reason/number logged in transfer; no caller PII.

Pattern analog: src/pipeline/fallback.py (async handler + try/except + no-secrets-in-logs).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from loguru import logger
from pipecat.frames.frames import EndWorkerFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat_flows import FlowsFunctionSchema

from src.booking.date_parser import normalize_future_date, slot_to_datetimes
from src.booking.repository import ReservationRepository
from src.kb.fts import SQLiteFTSKnowledgeBase

# D-05: how many days forward to search when the requested day has no free slots
MAX_ALT_DAYS = 3

# --- Read-back pronunciation helpers (D-15) --------------------------------
# The phone/date in the read-back are formatted server-side so the spoken output
# does not depend on the LLM. The phone is spelled as Italian *words* (not just
# digits separated by spaces) because the model would otherwise recompact the
# digits into one run-on, "alien"-sounding number before the TTS ever sees them.
_DIGIT_WORDS_IT = {
    "0": "zero", "1": "uno", "2": "due", "3": "tre", "4": "quattro",
    "5": "cinque", "6": "sei", "7": "sette", "8": "otto", "9": "nove",
}

_MONTHS_IT = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)


def _spell_phone_it(phone: str) -> str:
    """Spell a phone number digit-by-digit as Italian words ("tre, quattro, ...").

    Words cannot be recompacted by the LLM into a single number, so the TTS
    pronounces each digit clearly (D-15). Non-digit characters are dropped.
    """
    return ", ".join(_DIGIT_WORDS_IT[ch] for ch in str(phone) if ch.isdigit())


def _format_date_it(iso_date: str) -> str:
    """Format an ISO date (YYYY-MM-DD) as natural Italian, e.g. "8 luglio 2026".

    Falls back to the raw string if it cannot be parsed (never raises).
    """
    from datetime import date as _date

    try:
        d = _date.fromisoformat(iso_date)
    except (ValueError, TypeError):
        return iso_date
    return f"{d.day} {_MONTHS_IT[d.month - 1]} {d.year}"

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
                "description": (
                    "Data della prenotazione in formato ISO 8601 YYYY-MM-DD "
                    "(es. AAAA-07-08). Usa l'anno corrente o futuro indicato nel "
                    "contesto, mai un anno passato."
                ),
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
    # The LLM has no notion of the current date, so it routinely emits a past year
    # (e.g. 2025 when the caller only said "8 luglio"). Roll any past date forward
    # to its nearest future occurrence server-side (mirrors PREFER_DATES_FROM=future).
    norm_date = normalize_future_date(args["date"])
    fm.state["booking_slot"] = {
        "date": norm_date,
        "time_slot": args["time_slot"],
        "covers": args["covers"],
    }
    fm.state["customer"] = {
        "name": args["name"],
        "phone": args["phone"],
    }
    # Build the read-back string server-side so it is deterministic (BOOK-03/D-15)
    # rather than relying on the LLM to remember to read everything back — the
    # previous prompt-only approach let the model skip the read-back under
    # interruptions/latency. The phone is spelled as Italian words and the date in
    # natural Italian (D-15) so the TTS pronounces them clearly instead of a run-on,
    # alien-sounding number / raw ISO string.
    phone_spelled = _spell_phone_it(args["phone"])
    date_it = _format_date_it(norm_date)
    readback = (
        f"Le rileggo i dati: prenotazione per il {date_it} "
        f"alle {args['time_slot']}, per {args['covers']} persone, "
        f"a nome {args['name']}, numero di telefono {phone_spelled}. "
        "È tutto corretto?"
    )
    # Stay in booking node — do NOT call create_event here (BOOK-03 read-back gating)
    return {"collected": True, "readback": readback}, None


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
        # Slot full — find same-day alternatives first (D-04)
        alternatives = await repo.find_available_slots(
            tenant_id=tenant_id,
            slot_date=slot_date,
            limit_per_slot=max_covers,
        )
        # If no same-day alternatives, search forward up to MAX_ALT_DAYS (D-05)
        next_day_proposal: dict | None = None
        if not alternatives:
            try:
                requested_date = date.fromisoformat(slot_date)
            except ValueError:
                requested_date = None
            if requested_date is not None:
                for delta in range(1, MAX_ALT_DAYS + 1):
                    candidate_date = (requested_date + timedelta(days=delta)).isoformat()
                    next_day_slots = await repo.find_available_slots(
                        tenant_id=tenant_id,
                        slot_date=candidate_date,
                        limit_per_slot=max_covers,
                        count=1,
                    )
                    if next_day_slots:
                        next_day_proposal = {
                            "date": candidate_date,
                            "slot_time": next_day_slots[0],
                        }
                        break
        return {
            "available": False,
            "alternatives": alternatives,
            "next_day": next_day_proposal,
        }, None

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
    except Exception as exc:
        # Calendar write failed — stay in booking node, no false confirmation (T-02-04).
        # PII (phone/name) is intentionally NOT logged (T-02-07). Google API errors carry
        # the response status, not our request body, so the type/message is safe to log
        # and is essential for diagnosing why a confirmed-sounding booking never lands
        # on the calendar (e.g. 403 ACL, disabled API, wrong calendar_id).
        logger.error(
            f"Calendar create_event failed for tenant {tenant_id!r}: "
            f"{type(exc).__name__}: {exc}"
        )
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

    # A corrected date can again come back with a past year from the LLM — roll it
    # forward to the nearest future occurrence, same as at collect time.
    if field_name == "date":
        new_value = normalize_future_date(str(new_value))

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


# ---------------------------------------------------------------------------
# FAQ handlers and schema builders (D-06, D-07, D-08, FAQ-01..03)
# ---------------------------------------------------------------------------

# Keywords that indicate the caller is asking about hours or services (D-06).
# These are answered directly from TenantConfig structured fields — no FTS5 call.
_HOURS_KEYWORDS = {"orari", "orario", "apertura", "chiusura", "aperto", "chiuso", "aprite", "chiudete"}
_SERVICES_KEYWORDS = {"servizi", "servizio", "cucina", "specialità", "specialita", "offrite", "offerta"}


def build_faq_lookup_schema() -> FlowsFunctionSchema:
    """Return the FlowsFunctionSchema for faq_lookup.

    Hybrid routing (D-06):
    - Hours/services queries → answered from TenantConfig structured fields.
    - Address/price/free-text queries → FTS5 KB search via SQLiteFTSKnowledgeBase.
    - No match → found=False (D-08 honest fallback, FAQ-02).
    """
    return FlowsFunctionSchema(
        name="faq_lookup",
        description=(
            "Cerca una risposta alla domanda del cliente nella knowledge base del ristorante. "
            "Usa questo strumento per domande su orari, indirizzo, prezzi, menu, servizi, "
            "e qualsiasi altra informazione sul ristorante."
        ),
        properties={
            "query": {
                "type": "string",
                "description": "La domanda o il termine da cercare (in italiano).",
            },
        },
        required=["query"],
        handler=handle_faq_lookup,
    )


async def handle_faq_lookup(args: dict, fm) -> tuple[dict, None]:
    """Hybrid FAQ retrieval (D-06, D-07, D-08, FAQ-01..03).

    Routing logic:
    1. If the query contains hours/services keywords → answer from TenantConfig.hours
       or TenantConfig.services (structured fields, no FTS5 call needed).
    2. Otherwise → call SQLiteFTSKnowledgeBase.search(tenant_id, query, top_k=3).
    3. If search returns nothing → found=False (D-08 fallback: honest 'non ho questa info').

    Security:
    - T-02-13: tenant_id comes from fm.state session context, never from caller input.
    - T-01-SQLI: SQLiteFTSKnowledgeBase uses parameterized MATCH ? (Pitfall 6).
    """
    from src.config.tenant_config import TenantConfig

    query: str = args.get("query", "").lower().strip()
    tenant: TenantConfig | None = fm.state.get("tenant")
    db_path: str = fm.state.get("db_path", "centralino.db")
    # tenant_id from session context — T-02-13
    tenant_id: str = (tenant.id if tenant else "") or fm.state.get("tenant_id", "")

    # --- Step 1: Hybrid routing — check structured config fields first (D-06) ---
    query_tokens = set(query.split())

    # Hours query (orari di apertura, a che ora aprite, etc.)
    if query_tokens & _HOURS_KEYWORDS:
        hours = (tenant.hours or "") if tenant else ""
        services = (tenant.services or "") if tenant else ""
        answer = f"Orari: {hours}" if hours else "Orari non disponibili"
        if query_tokens & _SERVICES_KEYWORDS and services:
            answer = f"Orari: {hours}. Servizi: {services}"
        return {"source": "config", "answer": answer}, None

    # Services query (servizi, cucina, specialità, etc.)
    if query_tokens & _SERVICES_KEYWORDS:
        services = (tenant.services or "") if tenant else ""
        answer = f"Servizi: {services}" if services else "Informazioni sui servizi non disponibili"
        return {"source": "config", "answer": answer}, None

    # --- Step 2: FTS5 KB search for address/price/free-text queries ---
    kb = SQLiteFTSKnowledgeBase(db_path=db_path)
    chunks = await kb.search(tenant_id=tenant_id, query=query, top_k=3)

    if chunks:
        return {"found": True, "chunks": chunks}, None

    # --- Step 3: No match — honest fallback (D-08, FAQ-02) ---
    # Phase 3 (D-03): signal that the FAQ was not found so the FAQ node can offer
    # to transfer to an operator if the caller prefers (faq_transfer_offered flag).
    fm.state["faq_transfer_offered"] = True
    return {"found": False, "offer_transfer": True}, None


# ---------------------------------------------------------------------------
# Transfer handlers and schema builders (HAND-01..04, Phase 3 / 03-01)
# ---------------------------------------------------------------------------


def build_transfer_schema() -> FlowsFunctionSchema:
    """Return the FlowsFunctionSchema for transfer_call (HAND-04).

    This schema is passed to ``FlowManager(global_functions=[...])`` so it is
    automatically prepended to EVERY node's function list, making transfer
    invocable from greeting, booking, and FAQ nodes without adding it to each
    node individually (HAND-04 — transfer from any flow point).

    Triggers (per system instructions):
    - Caller explicitly requests a human (HAND-01)
    - Caller speaks a non-Italian language (HAND-03)
    - Request is out of scope or the bot is uncertain (HAND-02)
    - FAQ not found and caller prefers an operator (D-03)

    Security (T-03-INJ): ``reason`` is a safe, descriptive string (never used
    for routing).  The actual transfer target comes ONLY from tenant config.
    """
    return FlowsFunctionSchema(
        name="transfer_call",
        description=(
            "Trasferisci la chiamata a un operatore umano. "
            "Usa quando il cliente lo richiede esplicitamente, "
            "quando parla una lingua diversa dall'italiano, "
            "quando la richiesta è fuori dal tuo ambito, "
            "o quando non riesci ad aiutare il cliente."
        ),
        properties={
            "reason": {
                "type": "string",
                "description": (
                    "Motivo del trasferimento (es. 'richiesta_cliente', "
                    "'lingua_non_supportata', 'fuori_ambito', 'incertezza')."
                ),
            },
        },
        required=["reason"],
        handler=handle_transfer_call,
    )


async def handle_transfer_call(args: dict, fm) -> tuple[dict, None]:
    """Global transfer handler — local stub path (D-01, D-04, HAND-01..04).

    Resolves the transfer target EXCLUSIVELY from trusted tenant config
    (``fm.state["tenant"].transfer_number``) — NEVER from ``args``
    (T-injection prevention, T-03-INJ, PITFALLS §Security).

    Steps:
    1. Resolve transfer_number from trusted config (T-03-INJ).
    2. Assemble warm-ready payload (D-04) for Phase 4 real warm-transfer.
    3. Set fm.state["outcome"] = "trasferito" (D-06 taxonomy).
    4. Speak handoff courtesy phrase via TTSSpeakFrame (D-01).
    5. Enqueue EndWorkerFrame UPSTREAM for clean pipeline shutdown (D-01 stub).
    6. Call LocalTransferStub.transfer() as the domain seam (Phase 4 replaces impl).

    Args:
        args: Tool args dict — only ``reason`` (str) is read; all other keys
              are ignored (T-03-INJ).
        fm:   FlowManager instance providing ``fm.state`` and ``fm.worker``.

    Returns:
        (result_dict, None) — None keeps the flow in the current node; the
        pipeline shuts down before any further node transition is needed.
    """
    from src.telephony.stub import LocalTransferStub

    # --- Step 1: Resolve transfer_number from TRUSTED config only (T-03-INJ) ---
    # NEVER read transfer_number from args — T-injection prevention.
    tenant = fm.state.get("tenant")
    transfer_number: str = (
        (tenant.transfer_number if tenant and tenant.transfer_number else None)
        or "operatore"
    )

    # Step 2a: Read reason from args (safe — logged only, never used for routing)
    reason: str = args.get("reason", "richiesta_cliente")

    # Step 2b: Assemble warm-ready payload (D-04) — Phase 4 uses for real warm transfer
    warm_payload: dict = {
        "transfer_number": transfer_number,
        "reason": reason,
        "booking_slot": fm.state.get("booking_slot"),
        "customer": fm.state.get("customer"),
        "confirmed_event_id": fm.state.get("confirmed_event_id"),
    }

    # Step 3: Record outcome and payload in flow state (D-06)
    fm.state["transfer_payload"] = warm_payload
    fm.state["transfer_reason"] = reason
    fm.state["outcome"] = "trasferito"

    # Step 4: Speak handoff phrase BEFORE ending pipeline (D-01 courtesy)
    # append_to_context=False — this is a system message, not a conversational turn
    await fm.worker.queue_frames(
        [
            TTSSpeakFrame(
                text="La metto in contatto con un operatore, resti in linea.",
                append_to_context=False,
            )
        ]
    )

    # Step 5: Clean shutdown — EndWorkerFrame UPSTREAM terminates the pipeline (D-01 stub)
    await fm.worker.queue_frame(EndWorkerFrame(), FrameDirection.UPSTREAM)

    # Step 6: Call the telephony seam (Phase 4 replaces LocalTransferStub with real impl)
    # Security (T-03-LOG): stub logs only number + reason, never caller PII.
    stub = LocalTransferStub()
    await stub.transfer(transfer_number, warm_payload)

    return {"transferred": True, "to": transfer_number}, None


def build_route_to_faq_schema() -> FlowsFunctionSchema:
    """Return the FlowsFunctionSchema for route_to_faq (W1 greeting → faq transition).

    Called by the LLM from the greeting node when the caller has a question.
    Handler returns (result, build_faq_node(tenant)) to transition the flow to the FAQ node.
    """
    return FlowsFunctionSchema(
        name="route_to_faq",
        description=(
            "Passa al nodo FAQ per rispondere a una domanda del cliente "
            "(su orari, indirizzo, prezzi, menu, servizi, ecc.)."
        ),
        properties={
            "reason": {
                "type": "string",
                "description": "Breve descrizione della domanda del cliente.",
            },
        },
        required=["reason"],
        handler=handle_route_to_faq,
    )


async def handle_route_to_faq(args: dict, fm) -> tuple[dict, dict]:
    """Transition from greeting node to the FAQ node (W1)."""
    from src.flows.nodes import build_faq_node
    from src.config.tenant_config import TenantConfig

    tenant: TenantConfig | None = fm.state.get("tenant")
    return {"routed": "faq"}, build_faq_node(tenant)


def build_route_to_booking_schema() -> FlowsFunctionSchema:
    """Return the FlowsFunctionSchema for route_to_booking (W1 greeting → booking transition).

    Called by the LLM from the greeting node when the caller wants to make a reservation.
    Handler returns (result, build_booking_node(tenant)) to transition to the booking node.
    """
    return FlowsFunctionSchema(
        name="route_to_booking",
        description=(
            "Passa al nodo prenotazione quando il cliente vuole prenotare un tavolo."
        ),
        properties={
            "reason": {
                "type": "string",
                "description": "Breve descrizione della richiesta di prenotazione del cliente.",
            },
        },
        required=["reason"],
        handler=handle_route_to_booking,
    )


async def handle_route_to_booking(args: dict, fm) -> tuple[dict, dict]:
    """Transition from greeting node to the booking node (W1)."""
    from src.flows.nodes import build_booking_node
    from src.config.tenant_config import TenantConfig

    tenant: TenantConfig | None = fm.state.get("tenant")
    return {"routed": "booking"}, build_booking_node(tenant)
