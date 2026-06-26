# Phase 3: Handoff + Summary + Notifications - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Ogni chiamata finisce con un **record loggato** (`call_log`) e un **riepilogo inviato al titolare** sul canale configurato per il suo account; **qualsiasi chiamata può essere trasferita a un operatore umano da qualsiasi punto** (anche in mezzo al flusso di prenotazione); e **ogni guasto di provider degrada con grazia** — frase di cortesia → fallback STT faster-whisper → in ultima istanza trasferimento all'operatore — invece del dead-air, con un **watchdog** che rileva il silenzio anomalo e innesca il recupero.

**Requirements coperti:** HAND-01, HAND-02, HAND-03, HAND-04, NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04, NOTIF-05, REL-02, REL-03, REL-04.

**Path di esecuzione di questa fase = locale (WebRTC/mic).** La telefonia reale Telnyx (SIP REFER / Dial+Bridge, percorso 8kHz) è **Fase 4**: il trasferimento qui è dietro un seam con **stub locale**, sostituito in Fase 4 senza toccare la logica di business.

**Fuori scope (altre fasi):** meccanica di trasferimento telefonico reale (SIP REFER cold / Dial+Bridge warm) e percorso 8kHz → **Fase 4** (TEL-*); isolamento multi-tenant completo, credential store per-tenant e onboarding CLI → **Fase 5** (TENANT-*); test reale dei canali SMS/WhatsApp con account/numero → quando arrivano le chiavi (Fase 4+); warm transfer reale con bridge → Fase 4 (qui si assembla solo il payload di contesto warm-ready).
</domain>

<decisions>
## Implementation Decisions

### Meccanica del trasferimento (HAND-01..04)
- **D-01:** Il trasferimento sta dietro un **seam `TelephonyProvider.transfer(number)`** (coerente con i seam definiti in Fase 1). Sul **path locale (Fase 3)** è uno **stub**: il bot dice una frase di cortesia ("La metto in contatto con un operatore, resti in linea"), **logga l'intento di trasferimento** verso `transfer_number`, e **chiude la chiamata in modo pulito**; l'esito nel `call_log` è **`trasferito`**. La **Fase 4 sostituisce lo stub con SIP/Dial reale**, zero modifiche alla logica conversazionale. (HAND-01, HAND-04)
- **D-02:** Il trasferimento è **disponibile da qualsiasi punto** come **global function dei Pipecat Flows** (HAND-04) — non un nodo terminale isolato, ma uno strumento invocabile da greeting/booking/faq. Funziona anche **mid-booking-flow** (SC1).
- **D-03:** **Trigger automatici** oltre alla richiesta esplicita:
  - **Non-italiano → trasferimento diretto** (HAND-03): l'LLM/STT riconosce input non-italiano e invoca lo strumento transfer. (Soglia/affidabilità del rilevamento = discrezione planning.)
  - **Incertezza / fuori ambito → trasferimento** (HAND-02): istruzione nel system prompt "in caso di dubbio, trasferisci invece di inventare"; il modello decide via tool.
  - **FAQ-non-trovata → OFFRE il trasferimento** (aggancio rinviato dalla Fase 2 D-08): quando l'info non è nella KB, oltre a "prendere nota" il bot **offre** "vuole che la passi a un operatore?".
- **D-04:** `transfer()` porta un **payload di contesto warm-ready** (riepilogo parziale: chi chiama, cosa voleva, stato del flow). Sul path locale il contesto viene **assemblato e loggato**; la **Fase 4** lo usa per un warm transfer reale senza ridisegnare il seam.

