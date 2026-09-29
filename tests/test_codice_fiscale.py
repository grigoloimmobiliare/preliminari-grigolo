from datetime import date

from app.estrazione import codice_fiscale as cfm


def _cf(cognome, nome, nascita, sesso, belfiore):
    base = cfm.codice_cognome(cognome) + cfm.codice_nome(nome) + cfm.codice_data_sesso(nascita, sesso) + belfiore
    return base + cfm.carattere_controllo(base)


ROSSI = _cf("ROSSI", "MARIO", date(1980, 3, 15), "M", "L407")
BIANCHI = _cf("BIANCHI", "GIULIA", date(1992, 7, 4), "F", "F999")


def test_codici():
    assert cfm.codice_cognome("ROSSI") == "RSS"
    assert cfm.codice_nome("GIANFRANCO") == "GFR"  # con 4+ consonanti: 1a, 3a, 4a
    assert cfm.valido(ROSSI) and cfm.valido(BIANCHI)
    assert cfm.sesso(BIANCHI) == "F"
    assert cfm.data_nascita(ROSSI) == date(1980, 3, 15)


def test_candidati_da_ocr_con_errori():
    # 'O' al posto di '0' e spazi come nella bozza: il CF viene comunque riconosciuto
    sporco = ROSSI[:9] + ROSSI[9:11].replace("1", "I") + " " + ROSSI[11:]
    assert ROSSI in cfm.candidati("CODICE FISCALE " + sporco)


def test_ricostruzione():
    # cognome e nome certi, data dalla MRZ: il comune di nascita si legge dal testo
    letto = "V" + ROSSI[1:6] + ROSSI[6:]  # prime lettere sbagliate
    assert cfm.ricostruisci([letto], "ROSSI", "MARIO", date(1980, 3, 15), "M") == ROSSI


def test_coerenza():
    assert cfm.coerenza(ROSSI, "ROSSI", "MARIO", date(1980, 3, 15), "M") == []
    assert cfm.coerenza(ROSSI, "ROSSI", "LUCA", date(1980, 3, 15), "M")
    assert cfm.coerenza(ROSSI[:15] + "A", "ROSSI", "MARIO")  # carattere di controllo errato
