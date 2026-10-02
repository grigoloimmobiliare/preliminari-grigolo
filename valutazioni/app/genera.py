"""Generazione della valutazione: Excel -> ricerca OMI -> comparabili -> Word con carta intestata."""

from __future__ import annotations

import json
import logging
import shutil
import threading
import traceback
from datetime import datetime
from pathlib import Path

from . import comuni, archivio, excel, immagini, omi, word

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
    """Comune e provincia per la ricerca OMI, dal primo che c'è tra: pagina della valutazione,
    Excel (celle COMUNE e PROVINCIA), comune scritto nell'indirizzo dell'Excel, impostazioni.
    La provincia, se non scritta, si ricava dal comune (elenco ISTAT): Jesolo -> VE."""
    stato = v.carica()
    imp = archivio.impostazioni()
    da_excel = {k: str((d.valore(k) if d else None) or "").strip() for k in ("PROVINCIA", "COMUNE", "ZONA OMI", "INDIRIZZO")}
    avvisi = []
    provincia = ""
    if (stato.get("comune") or "").strip():
        comune, fonte = stato["comune"].strip(), "pagina"
    elif da_excel["COMUNE"]:
        comune, provincia, fonte = da_excel["COMUNE"], da_excel["PROVINCIA"], "Excel"
    elif comuni.dall_indirizzo(da_excel["INDIRIZZO"]):
        comune, provincia = comuni.dall_indirizzo(da_excel["INDIRIZZO"])
        provincia, fonte = provincia or "", "indirizzo"
    else:
        comune, provincia, fonte = (imp["comune"] or "").strip(), (imp["provincia"] or "").strip(), "predefinito"
    provincia = (stato.get("provincia") or "").strip() or provincia     # la pagina vale sempre
    trovato = comuni.trova(comune)
    if trovato:
        if not provincia and len(trovato[1]) == 1:
            provincia = trovato[1][0]
        elif provincia and provincia.upper() not in trovato[1]:
            avvisi.append(f"{trovato[0]} risulta in provincia di {'/'.join(trovato[1])}, non {provincia.upper()}: controlla.")
        elif not provincia:
            avvisi.append(f"Ci sono più comuni chiamati {trovato[0]} ({', '.join(trovato[1])}): scrivi la provincia.")
    elif comune:
        avvisi.append(f"Comune \"{comune}\" non trovato nell'elenco ISTAT: controlla come è scritto.")
    return {
        "provincia": provincia.upper(),
        "comune": comune,
        "comune_nome": trovato[0] if trovato else comune,      # come si scrive (per il Word)
        "fonte": fonte,
        "avvisi": avvisi,
        "zona": da_excel["ZONA OMI"],
        "destinazioni": [x.strip() for x in (imp.get("destinazioni") or "").split(",") if x.strip()],
    }


def genera(v: archivio.Valutazione, messaggi: list[dict], cerca_omi: bool = True) -> Path:
    archivio.CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)     # logo e carta intestata vanno qui
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
    logo_trovato: Path | None = None
    dati_omi: dict | None = None
    if manuali:
        img_omi = immagini.immagini_da_file(manuali, v.lavoro / "omi")
        _msg(messaggi, "ok", f"Valori OMI: uso i file caricati a mano ({', '.join(f.name for f in manuali)}).")
    elif cerca_omi:
        par = parametri_omi(v, d)
        da = {"pagina": "scritto nella pagina della valutazione", "Excel": "dall'Excel (cella COMUNE)",
              "indirizzo": "dall'indirizzo nell'Excel", "predefinito": "comune predefinito delle impostazioni"}
        _msg(messaggi, "ok", f"Comune per la ricerca OMI: {par['comune_nome']} ({par['provincia']}), {da[par['fonte']]}.")
        for a in par["avvisi"]:
            _msg(messaggi, "avviso", a)
        if not par["zona"]:
            _msg(messaggi, "errore", "Nell'Excel manca la zona OMI (cella accanto a \"ZONA OMI\": il codice, "
                                     "es. B1, o il nome della zona, es. Centro storico): ricerca OMI non eseguita.")
        else:
            for vecchio in cartella_omi.glob("*"):
                if vecchio.name.startswith(archivio.PREFISSO_AUTO):
                    vecchio.unlink()
            try:
                r = omi.cerca(par["provincia"], par["comune"], par["zona"], cartella_omi,
                              destinazioni=par["destinazioni"] or None)
                img_omi = r.immagini
                if r.tabelle:
                    dati_omi = r.come_dict()
                    dati_omi["data"] = excel.fmt_data(datetime.now())
                    (cartella_omi / "auto_OMI.json").write_text(json.dumps(dati_omi, ensure_ascii=False, indent=1),
                                                              encoding="utf-8")
                else:
                    _msg(messaggi, "avviso", "Non sono riuscito a leggere i valori dalla pagina OMI: "
                                             "nel Word inserisco la schermata al posto della tabella.")
                logo_trovato = r.logo if r.logo and r.logo.exists() else None
                if logo_trovato and not archivio.logo_agenzia():
                    try:        # il logo serve anche alle prossime valutazioni: va nella cartella del modello
                        archivio.CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)
                        shutil.copy(r.logo, archivio.CARTELLA_MODELLO / "logo_agenzia_entrate.png")
                    except OSError as e:
                        log.warning("Logo dell'Agenzia non salvato nella cartella del modello: %s", e)
                codice = next((v for t in r.tabelle for k, v in t.get("info", []) if k == "Codice di zona"),
                              omi.codice_zona(par["zona"]))
                dettagli = f"{par['comune']} ({par['provincia']}), zona {codice}"
                if r.semestre:
                    dettagli += f", semestre {r.semestre}"
                if r.destinazioni:
                    dettagli += f", destinazioni: {', '.join(r.destinazioni)}"
                _msg(messaggi, "ok", f"Valori OMI trovati sul sito dell'Agenzia delle Entrate: {dettagli}.")
            except omi.ErroreOMI as e:
                _msg(messaggi, "errore", f"{e} Puoi caricare a mano la schermata dei valori OMI nella cartella "
                                         f"03_OMI e rigenerare.")
    else:
        salvati = cartella_omi / "auto_OMI.json"
        if salvati.exists():
            dati_omi = json.loads(salvati.read_text(encoding="utf-8"))
            _msg(messaggi, "ok", f"Valori OMI: riuso quelli della ricerca del {dati_omi.get('data', '?')}.")
        else:
            img_omi = sorted(p for p in cartella_omi.glob("auto_OMI*.png") if not p.stem.endswith("_logo"))
            if img_omi:
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
                     oggi=excel.fmt_data(datetime.now()), immagini_omi=img_omi,
                     immagini_comparabili=img_comp, carta_intestata=img_carta,
                     extra={"COMUNE": par["comune_nome"].title() if par["comune_nome"].isupper() else par["comune_nome"],
                            "PROVINCIA": par["provincia"].upper()},
                     dati_omi=dati_omi, logo_omi=archivio.logo_agenzia() or logo_trovato)
    if dati_omi and not (archivio.logo_agenzia() or logo_trovato):
        _msg(messaggi, "avviso", "Logo dell'Agenzia delle Entrate non disponibile: caricalo dalla pagina "
                                 "Modello e carta intestata.")
    for a in r["avvisi"]:
        _msg(messaggi, "avviso", a)
    if r["mancanti"]:
        _msg(messaggi, "avviso", "Dati non trovati nell'Excel (evidenziati in giallo nel Word): "
                                 + ", ".join(f"[{m}]" for m in r["mancanti"]))
    _msg(messaggi, "ok", f"Word creato: {dest.name}")
    return dest
