---
status: complete
phase: 02-booking-calendar-faq
source:
  - 02-01-SUMMARY.md
  - 02-02-SUMMARY.md
  - 02-03-SUMMARY.md
  - 02-04-SUMMARY.md
started: 2026-06-26T18:40:00Z
updated: 2026-06-26T18:55:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Avvio da zero (server spento) per il tenant demo: il server parte senza errori, il seed è pronto, e il bot saluta da solo in italiano (Ristorante Da Mario).
result: pass

### 2. Saluto personalizzato + routing (W1)
expected: Dopo il saluto, se chiedi un'informazione (orari/indirizzo) il bot va sul percorso FAQ; se dici che vuoi prenotare un tavolo, va sul percorso prenotazione. Il passaggio è naturale, senza ripetere il saluto.
result: pass

### 3. Prenotazione end-to-end (BOOK-01/03/05)
expected: Fornendo data, ora, numero persone, nome e telefono, il bot raccoglie i 5 dati, ti rilegge il riepilogo e — solo dopo la tua conferma a voce — crea l'evento su Google Calendar e conferma. La prenotazione compare davvero sul calendario.
result: pass

### 4. Read-back: telefono chiaro + anno corretto (D-15)
expected: Nella rilettura il telefono viene scandito cifra per cifra in modo comprensibile (non un numero "alieno"), e la data ha l'anno corretto (2026/futuro, non 2025).
result: pass

### 5. Correzione di un singolo campo al read-back (D-17)
expected: Se durante la rilettura dici "no" e vuoi cambiare un dato (es. l'ora o le persone), il bot corregge solo quel campo e ti rilegge i dati aggiornati, senza ricominciare la raccolta da capo.
result: pass

### 6. Slot pieno → proposta alternative (D-04/D-05)
expected: Se l'orario richiesto è al completo, il bot propone alternative nello stesso giorno; se la giornata è piena, propone il primo slot disponibile in un giorno successivo. Non conferma una prenotazione inesistente.
result: skipped
reason: "Capienza demo 40 coperti — difficile saturare uno slot dal vivo. Logica coperta da test automatici test_alternatives_same_day / test_alternatives_next_day."

### 7. FAQ orari/servizi da configurazione (D-06)
expected: Chiedendo gli orari di apertura o i servizi, il bot risponde con i dati del ristorante (dalla configurazione del tenant), in modo rapido e corretto.
result: pass

### 8. FAQ indirizzo/prezzi dalla knowledge base (D-06)
expected: Chiedendo indirizzo, prezzi o info dal menu, il bot risponde pescando dalla knowledge base del tenant demo (i file KB caricati), con informazioni pertinenti.
result: pass

### 9. FAQ fuori knowledge base → fallback onesto (D-08)
expected: Chiedendo qualcosa che non è nella KB né nella config, il bot NON inventa: ammette di non avere l'informazione e offre di prendere nota per far ricontattare.
result: pass

### 10. Abbandono chiamata → bozza salvata, nessun evento (D-18)
expected: Se interrompi/chiudi la chiamata a metà prenotazione (prima della conferma), non viene creato alcun evento sul calendario; resta al più una bozza interna. Nessuna falsa conferma.
result: pass
note: "Verificato lato calendario (nessun evento creato). Bozza interna non ispezionata dall'utente."

## Summary

total: 10
passed: 9
issues: 0
pending: 0
skipped: 1

## Gaps

[none yet]
