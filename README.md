# Preliminari Grigolo

Programma interno per compilare in automatico il **contratto preliminare di compravendita** partendo dalla bozza Word dell'agenzia e dai documenti di ogni pratica:

- proposta di acquisto;
- documenti d'identità dei venditori e degli acquirenti;
- atto di provenienza;
- planimetrie catastali.

Nella cartella [`valutazioni/`](valutazioni/README.md) c'è un secondo programma, separato, per le **valutazioni immobiliari** (Excel della stima + valori OMI + comparabili BorsinoPro → Word su carta intestata).

Gira sul **NAS dell'ufficio** e si usa dal browser di qualsiasi PC della rete interna. Tutto viene elaborato **in locale**: nessun documento viene inviato a servizi esterni.

## Come funziona

1. **Nuova pratica.** Dalla pagina iniziale si crea la pratica. Sul NAS viene creata una cartella con queste sottocartelle:
   ```
   Preliminari/pratiche/2026-09-29 Rossi - Bianchi/
       01_Proposta/
       02_Documenti_venditori/
       03_Documenti_acquirenti/
       04_Atto_provenienza/
       05_Planimetrie/
   ```
   I file (PDF, JPG, PNG) si possono trascinare nella pagina web oppure copiare direttamente in queste cartelle dalla rete.
2. **Analizza documenti.** Il programma legge da solo:
   - **Documenti d'identità** (OCR con Tesseract): nome, cognome, data e luogo di nascita, codice fiscale, numero del documento, date di rilascio e di scadenza, residenza. Data di nascita, scadenza e numero del documento sono verificati con le cifre di controllo della banda MRZ. Il codice fiscale è verificato col carattere di controllo e, se l'OCR lo legge male, viene ricostruito dai dati certi. Fronte e retro possono stare in file separati: vengono uniti alla persona giusta.
   - **Atto di provenienza**: notaio, data, repertorio, raccolta, registrazione, trascrizione (se presente), intestatari, dati catastali, descrizione e indirizzo, dichiarazione urbanistica e agibilità. Il testo dell'atto è più affidabile dell'OCR, quindi i venditori vengono completati e verificati con i dati dell'atto: codice fiscale, luogo di nascita e stato civile.
   - **Planimetrie**: dalla dicitura catastale a margine si leggono foglio, particella e subalterno, confrontati con le unità dell'atto. Il numero di planimetrie viene riportato nel contratto.
3. **Accordi dalla proposta.** La proposta è compilata a mano e un OCR locale non legge la scrittura a mano in modo affidabile. Prezzo, caparre, acconti, data del rogito, mutuo e clausole aggiuntive si trascrivono nel modulo, con la proposta visibile accanto. Il saldo viene calcolato da solo.
4. **Controlli.** Prima della generazione vengono segnalati:
   - dati mancanti;
   - codice fiscale incoerente con nome o data di nascita;
   - documenti scaduti o in scadenza prima del rogito;
   - venditori diversi dagli intestatari dell'atto;
   - planimetrie che non corrispondono alle unità;
   - importi che non tornano;
   - residenza diversa tra atto e documento.
5. **Genera il Word.** Il preliminare viene salvato nella cartella della pratica, ad esempio `Preliminare - Rossi - Bianchi.docx`, insieme al file `Controlli.txt`. In particolare:
   - i dati mancanti compaiono **evidenziati in giallo** come `[● descrizione]`;
   - il paragrafo di ogni parte viene ripetuto per ciascuna persona, e le società sono gestite;
   - singolari e plurali si adattano al numero di unità;
   - la numerazione dell'art. 3 si adatta ai pagamenti;
   - le clausole della proposta diventano i punti 5.7, 5.8 e seguenti;
   - il numero di pagine viene calcolato da solo.

Ogni campo compilato in automatico mostra la sua **fonte**:
- **verde**: dato verificato (MRZ, carattere di controllo, atto);
- **arancione**: dato da controllare;
- **grigio**: letto con OCR.

