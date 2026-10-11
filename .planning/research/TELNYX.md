# Ricerca Fase Telefonia Telnyx (flag HIGH) — 2026-07-05

Scope pilota: **inbound only** su numero italiano + trasferimento operatore reale.
Domanda commerciale chiave del titolare: *"il cliente può tenere il suo vecchio numero?"* → **Sì** (vedi Strategia numero).

---

## 1. Strategia numero per il cliente pilota

### Opzione A — Deviazione di chiamata (CONSIGLIATA per il pilota)
Il ristorante **tiene il suo numero e il suo operatore** (TIM/Vodafone/WindTre/Fastweb…); attiva una deviazione verso il DID Telnyx a cui risponde il bot.

- **Incondizionata** (`*21*<numero telnyx>#`, disattiva `#21#`): il bot risponde a tutto.
- **Su occupato** (`*67*…#`) / **su mancata risposta** (`*61*…#`): il bot risponde **solo quando il titolare non può** — argomento di vendita perfetto per il pilota ("non perdi più una prenotazione mentre sei in servizio").
- Costo: la tratta deviata la paga il ristorante secondo la sua tariffa (le flat business verso fissi nazionali di norma la includono — da verificare col piano del cliente).
- **Reversibile in 10 secondi**, zero pratiche, zero rischio → ideale per un pilota.
- ⚠️ Da verificare live nel pilota: preservazione del **caller ID** del chiamante attraverso la deviazione (in Italia di norma si preserva, ma dipende dall'operatore di origine) — ci serve per il riepilogo/richiamata.

### Opzione B — Porting del numero a Telnyx (dopo, se il cliente è convinto)
Portabilità dei numeri geografici italiani supportata. Servono: LOA, **codice di migrazione** (in fattura dell'operatore attuale), P.IVA/registrazione societaria, documento del referente, **codice fiscale**, prova di indirizzo in Italia. Cancellabile fino a 5 giorni lavorativi prima della data porto (7 per porti complessi), poi **irreversibile**; possibili disservizi durante il porto. Tempi: settimane. **Non adatto al pilota**, giusto per il cliente consolidato.

### Percorso consigliato
Pilota con deviazione (A) → se il cliente firma, porting (B) come upgrade.

---

## 2. Acquisto DID italiano su Telnyx (serve comunque, A o B)

- Numeri locali IT: **~$1/mese** (+ tariffa al minuto inbound, da listino).
- L'Italia richiede **Requirement Groups obbligatori** all'ordine, **senza pre-approvazione**: l'ordine parte solo con il gruppo requisiti compilato.
- Documenti (tutti PDF):
  - **Persona fisica**: documento fronte/retro, codice fiscale, prova di indirizzo (<3 mesi).
  - **Società/ditta individuale**: documento del rappresentante, visura/certificato registrazione, P.IVA, prova di indirizzo (<3 mesi).
- Per l'MVP: registrazione a nome del titolare (persona fisica) è la via più rapida; per i clienti reali andrà valutato l'end-user registration per-tenant.
- Tempi di approvazione non dichiarati → prevedere giorni, avviare subito.

---

## 3. Integrazione tecnica (conferma l'impianto CLAUDE.md)

- **TeXML Application** che risponde all'inbound con `<Connect><Stream bidirectionalMode="rtp" url="wss://<nostro-host>/ws" />` → il media stream bidirezionale (PCMU 8kHz) arriva al nostro endpoint FastAPI.
- Lato pipeline: `TelnyxFrameSerializer` + `FastAPIWebsocketTransport` — pipeline invariata rispetto al path WebRTC locale. Esempio funzionante nel repo `pipecat-examples` (telnyx-websocket, self-hosted).
- **Routing DID→tenant**: il messaggio `start` dello stream / webhook TeXML porta il numero chiamato (`To`) → lookup tenant in `centralino.db`.
- **Trasferimento operatore (SC1 reale)**: aggiornare il TeXML della chiamata via API (call_control_id) con `<Dial><Number>+39…</Number></Dial>` = cold transfer, sufficiente per il pilota. Warm transfer (Dial+Bridge) = fase successiva.
- Dev: serve `wss://` pubblico → ngrok/cloudflared davanti a uvicorn.
- Pitfall già schedati (PITFALLS.md): PCMU 8kHz solo `audio_out_sample_rate=8000`, NON settare `audio_in_sample_rate=8000` (bug Smart Turn), barge-in su WebSocket da riverificare, co-locare il server vicino all'Italia.

---

## 4. Azioni immediate (ordine)

1. Aprire account Telnyx + compilare il **Requirement Group Italia** con i documenti del titolare (tempi burocratici → subito).
2. Comprare 1 DID geografico italiano di test (~$1/mese).
3. Implementare endpoint FastAPI + TeXML app + ngrok → prima chiamata reale al bot demo.
4. Trasferimento reale via TeXML Dial (sostituisce `LocalTransferStub`).
5. Test con deviazione da un cellulare (simula il "vecchio numero" del ristorante).

## Fonti

- [Italy DID Requirements — Telnyx Help Center](https://support.telnyx.com/en/articles/1311462-italy-did-requirements)
- [Italy Number Porting — Telnyx Help Center](https://support.telnyx.com/en/articles/3267012-italy-number-porting)
- [Buy Italy virtual phone numbers — Telnyx](https://telnyx.com/phone-numbers/italy)
- [Telnyx Websocket Transport — Pipecat docs](https://docs.pipecat.ai/deployment/pipecat-cloud/guides/telephony/telnyx-websocket)
- [TeXML Dial verb — Telnyx developers](https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/dial)
- [Bi-directional streaming support — Telnyx release notes](https://telnyx.com/release-notes/bi-directional-streaming-support)
- [International Numbers - Required Documents — Telnyx](https://support.telnyx.com/en/articles/5469551-international-numbers-required-documents)
