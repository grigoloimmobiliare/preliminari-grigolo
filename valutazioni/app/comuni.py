"""Comuni italiani e loro provincia (elenco ISTAT), per la ricerca OMI fuori Treviso.

- `provincia(comune)`: sigla della provincia ("Jesolo" -> "VE"), senza badare a maiuscole,
  accenti e apostrofi ("San Dona di Piave", "SAN DONÀ DI PIAVE").
- `dall_indirizzo(testo)`: il comune scritto nell'indirizzo ("Via Roma 10, Jesolo (VE)",
  "Piazza Milano 3 - 30016 Jesolo"). Il nome della via non conta: "Via Roma 10" non è Roma.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).parent / "risorse" / "comuni.json"


def chiave(nome: str) -> str:
    """Forma confrontabile: minuscole, senza accenti, apostrofi e trattini come spazi."""
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[`'’\-/.]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _dati() -> tuple[dict[str, tuple[str, list[str]]], dict[str, list[str]]]:
    d = json.loads(FILE.read_text(encoding="utf-8"))
    comuni = {chiave(nome): (nome, sigle) for nome, sigle in d["comuni"].items()}
    return comuni, d["cap"]


def trova(nome: str) -> tuple[str, list[str]] | None:
    """(nome ufficiale, sigle delle province) del comune, o None."""
    return _dati()[0].get(chiave(nome))


def provincia(nome: str) -> str | None:
    """Sigla della provincia; None se il comune non c'è o il nome è ambiguo (es. Castro, BG e LE)."""
    t = trova(nome)
    return t[1][0] if t and len(t[1]) == 1 else None


def dall_indirizzo(testo: str) -> tuple[str, str | None] | None:
    """(comune, sigla provincia se scritta o deducibile) dall'indirizzo, o None."""
    if not testo:
        return None
    comuni, cap = _dati()
    sigla_scritta = None
    m = re.search(r"\(\s*([A-Za-z]{2})\s*\)", testo)
    if m:
        sigla_scritta = m.group(1).upper()
        testo = testo[:m.start()]
    # pezzi separati da virgole o trattini: il primo è la via, il comune è in uno dei successivi
    pezzi = [p.strip() for p in re.split(r",|\s[-–]\s", testo) if p.strip()]
    candidati = pezzi[1:]
    # tutto in un pezzo ("Via Roma 10 Jesolo"): il comune è dopo il numero civico
    m = re.search(r"\d+\s*[a-zA-Z]?(?:/\d+)?\s+(?:\d{5}\s+)?([^\d]+)$", pezzi[0]) if pezzi else None
    if m:
        candidati.append(m.group(1))
    for pezzo in reversed(candidati):
        cap_scritto = re.search(r"\b(\d{5})\b", pezzo)
        nome = re.sub(r"\b\d{5}\b", " ", pezzo)
        nome = re.sub(r"\b(?:prov(?:incia)?\.?\s+di\s+\w+|località|loc\.|fraz(?:ione)?\.?)\b.*$", "", nome,
                      flags=re.I).strip()
        parole = nome.split()
        if len(parole) > 1 and re.fullmatch(r"[A-Z]{2}", parole[-1]):      # "Treviso TV"
            sigla_scritta = sigla_scritta or parole.pop()
        # il nome più lungo che chiude il pezzo ("Ponte di Piave", "San Donà di Piave")
        for k in range(min(len(parole), 6), 0, -1):
            t = comuni.get(chiave(" ".join(parole[-k:])))
            if t:
                ufficiale, sigle = t
                sigla = sigla_scritta if sigla_scritta in sigle else (sigle[0] if len(sigle) == 1 else None)
                return ufficiale, sigla
        if cap_scritto and len(cap.get(cap_scritto.group(1), [])) == 1:
            ufficiale = cap[cap_scritto.group(1)][0]
            return ufficiale, comuni[chiave(ufficiale)][1][0]
    return None
