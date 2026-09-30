import pymupdf
from PIL import Image

from app import immagini


def test_pdf_browser_senza_intestazione(tmp_path):
    d = pymupdf.open()
    pg = d.new_page(width=842, height=1191)
    pg.insert_text((20, 20), "30/09/26, 15:58", fontsize=8)
    pg.insert_text((1191 / 2, 20), "BorsinoPro Piattaforma Valutazione Immobili", fontsize=8)
    pg.draw_rect(pymupdf.Rect(60, 60, 780, 400), color=None, fill=(0, 0, 0.3))
    pg.insert_text((20, 1180), "https://borsinopro.it/comparabili", fontsize=8)
    pg.insert_text((800, 1180), "1/2", fontsize=8)
    pdf = tmp_path / "b.pdf"
    d.save(pdf)
    [png] = immagini.pagine_pdf(pdf, tmp_path / "out", dpi=72)
    w, h = Image.open(png).size
    # restano solo il riquadro (720x340) e un piccolo margine
    assert 720 <= w <= 760 and 340 <= h <= 380


def test_carta_intestata_trasparente(tmp_path, carta_pdf):
    png = immagini.carta_intestata_png(carta_pdf, tmp_path / "c.png", dpi=50)
    im = Image.open(png)
    assert im.mode == "RGBA"
    assert im.getpixel((im.width // 2, im.height // 2))[3] == 0      # centro trasparente
    assert im.getpixel((5, 5))[3] == 255                               # fascia colorata piena
