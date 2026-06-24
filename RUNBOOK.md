# 🛠️ RUNBOOK — Centralino AI

Guida operativa rapida: come avviare, provare e testare il bot.
**Questo file viene aggiornato man mano che il progetto avanza.**

> Ultimo aggiornamento: 2026-06-24 — Fase 1, piano 01-02 (slice voce E2E) completato e verificato in live.

---

## ⚡ TL;DR — provare il bot in 3 passi

```bash
# 1. (una volta) seed del tenant demo nel database
.venv/Scripts/python -m src.db.seed_demo

# 2. avvia il bot
.venv/Scripts/python main.py --tenant=demo

# 3. apri nel browser e consenti il microfono:
#    http://localhost:7860/prebuilt/
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

## 🧪 Cosa verificare nel test live (Fase 1)

Apri `http://localhost:7860/prebuilt/`, consenti il microfono, premi Connect:

1. ✅ Il bot dice **da solo** il saluto in italiano appena ti connetti (VOICE-02)
2. ✅ Gli parli in italiano → ti risponde come receptionist (VOICE-01)
3. ✅ Lo interrompi mentre parla → si ferma e ascolta (**barge-in**, VOICE-03)
4. ✅ La voce è quella italiana configurata (VOICE-05)

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

**Milestone v1.0 — 5 fasi**

| Fase | Nome | Stato |
|------|------|-------|
| 1 | Local Voice Loop (bot vocale locale) | ◆ In corso |
| 2 | Booking / Calendar | ○ Da fare |
| 3 | Notifiche / riepilogo fine chiamata | ○ Da fare |
| 4 | Telefonia Telnyx | ○ Da fare |
| 5 | Multi-tenant | ○ Da fare |

**Fase 1 — piani:**

| Piano | Cosa fa | Stato |
|-------|---------|-------|
| 01-01 | Scheletro: venv 3.12, dipendenze, config tenant + SQLite, seam interfacce, test harness | ✓ Completo |
| 01-02 | Slice voce E2E: pipeline Deepgram→Claude→ElevenLabs, saluto IT, barge-in | ✓ Completo (verificato live) |
| 01-03 | Strumentazione latenza per-stage + frase di cortesia su errore | ○ Prossimo |

> Nota latenza: durante il test live di 01-02 si è percepita "un po' di latenza lato Claude".
> Il piano 01-03 aggiunge la misurazione per-stage che la quantificherà.
