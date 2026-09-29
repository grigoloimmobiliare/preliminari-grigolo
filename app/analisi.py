"""Analisi dei documenti caricati e precompilazione dei dati del preliminare."""

from __future__ import annotations

import difflib
import logging
import threading
import traceback
from datetime import datetime

from . import modello_dati
from . import testo as tx
from .estrazione import atto as atto_m
from .estrazione import codice_fiscale as cfm
from .estrazione import documento_identita as docid
from .estrazione import planimetria as plan_m
from .pratiche import Pratica

log = logging.getLogger(__name__)
_in_corso: set[str] = set()
_lock = threading.Lock()


def avvia(pratica: Pratica, sovrascrivi: bool = False) -> bool:
    """Avvia l'analisi in background. Restituisce False se e' gia' in corso."""
    with _lock:
        if pratica.id in _in_corso:
            return False
        _in_corso.add(pratica.id)
    stato = pratica.carica()
    stato["analisi"] = {"stato": "in corso", "inizio": datetime.now().isoformat(timespec="seconds"), "fase": "avvio"}
    pratica.salva(stato)
    threading.Thread(target=_esegui, args=(pratica, sovrascrivi), daemon=True).start()
    return True


def in_corso(pratica: Pratica) -> bool:
    return pratica.id in _in_corso


def _fase(pratica: Pratica, testo: str) -> None:
    stato = pratica.carica()
    stato["analisi"]["fase"] = testo
    pratica.salva(stato)


def _esegui(pratica: Pratica, sovrascrivi: bool) -> None:
    try:
        estratti = estrai_tutto(pratica, lambda f: _fase(pratica, f))
        stato = pratica.carica()
        stato["estratti"] = estratti
        stato["dati"] = unisci(stato["dati"], estratti, sovrascrivi)
        stato["analisi"] = {"stato": "completata", "fine": datetime.now().isoformat(timespec="seconds")}
        pratica.salva(stato)
    except Exception as e:  # pragma: no cover - errori imprevisti mostrati all'utente
        log.exception("Analisi fallita")
        stato = pratica.carica()
        stato["analisi"] = {"stato": "errore", "errore": f"{e}", "dettaglio": traceback.format_exc()[-2000:]}
        pratica.salva(stato)
    finally:
        with _lock:
            _in_corso.discard(pratica.id)


def estrai_tutto(pratica: Pratica, fase=lambda f: None) -> dict:
    estratti: dict = {"errori": []}

    def prova(nome, funzione, *args):
        try:
            return funzione(*args)
        except Exception as e:
            log.exception("Errore in %s", nome)
            estratti["errori"].append(f"{nome}: {e}")
            return None

    fase("lettura atto di provenienza")
    atti = [prova(f.name, atto_m.estrai, f) for f in pratica.file_categoria("provenienza")]
    atti = [a for a in atti if a]
    estratti["atto"] = atti[0] if atti else None

    fase("lettura documenti venditori")
    estratti["venditori"] = prova("documenti venditori", docid.estrai_persone, pratica.file_categoria("venditori")) or []
    fase("lettura documenti acquirenti")
    estratti["acquirenti"] = prova("documenti acquirenti", docid.estrai_persone, pratica.file_categoria("acquirenti")) or []

    fase("lettura planimetrie")
    planimetrie = []
    for f in pratica.file_categoria("planimetrie"):
        planimetrie += prova(f.name, plan_m.estrai, f) or []
    if estratti["atto"]:
        plan_m.abbina(planimetrie, estratti["atto"].get("catastali", []))
    estratti["planimetrie"] = planimetrie
    return estratti


# ------------------------------------------------------------------ unione

