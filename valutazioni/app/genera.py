"""Generazione della valutazione: Excel -> ricerca OMI -> comparabili -> Word con carta intestata."""

from __future__ import annotations

import logging
import shutil
import threading
import traceback
from datetime import datetime
from pathlib import Path

from . import archivio, excel, immagini, omi, word

log = logging.getLogger("valutazioni")

_in_corso: set[str] = set()
_lock = threading.Lock()


def in_corso(v: archivio.Valutazione) -> bool:
    with _lock:
        return v.id in _in_corso


def avvia(v: archivio.Valutazione, cerca_omi: bool = True) -> bool:
    with _lock:
        if v.id in _in_corso:
            return False
        _in_corso.add(v.id)
    stato = v.carica()
    stato["generazione"] = {"stato": "in corso", "iniziata": datetime.now().isoformat(timespec="seconds"),
                            "messaggi": []}
    v.salva(stato)
    threading.Thread(target=_esegui, args=(v, cerca_omi), daemon=True).start()
    return True


def _esegui(v: archivio.Valutazione, cerca_omi: bool) -> None:
    messaggi: list[dict] = []
    esito = "completata"
    documento = None
    try:
        documento = genera(v, messaggi, cerca_omi)
        if any(m["tipo"] == "errore" for m in messaggi):
            esito = "completata con avvisi"
    except Exception as e:  # noqa: BLE001 - l'errore va mostrato nella pagina
        log.exception("Generazione non riuscita per %s", v.id)
        messaggi.append({"tipo": "errore", "testo": str(e) or e.__class__.__name__})
        messaggi.append({"tipo": "dettaglio", "testo": traceback.format_exc(limit=3)})
        esito = "non riuscita"
    finally:
        stato = v.carica()
        stato["generazione"] = {"stato": esito, "finita": datetime.now().isoformat(timespec="seconds"),
                                "messaggi": messaggi, "documento": documento.name if documento else None}
        v.salva(stato)
        with _lock:
            _in_corso.discard(v.id)


def _msg(messaggi, tipo, testo):
    messaggi.append({"tipo": tipo, "testo": testo})
    log.info("%s: %s", tipo, testo)


def parametri_omi(v: archivio.Valutazione, d: excel.DatiExcel | None) -> dict:
    """Provincia e comune: pagina della valutazione > Excel (celle COMUNE/PROVINCIA) > impostazioni."""
    stato = v.carica()
    imp = archivio.impostazioni()
    da_excel = {k: (d.valore(k) if d else None) for k in ("PROVINCIA", "COMUNE", "ZONA OMI")}
    return {
        "provincia": (stato.get("provincia") or da_excel["PROVINCIA"] or imp["provincia"] or "").strip(),
        "comune": (stato.get("comune") or da_excel["COMUNE"] or imp["comune"] or "").strip(),
        "zona": str(da_excel["ZONA OMI"] or "").strip(),
        "destinazioni": [x.strip() for x in (imp.get("destinazioni") or "").split(",") if x.strip()],
    }


def genera(v: archivio.Valutazione, messaggi: list[dict], cerca_omi: bool = True) -> Path:
    stato = v.carica()
    fogli = v.file_categoria("excel")
    if not fogli:
        raise RuntimeError("Carica prima il file Excel della stima.")
    foglio = max(fogli, key=lambda p: p.stat().st_mtime)
    if len(fogli) > 1:
        _msg(messaggi, "avviso", f"Ci sono più file Excel: uso il più recente, {foglio.name}.")
    d = excel.leggi(foglio)
    for a in d.avvisi:
        _msg(messaggi, "avviso", a)
    _msg(messaggi, "ok", f"Excel letto: {foglio.name} ({len(d.vani)} vani, {len(d.pertinenze)} pertinenze).")

    shutil.rmtree(v.lavoro, ignore_errors=True)
    v.lavoro.mkdir(parents=True)

    # ---- valori OMI
    cartella_omi = v.cartella_categoria("omi")
    manuali = v.file_categoria("omi", anche_automatici=False)
    img_omi: list[Path] = []
    if manuali:
        img_omi = immagini.immagini_da_file(manuali, v.lavoro / "omi")
        _msg(messaggi, "ok", f"Valori OMI: uso i file caricati a mano ({', '.join(f.name for f in manuali)}).")
    elif cerca_omi:
        par = parametri_omi(v, d)
        if not par["zona"]:
            _msg(messaggi, "errore", "Nell'Excel manca la zona OMI (cella accanto a \"ZONA OMI\"): "
                                     "ricerca OMI non eseguita.")
        else:
            for vecchio in cartella_omi.glob("*"):
                if vecchio.name.startswith(archivio.PREFISSO_AUTO):
                    vecchio.unlink()
            try:
                r = omi.cerca(par["provincia"], par["comune"], par["zona"], cartella_omi,
                              destinazioni=par["destinazioni"] or None)
                img_omi = r.immagini
                dettagli = f"{par['comune']} ({par['provincia']}), zona {omi.codice_zona(par['zona'])}"
                if r.semestre:
                    dettagli += f", semestre {r.semestre}"
                if r.destinazioni:
                    dettagli += f", destinazioni: {', '.join(r.destinazioni)}"
                _msg(messaggi, "ok", f"Valori OMI trovati sul sito dell'Agenzia delle Entrate: {dettagli}.")
            except omi.ErroreOMI as e:
                _msg(messaggi, "errore", f"{e} Puoi caricare a mano la schermata dei valori OMI nella cartella "
                                         f"03_OMI e rigenerare.")
    else:
        old = sorted(p for p in cartella_omi.glob("auto_*.png"))
        img_omi = old
        if old:
            _msg(messaggi, "ok", "Valori OMI: riuso le schermate della ricerca precedente.")

    # ---- comparabili
    comp = v.file_categoria("comparabili")
    img_comp = immagini.immagini_da_file(comp, v.lavoro / "comparabili")
    if img_comp:
        _msg(messaggi, "ok", f"Comparabili: {len(img_comp)} pagine inserite dopo \"Valori di Comparazione\".")
    else:
        _msg(messaggi, "avviso", "Nessun PDF dei comparabili (BorsinoPro) caricato.")

    # ---- carta intestata
    carta = archivio.carta_intestata()
    img_carta = None
    if carta:
        img_carta = immagini.carta_intestata_png(carta, archivio.CARTELLA_MODELLO / ".carta_intestata.png")
    else:
        _msg(messaggi, "avviso", "Carta intestata non ancora caricata (pagina Impostazioni): il Word è senza.")

    # ---- Word
    dest = v.cartella / f"Valutazione - {archivio.nome_sicuro(stato['nome'])}.docx"
    par = parametri_omi(v, d)
    r = word.compila(archivio.file_modello("valutazione_modello.docx"), d, dest,
                     oggi=datetime.now().strftime("%d/%m/%Y"), immagini_omi=img_omi,
                     immagini_comparabili=img_comp, carta_intestata=img_carta,
                     extra={"COMUNE": par["comune"], "PROVINCIA": par["provincia"]})
    for a in r["avvisi"]:
        _msg(messaggi, "avviso", a)
    if r["mancanti"]:
        _msg(messaggi, "avviso", "Dati non trovati nell'Excel (evidenziati in giallo nel Word): "
                                 + ", ".join(f"[{m}]" for m in r["mancanti"]))
    _msg(messaggi, "ok", f"Word creato: {dest.name}")
    return dest
