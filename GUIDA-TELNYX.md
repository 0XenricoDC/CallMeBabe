# 📞 Guida Telnyx passo-passo — account, verifica e numeri

Guida operativa per il titolare. Obiettivo: account Telnyx funzionante, numero USA di
test subito, numero italiano appena pronti i documenti.

> Aggiornata: 2026-07-06. Se il portale cambia qualcosa, i nomi delle voci di menu
> potrebbero variare leggermente — la logica resta quella.

---

## 📋 Cosa preparare prima (checklist)

Per l'account e il numero USA di test **non serve nulla** oltre a email e carta.

Per il **numero italiano** (quando vorrai farlo), prepara come **PDF**:
- [ ] Documento d'identità **fronte e retro** (carta d'identità o passaporto)
- [ ] **Codice fiscale** (tessera sanitaria va bene)
- [ ] **Prova di indirizzo di meno di 3 mesi** intestata a te: bolletta luce/gas/internet/telefono.
      Se non hai bollette a tuo nome → scrivi PRIMA a **numbering@telnyx.com** chiedendo se
      accettano il certificato di residenza ANPR (gratis con SPID da
      https://www.anagrafenazionale.interno.it) o un estratto conto bancario.

---

## Passo 1 — Registrazione account

1. Vai su **https://telnyx.com/sign-up**
2. Compila: nome, email, password. Se chiede "Company": metti `CallMeBabe` o il tuo nome
   (NON serve P.IVA — vale come persona fisica)
3. Conferma l'email cliccando il link che ti arriva
4. ✅ A questo punto sei **Level 1** automaticamente (basta l'email confermata)

⚠️ Con email gratuite (Gmail ecc.) a volte l'account viene messo in **revisione manuale**
prima di poter comprare: è normale, si sblocca in ore/1 giorno. Se resta bloccato,
scrivi a support@telnyx.com.

## Passo 2 — Carica credito

1. Portale: **https://portal.telnyx.com** → menu a sinistra → **Billing** (o **Account → Billing**)
2. **Add funds / Payments** → carica **$10** con carta
3. Serve per comprare numeri ($1/mese l'uno) e pagare i minuti di chiamata

## Passo 3 — Verifica Level 2 (falla SUBITO, ci mettono ~48h)

Il Level 2 serve per: chiamate verso destinazioni internazionali (il **trasferimento
all'operatore italiano** è una chiamata in uscita verso l'Italia!) e call forwarding.
Senza L2 il bot risponde ma il trasferimento reale potrebbe essere bloccato.

1. Nel portale, clicca l'**icona profilo in alto a destra** → **Account Settings**
2. Vai alla sezione **Verifications**
3. Compila il modulo di richiesta **L2 Verification**: descrivi l'uso reale, es.
   *"AI voice receptionist for Italian small businesses (restaurants). Inbound calls
   answered by an AI assistant; occasional call transfer to the business owner's
   Italian phone number. Low volume, pilot phase."*
4. Invia e aspetta la review (**fino a 48 ore**). Stato visibile in
   **Account Settings → My Account → Account Level**
5. Se viene respinta: si può fare **appeal** (vedi link in fondo)

## Passo 4 — Numero USA di test (subito, zero documenti)

Con questo io parto con l'integrazione mentre la burocrazia italiana fa il suo corso.

1. Portale → menu a sinistra → **Numbers** → **Search & Buy Numbers**
   (link diretto: https://portal.telnyx.com/#/app/numbers/search-numbers)
2. Filtro **Country: United States**, tipo **Local** — scegli un numero qualsiasi
3. Aggiungi al carrello → **Purchase**. Fine: nessun documento richiesto
4. Dimmi il numero e comincio a collegarci il bot

## Passo 5 — Requirement Group Italia (quando hai i PDF pronti)

Obbligatorio per ordinare numeri italiani; si compila **una volta sola** e si riusa.

1. Portale → **Numbers** → sezione **Requirements** → tab **Requirement Groups**
2. **New Requirement Group** e nel modulo scegli:
   - **Country:** Italy
   - **Phone number type:** Local
   - **Order type:** New number
   - **Customer/End-user type:** *Natural person* (persona fisica)
3. Compila i dati anagrafici (nome, indirizzo italiano completo, codice fiscale)
   e **carica i 3 PDF** della checklist
4. Salva. Il gruppo deve risultare **fulfilled/approvato** prima dell'ordine
5. Se un documento viene rifiutato → scrivi a **numbering@telnyx.com** spiegando il caso

## Passo 6 — Compra il numero italiano

1. **Numbers → Search & Buy Numbers** → **Country: Italy**, tipo **Local**
2. Scegli il prefisso della zona del cliente pilota (es. 02 Milano, 06 Roma, 051 Bologna…)
3. All'ordine, **associa il Requirement Group** creato al Passo 5
4. L'ordine parte solo a requisiti approvati; se resta "pending" più di qualche giorno,
   sollecita numbering@telnyx.com

## Passo 7 — STOP: la configurazione tecnica la faccio io

Quando il numero (USA o IT) è attivo **fermati qui**: TeXML Application, WebSocket,
media streaming e trasferimento li configuro io da codice/portale insieme a te.
Non serve toccare **Voice → TeXML** o simili.

---

## 🩹 Problemi comuni

| Problema | Soluzione |
|---|---|
| Account bloccato dopo signup (email gratuita) | Attendi la review manuale; poi support@telnyx.com |
| L2 respinto | Appeal: rispondi alla mail o vedi guida "Appeal Level 2" sotto |
| Documento indirizzo rifiutato / non hai bollette | numbering@telnyx.com → chiedi alternative (certificato ANPR, estratto conto) |
| Numero IT non ordinabile | Il Requirement Group non è ancora approvato — controlla lo stato |

## 🔗 Link ufficiali

- Portale: https://portal.telnyx.com
- Verifica account (L1/L2): https://support.telnyx.com/en/articles/1130595-account-verification
- Appeal L2: https://support.telnyx.com/en/articles/8269305-appeal-level-2-verification-status
- Requirement Groups (guida): https://support.telnyx.com/en/articles/9801714-requirement-groups-for-ordering-phone-numbers
- Requisiti DID Italia: https://support.telnyx.com/en/articles/1311462-italy-did-requirements
- Ricerca/acquisto numeri: https://portal.telnyx.com/#/app/numbers/search-numbers
- Contatti utili: numbering@telnyx.com (documenti/numeri) · support@telnyx.com (account)
