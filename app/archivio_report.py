"""Cartella dei report personali dei collaboratori.

Ogni settimana si caricano i report aggiornati: il consulente viene riconosciuto dalla cella
CONSULENTE e il file viene salvato come ``report_collaboratori/TATIANA.xlsx``. La versione
precedente passa in ``report_collaboratori/archivio`` con la data. Nella cartella si possono anche
copiare i file direttamente dalla rete: vengono letti allo stesso modo.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from . import pratiche
from .report_consulenti import ErroreReport, _leggi_foglio, descrizione_mese, mese_da_nome

CARTELLA = pratiche.DATI / "report_collaboratori"


def _archivio() -> Path:
    return CARTELLA / "archivio"


@dataclass
class ReportSalvato:
    file: Path
    consulente: str
    mesi: list[tuple[int, int]]
    aggiornato: datetime
    avvisi: list[str] = field(default_factory=list)

    @property
    def mesi_descritti(self) -> list[str]:
        return [descrizione_mese(a, m) for a, m in self.mesi]


def leggi_info(contenuto: bytes, nome_file: str) -> tuple[str, list[tuple[int, int]]]:
    """Consulente e mesi presenti in un report personale."""
    try:
        wb = load_workbook(io.BytesIO(contenuto), data_only=True)
    except Exception:
        raise ErroreReport(f"{nome_file}: non è un file Excel .xlsx leggibile")
    mesi, nomi = [], []
    for ws in wb.worksheets:
        m = mese_da_nome(ws.title)
        if not m:
            continue
        try:
            nomi.append(_leggi_foglio(ws, nome_file).consulente)
        except ErroreReport:
            continue
        mesi.append(m)
    if not nomi:
        raise ErroreReport(f"{nome_file}: non trovo fogli dei mesi (es. NOVEMBRE_2026) con le intestazioni "
                           "del report personale")
    return nomi[-1], sorted(set(mesi))


def _nome_file(consulente: str) -> str:
    return (re.sub(r"[^\w\s-]", "", consulente).strip() or "CONSULENTE") + ".xlsx"


def salva(nome_file: str, contenuto: bytes) -> ReportSalvato:
    consulente, mesi = leggi_info(contenuto, nome_file)
    CARTELLA.mkdir(parents=True, exist_ok=True)
    adesso = datetime.now()
    # La versione precedente dello stesso consulente (anche con un altro nome di file) va in archivio.
    for vecchio in elenco():
        if vecchio.consulente == consulente:
            if vecchio.file.read_bytes() == contenuto:
                pratiche._con_tentativi(lambda f=vecchio.file: f.unlink())
                continue
            _archivio().mkdir(exist_ok=True)
            dest = _archivio() / f"{vecchio.file.stem} {vecchio.aggiornato:%Y-%m-%d %H%M%S}.xlsx"
            pratiche._con_tentativi(lambda f=vecchio.file, d=dest: f.replace(d))
    dest = CARTELLA / _nome_file(consulente)
    pratiche._con_tentativi(lambda: dest.write_bytes(contenuto))
    return ReportSalvato(dest, consulente, mesi, adesso)


def elenco() -> list[ReportSalvato]:
    """Report nella cartella (non in archivio). Se due file sono dello stesso consulente vale il più recente."""
    if not CARTELLA.exists():
        return []
    trovati: dict[str, ReportSalvato] = {}
    for f in sorted(CARTELLA.glob("*.xls[xm]")):
        if f.name.startswith("~$"):  # file di blocco di Excel aperto
            continue
        aggiornato = datetime.fromtimestamp(f.stat().st_mtime)
        try:
            consulente, mesi = leggi_info(f.read_bytes(), f.name)
        except (ErroreReport, OSError) as e:
            trovati[f"?{f.name}"] = ReportSalvato(f, "", [], aggiornato, [str(e)])
            continue
        r = ReportSalvato(f, consulente, mesi, aggiornato)
        if (prec := trovati.get(consulente)) and prec.aggiornato > aggiornato:
            prec.avvisi.append(f"C'è anche {f.name} dello stesso consulente, più vecchio: non viene usato")
            continue
        if prec:
            r.avvisi.append(f"C'è anche {prec.file.name} dello stesso consulente, più vecchio: non viene usato")
        trovati[consulente] = r
    return sorted(trovati.values(), key=lambda r: (r.consulente == "", r.consulente or r.file.name))


def file_per_elaborare() -> list[tuple[str, bytes]]:
    validi = [r for r in elenco() if r.consulente]
    if not validi:
        raise ErroreReport("Nella cartella dei report collaboratori non ci sono report: caricali dalla pagina "
                           "Report collaboratori")
    return [(r.file.name, r.file.read_bytes()) for r in validi]


def percorso(nome: str) -> Path | None:
    f = (CARTELLA / nome).resolve()
    if f.parent != CARTELLA.resolve() or not f.is_file() or f.suffix.lower() not in (".xlsx", ".xlsm"):
        return None
    return f


def elimina(nome: str) -> bool:
    """Sposta il report in archivio (non viene cancellato)."""
    f = percorso(nome)
    if f is None:
        return False
    _archivio().mkdir(parents=True, exist_ok=True)
    dest = _archivio() / f"{f.stem} tolto {datetime.now():%Y-%m-%d %H%M%S}{f.suffix}"
    pratiche._con_tentativi(lambda: f.replace(dest))
    return True
