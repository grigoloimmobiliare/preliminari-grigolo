"""Cartelle sul NAS.

    <DATI>/modello/valutazione_modello.docx   modello Word (sostituibile dalla pagina Impostazioni)
    <DATI>/modello/carta_intestata.pdf        carta intestata, messa dietro a ogni pagina
    <DATI>/modello/stima_modello.xlsx         Excel vuoto da cui partire
    <DATI>/modello/impostazioni.json          provincia e comune predefiniti per la ricerca OMI
    <DATI>/valutazioni/<AAAA-MM-GG Nome>/
        01_Excel/  02_Comparabili/  03_OMI/
        valutazione.json
        Valutazione - <Nome>.docx
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATI = Path(os.environ.get("VALUTAZIONI_DATI", BASE / "dati"))
CARTELLA_VALUTAZIONI = DATI / "valutazioni"
CARTELLA_MODELLO = DATI / "modello"

PREDEFINITI = {
    "valutazione_modello.docx": BASE / "modelli" / "valutazione_modello.docx",
    "stima_modello.xlsx": BASE / "modelli" / "stima_modello.xlsx",
    "carta_intestata.pdf": BASE / "modelli" / "carta_intestata.pdf",
}
IMPOSTAZIONI_PREDEFINITE = {"provincia": "TV", "comune": "TREVISO", "destinazioni": ""}

CATEGORIE = {
    "excel": ("01_Excel", "Excel della stima", {".xlsx", ".xlsm"}),
    "comparabili": ("02_Comparabili", "Comparabili BorsinoPro (PDF)", {".pdf", ".png", ".jpg", ".jpeg"}),
    "omi": ("03_OMI", "Valori OMI", {".png", ".jpg", ".jpeg", ".pdf"}),
}
PREFISSO_AUTO = ("auto_", "errore_")

_lock = threading.Lock()


def file_modello(nome: str) -> Path:
    CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)
    p = CARTELLA_MODELLO / nome
    if not p.exists() and nome in PREDEFINITI:
        shutil.copy(PREDEFINITI[nome], p)
    return p


def carta_intestata() -> Path | None:
    """Quella caricata dalla pagina Impostazioni; al primo avvio, quella fornita col programma."""
    p = file_modello("carta_intestata.pdf")
    return p if p.exists() else None


def impostazioni() -> dict:
    p = CARTELLA_MODELLO / "impostazioni.json"
    dati = dict(IMPOSTAZIONI_PREDEFINITE)
    if p.exists():
        dati.update(json.loads(p.read_text(encoding="utf-8")))
    return dati


def salva_impostazioni(dati: dict) -> None:
    CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)
    (CARTELLA_MODELLO / "impostazioni.json").write_text(json.dumps(dati, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")


def nome_sicuro(s: str) -> str:
    s = re.sub(r"[^\w\s\-.'àèéìòùÀÈÉÌÒÙ]", "", s, flags=re.U).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:80].strip(". ") or "valutazione"


def nome_file_sicuro(nome: str) -> str:
    base = Path(nome).name
    ext = re.sub(r"[^A-Za-z0-9.]", "", Path(base).suffix.lower())[:6]
    return (nome_sicuro(Path(base).stem) or "file") + ext


class Valutazione:
    def __init__(self, cartella: Path):
        self.cartella = cartella

    @property
    def id(self) -> str:
        return self.cartella.name

    @property
    def lavoro(self) -> Path:
        """Immagini intermedie (pagine dei PDF): cartella nascosta, rigenerata ogni volta."""
        return self.cartella / ".lavoro"

    def carica(self) -> dict:
        f = self.cartella / "valutazione.json"
        stato = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        stato.setdefault("nome", self.id)
        stato.setdefault("creata", datetime.fromtimestamp(self.cartella.stat().st_mtime).isoformat(timespec="seconds"))
        stato.setdefault("provincia", "")
        stato.setdefault("comune", "")
        stato.setdefault("generazione", {"stato": "mai eseguita"})
        return stato

    def salva(self, stato: dict) -> None:
        with _lock:
            f = self.cartella / "valutazione.json"
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(stato, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            tmp.replace(f)

    def cartella_categoria(self, cat: str) -> Path:
        c = self.cartella / CATEGORIE[cat][0]
        c.mkdir(parents=True, exist_ok=True)
        return c

    def file_categoria(self, cat: str, anche_automatici: bool = True) -> list[Path]:
        est = CATEGORIE[cat][2]
        return sorted(p for p in self.cartella_categoria(cat).iterdir()
                      if p.is_file() and p.suffix.lower() in est and not p.name.startswith((".", "~"))
                      and (anche_automatici or not p.name.startswith(PREFISSO_AUTO)))

    def aggiungi_file(self, cat: str, nome: str, contenuto: bytes) -> Path:
        pulito = nome_file_sicuro(nome)
        if cat == "omi" and pulito.startswith(PREFISSO_AUTO):
            pulito = "manuale_" + pulito
        dest = self.cartella_categoria(cat) / pulito
        i = 1
        while dest.exists():
            dest = dest.with_name(f"{Path(pulito).stem}_{i}{Path(pulito).suffix}")
            i += 1
        dest.write_bytes(contenuto)
        return dest

    def file(self, cat: str, nome: str) -> Path:
        base = self.cartella_categoria(cat).resolve()
        p = (base / nome).resolve()
        if p.parent != base or not p.is_file():
            raise FileNotFoundError(nome)
        return p

    def documenti(self) -> list[Path]:
        return sorted(self.cartella.glob("Valutazione*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)

    def documento(self, nome: str) -> Path:
        p = (self.cartella / nome).resolve()
        if p.parent != self.cartella.resolve() or not p.is_file() or p.suffix.lower() not in (".docx", ".txt"):
            raise FileNotFoundError(nome)
        return p


def elenco() -> list[dict]:
    CARTELLA_VALUTAZIONI.mkdir(parents=True, exist_ok=True)
    out = []
    for c in sorted(CARTELLA_VALUTAZIONI.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if c.is_dir() and not c.name.startswith("."):
            v = Valutazione(c)
            stato = v.carica()
            out.append({"id": v.id, "nome": stato["nome"], "creata": stato["creata"],
                        "stato": stato["generazione"].get("stato", ""), "generato": bool(v.documenti())})
    return out


def crea(nome: str) -> Valutazione:
    CARTELLA_VALUTAZIONI.mkdir(parents=True, exist_ok=True)
    base = f"{date.today().isoformat()} {nome_sicuro(nome)}"
    cartella = CARTELLA_VALUTAZIONI / base
    i = 2
    while cartella.exists():
        cartella = CARTELLA_VALUTAZIONI / f"{base} ({i})"
        i += 1
    cartella.mkdir(parents=True)
    v = Valutazione(cartella)
    for cat in CATEGORIE:
        v.cartella_categoria(cat)
    stato = v.carica()
    stato["nome"] = nome.strip() or cartella.name
    v.salva(stato)
    return v


def apri(vid: str) -> Valutazione:
    base = CARTELLA_VALUTAZIONI.resolve()
    c = (base / vid).resolve()
    if c.parent != base or not c.is_dir():
        raise FileNotFoundError(vid)
    return Valutazione(c)
