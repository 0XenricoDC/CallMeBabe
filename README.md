# Centralino AI

Assistente vocale telefonico multi-tenant per piccole attività italiane
(ristoranti, hotel/B&B, studi medici/dentistici). Un solo motore self-hosted,
con BYO API keys, che risponde alle chiamate in entrata in italiano naturale:
prende prenotazioni/appuntamenti, risponde a FAQ da una knowledge base
per-cliente, trasferisce a un operatore quando serve, e a fine chiamata invia al
titolare un riepilogo. Ogni cliente è un record di configurazione, **non** una
modifica al codice.

Stack: **Pipecat 1.4.0** (Python) + **Pipecat Flows 1.3.0** — STT Deepgram → LLM
Claude → TTS ElevenLabs, con Silero VAD per il barge-in.

---

## Setup

### 1. Requisiti

- **Python 3.12** (3.11 va bene; 3.13 **no** — `ctranslate2`/`faster-whisper` non
  hanno wheel Windows per 3.13). Il file `.python-version` fissa `3.12`.
- Git, e una connessione per scaricare le dipendenze ML (diverse centinaia di MB).

Verifica Python 3.12:

```bash
py -3.12 --version     # Windows
python3.12 --version   # macOS/Linux
```

### 2. Crea il virtual environment e installa le dipendenze

```bash
# Windows (PowerShell o Git Bash)
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/pip install -e ".[dev]"

# macOS/Linux
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```

> Le dipendenze includono pacchetti ML pesanti (`ctranslate2`, `faster-whisper`,
> `aiortc`, `opencv-python`): il primo install scarica parecchi MB.

### 3. Crea gli account e ottieni le 3 chiavi API

Copia `.env.example` in `.env` e compila le chiavi. **Non committare mai `.env`.**

| Servizio | Dove creare l'account | Chiave | Note |
|----------|-----------------------|--------|------|
| **Deepgram** (STT italiano) | https://console.deepgram.com → *API Keys* → *Create a New API Key* | `DEEPGRAM_API_KEY` | Free tier ~12.000 minuti/anno. |
| **Anthropic** (LLM Claude) | https://console.anthropic.com → *Settings* → *API Keys* → *Create Key* | `ANTHROPIC_API_KEY` | Richiede billing attivo. Default model: `claude-haiku-4-5`. |
| **ElevenLabs** (TTS italiano) | https://elevenlabs.io → *Profile* → *API Key* | `ELEVENLABS_API_KEY` | Free tier ~10.000 caratteri/mese. |

Inoltre imposta `DEMO_VOICE_ID` con l'ID di una voce italiana da
https://elevenlabs.io/voice-library (un default è già presente in `.env.example`).

```bash
cp .env.example .env   # poi apri .env e incolla le tue chiavi
```

**Sicurezza:** non committare mai `.env`; non loggare mai le chiavi API in chiaro
(al massimo le ultime 4 cifre per debug). Tutte le chiavi sono caricate via
`python-dotenv`; nessuna chiave è hardcoded nel codice.

### 4. (Opzionale) Pre-scarica il modello Whisper

Il fallback STT self-hosted usa `faster-whisper` con il modello `large-v3-turbo`
(~1.5 GB), scaricato da HuggingFace al **primo** uso di Whisper. Pre-scaricalo per
evitare un'attesa silenziosa durante la prima chiamata:

```bash
.venv/Scripts/python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo')"
```

### 5. Esegui il bot demo

```bash
python main.py --tenant=demo
```

Poi apri `http://localhost:7860/prebuilt/` nel browser, concedi l'accesso al
microfono e parla con il bot in italiano. *(L'assemblaggio della pipeline live
arriva nel Plan 02 di questa fase.)*

---

## Sviluppo

```bash
# Test (unit, ~5s, nessuna chiamata API live)
.venv/Scripts/python -m pytest tests/ -q

# Lint / type-check
.venv/Scripts/ruff check src tests
.venv/Scripts/mypy src
```

---

## Struttura del progetto

```
src/
├── config/
│   ├── tenant_config.py   # TenantConfig (Pydantic) — il seam di config tipata
│   └── repository.py      # TenantRepository (aiosqlite), Postgres-ready
├── db/
│   ├── schema.sql         # schema tenants completo a colonne nullable
│   └── seed_demo.py       # seed del tenant `demo`
└── interfaces/
    ├── calendar_provider.py     # CalendarProvider ABC (seam Fase 2)
    └── notification_channel.py  # NotificationChannel ABC (seam Fase 3)
tests/                     # pytest harness + stub RED per ogni requisito Fase 1
```
