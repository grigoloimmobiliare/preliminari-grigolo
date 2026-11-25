from datetime import date

from app.estrazione import codice_fiscale as cfm
from sintesi import analisi, provenienza

CF_VERDI = (lambda b: b + cfm.carattere_controllo(b))(
    cfm.codice_cognome("VERDI") + cfm.codice_nome("LUCA") + cfm.codice_data_sesso(date(1975, 5, 2), "M") + "L407")
CF_GIALLI = (lambda b: b + cfm.carattere_controllo(b))(
    cfm.codice_cognome("GIALLI") + cfm.codice_nome("ANNA") + cfm.codice_data_sesso(date(1960, 1, 1), "F") + "G224")

# atto con provenienza da donazione, servitu' specifica, licenza + sanatoria + SCIA
ATTO = f"""Repertorio N. 1234
    Raccolta N.  987
COMPRAVENDITA
REPUBBLICA ITALIANA
L'anno duemilaventiquattro il giorno dieci del mese di marzo (10/3/2024).
Davanti a me dottor PAOLO NERI, notaio in Treviso, iscritto presso
SONO COMPARSI I SIGNORI:
- GIALLI ANNA, nata a Padova (PD) il giorno 1 gennaio 1960, residente
a Padova, Via Roma n. 1, codice fiscale {CF_GIALLI}, che dichiara di essere di stato civile libero;
- VERDI LUCA, nato a Treviso (TV) il giorno 2 maggio 1975, residente
a Treviso, Via Garibaldi n. 5, codice fiscale {CF_VERDI}, che
dichiara di essere coniugato in regime di separazione dei beni.
ART.1) La signora GIALLI ANNA vende al signor VERDI LUCA che acquista la piena proprietà
delle unità immobiliari facenti parte del fabbricato sito in Comune di Treviso, Via Roma n.
3, e più precisamente dell'appartamento posto al primo piano e del garage al piano terra, identificati come
segue al Catasto Fabbricati:
COMUNE DI TREVISO = Sez. E
Foglio 2 (due)
mappale 100 sub 5 - Via Roma P. 1 - cat. A/2 - cl. 4 - vani 5,5 - R.C. Euro 500,00
mappale 100 sub 9 - Via Roma P. T - cat. C/6 - cl. 2 - sup. cat. tot. mq. 14 - mq. 13 - R.C. Euro 40,10.
Confini: ...
ART.2) Il trasferimento comprende la proporzionale quota di comproprietà sulle parti comuni dell'edificio
ai sensi dell'art. 1117 c.c. come individuate nel regolamento di condominio depositato con atto del notaio
Bianchi in data 5 maggio 1980 rep. n. 3333, che la parte acquirente dichiara di conoscere ed accettare.
ART.3) La parte venditrice garantisce che quanto venduto è libero da pesi, vincoli, ipoteche, trascrizioni
pregiudizievoli e privilegi anche fiscali. Quanto venduto viene trasferito con tutte le servitù attive e passive se e come esistenti.
ART.4) Si dà atto che a carico del mappale 100 grava servitù di passaggio pedonale e carraio a favore del mappale 101,
costituita con atto del notaio Rossi del 3 aprile 1970.
ART.4-bis) PROVENIENZA. Quanto in oggetto è pervenuto alla signora GIALLI ANNA per donazione dalla madre BIANCHI MARIA
in forza di atto a rogito del notaio Luigi Fabbri di Padova in data 10 gennaio 2015, repertorio n. 777,
registrato a Padova il 20 gennaio 2015 al n. 300 e trascritto a Treviso il 22 gennaio 2015 ai nn. 1111/800.
ART.5) Il prezzo della vendita è stato convenuto in euro 180.000,00 (centottantamila virgola zero zero) che la
parte venditrice dichiara di aver ricevuto.
ART.6) La parte acquirente chiede l'applicazione delle agevolazioni prima casa di cui alla nota II-bis.
ART.8) La parte venditrice dichiara che le opere di costruzione del fabbricato in oggetto sono state iniziate in
forza di licenza edilizia n. 45/1970 rilasciata dal Comune di Treviso in data 12 marzo 1970 e che successivamente
sono state eseguite opere in forza di concessione edilizia in sanatoria n. 77 del 3 febbraio 1990 e di S.C.I.A.
prot. n. 12345 del 15/06/2015. La parte venditrice dichiara che l'abitabilità originaria è stata rilasciata
dal Comune di Treviso in data 1 giugno 1972 con prot. gen. n. 111. Ciascuna parte, ...
REGISTRATO A
 TREVISO
Il 20 marzo 2024
al n.5555 serie 1T
Trascritto a Treviso il 21 marzo 2024 ai nn. 9999/7777
"""


