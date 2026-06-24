# Requirements: Centralino AI

**Defined:** 2026-06-23
**Core Value:** Una chiamata reale in italiano viene gestita end-to-end dal bot (saluto personalizzato, conversazione naturale a bassa latenza, azione completata) senza intervento umano e senza riscrivere codice per un nuovo cliente.

## v1 Requirements

Requisiti per il rilascio iniziale. Ogni requisito mappa a una fase del roadmap.

### Conversazione vocale (Voice)

- [x] **VOICE-01**: Il bot conversa in italiano naturale in locale (microfono/cuffie) attraverso una pipeline streaming Deepgram (STT) → Claude (LLM) → ElevenLabs (TTS)
- [x] **VOICE-02**: Il bot apre la conversazione con un saluto personalizzato preso dalla config del cliente
- [x] **VOICE-03**: Il chiamante può interrompere il bot mentre parla (barge-in) e il bot smette di parlare e ascolta
- [x] **VOICE-04**: La latenza percepita per turno è sotto la soglia target (<800ms end-to-end) con strumentazione per-stage
- [x] **VOICE-05**: La voce TTS usata è quella configurata per il cliente (`voice_id` ElevenLabs), predisposta per voice cloning

### Prenotazioni (Booking)

- [ ] **BOOK-01**: Il bot raccoglie in modo strutturato i dati di una prenotazione (data, ora, n. persone o servizio, nome, telefono) tramite un flusso Pipecat Flows
- [ ] **BOOK-02**: Il bot verifica la disponibilità/capienza prima di confermare la prenotazione, usando una capienza autoritativa nel DB del progetto
- [ ] **BOOK-03**: Il bot ripete al chiamante i dati raccolti (read-back) e attende conferma prima di scrivere la prenotazione
- [ ] **BOOK-04**: Il bot scrive la prenotazione confermata su Google Calendar reale tramite l'interfaccia `CalendarProvider`
- [ ] **BOOK-05**: Il bot conferma a voce la prenotazione solo dopo che la scrittura su calendario è riuscita (nessuna conferma fantasma)
- [ ] **BOOK-06**: Una prenotazione confermata viene persistita nel DB del progetto (record reservation)

### FAQ / Knowledge base (FAQ)

- [ ] **FAQ-01**: Il bot risponde a domande frequenti (orari, indirizzo, servizi, prezzi) attingendo alla knowledge base del cliente via RAG semplice
- [ ] **FAQ-02**: Le risposte FAQ sono ancorate ai contenuti della KB del cliente; il bot non inventa dati (orari/prezzi assenti → non risponde a caso)
- [ ] **FAQ-03**: La knowledge base è per-cliente (ogni cliente ha i propri contenuti FAQ)

### Trasferimento a operatore (Handoff)

- [ ] **HAND-01**: Il bot trasferisce la chiamata a un operatore umano (numero configurabile) quando il chiamante lo richiede
- [ ] **HAND-02**: Il bot trasferisce all'operatore quando non sa rispondere / è incerto / la richiesta è fuori ambito
- [ ] **HAND-03**: Se il chiamante non parla italiano, il bot trasferisce direttamente all'operatore
- [ ] **HAND-04**: Il trasferimento è disponibile da qualsiasi punto della conversazione (global function nei flussi)

### Riepilogo e notifiche (Notify)

- [ ] **NOTIF-01**: A fine chiamata il bot registra un log della chiamata (trascrizione, esito, eventuale prenotazione)
- [ ] **NOTIF-02**: Il bot genera un riepilogo testuale della chiamata (trascrizione + esito + dettagli prenotazione)
- [ ] **NOTIF-03**: Il riepilogo viene inviato al titolare tramite un layer notifiche astratto (`NotificationChannel`)
- [ ] **NOTIF-04**: Sono implementati i canali Email/SMTP, SMS/WhatsApp, Telegram e log su DB
- [ ] **NOTIF-05**: Il canale di notifica è scelto per-cliente dalla config

### Affidabilità e fallback (Reliability)

- [x] **REL-01**: Se STT/LLM/TTS falliscono durante la chiamata, il bot pronuncia frasi di cortesia anziché lasciare dead-air
- [ ] **REL-02**: In caso di guasto persistente di un provider, il bot offre/effettua il trasferimento all'operatore
- [ ] **REL-03**: È predisposto un fallback STT self-hosted (faster-whisper) attivabile in alternativa a Deepgram
- [ ] **REL-04**: Un watchdog rileva il dead-air / silenzio anomalo e innesca la strategia di recupero

### Telefonia (Telephony)

- [ ] **TEL-01**: Il layer telefonia è astratto dietro un'interfaccia, con la logica di business indipendente dal provider
- [ ] **TEL-02**: Il bot riceve chiamate reali in entrata su numeri geografici italiani via Telnyx (transport WebSocket media streaming)
- [ ] **TEL-03**: Il sistema instrada la chiamata al cliente corretto in base al numero chiamato (DID → tenant)
- [ ] **TEL-04**: Barge-in, endpointing e fallback sono verificati anche sul percorso telefonico reale (8kHz)
- [ ] **TEL-05**: Il trasferimento a operatore funziona su chiamata telefonica reale

### Multi-tenant e onboarding (Tenant)

