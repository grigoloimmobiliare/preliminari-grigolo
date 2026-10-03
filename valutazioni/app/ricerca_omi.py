"""Ricerca OMI dalla pagina della valutazione, prima di creare il Word.

1. "Cerca le zone": elenco delle zone OMI del comune (ultimo semestre);
2. "Cerca i valori": valori di tutte le destinazioni della zona scelta, salvati in 03_OMI/auto_OMI.json;
3. nella pagina si spuntano le destinazioni e le righe (tipologia / stato) da mettere nel Word;
   la scelta è salvata nello stesso file e la creazione del Word la usa senza ripetere la ricerca.

Le ricerche durano da qualche secondo a qualche minuto: girano in background e la pagina si
aggiorna da sola finché non sono finite.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from . import archivio, excel, omi

log = logging.getLogger("valutazioni")
_lock = threading.Lock()
_in_corso: set[str] = set()


def in_corso(v: archivio.Valutazione) -> bool:
    with _lock:
        return v.id in _in_corso


def file_valori(v: archivio.Valutazione) -> Path:
    return v.cartella_categoria("omi") / "auto_OMI.json"


def valori(v: archivio.Valutazione) -> dict | None:
    """Ultimi valori trovati (con la scelta fatta nella pagina), o None."""
    f = file_valori(v)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (OSError, ValueError):
        return None


def _avvia(v: archivio.Valutazione, tipo: str, lavoro) -> bool:
    with _lock:
        if v.id in _in_corso:
            return False
        _in_corso.add(v.id)
    stato = v.carica()
    stato["omi"] = {**stato.get("omi", {}), "in_corso": tipo, "errore": "",
                    "iniziata": datetime.now().isoformat(timespec="seconds")}
    v.salva(stato)

    def esegui():
        errore = ""
        try:
            risultato = lavoro()
        except Exception as e:  # noqa: BLE001 - l'errore va mostrato nella pagina
            log.exception("Ricerca OMI (%s) non riuscita per %s", tipo, v.id)
            errore, risultato = str(e).split("\n--- pagina ---")[0] or e.__class__.__name__, {}
        finally:
            with _lock:
                _in_corso.discard(v.id)
        stato = v.carica()
        stato["omi"] = {**stato.get("omi", {}), **risultato, "in_corso": "", "errore": errore}
        v.salva(stato)

    threading.Thread(target=esegui, daemon=True).start()
    return True


def avvia_zone(v: archivio.Valutazione, provincia: str, comune: str, configura=None) -> bool:
    def lavoro():
        r = omi.zone_disponibili(provincia, comune, configura=configura)
        if not r["zone"]:
            raise omi.ErroreOMI(f"Nessuna zona OMI trovata per {comune} ({provincia}).")
        return {"zone": r["zone"], "semestre_zone": r["semestre"], "comune_zone": comune, "provincia_zone": provincia}
    return _avvia(v, "zone", lavoro)


def avvia_valori(v: archivio.Valutazione, provincia: str, comune: str, zona: str, configura=None) -> bool:
    cartella = v.cartella_categoria("omi")

    def lavoro():
        for vecchio in cartella.iterdir():
            if vecchio.name.startswith(archivio.PREFISSO_AUTO):
                vecchio.unlink()
        r = omi.cerca(provincia, comune, zona, cartella, configura=configura)
        if not r.tabelle:
            raise omi.ErroreOMI("Valori non leggibili dalla pagina OMI: puoi caricare a mano la schermata.")
        dati = r.come_dict()
        dati.update({"data": excel.fmt_data(datetime.now()), "comune": comune, "provincia": provincia,
                     "zona": zona, "dalla_pagina": True})
        for t in dati["tabelle"]:          # di partenza è tutto scelto
            t["scelta"] = True
            t["righe_escluse"] = []
        file_valori(v).write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
        if r.logo and r.logo.exists() and not archivio.logo_agenzia():
            try:
                archivio.CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)
                (archivio.CARTELLA_MODELLO / "logo_agenzia_entrate.png").write_bytes(r.logo.read_bytes())
            except OSError as e:
                log.warning("Logo dell'Agenzia non salvato: %s", e)
        return {"zona_valori": zona}
    return _avvia(v, "valori", lavoro)


# ---------------------------------------------------------------- righe e scelta

def righe_dati(t: dict, ripeti: bool = True) -> list[dict]:
    """Righe di valori di una tabella (sotto l'intestazione), col testo di ogni colonna
    (le celle unite su più righe, es. "Abitazioni civili", valgono per tutte se `ripeti`)."""
    testo: dict[tuple[int, int], str] = {}
    for c in t["celle"]:
        for dr in range(c["rs"]):
            for dc in range(c["cs"]):
                testo[(c["r"] + dr, c["c"] + dc)] = c["t"] if dc == 0 and (dr == 0 or ripeti) else ""
    out = []
    for r in range(t["intestazione"], t["righe"]):
        celle = [testo.get((r, c), "") for c in range(t["colonne"])]
        if any(celle):
            out.append({"r": r, "celle": celle})
    return out


def filtra(t: dict, escluse: list[int]) -> dict:
    """La tabella senza le righe escluse (indici di riga della griglia); le celle unite si accorciano."""
    tenute = [r for r in range(t["righe"]) if r < t["intestazione"] or r not in set(escluse)]
    nuovo = {r: i for i, r in enumerate(tenute)}
    celle = []
    for c in t["celle"]:
        coperte = [r for r in range(c["r"], c["r"] + c["rs"]) if r in nuovo]
        if coperte:
            celle.append({**c, "r": nuovo[coperte[0]], "rs": len(coperte)})
    return {**t, "celle": celle, "righe": len(tenute)}


def per_il_word(dati: dict) -> dict:
    """Solo le destinazioni e le righe scelte nella pagina."""
    tabelle = []
    for t in dati.get("tabelle", []):
        if t.get("scelta", True):
            tabelle.append(filtra(t, t.get("righe_escluse", [])))
    return {**dati, "tabelle": tabelle, "destinazioni": [t.get("destinazione", "") for t in tabelle]}


def salva_scelta(v: archivio.Valutazione, form: dict) -> dict | None:
    """form: dest_<i> = destinazione scelta, riga_<i>_<r> = riga scelta (checkbox spuntate)."""
    dati = valori(v)
    if not dati:
        return None
    for i, t in enumerate(dati["tabelle"]):
        t["scelta"] = f"dest_{i}" in form
        t["righe_escluse"] = [x["r"] for x in righe_dati(t) if f"riga_{i}_{x['r']}" not in form]
    file_valori(v).write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
    return dati
