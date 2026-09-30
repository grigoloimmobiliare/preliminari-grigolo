"""Immagini da inserire nel Word: pagine del PDF BorsinoPro e carta intestata."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

ESTENSIONI_IMMAGINE = {".png", ".jpg", ".jpeg"}

# righe che il browser aggiunge stampando in PDF (data, titolo, indirizzo, "1/2")
_RIGA_BROWSER = re.compile(r"^\s*(\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}|https?://|\d+\s*/\s*\d+\s*$|"
                           r"BorsinoPro Piattaforma)", re.I)


def ritaglia_bianco(im: Image.Image, margine: int = 12) -> Image.Image:
    """Toglie il bianco attorno al contenuto."""
    rgb = im.convert("RGB")
    sfondo = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, sfondo).convert("L").point(lambda v: 255 if v > 12 else 0)
    box = diff.getbbox()
    if not box:
        return im
    l, t, r, b = box
    return im.crop((max(l - margine, 0), max(t - margine, 0), min(r + margine, im.width), min(b + margine, im.height)))


def pagine_pdf(pdf: Path, cartella_uscita: Path, dpi: int = 170) -> list[Path]:
    """Ogni pagina del PDF diventa un'immagine, senza intestazione e piè di pagina del browser."""
    cartella_uscita.mkdir(parents=True, exist_ok=True)
    out = []
    with pymupdf.open(pdf) as doc:
        for n, pagina in enumerate(doc):
            r = pagina.rect
            alto, basso = r.y0, r.y1
            fascia = min(40, r.height * 0.05)
            for x0, y0, x1, y1, testo, *_ in pagina.get_text("blocks"):
                riga = testo.strip()
                if not _RIGA_BROWSER.search(riga):
                    continue
                if y1 <= r.y0 + fascia:
                    alto = max(alto, y1 + 2)
                elif y0 >= r.y1 - fascia:
                    basso = min(basso, y0 - 2)
            clip = pymupdf.Rect(r.x0, alto, r.x1, basso)
            pix = pagina.get_pixmap(dpi=dpi, clip=clip)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            im = ritaglia_bianco(im)
            dest = cartella_uscita / f"{pdf.stem} - pagina {n + 1}.png"
            im.save(dest, optimize=True)
            out.append(dest)
    return out


def immagini_da_file(files: list[Path], cartella_lavoro: Path) -> list[Path]:
    """PDF -> immagini delle pagine; le immagini vengono usate così come sono."""
    out = []
    for f in files:
        if f.suffix.lower() == ".pdf":
            out.extend(pagine_pdf(f, cartella_lavoro))
        elif f.suffix.lower() in ESTENSIONI_IMMAGINE:
            out.append(f)
    return out


def carta_intestata_png(pdf: Path, dest: Path, dpi: int = 200) -> Path:
    """Prima pagina del PDF della carta intestata -> PNG con sfondo trasparente.

    Rigenerata solo se il PDF è più recente dell'immagine.
    """
    if dest.exists() and dest.stat().st_mtime >= pdf.stat().st_mtime:
        return dest
    with pymupdf.open(pdf) as doc:
        pix = doc[0].get_pixmap(dpi=dpi, alpha=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name("~" + dest.name)
        pix.save(tmp)
    tmp.replace(dest)
    return dest
