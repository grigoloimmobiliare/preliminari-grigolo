"""Caricamento di PDF/immagini e OCR locale con Tesseract."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytesseract

log = logging.getLogger(__name__)

ESTENSIONI_IMMAGINE = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
ESTENSIONI_AMMESSE = ESTENSIONI_IMMAGINE | {".pdf"}


def testo_pdf(percorso: Path) -> list[str]:
    """Testo digitale di ogni pagina di un PDF (stringa vuota se la pagina e' una scansione)."""
    if percorso.suffix.lower() != ".pdf":
        return []
    with pymupdf.open(percorso) as doc:
        return [p.get_text() for p in doc]


def numero_pagine(percorso: Path) -> int:
    if percorso.suffix.lower() == ".pdf":
        with pymupdf.open(percorso) as doc:
            return len(doc)
    return 1


def immagine_pagina(percorso: Path, pagina: int = 0, dpi: int = 300) -> np.ndarray:
    """Restituisce la pagina come array RGB."""
    if percorso.suffix.lower() == ".pdf":
        with pymupdf.open(percorso) as doc:
            pix = doc[pagina].get_pixmap(dpi=dpi)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
            return np.ascontiguousarray(img[:, :, :3])
    dati = np.fromfile(str(percorso), dtype=np.uint8)
    img = cv2.imdecode(dati, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Immagine non leggibile: {percorso.name}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    # foto piccole: ingrandisci per avvicinarsi a ~300 dpi
    lato = max(img.shape[:2])
    if lato < 2500 and dpi > 300:
        f = min(3.0, 3300 / lato)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    return img


def pagine_affiancate(percorso: Path) -> list[bool]:
    """Per ogni pagina indica se e' un foglio orizzontale con due pagine affiancate (es. A3)."""
    if percorso.suffix.lower() != ".pdf":
        return [False]
    with pymupdf.open(percorso) as doc:
        return [p.rect.width > p.rect.height * 1.2 for p in doc]


def anteprima_png(percorso: Path, pagina: int = 0, larghezza: int = 1100, parte: int = 0) -> bytes:
    """PNG di anteprima di una pagina, per la visualizzazione nel browser.
    parte: 0 = pagina intera, 1 = meta' sinistra, 2 = meta' destra."""
    if percorso.suffix.lower() == ".pdf":
        with pymupdf.open(percorso) as doc:
            p = doc[pagina]
            r = p.rect
            if parte in (1, 2):
                meta = r.width / 2
                r = pymupdf.Rect(r.x0 + meta * (parte - 1), r.y0, r.x0 + meta * parte, r.y1)
            zoom = larghezza / r.width
            return p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=r).tobytes("png")
    img = immagine_pagina(percorso)
    if img.shape[1] > larghezza:
        f = larghezza / img.shape[1]
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return buf.tobytes()


def ocr(img: np.ndarray, psm: int = 3, lingua: str = "ita", extra: str = "") -> str:
    try:
        return pytesseract.image_to_string(img, lang=lingua, config=f"--psm {psm} {extra}".strip())
    except pytesseract.TesseractError as e:  # pragma: no cover - dipende dall'installazione
        log.warning("Errore Tesseract: %s", e)
        return ""


# ------------------------------------------------------------- tessere

def trova_tessere(img: np.ndarray) -> list[np.ndarray]:
    """Individua le tessere (carta d'identità, tessera sanitaria...) scansionate su un foglio A4.
    Se la pagina e' gia' una foto ravvicinata della tessera restituisce l'immagine intera."""
    grigio = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    maschera = ((grigio < 200) | (hsv[:, :, 1] > 40)).astype(np.uint8) * 255
    k = max(15, img.shape[1] // 110)
    maschera = cv2.morphologyEx(maschera, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    maschera = cv2.morphologyEx(maschera, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k // 2, k // 2)))
    n, _, stat, _ = cv2.connectedComponentsWithStats(maschera)
    alt, larg = grigio.shape
    riquadri = [list(stat[i][:4]) for i in range(1, n) if stat[i][2] > larg * 0.08 and stat[i][3] > alt * 0.01]
    # unisci le parti della stessa tessera separate da fasce chiare (es. la banda MRZ)
    unito = True
    while unito:
        unito = False
        for i in range(len(riquadri)):
            for j in range(i + 1, len(riquadri)):
                a, b = riquadri[i], riquadri[j]
                sovrap_x = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
                distanza_y = max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3])
                if sovrap_x > 0.5 * min(a[2], b[2]) and distanza_y < 3 * k:
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
                    riquadri[i] = [x0, y0, x1 - x0, y1 - y0]
                    del riquadri[j]
                    unito = True
                    break
            if unito:
                break
    tessere = []
    for x, y, w, h in riquadri:
        if w > larg * 0.2 and h > alt * 0.08 and 1.2 < w / h < 2.1:
            tessere.append((y, x, img[y:y + h, x:x + w]))
    tessere.sort(key=lambda t: (t[0], t[1]))
    if not tessere:
        return [img]
    return [t[2] for t in tessere]


def varianti_binarizzate(tessera: np.ndarray) -> list[np.ndarray]:
    """Diverse versioni della tessera: il testo stampato e' scuro su tutti i canali,
    mentre gli sfondi di sicurezza sono colorati; si tengono solo i pixel scuri."""
    massimo = np.max(tessera, axis=2)
    varianti = []
    for soglia in (90, 120, 150):
        b = np.where(massimo < soglia, 0, 255).astype(np.uint8)
        varianti.append(cv2.resize(b, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_NEAREST))
    grigio = cv2.cvtColor(tessera, cv2.COLOR_RGB2GRAY)
    varianti.append(cv2.resize(grigio, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    return varianti


MRZ_WHITELIST = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"


def ocr_tessera(tessera: np.ndarray) -> list[str]:
    """Esegue piu' letture OCR della stessa tessera; il confronto tra le letture
    (e le cifre di controllo) permette di scegliere i valori corretti."""
    testi = []
    for v in varianti_binarizzate(tessera):
        testi.append(ocr(v, psm=11))
        # zona MRZ: terzo inferiore, caratteri limitati
        h = v.shape[0]
        testi.append(ocr(v[int(h * 0.6):, :], psm=6, lingua="eng", extra=MRZ_WHITELIST))
    return testi
