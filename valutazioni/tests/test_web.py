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
