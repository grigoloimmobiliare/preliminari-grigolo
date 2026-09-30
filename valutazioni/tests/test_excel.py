from app import excel


def test_lettura_modello_compilato(excel_compilato):
    d = excel.leggi(excel_compilato)
    assert d.valore("CLIENTE") == "Sig. Mario Rossi"
    assert d.valore("ZONA OMI") == "B1"
    assert d.valore("TIPOLOGIA") == "Appartamento al piano secondo"
    assert [v.nome for v in d.vani] == ["Ingresso", "Soggiorno", "Cucina", "Camera 1", "Camera 2"]
    assert [v.nome for v in d.pertinenze] == ["Garage", "Terrazzi/Poggioli"]
    assert d.tot_mq == 75.5
    assert d.tot_valore_tipologia == 75.5 * 2202
    assert round(d.valore_nuovo) == round(75.5 * 2202 + 18 * 2202 + 9 * 2202 / 3)
    assert round(d.valore_attuale) == round(d.valore_nuovo * 0.7)
    assert d.unicita == ["Posizione centrale", "Ampia terrazza abitabile"]
    assert d.criticita == ["Assenza di ascensore"]
    assert d.avvisi   # formule senza valore salvato: ricalcolate


def test_modello_vuoto_non_ha_voci():
    from conftest import RADICE
    d = excel.leggi(RADICE / "modelli" / "stima_modello.xlsx")
    assert d.vani == [] and d.pertinenze == []
    assert d.valore("CLIENTE") is None       # cella vuota: non prende l'etichetta vicina


def test_formati():
    assert excel.fmt_euro(166251.4) == "166.251"
    assert excel.fmt_numero(30.5) == "30,5"
    assert excel.fmt_numero(1234) == "1.234"
    assert excel.fmt_quota(1) == "per intero"
    assert excel.fmt_quota(0.333333333) == "ad 1/3"
    assert excel.fmt_quota(0.1) == "al 10%"
    assert excel.numero("2.202,50 €") == 2202.5
