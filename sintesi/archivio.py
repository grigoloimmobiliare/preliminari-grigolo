"""Cartelle delle sintesi sulla cartella condivisa.

Struttura:
    <DATI>/<AAAA-MM-GG Nome immobile>/
        01_Atto_provenienza/
        02_Visure_catastali/
        sintesi.json
        Sintesi - <Nome immobile>.pdf
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path

DATI = Path(os.environ.get("SINTESI_DATI", Path(__file__).resolve().parent.parent / "dati_sintesi"))

CATEGORIE = {
    "atto": ("01_Atto_provenienza", "Atto di provenienza"),
    "visure": ("02_Visure_catastali", "Visure catastali"),
}
ESTENSIONI = {".pdf"}

_lock = threading.RLock()


def _con_tentativi(funzione, tentativi: int = 10):
    """Ripete l'operazione se Windows rifiuta il file perche' in uso (antivirus, altro PC in rete)."""
    for i in range(tentativi):
        try:
            return funzione()
        except PermissionError:
            if i == tentativi - 1:
                raise
            time.sleep(0.2 * (i + 1))


def nome_sicuro(s: str) -> str:
    s = re.sub(r"[^\w\s\-.'àèéìòùÀÈÉÌÒÙ]", "", s, flags=re.U).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:80].strip(". ") or "immobile"


def nome_file_sicuro(nome: str) -> str:
    base = Path(nome).name
    stem = nome_sicuro(Path(base).stem) or "file"
    ext = re.sub(r"[^A-Za-z0-9.]", "", Path(base).suffix.lower())[:6]
    return stem + ext


class Sintesi:
    def __init__(self, cartella: Path):
        self.cartella = cartella

    @property
    def id(self) -> str:
        return self.cartella.name

    @property
    def file_json(self) -> Path:
        return self.cartella / "sintesi.json"

    def carica(self) -> dict:
        with _lock:
            testo = _con_tentativi(lambda: self.file_json.read_text(encoding="utf-8")) if self.file_json.exists() else None
        stato = json.loads(testo) if testo else {}
        stato.setdefault("nome", self.id)
        stato.setdefault("creata", "")
        return stato

    def salva(self, stato: dict) -> None:
        testo = json.dumps(stato, ensure_ascii=False, indent=1, default=str)
        with _lock:
            tmp = self.file_json.with_suffix(".tmp")
            _con_tentativi(lambda: tmp.write_text(testo, encoding="utf-8"))
            try:
                _con_tentativi(lambda: tmp.replace(self.file_json), tentativi=5)
            except PermissionError:
                _con_tentativi(lambda: self.file_json.write_text(testo, encoding="utf-8"))
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def cartella_categoria(self, cat: str) -> Path:
        c = self.cartella / CATEGORIE[cat][0]
        c.mkdir(parents=True, exist_ok=True)
        return c

    def file_categoria(self, cat: str) -> list[Path]:
        c = self.cartella_categoria(cat)
        return sorted(p for p in c.iterdir() if p.is_file() and p.suffix.lower() in ESTENSIONI
                      and not p.name.startswith((".", "~")))

    def aggiungi_file(self, cat: str, nome: str, contenuto: bytes) -> Path:
        base = nome_file_sicuro(nome)
        dest = self.cartella_categoria(cat) / base
        i = 1
        while dest.exists():
            dest = dest.with_name(f"{Path(base).stem}_{i}{dest.suffix}")
            i += 1
        dest.write_bytes(contenuto)
        return dest

    def file(self, cat: str, nome: str) -> Path:
        p = (self.cartella_categoria(cat) / nome).resolve()
        if p.parent != self.cartella_categoria(cat).resolve() or not p.is_file():
            raise FileNotFoundError(nome)
        return p

    def pdf(self) -> Path | None:
        pdf = sorted(self.cartella.glob("Sintesi*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        return pdf[0] if pdf else None


def elenco() -> list[dict]:
    DATI.mkdir(parents=True, exist_ok=True)
    out = []
    for c in sorted(DATI.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if c.is_dir() and not c.name.startswith((".", "cestino")):
            s = Sintesi(c)
            stato = s.carica()
            out.append({"id": s.id, "nome": stato.get("nome", s.id), "creata": stato.get("creata", ""),
                        "pdf": bool(s.pdf())})
    return out


def crea(nome: str) -> Sintesi:
    DATI.mkdir(parents=True, exist_ok=True)
    base = f"{date.today().isoformat()} {nome_sicuro(nome)}"
    cartella = DATI / base
    i = 2
    while cartella.exists():
        cartella = DATI / f"{base} ({i})"
        i += 1
    cartella.mkdir(parents=True)
    s = Sintesi(cartella)
    for cat in CATEGORIE:
        s.cartella_categoria(cat)
    s.salva({"nome": nome.strip() or cartella.name, "creata": datetime.now().isoformat(timespec="seconds")})
    return s


def apri(sid: str) -> Sintesi:
    c = (DATI / sid).resolve()
    if c.parent != DATI.resolve() or not c.is_dir():
        raise FileNotFoundError(sid)
    return Sintesi(c)
