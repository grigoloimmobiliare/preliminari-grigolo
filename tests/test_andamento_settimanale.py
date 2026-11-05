import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import andamento_settimanale as a
from app.report_consulenti import ErroreReport
from test_report_consulenti import _personale


def _report_due_mesi(nome="TATIANA") -> bytes:
    """Ottobre 2026 con attività nei giorni 1-3 e 10; settembre con 4 primi appuntamenti il 29."""
    wb = load_workbook(io.BytesIO(_personale(nome)))
    ott = wb["OTTOBRE_26"]
    ott["L14"] = 2                       # 10 ottobre: 2 primi di acquisizione
    sett = wb.copy_worksheet(ott)
    sett.title = "SETTEMBRE_2026"
    for r in range(5, 36):
        for c in range(3, 21):
            sett.cell(r, c).value = None
    sett["L33"] = 4                      # 29 settembre
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _benchmark(righe: dict, intestazioni=("CONSULENTE", "ACQUISIZIONE", "PRIMI", "VISITE")) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "BENCHMARK OTTOBRE"
    for i, h in enumerate(intestazioni, 1):
        ws.cell(3, i, h)
    for r, (nome, valori) in enumerate(righe.items(), 4):
        ws.cell(r, 1, nome)
        for i, v in enumerate(valori, 2):
            ws.cell(r, i, v)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_settimane_da_lunedi_a_domenica():
    s = a.settimane(2026, 10)
    assert [(x.inizio.day, x.fine.day) for x in s] == [(1, 4), (5, 11), (12, 18), (19, 25), (26, 31)]
    assert [x.giorni_lavorativi for x in s] == [3, 6, 6, 6, 6]
    # Novembre 2026 inizia di domenica (festivo): il primo si unisce alla settimana dopo.
    s = a.settimane(2026, 11)
    assert (s[0].inizio, s[0].fine) == (date(2026, 11, 1), date(2026, 11, 8))
    assert s[-1].giorni_lavorativi == 1
    # Festivi: 8, 25 e 26 dicembre.
    assert [x.giorni_lavorativi for x in a.settimane(2026, 12)] == [5, 5, 6, 4, 4]
    assert a._pasqua(2026) == date(2026, 4, 5) and a._pasqua(2027) == date(2027, 3, 28)


def test_leggi_benchmark():
    bm = a.leggi_benchmark(_benchmark({"Tatiana": [9, 40, 25], "Laura": [5, "10", None], "UFFICIO": [60, 200, 120]}))
    assert bm.consulenti["TATIANA"] == {"acquisizioni": 9, "primi": 40, "visite": 25}
    assert bm.consulenti["LAURA"] == {"acquisizioni": 5, "primi": 10}
    assert bm.ufficio["primi"] == 200 and not bm.avvisi
    with pytest.raises(ErroreReport):
        a.leggi_benchmark(_benchmark({"X": [1]}, intestazioni=("NOME", "PIPPO")))


def test_modello_benchmark_si_rilegge(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "CARTELLA_BENCHMARK", tmp_path)
    wb = load_workbook(io.BytesIO(a.modello_benchmark(2026, 11)))
    ws = wb.active
    assert ws.cell(4, 1).value == "CONSULENTE"
    assert ws.cell(ws.max_row, 1).value == "UFFICIO"
    for r in range(5, ws.max_row + 1):
        for c in range(2, ws.max_column + 1):
            ws.cell(r, c, r + c)
    out = io.BytesIO()
    wb.save(out)
    bm = a.salva_benchmark(out.getvalue(), 2026, 11)
    assert len(bm.indicatori) == len(a.INDICATORI) and "TATIANA" in bm.consulenti and bm.ufficio
    # Il modello del mese dopo riprende i valori appena salvati.
    ws2 = load_workbook(io.BytesIO(a.modello_benchmark(2026, 12))).active
    assert ws2.cell(5, 2).value == ws.cell(5, 2).value


