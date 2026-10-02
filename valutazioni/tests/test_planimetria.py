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
