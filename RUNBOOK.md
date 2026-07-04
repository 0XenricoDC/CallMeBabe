# 🛠️ RUNBOOK — Centralino AI

Guida operativa rapida: come avviare, provare e testare il bot.
**Questo file viene aggiornato man mano che il progetto avanza.**

> Ultimo aggiornamento: 2026-07-04 (sera) — Verifica live Fase 3 chiusa: SC1/SC2 ✅, SC3 core ✅ con 1 bug killer fixato (139 test verdi + 1 skip), SC4 skipped, SC5 osservato. Difetti residui annotati nella checklist. **Prossimo passo: Fase Telefonia Telnyx** (parte con la sessione di ricerca dedicata — flag HIGH in `.planning/research/`).

---

## ⚡ TL;DR — provare il bot in 3 passi

```bash
# 1. (una volta) seed del tenant demo nel database
.venv/Scripts/python -m src.db.seed_demo

# 2. avvia il bot
.venv/Scripts/python main.py --tenant=demo

# 3. apri nel browser e consenti il microfono:
#    http://localhost:7860/client/
```

Il bot ti saluta da solo in italiano (Ristorante Da Mario), poi puoi conversarci.
Per **fermarlo**: CTRL+C nel terminale.

---

## 🌐 Link utili

| Cosa | URL |
|------|-----|
| **Pagina di test del bot** (microfono browser) | http://localhost:7860/prebuilt/ |
| Server locale (base) | http://localhost:7860 |
| Console Deepgram (STT) | https://console.deepgram.com |
| Console Anthropic (LLM) | https://console.anthropic.com |
| ElevenLabs (TTS / voci) | https://elevenlabs.io |

---

## 🔑 Chiavi API (file `.env`)

Le chiavi stanno nel file **`.env`** nella root (NON committato, ignorato da git).
Mai metterle in `.env.example` (quello è tracciato da git).

| Variabile | Dove prenderla | Piano gratuito? |
|-----------|----------------|-----------------|
| `DEEPGRAM_API_KEY` | console.deepgram.com → API Keys | Sì (200$ credito) |
| `ANTHROPIC_API_KEY` | console.anthropic.com | A consumo (centesimi) |
| `ELEVENLABS_API_KEY` | elevenlabs.io → profilo → API Keys | Sì (10k caratteri/mese) |
| `DEMO_VOICE_ID` | elevenlabs.io → Voice Library | Default IT già impostato |

