---
quick_id: 260626-sax
title: "Fix booking flow: anno data 2025 + numeri telefono alieni nel readback"
date: 2026-06-26
status: complete
---

# Quick Task 260626-sax — Summary

Due bug emersi in chiamata reale di test, entrambi risolti.

## Bug 1 — Anno data nel passato (2025)
**Causa:** l'LLM riempiva il campo `date` ISO senza sapere la data odierna →
anno passato; lo schema usava l'esempio `es. 2025-07-08` che ancorava il modello.

**Fix (difesa a 3 livelli):**
- `src/booking/date_parser.py`: nuova `normalize_future_date(iso, *, today=None)`
  che porta una data passata alla prima occorrenza futura (mirror di
  `PREFER_DATES_FROM=future`); robusta su garbage e 29 febbraio.
- `src/flows/functions.py`: `handle_collect_booking_info` e `correct_booking_field`
  normalizzano la data server-side prima di salvarla in `fm.state`.
- `src/flows/nodes.py`: il booking node ora inietta `La data di oggi è {oggi}`
  (Europe/Rome) nel `role_message`, con istruzione di usare anno corrente/futuro.
- Esempio dello schema `collect_booking_info` non più ancorato a un anno passato.

## Bug 2 — Numeri di telefono "alieni"
**Causa:** il readback separava le cifre solo con spazi; l'LLM le ricompattava in
un unico numero prima del TTS.

**Fix:** `src/flows/functions.py`:
- `_spell_phone_it`: cifre → **parole italiane** (`tre, quattro, sette, ...`),
  non ricompattabili dall'LLM.
- `_format_date_it`: ISO → italiano naturale (`8 luglio 2026`) per pronuncia pulita.

## Test
- `tests/test_date_parser.py`: +4 test per `normalize_future_date`
  (bump passato, futuro invariato, garbage, 29 feb).
- `tests/test_flows.py`: aggiornati `test_booking_field_collection` (data
  normalizzata) e `test_collect_returns_spelled_readback` (telefono a parole + data IT).
- **Suite completa: 72 passed, 1 skipped** (skip pre-esistente).

## Vincoli rispettati
- PII (telefono/nome) mai loggati — invariato.
- Gating BOOK-03 / BOOK-05 invariato.

## Note / follow-up
- I test usano `today=` esplicito per `normalize_future_date`; i due test di
  `test_flows` con `normalize_future_date("2025-07-08")` restano stabili finché
  l'8 luglio dell'anno corrente non è passato — comportamento corretto comunque.
