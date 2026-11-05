import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import andamento_settimanale as a
from app import archivio_report as ar
from test_report_consulenti import _personale

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cartella(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "CARTELLA", tmp_path / "report_collaboratori")
    monkeypatch.setattr(a, "CARTELLA_BENCHMARK", tmp_path / "benchmark")


def test_salva_sostituisce_e_archivia(tmp_path, monkeypatch):
    _cartella(tmp_path, monkeypatch)
    r = ar.salva("REPORT_TATIANA_MENSILE_2026.xlsx", _personale())
    assert r.consulente == "TATIANA" and r.mesi == [(2026, 10)]
    assert (ar.CARTELLA / "TATIANA.xlsx").exists()
    ar.salva("REPORT_LAURA.xlsx", _personale("LAURA"))
    # Settimana dopo: nuovo report di Tatiana, la versione precedente va in archivio.
    wb = load_workbook(io.BytesIO(_personale()))
    wb.active["L20"] = 3
    out = io.BytesIO()
    wb.save(out)
    ar.salva("tatiana settimana 2.xlsx", out.getvalue())
    assert [x.consulente for x in ar.elenco()] == ["LAURA", "TATIANA"]
    assert len(list((ar.CARTELLA / "archivio").glob("TATIANA *.xlsx"))) == 1
    assert (ar.CARTELLA / "TATIANA.xlsx").read_bytes() == out.getvalue()
    # Ricaricare lo stesso file non crea copie in archivio.
    ar.salva("x.xlsx", out.getvalue())
    assert len(list((ar.CARTELLA / "archivio").glob("TATIANA *.xlsx"))) == 1
    assert len(ar.file_per_elaborare()) == 2
    assert ar.elimina("LAURA.xlsx") and [x.consulente for x in ar.elenco()] == ["TATIANA"]
    assert ar.percorso("../TATIANA.xlsx") is None


def test_file_copiato_a_mano_e_file_non_valido(tmp_path, monkeypatch):
    _cartella(tmp_path, monkeypatch)
    ar.CARTELLA.mkdir(parents=True)
    (ar.CARTELLA / "copiato dalla rete.xlsx").write_bytes(_personale("SOFIA"))
    (ar.CARTELLA / "rotto.xlsx").write_bytes(b"non excel")
    el = ar.elenco()
    assert el[0].consulente == "SOFIA" and el[1].consulente == "" and el[1].avvisi
    assert [n for n, _ in ar.file_per_elaborare()] == ["copiato dalla rete.xlsx"]


def test_pagine_con_report_salvati(tmp_path, monkeypatch):
    from app import main
    _cartella(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CARTELLA_REPORT", tmp_path / "temp")
    c = TestClient(main.app)
    r = c.post("/collaboratori", files=[("files", ("t.xlsx", _personale(), XLSX)),
                                        ("files", ("l.xlsx", _personale("LAURA"), XLSX)),
                                        ("files", ("rotto.xlsx", b"x", XLSX))])
    assert r.status_code == 200 and "Salvati i report di TATIANA, LAURA" in r.text and "Non salvati" in r.text
    assert "TATIANA.xlsx" in r.text and "LAURA.xlsx" in r.text
    # Andamento settimanale senza scegliere file: usa la cartella.
    r = c.post("/settimanale", data={"anno": 2026, "mese": 10})
    assert r.status_code == 200 and "pronto" in r.text and "LAURA" in r.text and "TATIANA" in r.text
    f = c.get("/collaboratori/file/TATIANA.xlsx")
    assert f.status_code == 200 and f.content[:2] == b"PK"
    assert c.get("/collaboratori/file/..%2Fx.xlsx").status_code == 404