Se cambi le chiavi, riavvia il bot (le legge all'avvio).

---

## 📋 Comandi principali

```bash
# --- Ambiente ---
.venv/Scripts/python --version          # deve dire Python 3.12.x
.venv/Scripts/pip show pipecat-ai       # deve dire Version: 1.4.0

# --- Database / tenant ---
.venv/Scripts/python -m src.db.seed_demo   # crea/aggiorna il tenant "demo"

# --- Avvio bot ---
.venv/Scripts/python main.py --tenant=demo

# --- Test automatici ---
.venv/Scripts/python -m pytest -q          # tutta la suite
.venv/Scripts/python -m pytest tests/test_bot.py -q   # un singolo file
```

---

## 🧪 Test live

### Base (Fase 1 — già verificata, utile come smoke test)

Apri `http://localhost:7860/prebuilt/`, consenti il microfono, premi Connect:

1. ✅ Il bot dice **da solo** il saluto in italiano appena ti connetti (VOICE-02)
2. ✅ Gli parli in italiano → ti risponde come receptionist (VOICE-01)
3. ✅ Lo interrompi mentre parla → si ferma e ascolta (**barge-in**, VOICE-03)
4. ✅ La voce è quella italiana configurata (VOICE-05)

### ⏳ Verifica Fase 3 — SC1–SC5 (DA FARE, sessione unica ~30-45 min)

Prerequisiti: bot avviato con `.venv/Scripts/python main.py --tenant=demo`, client su `http://localhost:7860/prebuilt/`. Gli scenari SC3/SC4 richiedono riavvii con `.env`/codice modificati temporaneamente.

1. ✅ **SC1 — Trasferimento operatore** (3 varianti, una chiamata ciascuna):
   (a) chiedi subito "mi passi una persona?"; (b) chiedilo a metà prenotazione; (c) parla in inglese.
   Atteso: il bot annuncia il trasferimento e chiude la chiamata; nel log il numero viene dalla config del tenant.
   ✔️ *Verificato live 2026-07-04.*
2. ✅ **SC2 — Notifica di fine chiamata**: completa una prenotazione e chiudi → riga `[CALL LOG]` in console (+ messaggio Telegram se `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in `.env`) con esito `prenotato`. Ripeti abbandonando a metà → esito `abbandonato`.
   ✔️ *Verificato live 2026-07-04: messaggio Telegram ricevuto con esito `prenotato`.*
3. ◐ **SC3 — Failover STT sulla stessa chiamata**: in `.env` metti `DEEPGRAM_API_KEY=invalid`, riavvia, connettiti e parla.
   Atteso: frase di cortesia *"Un momento, sto risolvendo un problema tecnico…"* e la **stessa chiamata** continua su faster-whisper (primo turno lento 10-20s: carica il modello sul CPU). La chiamata NON deve cadere.
   ✔️ *2026-07-04: verificato il core — failover scatta, la chiamata sopravvive, whisper trascrive e il bot risponde. Bug bloccante trovato e fissato (vedi "Bug fixati" sotto). Ultimo run inconcludente per rete/DNS instabile lato macchina di test; verifica completa rimandata (decisione titolare: avanti verso MVP).*
4. ⏭️ **SC4 — Doppio guasto → trasferimento** (SKIPPED 2026-07-04, decisione titolare): chiave invalida **e** whisper forzato a fallire (`device="cuda"` in `stt_switcher.py`, riga ~340). Atteso: *"…La trasferisco a un operatore."*, chiusura pulita, `outcome='fallito'`.
5. ◐ **SC5 — Watchdog dead-air**: chiamata normale, silenzio ~6s → sollecito; altri ~8s → chiusura.
   ✔️ *2026-07-04: osservato live incidentalmente durante SC3 — sollecito T1 e chiusura T2 funzionano. Nota: la frase finale può non essere udibile (bug noto sotto).*

⚠️ **Al termine dei test forzati ripristina**: `DEEPGRAM_API_KEY` corretta in `.env` (fatto 2026-07-04) e `device="cpu"` in `stt_switcher.py`, poi smoke test base.

#### 🐛 Bug fixati nella sessione live 2026-07-04

- **SC3 killer (FIXATO)**: il monitor di `FailoverDeepgramSTTService` continuava a spingere ErrorFrame ogni 2s anche dopo il failover riuscito; l'`ErrorFallbackObserver` li contava e chiudeva la chiamata a ~13s con esito `fallito`. Fix: il monitor ora tace quando Deepgram non è il servizio attivo (`_is_active_stt()`, wiring in `build_stt_switcher`). Coperto da 3 test nuovi (139 verdi).
- Aggiunta strumentazione permanente: log `[WATCHDOG]` (reset/idle in `bot.py`) e `[WHISPER]` (load/segmenti in `stt_switcher.py`) per diagnosi live.

#### ⚠️ Difetti noti residui (non bloccanti per MVP, da ripescare prima del pilota)

1. **Frase di chiusura tagliata**: su escalation watchdog/SC4 l'`EndWorkerFrame` chiude la pipeline prima che il TTS della frase finale ("…la passo a un operatore") venga riprodotto. Il pattern identico in `handle_transfer_call` (SC1) invece si sente — da indagare la differenza (push da aggregator vs worker.queue).
2. **Timer dead-air non riparte** se il turno utente inizia mentre il bot sta ancora parlando e poi la trascrizione non arriva: il guard `_user_turn_in_progress` impedisce l'avvio del timer su BotStoppedSpeaking → silenzio infinito invece della chiusura SC5.
3. **Chiave Deepgram nei log**: il warning di pipecat `Connection lost, will retry` stampa l'header `Authorization` completo in console. Con chiave valida e drop di rete la chiave finisce nei log (T-02-KEY). Hardening: filtro loguru o patch del logging.
4. **Whisper load dipendente dalla rete**: al primo uso huggingface fa un check online anche a modello già in cache; con DNS instabile può bloccarsi. Hardening: `local_files_only=True` quando la cache esiste.

---

## 🩹 Problemi noti / troubleshooting

- **`UnicodeEncodeError ... '\U0001f680'` all'avvio (Windows):** il runner di Pipecat
  stampa emoji e la console Windows (cp1252) va in errore. Risolto in `main.py`
  (forza UTF-8 su Windows). Se ricapita in un altro script, lancia con prefisso:
  `PYTHONUTF8=1 .venv/Scripts/python <script>`.
- **Prima connessione lenta:** al primo avvio Silero VAD scarica il modello — normale.
- **Il bot non risponde (solo trascrive):** controlla che `ANTHROPIC_API_KEY` sia valorizzata in `.env`.
- **Errore chiave / 401:** verifica le chiavi in `.env` (nessun placeholder `INCOLLA_QUI...`).

---

## 📍 Stato avanzamento

> Roadmap riorganizzata **pilot-first** il 2026-07-03: l'obiettivo non è completare la roadmap originale ma installare il bot dal **primo cliente pilota (ristorante)**. Le 5 fasi originali restano documentate in `.planning/ROADMAP.md` (storico GSD); questo file è la verità operativa.

**Fasi originali (v1.0):**

| Fase | Nome | Stato |
|------|------|-------|
| 1 | Local Voice Loop (bot vocale locale) | ✅ Completa (verificata live) |
| 2 | Booking / Calendar / FAQ | ✅ Completa |
| 3 | Trasferimento / riepilogo / notifiche / failover STT | ✅ Codice completo — verifiche live SC1–SC5 da fare (checklist sopra) |
| 4 | Telefonia Telnyx | ○ Prossima (scope pilota: solo inbound + trasferimento reale) |
| 5 | Multi-tenant + onboarding | ◐ Ridotta a "Pilot-Ready" (vedi sotto) |

**Percorso pilot-first (ordine di esecuzione):**

| Step | Cosa | Stato |
|------|------|-------|
| 0 | Pulizia: CLAUDE.md senza GSD, RUNBOOK aggiornato, `aiosmtplib` dichiarata in pyproject | ✅ 2026-07-04 |
| 1 | Sessione di verifica live Fase 3 (SC1–SC5) | ◐ 2026-07-04: SC1 ✅ SC2 ✅ SC3 core ✅ (+1 bug killer fixato) · SC5 osservato · SC4 skipped — chiusa per decisione titolare, difetti residui annotati sopra |
| 2 | Telefonia Telnyx: inbound su DID italiano, routing DID→tenant, parità col path locale, trasferimento reale | ○ Da fare — parte con sessione di ricerca dedicata (flag HIGH in `.planning/research/`) |
| 3 | Pilot-Ready: secondo tenant via script di seed, prompt caching Anthropic (latenza), checklist installazione pilota, backup `centralino.db` | ○ Da fare |

**Rimandato a dopo il primo cliente pagante:** onboarding CLI, credential store cifrato per-tenant, voice cloning ElevenLabs (+ consenso GDPR), canale SMS/WhatsApp (resta stub), migrazione Postgres, target rigido <800ms.

### 📊 Latenza misurata (Fase 1, dati reali `logs/latency.jsonl`)

Output per turno in console: `response=Xms | stt=.. llm_ttft=.. tts_ttfb=.. (turn=Yms)`
(`response_ms` = latenza di risposta = stt + llm_ttft + tts_ttfb; il `[WARN]` scatta se > 800ms).
Per la diagnostica verbosa: avvia con `LATENCY_DEBUG=1`.

Misure a regime: STT ~600–740ms · **Claude TTFT ~800ms (warm), ~2.3s (cold start)** · TTS ~290ms → risposta ~1.7s.
⚠️ **Sopra il budget <800ms.** Ottimizzazione rimandata a una fase futura. Leve identificate:
- **Prompt caching Anthropic NON attivo** (`cache_read_input_tokens=0`) → attivarlo sul system prompt taglia il TTFT di Claude.
- Cold start del primo turno; eventuale tuning modello/streaming.

### 🩹 Frase di cortesia (REL-01)
Su errore di un provider il bot dice *"Mi scusi, ho avuto un problema tecnico, può ripetere?"* invece del silenzio.
Per testarlo: metti temporaneamente una `ANTHROPIC_API_KEY` non valida nel `.env`, riavvia, parla → senti la frase. Poi ripristina la chiave.