# atto con provenienza da successione (con accettazione dell'eredita') e ipoteca da cancellare
ATTO_SUCCESSIONE = """Repertorio n. 45.678                                   Raccolta n. 12.345
COMPRAVENDITA
REPUBBLICA ITALIANA
L'anno duemilaventicinque il giorno quindici del mese di settembre (15/9/2025).
In Treviso, nel mio studio.
Davanti a me dottor MARCO BIANCHI, notaio in Treviso, iscritto nel Collegio Notarile di Treviso,
SONO COMPARSI I SIGNORI:
- ROSSI MARIO, nato a Treviso (TV) il giorno 4 marzo 1960, residente a Treviso, Via Verdi n. 2, codice fiscale RSSMRA60C04L407X, che dichiara di essere coniugato in regime di comunione legale dei beni;
- NERI GIULIA, nata a Venezia (VE) il giorno 10 aprile 1990, residente a Treviso, Via Dante n. 8, codice fiscale NREGLI90D50L736Y, che dichiara di essere di stato civile libero.
ART. 1) Il signor ROSSI MARIO vende alla signora NERI GIULIA che acquista la piena proprietà dell'unità immobiliare facente parte del fabbricato sito in Comune di Treviso, Via Roma n. 10, e più precisamente dell'appartamento posto al secondo piano con cantina al piano interrato, identificato come segue al Catasto Fabbricati:
COMUNE DI TREVISO = Sez. A
Foglio 5
mappale 200 sub 7 - Via Roma P. 2-S1 - cat. A/3 - cl. 3 - vani 4,5 - R.C. Euro 350,00
Confini: ...
ART. 2) PROVENIENZA. Quanto in oggetto è pervenuto al signor ROSSI MARIO per successione in morte del padre ROSSI GIOVANNI, nato a Treviso il 1 gennaio 1930 e deceduto a Treviso il 3 marzo 2010, giusta dichiarazione di successione registrata a Treviso in data 20 agosto 2010 al n. 1234 vol. 9990 e trascritta a Treviso il 15 settembre 2010 ai nn. 33333/22222; l'accettazione tacita dell'eredità è stata trascritta a Treviso il 10 ottobre 2015 ai nn. 44444/30000. Al de cuius l'immobile era pervenuto in forza di atto di compravendita a rogito del notaio Carlo Verdi di Treviso in data 12 maggio 1975, repertorio n. 5555, registrato a Treviso il 30 maggio 1975 al n. 2345 e trascritto a Treviso il 2 giugno 1975 ai nn. 7777/5555.
ART. 3) La vendita comprende la proporzionale quota di comproprietà sulle parti comuni del fabbricato ai sensi dell'art. 1117 c.c. La parte acquirente dichiara di conoscere ed accettare il regolamento di condominio depositato con atto del notaio Bianchi in data 5 maggio 1980 rep. n. 3333, che vieta l'esercizio di attività commerciali nelle unità residenziali.
ART. 4) La parte venditrice garantisce che quanto venduto è libero da pesi, vincoli, ipoteche, trascrizioni pregiudizievoli e privilegi anche fiscali, ad eccezione dell'ipoteca volontaria iscritta a Treviso il 5 febbraio 2016 ai nn. 4000/600 a favore di Banca Esempio S.p.A. a garanzia di un mutuo, il cui debito residuo verrà estinto contestualmente al presente atto con successiva cancellazione. Quanto venduto viene trasferito con tutte le servitù attive e passive se e come esistenti.
ART. 5) Si dà atto che sul mappale 200 grava servitù di elettrodotto a favore di Enel costituita con atto del notaio Rossi del 3 aprile 1970.
ART. 6) La parte venditrice dichiara che l'immobile non è locato e che non sussistono diritti di prelazione a favore di terzi.
ART. 7) Il prezzo della vendita è stato convenuto in euro 210.000,00 che la parte venditrice dichiara di aver ricevuto.
ART. 8) La parte venditrice dichiara che il fabbricato di cui fa parte quanto in oggetto è stato costruito in forza di licenza edilizia n. 120/1972 rilasciata dal Comune di Treviso in data 3 marzo 1972 e che successivamente sono state eseguite opere in forza di D.I.A. prot. n. 5678 del 10/04/2005. La parte venditrice dichiara che l'agibilità è stata rilasciata dal Comune di Treviso in data 20 dicembre 1974 con prot. n. 999. La parte venditrice dichiara la conformità allo stato di fatto dei dati catastali e delle planimetrie depositate in catasto, ai sensi dell'art. 29, comma 1-bis, della legge 52/1985.
REGISTRATO A TREVISO Il 20 settembre 2025 al n. 8888 serie 1T
Trascritto a Treviso il 22 settembre 2025 ai nn. 55555/40000
"""

