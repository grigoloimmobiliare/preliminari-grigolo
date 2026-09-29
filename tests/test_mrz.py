from datetime import date

from app.estrazione import mrz


def _riga1(numero):
    return f"C<ITA{numero}{mrz.cifra_controllo(numero)}" + "<" * 15


def _riga2(nascita, sesso, scadenza):
    return f"{nascita}{mrz.cifra_controllo(nascita)}{sesso}{scadenza}{mrz.cifra_controllo(scadenza)}ITA" + "<" * 11 + "0"


def test_cie_pulita():
    testo = "\n".join([_riga1("CA12345AB"), _riga2("800315", "M", "300315"), "ROSSI<<MARIO<<<<<<<<<<<<<<<<<<"])
    d = mrz.leggi([testo])
    assert d.numero_documento == "CA12345AB" and d.numero_valido
    assert d.data_nascita == date(1980, 3, 15) and d.nascita_valida
    assert d.scadenza == date(2030, 3, 15) and d.scadenza_valida
    assert (d.cognome, d.nome, d.sesso) == ("ROSSI", "MARIO", "M")


def test_cie_con_errori_ocr():
    # riempitivo letto come K/C/E e 'O' al posto di '0' nel numero
    r1 = _riga1("CA12345AB").replace("<<<<", "<KCE", 1).replace("0", "O")
    r2 = _riga2("800315", "M", "300315").replace("<<<", "<K<", 1)
    d = mrz.leggi([r1 + "\n" + r2])
    assert d.numero_documento == "CA12345AB"
    assert d.affidabile
