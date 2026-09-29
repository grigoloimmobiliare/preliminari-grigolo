"""Lettura delle planimetrie catastali: si legge la dicitura a margine
'Catasto dei Fabbricati - Situazione al ... - Comune di X(L407) - < Sez. urbana D - Foglio 1 - Particella 134 - Subalterno 67 >'."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import cv2

from . import ocr


def _cerca(testo: str) -> dict:
    t = testo.replace("\n", " ")
    ris = {}
    m = re.search(r"Comune\s*\w{0,3}\s*([A-Z][A-Z' ]{2,30}?)\s*[\[(]\s*([A-Z][0-9O]{3})", t)
    if m:
        ris["comune"] = m[1].strip().title()
        ris["codice_comune"] = m[2].replace("O", "0")
    m = re.search(r"Sez\w*\s*\.?\s*urb\w*\s*\.?\s*([A-Z0-9])\b", t, re.I)
    if m:
        ris["sezione"] = m[1].upper()
    m = re.search(r"Fogl\w*\s*[:.]?\s*([0-9|Il]{1,4})(?=\W|$)", t, re.I)
    if m:
        ris["foglio"] = m[1].replace("|", "1").replace("I", "1").replace("l", "1")
    m = re.search(r"Pa\w{4,9}\s*[:.]?\s*([0-9]{1,5})\b", t)
    if m:
        ris["particella"] = m[1]
    m = re.search(r"Su\w{4,9}\s*[:.]?\s*([0-9TIOl]{1,4})\s*>?", t) or \
        re.search(r"\bS\w{5,9}\s*[:.]?\s*([0-9TIOl]{1,4})\s*>", t)
    if m:
        ris["sub"] = m[1].replace("T", "7").replace("I", "1").replace("l", "1").replace("O", "0")
    return ris


def estrai(percorso: Path) -> list[dict]:
    """Restituisce un elenco di planimetrie (una per pagina) con i riferimenti letti."""
    risultati = []
    testo_pdf = ocr.testo_pdf(percorso)
    for p in range(ocr.numero_pagine(percorso)):
        voti: dict[str, Counter] = {}
        testi = []
        if testo_pdf and len(testo_pdf[p].strip()) > 50:
            testi.append(testo_pdf[p])
        else:
            for dpi in (300, 400):
                img = ocr.immagine_pagina(percorso, p, dpi=dpi)
                grigio = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                h, w = grigio.shape
                fascia_dx = grigio[:, int(w * 0.92):]
                for rot in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
                    testi.append(ocr.ocr(cv2.rotate(fascia_dx, rot), psm=6))
                if dpi == 300:
                    testi.append(ocr.ocr(grigio[: int(h * 0.12), :], psm=6))
                    testi.append(ocr.ocr(grigio[int(h * 0.88):, :], psm=6))
        for t in testi:
            for k, v in _cerca(t).items():
                voti.setdefault(k, Counter())[v] += 1
        dati = {k: c.most_common(1)[0][0] for k, c in voti.items()}
        # tutte le letture: servono per il confronto con i dati dell'atto
        dati["_candidati"] = {k: list(c) for k, c in voti.items()}
        dati["file"] = percorso.name
        dati["pagina"] = p + 1
        risultati.append(dati)
    return risultati


def abbina(planimetrie: list[dict], unita: list[dict]) -> None:
    """Abbina ogni planimetria all'unita' catastale dell'atto compatibile con le letture OCR
    (le letture sono spesso imprecise: basta che una delle letture corrisponda)."""
    for pl in planimetrie:
        cand = pl.get("_candidati", {})
        migliore, punteggio = None, 0
        for i, u in enumerate(unita):
            p = 0
            if u.get("sub") and u["sub"] in cand.get("sub", []):
                p += 2
            if u.get("particella") and u["particella"] in cand.get("particella", []):
                p += 1
            if u.get("foglio") and u["foglio"] in cand.get("foglio", []):
                p += 1
            if p > punteggio:
                migliore, punteggio = i, p
        if migliore is not None and punteggio >= 2:
            u = unita[migliore]
            pl["unita"] = migliore
            for k in ("sezione", "foglio", "particella", "sub"):
                if u.get(k):
                    pl[k] = u[k]
