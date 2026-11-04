import io

import pytest
from openpyxl import Workbook, load_workbook

from app import report_consulenti as rc

INTESTAZIONI = ["CONTATTI", "MAIL", "TEL", "NOTIZIE", "RICHIESTE", "MUTUO", "I APP", "II APP", "INCARICO",
                "GESTIONE", "ASSEGNATE", "NUOVE", "FISSATE", "VECCHIE", "FISSATE", "I APP", "II APP",
                "PROPOSTE", "RIF PROPOSTA", "ACCETTATA", "VEND. SUB", "VEND. ALTRI", "VEND. PROP.",
                "VENDITA IE", " FISSATI", "INCARICO", "EROGATO"]
COL = {(h.strip(), n): i + 2 for i, h in enumerate(INTESTAZIONI)
       for n in range(2) if [x.strip() for x in INTESTAZIONI[:i + 1]].count(h.strip()) == n + 1}


def _foglio_mensile(wb, titolo, righe):
    ws = wb.create_sheet(titolo)
    ws["A1"] = "GRIGOLO IMMOBILIARE"
    ws["A2"], ws["B2"], ws["H2"], ws["Q2"] = "R.U.", "RICERCA", "ACQUISIZIONE", "VENDITA"
    for i, h in enumerate(INTESTAZIONI):
        ws.cell(3, i + 2, h)
    r = 4
    for nome, valori in righe:
        ws.cell(r, 1, nome)
        for (h, n), v in valori.items():
            ws.cell(r, COL[(h, n)], v)
        r += 1
    ws.cell(r, 1, None)  # riga libera
    ws.cell(r + 1, 1, "MKTG")
    ws.cell(r + 3, 1, "TOT")
    ws.cell(r + 3, 2, f"=SUM(B4:B{r + 2})")
    ws.cell(r + 4, 1, "OBIETTIVO")
    ws.cell(r + 4, 8, 50)
    return ws


def _mensile() -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    _foglio_mensile(wb, "ottobre 25", [("TATIANA", {("I APP", 0): 1, ("PROPOSTE", 0): 1})])
    _foglio_mensile(wb, "sett 26", [("LAURA", {("I APP", 0): 4, ("NUOVE", 0): 10}),
                                    ("TATIANA", {("I APP", 0): 3, ("NUOVE", 0): 20, ("PROPOSTE", 0): 2})])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _personale(nome="TATIANA", foglio="OTTOBRE_26") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = foglio
    ws["A1"], ws["C1"], ws["E1"], ws["G1"] = "MESE", "OTTOBRE", "CONSULENTE", nome
    ws["A2"], ws["C2"], ws["E2"], ws["G2"], ws["L2"] = "DATA", "CONTATTI", "NOTIZIE", "RICHIESTE", "APPUNTAMENTI"
    ws.merge_cells("C2:D2"); ws.merge_cells("E2:F2"); ws.merge_cells("G2:K2"); ws.merge_cells("L2:T2")
    for cella, v in {"C3": "ZONA", "D3": "TELEM", "E3": "ZONA", "F3": "TELEM", "G3": "NUOVE", "I3": "VECCHIE",
                     "L3": "ACQUISIZIONE", "N3": "VENDITA", "P3": "PROPOSTE", "Q3": "EXCL", "R3": "PRELIMINARI",
                     "S3": "MUTUI", "T3": "GESTIONE", "G4": "CHIAMATE", "H4": "FISSATE", "I4": "CHIAMATE",
                     "J4": "MESSAGGI", "K4": "FISSATE", "L4": "PRIMO", "M4": "SECONDO", "N4": "INFORMATIVO",
                     "O4": "VISITA"}.items():
        ws[cella] = v
    for m in ("G3:H3", "I3:K3", "L3:M3", "N3:O3", "P3:P4", "Q3:Q4", "R3:R4", "S3:S4", "T3:T4"):
        ws.merge_cells(m)
    giorni = {5: {"C": 2, "D": 1, "G": 4, "H": 2, "L": 1, "N": 3},
              6: {"E": 1, "I": 5, "J": 9, "K": 1, "M": 1, "O": 2, "P": 1, "R": "1 villa dei Cedri"},
              7: {"G": 3, "L": 1, "Q": 1, "T": 1, "S": 1}}
    for g in range(1, 32):
        ws.cell(4 + g, 1, g)
        for col, v in giorni.get(4 + g, {}).items():
            ws[f"{col}{4 + g}"] = v
    ws["G37"], ws["G38"] = "MARKETING", "PROF"
    ws["G39"] = "=SUM(G5:G36)"
    ws["V29"], ws["W29"], ws["X29"], ws["Y29"], ws["Z29"] = "PROPOSTA", "RIF", "NOME", "OFFERTA", "ESITO"
    ws["W31"], ws["X31"], ws["Y31"], ws["Z31"] = "GT316", "Mario Rossi", 165000, "accettata"
    ws["W32"], ws["X32"], ws["Y32"] = "B9", "Anna Bianchi", 200000
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.mark.parametrize("nome,atteso", [
    ("ott 26", (2026, 10)), ("SETT 25", (2025, 9)), ("ottobre 25", (2025, 10)), ("GIU 26", (2026, 6)),
    ("OTTOBRE_26", (2026, 10)), ("GIUGNO_2026", (2026, 6)), ("mag 26", (2026, 5)), ("mar 26", (2026, 3)),
    ("GENNAIO", None), ("CONFRONTO", None),
])
def test_mese_da_nome(nome, atteso):
    assert rc.mese_da_nome(nome) == atteso


