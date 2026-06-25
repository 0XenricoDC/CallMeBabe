# Phase 2: Booking + Calendar + FAQ - Context

**Gathered:** 2026-06-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Un chiamante completa una **prenotazione vocale in italiano** end-to-end via **Pipecat Flows** — fornendo data, ora, numero di persone, nome e telefono — e la prenotazione compare nel **Google Calendar reale del cliente giusto** solo **dopo** che il chiamante ha confermato verbalmente il read-back e **solo se** lo slot rientra nella capienza. In parallelo: **FAQ per-cliente** in italiano via RAG semplice, ancorate alla knowledge base del tenant, senza inventare dati.

**Requirements coperti:** BOOK-01, BOOK-02, BOOK-03, BOOK-04, BOOK-05, BOOK-06, FAQ-01, FAQ-02, FAQ-03.

**Vincoli di correttezza già stabiliti (research) — non rimetterli in discussione:**
- La **capienza autoritativa vive nel DB del progetto**, con **check-and-insert transazionale** (unique constraint / optimistic lock). Google Calendar è la **proiezione**, non il lock — Google non ha check-and-reserve atomico (PITFALL 7).
- La **conferma vocale avviene solo dopo che `create_event` ritorna un event id reale**, con **gating via Pipecat Flows** (BOOK-05, PITFALL 6). Il modello non auto-conferma mai una prenotazione o una disponibilità senza il risultato dello strumento.
- **Timezone Europe/Rome** ovunque; **read-back obbligatorio** dei campi critici prima della scrittura (PITFALL 5).

**Fuori scope (altre fasi):** trasferimento vero a operatore umano (Fase 3, HAND-*), riepilogo/notifiche di fine chiamata (Fase 3, NOTIF-*), failover STT automatico + watchdog dead-air (Fase 3, REL-*), telefonia Telnyx / percorso 8kHz (Fase 4), onboarding CLI e isolamento multi-tenant completo + credential store per-tenant (Fase 5), logica avanzata di combinazione tavoli (v2, BOOKV2-01), RAG con embedding/vector store (v2, FAQV2-01), trasferimento "warm" con briefing (v2, BOOKV2-02).
</domain>

<decisions>
## Implementation Decisions

### Vertical & modello di capienza
- **D-01:** Il **tenant demo della Fase 2 è un ristorante a coperti** (allineato al goal del roadmap "party size"). La prenotazione raccoglie data + ora + n. persone + nome + telefono. (BOOK-01)
- **D-02:** La capienza si modella come **coperti totali per fascia oraria**: più prenotazioni nello stesso slot si sommano fino a un limite configurato. La verifica è la **somma dei coperti già prenotati + i nuovi < limite**, eseguita come check-and-insert transazionale (unique/optimistic lock sul conteggio dello slot). La logica di combinazione tavoli è rinviata a v2 (BOOKV2-01). (BOOK-02)
- **D-03:** Orari di apertura, **durata slot fissa** (es. 30 min) e **coperti-per-slot** vivono nella **config del tenant** (campi `hours` / `booking_rules` già presenti nello schema). La **durata di occupazione della prenotazione è fissa** (non per-tenant variabile in v1). Niente codice per cambiare ristorante — solo config.

### Esito "slot pieno" & proposta alternative (SC2)
- **D-04:** Quando lo slot richiesto è al completo, il bot **propone le 2-3 fasce libere più vicine nello stesso giorno** (es. "Le 20:00 sono al completo, ho posto alle 19:00 o alle 21:30"), interrogando il DB autoritativo. Nessun evento calendario creato, nessuna falsa conferma (SC2).
- **D-05:** Se nel giorno richiesto **non** ci sono alternative vicine, il bot **propone la prima disponibilità nei giorni successivi** (es. "domani sera alle 20:00"). Profondità esatta della ricerca (quante proposte, quanti giorni avanti) = discrezione planning, partendo da questo comportamento.

