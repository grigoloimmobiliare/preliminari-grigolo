# Valutazioni Grigolo

Programma interno per creare in automatico la **valutazione tecnico-commerciale** di un immobile, partendo da:
- la bozza Word dell'agenzia;
- l'Excel della stima ("STIMA facile appartamento");
- il PDF dei comparabili di BorsinoPro.

Il risultato è un Word con la **carta intestata** su ogni pagina.

Il programma è separato da quello dei preliminari, ma si installa allo stesso modo sul NAS. Si usa dal browser di qualsiasi PC dell'ufficio.

## Come funziona

1. **Nuova valutazione.** Sul NAS viene creata una cartella:
   ```
   Valutazioni/valutazioni/2026-09-30 Rossi - Via Roma 10/
       01_Excel/          Excel della stima compilato
       02_Comparabili/    PDF di BorsinoPro (dal browser: Stampa -> Salva come PDF)
       03_OMI/            schermate dei valori OMI (create dal programma)
       Valutazione - Rossi - Via Roma 10.docx
   ```
   I file si trascinano nella pagina web oppure si copiano direttamente nelle cartelle dalla rete.
2. **Crea la valutazione.** Il programma:
   - **legge l'Excel.** Prende i dati cercando le etichette (`CLIENTE:`, `INDIRIZZO:`, `ZONA OMI`, `Valore al mq`...) e la tabella delle superfici: vani sopra "TOT VALORE TIPOLOGIA", pertinenze sotto. Se le formule non hanno un valore salvato, i totali vengono ricalcolati con le stesse regole del foglio.
   - **cerca i valori OMI** sul [sito dell'Agenzia delle Entrate](https://www1.agenziaentrate.gov.it/servizi/Consultazione/ricerca.htm?level=0). Usa l'ultimo semestre disponibile, la provincia e il comune predefiniti (Treviso, modificabili) e la zona OMI dell'Excel. Salva una schermata del risultato per ogni destinazione della zona (Residenziale, Commerciale...), inserita sotto "Valori OMI".
   - **prepara i comparabili.** Trasforma le pagine del PDF BorsinoPro in immagini, senza data e indirizzo aggiunti dal browser, e le inserisce dopo "Valori di Comparazione".
   - **compila il Word** mantenendo la formattazione del modello e mette la carta intestata dietro al testo di ogni pagina.
3. **Controllo.** I dati non trovati nell'Excel restano nel Word **evidenziati in giallo**, ad esempio `[CLIENTE]`. Sono elencati anche nella pagina della valutazione.

**Se la ricerca OMI non riesce** (sito non raggiungibile o cambiato):
- la pagina lo segnala;
- nella cartella `03_OMI` vengono salvati `errore_OMI.png` ed `errore_OMI.html`, utili per capire cosa è cambiato;
- si può caricare a mano una schermata in "Valori OMI" e rigenerare: il programma usa quella.

## Il modello Word

La bozza fornita (`strumenti/VALUTAZIONE_TIPO_bozza.docx`) è stata trasformata in `modelli/valutazione_modello.docx`: stesso testo e formattazione, con qualche segnaposto in più. Il modello si può scaricare, modificare in Word e ricaricare dalla pagina **Modello e carta intestata**. L'elenco completo dei segnaposto è nella pagina **Guida** del programma.

Riassunto dei segnaposto:
- `[QUALSIASI ETICHETTA DELL'EXCEL]`: il valore accanto all'etichetta, ad esempio `[CLIENTE]` o `[ZONA OMI]`.
- `[VALORE MQ]`, `[TOT MQ TIPOLOGIA]`, `[TOT VALORE TIPOLOGIA]`, `[VALORE A NUOVO]`, `[VETUSTA]`, `[VALORE ATTUALE]`: i valori della stima.
- `[INDICE DI VETUSTA]`: la decurtazione. Con 0,7 nell'Excel diventa 30 (%).
- `[VALORE COMMERCIALE]`: il valore dell'Excel. Se manca, è il valore attuale + 10%, come dice il testo del modello.
- Righe ripetute per ogni voce dell'Excel con dei mq:
  - `[VANO]` / `[MQ VANO]`;
  - `[PERTINENZA]` / `[MQ PERTINENZA]` / `[QUOTA PERTINENZA]` ("per intero", "ad 1/3", "al 10%") / `[VALORE PERTINENZA]`;
  - `[PRINCIPIO DI UNICITA]`;
  - `[CRITICITA]`.
- `[VALORI OMI]`, `[VALORI COMPARABILI]`: le immagini.

Rispetto alla bozza:
- l'elenco fisso dei vani (Soggiorno, Cucina, Tinello...) è diventato l'elenco dei vani dell'Excel;
- terrazza e garage sono diventati l'elenco delle pertinenze dell'Excel (garage, cantina, magazzino, terrazzi, giardino...);
- è stato aggiunto il titolo **Valori OMI** prima di "Valori di Comparazione".

Per rigenerare il modello dalla bozza:
```bash
python strumenti/crea_modello.py strumenti/VALUTAZIONE_TIPO_bozza.docx modelli/valutazione_modello.docx
```

## Carta intestata

Il programma include la carta intestata dell'agenzia (`modelli/carta_intestata.pdf`, "carta intestata new trasp"), che viene copiata nella cartella del NAS al primo avvio. Per cambiarla basta caricare un nuovo PDF, sempre a sfondo trasparente, dalla pagina **Modello e carta intestata**.

La prima pagina del PDF viene messa a tutta pagina dietro al testo, in ogni pagina del Word. Il programma misura anche dove finisce il logo in alto: se il testo del modello partirebbe sopra al logo, abbassa il margine superiore quanto basta. Con la carta attuale il margine passa da 3 cm a circa 5,4 cm.

## Installazione sul NAS

Come per i preliminari. Serve Docker:
- **Synology**: *Container Manager*;
- **QNAP**: *Container Station*.

Il NAS deve poter uscire su internet verso `www1.agenziaentrate.gov.it` per la ricerca OMI.

1. Crea una cartella condivisa, ad esempio `Valutazioni`, con accesso in lettura e scrittura per gli utenti dell'ufficio.
2. Collegati in SSH al NAS ed esegui, dalla cartella del programma (es. `/volume1/docker/preliminari-grigolo`):
   ```bash
   cd valutazioni
   sudo ./installa.sh
   ```
   Lo script chiede:
   - la cartella condivisa (es. `/volume1/Valutazioni`);
   - la porta (predefinita **8081**, perché la 8080 è dei preliminari);
   - l'utente proprietario dei file.
3. Dai PC dell'ufficio apri `http://<indirizzo-del-NAS>:8081`.

**Aggiornamento:** rilancia `sudo ./installa.sh`. Valutazioni, modello, carta intestata e impostazioni restano invariati.

**Accesso:** il programma non ha login. Deve essere raggiungibile solo dalla rete dell'ufficio.

## Sviluppo

```bash
pip install -r requirements.txt pytest httpx && playwright install chromium
VALUTAZIONI_DATI=./dati uvicorn app.main:app --reload --port 8081
pytest
```

I test della ricerca OMI usano un'imitazione del sito (`tests/sito_omi_finto.py`), quindi non escono su internet.

| Percorso | Contenuto |
|---|---|
| `app/main.py` | pagine web |
| `app/excel.py` | lettura dell'Excel della stima |
| `app/omi.py` | ricerca sul sito OMI e schermata del risultato |
| `app/immagini.py` | pagine del PDF BorsinoPro, carta intestata |
| `app/word.py` | compilazione del modello Word |
| `app/genera.py` | sequenza completa della generazione |
| `app/archivio.py` | cartelle sul NAS |
