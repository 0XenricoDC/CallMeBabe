"""Pipecat Flows node builders — greeting / booking / end nodes (D-13).

Each builder returns a NodeConfig dict.  Nodes expose only the tools they need:
- greeting node: no tools (prevents stray tool calls; routing tools added in Plan 02-04)
- booking node: collect_booking_info + confirm_booking + correct_booking_field
- end node: no tools (spoken confirmation text lives ONLY here — BOOK-05 gating)

CRITICAL (from RESEARCH.md §Pattern 1, verified against pipecat_flows 1.3.0 source):
- NodeConfig uses `role_message` (str), NOT deprecated `role_messages` (list)
- `functions` list contains FlowsFunctionSchema instances
- Handler signature: async def h(args: FlowArgs, fm: FlowManager) -> (result, NodeConfig | None)

NOTE: build_greeting_node currently exposes `functions=[]`.
Plan 02-04 (Wave 1) extends this list with `route_to_faq`/`route_to_booking`
transition tools — the structure is kept ready for a one-line addition.
"""

from __future__ import annotations

from src.config.tenant_config import TenantConfig


def build_greeting_node(tenant: TenantConfig) -> dict:
    """Opening node — no booking tools exposed; LLM greets and asks how to help.

    functions=[] here prevents stray tool calls at greeting.
    Plan 02-04 will add routing tools to this list so the LLM can
    transition to the booking or FAQ node.
    """
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
                    "Se vuole prenotare, usa collect_booking_info. "
                    "Se fa domande generali, usa faq_lookup."
                ),
            }
        ],
        "functions": [],  # no tools at greeting — prevents stray tool calls
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