### FAQ / Knowledge base
- **D-06:** Modello FAQ **ibrido**: **orari e servizi** rispondono direttamente dai **campi config strutturati** del tenant (`hours`, `services` già nello schema); **indirizzo, prezzi e tutto il resto** vivono in una **KB testuale per-tenant indicizzata in SQLite FTS5** (keyword search). (FAQ-01, FAQ-03)
- **D-07:** Il **retrieval è SQLite FTS5** (keyword, top-k chunk) — **niente embedding/vector store in v1** (differito a v2, FAQV2-01). La KB è esposta come **tool LLM** ("faq_lookup") invocabile dal nodo FAQ dei Flows. *(Nota: la cartella `lancedb/` nel repo è residua e NON pertinente.)*
- **D-08:** Quando l'informazione **non è nella KB**, il bot **lo ammette onestamente e offre di prendere nota / far ricontattare** (es. "Non ho questa informazione al momento, posso prendere nota e farla ricontattare"). Niente invenzioni (FAQ-02). Il **trasferimento vero all'operatore arriva in Fase 3** (HAND-*); qui resta una cortesia/nota.

### Google Calendar: auth & isolamento
- **D-09:** Autenticazione tramite **service account unico**: una credenziale service-account JSON **globale** (via `.env` / file montato), non OAuth per-tenant. L'owner del ristorante **condivide il proprio Google Calendar con l'email del service account**. Nessun flusso OAuth né token-refresh per-tenant in v1 (OAuth/credential store per-tenant è tema della Fase 5).
- **D-10:** **Isolamento per calendario dedicato**: ogni tenant ha un **`calendar_id` distinto** e la prenotazione viene scritta **solo lì** (il booking finisce nel calendario del cliente giusto, SC1). Niente calendario condiviso con tag.
- **D-11:** Serve una **nuova colonna `calendar_id`** (nullable) nella tabella `tenants` — **oggi assente nello schema** (`src/db/schema.sql`). Va aggiunta in Fase 2; valutare anche dove vive il riferimento alla credenziale service-account (globale via env vs ref per-tenant). Nota: l'intento D-02 della Fase 1 ("schema completo dal giorno 1, niente ALTER per fase") qui va integrato con questo campo mancante.
- **D-12:** Implementazione reale **`GoogleCalendarProvider` dietro l'interfaccia `CalendarProvider`** già stubbata in `src/interfaces/calendar_provider.py` (metodi `check_availability` / `create_event` → ritorna event id). Prevedere un'impl in-memory per i test (`InMemoryCalendarProvider`).

### Flussi conversazionali (Pipecat Flows)
- **D-13:** Conversazione orchestrata come **grafo di nodi Pipecat Flows** (greeting → booking → faq), ogni nodo espone **solo i tool che gli servono** (evita il monoprompt con tutti i tool → riduce allucinazioni). Handler delle funzioni: `collect_*`, `check_availability`, `create_event`/`book`, `faq_lookup`. La conferma "prenotato" è guidata **dal risultato del tool**, non dal modello (D-gating BOOK-05).
- **D-14:** Una prenotazione confermata è **persistita nel DB del progetto** (record `reservation`) oltre che scritta su Calendar (BOOK-06) — il DB è la fonte autoritativa della capienza, il Calendar la proiezione.

