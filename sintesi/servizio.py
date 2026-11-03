"""Creazione della sintesi e sorveglianza della cartella condivisa.

Oltre che dalla pagina web, i documenti si possono semplicemente copiare nella
cartella condivisa (es. \\\\NAS\\Sintesi):

    Sintesi/
        Rossi Via Roma 10/          <- cartella creata dall'utente
            atto.pdf                <- PDF copiati alla rinfusa
            visura sub 5.pdf
            visura sub 9.pdf

Ogni mezzo minuto il programma controlla le cartelle: i PDF vengono smistati da soli
in 01_Atto_provenienza e 02_Visure_catastali (riconoscendo le visure dal contenuto) e,
quando i documenti sono cambiati, viene creato "Sintesi - <nome cartella>.pdf"
nella stessa cartella.
"""

from __future__ import annotations

import logging
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from app.estrazione import ocr

from . import analisi, archivio, pdf

log = logging.getLogger("sintesi.servizio")

INTERVALLO = 30          # secondi tra un controllo e l'altro
ATTESA_COPIA = 20        # secondi senza modifiche prima di analizzare (copia dei file finita)
LEGGIMI = "LEGGIMI - come usare questa cartella.txt"

_lock_sintesi: dict[str, threading.Lock] = {}
_lock_globale = threading.Lock()


def _lock(s: archivio.Sintesi) -> threading.Lock:
    with _lock_globale:
        return _lock_sintesi.setdefault(s.id, threading.Lock())


# ------------------------------------------------------------------ smistamento

def e_visura(percorso: Path) -> bool:
    """Riconosce una visura catastale dal testo della prima pagina (o dal nome del file)."""
    try:
        pagine = ocr.testo_pdf(percorso)
    except Exception:
        pagine = []
    testo = " ".join(pagine[:2])
    if testo.strip():
        return bool(re.search(r"visura\s+(?:attuale|storica|per\s+(?:immobile|soggetto))|"
                              r"Situazione degli atti informatizzati|Servizi Catastali", testo, re.I)) \
            and not re.search(r"\bnotaio\b.{0,300}\bREPUBBLICA ITALIANA\b|REPUBBLICA ITALIANA.{0,600}\bnotaio\b", testo, re.I | re.S)
    return "visur" in percorso.name.lower()


def smista(s: archivio.Sintesi) -> int:
    """Sposta i PDF lasciati nella cartella principale nelle sottocartelle giuste."""
    spostati = 0
    for f in sorted(s.cartella.iterdir()):
        if not f.is_file() or f.suffix.lower() != ".pdf" or f.name.startswith((".", "~", "Sintesi")):
            continue
        if time.time() - f.stat().st_mtime < ATTESA_COPIA:
            continue  # copia forse ancora in corso
        cat = "visure" if e_visura(f) else "atto"
        dest = s.cartella_categoria(cat) / f.name
        i = 1
        while dest.exists():
            dest = dest.with_name(f"{f.stem}_{i}{f.suffix}")
            i += 1
        try:
            shutil.move(str(f), str(dest))
            spostati += 1
            log.info("%s: %s -> %s", s.id, f.name, archivio.CATEGORIE[cat][0])
        except OSError as e:  # file aperto da qualcuno: si riprova al giro dopo
            log.warning("Non riesco a spostare %s: %s", f, e)
    return spostati


def firma_documenti(s: archivio.Sintesi) -> list:
    return [[c, f.name, f.stat().st_size, int(f.stat().st_mtime)]
            for c in archivio.CATEGORIE for f in s.file_categoria(c)]


# ------------------------------------------------------------------ creazione

