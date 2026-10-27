"""Ricerca OMI in un processo separato, che si può fermare con certezza.

Su alcuni PC Windows il browser (Edge) usato per il sito dell'Agenzia delle Entrate resta appeso,
di solito alla chiusura: la ricerca aveva trovato i dati ma il programma continuava ad aspettare.
Qui la ricerca gira in un processo a parte che manda i passi e il risultato appena è pronto;
avuto il risultato (o scaduto il tempo, o premuto "Annulla") il processo viene chiuso, se serve
con la forza insieme al browser.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import signal
import subprocess
import time
from pathlib import Path

from . import omi

# i test che simulano il sito sostituiscono le funzioni di ricerca: lì la ricerca resta nel processo
IN_PROCESSO = os.environ.get("VALUTAZIONI_OMI_PROCESSO", "1") != "0"
MARGINE_S = 30           # oltre il tempo massimo della ricerca, prima di chiudere il processo con la forza


def _figlio(funzione: str, kwargs: dict, coda, scadenza_s: float) -> None:
    if os.name != "nt":
        os.setsid()                    # gruppo di processi a sé: si chiude tutto insieme al browser
    consegnato = False

    def consegna(r):
        nonlocal consegnato
        if not consegnato:
            consegnato = True
            coda.put(("ok", _serializza(r)))

    omi.imposta_controllo(time.monotonic() + scadenza_s, lambda t: coda.put(("passo", t)))
    try:
        if funzione == "zone":
            r = omi.zone_disponibili(**kwargs, consegna=consegna)
        elif funzione == "valori":
            r = omi.cerca(**kwargs, consegna=consegna)
        elif funzione == "_prova_appeso":   # per i test: risultato pronto, poi resta appeso (come Edge)
            consegna(kwargs)
            time.sleep(600)
            r = kwargs
        elif funzione == "_prova_bloccato":  # per i test: non risponde mai
            time.sleep(600)
            r = kwargs
        else:                          # "eco": prova del pacchetto (il processo parte e risponde?)
            r = kwargs
        consegna(r)
    except omi.TempoScaduto as e:
        coda.put(("errore", "tempo", str(e)))
    except Exception as e:  # noqa: BLE001 - l'errore va al processo principale
        coda.put(("errore", "", str(e) or e.__class__.__name__))


def _serializza(r):
    if isinstance(r, omi.RisultatoOMI):
        return {"immagini": [str(p) for p in r.immagini], "semestre": r.semestre, "destinazioni": r.destinazioni,
                "note": r.note, "tabelle": r.tabelle, "logo": str(r.logo) if r.logo else None}
    return r


def _risultato_omi(d: dict) -> omi.RisultatoOMI:
    return omi.RisultatoOMI(immagini=[Path(p) for p in d["immagini"]], semestre=d["semestre"],
                            destinazioni=d["destinazioni"], note=d["note"], tabelle=d["tabelle"],
                            logo=Path(d["logo"]) if d.get("logo") else None)


def chiudi(p) -> None:
    """Chiude il processo della ricerca e quello che ha aperto (browser compreso)."""
    if p is None or not p.is_alive():
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    if p.is_alive():
        p.kill()
    p.join(timeout=5)


def esegui(funzione: str, kwargs: dict, scadenza_s: float, avanzamento=None, registra=None):
    """Esegue la ricerca nel processo separato e restituisce il risultato appena arriva."""
    ctx = mp.get_context("spawn")
    coda = ctx.Queue()
    p = ctx.Process(target=_figlio, args=(funzione, kwargs, coda, scadenza_s), name=f"OMI {funzione}")
    p.start()
    if registra:
        registra(p)
    limite = time.monotonic() + scadenza_s + MARGINE_S
    try:
        while True:
            try:
                msg = coda.get(timeout=0.5)
            except queue.Empty:
                if not p.is_alive():
                    try:
                        msg = coda.get(timeout=2)
                    except queue.Empty:
                        raise omi.ErroreOMI("La ricerca OMI si è interrotta senza risultato.") from None
                elif time.monotonic() > limite:
                    raise omi.TempoScaduto("Tempo scaduto: il sito dell'Agenzia delle Entrate non ha risposto "
                                           "in tempo. Riprova tra qualche minuto.") from None
                else:
                    continue
            if msg[0] == "passo":
                if avanzamento:
                    avanzamento(msg[1])
                continue
            if msg[0] == "ok":
                return _risultato_omi(msg[1]) if funzione == "valori" else msg[1]
            raise (omi.TempoScaduto if msg[1] == "tempo" else omi.ErroreOMI)(msg[2])
    finally:
        p.join(timeout=10)              # chiusura normale del browser; se resta appeso, si chiude con la forza
        chiudi(p)


def zone(provincia: str, comune: str, scadenza_s: float, avanzamento=None, registra=None, configura=None) -> dict:
    kwargs = {"provincia": provincia, "comune": comune, "configura": configura}
    if not IN_PROCESSO:
        return omi.zone_disponibili(**kwargs)
    return esegui("zone", kwargs, scadenza_s, avanzamento, registra)


def valori(provincia: str, comune: str, zona: str, cartella: Path, scadenza_s: float, avanzamento=None,
           registra=None, **altro) -> omi.RisultatoOMI:
    kwargs = {"provincia": provincia, "comune": comune, "zona": zona, "cartella": cartella, **altro}
    if not IN_PROCESSO:
        return omi.cerca(**kwargs)
    return esegui("valori", kwargs, scadenza_s, avanzamento, registra)
