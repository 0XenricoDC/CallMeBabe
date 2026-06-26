# Phase 3: Handoff + Summary + Notifications - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-26
**Phase:** 3-Handoff + Summary + Notifications
**Areas discussed:** Meccanica del trasferimento, Contenuto del riepilogo, Canali di notifica, Scala di recupero guasti

---

## Meccanica del trasferimento — comportamento sul path locale

| Option | Description | Selected |
|--------|-------------|----------|
| Interfaccia + stub locale | Seam `TelephonyProvider.transfer(number)`; locale = cortesia + log intento + chiusura pulita, esito `trasferito`; Fase 4 → SIP/Dial reale | ✓ |
| Solo messaggio + chiusura | Niente seam telephony; messaggio + chiude; transfer vero interamente Fase 4 | |
| Bridge locale simulato | Bridge simulato locale per testare warm end-to-end ora; più lavoro | |

**User's choice:** Interfaccia + stub locale (Raccomandato)
**Notes:** Seam riusa il pattern interfacce della Fase 1; Fase 4 sostituisce lo stub senza toccare la logica.

## Meccanica del trasferimento — trigger automatici (multiselect)

| Option | Description | Selected |
|--------|-------------|----------|
| Non-italiano → trasferimento (HAND-03) | Lingua non-italiana rilevata → transfer diretto via tool | ✓ |
| Incertezza/fuori ambito → trasferimento (HAND-02) | Dubbio/out-of-scope → transfer; system prompt "in dubbio trasferisci" | ✓ |
| FAQ-non-trovata → offri trasferimento (Fase 2 D-08) | Info assente in KB → offre transfer oltre al "prendo nota" | ✓ |
| Briefing warm-ready nel seam | `transfer()` porta payload di contesto per warm transfer Fase 4 | ✓ |

**User's choice:** Tutte e quattro selezionate.
**Notes:** Trigger completi + payload warm-ready assemblato e loggato già sul path locale.

---

## Contenuto del riepilogo — generazione e dettaglio

| Option | Description | Selected |
|--------|-------------|----------|
| Sintesi LLM + dati strutturati | Sintesi LLM 2-3 frasi + blocco strutturato; trascrizione integrale nel call_log | ✓ |
| Solo template strutturato | Template fisso compilato + trascrizione integrale; deterministico, zero LLM | |
| Sintesi LLM + trascrizione inline | Come la prima ma trascrizione completa sempre nel corpo notifica | |

**User's choice:** Sintesi LLM + dati strutturati (Raccomandato)
**Notes:** Trascrizione integrale linkata/allegata nel DB, non incollata nella notifica.

## Contenuto del riepilogo — tassonomia esito e invio

| Option | Description | Selected |
|--------|-------------|----------|
| Tassonomia ricca, invio sempre | Esiti prenotato/faq/trasferito/abbandonato/fallito; notifica sempre a fine chiamata | ✓ |
| Tassonomia ricca, invio selettivo | Stessi esiti, notifica solo per esiti azionabili; FAQ pure non notificano | |
| Esito binario semplice | Solo gestita/non gestita; minimo sforzo classificazione | |

**User's choice:** Tassonomia ricca, invio sempre (Raccomandato)
**Notes:** Il titolare vede ogni chiamata, incluse abbandonate/fallite, per follow-up.

---

## Canali di notifica — scope di implementazione

| Option | Description | Selected |
|--------|-------------|----------|
| Tutti dietro interfaccia, log + Telegram reali | 4 canali dietro interfaccia; log + Telegram testabili ora; email/SMS/WhatsApp in codice, test con chiavi | ✓ |
| Tutti e quattro completi ora | Implementazione piena incl. SMS/WhatsApp con provider; testato al buio senza chiavi | |
| Solo log + Email ora, resto Fase 5 | log + Email reali ora; Telegram/SMS/WhatsApp rinviati; NOTIF-04 parziale | |

**User's choice:** Tutti dietro interfaccia, log + Telegram reali (Raccomandato)
**Notes:** Default demo = log (+ Telegram se token in `.env`); `.env.example` esteso.

---

## Scala di recupero guasti — fallback STT faster-whisper

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy-load al primo guasto, switch mid-call | faster-whisper non pre-caricato; al guasto persistente Deepgram → cortesia + switch per il resto della chiamata (small/int8) | ✓ |
| Hot standby pre-caricato | Caricato all'avvio, switch istantaneo; consuma RAM/CPU sempre | |
| Config-level (no switch a caldo) | Solo STT alternativo via config; guasto mid-call → diritto al transfer | |

**User's choice:** Lazy-load al primo guasto, switch mid-call (Raccomandato)
**Notes:** Trade-off ritardo primo switch mitigato con modello small/int8; ulteriore guasto → transfer (REL-02).

## Scala di recupero guasti — watchdog dead-air

| Option | Description | Selected |
|--------|-------------|----------|
| Re-prompt, poi escalation | Silenzio>T1 → "È ancora in linea?"; persiste>T2 → recovery/transfer | ✓ |
| Escalation diretta | Soglia superata → dritto a recovery/transfer, niente re-prompt | |
| Solo re-prompt, niente auto-transfer | Solo re-prompt ripetuti; mai forza il transfer | |

**User's choice:** Re-prompt, poi escalation (Raccomandato)
**Notes:** Distingue chiamante pensieroso da guasto reale; T1≈6s, T2≈+8s come punto di partenza (affinabili in planning).

---

## Claude's Discretion

- Wording esatto delle frasi (cortesia switch STT, re-prompt, offerta transfer, handoff).
- Soglie numeriche T1/T2 del watchdog e conteggio retry/timeout per "guasto persistente".
- Schema esatto di `call_logs` (colonne, dove vive la trascrizione, formato esito) — pattern `aiosqlite`/repository.
- Meccanismo preciso dello switch STT mid-call in Pipecat 1.4.0 (da verificare in research).
- Modello e formato della sintesi LLM del riepilogo.
- Meccanismo di rilevamento "non-italiano".
- Provider concreto per SMS/WhatsApp (Telnyx/Twilio/Meta) — dietro l'interfaccia.

## Deferred Ideas

- Meccanica di trasferimento telefonico reale (cold SIP REFER / warm Dial+Bridge) + percorso 8kHz → Fase 4.
- Test reale dei canali SMS/WhatsApp (account/numero, costi) → Fase 4+.
- Isolamento multi-tenant completo + credential store per-tenant → Fase 5.
- Warm transfer reale con briefing vocale all'operatore → Fase 4 / v2 (BOOKV2-02).
- Tuning fine di soglie/latenza della ladder fallback sul percorso telefonico reale → Fase 4.