### Claude's Discretion
- **Modello Claude per il path booking**: il campo `model` per-tenant esiste già (default `claude-haiku-4-5`). Se serve più affidabilità nel tool-calling del booking, valutare in planning Sonnet per il tenant demo — temperatura bassa + max_tokens stretti sul path booking (PITFALL 6).
- **Design conversazionale della raccolta dati**: gestione date relative ("domani", "venerdì prossimo"), normalizzazione orari ("le otto" → 20:00), **conferma del telefono cifra-per-cifra / spelling del nome su bassa confidenza** (PITFALL 5 raccomanda read-back e spelling). Ordine esatto di raccolta dei campi.
- **Wording esatto** di read-back, frasi "slot pieno", proposta alternative, e risposta "info assente".
- **Granularità slot e formato `booking_rules`** (D-03): partire da slot fissi semplici.
- **Schema persistenza** (`reservations`, `kb_documents`/`kb_chunks`): la ricerca suggeriva SQLAlchemy, ma la Fase 1 ha usato `aiosqlite` + SQL parametrizzato dietro repository. Mantenere coerenza col pattern Fase 1 salvo motivazione contraria in planning.
- **Profondità ricerca alternative** (D-05): quante proposte, quanti giorni in avanti.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning docs
- `.planning/PROJECT.md` — visione, vincoli stack vincolanti, Key Decisions (prenotazioni con verifica capienza + Google Calendar reale già in questa fase).
- `.planning/REQUIREMENTS.md` — definizione **BOOK-01..06**, **FAQ-01..03**; sezione v2 (FAQV2-01 embedding differito, BOOKV2-01 combinazione tavoli differita) e Out of Scope.
- `.planning/ROADMAP.md` §"Phase 2: Booking + Calendar + FAQ" — goal e 5 success criteria (SC1 conferma solo dopo event id; SC2 alternative; SC3 booking concorrente → esattamente una conferma; SC4/SC5 FAQ ancorata e per-tenant).
- `.planning/STATE.md` §Accumulated Context — flag MEDIUM Fase 2 (freebusy inversion, schema reserve transazionale); decisioni di roadmap (seam definiti in Fase 1).
- `.planning/phases/01-local-voice-loop/01-CONTEXT.md` — decisioni Fase 1 portate avanti (TenantConfig tipato D-03, schema `tenants` nullable D-02, pipeline streaming, model per-tenant D-10).

### Research del progetto (MUST read — pitfall di correttezza di questa fase)
- `.planning/research/PITFALLS.md` §Pitfall 5 (STT su numeri/date/orari/nomi → read-back obbligatorio), §Pitfall 6 (Claude allucina conferme/disponibilità → gating Flows tool-driven), §Pitfall 7 (race double-booking Google Calendar → capienza autoritativa nel DB + check-and-insert transazionale, freebusy = busy array, timezone Europe/Rome).
- `.planning/research/ARCHITECTURE.md` §Conversation orchestration / §Domain services — `FlowManager` nodi greeting/booking/faq/handoff, `CalendarProvider` (`GoogleCalendarProvider` reale + `InMemoryCalendarProvider` test), `KB/RAG` = SQLite FTS5 con `KnowledgeBase` protocol (`search(tenant, query) -> chunks`), struttura `data/tenants/<slug>/kb/`, tabelle `reservations` / `kb_documents` / `kb_chunks`.
- `.planning/research/FEATURES.md`, `.planning/research/STACK.md`, `.planning/research/SUMMARY.md` — contesto ecosistema e stack (Pipecat Flows, Google Calendar API, FTS5).

### Codice esistente (seam da estendere)
- `src/interfaces/calendar_provider.py` — interfaccia `CalendarProvider` (stub Fase 1) da implementare con `GoogleCalendarProvider`.
- `src/db/schema.sql` — schema `tenants`; **manca la colonna `calendar_id`** (D-11) e mancano le tabelle `reservations` / `kb_documents`/`kb_chunks`.
- `src/config/tenant_config.py` — modello `TenantConfig` Pydantic 1:1 con la riga DB (va esteso con `calendar_id`).
- `src/pipeline/build.py` — assembla la pipeline streaming; qui si innestano i Pipecat Flows (nodo booking/faq + tool).
- `CLAUDE.md` — versioni Pipecat 1.4.0 / Pipecat Flows 1.3.0 (import `pipecat_flows`), superficie integrazione, "What NOT to Use", nota model-id.

