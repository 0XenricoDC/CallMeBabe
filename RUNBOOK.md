# 🛠️ RUNBOOK — Centralino AI

Guida operativa rapida: come avviare, provare e testare il bot.
**Questo file viene aggiornato man mano che il progetto avanza.**

> Ultimo aggiornamento: 2026-07-04 — Fasi 1–3 complete a livello di codice (136 test verdi + 1 skip). Roadmap riorganizzata **pilot-first** (obiettivo: primo cliente pilota ristorante — vedi CLAUDE.md → Priorità corrente). Prossimo passo: sessione di verifica live Fase 3 (checklist SC1–SC5 qui sotto), poi telefonia Telnyx.

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

1. **SC1 — Trasferimento operatore** (3 varianti, una chiamata ciascuna):
   (a) chiedi subito "mi passi una persona?"; (b) chiedilo a metà prenotazione; (c) parla in inglese.
   Atteso: il bot annuncia il trasferimento e chiude la chiamata; nel log il numero viene dalla config del tenant.
2. **SC2 — Notifica di fine chiamata**: completa una prenotazione e chiudi → riga `[CALL LOG]` in console (+ messaggio Telegram se `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in `.env`) con esito `prenotato`. Ripeti abbandonando a metà → esito `abbandonato`.
3. **SC3 — Failover STT sulla stessa chiamata**: in `.env` metti `DEEPGRAM_API_KEY=invalid`, riavvia, connettiti e parla.
   Atteso: frase di cortesia *"Un momento, sto risolvendo un problema tecnico…"* e la **stessa chiamata** continua su faster-whisper (primo turno lento 10-20s: carica il modello sul CPU). La chiamata NON deve cadere.
4. **SC4 — Doppio guasto → trasferimento**: chiave ancora invalida **e** whisper forzato a fallire: in `src/pipeline/stt_switcher.py` cambia temporaneamente `device="cpu"` → `device="cuda"` (riga ~320, macchina senza GPU). Riavvia, parla.
   Atteso: dopo qualche ciclo *"Mi scusi, sto riscontrando problemi tecnici. La trasferisco a un operatore."*, chiusura pulita, riga in `call_logs` con `outcome='fallito'`, nessun silenzio prolungato.
5. **SC5 — Watchdog dead-air**: chiamata normale (chiavi valide), resta in silenzio ~6s → il bot ti sollecita; resta zitto altri ~8s → parte la sequenza di recupero/chiusura.

⚠️ **Al termine ripristina**: `DEEPGRAM_API_KEY` corretta in `.env` e `device="cpu"` in `stt_switcher.py`, poi riavvia e fai un giro di smoke test base.

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
| 1 | Sessione di verifica live Fase 3 (SC1–SC5) | ○ Da fare |
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
