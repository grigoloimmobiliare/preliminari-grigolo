from datetime import date

from app.estrazione import codice_fiscale as cfm
from sintesi import analisi, provenienza, visura

CF_VERDI = (lambda b: b + cfm.carattere_controllo(b))(
    cfm.codice_cognome("VERDI") + cfm.codice_nome("LUCA") + cfm.codice_data_sesso(date(1975, 5, 2), "M") + "L407")
CF_GIALLI = (lambda b: b + cfm.carattere_controllo(b))(
    cfm.codice_cognome("GIALLI") + cfm.codice_nome("ANNA") + cfm.codice_data_sesso(date(1960, 1, 1), "F") + "G224")
CF_ROSSI = (lambda b: b + cfm.carattere_controllo(b))(
    cfm.codice_cognome("ROSSI") + cfm.codice_nome("MARCO") + cfm.codice_data_sesso(date(2001, 3, 4), "M") + "L407")

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

# visura recente "a schede"
VISURA_NUOVA = f"""Direzione Provinciale di Treviso
Ufficio Provinciale - Territorio
Servizi Catastali
Visura attuale per immobile
Situazione degli atti informatizzati al 28/10/2026
Dati della richiesta
Comune di TREVISO (Codice:L407)
Provincia di TREVISO
Catasto Fabbricati Sez. Urb.: E Foglio: 2 Particella: 100 Sub.: 5
Immobile
> Dati identificativi
Comune di TREVISO (L407) (TV)
Sez. Urb. E Foglio 2 Particella 100 Subalterno 5
> Indirizzo
VIA ROMA n. 3 Piano 1
> Dati di classamento
Rendita: Euro 500,00
Categoria A/2a), Classe 4, Consistenza 5,5 vani
> Dati di superficie
Totale: 95 m2
Totale escluse aree scoperte b): 92 m2
> Intestati catastali
> 1. VERDI Luca (CF {CF_VERDI})
nato a TREVISO (TV) il 02/05/1975
Diritto di: Proprieta' per 1/1 (deriva dall'atto 1)
> Dati derivanti da
1. Atto del 10/03/2024 Pubblico ufficiale NERI PAOLO Sede TREVISO (TV) Repertorio n. 1234 - COMPRAVENDITA
Nota presentata con Modello Unico n. 7777.1/2024 Reparto PI di TREVISO in atti dal 21/03/2024
Visura telematica
"""

# visura del vecchio formato "a tabella" del garage, con successione
VISURA_VECCHIA = f"""Data: 01/02/2026 - Ora: 10.15.22
Visura n.: T12345 Pag: 1
Visura per immobile
Situazione degli atti informatizzati al 01/02/2026
Dati della richiesta Comune di TREVISO ( Codice: L407)
Provincia di TREVISO
Catasto Fabbricati Sez. Urb.: E Foglio: 2 Particella: 100 Sub.: 9
Unità immobiliare
N.
DATI IDENTIFICATIVI DATI DI CLASSAMENTO DATI DERIVANTI DA
Sezione
Urbana
Foglio Particella Sub Zona
Cens.
Micro
Zona
Categoria Classe Consistenza Superficie
Catastale
Rendita
1 E 2 100 9 C/6 2 13 m² Totale: 14 m² Euro 40,10 Variazione del 09/11/2015 - Inserimento in visura dei dati di
superficie.
Indirizzo VIA ROMA n. 3 Piano T
INTESTATI
N. DATI ANAGRAFICI CODICE FISCALE DIRITTI E ONERI REALI
1 ROSSI Marco nato a TREVISO il 04/03/2001 {CF_ROSSI}* (1) Proprieta' 1/2
2 VERDI Anna nata a TREVISO il 01/01/1950 VRDNNA50A41L407Z* (1) Proprieta' 1/2
DATI DERIVANTI DA DENUNZIA (NEI PASSAGGI PER CAUSA DI MORTE) del 12/05/2025 - UU Sede TREVISO (TV) Registrazione
Volume 9990 n. 1234 registrato in data 10/06/2025 - SUCCESSIONE DI VERDI LUCA Voltura n. 5555.1/2025
Mappali Terreni Correlati
"""


def test_visura_nuovo_formato():
    v = visura.analizza_testo(VISURA_NUOVA)
    assert v["data"] == "28/10/2026" and v["comune"] == "Treviso" and v["prov"] == "TV"
    assert v["tipo"] == "attuale per immobile"
    (u,) = v["unita"]
    assert (u["sezione"], u["foglio"], u["particella"], u["sub"]) == ("E", "2", "100", "5")
    assert (u["categoria"], u["classe"], u["consistenza"], u["rendita"], u["superficie"]) == ("A/2", "4", "5,5 vani", "500,00", "95")
    assert u["indirizzo"].startswith("Via Roma n. 3")
    (i,) = v["intestati"]
    assert (i["nominativo"], i["codice_fiscale"], i["data_nascita"]) == ("VERDI Luca", CF_VERDI, "02/05/1975")
    assert i["diritto"] == "Proprietà per 1/1"
    assert visura.estremi_atto_derivante(v["derivanti_da"])["repertorio"] == "1234"
    assert not v["successione"]


