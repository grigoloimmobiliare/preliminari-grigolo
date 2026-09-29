from datetime import date

from app import testo as tx


def test_numeri_in_lettere():
    assert tx.numero_in_lettere(21) == "ventuno"
    assert tx.numero_in_lettere(23) == "ventitré"
    assert tx.numero_in_lettere(108) == "centotto"
    assert tx.numero_in_lettere(180) == "centottanta"
    assert tx.numero_in_lettere(1100) == "millecento"
    assert tx.numero_in_lettere(23000) == "ventitremila"
    assert tx.numero_in_lettere(190000) == "centonovantamila"
    assert tx.numero_in_lettere(235000) == "duecentotrentacinquemila"
    assert tx.numero_in_lettere(1_000_000) == "unmilione"
    assert tx.numero_in_lettere(2_500_000) == "duemilionicinquecentomila"


def test_importi():
    assert tx.euro_completo("260.000,00") == "Euro 260.000,00 (duecentosessantamila/00)"
    assert tx.euro_completo("260'000,00") == "Euro 260.000,00 (duecentosessantamila/00)"
    assert tx.euro_completo("1234,5") == "Euro 1.234,50 (milleduecentotrentaquattro/50)"
    assert tx.formato_euro("5000") == "5.000,00"
    assert tx.parse_importo("") is None


def test_date():
    assert tx.parse_data("13.01.2034") == date(2034, 1, 13)
    assert tx.parse_data("9 dicembre 1973") == date(1973, 12, 9)
    assert tx.parse_data("2026-09-29") == date(2026, 9, 29)
    assert tx.formato_data("1/2/2025") == "01/02/2025"
    assert tx.lettere_in_numero("duemilaventicinque") == 2025


def test_province():
    assert tx.correggi_provincia("TU") == "TV"
    assert tx.provincia_da_comune("Treviso") == "TV"
