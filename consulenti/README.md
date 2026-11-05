# Report consulenti

Programma dell'agenzia, come *Preliminari*, *Valutazioni* e *Sintesi*. Dai report personali Excel dei consulenti (un foglio per mese e una riga per giorno) calcola:

- l'**andamento settimanale** di ogni consulente e dell'ufficio, rispetto alla settimana precedente e ai **benchmark** del mese;
- il **report mensile della filiale**, con le variazioni percentuali per consulente e per l'ufficio.

## Pagine

- **Benchmark**: a inizio mese si carica il file degli obiettivi, con una riga per consulente e il riquadro dell'ufficio.
  - Viene letto il formato usato in ufficio: 1/2 APPUNTAMENTO, INCARICO, MANDATI, I/II APP, PROPOSTE, BUDGET.
  - Si può anche scaricare un modello da compilare.
  - I file vengono salvati in `Dati/benchmark/anno-mese.xlsx`.
- **Report collaboratori**: ogni settimana si caricano i report personali aggiornati.
  - Il consulente viene riconosciuto dalla cella CONSULENTE e il report si salva in `Dati/report_collaboratori/NOME.xlsx`.
  - La versione precedente passa in `archivio/`.
  - I file si possono anche copiare direttamente nella cartella.
- **Andamento settimanale**: crea un Excel con un foglio per consulente, il foglio UFFICIO e il foglio SINTESI.
  - Le settimane vanno da lunedì a domenica.
  - Il benchmark del mese è diviso tra le settimane in base ai giorni lavorativi, da lunedì a sabato esclusi i festivi.
  - MANDATI e BUDGET si leggono dalle colonne giornaliere del report personale. Le colonne RIF non si sommano.
- **Report mensile**: compila la riga di ogni consulente nel foglio del mese del report della filiale, creandolo se manca, e aggiunge i fogli:
  - CONFRONTO: variazioni % sul mese precedente e sullo stesso mese dell'anno prima, e progressivo dell'anno;
  - VARIAZIONI: la tabella riassuntiva.

Gli Excel prodotti si salvano in `Dati/risultati`. Tutti i confronti sono formule, quindi correggendo un valore a mano si aggiorna tutto.

## Installazione (cartella condivisa, anche sul NAS senza internet)

1. Da un PC scarica il pacchetto: <https://github.com/grigoloimmobiliare/preliminari-grigolo/releases/download/consulenti/ReportConsulenti.zip>
2. Estrai lo zip in una cartella condivisa dell'ufficio, ad esempio `\\NAS\Consulenti`. Gli utenti devono poterci leggere e scrivere.
3. Su ogni PC fai doppio clic su **`Avvia Report consulenti.bat`**, oppure su un suo collegamento sul desktop. Il programma viene copiato sul PC e si apre nel browser; i dati restano nella cartella condivisa.

Il programma gira sui PC con Windows 10 o 11: non servono internet, Docker o Python. Per aggiornarlo basta sostituire la cartella `Programma` con quella del pacchetto nuovo. Il pacchetto viene costruito e provato su Windows a ogni modifica, con il workflow `.github/workflows/consulenti-windows.yml`.

## Sviluppo

```bash
cd consulenti
pip install -r requirements.txt pytest httpx
python -m pytest -q
CONSULENTI_DATI=./dati uvicorn app.main:app --port 8091
```