OGGI = date(2026, 11, 25)


def test_estremi_e_parti():
    a = provenienza.analizza_testo(ATTO)
    assert (a["notaio"], a["data_atto"], a["repertorio"]) == ("Paolo Neri", "10/03/2024", "1234")
    assert [c["nominativo"] for c in a["intestatari"]] == ["VERDI LUCA"]
    assert [c["nominativo"] for c in a["cedenti"]] == ["GIALLI ANNA"]
    assert a["prezzo"] == "180.000,00"
    assert a["trascrizione"] == "trascritto a Treviso il 21/03/2024 ai nn. 9999/7777"


def test_urbanistica():
    a = provenienza.analizza_testo(ATTO)
    titoli = [(t["tipo"], t["numero"], t["data"]) for t in a["titoli_edilizi"]]
    assert ("Licenza edilizia", "45/1970", "12/03/1970") in titoli
    assert ("Concessione edilizia in sanatoria", "77", "03/02/1990") in titoli
    assert ("S.C.I.A.", "12345", "15/06/2015") in titoli
    assert not any(t[0] == "Concessione edilizia" for t in titoli)
    assert "1 giugno 1972" in a["agibilita_testo"]
    b = provenienza.analizza_testo(ATTO_SUCCESSIONE)
    assert [n["tema"] for n in b["note_urbanistiche"]] == ["Conformità catastale"]


def test_provenienza_donazione():
    a = provenienza.analizza_testo(ATTO)
    (t,) = a["provenienza_precedente"]["titoli"]
    assert (t["tipo"], t["notaio"], t["data"], t["repertorio"]) == ("donazione", "Luigi Fabbri di Padova", "10/01/2015", "777")
    assert t["trascrizione"] == "a Treviso il 22/01/2015 ai nn. 1111/800"


def test_provenienza_successione():
    a = provenienza.analizza_testo(ATTO_SUCCESSIONE)
    s, acc, cv = a["provenienza_precedente"]["titoli"]
    assert (s["tipo"], s["defunto"], s["data_decesso"]) == ("successione", "Rossi Giovanni", "03/03/2010")
    assert s["registrazione"] == "a Treviso il 20/08/2010 al n. 1234 vol. 9990"
    assert s["trascrizione"] == "a Treviso il 15/09/2010 ai nn. 33333/22222"
    assert acc["accettazione_eredita"] and acc["trascrizione"] == "a Treviso il 10/10/2015 ai nn. 44444/30000"
    assert (cv["tipo"], cv["notaio"], cv["data"], cv["repertorio"]) == ("compravendita", "Carlo Verdi di Treviso", "12/05/1975", "5555")


