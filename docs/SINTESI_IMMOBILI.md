# Sintesi immobili

Programma interno, **separato dai preliminari**, che legge l'**atto di provenienza** e le **visure catastali** in PDF di un immobile e crea un **PDF di sintesi**. Il PDF viene salvato nella cartella condivisa del server.

Gira su un PC Windows dell'ufficio, anche lo stesso dei preliminari, ma ha:
- una sua porta: **8081**, mentre i preliminari usano la 8080;
- una sua cartella dati sul NAS, ad esempio `\\NAS\Sintesi`.

I PDF si possono semplicemente **copiare nella cartella condivisa**: la sintesi compare da sola. In alternativa si usa la pagina web `http://<nome-PC>:8081`. Tutto viene elaborato **in locale**: nessun documento viene inviato a servizi esterni.

## Come si usa

Come per i preliminari, il programma gira su un **PC Windows dell'ufficio sempre acceso**. Documenti e PDF stanno in una **cartella condivisa del NAS**, ad esempio `\\NAS\Sintesi`: il NAS fa solo da archivio, non deve eseguire programmi. I documenti si possono dare al programma in due modi.

### A) Copiando i PDF nella cartella condivisa (senza browser)

1. In `\\NAS\Sintesi` crea una cartella con il nome dell'immobile, ad esempio `Rossi - Via Roma 10`.
2. Copia dentro i PDF dell'atto di provenienza e delle visure, anche tutti insieme e con qualsiasi nome.
3. Entro un minuto circa:
   - i PDF vengono **smistati da soli** in `01_Atto_provenienza` e `02_Visure_catastali` (le visure sono riconosciute dal contenuto);
   - nella cartella compare **`Sintesi - Rossi - Via Roma 10.pdf`**.

Se aggiungi o sostituisci un documento, la sintesi viene ricreata da sola. Se qualcosa va storto, nella cartella compare `ERRORE.txt` con la spiegazione. Nella cartella condivisa trovi anche il promemoria `LEGGIMI - come usare questa cartella.txt`.

### B) Dalla pagina web

Apri `http://<nome-PC>:8081`. Poi:
1. crea l'immobile;
2. trascina i PDF nelle due caselle;
3. premi **Analizza e crea il PDF**.

Il PDF viene salvato nella stessa cartella condivisa. La pagina mostra anche un riepilogo con i punti da verificare.

Le cartelle create nei due modi sono le stesse: un immobile preparato copiando i file si vede anche dalla pagina web, e viceversa.

```
\\NAS\Sintesi\
    LEGGIMI - come usare questa cartella.txt
    Rossi - Via Roma 10\
        01_Atto_provenienza\
        02_Visure_catastali\
        sintesi.json
        Sintesi - Rossi - Via Roma 10.pdf
```

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

## Installazione su un PC Windows (consigliata)

Serve un PC Windows 10 o 11 dell'ufficio che resta acceso. Può essere lo stesso dei preliminari.

1. Su NAS crea la cartella condivisa `Sintesi` e dai accesso in lettura e scrittura agli utenti dell'ufficio.
2. Da GitHub scarica il programma (Code → Download ZIP) ed estrai **tutto** lo ZIP.
3. Fai doppio clic su **`installa_sintesi_windows.bat`** e conferma i permessi di amministratore.
4. Rispondi alle domande:
   - **Cartella dati**: `\\NAS\Sintesi`. Un'unità di rete come `Z:\Sintesi` viene convertita da sola. Vengono poi chiesti **utente e password del NAS**, quelli usati per aprire la cartella da Esplora file. Se la cartella si apre senza password, si lascia vuoto. Il programma si collega da solo al NAS a ogni avvio. La password è salvata cifrata e vale solo per quel PC.
   - **Porta**: 8081. I preliminari usano la 8080.
   - **Nome nell'intestazione del PDF**: predefinito *Grigolo Immobiliare*.

Lo script fa tutto da solo:
- installa Python ed eventualmente Tesseract (serve solo per PDF scansionati);
- copia il programma in `C:\SintesiGrigolo`;
- lo avvia a ogni accensione del PC, anche senza nessuno collegato;
- apre la porta nel firewall solo per la rete dell'ufficio;
- crea sul desktop il collegamento *Sintesi immobili*.

**Altri comandi:**
- `sintesi\windows\riconfigura_sintesi.bat` cambia cartella, porta, credenziali del NAS o nome nel PDF;
- `sintesi\windows\disinstalla_sintesi.bat` rimuove il programma. I documenti non vengono cancellati.

Il log è in `C:\SintesiGrigolo\log\server.log`.

**Aggiornamento.** Scarica la nuova versione e rilancia `installa_sintesi_windows.bat`: documenti e impostazioni restano invariati.

### In alternativa: NAS con Docker

Vale solo per i NAS che eseguono container (Synology Container Manager, QNAP Container Station). In SSH, dalla cartella del programma:
```bash
sudo ./sintesi/installa.sh
```

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
| `sintesi/servizio.py` | creazione della sintesi e sorveglianza della cartella condivisa (smistamento dei PDF, sintesi automatica) |
| `sintesi/analisi.py` | unione dei dati e controlli di coerenza |
| `sintesi/pdf.py` | impaginazione del PDF (ReportLab) |
| `sintesi/archivio.py` | cartelle sul server |
