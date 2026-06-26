"""Pipecat Flows node builders — greeting / booking / faq / end nodes (D-13).

Each builder returns a NodeConfig dict.  Nodes expose only the tools they need:
- greeting node: route_to_faq + route_to_booking (explicit routing — W1)
- booking node: collect_booking_info + confirm_booking + correct_booking_field
- faq node: faq_lookup ONLY (no booking tools — D-13 tool isolation)
- end node: no tools (spoken confirmation text lives ONLY here — BOOK-05 gating)

CRITICAL (from RESEARCH.md §Pattern 1, verified against pipecat_flows 1.3.0 source):
- NodeConfig uses `role_message` (str), NOT deprecated `role_messages` (list)
- `functions` list contains FlowsFunctionSchema instances
- Handler signature: async def h(args: FlowArgs, fm: FlowManager) -> (result, NodeConfig | None)

W1 routing:
- build_greeting_node exposes route_to_faq and route_to_booking tool calls
  so the LLM can explicitly transition to either the FAQ or booking node.
- Both transitions are tool-driven (not implicit prose routing per W1 requirement).
"""

from __future__ import annotations

from src.config.tenant_config import TenantConfig


def build_greeting_node(tenant: TenantConfig) -> dict:
    """Opening node — exposes routing tools: route_to_faq and route_to_booking (W1).

    The LLM must use a routing tool to leave the greeting node:
    - route_to_faq: for questions about hours, address, prices, menu, services
    - route_to_booking: for reservation requests

    Tool-driven routing (W1): the LLM cannot implicitly transition; it must call
    a routing tool whose handler returns the target NodeConfig.
    """
    from src.flows.functions import (
        build_route_to_faq_schema,
        build_route_to_booking_schema,
    )

    return {
        "name": "greeting",
        "role_message": (
            f"Sei la receptionist di {tenant.business_name}. "
            "Dai del Lei al cliente. "
            "Parla in italiano naturale. "
            "Risposte brevi ed essenziali (D-20)."
        ),
        "task_messages": [
            {
                "role": "user",
                "content": (
                    "Accogli il cliente con calore e chiedi come puoi aiutarlo. "
                    "Se ha una domanda (orari, indirizzo, prezzi, menu, servizi), "
                    "chiama route_to_faq. "
                    "Se vuole prenotare un tavolo, chiama route_to_booking."
                ),
            }
        ],
        "functions": [
            build_route_to_faq_schema(),
            build_route_to_booking_schema(),
        ],
    }


def build_booking_node(tenant: TenantConfig) -> dict:
    """Booking data-collection node (D-13).

    Exposes only the booking tools:
    - collect_booking_info: stores all five fields in fm.state (BOOK-01)
    - confirm_booking: capacity check + calendar write + DB persist (BOOK-02..06)
    - correct_booking_field: single-field correction at read-back (D-17)

    pre_actions carries a switch_llm_to_sonnet marker for Plan 03 to register
    the per-node model override (D-19) — inert until Plan 03 wires it.

    System rule in role_message: 'Non confermare mai una prenotazione senza il
    risultato dello strumento' prevents phantom confirms (Pitfall 3).
    """
    from src.flows.functions import (
        build_collect_booking_schema,
        build_confirm_booking_schema,
        build_correct_booking_field_schema,
    )

    return {
        "name": "booking",
        "role_message": (
            f"Sei la receptionist di {tenant.business_name}. "
            "Stai raccogliendo i dati per una prenotazione. "
            "Dai del Lei al cliente. "
            "Risposte brevi ed essenziali (D-20). "
            "Non confermare mai una prenotazione senza il risultato dello strumento."
        ),
        "task_messages": [
            {
                "role": "user",
                "content": (
                    "Raccogli data, ora, numero persone, nome e telefono. "
                    "Dopo aver raccolto tutti e cinque i dati, rileggili al cliente per conferma. "
                    "Rileggi il numero di telefono cifra per cifra (D-15). "
                    "Solo dopo la conferma vocale del cliente, chiama confirm_booking. "
                    "Se il cliente dice 'no' o vuole correggere un dato, chiedi quale campo "
                    "vuole cambiare e chiama correct_booking_field con il campo e il nuovo valore, "
                    "poi rileggi i dati aggiornati (D-17 — correggi solo il campo indicato, "
                    "non ricominciare la raccolta da capo). "
                    "Se confirm_booking restituisce available=false con alternatives, "
                    "proponi gli slot disponibili nella stessa giornata in modo naturale "
                    "(es. 'Le 20:00 sono al completo, ho posto alle 19:00 o alle 21:30'). "
                    "Se anche next_day è presente, proponi il primo slot disponibile "
                    "nel giorno indicato (es. 'domani sera alle 20:00'). "
                    "Non ripetere la raccolta dati da capo — chiedi solo se la nuova "
                    "fascia oraria va bene."
                ),
            }
        ],
        "functions": [
            build_collect_booking_schema(),
            build_confirm_booking_schema(),
            build_correct_booking_field_schema(),
        ],
        # pre_actions marker for Plan 03 per-node model override (D-19 — inert until then)
        "pre_actions": [{"type": "switch_llm_to_sonnet"}],
    }


