import math

import cv2
import numpy as np
import pytest

from app import planimetria as pl


def disegna(tmp_path, ridotta: bool, scala: float | None = None, scritte_grandi: bool = False):
    """Due stanze (4 x 3 m e 3 x 3 m), muri a doppia linea, porta da 0,9 m, scritte, una finestra."""
    scala = scala or (pl.SCALE["1:200 ridotta (A3 su A4)"] if ridotta else pl.SCALE["1:200"])
    m = pl.px_per_metro(300, scala)
    img = np.full((3508, 2480), 255, np.uint8)
    ox, oy = 600, 900
    P = lambda x, y: (int(ox + x * m), int(oy + y * m))       # noqa: E731

    def muro(x0, y0, x1, y1):           # rettangolo pieno di muro disegnato a contorno
        cv2.rectangle(img, P(x0, y0), P(x1, y1), 0, 2)

    e = 0.30                             # muri esterni
    muro(-e, -e, 7.12 + e, 0)            # sopra
    muro(-e, 3, 7.12 + e, 3 + e)         # sotto
    muro(-e, 0, 0, 3)                    # sinistra
    muro(7.12, 0, 7.12 + e, 3)           # destra
    # divisorio a x=4..4,12 con porta da 0,9 m tra y=1 e y=1,9
    muro(4, 0, 4.12, 1)
    muro(4, 1.9, 4.12, 3)
    # finestra nel muro esterno (simbolo dentro lo spessore)
    cv2.line(img, P(1.5, -e / 2), P(2.5, -e / 2), 0, 1)
    if scritte_grandi:              # scritte a mano grandi e spesse, come nelle planimetrie vecchie
        cv2.putText(img, "soggiorno", P(0.2, 1.8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 4)
        cv2.putText(img, "camera", P(4.4, 1.8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 4)
    else:
        cv2.putText(img, "soggiorno", P(1.2, 1.5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)
        cv2.putText(img, "camera", P(5.0, 1.5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)
    f = tmp_path / ("ridotta.png" if ridotta else "piena.png")
    cv2.imwrite(str(f), img)
    return f, scala


@pytest.mark.parametrize("ridotta", [False, True])
def test_due_stanze(tmp_path, ridotta):
    f, scala = disegna(tmp_path, ridotta)
    r = pl.analizza(f)
    px_m = pl.px_per_metro(r["dpi"], scala)
    aree = sorted(v.mq(px_m) for v in r["vani"] if 2 < v.mq(px_m) < 40)
    assert len(aree) == 2, aree
    assert aree[0] == pytest.approx(3.0 * 3.0, rel=0.05)
    assert aree[1] == pytest.approx(4.0 * 3.0, rel=0.05)


def test_pdf_con_barra_di_scala(tmp_path):
    """Visura del catasto: scansione a tutta pagina, griglia blu disegnata sopra e barra "10 metri"."""
    import pymupdf
    f, _ = disegna(tmp_path, False, scala=300, scritte_grandi=True)
    doc = pymupdf.open()
    pag = doc.new_page(width=595.28, height=841.89)
    pag.insert_image(pag.rect, filename=str(f))
    passo = 10 * 1000 / 300 / 25.4 * 72                  # 10 m a 1:300, in punti
    for k in range(1, 9):
        pag.draw_line((k * passo, 0), (k * passo, pag.rect.height), color=(0, 0, 1), width=0.3)
        pag.draw_line((0, k * passo), (pag.rect.width, k * passo), color=(0, 0, 1), width=0.3)
    pag.draw_line((570, 300), (570, 300 + passo), color=(0, 0, 1), width=0.9)
    pag.insert_text((576, 320), "10 metri", fontsize=8, rotate=270)
    pdf = tmp_path / "visura.pdf"
    doc.save(pdf)
    r = pl.analizza(pdf)
    assert r["scala_barra"] == pytest.approx(300, rel=0.01)
    px_m = pl.px_per_metro(r["dpi"], r["scala_barra"])
    aree = sorted(v.mq(px_m) for v in r["vani"] if 2 < v.mq(px_m) < 40)
    assert len(aree) == 2, aree
    assert aree[0] == pytest.approx(3.0 * 3.0, rel=0.06)
    assert aree[1] == pytest.approx(4.0 * 3.0, rel=0.06)


def test_scala_proposta(tmp_path):
    f, _ = disegna(tmp_path, ridotta=True)
    r = pl.analizza(f)
    stanze = [v for v in r["vani"] if v.mq(pl.px_per_metro(300, 200)) > 2]
    assert pl.scala_proposta(stanze, r["dpi"]) == "1:200 ridotta (A3 su A4)"
    f, _ = disegna(tmp_path, ridotta=False)
    r = pl.analizza(f)
    stanze = [v for v in r["vani"] if v.mq(pl.px_per_metro(300, 200)) > 2]
    assert pl.scala_proposta(stanze, r["dpi"]) == "1:200"


def test_superfici_commerciali(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUTAZIONI_DATI", str(tmp_path / "dati"))
    import importlib

    from app import archivio, superfici
    importlib.reload(archivio)
    importlib.reload(superfici)
    v = archivio.crea("Prova")
    f, _ = disegna(tmp_path, ridotta=True)
    dest = v.cartella_categoria("planimetria") / "plan.png"
    dest.write_bytes(f.read_bytes())
    p = superfici.calcola(v, dest)
    grandi = [z["n"] for z in p["zone"] if z["mq"] > 2]
    p = superfici.aggiorna(v, grandi, {str(grandi[0]): "Soggiorno"}, "automatica")
    assert p["scala_usata"] == "1:200 ridotta (A3 su A4)"
    assert p["tot_commerciale"] == pytest.approx(p["tot_calpestabile"] * 1.15, rel=0.001)
    assert p["tot_calpestabile"] == pytest.approx(21, rel=0.05)
    assert (v.cartella / "Superfici - planimetria.txt").exists()
    assert "Soggiorno" in (v.cartella / "Superfici - planimetria.txt").read_text(encoding="utf-8")
    # una zona chiamata "Balcone" è una pertinenza: a parte e senza maggiorazione
    p = superfici.aggiorna(v, grandi, {str(grandi[0]): "Soggiorno", str(grandi[1]): "Balcone"}, "automatica")
    assert [r["nome"] for r in p["pertinenze"]] == ["Balcone"]
    assert [r["nome"] for r in p["righe"]] == ["Soggiorno"]
    assert p["tot_commerciale"] == pytest.approx(p["righe"][0]["calpestabile"] * 1.15, rel=0.001)
    assert "Balcone" in (v.cartella / "Superfici - planimetria.txt").read_text(encoding="utf-8")


def _con_superfici_scritte(tmp_path):
    """Planimetria di progetto: sotto il nome di ogni stanza è scritta la superficie."""
    f, scala = disegna(tmp_path, False)
    img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
    img[:] = 255
    m = pl.px_per_metro(300, scala)
    ox, oy = 600, 900
    cv2.rectangle(img, (ox, oy), (int(ox + 7 * m), int(oy + 3 * m)), 0, 3)
    for nome, mq, x in (("CAMERA", "18,87 m2", 0.6), ("CUCINA", "11,86 m2", 4.2)):
        cv2.putText(img, nome, (int(ox + x * m), int(oy + 1.2 * m)), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 3)
        cv2.putText(img, mq, (int(ox + x * m), int(oy + 1.2 * m) + 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 3)
    # quote dei muri (senza virgola) e altezza dei locali: da non leggere come superfici
    cv2.putText(img, "451", (ox + 40, oy - 40), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 3)
    cv2.putText(img, "H. 2,80 m", (ox, int(oy + 3 * m) + 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 3)
    dest = tmp_path / "progetto.png"
    cv2.imwrite(str(dest), img)
    return dest


def test_superfici_scritte(tmp_path):
    from app import letture
    if not letture.disponibile():
        pytest.skip("Tesseract non installato")
    img, _, _ = pl.carica(_con_superfici_scritte(tmp_path))
    lette = [(t["nome"], t["mq"]) for t in letture.leggi(img)]
    assert lette == [("Camera", 18.87), ("Cucina", 11.86)]


def test_superfici_scritte_nella_valutazione(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUTAZIONI_DATI", str(tmp_path / "dati"))
    import importlib

    from app import archivio, letture, superfici
    if not letture.disponibile():
        pytest.skip("Tesseract non installato")
    importlib.reload(archivio)
    importlib.reload(superfici)
    v = archivio.crea("Progetto")
    dest = v.cartella_categoria("planimetria") / "plan.png"
    dest.write_bytes(_con_superfici_scritte(tmp_path).read_bytes())
    p = superfici.calcola(v, dest)
    assert [t["sigla"] for t in p["letture"]] == ["L1", "L2"]
    # proposte già spuntate; i valori si possono correggere e togliere
    assert p["tot_calpestabile"] == pytest.approx(18.87 + 11.86)
    p = superfici.aggiorna(v, [], {}, "automatica",
                           {"L1": {"scelta": True, "nome": "Camera matrimoniale", "mq": 18.9},
                            "L2": {"scelta": False, "nome": "Cucina", "mq": 11.86}})
    assert [(r["nome"], r["calpestabile"], r["commerciale"]) for r in p["righe"]] == \
        [("Camera matrimoniale", 18.9, round(18.9 * 1.15, 2))]
