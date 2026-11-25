# Sintesi atti di provenienza

Programma interno che legge l'**atto di provenienza** di un immobile (PDF) e crea un **PDF di sintesi**. La sintesi si concentra su tre temi:

- **Urbanistica**:
  - costruzione ante 1° settembre 1967;
  - titoli edilizi con numero e data: licenze, concessioni, permessi di costruire, DIA, SCIA, CILA;
  - condoni e sanatorie;
  - agibilità o abitabilità;
  - conformità catastale;
  - difformità dichiarate;
  - testo integrale della dichiarazione urbanistica.
- **Provenienza precedente**: come la parte venditrice era diventata proprietaria (compravendita, successione, donazione, divisione…). Per ogni titolo:
  - notaio, data e repertorio;
  - registrazione e trascrizione;
  - per le successioni, defunto, data del decesso e accettazione dell'eredità.
- **Vincoli e gravami che possono limitare la circolazione**, divisi per gravità:
  - **può limitare la vendita**: ipoteche e pignoramenti, usufrutto e diritti di abitazione, edilizia convenzionata/PEEP, divieti di alienazione e riscatto, vincoli culturali e paesaggistici, prelazioni, fondo patrimoniale e trust;
  - **da verificare**: vincolo pertinenziale dei parcheggi (L. 122/89), servitù, locazioni, patti particolari;
  - **da conoscere**: regolamento di condominio, agevolazioni prima casa.

Le formule di rito, come "libero da pesi, vincoli, ipoteche…" o "servitù attive e passive se e come esistenti", non vengono riportate come vincoli. Le dichiarazioni di assenza, come "non è locato" o "non sussistono prelazioni", sono riportate a parte.

In testa al PDF ci sono gli estremi dell'atto, le parti, i dati catastali e un riquadro **Punti di attenzione**, per esempio:
- provenienza da donazione con meno di 20 anni;
- successione senza accettazione dell'eredità trascritta;
- nessun titolo edilizio citato;
- sanatorie da verificare;
- ipoteche da cancellare;
- vincoli che limitano la vendita;
- prima casa da meno di 5 anni;
- ventennio non coperto dall'atto.

Tutto viene elaborato **sul PC**: l'atto non viene inviato a servizi esterni. Gli atti scansionati vengono letti con l'OCR (Tesseract, incluso nel pacchetto), con risultati meno affidabili.

## Come funziona

Come i programmi delle valutazioni e dei preliminari, è un **pacchetto da copiare nella cartella condivisa del server** (per esempio `\\SERVER\Sintesi`). Sui PC non va installato niente.

```
\\SERVER\Sintesi\
    Avvia Sintesi.bat     doppio clic per aprire il programma
    LEGGIMI.txt
    Programma\            il programma (non modificare)
    Dati\                 una cartella per ogni immobile
        Rossi - Via Roma 10\
            Atto_provenienza\atto.pdf
            Sintesi - Rossi - Via Roma 10.pdf
```

Doppio clic su **Avvia Sintesi.bat**: il programma viene copiato sul PC (la prima volta ci vuole circa un minuto) e si apre nel browser. La finestra nera va lasciata aperta mentre lo si usa.

L'atto si può dare al programma in due modi:
1. **dalla pagina**: crea l'immobile, trascina il PDF dell'atto e premi **Analizza e crea il PDF**;
2. **da Esplora risorse**: crea una cartella in `Dati\`, ad esempio `Rossi - Via Roma 10`, e copiaci il PDF dell'atto. Con il programma aperto su almeno un PC, entro un minuto circa il PDF viene spostato in `Atto_provenienza` e compare `Sintesi - Rossi - Via Roma 10.pdf`.

Se l'atto viene sostituito, la sintesi viene ricreata. In caso di problemi nella cartella compare `ERRORE.txt`.

## Dove si scarica il pacchetto

A ogni modifica del programma, GitHub costruisce e **prova il pacchetto su Windows**:
- test;
- OCR;
- avvio;
- sintesi dalla pagina e dalla cartella condivisa.

Poi lo pubblica sempre allo stesso link:

https://github.com/grigoloimmobiliare/preliminari-grigolo/releases/download/sintesi/Sintesi.zip

**Prima installazione**:
1. Estrai lo ZIP.
2. Copia la cartella `Sintesi` sul server.
3. Dai a tutti gli utenti lettura e scrittura.

**Aggiornamento**: con il programma chiuso su tutti i PC, sostituisci solo la cartella `Programma`. La cartella `Dati` non va toccata.

## Sviluppo

```bash
pip install -r sintesi/requirements.txt pytest httpx
SINTESI_DATI=./dati_sintesi python sintesi/windows/avvia.py
pytest tests/test_sintesi.py
```

| Percorso | Contenuto |
|---|---|
| `sintesi/provenienza.py` | lettura dell'atto: riusa `app/estrazione/atto.py` e aggiunge urbanistica, provenienza precedente, vincoli e gravami |
| `sintesi/analisi.py` | punti di attenzione |
| `sintesi/pdf.py` | impaginazione del PDF (ReportLab) |
| `sintesi/servizio.py` | creazione della sintesi e sorveglianza della cartella condivisa |
| `sintesi/archivio.py` | cartelle degli immobili |
| `sintesi/main.py`, `sintesi/web/` | pagine web |
| `sintesi/windows/` | avvio su Windows, `Avvia Sintesi.bat`, `LEGGIMI.txt`, prova del pacchetto |
| `.github/workflows/sintesi-windows.yml` | costruzione, prova e pubblicazione del pacchetto |