### Stack / framework (da consultare in ricerca — non installato come MCP/skill in sessione)
- Pipecat Flows 1.3.0 docs (import `pipecat_flows`) — `FlowManager`, nodi, `FlowsFunctionSchema`, handler `(result, next_node)`, `flow_manager.state`.
- Google Calendar API (`google-api-python-client` + `google-auth`) — service account, `events.insert`, `freebusy.query` (interpretazione `busy` array), timezone Europe/Rome.
- SQLite FTS5 — virtual table per il keyword search della KB.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/interfaces/calendar_provider.py`: interfaccia `CalendarProvider` già definita (`check_availability`, `create_event` → event id) — la Fase 2 aggiunge `GoogleCalendarProvider` dietro di essa, niente restructuring.
- `src/config/tenant_config.py` + `src/db/schema.sql`: modello tipato + schema `tenants` con campi già presenti (`hours`, `services`, `booking_rules`, `kb_ref`) riusabili per capienza/FAQ; vanno estesi con `calendar_id`.
- `src/config/repository.py`: pattern repository su `aiosqlite` con SQL parametrizzato (Fase 1) — riusare lo stesso pattern per `ReservationRepository` / KB.
- `src/pipeline/build.py`: pipeline streaming e `LLMContext`/aggregatori già montati — i Flows si innestano qui senza riscrivere la pipeline.

### Established Patterns
- Seam dietro interfacce (Fase 1): ogni integrazione esterna sta dietro un'interfaccia; il booking segue lo stesso pattern (`CalendarProvider`, `KnowledgeBase`).
- Config tipata Pydantic 1:1 con la riga DB (`TenantConfig(**dict(row))`) — estendere con `calendar_id` mantenendo l'1:1.
- Repository su `aiosqlite` + SQL parametrizzato, strutturato per migrazione Postgres (cambio connection-string).
- Tool/funzioni LLM gated dai nodi Flows (decisione architetturale per evitare allucinazioni).

### Integration Points
- `build_pipeline()` → innesto del `FlowManager` con nodi greeting→booking→faq; i tool handler chiamano `CalendarProvider` (Google) e `KnowledgeBase` (FTS5) e ritornano `(result, next_node)`.
- Nuova colonna `tenants.calendar_id` + nuove tabelle `reservations`, `kb_documents`/`kb_chunks` nello schema; nuovo seed/ingest KB per il tenant demo (`data/tenants/<slug>/kb/`).
- Credenziale service-account Google via `.env` (nuova chiave `GOOGLE_*` da aggiungere a `.env.example`, prima differita dalla Fase 1).
</code_context>

<specifics>
## Specific Ideas

- Read-back tipo: "Confermo: martedì 8 luglio, ore 20, per 4 persone, a nome Rossi, telefono …" prima di scrivere (PITFALL 5).
- Slot pieno: "Le 20:00 sono al completo, ho disponibilità alle 19:00 o alle 21:30, le va bene una di queste?" → se giorno pieno: "domani sera alle 20:00".
- Info FAQ assente: "Non ho questa informazione al momento, posso prendere nota e farla ricontattare."
- Regola system prompt booking: "Mai confermare una prenotazione o una disponibilità senza il risultato dello strumento. Se lo strumento non risponde, di' che verifichi."
- Capienza = coperti totali per fascia (es. max 40 coperti per slot), somma transazionale.
</specifics>

<deferred>
## Deferred Ideas

- **Altri vertical (hotel/B&B a camere, studio medico ad appuntamenti)** — la Fase 2 implementa il ristorante a coperti; gli altri vertical riusano lo stesso motore via config, ma la modellazione (camere/notti, appuntamenti per professionista) si valuta in fasi/iterazioni successive.
- **Logica avanzata di combinazione tavoli / capienza complessa** → v2 (BOOKV2-01).
- **RAG con embedding/vector store** → v2 (FAQV2-01), solo se FTS5 keyword non basta per la recall.
- **OAuth Google per-tenant + credential store isolato** → Fase 5 (TENANT-06); in Fase 2 service account unico.
- **Trasferimento vero all'operatore** (incl. il gancio dal "info assente" FAQ e dalla bassa confidenza) → Fase 3 (HAND-*).
- **Trasferimento "warm" con briefing** → v2 (BOOKV2-02).
- **Durata occupazione tavolo per-tenant variabile** → oltre la v1 (in v1 durata fissa).

None oltre a quanto sopra — la discussione è rimasta nello scope della fase.
</deferred>

---

*Phase: 2-Booking + Calendar + FAQ*
*Context gathered: 2026-06-25*
