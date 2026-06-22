# Centralino AI

## What This Is

Assistente vocale telefonico multi-tenant per piccole attività italiane (ristoranti, hotel/B&B, studi medici/dentistici). Un solo motore self-hosted, con BYO API keys, che risponde alle chiamate in entrata in italiano naturale: prende prenotazioni/appuntamenti, risponde a FAQ pescando da una knowledge base per-cliente, trasferisce a un operatore umano quando serve, e a fine chiamata invia al titolare un riepilogo (trascrizione, esito, eventuale prenotazione). Ogni cliente è un record di configurazione, **non** una modifica al codice. Niente piattaforme tipo Synthflow/Vapi: si possiede l'intero stack.

## Core Value

Una chiamata reale in italiano viene gestita end-to-end dal bot — saluto personalizzato, conversazione naturale a bassa latenza, azione completata (prenotazione/FAQ/trasferimento) — senza intervento umano e senza riscrivere codice per un nuovo cliente.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

- [ ] Agente Pipecat che conversa in italiano naturale in locale (mic/cuffie) con pipeline Deepgram (STT) → Claude (LLM, tool calling) → ElevenLabs (TTS)
- [ ] Saluto personalizzato per cliente all'inizio della conversazione
- [ ] Flusso prenotazione strutturato (Pipecat Flows): raccolta data, ora, n. persone/servizio, nome, telefono
- [ ] Verifica disponibilità/capienza prima di confermare una prenotazione
- [ ] Scrittura della prenotazione su Google Calendar reale (dietro interfaccia `CalendarProvider`)
- [ ] FAQ in italiano via RAG semplice su knowledge base per-cliente (orari, indirizzo, servizi, prezzi)
- [ ] Trasferimento della chiamata a un operatore umano (numero configurabile) su richiesta, in caso di incertezza, o se il chiamante non parla italiano
- [ ] Log della chiamata + riepilogo testuale a fine chiamata (trascrizione, esito, eventuale prenotazione)
- [ ] Invio del riepilogo al titolare tramite layer notifiche multi-canale (Email/SMTP, SMS/WhatsApp, Telegram, log), con canale scelto per-cliente
- [ ] Layer telefonia astratto dietro interfaccia, con implementazione Telnyx (numeri geografici italiani) per chiamate reali in entrata
- [ ] Barge-in / gestione interruzioni durante il parlato del bot
- [ ] Fallback robusti: se STT/LLM/TTS falliscono → frasi di cortesia + eventuale trasferimento
- [ ] Fallback STT self-hosted (faster-whisper) predisposto in alternativa a Deepgram
- [ ] TTS predisposto per voice cloning ElevenLabs (voce personalizzata per cliente via `voice_id`)
- [ ] Multi-tenant: ogni cliente è un record di config (nome attività, saluto, voice_id, orari, servizi/menu, regole prenotazione, numero trasferimento, knowledge base, canale notifiche)
- [ ] Config in DB con SQLite/JSON iniziale, codice strutturato per migrare a Postgres
- [ ] Mini pannello/CLI per aggiungere un nuovo cliente (onboarding senza toccare il codice)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Supporto multilingua nelle conversazioni — v1 è solo italiano; un chiamante non-italiano viene trasferito all'operatore invece di essere servito dal bot
- Piattaforme vocali gestite (Synthflow, Vapi, ecc.) — obiettivo esplicito è possedere l'intero stack self-hosted
- Chiamate in uscita / outbound (campagne, reminder proattivi) — v1 gestisce solo chiamate in entrata
- Pagamenti / incassi in chiamata — fuori dal valore core di v1
- Postgres come DB di partenza — si parte da SQLite/JSON; il codice è strutturato per la migrazione ma Postgres non è richiesto in v1

## Context

