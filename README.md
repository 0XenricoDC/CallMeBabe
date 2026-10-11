# 📞 CallMeBabe — AI Phone Receptionist

> Self-hosted, multi-tenant AI voice assistant that answers phone calls for Italian small businesses — in natural Italian.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Pipecat](https://img.shields.io/badge/Pipecat-1.4-000000)
![Claude](https://img.shields.io/badge/LLM-Claude-D97757?logo=anthropic&logoColor=white)
![Deepgram](https://img.shields.io/badge/STT-Deepgram-13EF93)
![ElevenLabs](https://img.shields.io/badge/TTS-ElevenLabs-000000)
![Telnyx](https://img.shields.io/badge/Telephony-Telnyx-00C08B)

🇮🇹 [Versione italiana](./README.it.md)

---

## What it does

CallMeBabe picks up incoming calls for restaurants, hotels/B&Bs and medical/dental practices and handles them end-to-end:

- 🗓️ **Takes bookings and appointments** — parses Italian dates and times, checks availability, writes to the calendar
- ❓ **Answers FAQs** from a per-client knowledge base (menu, prices, opening hours, address…)
- 🙋 **Transfers to a human** when the caller asks for it or the bot can't help
- 📝 **Sends the owner a call summary** — transcript, outcome and booking details

Every client is a **configuration record, not a code change**: greeting, voice, knowledge base, calendar and notification channel are all per tenant.

## Architecture

```
Caller ──► Telnyx (Italian number) ──► Pipecat pipeline
                                         │
             Silero VAD (barge-in) ──────┤
             Deepgram STT (it) ──────────┤  fallback: faster-whisper (self-hosted)
             Claude + tool calling ──────┤  ◄── Pipecat Flows (conversation states)
             ElevenLabs TTS (it) ────────┘
                                         │
         ┌───────────────────────────────┼─────────────────────────────┐
         ▼                               ▼                             ▼
  CalendarProvider               Knowledge base                NotificationChannel
  (Google Calendar / memory)     (per tenant)                  (email · SMS · Telegram · log)
```

Telephony, calendar and notifications sit behind interfaces, so providers can be swapped (e.g. Telnyx → Twilio) without touching the conversation logic.

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | Pipecat 1.4 + Pipecat Flows 1.3 |
| Speech-to-text | Deepgram (Italian), faster-whisper fallback |
| LLM | Anthropic Claude with tool calling |
| Text-to-speech | ElevenLabs (Italian voice, per-tenant voice cloning ready) |
| Telephony | Telnyx with Italian geographic numbers |
| Storage | SQLite (aiosqlite), Postgres-ready |
| Quality | pytest, ruff, mypy |

## Quick start

```bash
# Python 3.12 is required (3.13 has no Windows wheels for ctranslate2)
py -3.12 -m venv .venv
.venv/Scripts/pip install -e ".[dev]"

cp .env.example .env      # add DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, ELEVENLABS_API_KEY
python main.py --tenant=demo
```

Then open `http://localhost:7860/prebuilt/`, allow microphone access and talk to the bot in Italian.

Telephony setup with Telnyx is covered in [`GUIDA-TELNYX.md`](./GUIDA-TELNYX.md) and operations in [`RUNBOOK.md`](./RUNBOOK.md).

## Development

```bash
.venv/Scripts/python -m pytest tests/ -q   # unit tests, no live API calls
.venv/Scripts/ruff check src tests
.venv/Scripts/mypy src
```

## Project structure

```
src/
├── bot.py            # Pipecat pipeline assembly
├── booking/          # Italian date parsing + booking repository
├── calendar/         # CalendarProvider: Google Calendar and in-memory
├── call_log/         # call records and end-of-call summaries
├── config/           # typed TenantConfig + repository
└── ...
data/tenants/demo_trattoria/kb/   # example knowledge base
```

## Security

API keys are loaded from `.env` via `python-dotenv` and never hard-coded or logged. `.env`, databases and Google service-account keys are git-ignored.
