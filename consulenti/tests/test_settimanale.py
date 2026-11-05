import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import settimanale as a
from app.report_mensile import ErroreReport
from test_report_mensile import _personale


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
    assert "Contatti" not in valori and "Vendita - II appuntamento (visite)" in valori    # solo indicatori con benchmark


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
    from app import config
    monkeypatch.setattr(config, "DATI", tmp_path)
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
    link = r.text.split('href="/risultati/')[1].split('"')[0]
    f = c.get("/risultati/" + link)
    assert f.status_code == 200 and load_workbook(io.BytesIO(f.content)).sheetnames[0] == "SINTESI"
    # Il file resta nella cartella dei dati (risultati) e compare nella pagina iniziale.
    assert (tmp_path / "risultati" / "Andamento settimanale ott 26.xlsx").exists()
    assert "Andamento settimanale ott 26.xlsx" in c.get("/").text
    assert c.get("/risultati/..%2F..%2Fx.xlsx").status_code == 404


def test_benchmark_formato_ufficio():
    """Il formato usato in ufficio: riquadro dell'ufficio in verticale sopra la tabella dei consulenti,
    intestazioni 1/2 APPUNTAMENTO (acquisizione) e I/II APP (vendita), colonne MANDATI e BUDGET."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws["A2"] = "benchmark complessivi ufficio MENSILI"
    for r, (k, v) in enumerate([("1 APPUNTAMENTO", 50), ("2 APPUNTAMENTO", 50), ("INCARICO", 12), ("MANDATTI", 27)], 3):
        ws.cell(r, 1, k)
        ws.cell(r, 2, v)
    ws["A11"] = "benchmark SINGOLI MENSILI"
    intest = ["CONTATTI", "NOTIZIE", "1 APPUNTAMENTO", "2 APPUNTAMENTO", "INCARICO", "MANDATI", "I APP",
              "II APP", "PROPOSTE", "BUDGET"]
    for i, h in enumerate(intest, 2):
        ws.cell(12, i, h)
    righe = {"ROSSI": [480, 30, 20, 20, 4, 4, 10, 10, 2, 30000], "BIANCHI": [None] * 6 + [20, 20, 4, "40.000"]}
    for r, (nome, valori) in enumerate(righe.items(), 13):
        ws.cell(r, 1, nome)
        for i, v in enumerate(valori, 2):
            ws.cell(r, i, v)
    ws["J15"], ws["K15"] = "TOTALE", 70000
    out = io.BytesIO()
    wb.save(out)
    bm = a.leggi_benchmark(out.getvalue())
    assert bm.consulenti["ROSSI"] == {"contatti": 480, "notizie": 30, "acquisizioni": 20, "consegne": 20,
                                      "esclusive": 4, "primi": 10, "visite": 10, "proposte": 2, "mandati": 4,
                                      "budget": 30000}
    assert bm.consulenti["BIANCHI"] == {"primi": 20, "visite": 20, "proposte": 4, "budget": 40000}
    assert bm.ufficio == {"acquisizioni": 50, "consegne": 50, "esclusive": 12, "mandati": 27}
    assert not bm.non_misurati
    assert any("somma dei consulenti" in x for x in bm.avvisi)
    # Ufficio: valore del file dove c'è, altrimenti somma dei consulenti.
    ris = a.elabora([("t.xlsx", _report_due_mesi("BIANCHI"))], 2026, 10, bm)
    u = load_workbook(io.BytesIO(ris.contenuto))["UFFICIO"]
    _, _, col_tot, righe_l = a._layout(5)
    assert u.cell(righe_l["acquisizioni"] + 1, col_tot).value == 50
    assert u.cell(righe_l["primi"] + 1, col_tot).value == f"=N('BIANCHI'!I{righe_l['primi'] + 1})"
    assert any("ROSSI" in x for x in ris.avvisi) is False  # Rossi senza report: nessun foglio, nessun errore


def _report_nuovo_formato() -> bytes:
    """Report personale come rivisto a novembre 2026: dopo PROPOSTE ci sono RIF PROP, EXCL, RIF ESCL,
    MANDATI, RIFA MAND, PRELIMINARI, RIF PREL, BUDGET e GESTIONE (tutto sotto APPUNTAMENTI)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "OTTOBRE_26"
    ws["A1"], ws["E1"], ws["G1"] = "MESE", "CONSULENTE", "TATIANA"
    ws["A2"], ws["C2"], ws["E2"], ws["G2"], ws["L2"] = "DATA", "CONTATTI", "NOTIZIE", "RICHIESTE", "APPUNTAMENTI"
    ws.merge_cells("C2:D2"); ws.merge_cells("E2:F2"); ws.merge_cells("G2:K2"); ws.merge_cells("L2:Y2")
    for cella, v in {"G3": "NUOVE", "I3": "VECCHIE", "L3": "ACQUISIZIONE", "N3": "VENDITA", "P3": "PROPOSTE",
                     "Q3": "RIF PROP", "R3": "EXCL", "S3": "RIF ESCL", "T3": "MANDATI", "U3": "RIFA MAND",
                     "V3": "PRELIMINARI", "W3": "RIF PREL", "X3": "BUDGET", "Y3": "GESTIONE",
                     "G4": "CHIAMATE", "H4": "FISSATE", "I4": "CHIAMATE", "J4": "MESSAGGI", "K4": "FISSATE",
                     "L4": "PRIMO", "M4": "SECONDO", "N4": "INFORMATIVO", "O4": "VISITA",
                     "AA4": "PERFORMANCE", "AC4": "BUDGET"}.items():
        ws[cella] = v
    for m in ("G3:H3", "I3:K3", "L3:M3", "N3:O3", *(f"{c}3:{c}4" for c in "PQRSTUVWXY")):
        ws.merge_cells(m)
    for g in range(1, 32):
        ws.cell(4 + g, 1, g)
    # 2 ottobre: proposta GT316 e un mandato; 6 ottobre: esclusiva B9 (mandato) e 2.500 €; 20 ottobre: 10.000 €
    for cella, v in {"P6": 1, "Q6": "GT316", "T6": 1, "U6": "GT316",
                     "R10": 1, "S10": "B9", "T10": 1, "U10": "B9", "X10": 2500,
                     "V24": 1, "W24": "jesolo", "X24": 10000,
                     "AB6": "CONTATTI", "AC6": 0}.items():
        ws[cella] = v
    ws["G37"], ws["G38"] = "MARKETING", "PROF"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_mandati_e_budget_settimanali():
    from app.report_mensile import leggi_report_personale
    rp = leggi_report_personale(_report_nuovo_formato(), 2026, 10, "t.xlsx")
    assert rp.totali["mandati"] == 2 and rp.totali["budget"] == 12500
    assert rp.totali["proposte"] == 1 and rp.totali["esclusive"] == 1 and rp.totali["preliminari"] == 1
    assert not rp.avvisi  # i riferimenti (GT316, B9, ...) non vengono contati
    bm = a.leggi_benchmark(_benchmark({"TATIANA": [6, 40000], "UFFICIO": [27, 220000]},
                                      intestazioni=("CONSULENTE", "MANDATI", "BUDGET")))
    ris = a.elabora([("t.xlsx", _report_nuovo_formato())], 2026, 10, bm)
    assert not any("manca la colonna" in x for x in ris.avvisi)
    wb = load_workbook(io.BytesIO(ris.contenuto))
    ws = wb["TATIANA"]
    _, col_sett, col_tot, righe = a._layout(5)
    assert [ws.cell(righe["mandati"], c).value for c in col_sett] == [1, 1, 0, 0, 0]
    r = righe["budget"]
    assert [ws.cell(r, c).value for c in col_sett] == [0, 2500, 0, 10000, 0]
    assert ws.cell(r + 1, col_tot).value == 40000 and ws.cell(r, col_sett[0]).number_format == "#,##0 €"
    u = wb["UFFICIO"]
    assert u.cell(r + 1, col_tot).value == 220000
    # Report col vecchio formato: avviso per le colonne che mancano.
    ris = a.elabora([("t.xlsx", _report_due_mesi())], 2026, 10, bm)
    assert any("manca la colonna MANDATI e la colonna BUDGET" in x for x in ris.avvisi)