def test_vincoli():
    a = provenienza.analizza_testo(ATTO)
    v = a["vincoli"]
    categorie = [x["categoria"] for x in v["trovati"]]
    assert "Servitù" in categorie and any("passaggio pedonale" in f for x in v["trovati"] for f in x["frasi"])
    # la garanzia di liberta' e' una formula di rito, non un gravame
    assert "Ipoteche, pignoramenti e trascrizioni pregiudizievoli" not in categorie
    assert "Ipoteche, pignoramenti e trascrizioni pregiudizievoli" in v["di_rito"]

    b = provenienza.analizza_testo(ATTO_SUCCESSIONE)["vincoli"]
    ipoteca = next(x for x in b["trovati"] if x["categoria"].startswith("Ipoteche"))
    assert "Banca Esempio S.p.A. a garanzia di un mutuo" in ipoteca["frasi"][0]
    assert ipoteca["gravita"] == "alta"
    assert any("elettrodotto" in f for x in b["trovati"] for f in x["frasi"])
    # "non è locato" e "non sussistono prelazioni" sono dichiarazioni negative, non vincoli
    assert not any(x["categoria"] in ("Diritti di prelazione", "Locazioni, comodati e occupazione") for x in b["trovati"])
    assert any("non sussistono diritti di prelazione" in f for f in b["negative"])


def test_vincoli_che_limitano_la_vendita():
    t = ("ART. 5) L'immobile è stato realizzato nell'ambito di un piano P.E.E.P. ed è soggetto alla convenzione "
         "stipulata con il Comune ai sensi dell'art. 35 della legge 865/1971, che prevede un prezzo massimo di cessione. "
         "ART. 6) Il posto auto è legato da vincolo pertinenziale all'appartamento ai sensi della legge 122/1989. "
         "ART. 7) La parte venditrice si riserva il diritto di abitazione vita natural durante. "
         "ART. 8) L'immobile è dichiarato di interesse storico artistico ai sensi del D.Lgs. 42/2004.")
    v = provenienza.vincoli_gravami(t)
    categorie = {x["categoria"]: x["gravita"] for x in v["trovati"]}
    assert categorie["Edilizia convenzionata / PEEP"] == "alta"
    assert categorie["Vincolo pertinenziale dei parcheggi (L. 122/1989)"] == "media"
    assert categorie["Diritti reali di terzi (usufrutto, abitazione, uso)"] == "alta"
    assert categorie["Vincoli culturali e paesaggistici"] == "alta"


def test_avvisi():
    a = provenienza.analizza_testo(ATTO)
    s = analisi.componi([a], oggi=OGGI)
    testi = " ".join(x["testo"] for x in s["avvisi"])
    assert "DONAZIONE del 10/01/2015" in testi
    assert "sanatorie o condoni" in testi
    assert "prima casa" in testi

    b = provenienza.analizza_testo(ATTO_SUCCESSIONE)
    s = analisi.componi([b], oggi=OGGI)
    gravi = [x for x in s["avvisi"] if x["livello"] == "errore"]
    assert [x["tema"] for x in gravi] == ["vincoli"]          # solo l'ipoteca da cancellare
    assert "accettazione" not in " ".join(x["testo"] for x in s["avvisi"])


def test_successione_senza_accettazione():
    t = ATTO_SUCCESSIONE.replace("; l'accettazione tacita dell'eredità è stata trascritta a Treviso il 10 ottobre 2015 "
                                 "ai nn. 44444/30000", "")
    s = analisi.componi([provenienza.analizza_testo(t)], oggi=OGGI)
    assert any("accettazione dell'eredità" in x["testo"] and x["livello"] == "errore" for x in s["avvisi"])


def test_pdf(tmp_path):
    from sintesi import pdf
    import pymupdf
    a = provenienza.analizza_testo(ATTO_SUCCESSIONE)
    a["_file"], a["_metodo"] = "atto.pdf", "testo digitale"
    s = analisi.componi([a], oggi=OGGI)
    dest = pdf.genera("Neri - Via Roma 10", s, tmp_path / "Sintesi.pdf")
    with pymupdf.open(dest) as doc:
        testo = "".join(p.get_text() for p in doc)
    for atteso in ("Punti di attenzione", "Situazione urbanistica", "Provenienza precedente", "Rossi Giovanni",
                   "Carlo Verdi di Treviso", "Vincoli e gravami", "elettrodotto", "Licenza edilizia", "Pagina 1 di"):
        assert atteso in testo, atteso


def _pdf_da_testo(testo, percorso):
    import pymupdf
    doc = pymupdf.open()
    righe = testo.split("\n")
    for i in range(0, len(righe), 55):
        doc.new_page().insert_text((40, 50), "\n".join(righe[i:i + 55]), fontsize=8)
    doc.save(percorso)


