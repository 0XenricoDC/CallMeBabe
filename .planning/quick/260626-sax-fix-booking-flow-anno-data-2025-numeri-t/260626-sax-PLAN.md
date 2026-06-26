---
quick_id: 260626-sax
title: "Fix booking flow: anno data 2025 + numeri telefono alieni nel readback"
date: 2026-06-26
status: in-progress
---

# Quick Task 260626-sax

Fix di due bug emersi in chiamata reale di test sul booking flow:

1. **Anno data = 2025.** Quando il cliente dice solo "8 luglio", l'LLM produce
   date ISO con anno passato (2025) invece dell'anno corrente/futuro. Cause:
   (a) lo schema `collect_booking_info` usa l'esempio `es. 2025-07-08` che ancora
   il modello al 2025; (b) il booking node non inietta mai la data odierna nel prompt.
2. **Numeri telefono "alieni".** Il telefono viene letto cifra-per-cifra solo con
   spazi (`" ".join`), ma l'LLM ricompatta le cifre in un unico numero e il TTS lo
   pronuncia male.

## Task 1 — Normalizzazione data al futuro (server-side)

- **files:** `src/booking/date_parser.py`
- **action:** Aggiungere `normalize_future_date(iso_date, *, today=None) -> str`
  che, se la data ISO è nel passato rispetto a oggi (Europe/Rome), porta l'anno
  in avanti alla prima occorrenza futura (mirror di `PREFER_DATES_FROM=future`).
  Robusto su input non parsabile (ritorna l'input invariato) e su 29 febbraio.
- **verify:** test in `tests/test_date_parser.py` — data passata → anno bumpato;
  data futura → invariata; input garbage → invariato.
- **done:** funzione importabile e testata.

## Task 2 — Readback robusto: data in italiano + telefono a parole

- **files:** `src/flows/functions.py`, `src/flows/nodes.py`
- **action:**
  - `_spell_phone_it(phone)`: cifre → parole italiane (zero..nove) separate da
    virgola, così l'LLM non può ricompattarle.
  - `_format_date_it(iso)`: ISO → "8 luglio 2026" (fallback all'ISO se non parsa).
  - `handle_collect_booking_info`: normalizza la data con `normalize_future_date`,
    costruisce il readback con data in italiano + telefono a parole.
  - `correct_booking_field`: normalizza anche quando si corregge il campo `date`.
  - `collect_booking_info` schema: esempio data non ancorato a un anno passato.
  - booking node (`nodes.py`): iniettare la data odierna Europe/Rome nel prompt
    così l'LLM calcola l'anno corretto.
- **verify:** `tests/test_flows.py` — readback contiene telefono a parole e data
  in italiano; data passata normalizzata al futuro in `fm.state`.
- **done:** test verdi.

## Vincoli
- PII (telefono/nome) mai loggati — invariato.
- Nessuna modifica al gating BOOK-03/BOOK-05.