def test_andamento_con_benchmark():
    bm = a.leggi_benchmark(_benchmark({"TATIANA": [27, 40, 25], "UFFICIO": [54, 200, 120]}))
    ris = a.elabora([("t.xlsx", _report_due_mesi())], 2026, 10, bm)
    assert ris.con_benchmark and ris.avvisi  # c'è l'avviso del testo "1 villa dei Cedri"
    wb = load_workbook(io.BytesIO(ris.contenuto))
    assert wb.sheetnames == ["SINTESI", "UFFICIO", "TATIANA"]
    ws = wb["TATIANA"]
    _, col_sett, col_tot, righe = a._layout(5)
    r = righe["acquisizioni"]
    assert ws.cell(r, 3).value == 4                                    # settimana prec. (28-30 settembre)
    assert [ws.cell(r, c).value for c in col_sett] == [2, 2, 0, 0, 0]  # 1-4 ottobre e 10 ottobre
    assert ws.cell(r + 1, col_tot).value == 27                         # benchmark del mese
    assert ws.cell(r + 1, col_sett[0]).value == f'=IF(ISNUMBER($I{r + 1}),$I{r + 1}*D$6,"n.d.")'
    assert ws.cell(6, col_sett[0]).value == "=D5/$I$5"
    assert [ws.cell(5, c).value for c in col_sett] == [3, 6, 6, 6, 6]
    assert ws.cell(r + 5, col_sett[0]).value.startswith("=IF(ISNUMBER(C")  # var. % sulla settimana prec.
    u = wb["UFFICIO"]
    assert u.cell(r, col_sett[0]).value == f"=N('TATIANA'!D{r})"
    assert u.cell(r + 1, col_tot).value == 54                           # riga UFFICIO del file benchmark
    s = wb["SINTESI"]
    valori = [c.value for riga in s.iter_rows() for c in riga if isinstance(c.value, str)]
    assert "Contatti" not in valori and "Vendita - visite" in valori    # solo indicatori con benchmark


def test_andamento_senza_benchmark_e_senza_mese_precedente():
    ris = a.elabora([("t.xlsx", _personale())], 2026, 10, None)
    assert not ris.con_benchmark
    assert any("benchmark" in x for x in ris.avvisi) and any("settembre" in x for x in ris.avvisi)
    ws = load_workbook(io.BytesIO(ris.contenuto))["TATIANA"]
    _, _, col_tot, righe = a._layout(5)
    assert ws.cell(righe["primi"], 3).value == "n.d."
    assert ws.cell(righe["primi"] + 1, col_tot).value == "n.d."


def test_pagine_web(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(a, "CARTELLA_BENCHMARK", tmp_path / "benchmark")
    monkeypatch.setattr(main, "CARTELLA_REPORT", tmp_path / "report")
    c = TestClient(main.app)
    assert c.get("/benchmark").status_code == 200
    assert c.get("/benchmark/modello?anno=2026&mese=10").content[:2] == b"PK"
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    r = c.post("/benchmark", data={"anno": 2026, "mese": 10},
               files={"file": ("bm.xlsx", _benchmark({"TATIANA": [27, 40, 25], "UFFICIO": [54, 200, 120]}), xlsx)})
    assert r.status_code == 200 and "valori letti" in r.text and "TATIANA" in r.text
    assert (tmp_path / "benchmark" / "2026-10.xlsx").exists()
    r = c.post("/settimanale", data={"anno": 2026, "mese": 10},
               files=[("personali", ("t.xlsx", _report_due_mesi(), xlsx))])
    assert r.status_code == 200 and "pronto" in r.text
    link = r.text.split('href="/report/scarica/')[1].split('"')[0]
    f = c.get("/report/scarica/" + link)
    assert f.status_code == 200 and load_workbook(io.BytesIO(f.content)).sheetnames[0] == "SINTESI"