def test_cartella_condivisa(tmp_path, monkeypatch):
    """PDF copiato in una cartella nuova: spostato in Atto_provenienza e sintesi creata da sola."""
    import os
    import time
    from sintesi import archivio, servizio
    monkeypatch.setattr(archivio, "DATI", tmp_path)
    cartella = tmp_path / "Verdi - Via Roma 3"
    cartella.mkdir()
    _pdf_da_testo(ATTO, cartella / "scansione 001.pdf")
    vecchio = time.time() - 120  # copia finita da un po'
    os.utime(cartella / "scansione 001.pdf", (vecchio, vecchio))
    servizio.controlla_cartelle()
    assert (cartella / "Atto_provenienza" / "scansione 001.pdf").exists()
    pdf_creato = cartella / "Sintesi - Verdi - Via Roma 3.pdf"
    assert pdf_creato.exists()
    assert not (cartella / servizio.BLOCCO).exists()
    assert (tmp_path / servizio.LEGGIMI).exists()
    assert archivio.Sintesi(cartella).carica()["pdf"]["origine"] == "cartella condivisa"
    # nessun documento cambiato: il PDF non viene ricreato
    prima = pdf_creato.stat().st_mtime_ns
    servizio.controlla_cartelle()
    assert pdf_creato.stat().st_mtime_ns == prima
    # un altro PC sta gia' lavorando la cartella: si salta
    _pdf_da_testo(ATTO_SUCCESSIONE, cartella / "Atto_provenienza" / "altro.pdf")
    os.utime(cartella / "Atto_provenienza" / "altro.pdf", (vecchio, vecchio))
    (cartella / servizio.BLOCCO).write_text("ALTRO-PC")
    servizio.controlla_cartelle()
    assert pdf_creato.stat().st_mtime_ns == prima
    (cartella / servizio.BLOCCO).unlink()
    servizio.controlla_cartelle()
    assert pdf_creato.stat().st_mtime_ns != prima