### Contenuto del riepilogo & call log (NOTIF-01/02)
- **D-05:** Il riepilogo al titolare = **breve sintesi in italiano generata dall'LLM** (2-3 frasi: chi ha chiamato, cosa voleva, com'è finita) **+ un blocco strutturato** (esito, dettagli prenotazione, ID/link Calendar). La **trascrizione integrale** vive nel **`call_log` su DB** (allegata/linkata), **non incollata per intero** nella notifica.
- **D-06:** **Tassonomia esito** registrata in `call_log` e usata nell'oggetto della notifica: **`prenotato` / `faq` / `trasferito` / `abbandonato` / `fallito`**. L'esito è **derivato dallo stato finale del flow + dai record DB** (es. reservation `confermata` → `prenotato`; bozza su abbandono → `abbandonato`, coerente con Fase 2 D-18).
- **D-07:** Il riepilogo viene **inviato SEMPRE a fine chiamata**, qualunque sia l'esito — il titolare vede **ogni** chiamata, incluse abbandonate e fallite (utile per follow-up). (NOTIF-02, NOTIF-03)
- **D-08:** Serve una **nuova tabella `call_logs`** — **oggi assente** nello schema (`src/db/schema.sql` ha `tenants`, `reservations`, `kb_documents`, `kb_chunks`). Campi attesi (forma esatta = planning): `tenant_id`, timestamp/durata, **trascrizione integrale**, **esito** (tassonomia D-06), **riferimento alla prenotazione** (`reservation_id` / `google_event_id`) se presente, eventuale numero/intento di trasferimento. Schema strutturato per migrazione Postgres (coerente con il pattern Fase 1/2).

### Canali di notifica (NOTIF-03/04/05)
- **D-09:** **Tutti e quattro i canali dietro l'interfaccia `NotificationChannel`** (già stubbata in `src/interfaces/notification_channel.py`, `async send(subject, body)`), **scelti per-cliente dalla config** (`tenants.notification_channel` già esistente). (NOTIF-03, NOTIF-05)
- **D-10:** Profondità di implementazione in Fase 3:
  - **`log` su DB → REALE**, default/fallback a zero dipendenze (scrive nel `call_log`).
  - **`telegram` → REALE e testabile end-to-end ora** (Bot API, token gratuito, niente numero/costi).
  - **`email` (SMTP via `aiosmtplib`) → implementato in codice**, testato quando arrivano le chiavi SMTP.
  - **`sms`/`whatsapp` → implementati in codice** (provider Telnyx/Twilio/Meta), testati in Fase 4+ con account/numero.
  - **`.env.example` aggiornato** con i placeholder dei nuovi canali + istruzioni passo-passo (coerente con SETUP-01).
- **D-11:** **Default del tenant demo = `log`** (+ `telegram` se un bot token è presente in `.env`), così la fase è provabile end-to-end senza chiavi a pagamento.

### Scala di recupero guasti (REL-02/03/04)
- **D-12:** **Fallback STT faster-whisper (REL-03) in lazy-load**: NON caricato all'avvio (modello pesante/RAM); al **primo guasto/timeout persistente di Deepgram** (oltre il retry slot già gestito dall'`ErrorFallbackObserver`, REL-01), il bot dice la frase di cortesia e **attiva faster-whisper per il resto della chiamata**. Trade-off accettato: piccolo ritardo al primo switch, **mitigato con modello small/int8**.
- **D-13:** **Escalation a trasferimento (REL-02)**: se **anche faster-whisper fallisce** (o un guasto LLM/TTS è persistente senza recupero), il bot pronuncia una frase di cortesia e **trasferisce all'operatore** (via seam D-01), esito `fallito`, senza dead-air oltre pochi secondi (SC4).
- **D-14:** **Watchdog dead-air (REL-04) = re-prompt poi escalation**: al superamento di una soglia di silenzio totale **T1** (né STT in ingresso né TTS in uscita), il bot fa un **re-prompt gentile** ("È ancora in linea?"); se il silenzio **persiste oltre T2**, innesca la **sequenza di recupero → trasferimento** (esito `fallito`). Distingue il chiamante pensieroso dal guasto reale. **T1/T2 esatte = discrezione planning** (punto di partenza ~6s re-prompt, ~+8s escalation). (SC5)

