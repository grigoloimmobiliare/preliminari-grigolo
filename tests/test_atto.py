from app.estrazione import atto
from app.estrazione import codice_fiscale as cfm
from datetime import date

CF_VERDI = (lambda b: b + cfm.carattere_controllo(b))(
    cfm.codice_cognome("VERDI") + cfm.codice_nome("LUCA") + cfm.codice_data_sesso(date(1975, 5, 2), "M") + "L407")

TESTO = f"""Repertorio N. 1234
    Raccolta N.  987
COMPRAVENDITA
REPUBBLICA ITALIANA
L'anno duemilaventiquattro il giorno dieci del mese di marzo (10/3/2024).
Davanti a me dottor PAOLO NERI, notaio in Treviso, iscritto presso
SONO COMPARSI I SIGNORI:
- GIALLI ANNA, nata a Padova (PD) il giorno 1 gennaio 1960, residente
a Padova, Via Roma n. 1, codice fiscale GLLNNA60A41G224X, che dichiara di essere di stato civile libero;
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
ART.8) La parte venditrice dichiara che le opere di costruzione del fabbricato in oggetto sono iniziate
anteriormente al 1 settembre 1967. La parte venditrice dichiara che l'abitabilità originaria è stata rilasciata
dal Comune di Treviso in data 1 giugno 1965 con prot. gen. n. 111. Ciascuna parte, ...
REGISTRATO A
 TREVISO
Il 20 marzo 2024
al n.5555 serie 1T
"""


def test_atto():
    d = atto.analizza_testo(TESTO)
    assert (d["repertorio"], d["raccolta"], d["tipo_atto"]) == ("1234", "987", "compravendita")
    assert d["data_atto"] == "10/03/2024"
    assert (d["notaio"], d["notaio_sede"]) == ("Paolo Neri", "Treviso")
    assert d["registrazione"] == "registrato a Treviso il 20/03/2024 al n. 5555 serie 1T"
    assert [c["nominativo"] for c in d["intestatari"]] == ["VERDI LUCA"]
    assert d["comune"] == "Treviso" and d["indirizzo"] == "Via Roma n. 3"
    assert d["descrizione"] == "appartamento posto al primo piano e garage al piano terra"
    u1, u2 = d["catastali"]
    assert (u1["sezione"], u1["foglio"], u1["particella"], u1["sub"]) == ("E", "2", "100", "5")
    assert (u1["categoria"], u1["classe"], u1["consistenza"], u1["rendita"]) == ("A/2", "4", "5,5 vani", "500,00")
    assert (u2["categoria"], u2["consistenza"], u2["rendita"]) == ("C/6", "13 mq", "40,10")
    assert d["ante_67"] is True
    assert d["agibilita"].startswith("rilasciato dal Comune di Treviso in data 1 giugno 1965")


def test_persona_da_comparente():
    d = atto.analizza_testo(TESTO)
    p = atto.persona_da_comparente(d["intestatari"][0])
    assert (p["cognome"], p["nome"], p["sesso"]) == ("VERDI", "LUCA", "M")
    assert p["stato_civile"] == "coniugato in regime di separazione dei beni"