def _vuoto(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == []


def _imposta(dest: dict, chiave: str, valore, sovrascrivi: bool) -> None:
    if _vuoto(valore):
        return
    if sovrascrivi or _vuoto(dest.get(chiave)):
        dest[chiave] = valore


def _stesso_nominativo(a: dict, b: dict) -> bool:
    if a.get("codice_fiscale") and a.get("codice_fiscale") == b.get("codice_fiscale"):
        return True
    na = f"{a.get('cognome', '')} {a.get('nome', '')}".upper().strip()
    nb = f"{b.get('cognome', '')} {b.get('nome', '')}".upper().strip()
    return bool(na and nb) and difflib.SequenceMatcher(None, na, nb).ratio() > 0.85


def persone_da_estratti(estratti_docs: list[dict], da_atto: list[dict]) -> list[dict]:
    """Unisce i dati letti dai documenti d'identità con quelli presenti nell'atto
    (per i venditori l'atto riporta CF, luogo di nascita e stato civile)."""
    persone = []
    usati = set()
    for d in estratti_docs:
        p = modello_dati.persona_vuota()
        for k, v in d.items():
            if not k.startswith("_") and not _vuoto(v):
                p[k] = v
        p["_fonti"] = dict(d.get("_fonti", {}))
        p["_avvisi"] = list(d.get("_avvisi", []))
        for i, a in enumerate(da_atto):
            if i in usati:
                continue
            # confronto per CF, oppure per nome/cognome, oppure per data di nascita + cognome simile
            simile = _stesso_nominativo(p, a) or (
                p.get("data_nascita") and p.get("data_nascita") == a.get("data_nascita")
                and difflib.SequenceMatcher(None, p.get("cognome", "").upper(), a.get("cognome", "").upper()).ratio() > 0.7)
            if simile:
                usati.add(i)
                # l'atto e' un testo affidabile: se il CF dell'OCR non e' verificato prevalgono
                # nome, cognome e CF dell'atto
                cf_ocr_verificato = cfm.valido(p.get("codice_fiscale", "")) and "verificato" in p["_fonti"].get("codice_fiscale", "")
                prevale_atto = cfm.valido(a.get("codice_fiscale", "")) and not cf_ocr_verificato
                for k in ("cognome", "nome", "codice_fiscale", "luogo_nascita", "prov_nascita", "data_nascita", "sesso"):
                    if _vuoto(a.get(k)):
                        continue
                    if _vuoto(p.get(k)) or (prevale_atto and k in ("cognome", "nome", "codice_fiscale")) \
                            or (k == "prov_nascita" and p.get(k) not in tx.PROVINCE):
                        p[k] = a[k]
                        p["_fonti"][k] = "atto di provenienza"
                if _vuoto(p.get("stato_civile")) and a.get("stato_civile"):
                    p["stato_civile"] = a["stato_civile"]
                    p["_fonti"]["stato_civile"] = "atto di provenienza (verificare se ancora attuale)"
                p["_residenza_atto"] = a.get("_residenza_atto", "")
                break
        persone.append(p)
    # intestatari dell'atto senza documento caricato
    for i, a in enumerate(da_atto):
        if i not in usati:
            p = modello_dati.persona_vuota()
            p.update({k: v for k, v in a.items() if not _vuoto(v)})
            p["_fonti"] = {k: "atto di provenienza" for k in a if not k.startswith("_")}
            p["_avvisi"] = ["Documento d'identità non caricato: dati presi dall'atto di provenienza"]
            persone.append(p)
    for p in persone:
        if p.get("cognome"):
            p["cognome"] = p["cognome"].upper()
        if p.get("nome"):
            p["nome"] = p["nome"].upper()
    return persone


def unisci(dati: dict, estratti: dict, sovrascrivi: bool = False) -> dict:
    """Riporta i dati estratti nella pratica. Di norma riempie solo i campi vuoti,
    cosi' le correzioni fatte a mano non vengono perse rianalizzando."""
    dati = modello_dati.completa(dati)
    atto = estratti.get("atto") or {}
    intestatari = [atto_m.persona_da_comparente(c) for c in atto.get("intestatari", [])]

    for ruolo, da_atto in (("venditori", intestatari), ("acquirenti", [])):
        nuove = persone_da_estratti(estratti.get(ruolo, []), da_atto)
        if sovrascrivi or not dati[ruolo]:
            dati[ruolo] = nuove
        else:
            for n in nuove:
                esistente = next((p for p in dati[ruolo] if _stesso_nominativo(p, n)), None)
                if esistente is None:
                    dati[ruolo].append(n)
                else:
                    for k, v in n.items():
                        if not k.startswith("_"):
                            _imposta(esistente, k, v, False)
                    esistente.setdefault("_fonti", {}).update(
                        {k: v for k, v in n.get("_fonti", {}).items() if k not in esistente["_fonti"]})

    imm = dati["immobile"]
    for k in ("comune", "prov", "indirizzo", "descrizione"):
        _imposta(imm, k, atto.get(k), sovrascrivi)
    if atto.get("catastali") and (sovrascrivi or not imm["unita"]):
        imm["unita"] = [{k: u.get(k, "") for k, _ in modello_dati.CAMPI_UNITA} for u in atto["catastali"]]
    n_plan = len(estratti.get("planimetrie", []))
    if n_plan:
        _imposta(imm, "n_planimetrie", str(n_plan), sovrascrivi)

    prov = dati["provenienza"]
    _imposta(prov, "tipo_atto", atto.get("tipo_atto"), sovrascrivi)
    _imposta(prov, "notaio", atto.get("notaio"), sovrascrivi)
    _imposta(prov, "notaio_sede", atto.get("notaio_sede"), sovrascrivi)
    _imposta(prov, "data", atto.get("data_atto"), sovrascrivi)
    for k in ("repertorio", "raccolta", "registrazione", "trascrizione"):
        _imposta(prov, k, atto.get(k), sovrascrivi)

    urb = dati["urbanistica"]
    _imposta(urb, "dichiarazione", atto.get("urbanistica"), sovrascrivi)
    if atto.get("ante_67"):
        urb["ante_67"] = True
    if atto.get("agibilita"):
        _imposta(urb, "agibilita", atto.get("agibilita"), sovrascrivi)
        urb["agibilita_presente"] = True

    if not dati["firma"].get("data"):
        dati["firma"]["data"] = tx.formato_data(datetime.now().date())
    return dati