### Claude's Discretion
- **Wording esatto** delle frasi: cortesia su switch STT, re-prompt watchdog, offerta di trasferimento, frase di handoff.
- **Soglie numeriche**: T1/T2 del watchdog (D-14); numero di retry/timeout prima di considerare un guasto "persistente" (D-12/D-13), partendo dal retry slot già esistente in `fallback.py`.
- **Schema esatto di `call_logs`** (D-08): nomi colonne, dove vive la trascrizione (campo TEXT vs tabella separata di turni), formato dell'esito — mantenere coerenza col pattern `aiosqlite` + SQL parametrizzato dietro repository (Fase 1/2).
- **Meccanismo preciso dello switch STT mid-call** in Pipecat 1.4.0 (come sostituire il servizio STT nel pipeline a runtime / quale processore-slot) — da verificare in research/planning sulla doc Pipecat.
- **Modello e formato della sintesi LLM** del riepilogo (D-05): quale modello (Haiku vs Sonnet), prompt, lunghezza.
- **Meccanismo di rilevamento "non-italiano"** (D-03): confidenza STT / language hint / giudizio LLM — set minimo garantito = il modello riconosce input non-italiano e trasferisce.
- **Provider concreto** per SMS/WhatsApp (D-10): Telnyx Messaging vs Twilio vs Meta WhatsApp — scelta differibile, dietro l'interfaccia.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning docs
- `.planning/PROJECT.md` — visione, vincoli stack vincolanti, Key Decisions (layer telefonia dietro interfaccia con Telnyx prima impl.; layer notifiche multi-canale configurabile per-cliente).
- `.planning/REQUIREMENTS.md` — definizione **HAND-01..04**, **NOTIF-01..05**, **REL-02/03/04** (REL-01 già Complete in Fase 1).
- `.planning/ROADMAP.md` §"Phase 3: Handoff + Summary + Notifications" — goal e 5 success criteria (SC1 transfer da qualsiasi punto incl. mid-booking; SC2 riepilogo sul canale configurato; SC3 guasto Deepgram → cortesia + switch faster-whisper senza interrompere; SC4 guasto persistente → cortesia + transfer, niente dead-air >pochi secondi; SC5 watchdog dead-air → recovery/transfer automatico).
- `.planning/STATE.md` §Accumulated Context — decisioni Fase 1/2 (seam NotificationChannel/CalendarProvider/TransportFactory definiti in Fase 1; ErrorFallbackObserver via `observers=` non PipelineParams; bozza su abbandono Fase 2 D-18).
- `.planning/phases/01-local-voice-loop/01-CONTEXT.md` — decisioni Fase 1 portate avanti (seam dietro interfacce, TenantConfig tipato, pipeline streaming, courtesy-phrase REL-01).
- `.planning/phases/02-booking-calendar-faq/02-CONTEXT.md` — Fase 2: D-08 (FAQ info-assente, gancio transfer rinviato QUI), D-18 (bozza su abbandono → esito `abbandonato`), persona "Lei"/receptionist, pattern repository `aiosqlite`.