def crea_sintesi(s: archivio.Sintesi, origine: str = "pagina web") -> dict:
    """Analizza i documenti e salva il PDF. Restituisce lo stato aggiornato."""
    with _lock(s):
        stato = s.carica()
        atti, visure = s.file_categoria("atto"), s.file_categoria("visure")
        if not atti and not visure:
            raise ValueError("Nessun documento: carica l'atto di provenienza e le visure catastali")
        firma = firma_documenti(s)
        ris = analisi.analizza(atti, visure)
        nome = stato.get("nome") or s.id
        dest = pdf.genera(nome, ris, s.cartella / f"Sintesi - {archivio.nome_sicuro(nome)}.pdf")
        stato["risultato"] = ris
        stato["pdf"] = {"file": dest.name, "quando": datetime.now().isoformat(timespec="seconds"),
                        "origine": origine, "firma": firma}
        stato.pop("errore", None)
        s.salva(stato)
        errore = s.cartella / "ERRORE.txt"
        if errore.exists():
            errore.unlink(missing_ok=True)
        return stato


def _da_aggiornare(s: archivio.Sintesi) -> bool:
    firma = firma_documenti(s)
    if not firma:
        return False
    if max(x[3] for x in firma) > time.time() - ATTESA_COPIA:
        return False  # documenti appena modificati: si aspetta la fine della copia
    stato = s.carica()
    if stato.get("errore", {}).get("firma") == firma:
        return False  # gia' fallita con questi stessi documenti
    return (stato.get("pdf") or {}).get("firma") != firma or not s.pdf()


def controlla_cartelle() -> None:
    archivio.DATI.mkdir(parents=True, exist_ok=True)
    scrivi_leggimi()
    for c in sorted(archivio.DATI.iterdir()):
        if not c.is_dir() or c.name.startswith((".", "cestino")):
            continue
        s = archivio.Sintesi(c)
        try:
            smista(s)
            if not s.file_json.exists():
                s.salva({"nome": c.name, "creata": datetime.now().isoformat(timespec="seconds")})
            if _da_aggiornare(s):
                log.info("Creazione automatica della sintesi: %s", s.id)
                crea_sintesi(s, origine="cartella condivisa")
        except Exception as e:
            log.exception("Sintesi automatica non riuscita: %s", c)
            try:
                stato = s.carica()
                stato["errore"] = {"testo": str(e), "quando": datetime.now().isoformat(timespec="seconds"),
                                   "firma": firma_documenti(s)}
                s.salva(stato)
                (c / "ERRORE.txt").write_text(
                    f"{datetime.now():%d/%m/%Y %H:%M} - la sintesi non è stata creata.\n\n{e}\n\n"
                    "Controlla che i PDF siano integri; si riprova da soli quando i documenti cambiano.\n",
                    encoding="utf-8")
            except Exception:
                pass


def scrivi_leggimi() -> None:
    f = archivio.DATI / LEGGIMI
    if f.exists():
        return
    try:
        f.write_text(
            "SINTESI IMMOBILI - come usare questa cartella\r\n"
            "=============================================\r\n\r\n"
            "1. Crea qui una nuova cartella con il nome dell'immobile, ad esempio:  Rossi - Via Roma 10\r\n"
            "2. Copia dentro i PDF dell'atto di provenienza e delle visure catastali (anche tutti insieme).\r\n"
            "3. Entro un minuto circa i PDF vengono smistati nelle sottocartelle\r\n"
            "   01_Atto_provenienza e 02_Visure_catastali e compare il file\r\n"
            "   \"Sintesi - <nome cartella>.pdf\".\r\n\r\n"
            "Aggiungendo o sostituendo documenti la sintesi viene ricreata da sola.\r\n"
            "In caso di problemi nella cartella compare il file ERRORE.txt.\r\n"
            "Le stesse cartelle si vedono anche dalla pagina web del programma.\r\n",
            encoding="utf-8")
    except OSError:
        pass


def _ciclo() -> None:
    time.sleep(5)
    while True:
        try:
            controlla_cartelle()
        except Exception:
            log.exception("Controllo delle cartelle non riuscito")
        time.sleep(INTERVALLO)


_avviato = False


def avvia_sorveglianza() -> None:
    global _avviato
    if _avviato:
        return
    _avviato = True
    threading.Thread(target=_ciclo, name="sorveglianza-cartelle", daemon=True).start()
    log.info("Sorveglianza della cartella %s avviata (ogni %s secondi)", archivio.DATI, INTERVALLO)