def test_visura_vecchio_formato_con_successione():
    v = visura.analizza_testo(VISURA_VECCHIA)
    (u,) = v["unita"]
    assert (u["sezione"], u["foglio"], u["particella"], u["sub"], u["categoria"], u["classe"]) == ("E", "2", "100", "9", "C/6", "2")
    assert (u["consistenza"], u["superficie"], u["rendita"]) == ("13 mq", "14", "40,10")
    assert u["piano"] == "T"
    assert [i["nominativo"] for i in v["intestati"]] == ["ROSSI Marco", "VERDI Anna"]
    assert [i["diritto"] for i in v["intestati"]] == ["Proprietà 1/2", "Proprietà 1/2"]
    assert v["successione"]["defunto"] == "VERDI LUCA"
    assert v["successione"]["data"] == "12/05/2025"


def test_provenienza():
    a = provenienza.analizza_testo(ATTO)
    assert [c["nominativo"] for c in a["intestatari"]] == ["VERDI LUCA"]
    assert [c["nominativo"] for c in a["cedenti"]] == ["GIALLI ANNA"]
    assert a["prezzo"] == "180.000,00"
    assert a["prima_casa"] is True
    assert a["trascrizione"] == "trascritto a Treviso il 21/03/2024 ai nn. 9999/7777"
    titoli = [(t["tipo"], t["numero"], t["data"]) for t in a["titoli_edilizi"]]
    assert ("Licenza edilizia", "45/1970", "12/03/1970") in titoli
    assert ("Concessione edilizia in sanatoria", "77", "03/02/1990") in titoli
    assert ("S.C.I.A.", "12345", "15/06/2015") in titoli
    assert not any(t[0] == "Concessione edilizia" for t in titoli)
    assert "1 giugno 1972" in a["agibilita_testo"]
    cl = a["clausole"]
    assert any("passaggio pedonale" in f for f in cl["Servitù"])
    assert "Regolamento di condominio e parti comuni" in cl
    # la garanzia di liberta' e' una formula di rito, non una clausola particolare
    assert "Ipoteche, pignoramenti e gravami" not in cl
    assert "Ipoteche, pignoramenti e gravami" in cl["_formule_di_rito"]


def test_componi_coincidono():
    a = provenienza.analizza_testo(ATTO)
    a["_file"] = "atto.pdf"
    v = visura.analizza_testo(VISURA_NUOVA)
    v["_file"] = "visura.pdf"
    s = analisi.componi([a], [v], oggi=date(2026, 11, 3))
    assert s["coincidono"] is True
    assert [p["codice_fiscale"] for p in s["proprietari"]] == [CF_VERDI]
    testi = " ".join(x["testo"] for x in s["avvisi"])
    assert "mappale" not in testi
    # il garage dell'atto non ha la visura
    assert "sub 9 dell'atto non compare" in testi
    assert "prima casa" in testi


def test_componi_successione():
    a = provenienza.analizza_testo(ATTO)
    v = visura.analizza_testo(VISURA_VECCHIA)
    s = analisi.componi([a], [v], oggi=date(2026, 11, 3))
    assert s["coincidono"] is False
    gravi = [x["testo"] for x in s["avvisi"] if x["livello"] == "errore"]
    assert any("successione di Verdi Luca del 12/05/2025" in g for g in gravi)
    assert any("più vecchia di 3 mesi" in x["testo"] for x in s["avvisi"])


def test_pdf(tmp_path):
    from sintesi import pdf
    a = provenienza.analizza_testo(ATTO)
    a["_file"], a["_metodo"] = "atto.pdf", "testo digitale"
    v1 = visura.analizza_testo(VISURA_NUOVA)
    v2 = visura.analizza_testo(VISURA_VECCHIA)
    v1["_file"], v2["_file"] = "visura sub 5.pdf", "visura sub 9.pdf"
    s = analisi.componi([a], [v1, v2], oggi=date(2026, 11, 3))
    dest = pdf.genera("Verdi - Via Roma 3", s, tmp_path / "Sintesi.pdf")
    import pymupdf
    with pymupdf.open(dest) as doc:
        testo = "".join(p.get_text() for p in doc)
    for atteso in ("Proprietari attuali", "VERDI Luca", "Licenza edilizia", "45/1970", "Rep", "1234",
                   "passaggio pedonale", "Pagina 1 di"):
        assert atteso in testo, atteso
