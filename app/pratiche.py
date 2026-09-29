"""Archivio delle pratiche su disco (cartella condivisa sul NAS).

Struttura:
    <DATI>/modello/preliminare_modello.docx
    <DATI>/pratiche/<AAAA-MM-GG Nome pratica>/
        01_Proposta/ 02_Documenti_venditori/ 03_Documenti_acquirenti/
        04_Atto_provenienza/ 05_Planimetrie/
        pratica.json
        Preliminare - <Nome pratica>.docx
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import date, datetime
from pathlib import Path

from . import modello_dati

DATI = Path(os.environ.get("PRELIMINARI_DATI", Path(__file__).resolve().parent.parent / "dati"))
CARTELLA_PRATICHE = DATI / "pratiche"
CARTELLA_MODELLO = DATI / "modello"
MODELLO_PREDEFINITO = Path(__file__).resolve().parent.parent / "modelli" / "preliminare_modello.docx"

CATEGORIE = {
    "proposta": ("01_Proposta", "Proposta di acquisto"),
    "venditori": ("02_Documenti_venditori", "Documenti d'identità venditori"),
    "acquirenti": ("03_Documenti_acquirenti", "Documenti d'identità acquirenti"),
    "provenienza": ("04_Atto_provenienza", "Atto di provenienza"),
    "planimetrie": ("05_Planimetrie", "Planimetrie catastali"),
}

_lock = threading.Lock()


def percorso_modello() -> Path:
    CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)
    m = CARTELLA_MODELLO / "preliminare_modello.docx"
    if not m.exists():
        shutil.copy(MODELLO_PREDEFINITO, m)
    return m


def _nome_sicuro(s: str) -> str:
    s = re.sub(r"[^\w\s\-.'àèéìòùÀÈÉÌÒÙ]", "", s, flags=re.U).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:80].strip(". ") or "pratica"


def nome_file_sicuro(nome: str) -> str:
    base = Path(nome).name
    stem = _nome_sicuro(Path(base).stem) or "file"
    ext = re.sub(r"[^A-Za-z0-9.]", "", Path(base).suffix.lower())[:6]
    return stem + ext


class Pratica:
    def __init__(self, cartella: Path):
        self.cartella = cartella

    @property
    def id(self) -> str:
        return self.cartella.name

    @property
    def file_json(self) -> Path:
        return self.cartella / "pratica.json"

    def carica(self) -> dict:
        if self.file_json.exists():
            stato = json.loads(self.file_json.read_text(encoding="utf-8"))
        else:
            stato = {"nome": self.id, "creata": datetime.now().isoformat(timespec="seconds")}
        stato.setdefault("dati", modello_dati.dati_vuoti())
        stato["dati"] = modello_dati.completa(stato["dati"])
        stato.setdefault("estratti", {})
        stato.setdefault("analisi", {"stato": "mai eseguita"})
        return stato

    def salva(self, stato: dict) -> None:
        with _lock:
            tmp = self.file_json.with_suffix(".tmp")
            tmp.write_text(json.dumps(stato, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            tmp.replace(self.file_json)

    def cartella_categoria(self, cat: str) -> Path:
        c = self.cartella / CATEGORIE[cat][0]
        c.mkdir(parents=True, exist_ok=True)
        return c

    def file_categoria(self, cat: str) -> list[Path]:
        from .estrazione.ocr import ESTENSIONI_AMMESSE
        c = self.cartella_categoria(cat)
        return sorted(p for p in c.iterdir() if p.is_file() and p.suffix.lower() in ESTENSIONI_AMMESSE
                      and not p.name.startswith((".", "~")))

    def aggiungi_file(self, cat: str, nome: str, contenuto: bytes) -> Path:
        dest = self.cartella_categoria(cat) / nome_file_sicuro(nome)
        i = 1
        while dest.exists():
            dest = dest.with_name(f"{Path(nome_file_sicuro(nome)).stem}_{i}{dest.suffix}")
            i += 1
        dest.write_bytes(contenuto)
        return dest

    def file(self, cat: str, nome: str) -> Path:
        p = (self.cartella_categoria(cat) / nome).resolve()
        if p.parent != self.cartella_categoria(cat).resolve() or not p.is_file():
            raise FileNotFoundError(nome)
        return p

    def documenti_generati(self) -> list[Path]:
        return sorted(self.cartella.glob("Preliminare*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)


def elenco() -> list[dict]:
    CARTELLA_PRATICHE.mkdir(parents=True, exist_ok=True)
    out = []
    for c in sorted(CARTELLA_PRATICHE.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if c.is_dir() and not c.name.startswith("."):
            p = Pratica(c)
            stato = p.carica()
            out.append({"id": p.id, "nome": stato.get("nome", p.id), "creata": stato.get("creata", ""),
                        "generato": bool(p.documenti_generati()),
                        "analisi": stato.get("analisi", {}).get("stato", "")})
    return out


def crea(nome: str) -> Pratica:
    CARTELLA_PRATICHE.mkdir(parents=True, exist_ok=True)
    base = f"{date.today().isoformat()} {_nome_sicuro(nome)}"
    cartella = CARTELLA_PRATICHE / base
    i = 2
    while cartella.exists():
        cartella = CARTELLA_PRATICHE / f"{base} ({i})"
        i += 1
    cartella.mkdir(parents=True)
    p = Pratica(cartella)
    for cat in CATEGORIE:
        p.cartella_categoria(cat)
    stato = p.carica()
    stato["nome"] = nome.strip() or cartella.name
    p.salva(stato)
    return p


def apri(pid: str) -> Pratica:
    c = (CARTELLA_PRATICHE / pid).resolve()
    if c.parent != CARTELLA_PRATICHE.resolve() or not c.is_dir():
        raise FileNotFoundError(pid)
    return Pratica(c)
