# Sintesi immobili

Programma interno, **separato dai preliminari**, che legge l'**atto di provenienza** e le **visure catastali** in PDF di un immobile e crea un **PDF di sintesi**. Il PDF viene salvato nella cartella condivisa del server.

Gira sullo stesso NAS o PC dei preliminari, ma ha:
- una sua porta: **8081**, mentre i preliminari usano la 8080;
- una sua cartella dati, ad esempio `\\NAS\Sintesi`.

Dai PC dell'ufficio si apre con `http://<server>:8081`. Tutto viene elaborato **in locale**: nessun documento viene inviato a servizi esterni.

## Come si usa

1. **Nuova sintesi.** Dalla pagina iniziale si crea l'immobile, ad esempio "Rossi - Via Roma 10, Treviso". Sul server viene creata la cartella:
   ```
   Sintesi/2026-11-03 Rossi - Via Roma 10 Treviso/
       01_Atto_provenienza/
       02_Visure_catastali/
       sintesi.json
       Sintesi - Rossi - Via Roma 10 Treviso.pdf
   ```
2. **Carica i PDF.** I file si trascinano nella pagina oppure si copiano direttamente nelle cartelle. Servono:
   - l'atto di provenienza;
   - una visura per ogni unità (appartamento, garage, ...), oppure una visura per soggetto.
3. **Analizza e crea il PDF.** In pochi secondi il PDF viene salvato nella cartella e si può aprire o scaricare. La pagina mostra un riepilogo con i punti da verificare.

Il pulsante si può premere di nuovo quando vengono aggiunti o sostituiti documenti: il PDF viene ricreato.

## Contenuto del PDF

0. **Punti da verificare**, in un riquadro colorato in testa al documento:
   - intestati della visura diversi dagli acquirenti dell'atto, con l'eventuale successione presente in visura (defunto e data);
   - provenienza da donazione;
   - acquisto con agevolazioni "prima casa" da meno di 5 anni;
   - unità dell'atto senza visura, o unità della visura non citate nell'atto;
   - categoria cambiata dopo l'atto;
   - somma delle quote diversa da 1/1;
   - visura più vecchia di 3 mesi;
   - visura citata che deriva da un atto diverso da quello caricato;
   - trascrizione non trovata;
   - PDF senza testo, letto con OCR.
1. **Proprietari attuali**:
   - intestati catastali dalla visura: nominativo, codice fiscale, nascita, diritto e quota;
   - acquirenti dell'atto di provenienza: residenza e stato civile;
   - indicazione se coincidono.
2. **Immobile e dati catastali**:
   - comune, indirizzo e descrizione dall'atto;
   - per ogni unità, dalla visura: sezione, foglio, particella, subalterno, categoria, classe, consistenza, superficie, rendita, indirizzo e piano.
3. **Situazione urbanistica**:
   - costruzione ante 1° settembre 1967;
   - titoli edilizi con numero e data: licenze, concessioni, permessi di costruire, sanatorie e condoni, DIA, SCIA, CILA;
   - agibilità o abitabilità;
   - testo integrale della dichiarazione urbanistica dell'atto.
4. **Estremi della provenienza**:
   - tipo di atto, notaio, data, repertorio e raccolta;
   - registrazione e trascrizione;
   - parte cedente, prezzo dichiarato, agevolazioni;
   - "dati derivanti da" di ogni visura.
5. **Clausole particolari**: le frasi dell'atto, raggruppate per argomento:
   - servitù;
   - ipoteche e gravami;
   - vincoli;
   - pertinenze (L. 122/89);
   - prelazioni;
   - usufrutto e diritti riservati;
   - edilizia convenzionata/PEEP;
   - regolamento di condominio;
   - prima casa;
   - locazioni;
   - fondo patrimoniale e trust;
   - patti e condizioni.

   Le formule di rito, come "libero da pesi, vincoli, ipoteche..." o "servitù attive e passive se e come esistenti", non vengono riportate come clausole: sono solo segnalate in una riga.
6. **Documenti analizzati**: per ogni file, come è stato letto e la data della visura.

Le clausole sono individuate per parole chiave: il PDF è un aiuto alla lettura, l'atto va comunque riletto.

## Visure supportate

PDF digitali scaricati da SISTER, dall'Agenzia delle Entrate o dai servizi di visure:
- **formato a schede**, il più recente, con le sezioni "Dati identificativi", "Dati di classamento", "Intestati catastali" e "Diritto di: Proprieta' per 1/1";
- **formato a tabella**, il precedente, con la tabella delle unità e il blocco "INTESTATI".

Le visure attuali e storiche sono entrambe accettate. Nelle storiche vengono considerati solo la situazione attuale e gli intestati attuali.

Se un PDF è una scansione senza testo, viene letto con l'OCR (Tesseract). Il risultato è meno affidabile e viene segnalato.

## Installazione

### Sul NAS (Docker)

Dalla cartella del programma, la stessa dei preliminari, in SSH:
```bash
sudo ./sintesi/installa.sh
```
Lo script chiede:
- la cartella condivisa (predefinita `/volume1/Sintesi`);
- la porta (predefinita 8081);
- l'utente proprietario dei file.

Poi avvia il container `sintesi-grigolo`, che riparte da solo dopo ogni riavvio. Le impostazioni sono in `sintesi/.env` (vedi `sintesi/.env.esempio`).

**Senza SSH (Synology).** In Container Manager → Progetto → Crea, scegli la cartella `sintesi` e usa il suo `docker-compose.yml`, dopo aver creato `sintesi/.env`.

### Su un PC Windows

Doppio clic su **`installa_sintesi_windows.bat`** nella cartella principale del programma. Funziona come l'installazione dei preliminari, ma:
- il programma va in `C:\SintesiGrigolo`;
- la porta predefinita è 8081;
- l'attività pianificata si chiama *Sintesi Immobili Grigolo*;
- sul desktop compare il collegamento *Sintesi immobili*.

Si può installare sullo stesso PC dei preliminari. Altri comandi:
- `sintesi\windows\riconfigura_sintesi.bat` cambia cartella, porta, account o nome dell'agenzia nel PDF;
- `sintesi\windows\disinstalla_sintesi.bat` rimuove il programma. I documenti non vengono cancellati.

Il log è in `C:\SintesiGrigolo\log\server.log`.

**Aggiornamento.** Rilancia lo script di installazione: documenti e impostazioni restano invariati.

## Sviluppo

```bash
pip install -r sintesi/requirements.txt
SINTESI_DATI=./dati_sintesi uvicorn sintesi.main:app --reload --port 8081
pytest tests/test_sintesi.py
```

| Percorso | Contenuto |
|---|---|
| `sintesi/main.py` | pagine web |
| `sintesi/visura.py` | lettura delle visure: unità, classamento, intestati, dati derivanti, successioni |
| `sintesi/provenienza.py` | atto di provenienza: riusa `app/estrazione/atto.py` e aggiunge titoli edilizi, agibilità, prezzo, clausole |
| `sintesi/analisi.py` | unione dei dati e controlli di coerenza |
| `sintesi/pdf.py` | impaginazione del PDF (ReportLab) |
| `sintesi/archivio.py` | cartelle sul server |