- [ ] **TENANT-01**: Ogni cliente è un record di config (nome attività, saluto, voice_id, orari, servizi/menu, regole prenotazione, numero trasferimento, KB, canale notifiche), non una modifica al codice
- [ ] **TENANT-02**: La config del cliente viene caricata a inizio chiamata e iniettata in un unico motore condiviso
- [ ] **TENANT-03**: La config è persistita in DB con SQLite/JSON, con il codice strutturato per migrare a Postgres
- [ ] **TENANT-04**: I dati di un cliente sono isolati per `tenant_id`: nessuna fuga di config/KB/prenotazioni tra clienti
- [ ] **TENANT-05**: Un mini pannello/CLI permette di aggiungere un nuovo cliente (validazione + inserimento config + ingest KB) senza toccare il codice
- [ ] **TENANT-06**: Le credenziali/segreti sono per-cliente e gestiti in modo isolato (no chiavi hardcoded; tutto via .env / store)

### Setup e configurazione (Setup)

- [x] **SETUP-01**: Il repo include `.env.example`, placeholder e istruzioni passo-passo per creare gli account/chiavi (Deepgram, ElevenLabs, Anthropic, e Telnyx) — nessuna chiave hardcoded

## v2 Requirements

Differiti a un rilascio futuro. Tracciati ma non nel roadmap attuale.

### Telephony

- **TELV2-01**: Provider telefonia alternativo Twilio dietro la stessa interfaccia (aggiungere solo se Telnyx diventa limitante)

### Booking

- **BOOKV2-01**: Motore di regole prenotazione avanzato (logica combinazione tavoli / capienza complessa)
- **BOOKV2-02**: Trasferimento "warm" con briefing strutturato del contesto all'operatore

### Analytics

- **ANALV2-01**: Analitiche di esito chiamate dai log accumulati

### Knowledge base

- **FAQV2-01**: RAG con embedding/vector store (se il keyword search FTS5 non basta per la recall)

### Persistence

- **PERSV2-01**: Migrazione a Postgres (quando la concorrenza lo richiede)

## Out of Scope

Esplicitamente esclusi. Documentati per prevenire scope creep.

| Feature | Reason |
|---------|--------|
| Conversazione multilingua | v1 è solo italiano; non-IT → trasferimento operatore (anti-feature confermata dalla ricerca) |
| Piattaforme vocali gestite (Synthflow/Vapi) | Obiettivo esplicito: possedere l'intero stack self-hosted |
| Chiamate in uscita / outbound | v1 gestisce solo chiamate in entrata; compliance e casi d'uso diversi |
| Pagamenti / incassi in chiamata | Fuori dal valore core di v1; onere di compliance separato |
| Integrazioni specifiche PMS/POS/EHR | Non necessarie per v1; valutare per-cliente in futuro |
| Canale web/app vocale | Il focus v1 è il telefono |
| Postgres come DB di partenza | Si parte da SQLite/JSON; codice pronto a migrare ma non richiesto in v1 |

## Traceability

Quali fasi coprono quali requisiti. Aggiornata durante la creazione del roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| VOICE-01 | Phase 1 | Complete |
| VOICE-02 | Phase 1 | Complete |
| VOICE-03 | Phase 1 | Complete |
| VOICE-04 | Phase 1 | Complete |
| VOICE-05 | Phase 1 | Complete |
| REL-01 | Phase 1 | Complete |
| SETUP-01 | Phase 1 | Complete |
| BOOK-01 | Phase 2 | Pending |
| BOOK-02 | Phase 2 | Pending |
| BOOK-03 | Phase 2 | Pending |
| BOOK-04 | Phase 2 | Pending |
| BOOK-05 | Phase 2 | Pending |
| BOOK-06 | Phase 2 | Pending |
| FAQ-01 | Phase 2 | Pending |
| FAQ-02 | Phase 2 | Pending |
| FAQ-03 | Phase 2 | Pending |
| HAND-01 | Phase 3 | Pending |
| HAND-02 | Phase 3 | Pending |
| HAND-03 | Phase 3 | Pending |
| HAND-04 | Phase 3 | Pending |
| NOTIF-01 | Phase 3 | Pending |
| NOTIF-02 | Phase 3 | Pending |
| NOTIF-03 | Phase 3 | Pending |
| NOTIF-04 | Phase 3 | Pending |
| NOTIF-05 | Phase 3 | Pending |
| REL-02 | Phase 3 | Pending |
| REL-03 | Phase 3 | Pending |
| REL-04 | Phase 3 | Pending |
| TEL-01 | Phase 4 | Pending |
| TEL-02 | Phase 4 | Pending |
| TEL-03 | Phase 4 | Pending |
| TEL-04 | Phase 4 | Pending |
| TEL-05 | Phase 4 | Pending |
| TENANT-01 | Phase 5 | Pending |
| TENANT-02 | Phase 5 | Pending |
| TENANT-03 | Phase 5 | Pending |
| TENANT-04 | Phase 5 | Pending |
| TENANT-05 | Phase 5 | Pending |
| TENANT-06 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 39 total
- Mapped to phases: 39/39 ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-23*
*Last updated: 2026-06-23 after roadmap creation — all 39 v1 requirements mapped*
