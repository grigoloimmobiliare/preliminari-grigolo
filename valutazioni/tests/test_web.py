import importlib
import time
from urllib.parse import unquote


def test_percorso_completo(tmp_path, monkeypatch, excel_compilato, carta_pdf):
    monkeypatch.setenv("VALUTAZIONI_DATI", str(tmp_path / "dati"))
    from app import archivio, genera, main, omi
    importlib.reload(archivio)
    importlib.reload(genera)
    importlib.reload(main)
    import sito_omi_finto
    originale = omi.cerca
    monkeypatch.setattr(omi, "cerca", lambda *a, **k: originale(*a, configura=sito_omi_finto.configura, **k))
    from fastapi.testclient import TestClient
    c = TestClient(main.app)

    assert c.get("/").status_code == 200
    r = c.post("/valutazioni", data={"nome": "Rossi - Via Roma 10"}, follow_redirects=False)
    url = r.headers["location"]
    vid = unquote(url.rsplit("/", 1)[1])
    c.post(f"{url}/carica/excel", files={"files": ("stima.xlsx", excel_compilato.read_bytes())})
    c.post("/impostazioni/carta", files={"file": ("carta.pdf", carta_pdf.read_bytes())})
    pagina = c.get(url).text
    assert "stima.xlsx" in pagina and "B1" in pagina
    c.post(f"{url}/genera", data={"omi": "si"})
    for _ in range(120):
        if not genera.in_corso(archivio.apri(vid)):
            break
        time.sleep(1)
    stato = archivio.apri(vid).carica()["generazione"]
    assert stato["stato"] == "completata", stato
    doc = c.get(f"{url}/scarica/{stato['documento']}")
    assert doc.status_code == 200 and doc.content[:2] == b"PK"
    for p in ("/impostazioni", "/guida"):
        assert c.get(p).status_code == 200
    assert c.get("/valutazioni/../../etc").status_code == 404


def test_prima_valutazione_cartella_dati_vuota(tmp_path, monkeypatch, excel_compilato):
    """Cartella dei dati nuova (nessun modello o carta intestata caricati): la prima generazione
    deve salvare il logo dell'Agenzia nella cartella "modello", creandola."""
    monkeypatch.setenv("VALUTAZIONI_DATI", str(tmp_path / "dati nuova"))
    from app import archivio, genera, main, omi
    importlib.reload(archivio)
    importlib.reload(genera)
    importlib.reload(main)
    import sito_omi_finto
    originale = omi.cerca
    monkeypatch.setattr(omi, "cerca", lambda *a, **k: originale(*a, configura=sito_omi_finto.configura, **k))
    v = archivio.crea("Prima")
    (v.cartella_categoria("excel") / "stima.xlsx").write_bytes(excel_compilato.read_bytes())
    assert not archivio.CARTELLA_MODELLO.exists()
    messaggi = []
    genera.genera(v, messaggi)
    assert archivio.logo_agenzia() is not None, messaggi
    assert not [m for m in messaggi if m.get("tipo") == "errore"], messaggi


def test_ricerca_omi_dalla_pagina(tmp_path, monkeypatch, excel_compilato):
    """Zone del comune -> valori della zona scelta -> scelta di destinazioni e righe -> Word."""
    monkeypatch.setenv("VALUTAZIONI_DATI", str(tmp_path / "dati"))
    from app import archivio, genera, main, omi, ricerca_omi
    importlib.reload(archivio)
    importlib.reload(ricerca_omi)
    importlib.reload(genera)
    importlib.reload(main)
    import sito_omi_finto
    cerca, zone = omi.cerca, omi.zone_disponibili
    monkeypatch.setattr(omi, "cerca", lambda *a, **k: cerca(*a, **{**k, "configura": sito_omi_finto.configura}))
    monkeypatch.setattr(omi, "zone_disponibili",
                        lambda *a, **k: zone(*a, **{**k, "configura": sito_omi_finto.configura}))
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    v = archivio.crea("Ricerca OMI")
    (v.cartella_categoria("excel") / "stima.xlsx").write_bytes(excel_compilato.read_bytes())
    url = f"/valutazioni/{v.id}"

    def attendi():
        for _ in range(120):
            if not ricerca_omi.in_corso(v):
                return v.carica()["omi"]
            time.sleep(0.5)
        raise AssertionError("ricerca OMI non finita")

    c.post(f"{url}/parametri", data={"provincia": "", "comune": "", "zona": "", "azione": "zone"})
    s = attendi()
    assert not s["errore"], s
    assert any(z.startswith("C1/") for z in s["zone"])
    assert "C1/Semicentrale/SAN ZENO" in c.get(url).text          # menu delle zone nella pagina

    c.post(f"{url}/parametri", data={"provincia": "", "comune": "", "zona": "C1", "azione": "valori"})
    s = attendi()
    assert not s["errore"], s
    dati = ricerca_omi.valori(v)
    assert [t["destinazione"] for t in dati["tabelle"]] == ["Residenziale", "Commerciale"]
    pagina = c.get(url).text
    assert "Ville e Villini" in pagina and "Salva la scelta" in pagina

    # solo Residenziale, senza la riga dei box
    res = dati["tabelle"][0]
    righe = {r["celle"][0]: r["r"] for r in ricerca_omi.righe_dati(res)}
    form = {"dest_0": "on"} | {f"riga_0_{r}": "on" for t, r in righe.items() if t != "Box"}
    c.post(f"{url}/omi/scelta", data=form)
    word = ricerca_omi.per_il_word(ricerca_omi.valori(v))
    assert [t["destinazione"] for t in word["tabelle"]] == ["Residenziale"]
    testi = [x["t"] for x in word["tabelle"][0]["celle"]]
    assert "Box" not in testi and "Ville e Villini" in testi and "Abitazioni civili" in testi

    messaggi = []
    doc = genera.genera(v, messaggi)
    assert any("scelti nella pagina" in m["testo"] for m in messaggi), messaggi
    from docx import Document
    testo = "\n".join(cell.text for t in Document(doc).tables for row in t.rows for cell in row.cells)
    assert "Ville e Villini" in testo and "Box" not in testo and "Negozi" not in testo