- **Provider stack scelto a monte** dal titolare del progetto: Pipecat (orchestrazione Python), Deepgram (STT IT), Anthropic Claude (LLM/cervello con tool calling), ElevenLabs (TTS IT), Telnyx (telefonia IT). Sono decisioni vincolanti, non da rimettere in discussione.
- **Prima di scrivere codice** va consultata la documentazione ufficiale di Pipecat e Pipecat Flows. In questa sessione non è installato un plugin/skill Claude Code di Pipecat (l'unico MCP presente è un RAG per MQL5, non pertinente): la documentazione verrà raccolta nella fase di ricerca del workflow.
- **Nessuna chiave API ancora disponibile**: il progetto deve predisporre `.env.example`, placeholder e istruzioni passo-passo per creare gli account/chiavi (Deepgram, ElevenLabs, Anthropic, e più avanti Telnyx). La Milestone 1 diventa testabile end-to-end appena le chiavi vengono inserite.
- **Modello di sviluppo a tappe**: ogni milestone deve funzionare ed essere provata dal titolare prima di passare alla successiva (gate "fermati e fammela provare").
- Il dominio (centralino vocale a bassa latenza) è sensibile alla latenza percepita: la qualità della conversazione dipende da barge-in, gestione interruzioni e tempi di risposta sotto la soglia target.

## Constraints

- **Tech stack**: Pipecat (Python) + Pipecat Flows per l'orchestrazione e i flussi conversazionali — scelta vincolante del titolare.
- **STT**: Deepgram in italiano, con fallback faster-whisper self-hosted predisposto — robustezza e indipendenza da un singolo provider.
- **LLM**: Anthropic Claude via API con tool calling — è il "cervello" del bot.
- **TTS**: ElevenLabs, voce italiana, predisposto per voice cloning per-cliente (`voice_id`).
- **Telefonia**: Telnyx con numeri geografici italiani, **astratto dietro un'interfaccia** per poter passare a Twilio senza riscrivere la logica.
- **Notifiche/riepilogo**: layer astratto multi-canale (Email/SMTP, SMS/WhatsApp, Telegram, log), canale configurabile per-cliente.
- **Calendario**: interfaccia `CalendarProvider`; implementazione Google Calendar reale attiva dalla fase prenotazioni (non placeholder).
- **Architettura**: un solo motore; ogni cliente = record di CONFIG, mai una modifica al codice. Multi-tenant per configurazione.
- **Persistenza**: SQLite/JSON iniziale, codice strutturato per migrare a Postgres.
- **Performance**: latenza target < 800ms end-to-end; barge-in e gestione interruzioni obbligatori.
- **Affidabilità**: fallback robusti su tutti i layer (STT/LLM/TTS) con frasi di cortesia ed eventuale trasferimento.
- **Security/Config**: tutte le chiavi API via `.env`; nessuna chiave hardcoded; tutto self-hosted.
- **Lingua**: conversazione solo in italiano; non-italiano → trasferimento operatore.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pipecat (Python) + Pipecat Flows come orchestratore | Stack self-hosted, controllo completo della pipeline vocale e dei flussi strutturati | — Pending |
| Layer telefonia dietro interfaccia (Telnyx prima impl.) | Poter passare a Twilio senza riscrivere la logica di business | — Pending |
| Layer notifiche multi-canale configurabile per-cliente | Titolari diversi vogliono canali diversi (email, SMS/WhatsApp, Telegram); evitare hardcoding | — Pending |
| Prenotazioni con verifica capienza + Google Calendar reale già nella fase prenotazioni | Il titolare vuole una gestione prenotazioni completa, non un placeholder | — Pending |
| Multi-tenant per config, non per codice | Onboarding di nuovi clienti senza modificare/deployare codice | — Pending |
| SQLite/JSON ora, struttura pronta per Postgres | Partire leggeri ma senza chiudere la porta allo scaling | — Pending |
| Solo italiano in v1; non-IT → trasferimento operatore | Mantenere v1 focalizzata e affidabile; multilingua è complessità non necessaria ora | — Pending |
| Fallback STT self-hosted (faster-whisper) predisposto | Non dipendere da un singolo provider STT cloud | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-23 after initialization*