def build_faq_node(tenant: TenantConfig | None = None) -> dict:
    """FAQ node — exposes ONLY faq_lookup (D-13 tool isolation, FAQ-01..03).

    Grounding rule (FAQ-02, D-08): the LLM answers ONLY from the faq_lookup result
    (config fields or FTS5 chunks).  When found=False, it must speak the D-08 phrase:
    'Non ho questa informazione al momento, posso prendere nota e farla ricontattare.'

    No booking tools exposed here — the FAQ node is strictly for information retrieval.
    Per-tenant voice persona (Lei form) preserved.
    """
    from src.flows.functions import build_faq_lookup_schema

    business_name = tenant.business_name if tenant else "il ristorante"
    return {
        "name": "faq",
        "role_message": (
            f"Sei la receptionist di {business_name}. "
            "Dai del Lei al cliente. "
            "Parla in italiano naturale. "
            "Risposte brevi ed essenziali (D-20). "
            "REGOLA DI GROUNDING (FAQ-02): rispondi SOLO con informazioni "
            "restituite dallo strumento faq_lookup o dalla configurazione. "
            "Se lo strumento restituisce found=false, ammetti onestamente di non avere "
            "quella informazione e offri di prendere nota: "
            "'Non ho questa informazione al momento, posso prendere nota e farla ricontattare.' "
            "Non inventare mai dati (D-08)."
        ),
        "task_messages": [
            {
                "role": "user",
                "content": (
                    "Il cliente ha una domanda. "
                    "Usa faq_lookup per cercare la risposta. "
                    "Se faq_lookup restituisce source='config', rispondi con il valore di 'answer'. "
                    "Se faq_lookup restituisce found=true, usa i 'chunks' per costruire la risposta. "
                    "Se faq_lookup restituisce found=false, di' onestamente che non hai "
                    "quell'informazione e offri di prendere nota per farla ricontattare."
                ),
            }
        ],
        "functions": [
            build_faq_lookup_schema(),
        ],
    }


def build_end_node(tenant: TenantConfig | None = None) -> dict:
    """Confirmation node — spoken 'prenotazione confermata' text lives ONLY here.

    This node is structurally reachable ONLY when handle_confirm_booking returns
    a real event_id (BOOK-05 gating).  The LLM can never self-report success
    because the end node is the only place where the confirmation phrase appears.

    functions=[] — no further tool calls needed after confirmation.
    """
    business_name = tenant.business_name if tenant else "la nostra struttura"
    return {
        "name": "end",
        "role_message": (
            f"La prenotazione presso {business_name} è stata confermata con successo."
        ),
        "task_messages": [
            {
                "role": "user",
                "content": (
                    "Comunica al cliente che la prenotazione è confermata. "
                    "Di' 'Perfetto, la sua prenotazione è confermata!' e "
                    "riepilogha i dettagli (data, ora, numero persone). "
                    "Ringrazia il cliente e saluta."
                ),
            }
        ],
        "functions": [],
    }