def test_lettura_report_personale():
    rp = rc.leggi_report_personale(_personale(), 2026, 10, "REPORT_TATIANA_MENSILE_2026.xlsx")
    assert rp.consulente == "TATIANA"
    t = rp.totali
    assert t["contatti"] == 3 and t["notizie"] == 1
    assert t["rich_nuove"] == 7 and t["rich_nuove_fissate"] == 2
    assert t["rich_vecchie"] == 5 and t["rich_vecchie_fissate"] == 1   # i messaggi non contano
    assert t["acq_1"] == 2 and t["acq_2"] == 1
    assert t["vend_1"] == 3 and t["vend_2"] == 2
    assert t["proposte"] == 1 and t["esclusive"] == 1 and t["gestioni"] == 1 and t["mutui"] == 1
    assert t["preliminari"] == 1                                        # "1 villa dei Cedri"
    assert any("villa dei Cedri" in a for a in rp.avvisi)
    assert [p["rif"] for p in rp.proposte] == ["GT316", "B9"]


def test_mese_mancante_nel_report_personale():
    with pytest.raises(rc.ErroreReport, match="dicembre"):
        rc.leggi_report_personale(_personale(), 2026, 12, "r.xlsx")


def test_crea_mese_e_confronto():
    ris = rc.elabora(_mensile(), "mensile.xlsx", [("t.xlsx", _personale()), ("m.xlsx", _personale("MATTIA"))], 2026, 10)
    assert ris.foglio == "ott 26" and ris.foglio_creato
    wb = load_workbook(io.BytesIO(ris.contenuto))
    assert wb.sheetnames[:2] == ["CONFRONTO", "VARIAZIONI"]
    ws = wb["ott 26"]
    righe = {ws.cell(r, 1).value: r for r in range(4, 9)}
    t = righe["TATIANA"]
    assert ws.cell(t, COL[("I APP", 0)]).value == 2
    assert ws.cell(t, COL[("I APP", 1)]).value == 3
    assert ws.cell(t, COL[("FISSATE", 1)]).value == 1
    assert ws.cell(t, COL[("VEND. ALTRI", 0)]).value == 1
    assert ws.cell(t, COL[("RIF PROPOSTA", 0)]).value == "GT316/B9"
    assert ws.cell(t, COL[("ACCETTATA", 0)]).value == "GT316"
    # I dati di settembre di Laura non vengono ricopiati nel nuovo mese.
    assert ws.cell(righe["LAURA"], COL[("I APP", 0)]).value is None
    # Mattia non era nel foglio: va nella riga libera.
    assert "MATTIA" in righe
    assert ws.cell(righe["MATTIA"] + 3, 2).value.startswith("=SUM(")  # formula TOT intatta
    assert ws.cell(righe["MATTIA"] + 4, 8).value == 50                 # obiettivo intatto

    c = wb["CONFRONTO"]
    riga = next(r for r in range(1, 60) if c.cell(r, 1).value == "Acquisizione - I appuntamento")
    assert c.cell(riga, 2).value == "=SUM('ott 26'!H4:H6)"
    assert c.cell(riga, 3).value == "=SUM('sett 26'!H4:H6)"
    assert c.cell(riga, 5).value == "=SUM('ottobre 25'!H4:H5)"
    assert c.cell(riga, 4).value.startswith("=IF(ISNUMBER(C")
    assert "'sett 26'" in c.cell(riga, 7).value and "'ottobre 25'" not in c.cell(riga, 7).value
    tatiana = next(r for r in range(1, 200) if c.cell(r, 1).value == "TATIANA")
    assert c.cell(tatiana + 2, 2).value == f"=N('ott 26'!B{t})"


def test_aggiorna_mese_esistente():
    ris = rc.elabora(_mensile(), "mensile.xlsx", [("t.xlsx", _personale(foglio="SETTEMBRE_2026"))], 2026, 9)
    assert not ris.foglio_creato
    ws = load_workbook(io.BytesIO(ris.contenuto))["sett 26"]
    assert ws.cell(5, COL[("I APP", 0)]).value == 2       # Tatiana aggiornata
    assert ws.cell(4, COL[("I APP", 0)]).value == 4       # Laura invariata
