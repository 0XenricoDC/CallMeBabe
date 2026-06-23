# Phase 1: Local Voice Loop - Context

**Gathered:** 2026-06-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Un agente vocale che conversa in **italiano** *in locale* (microfono/cuffie, nessuna telefonia) attraverso una pipeline **streaming** Deepgram (STT) → Claude (LLM, tool-calling) → ElevenLabs (TTS), con:
- saluto personalizzato preso dalla config del tenant (il bot parla per primo),
- barge-in / gestione interruzioni,
- strumentazione di latenza per-stage a verifica del budget <800ms end-to-end,
- frasi di cortesia in italiano quando un provider STT/LLM/TTS fallisce (no dead-air),
- i seam di interfaccia (`TenantConfig`, `TransportFactory`, `STTProvider`, e gli stub di `CalendarProvider`/`NotificationChannel`) definiti perché le fasi successive aggiungano file dietro interfacce.

**Requirements coperti:** VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05, REL-01, SETUP-01.

**Fuori scope (altre fasi):** flussi di prenotazione e scrittura calendario (Fase 2), FAQ/RAG (Fase 2), trasferimento operatore (Fase 3), failover STT automatico a faster-whisper + watchdog dead-air (Fase 3), telefonia Telnyx / percorso 8kHz (Fase 4), onboarding CLI e isolamento multi-tenant completo (Fase 5).
</domain>

<decisions>
## Implementation Decisions

### Persistenza & config del tenant
- **D-01:** La config del tenant è persistita in **SQLite via `aiosqlite` fin dalla Fase 1** (non file JSON), dietro un'interfaccia di repository, con il codice strutturato per migrare a Postgres (cambio connection-string).
- **D-02:** La tabella `tenants` modella **da subito lo schema completo a colonne nullable** (campi noti dal PROJECT: `business_name`, `greeting`, `voice_id`, `language`, `system_prompt`, `model`, `hours`, `services`, `booking_rules`, `transfer_number`, `kb_ref`, `notification_channel`). In Fase 1 si popolano solo i campi rilevanti per la voce; nessun ALTER TABLE fase per fase.
- **D-03:** La config viene caricata a inizio chiamata e iniettata nel motore come **modello tipato** (`TenantConfig`, Pydantic) — è il seam che le Fasi 2–5 estendono.
- **D-04:** Tenant di Fase 1 = `demo`, eseguito con `python main.py --tenant=demo`.

### Esecuzione & trasporto locale
- **D-05:** Trasporto locale = **Pipecat runner + `SmallWebRTCTransport`** (browser su pagina localhost, mic del browser). Niente dipendenze audio native su Windows; stessa pipeline che in Fase 4 regge Telnyx cambiando solo il transport. Il trasporto sta dietro un seam `TransportFactory`.

### Strumentazione latenza
- **D-06:** Le metriche di latenza per-stage (STT-final, LLM TTFT, TTS TTFB, transport) si appoggiano alle **metriche native Pipecat** (`enable_metrics`) e vengono emesse **sia** come riga riassuntiva leggibile in console a ogni turno (es. `turn=620ms | stt=180 llm_ttft=240 tts_ttfb=160 transport=40`) **sia** come **log JSONL** su file per analisi/aggregati successivi.

### Fallback / affidabilità (REL-01)
- **D-07:** Su errore o timeout di STT/LLM/TTS: **un singolo retry rapido** dove sicuro; se fallisce ancora, una **frase di cortesia generica in italiano** (es. "Mi scusi, ho avuto un problema tecnico, può ripetere?"). Niente frasi differenziate per-stage in Fase 1.
- **D-08:** Esiste un seam **`STTProvider`** con **Deepgram come implementazione attiva di default**; in più, in Fase 1 si cabla `WhisperSTTService` (faster-whisper) **selezionabile da config**, **senza** failover automatico (lo switch automatico Deepgram→Whisper è REL-03, Fase 3). ⚠ Implica già in Fase 1 le dipendenze ML pesanti (`faster-whisper`/`ctranslate2`) — da gestire in setup.

### Persona & comportamento conversazionale
- **D-09:** Persona = **receptionist vincolato**: il bot si presenta come centralino dell'attività demo, conversa in italiano naturale e, se gli si chiede di prenotare o info specifiche non disponibili, risponde che la funzione arriverà a breve (non promette ciò che non esiste ancora). Definisce il `system_prompt` del tenant demo.

### LLM
- **D-10:** Campo **`model` nella config del tenant**, default **`claude-haiku-4-5`** in Fase 1 (TTFT basso, adatto a voce real-time entro 800ms), sovrascrivibile per-tenant (es. Sonnet dove servirà più qualità dalla Fase 2) senza modifiche al codice.

