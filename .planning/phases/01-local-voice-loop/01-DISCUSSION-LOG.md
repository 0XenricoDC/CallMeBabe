# Phase 1: Local Voice Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-23
**Phase:** 1-Local Voice Loop
**Areas discussed:** Config tenant demo, Esecuzione & test locale, Fallback di cortesia, Persona & scopo (default confermato), Modello Claude, Saluto & barge-in, .env.example & onboarding

---

## Selezione aree iniziali

Presentate 4 aree grigie. Selezionate dall'utente: **Config tenant demo**, **Esecuzione & test locale**, **Fallback di cortesia**. Non selezionata: *Persona & scopo del bot* (gestita con default, poi confermata).

---

## Config tenant demo

### Storage config
| Option | Description | Selected |
|--------|-------------|----------|
| JSON dietro repository | File tenants/demo.json letto da un ConfigRepository astratto; più semplice per 1 tenant | |
| Già SQLite (aiosqlite) | Tabella tenants in SQLite da subito; niente migrazione JSON→SQLite dopo | ✓ |

### Campi tenant
| Option | Description | Selected |
|--------|-------------|----------|
| Solo campi Fase 1 | id, business_name, greeting, voice_id, language, system_prompt | |
| Schema completo, colonne nullable | Modella ora tutte le colonne note (hours, services, booking_rules, transfer_number, kb_ref, notification_channel) come nullable | ✓ |
| Pydantic model + colonna JSON | Tabella id + blob JSON validato da modello Pydantic | |

**User's choice:** SQLite (aiosqlite) da subito + schema completo a colonne nullable.
**Notes:** Allinea col principio "ogni cliente = record di config" e con la migrazione a Postgres senza churn di schema.

---

## Esecuzione & test locale

### Trasporto
| Option | Description | Selected |
|--------|-------------|----------|
| Browser WebRTC | Pipecat runner + SmallWebRTCTransport, mic del browser, niente deps audio native su Windows | ✓ |
| Audio nativo da terminale | LocalAudioTransport (PyAudio/sounddevice), richiede PortAudio su Windows | |

### Latenza
| Option | Description | Selected |
|--------|-------------|----------|
| Console per-turno + JSONL | Riga leggibile a ogni turno + log JSONL per analisi, su metriche native Pipecat | ✓ |
| Solo console per-turno | Solo riga in console, niente storico | |
| Solo log JSONL strutturato | Solo file machine-readable | |

**User's choice:** Browser WebRTC + Console per-turno e log JSONL.
**Notes:** Stessa pipeline che reggerà Telnyx cambiando solo il transport.

---

## Fallback di cortesia (REL-01)

### Comportamento su errore/timeout
| Option | Description | Selected |
|--------|-------------|----------|
| 1 retry rapido poi frase generica | Singolo retry dove sicuro, poi frase di cortesia generica in italiano | ✓ |
| Frase generica immediata | Nessun retry, frase di cortesia subito | |
| Frasi per-stage | Frasi diverse per STT/LLM/TTS | |

### Scope faster-whisper in Fase 1
| Option | Description | Selected |
|--------|-------------|----------|
| Solo seam STTProvider | Interfaccia con Deepgram unica impl.; Whisper rinviato a Fase 3 | |
| Seam + WhisperSTTService selezionabile da config | Whisper cablato e attivabile da config, senza failover automatico | ✓ |

**User's choice:** 1 retry rapido → frase generica; seam STTProvider + WhisperSTTService selezionabile da config (no failover automatico).
**Notes:** ⚠ Porta le dipendenze ML pesanti (faster-whisper/ctranslate2) già in Fase 1. Il failover automatico resta REL-03/Fase 3.

---

## Persona & scopo del bot (default confermato)

| Option | Description | Selected |
|--------|-------------|----------|
| Receptionist vincolato | Si presenta come centralino, dice che booking/info arriveranno a breve | ✓ |
| Banco di prova libero | Assistente conversazionale generico senza vincolo di dominio | |

**User's choice:** Receptionist vincolato.

---

## Modello Claude

| Option | Description | Selected |
|--------|-------------|----------|
| Haiku 4.5 | TTFT basso, ideale per voce real-time | |
| Sonnet 4.6 | Più capace ma TTFT più alto | |
| Configurabile, default Haiku | Campo model per-tenant, default Haiku 4.5 | ✓ |

**User's choice:** `model` configurabile per-tenant, default `claude-haiku-4-5`.

---

## Saluto & barge-in

| Option | Description | Selected |
|--------|-------------|----------|
| Saluto interrompibile | Bot parla per primo, barge-in attivo già durante il saluto | ✓ |
| Saluto protetto | Saluto non interrompibile, poi attiva ascolto | |
| Attende il chiamante | Bot non parla per primo | |

**User's choice:** Saluto interrompibile (bot parla per primo).

---

## .env.example & onboarding (SETUP-01)

| Option | Description | Selected |
|--------|-------------|----------|
| .env.example commentato + sezione README | Solo chiavi Fase 1 con commenti inline; istruzioni passo-passo nel README | ✓ |
| Tutto dentro .env.example | Variabili + istruzioni complete nei commenti del file | |
| Include già chiavi future (Telnyx, Google) | Placeholder anche per fasi successive | |

**User's choice:** `.env.example` commentato (solo chiavi Fase 1) + guida account nel README.

---

## Claude's Discretion

- Tuning VAD/endpointing (Silero `stop_secs`/soglie) — area presentata ma non selezionata; lasciata a ricerca/planning. Vincolo: `aggregation_timeout` 0.1–0.3s.
- Wording esatto frasi di cortesia e saluto demo; struttura/percorso file JSONL; soglia di warning >800ms.
- Cablaggio degli stub `CalendarProvider`/`NotificationChannel` (solo interfacce in Fase 1).

## Deferred Ideas

- Failover STT automatico + watchdog dead-air → Fase 3 (REL-02/03/04).
- Frasi di cortesia per-stage → evoluzione futura.
- Chiavi `TELNYX_*` / `GOOGLE_*` in `.env.example` → Fasi 4 e 2.
- Uso effettivo di Sonnet/altri modelli per-tenant → da Fase 2 in poi.
