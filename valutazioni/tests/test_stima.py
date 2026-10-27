import importlib
from pathlib import Path

import pytest

from app import excel, stima


def _esempio():
    s = stima.vuota({"zona": "E3", "comune_nome": "Jesolo"})
    s.update(zona="Lido", tipologia="Appartamento", indirizzo="Via Levantina 40, Jesolo", cliente="Rossi",
             firma="Grigolo Mattia", valore_mq=3000, valore_mq_garage=2000, vetusta=10,
             unicita=["Vista mare", "Ascensore"], criticita=["Rumore"])
    for v, mq in zip(s["vani"], [6, 30, 12, 16, 11, 0, 7, 0, 2]):
        v["mq"] = mq
    s["pertinenze"][0]["mq"] = 18          # garage, al valore garage
    s["pertinenze"][3]["mq"] = 9           # terrazzi al 33%
    s["pertinenze"][6]["valore"] = 15000   # box a corpo
    return s


def test_excel_della_stima_letto_come_quello_a_mano(tmp_path):
    """L'Excel creato dalla stima della pagina dà gli stessi conti, letto dal programma."""
    s = _esempio()
    c = stima.calcola(s)
    assert c["nuovo"] == pytest.approx(84 * 3000 + 18 * 2000 + 9 * 3000 / 3 + 15000)
    d = excel.leggi(stima.scrivi_excel(s, tmp_path / "stima.xlsx"))
    assert d.avvisi == []
    assert d.tot_mq == 84
    assert d.valore_nuovo == pytest.approx(c["nuovo"])
    assert d.valore_attuale == pytest.approx(c["attuale"])
    assert d.valore_commerciale == pytest.approx(c["attuale"] * 1.10)
    assert [x.nome for x in d.pertinenze] == ["Garage", "Terrazzi/Poggioli", "Box auto"]
    assert d.pertinenze[2].a_corpo and d.pertinenze[2].valore == 15000
    assert (d.valore("ZONA OMI"), d.valore("COMUNE"), d.valore("FIRMA")) == ("E3", "Jesolo", "Grigolo Mattia")
    assert d.unicita == ["Vista mare", "Ascensore"] and d.criticita == ["Rumore"]


def test_stima_dalla_pagina_e_word(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUTAZIONI_DATI", str(tmp_path / "dati"))
    from app import archivio, genera, main
    importlib.reload(archivio)
    importlib.reload(genera)
    importlib.reload(main)
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    v = archivio.crea("Stima nel programma")
    form = {"zona": "Centro", "comune": "Treviso", "zona_omi": "B1", "valore_mq": "2.300", "vetusta": "30",
            "data": "2026-10-27", "valore_commerciale": "", "unicita": "Centro storico\nVista", "criticita": ""}
    for i, (n, m) in enumerate([("Soggiorno", "30,5"), ("Cucina", "12"), ("", "")]):
        form |= {f"vano_nome_{i}": n, f"vano_mq_{i}": m, f"vano_perc_{i}": "100"}
    form |= {"pert_nome_0": "Cantina", "pert_mq_0": "9", "pert_perc_0": "33,33", "pert_valore_0": ""}
    r = c.post(f"/valutazioni/{v.id}/stima", data=form, follow_redirects=True)
    assert r.status_code == 200 and "Apri l&#39;Excel della stima" in r.text or "Apri l'Excel della stima" in r.text
    d = excel.leggi(v.cartella_categoria("excel") / stima.NOME_FILE)
    assert [(x.nome, x.mq) for x in d.vani] == [("Soggiorno", 30.5), ("Cucina", 12)]
    assert d.valore_nuovo == pytest.approx(42.5 * 2300 + 9 * 0.3333 * 2300)
    assert d.valore_attuale == pytest.approx(d.valore_nuovo * 0.7)
    messaggi = []
    doc = genera.genera(v, messaggi, cerca_omi=False)
    assert Path(doc).exists()
    assert any("Excel letto: Stima (programma).xlsx (2 vani, 1 pertinenze)" in m["testo"] for m in messaggi), messaggi
