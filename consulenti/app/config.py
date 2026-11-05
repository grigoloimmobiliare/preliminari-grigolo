"""Cartella dei dati del programma e piccole utilità sui file.

La cartella dei dati è quella condivisa dell'ufficio (es. \\\\NAS\\Consulenti\\Dati), indicata dalla
variabile CONSULENTI_DATI. Contiene:
    report_collaboratori/   i report personali caricati ogni settimana (+ archivio/)
    benchmark/              i benchmark mensili (anno-mese.xlsx)
    risultati/              i file Excel prodotti dal programma
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path

DATI = Path(os.environ.get("CONSULENTI_DATI", Path(__file__).resolve().parent.parent / "dati"))


def con_tentativi(funzione, tentativi: int = 10):
    """Ripete un'operazione sui file se Windows la rifiuta perché il file è in uso
    (antivirus, indicizzazione, un altro PC che lo sta aprendo dalla rete)."""
    for i in range(tentativi):
        try:
            return funzione()
        except PermissionError:
            if i == tentativi - 1:
                raise
            time.sleep(0.2 * (i + 1))


def nome_file_sicuro(nome: str) -> str:
    base = Path(nome).name
    stem = re.sub(r"[^\w\s\-.'àèéìòùÀÈÉÌÒÙ]", "", Path(base).stem, flags=re.U).strip()
    stem = re.sub(r"\s+", " ", stem)[:80].strip(". ") or "file"
    ext = re.sub(r"[^A-Za-z0-9.]", "", Path(base).suffix.lower())[:6]
    return stem + ext


def cartella_risultati() -> Path:
    return DATI / "risultati"


def salva_risultato(contenuto: bytes, nome_file: str) -> str:
    """Salva un file prodotto in Dati/risultati e restituisce il nome. Se il file con lo stesso nome
    è aperto in Excel su un altro PC (e non si può sovrascrivere) aggiunge data e ora al nome."""
    cartella = cartella_risultati()
    cartella.mkdir(parents=True, exist_ok=True)
    nome = nome_file_sicuro(nome_file)
    try:
        con_tentativi(lambda: (cartella / nome).write_bytes(contenuto), tentativi=3)
    except PermissionError:
        p = Path(nome)
        nome = f"{p.stem} {datetime.now():%Y-%m-%d %H%M%S}{p.suffix}"
        con_tentativi(lambda: (cartella / nome).write_bytes(contenuto))
    return nome


def risultati_recenti(quanti: int = 8) -> list[dict]:
    cartella = cartella_risultati()
    if not cartella.exists():
        return []
    file = sorted(cartella.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)[:quanti]
    return [{"nome": f.name, "quando": datetime.fromtimestamp(f.stat().st_mtime)} for f in file]
