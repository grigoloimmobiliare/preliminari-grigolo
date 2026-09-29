# Guida al modello Word del preliminare

Il programma compila il file `preliminare_modello.docx`, che si trova nella cartella `modello` della cartella condivisa sul NAS.
Il modello è un normale documento Word: il testo del contratto si può modificare liberamente.
Le parti tra parentesi graffe sono **segnaposto** e vanno lasciate intatte.

- `{{ ... }}` viene sostituito con un dato. Esempio: `{{I.comune}}` diventa `Treviso`.
- `{% if ... %} ... {% else %} ... {% endif %}` mostra un testo solo in certi casi.
- Un paragrafo che contiene soltanto `{%p ... %}` è un comando: ripete o nasconde i paragrafi successivi, fino al `{%p end... %}` corrispondente. In Word va lasciato su una riga a sé.

Consigli pratici:
- Per modificare un segnaposto riscrivilo per intero, senza cambiare formattazione a metà, altrimenti Word lo spezza in pezzi.
- Usa le virgolette dritte `"` dentro i segnaposto, mai quelle curve `“ ”`.
- Salva sempre in formato **.docx**.
- Caricando il nuovo modello dalla pagina "Modello Word", il programma lo prova. Se contiene errori il modello non viene sostituito. La versione precedente resta nella cartella `modello/archivio`.

## Dati mancanti

Quando un dato manca, nel Word compare il testo `[● descrizione]`, evidenziato in giallo, al posto del segnaposto.
Prima di stampare cerca in Word le evidenziazioni gialle, oppure il carattere `●`.

## Elenco dei segnaposto

### Parti (paragrafi ripetuti per ogni persona)

```
{%p for p in venditori %}   ... un paragrafo per ogni venditore ...   {%p endfor %}
{%p for p in acquirenti %}  ... un paragrafo per ogni acquirente ...  {%p endfor %}
```

Dentro il ciclo, `loop.last` è vero per l'ultima persona.

| Segnaposto | Esempio |
|---|---|
| `{{p.art}}` / `{{p.art_min}}` | Il Sig. / La Sig.ra, il Sig. / la Sig.ra |
| `{{p.nominativo}}` | ROSSI MARIO |
| `{{p.nato}}` | nato / nata |
| `{{p.luogo_nascita}}` | Oderzo (TV) |
| `{{p.data_nascita}}` | 15/03/1980 |
| `{{p.cf}}` | RSS MRA 80C15 L407X |
| `{{p.doc_tipo}}`, `{{p.doc_numero}}` | C.I., CA12345AB |
| `{{p.rilasciato}}` | rilasciata (C.I.) / rilasciato (passaporto) |
| `{{p.doc_ente}}` | dal Comune di Treviso |
| `{{p.doc_rilascio}}`, `{{p.doc_scadenza}}` | 01/01/2020, 15/03/2031 |
| `{{p.residenza}}` | Treviso (TV) in Via Roma n. 16/F |
| `{{p.stato_civile}}` | coniugato in regime di separazione dei beni |
| `{% if p.societa %}` | vero se la parte è una società |
| `{{p.soc_denominazione}}`, `{{p.soc_sede}}`, `{{p.soc_cf}}`, `{{p.soc_rea}}`, `{{p.soc_qualita}}` | dati della società e qualità di chi firma |
| `{{V.che_sara}}` / `{{A_.che_sara}}` | "che sarà in seguito denominato/a", "che saranno in seguito denominati" (venditori / acquirenti) |

Per l'art. 6 (stato civile) si usa `{% for p in stato_civile %}`, cioè tutte le persone fisiche, venditori e acquirenti.

### Immobile (`I`)

| Segnaposto | Esempio |
|---|---|
| `{{I.tipologia}}` | fabbricato residenziale |
| `{{I.comune}}`, `{{I.prov}}`, `{{I.indirizzo}}` | Treviso, TV, Via Verdi n. 2 |
| `{{I.descrizione}}` | appartamento posto al quinto piano … |
| `{% if I.plurale %}` | vero se ci sono più unità catastali (per "L'unità immobiliare" / "Le unità immobiliari") |
| `{{I.n_planimetrie}}`, `{{I.planimetrie}}` | 2, "2 (due)" |
| `{%p for g in I.gruppi %}` … `{{g.intestazione}}` | Sezione D - Foglio 1 - Particella 134 |
| `{%p for u in g.unita %}` … `{{u.sub}}`, `{{u.categoria}}`, `{{u.classe}}`, `{{u.consistenza}}`, `{{u.rendita}}`, `{% if u.ultima %}` | dati di ogni subalterno |

### Provenienza (`P`)

`{{P.tipo_atto}}`, `{{P.notaio}}`, `{{P.notaio_sede}}`, `{{P.data}}`, `{{P.repertorio}}`, `{{P.raccolta}}`, `{{P.registrazione}}`, `{{P.trascrizione}}`

### Prezzo e pagamenti (`A`)

| Segnaposto | Significato |
|---|---|
| `{{A.prezzo}}` | Euro 260.000,00 (duecentosessantamila/00) |
| `{% if A.caparra %}`, `{{A.n_caparra}}`, `{{A.caparra}}`, `{{A.caparra_dettaglio}}` | numero del punto (3.2), totale caparra, descrizione dei versamenti |
| `{%p for a in A.acconti %}` … `{{a.n}}`, `{{a.importo}}`, `{{a.dettaglio}}` | acconti prezzo |
| `{{A.n_saldo}}`, `{{A.saldo}}`, `{{A.saldo_modalita}}` | saldo calcolato (prezzo meno caparre e acconti) |
| `{% if A.mutuo %}`, `{{A.n_mutuo}}`, `{{A.mutuo_importo}}`, `{{A.mutuo_entro}}` | condizione sospensiva del mutuo |
| `{{A.data_rogito}}`, `{{A.notaio_scelta}}`, `{% if A.locato %}` | rogito e consegna |

### Urbanistica (`U`) e APE (`E`)

`{{U.dichiarazione}}`, `{% if U.conforme %}` (conformità catastale), `{% if U.agibile %}`, `{{U.agibilita}}`

`{% if E.presente %}`, `{{E.classe}}`, `{{E.ipe}}`, `{{E.tecnico}}`, `{{E.data}}`

### Clausole aggiuntive

`{%p for c in clausole %}` … `{{c.n}} {{c.testo}}` … `{%p endfor %}`. La numerazione parte da 5.7.

### Chiusura (`F`)

`{{F.foro}}`, `{{F.luogo}}`, `{{F.data}}`, `{{F.pagine}}` ("5 (cinque)", calcolato automaticamente)
