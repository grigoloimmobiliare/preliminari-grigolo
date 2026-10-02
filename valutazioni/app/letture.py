"""Superfici già scritte sulla planimetria (es. "CAMERA 18,87 m²" nelle planimetrie di progetto).

Si legge il testo della pagina con Tesseract, a due ingrandimenti (alcune scritte si leggono
solo in uno dei due), e si cercano i numeri con la virgola seguiti da m², mq, m2 oppure scritti
sotto il nome di una stanza; il nome è la parola scritta subito sopra il numero. Le quote dei
muri (numeri interi in centimetri) non hanno la virgola e vengono ignorate.

I valori letti vanno sempre controllati: nella pagina si possono correggere nomi e mq.
"""

from __future__ import annotations

import logging
import re
import shutil

import cv2
import numpy as np

log = logging.getLogger("valutazioni")

NUMERO = re.compile(r"^(\d{1,3})[,.](\d{1,2})(m.*)?$", re.I)
UNITA = re.compile(r"^(m|mq|m2|m²|m\?|m°|mi|me)\W*$", re.I)
NOME = re.compile(r"^[A-Za-zÀ-ÿ]{3,}\.?$")
INGRANDIMENTI = (1.0, 2.0)


def disponibile() -> bool:
    try:
        import pytesseract
        return bool(shutil.which(pytesseract.pytesseract.tesseract_cmd) or shutil.which("tesseract"))
    except ImportError:
        return False


def _parole(img: np.ndarray, f: float) -> list[dict]:
    import pytesseract
    im = img if f == 1 else cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    d = pytesseract.image_to_data(im, lang="ita", config="--psm 11", output_type=pytesseract.Output.DICT)
    parole = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if t:
            parole.append({"t": t, "x": d["left"][i] / f, "y": d["top"][i] / f, "w": d["width"][i] / f,
                           "h": d["height"][i] / f, "c": float(d["conf"][i])})
    return parole


def _sopra(num: dict, nomi: list[dict], hmed: float) -> dict | None:
    """Nome scritto subito sopra il numero (centrato più o meno sulla stessa verticale)."""
    cx = num["x"] + num["w"] / 2
    migliore = None
    for p in nomi:
        pcx = p["x"] + p["w"] / 2
        distanza = num["y"] - (p["y"] + min(p["h"], 1.3 * hmed))      # spazio tra nome e numero
        if not -0.5 * hmed <= distanza <= 1.6 * hmed:
            continue
        if abs(pcx - cx) > max(p["w"], num["w"]) * 0.8 + hmed:
            continue
        if migliore is None or distanza < migliore[0]:
            migliore = (distanza, p)
    return migliore[1] if migliore else None


def leggi(img: np.ndarray) -> list[dict]:
    """[{nome, mq, x, y, w, h}] in pixel dell'immagine, in ordine di lettura."""
    if not disponibile():
        log.info("Tesseract non disponibile: superfici scritte non lette")
        return []
    try:
        passate = [_parole(img, f) for f in INGRANDIMENTI]
    except Exception:  # noqa: BLE001 - la lettura è un aiuto, non deve bloccare il calcolo
        log.exception("Lettura delle superfici scritte")
        return []
    trovati: list[dict] = []
    for parole in passate:
        nomi = [p for p in parole if NOME.match(p["t"]) and p["c"] > 40]
        hmed = float(np.median([p["h"] for p in nomi])) if nomi else 20.0
        nomi = [p for p in nomi if p["h"] < 4 * hmed]
        for i, p in enumerate(parole):
            m = NUMERO.match(p["t"].replace(" ", ""))
            if not m:
                continue
            mq = float(f"{m.group(1)}.{m.group(2)}")
            # unità di misura attaccata o subito a destra, oppure il nome della stanza sopra
            dopo = [q for q in parole if 0 <= q["x"] - (p["x"] + p["w"]) < 1.5 * p["h"]
                    and abs(q["y"] - p["y"]) < 0.6 * p["h"]]
            prima = [q for q in parole if 0 <= p["x"] - (q["x"] + q["w"]) < 1.5 * p["h"]
                     and abs(q["y"] - p["y"]) < 0.6 * p["h"]]
            if any(re.match(r"^h\W*$", q["t"], re.I) for q in prima):      # altezza dei locali (H. 2,80 m)
                continue
            unita = bool(m.group(3)) or any(UNITA.match(q["t"]) for q in dopo)
            nome = _sopra(p, nomi, hmed)
            if not (unita or nome) or mq <= 0:
                continue
            doppione = next((t for t in trovati if abs(t["x"] - p["x"]) < 2 * p["h"] and abs(t["y"] - p["y"]) < p["h"]), None)
            if doppione:
                if not doppione["nome"] and nome:
                    doppione["nome"] = nome["t"]
                continue
            trovati.append({"nome": nome["t"] if nome else "", "mq": mq,
                            "x": int(p["x"]), "y": int(p["y"]), "w": int(p["w"]), "h": int(p["h"])})
    for t in trovati:
        t["nome"] = t["nome"].rstrip(".").capitalize() if t["nome"] else "Vano"
    trovati.sort(key=lambda t: (round(t["y"] / 200), t["x"]))
    return trovati
