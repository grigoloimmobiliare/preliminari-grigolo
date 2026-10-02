import importlib

import openpyxl
import pytest

from app import comuni


@pytest.mark.parametrize("indirizzo, atteso", [
    ("Via Roma 10, Jesolo (VE)", ("Jesolo", "VE")),
    ("Piazza Milano 3 - 30016 Jesolo", ("Jesolo", "VE")),
    ("Via Roma 10 Jesolo", ("Jesolo", "VE")),
    ("Via G. Biscaro 11, San Donà di Piave", ("San Donà di Piave", "VE")),
    ("via Vittorio Veneto 1, Ponte di Piave", ("Ponte di Piave", "TV")),
    ("Via Garibaldi 5, 31100 Treviso TV", ("Treviso", "TV")),
    ("Via Roma 4, Castro (LE)", ("Castro", "LE")),
    ("Via Dante 2, Castro", ("Castro", None)),          # due comuni con questo nome: provincia da scrivere
    ("Via Roma 10", None),                              # "Roma" è la via, non il comune
    ("Galleria Bailo 11", None),
])
def test_comune_dall_indirizzo(indirizzo, atteso):
    assert comuni.dall_indirizzo(indirizzo) == atteso


def test_provincia_dal_comune():
    assert comuni.provincia("JESOLO") == "VE"
    assert comuni.provincia("san dona' di piave") == "VE"
    assert comuni.provincia("Treviso") == "TV"
    assert comuni.provincia("Castro") is None
    assert comuni.provincia("Nonesiste") is None


def _excel(tmp_path, **celle):
    from conftest import RADICE
    wb = openpyxl.load_workbook(RADICE / "modelli" / "stima_modello.xlsx")
    ws = wb["Foglio2"]
    for k, v in celle.items():
        ws[k] = v
    p = tmp_path / "stima.xlsx"
    wb.save(p)
    return p


@pytest.mark.parametrize("celle, pagina, atteso", [
    ({"B4": "Via Roma 10, Jesolo", "B5": "B1"}, {}, ("Jesolo", "VE", "indirizzo")),
    ({"B4": "Via Roma 10", "D5": "Jesolo", "B5": "B1"}, {}, ("Jesolo", "VE", "Excel")),
    ({"B4": "Via Roma 10", "B5": "B1"}, {}, ("TREVISO", "TV", "predefinito")),
    ({"B4": "Via Roma 10, Jesolo"}, {"comune": "Eraclea"}, ("Eraclea", "VE", "pagina")),
])
def test_parametri_omi(tmp_path, monkeypatch, celle, pagina, atteso):
    monkeypatch.setenv("VALUTAZIONI_DATI", str(tmp_path / "dati"))
    from app import archivio, excel, genera
    importlib.reload(archivio)
    importlib.reload(genera)
    v = archivio.crea("Prova")
    if pagina:
        stato = v.carica()
        stato.update(pagina)
        v.salva(stato)
    par = genera.parametri_omi(v, excel.leggi(_excel(tmp_path, **celle)))
    assert (par["comune"], par["provincia"], par["fonte"]) == atteso
    assert par["avvisi"] == []