# Struttura di un atto reale (notaio di Treviso, 2024) con DATI INVENTATI: intestazioni
# "QUALE PARTE VENDITRICE/ACQUIRENTE", codici fiscali con spazi, righe "=====", data
# "Il giorno ... (gg.mm.aaaa)", registrazione e trascrizione a margine, APE scaduto.
ATTO_REALE = """Repertorio n.297 Raccolta n.238
COMPRAVENDITA
REPUBBLICA ITALIANA
Il giorno venti dicembre duemilaventiquattro. ==========
(20.12.2024)
In Treviso, nel mio studio.
Innanzi a me dott.ssa Anna Esempio, Notaio residente in Treviso, iscritto presso il
Collegio Notarile del Distretto di Treviso, ==========
SONO PRESENTI:
QUALE PARTE VENDITRICE: ============
- BIANCHI Paolo, nato a Treviso il 23 febbraio 1979 e domiciliato in Maserada
sul Piave (TV) alla Via Roma n.46, codice fiscale: BNC PLA 79B23 L407X, cit-
tadino italiano, che dichiara di essere di stato civile libero nonché libero da unioni
civili; ============
QUALE PARTE ACQUIRENTE: ============
- VERDI Marco, nato a Conegliano (TV) il 27 giugno 1993 e residente in
Mareno di Piave (TV) alla Via Dante n.3, codice fiscale: VRD MRC 93H27
C957Y, cittadino italiano, che dichiara di essere celibe nonché libero da unioni civili.
REGISTRATO A TREVISO
il 23/12/2024
al n. 40805 serie 1T
TRASCRITTO A TREVISO
il 24/12/2024
ai nn. 48512/34979
I costituiti convengono e stipulano quanto segue: =======
ART.1) CONSENSO ED OGGETTO ==========
Il signor BIANCHI Paolo VENDE E TRASFERISCE in favore del signor VERDI Marco, che accetta ed acquista, la piena pro-
prietà dei seguenti beni immobili facenti parte del fabbricato sito in Comune di Ma-
serada sul Piave (TV), alla Via Roma n.46 (catastalmente civico n.44), loca-
lità Varago e precisamente:
- appartamento posto al piano terra, composto da cucina, camera e bagno. =======
- garage posto al piano terra, su corpo di fabbrica staccato. =====
- posto auto scoperto al piano terra, pertinenziale all'appartamento. ======
Gli immobili sono riportati nel Catasto Fabbricati del Comune di Maserada sul Piave (TV) come segue:
- Sezione C, Foglio n.5, particella n.218, sub.14, Via Roma n.44, piano T, Cat. A/3, classe 3, vani 3,5,
Superficie Catastale Totale mq.64, R.C. Euro 225,95 (l'appartamento); =======
- Sezione C, Foglio n.5, particella n.218, sub.16, Via Roma n.44, piano T, Cat. C/6, classe U,
consistenza mq.16, Superficie Catastale Totale mq.23, R.C. Euro 47,10 (il garage);
All'uopo la parte venditrice, ai sensi dell'articolo 29, comma 1-bis, della Legge 27 febbraio 1985, n. 52, dichiara
che i dati catastali e le planimetrie sono conformi allo stato di fatto e non sussistono difformità rilevanti. ====
ART.2) PROVENIENZA ===========
Quanto oggetto del presente atto è pervenuto alla parte venditrice in data 03 agosto 2021 con atto di
compravendita a rogito del notaio Luigi Prova, di Silea (TV), Repertorio n.6063, Raccolta n.5040, registrato a
Treviso in data 4 agosto 2021 al numero 28425 Serie 1T e trascritto presso l'Agenzia del Territorio - Servizio
Pubblicità Immobiliare - di Treviso in data 4 agosto 2021 ai numeri 33562/23219. =========
ART.3) PRECISAZIONI ==========
La vendita segue a corpo, nello stato di fatto e di diritto in cui quanto venduto si trova, con le servitù attive
e passive legalmente esistenti e/o costituite, come è posseduto dalla parte alienante. ======
Si richiamano tutti gli obblighi, limitazioni, riserve e servitù derivanti dalla vendita frazionata delle singole
unità, nonché gli obblighi derivanti dal passaggio sotterraneo delle reti tecnologiche (fognature, luce, acqua) con
i relativi pozzetti di ispezione. =======
ART.4) GARANZIE ==========
La parte venditrice dichiara e garantisce di avere la piena ed esclusiva titolarità di quanto alienato e la sua
libertà da livelli, oneri, vincoli, liti pendenti, privilegi anche fiscali, iscrizioni o trascrizioni
pregiudizievoli; precisando l'assenza di terzi aventi diritto a prelazione legale e/o convenzionale. =====
ART.5) PREZZO ======
Le parti dichiarano che il prezzo della presente compravendita è stato convenuto in complessivi Euro 108.000,00.
La medesima parte venditrice rinunzia ad ogni eventuale diritto di ipoteca legale nascente dal presente atto.
ART.8) NORMATIVA URBANISTICA ==========
La parte venditrice DICHIARA CHE
- la costruzione del fabbricato risulta iniziata in data anteriore al giorno 01 settembre 1967; =====
- che successivamente sono stati rilasciati dal Comune i seguenti provvedimenti:
* Concessione-autorizzazione edilizia in sanatoria rilasciata in data 10 settembre 1994, protocollo n. 3696; ====
* Concessione edilizia per ristrutturazione ed ampliamento n.3967, rilasciata in data 31 gennaio 2000; =====
* Concessione edilizia in variante alla concessione edilizia n.3967, rilasciata in data 30 novembre 2000, protocollo n. 14357; ===
La parte venditrice dichiara che l'immobile è stato dichiarato abitabile con certificato di abitabilità numero 37
rilasciato in data 14 giugno 2001. =====
Entrambe le parti si dichiarano edotte che gli accertamenti sulla regolarità urbanistica richiedono un sopralluogo da
parte di un tecnico che ne certifichi la regolarità mediante apposita relazione certificata, cui entrambe le parti
dichiarano di aver rinunciato. =======
ART.9) NORMATIVA ENERGETICA ==========
La parte alienante dichiara che l'immobile è dotato di attestato di prestazione energetica predisposto in data
5 aprile 2016 dal Geom. Mario Prova, nel quale è attribuita classe energetica di rendimento "E". =====
RICHIESTA TASSAZIONE SUL VALORE: la base imponibile ai fini delle imposte di registro, ipotecarie e catastali è il valore.
RICHIESTA AGEVOLAZIONI I CASA ======
La parte acquirente chiede i benefici prima casa e dichiara:
- che non è titolare esclusiva di diritti di proprietà, usufrutto, uso e abitazione di altra casa di abitazione nel Comune;
- di essere a conoscenza dell'obbligo di non alienare quanto in oggetto per cinque anni da oggi.
SEGUE QUANTO ALLEGATO
"""


