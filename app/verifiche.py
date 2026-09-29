"""Controlli di coerenza sui dati della pratica, mostrati prima di generare il Word."""

from __future__ import annotations

import difflib
from datetime import date
from decimal import Decimal

from . import modello_dati
from . import testo as tx
from .estrazione import codice_fiscale as cfm

ERRORE, ATTENZIONE, INFO = "errore", "attenzione", "info"


def _msg(livello: str, sezione: str, testo: str) -> dict:
    return {"livello": livello, "sezione": sezione, "testo": testo}


def _nome(p: dict) -> str:
    return f"{p.get('cognome', '')} {p.get('nome', '')}".strip() or "(senza nome)"


def controlla(stato: dict, file_per_categoria: dict[str, int]) -> list[dict]:
    dati = stato["dati"]
    estratti = stato.get("estratti") or {}
    out: list[dict] = []

    # ---------------------------------------------------------- documenti caricati
    etichette = {"proposta": "la proposta di acquisto", "venditori": "i documenti dei venditori",
                 "acquirenti": "i documenti degli acquirenti", "provenienza": "l'atto di provenienza",
                 "planimetrie": "le planimetrie catastali"}
    for cat, n in file_per_categoria.items():
        if not n:
            out.append(_msg(ATTENZIONE, "Documenti", f"Non sono stati caricati {etichette[cat]}."))
    for e in estratti.get("errori", []):
        out.append(_msg(ERRORE, "Documenti", f"Errore nella lettura di {e}"))

    firma = tx.parse_data(dati["firma"].get("data")) or date.today()
    rogito = tx.parse_data(dati["accordi"].get("data_rogito"))

    # ---------------------------------------------------------------- persone
    for ruolo, nome_ruolo in (("venditori", "Venditori"), ("acquirenti", "Acquirenti")):
        persone = dati[ruolo]
        if not persone:
            out.append(_msg(ERRORE, nome_ruolo, "Nessuna persona inserita."))
        for p in persone:
            chi = _nome(p)
            campi = modello_dati.CAMPI_PERSONA + (modello_dati.CAMPI_SOCIETA if p.get("tipo") == "societa" else [])
            mancanti = [etichetta for k, etichetta, obbl in campi if obbl and not str(p.get(k, "")).strip()]
            if mancanti:
                out.append(_msg(ATTENZIONE, nome_ruolo, f"{chi}: mancano {', '.join(mancanti)}."))
            cf = (p.get("codice_fiscale") or "").replace(" ", "").upper()
            if cf:
                for problema in cfm.coerenza(cf, p.get("cognome", ""), p.get("nome", ""),
                                             tx.parse_data(p.get("data_nascita")), p.get("sesso", "")):
                    out.append(_msg(ERRORE, nome_ruolo, f"{chi}: {problema}."))
            sca = tx.parse_data(p.get("doc_scadenza"))
            if sca and sca < firma:
                out.append(_msg(ERRORE, nome_ruolo, f"{chi}: il documento d'identità è scaduto il {tx.formato_data(sca)}."))
            elif sca and rogito and sca < rogito:
                out.append(_msg(ATTENZIONE, nome_ruolo,
                                f"{chi}: il documento scade il {tx.formato_data(sca)}, prima del rogito ({tx.formato_data(rogito)})."))
            for k, fonte in (p.get("_fonti") or {}).items():
                if "verificare" in fonte or "da verificare" in fonte:
                    etichetta = next((e for c, e, _ in campi if c == k), k)
                    out.append(_msg(INFO, nome_ruolo, f"{chi}: {etichetta} letto da {fonte}."))
            for a in p.get("_avvisi") or []:
                out.append(_msg(ATTENZIONE, nome_ruolo, f"{chi}: {a}"))
            if p.get("_residenza_atto") and p.get("res_comune"):
                out.append(_msg(INFO, nome_ruolo,
                                f"{chi}: nell'atto di provenienza la residenza era «{p['_residenza_atto']}», "
                                f"dal documento risulta «{p.get('res_indirizzo', '')}, {p.get('res_comune', '')}»: "
                                "verificare la residenza attuale."))

    # i venditori devono essere gli intestatari dell'atto di provenienza
    atto = estratti.get("atto") or {}
    intestatari = [c["nominativo"].upper() for c in atto.get("intestatari", [])]
    if intestatari:
        venditori = [f"{p.get('cognome', '')} {p.get('nome', '')}".upper().strip() for p in dati["venditori"]]
        for i in intestatari:
            if not any(difflib.SequenceMatcher(None, i, v).ratio() > 0.85 or
                       difflib.SequenceMatcher(None, i, " ".join(reversed(v.split()))).ratio() > 0.85 for v in venditori):
                out.append(_msg(ERRORE, "Venditori",
                                f"{i} risulta proprietario nell'atto di provenienza ma non è tra i venditori."))
        for v in venditori:
            if v and not any(difflib.SequenceMatcher(None, i, v).ratio() > 0.85 for i in intestatari):
                out.append(_msg(ATTENZIONE, "Venditori",
                                f"{v} non risulta tra gli acquirenti dell'atto di provenienza: verificare la titolarità."))
    elif atto:
        out.append(_msg(ATTENZIONE, "Venditori",
                        "Non è stato possibile individuare nell'atto chi è diventato proprietario: verificare i venditori."))

    # ---------------------------------------------------------------- immobile
    imm = dati["immobile"]
    for k, etichetta in (("comune", "il comune"), ("indirizzo", "l'indirizzo"), ("descrizione", "la descrizione")):
        if not str(imm.get(k, "")).strip():
            out.append(_msg(ATTENZIONE, "Immobile", f"Manca {etichetta} dell'immobile."))
    if not imm.get("unita"):
        out.append(_msg(ERRORE, "Immobile", "Nessuna unità catastale inserita."))
    for u in imm.get("unita", []):
        mancano = [e for k, e in modello_dati.CAMPI_UNITA if k != "sezione" and not str(u.get(k, "")).strip()]
        if mancano:
            out.append(_msg(ATTENZIONE, "Immobile", f"Unità sub. {u.get('sub') or '?'}: mancano {', '.join(mancano)}."))
    planimetrie = estratti.get("planimetrie") or []
    subs = {str(u.get("sub")) for u in imm.get("unita", [])}
    for pl in planimetrie:
        if pl.get("sub") and pl["sub"] not in subs:
            out.append(_msg(ATTENZIONE, "Planimetrie",
                            f"La planimetria a pag. {pl['pagina']} di {pl['file']} sembra riferita al sub. {pl['sub']}, "
                            "che non è tra le unità dell'immobile (lettura OCR: verificare)."))
        elif not pl.get("sub"):
            out.append(_msg(INFO, "Planimetrie",
                            f"Non è stato possibile leggere il subalterno della planimetria a pag. {pl['pagina']} di {pl['file']}."))
    plan_sub = {pl.get("sub") for pl in planimetrie if pl.get("sub")}
    for s in subs:
        if planimetrie and s and s not in plan_sub:
            out.append(_msg(ATTENZIONE, "Planimetrie", f"Non è stata trovata la planimetria del sub. {s}."))
    try:
        n_plan = int(imm.get("n_planimetrie") or 0)
    except ValueError:
        n_plan = 0
    if n_plan and imm.get("unita") and n_plan != len(imm["unita"]):
        out.append(_msg(INFO, "Planimetrie",
                        f"{n_plan} planimetrie allegate per {len(imm['unita'])} unità catastali: verificare."))

    # -------------------------------------------------------------- provenienza
    prov = dati["provenienza"]
    for k, etichetta in (("notaio", "il notaio"), ("data", "la data"), ("repertorio", "il numero di repertorio"),
                         ("trascrizione", "gli estremi di trascrizione")):
        if not str(prov.get(k, "")).strip():
            out.append(_msg(ATTENZIONE, "Provenienza", f"Mancano {etichetta} dell'atto di provenienza."
                            if k == "trascrizione" else f"Manca {etichetta} dell'atto di provenienza."))

    # ------------------------------------------------------------------ accordi
    acc = dati["accordi"]
    prezzo = tx.parse_importo(acc.get("prezzo"))
    if prezzo is None:
        out.append(_msg(ERRORE, "Accordi", "Manca il prezzo."))
    versamenti = [v for v in acc.get("versamenti", []) if str(v.get("importo", "")).strip()]
    totale = sum((tx.parse_importo(v["importo"]) or Decimal(0) for v in versamenti), Decimal(0))
    if prezzo is not None and totale > prezzo:
        out.append(_msg(ERRORE, "Accordi", "La somma di caparre e acconti supera il prezzo."))
    elif prezzo is not None:
        out.append(_msg(INFO, "Accordi", f"Saldo al rogito calcolato: {tx.euro_completo(prezzo - totale)}."))
    for v in versamenti:
        if tx.parse_importo(v["importo"]) is None:
            out.append(_msg(ERRORE, "Accordi", f"Importo non valido: «{v['importo']}»."))
        scad = tx.parse_data(v.get("scadenza"))
        if v.get("stato") == "da_versare" and not scad and not v.get("testo_libero"):
            out.append(_msg(INFO, "Accordi", f"Versamento di {tx.euro_completo(v['importo'])}: nessuna scadenza, "
                                             "verrà indicato «alla firma del presente contratto»."))
        if scad and rogito and scad > rogito:
            out.append(_msg(ERRORE, "Accordi", f"Il versamento del {tx.formato_data(scad)} è successivo al rogito."))
    if not rogito:
        out.append(_msg(ERRORE, "Accordi", "Manca la data entro cui stipulare il rogito."))
    elif rogito < firma:
        out.append(_msg(ERRORE, "Accordi", "La data del rogito è precedente alla data di firma."))
    if acc.get("mutuo_condizione") and not (acc.get("mutuo_importo") and acc.get("mutuo_entro")):
        out.append(_msg(ATTENZIONE, "Accordi", "Condizione mutuo attiva ma mancano importo o termine."))

    # -------------------------------------------------------------- urbanistica
    urb = dati["urbanistica"]
    if not str(urb.get("dichiarazione", "")).strip() and not urb.get("ante_67"):
        out.append(_msg(ATTENZIONE, "Urbanistica", "Mancano gli estremi dei titoli edilizi."))
    if urb.get("agibilita_presente") and not str(urb.get("agibilita", "")).strip():
        out.append(_msg(ATTENZIONE, "Urbanistica", "Mancano gli estremi del certificato di agibilità."))
    if not str(dati["ape"].get("classe", "")).strip():
        out.append(_msg(INFO, "APE", "Classe energetica non indicata: il contratto prevede l'obbligo di consegna "
                                     "dell'APE entro il rogito."))

    ordine = {ERRORE: 0, ATTENZIONE: 1, INFO: 2}
    out.sort(key=lambda m: ordine[m["livello"]])
    return out


def testo_riepilogo(controlli: list[dict]) -> str:
    righe = []
    simbolo = {ERRORE: "[ERRORE]", ATTENZIONE: "[ATTENZIONE]", INFO: "[INFO]"}
    for c in controlli:
        righe.append(f"{simbolo[c['livello']]} {c['sezione']}: {c['testo']}")
    return "\n".join(righe) or "Nessun problema rilevato."
