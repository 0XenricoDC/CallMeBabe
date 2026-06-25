# Phase 2: Booking + Calendar + FAQ - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-25
**Phase:** 2-booking-calendar-faq
**Areas discussed:** Vertical & modello capienza, Slot pieno & alternative, FAQ / Knowledge base, Google Calendar: auth & isolamento

---

## Vertical & modello capienza

### Vertical del tenant demo

| Option | Description | Selected |
|--------|-------------|----------|
| Ristorante (a coperti) | data+ora+n. persone; capienza = coperti totali per fascia; caso più ricco per la verifica capienza concorrente (SC3) | ✓ |
| Studio medico/dentistico (appuntamenti) | data+ora+servizio; capienza = 1 slot per volta (per professionista); modello più semplice | |
| Hotel/B&B (camere/notti) | check-in/out + camera; capienza = n. camere per notte; intervalli multi-giorno, più complesso | |

**User's choice:** Ristorante (a coperti)

### Modello di capienza

| Option | Description | Selected |
|--------|-------------|----------|
| Coperti totali per fascia | limite di coperti per finestra oraria, somma transazionale < limite; combinazione tavoli → v2 | ✓ |
| Turni fissi a coperti | due/tre turni configurati con tetto coperti; vincola al turno | |
| Posti-tavolo singoli | capienza = n. tavoli, ignora dimensione gruppo | |

**User's choice:** Coperti totali per fascia

### Config slot

| Option | Description | Selected |
|--------|-------------|----------|
| Slot fissi da config (es. 30 min) | orari + durata slot + coperti-per-slot in booking_rules/hours; durata prenotazione fissa | ✓ |
| Durata prenotazione configurabile | durata occupazione tavolo per-tenant; più flessibile | |
| Tu decidi (planning) | granularità e formato booking_rules a planning | |

**User's choice:** Slot fissi da config (es. 30 min)

**Notes:** Goal del roadmap "party size" confermato come ristorante. Capienza autoritativa nel DB con check-and-insert transazionale (già locked da PITFALL 7).

---

## Slot pieno & alternative

### Comportamento su slot pieno

| Option | Description | Selected |
|--------|-------------|----------|
| Propone le fasce libere più vicine | offre 2-3 alternative concrete stesso giorno dal DB | ✓ |
| Chiede la flessibilità al chiamante | "a che altro orario sarebbe disponibile?" poi ri-verifica | |
| Rifiuta e propone richiamo/operatore | comunica solo no posto | |

**User's choice:** Propone le fasce libere più vicine

### Fallback se giorno pieno

| Option | Description | Selected |
|--------|-------------|----------|
| Propone il giorno successivo utile | prima disponibilità nei giorni vicini | ✓ |
| Resta nel giorno richiesto | si limita al giorno chiesto | |
| Tu decidi (planning) | profondità ricerca a planning | |

**User's choice:** Propone il giorno successivo utile

---

## FAQ / Knowledge base

### Fonte KB

| Option | Description | Selected |
|--------|-------------|----------|
| Ibrido: config + KB testuale | orari/servizi dai campi config; indirizzo/prezzi/altro da KB testuale FTS5 | ✓ |
| Tutto in una KB testuale | cartella file → ingest chunk + FTS5 | |
| Coppie Q&A strutturate | domanda→risposta JSON/CSV via FTS5 | |

**User's choice:** Ibrido: config + KB testuale

### Comportamento info assente

| Option | Description | Selected |
|--------|-------------|----------|
| Ammette e offre richiamo/nota | "non ho l'informazione, posso prendere nota e farla ricontattare"; transfer vero → Fase 3 | ✓ |
| Ammette e basta | "non ho questa informazione", minimale | |
| Tu decidi (planning) | wording e gancio transfer a planning | |

**User's choice:** Ammette e offre richiamo/nota

**Notes:** Retrieval FTS5 già locked (FAQV2-01 differisce embeddings). La cartella `lancedb/` nel repo è residua/non pertinente.

---

## Google Calendar: auth & isolamento

### Modello auth

| Option | Description | Selected |
|--------|-------------|----------|
| Service account unico (consigliato) | credenziale JSON globale via .env; calendar_id per-tenant; owner condivide calendario con email service account | ✓ |
| OAuth per-tenant | autorizzazione nel Google del cliente, refresh token per-tenant; più complesso, vicino a Fase 5 | |
| Tu decidi (planning) | modello auth a planning | |

**User's choice:** Service account unico (consigliato)

### Isolamento calendari

| Option | Description | Selected |
|--------|-------------|----------|
| Un calendario dedicato per tenant | calendar_id distinto per tenant; richiede colonna calendar_id (assente) | ✓ |
| Calendario condiviso con tag tenant | unico calendario con tenant nei metadati; rischioso per isolamento | |
| Tu decidi (planning) | meccanismo isolamento e dove vive calendar_id a planning | |

**User's choice:** Un calendario dedicato per tenant

**Notes:** Lo schema `tenants` attuale NON ha colonna `calendar_id` — va aggiunta in Fase 2.

---

## Claude's Discretion

- Modello Claude per il path booking (Haiku default vs Sonnet per affidabilità tool-calling; temperatura bassa + max_tokens stretti).
- Design conversazionale raccolta dati: date relative, normalizzazione orari, conferma telefono cifra-per-cifra, spelling nome su bassa confidenza, ordine campi.
- Wording esatto di read-back, slot pieno, alternative, info assente.
- Granularità slot e formato `booking_rules`.
- Schema persistenza (`reservations`, `kb_documents`/`kb_chunks`): SQLAlchemy (research) vs aiosqlite + repository (pattern Fase 1) — preferenza coerenza Fase 1.
- Profondità ricerca alternative (quante proposte, quanti giorni avanti).

## Deferred Ideas

- Altri vertical (hotel/B&B, studio medico) — stesso motore via config, iterazioni successive.
- Logica avanzata combinazione tavoli / capienza complessa → v2 (BOOKV2-01).
- RAG con embedding/vector store → v2 (FAQV2-01).
- OAuth Google per-tenant + credential store isolato → Fase 5 (TENANT-06).
- Trasferimento vero all'operatore (gancio da "info assente" e bassa confidenza) → Fase 3 (HAND-*).
- Trasferimento "warm" con briefing → v2 (BOOKV2-02).
- Durata occupazione tavolo per-tenant variabile → oltre v1.