def test_atto_reale():
    a = provenienza.analizza_testo(ATTO_REALE, "OCR (testo del PDF illeggibile)")
    assert (a["notaio"], a["data_atto"], a["repertorio"], a["raccolta"]) == ("Anna Esempio", "20/12/2024", "297", "238")
    assert a["registrazione"] == "registrato a Treviso il 23/12/2024 al n. 40805 serie 1T"
    assert a["trascrizione"] == "trascritto a Treviso il 24/12/2024 ai nn. 48512/34979"
    venditore, acquirente = a["comparenti"]
    assert (venditore["nominativo"], venditore["codice_fiscale"], venditore["ruolo"]) == ("BIANCHI Paolo", "BNCPLA79B23L407X", "venditrice")
    assert (acquirente["nominativo"], acquirente["stato_civile"], acquirente["data_nascita"]) == ("VERDI Marco", "celibe", "27/06/1993")
    assert [c["nominativo"] for c in a["intestatari"]] == ["VERDI Marco"]
    assert [c["nominativo"] for c in a["cedenti"]] == ["BIANCHI Paolo"]
    assert (a["comune"], a["prov"]) == ("Maserada sul Piave", "TV")
    assert a["descrizione"] == "appartamento al piano terra; garage al piano terra; posto auto scoperto al piano terra"
    assert [(u["sezione"], u["sub"], u["categoria"], u["consistenza"], u["rendita"]) for u in a["catastali"]] == [
        ("C", "14", "A/3", "3,5 vani", "225,95"), ("C", "16", "C/6", "16 mq", "47,10")]
    assert a["prezzo"] == "108.000,00" and a["ante_67"]
    assert [(t["tipo"], t["numero"], t["data"]) for t in a["titoli_edilizi"]] == [
        ("Autorizzazione edilizia in sanatoria", "3696", "10/09/1994"),
        ("Concessione edilizia", "3967", "31/01/2000"),
        ("Concessione edilizia in variante", "3967", "30/11/2000")]
    assert "abitabilità numero 37" in a["agibilita_testo"]
    assert a["urbanistica_testo"].startswith("La parte venditrice DICHIARA CHE")
    assert a["ape"]["data"] == "05/04/2016" and a["ape"]["scadenza"] == "05/04/2026" and a["ape"]["classe"] == "E"
    (p,) = a["provenienza_precedente"]["titoli"]
    assert (p["notaio"], p["data"], p["repertorio"]) == ("Luigi Prova di Silea", "03/08/2021", "6063")
    assert p["trascrizione"] == "a Treviso il 04/08/2021 ai nn. 33562/23219"
    # solo la servitu' specifica delle reti; garanzie, imposte "ipotecarie", prima casa e rinuncia
    # all'ipoteca legale sono formule di rito
    v = a["vincoli"]
    assert [x["categoria"] for x in v["trovati"] if x["gravita"] != "info"] == ["Servitù"]
    assert "pozzetti" in v["trovati"][0]["frasi"][0]
    assert any("assenza di terzi aventi diritto a prelazione" in f for f in v["negative"])
    temi = [n["tema"] for n in a["note_urbanistiche"]]
    assert "Difformità o abusi dichiarati" not in temi

    s = analisi.componi([a], oggi=OGGI)
    testi = [x["testo"] for x in s["avvisi"]]
    assert any(t.startswith("APE del 05/04/2016 scaduto il 05/04/2026") for t in testi)
    assert any("rinunciato alla relazione di un tecnico" in t for t in testi)
    assert any("sanatorie o condoni" in t for t in testi)
    assert not any(x["tema"] == "vincoli" and x["livello"] == "errore" for x in s["avvisi"])


def test_testo_illeggibile():
    assert provenienza.testo_leggibile(ATTO_REALE)
    assert not provenienza.testo_leggibile("\x04\n\x03\x04\x05ǯ\x07ȱ \x0b\x0c\x0b\r ŗşřȦ" * 40)