Rilanciando l'analisi vengono riempiti solo i campi vuoti, quindi le correzioni fatte a mano non si perdono.

## Il modello Word

La bozza fornita (`Preliminare_bozza_sett_26.doc`) è stata trasformata in `modelli/preliminare_modello.docx`: stesso testo, carattere (Garamond 11), interlinea e margini, con i dati variabili sostituiti da segnaposto. Il modello si può modificare in Word e ricaricare dalla pagina **Modello Word**. I segnaposto disponibili sono in [docs/GUIDA_MODELLO.md](docs/GUIDA_MODELLO.md).

Rispetto alla bozza sono state aggiunte alcune parti automatiche:
- art. 3: punto sugli acconti e condizione sospensiva del mutuo, presenti solo se servono;
- art. 4: variante per immobile locato;
- art. 5.3: dichiarazione urbanistica ripresa dall'atto notarile, e testo alternativo se l'immobile non è conforme alle planimetrie catastali;
- art. 5.5: se l'APE non è ancora disponibile, obbligo di consegnarlo entro il rogito;
- art. 5.7 e seguenti: clausole aggiuntive.

Tutti questi testi si possono modificare nel modello.

## Installazione sul NAS

Serve Docker:
- **Synology**: pacchetto *Container Manager*;
- **QNAP**: *Container Station*.

1. Crea una cartella condivisa, ad esempio `Preliminari`, e dai accesso in lettura e scrittura agli utenti dell'ufficio.
2. Copia questo programma sul NAS, ad esempio in `/volume1/docker/preliminari-grigolo`, con `git clone` oppure scaricando lo ZIP da GitHub.
3. Collegati in SSH al NAS (su Synology: Pannello di controllo → Terminale e SNMP → abilita SSH) ed esegui:
   ```bash
   cd /volume1/docker/preliminari-grigolo
   sudo ./installa.sh
   ```
   Lo script chiede la cartella condivisa (es. `/volume1/Preliminari`), la porta (predefinita 8080) e l'utente proprietario dei file. Poi costruisce e avvia il programma, che ripartirà da solo anche dopo un riavvio del NAS.
4. Dai PC dell'ufficio apri `http://<indirizzo-del-NAS>:8080`.

**Senza SSH (Synology).** In Container Manager → Progetto → Crea, seleziona la cartella del programma e usa il `docker-compose.yml` incluso. Prima copia `.env.esempio` in `.env` e adatta i valori.

**Aggiornamento.** Rilancia `sudo ./installa.sh`: pratiche, modello e impostazioni restano invariati.

**Accesso.** Il programma non ha login: deve essere raggiungibile solo dalla rete dell'ufficio. Non aprire la porta 8080 sul router.

## Sviluppo e prove sul proprio PC

Servono Python 3.11+, Tesseract con la lingua italiana e, facoltativo, LibreOffice per il conteggio delle pagine.

```bash
pip install -r requirements.txt
PRELIMINARI_DATI=./dati uvicorn app.main:app --reload --port 8080
pytest
```

Il modello si rigenera dalla bozza con `python strumenti/crea_modello.py bozza.docx modelli/preliminare_modello.docx`. La bozza `.doc` va prima salvata come `.docx`.

## Struttura del codice

| Percorso | Contenuto |
|---|---|
| `app/main.py` | pagine web e salvataggio dei dati |
| `app/analisi.py` | lettura dei documenti e precompilazione della pratica |
| `app/estrazione/` | OCR e riconoscimento di documenti d'identità (MRZ, codice fiscale), atto, planimetrie |
| `app/genera.py` | compilazione del modello Word, evidenziazione dei dati mancanti, conteggio pagine |
| `app/verifiche.py` | controlli di coerenza |
| `app/pratiche.py` | cartelle delle pratiche sul NAS |
| `modelli/preliminare_modello.docx` | modello predefinito, copiato nella cartella del NAS al primo avvio |