### Research del progetto (MUST read — pitfall di affidabilità di questa fase)
- `.planning/research/PITFALLS.md` §Pitfall 8 (provider falliscono SENZA ErrorFrame → bot muto/dead-air; Deepgram droppa ~1/50, ElevenLabs reconnect loop, STT websocket muore dopo 60-70s di silenzio; serve **health-check + circuit breaker + timeout + dead-air watchdog**, switch a faster-whisper su guasto STT, cortesia + transfer su guasto LLM/TTS). §Pitfall 11 / §Telnyx (cold = SIP REFER, **warm = Dial+Bridge** da costruire → il payload warm-ready D-04 prepara questo per la Fase 4). §sezione sicurezza: **transfer/notification number MAI da payload del chiamante → risolvere da config fidata** (T-injection).
- `.planning/research/ARCHITECTURE.md` §Conversation orchestration (nodi greeting/booking/faq/**handoff/end**, `transfer_call` tool, **handoff escape sempre disponibile**), §Domain services (`NotificationChannel` impls Email/SMS/WhatsApp/Telegram + **log come default zero-dipendenze**), §End-of-call flow ("on end: assemble summary (transcript + outcome + reservation?) → NotificationChannel.send(owner, summary)"), §Fallback flow ("STT/LLM/TTS error → courtesy phrase → retry once → if still failing, transfer to human").

### Codice esistente (seam da estendere)
- `src/interfaces/notification_channel.py` — interfaccia `NotificationChannel` (stub Fase 1, `async send(subject, body)`) da implementare con i 4 canali (D-09/D-10).
- `src/pipeline/fallback.py` — `ErrorFallbackObserver` (REL-01): frase di cortesia su ErrorFrame non-fatale + retry slot per source; **base su cui costruire l'escalation** verso faster-whisper (D-12) e transfer (D-13). Vincolo V7/T-03-LOG: mai loggare `ErrorFrame.error`.
- `src/bot.py` — wiring di worker/observer/FlowManager + `on_client_disconnected` (bozza su abbandono D-18); qui si innestano il watchdog, l'hook di fine-chiamata (summary + notifica) e il global transfer tool.
- `src/flows/nodes.py`, `src/flows/functions.py` — nodi e `FlowsFunctionSchema`/handler dei Flows; aggiungere lo **strumento transfer come global function** (HAND-04) e l'aggancio FAQ-non-trovata (D-03).
- `src/db/schema.sql` — schema attuale (`tenants` con `transfer_number` + `notification_channel` GIÀ presenti; `reservations`; `kb_*`); **manca la tabella `call_logs`** (D-08).
- `src/config/tenant_config.py` — `TenantConfig` Pydantic con `transfer_number` e `notification_channel` già presenti (nullable); 1:1 con la riga DB.
- `CLAUDE.md` — versioni Pipecat 1.4.0 / Flows 1.3.0, "What NOT to Use", nota model-id, faster-whisper (`WhisperSTTService`, `Model.LARGE_V3_TURBO`/`LARGE`, `language=Language.IT`, CPU `int8`).

### Stack / framework (da consultare in research — non installato come MCP/skill in sessione)
- Pipecat 1.4.0 — `WhisperSTTService` (faster-whisper, modello + `language=IT`, lazy init), meccanismo di **switch STT a runtime** nel pipeline; pattern watchdog/idle-timeout su silenzio; `TTSSpeakFrame` per frasi di cortesia.
- Pipecat Flows 1.3.0 — **global/edge functions** per un transfer invocabile da qualsiasi nodo (HAND-04); hook/azioni di fine-nodo per innescare il summary.
- Telegram Bot API (token gratuito) — canale `telegram` reale (D-10); `aiosmtplib` per SMTP (D-10); provider SMS/WhatsApp (Telnyx Messaging / Twilio / Meta) differiti.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/interfaces/notification_channel.py`: interfaccia `NotificationChannel` già definita (`async send(subject, body)`) — la Fase 3 aggiunge i 4 canali concreti dietro di essa, niente restructuring (D-09).
- `src/pipeline/fallback.py`: `ErrorFallbackObserver` con frase di cortesia + retry slot per source (REL-01) — la base su cui innestare l'escalation faster-whisper (D-12) e transfer (D-13).
- `src/bot.py`: wiring di `PipelineWorker(observers=[...])`, `FlowManager`, e `on_client_disconnected` (bozza su abbandono) — punti di innesto per watchdog, fine-chiamata e global transfer tool.
- `src/config/repository.py` + pattern `aiosqlite` con SQL parametrizzato (Fase 1/2) — riusare per `CallLogRepository`.
- `tenants.transfer_number` e `tenants.notification_channel` GIÀ nello schema e in `TenantConfig` — niente migrazione per questi due campi.

### Established Patterns
- Seam dietro interfacce (Fase 1): ogni integrazione esterna sta dietro un'interfaccia; transfer (`TelephonyProvider`) e notifiche (`NotificationChannel`) seguono lo stesso pattern.
- Repository su `aiosqlite` + SQL parametrizzato, strutturato per migrazione Postgres (cambio connection-string) — vale anche per `call_logs`.
- Tool/funzioni LLM gated dai nodi Flows; il transfer è una **global function** (eccezione voluta: deve essere raggiungibile da ovunque, HAND-04).
- Config tipata Pydantic 1:1 con la riga DB; selezione comportamento per-tenant da campi config (es. `notification_channel`).
- Sicurezza: numeri di transfer/notifica risolti SOLO da config fidata, MAI da input del chiamante (T-injection); `ErrorFrame.error` mai loggato (V7/T-03-LOG).

### Integration Points
- **Fine chiamata** (hook su disconnect / end node): assembla la trascrizione dal context → genera sintesi LLM (D-05) → scrive `call_log` con esito (D-06) → `NotificationChannel.send()` sul canale del tenant (D-07/D-09).
- **Global transfer tool** nei Flows (HAND-04): invocabile da greeting/booking/faq; risolve `transfer_number` dalla config; assembla payload warm-ready (D-04); chiama `TelephonyProvider.transfer()` (stub locale, D-01).
- **Escalation STT** (D-12/D-13): estende `ErrorFallbackObserver` / pipeline per fare lazy-load di `WhisperSTTService` e switch a runtime su guasto Deepgram persistente; ulteriore guasto → transfer.
- **Watchdog dead-air** (D-14): nuovo osservatore/idle-timer che monitora assenza di STT-in e TTS-out; re-prompt a T1, recovery/transfer a T2.
- **Nuova tabella `call_logs`** nello schema + `CallLogRepository`; nuovo canale Telegram reale + SMTP/SMS/WhatsApp in codice; `.env.example` esteso (D-08/D-10).

### Concerns / Open
- **Switch STT a runtime in Pipecat 1.4.0**: il meccanismo esatto per sostituire il servizio STT mid-pipeline va verificato sulla doc (potrebbe richiedere un processore wrapper / due STT con routing). MEDIUM — da chiarire in research/planning.
- **faster-whisper su Windows/dev locale**: `ctranslate2` CPU `int8`; il primo lazy-load aggiunge latenza — confermare tempi accettabili sul dev box.
</code_context>

<specifics>
## Specific Ideas

- Frase di handoff: "La metto in contatto con un operatore, resti in linea."
- Frase di cortesia su switch STT: tipo "Un momento, c'è un problema tecnico…".
- Re-prompt watchdog: "È ancora in linea?"; se persiste: "Non riesco a sentirla, la passo a un operatore."
- Offerta transfer su FAQ-non-trovata: "Non ho questa informazione, vuole che la passi a un operatore?" (estende il "prendo nota" della Fase 2 D-08).
- Oggetto notifica esempio: "Chiamata 26/06 20:14 - Prenotazione confermata"; corpo = 2-3 frasi sintesi + blocco strutturato (esito, prenotazione, event id Calendar), trascrizione completa nel log.
- Esiti call_log: `prenotato` / `faq` / `trasferito` / `abbandonato` / `fallito`.
- Default demo: canale `log` (+ `telegram` se token in `.env`).
- Ladder affidabilità: Deepgram → (guasto persistente) cortesia + faster-whisper lazy → (ancora guasto) cortesia + transfer; watchdog: silenzio>T1 re-prompt, >T2 transfer.

</specifics>

<deferred>
## Deferred Ideas

- **Meccanica di trasferimento telefonico reale** (cold SIP REFER / warm Dial+Bridge) e percorso 8kHz → **Fase 4** (TEL-*). In Fase 3 il transfer è stub locale dietro seam, ma assembla già il payload warm-ready (D-04).
- **Test reale dei canali SMS/WhatsApp** (account/numero, costi) → quando arrivano le chiavi, indicativamente Fase 4+. Il codice è scritto in Fase 3 dietro l'interfaccia.
- **Isolamento multi-tenant completo + credential store per-tenant** per i canali di notifica e i numeri di transfer → **Fase 5** (TENANT-*). In Fase 3 si risolve da config fidata, single-process.
- **Warm transfer reale con briefing vocale all'operatore** (l'agente riassume prima di bridgiare) → **Fase 4** (richiede Dial+Bridge / call-control), v2 per il "warm" avanzato (BOOKV2-02).
- **Tuning fine di soglie/latenza della ladder fallback** sul percorso telefonico reale → re-test in **Fase 4** (le soglie locali sono un punto di partenza).

None oltre a quanto sopra — la discussione è rimasta nello scope della fase.

</deferred>

---

*Phase: 3-Handoff + Summary + Notifications*
*Context gathered: 2026-06-26*