### Apertura conversazione / barge-in
- **D-11:** Il bot **parla per primo** pronunciando il saluto personalizzato appena la connessione è pronta, e il **barge-in è attivo già durante il saluto** (il chiamante può interrompere il saluto stesso; il bot si ferma e ascolta).

### Setup / chiavi (SETUP-01)
- **D-12:** `.env.example` contiene **solo le chiavi della Fase 1** (`DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`) ognuna con commento inline su dove ottenerla; le **istruzioni passo-passo di creazione account** vivono in una **sezione del README**. Nessuna chiave hardcoded; tutto via `.env`.

### Claude's Discretion
- **Tuning VAD/endpointing** (parametri Silero VAD `stop_secs`/soglie): lasciato a ricerca/planning. Vincolo noto: `aggregation_timeout` 0.1–0.3s (il default ~1s sfonda gli 800ms).
- Wording esatto delle frasi di cortesia e del saluto demo; struttura precisa del file JSONL e percorso; eventuale soglia di warning quando un turno supera gli 800ms.
- Modalità esatta di cablaggio dei seam stub `CalendarProvider`/`NotificationChannel` (devono solo esistere come interfacce in Fase 1, non funzionanti).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning docs
- `.planning/PROJECT.md` — visione, vincoli stack vincolanti, Key Decisions.
- `.planning/REQUIREMENTS.md` — definizione VOICE-01..05, REL-01, SETUP-01 (e v2/out-of-scope).
- `.planning/ROADMAP.md` §"Phase 1: Local Voice Loop" — goal e 5 success criteria.
- `.planning/STATE.md` §Accumulated Context — decisioni di roadmap (streaming non negoziabile, `aggregation_timeout` 0.1–0.3s, seam da definire in Fase 1).
- `CLAUDE.md` — nota versioni Pipecat 1.x + superficie di integrazione esatta (STT/LLM/TTS/transport), "What NOT to Use", model-id note.

### Stack / framework (da consultare in ricerca — non installato come MCP/skill in sessione)
- Pipecat 1.4.0 docs (docs.pipecat.ai) — pipeline 1.x, `SmallWebRTCTransport`/runner, `enable_metrics`, `SileroVADAnalyzer`, `DeepgramSTTService`, `AnthropicLLMService`, `ElevenLabsTTSService`, `WhisperSTTService`.
- Pipecat Flows 1.3.0 (import `pipecat_flows`) — rilevante da Fase 2, non in Fase 1.

*Nessun ADR/spec esterno aggiuntivo: i requisiti sono catturati nelle decisioni sopra e nei doc di planning.*
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Nessuno — progetto greenfield. Solo `CLAUDE.md`, `.planning/`, e una cartella `lancedb/` non pertinente alla Fase 1. La Fase 1 crea la struttura di base (`main.py`, config repo, seam delle interfacce, pipeline).

### Established Patterns
- Nessun pattern di codice preesistente. I pattern di questa fase (seam dietro interfacce, config tipata, pipeline streaming) diventeranno il riferimento per le fasi successive.

### Integration Points
- `main.py --tenant=<id>` → carica `TenantConfig` da repository SQLite → costruisce pipeline via `TransportFactory` (WebRTC) + `STTProvider` (Deepgram|Whisper) → LLM Claude (`model` da config) → ElevenLabs (`voice_id` da config).
- Seam definiti ora ma non funzionanti: `CalendarProvider` (Fase 2), `NotificationChannel` (Fase 3), oltre a `TransportFactory` per il futuro swap Telnyx (Fase 4).
</code_context>

<specifics>
## Specific Ideas

- Riga di latenza per-turno human-readable in console, sul modello `turn=620ms | stt=180 llm_ttft=240 tts_ttfb=160 transport=40`.
- Frase di cortesia tipo "Mi scusi, ho avuto un problema tecnico, può ripetere?".
- Persona demo = centralino di un'attività italiana che si presenta e dice che prenotazioni/info dettagliate arriveranno a breve.
</specifics>

<deferred>
## Deferred Ideas

- **Failover STT automatico Deepgram→faster-whisper** + watchdog dead-air → Fase 3 (REL-02, REL-03, REL-04). In Fase 1 solo seam + selezione manuale da config.
- **Frasi di cortesia differenziate per-stage** → eventuale evoluzione successiva; in Fase 1 frase generica unica.
- **Chiavi future** (`TELNYX_*`, `GOOGLE_*`) in `.env.example` → si aggiungono nelle rispettive fasi (4 e 2), non ora.
- **Sonnet/altri modelli per-tenant** → abilitato dal campo `model` configurabile; uso effettivo valutato dalla Fase 2 in poi.

None oltre a quanto sopra — la discussione è rimasta nello scope della fase.
</deferred>

---

*Phase: 1-Local Voice Loop*
*Context gathered: 2026-06-23*
