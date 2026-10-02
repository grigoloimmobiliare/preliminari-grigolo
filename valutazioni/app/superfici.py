"""Superfici dalla planimetria per una valutazione: calcolo, scelta delle stanze, riepilogo.

Primo passo della valutazione: si carica la planimetria catastale, il programma trova le
zone chiuse e ne misura la superficie calpestabile; si spuntano le stanze dell'immobile e
si dà loro il nome; la superficie commerciale è quella calpestabile aumentata della
percentuale indicata nelle impostazioni (15% se non cambiata). I valori vanno poi riportati
a mano nell'Excel della stima.
"""

from __future__ import annotations

import pickle
import re
from datetime import datetime
from pathlib import Path

from . import archivio, letture as lt, planimetria as pl
from .excel import fmt_numero

MAGGIORAZIONE_PREDEFINITA = 15.0

# stanze che sono pertinenze: niente maggiorazione, vanno tra le pertinenze dell'Excel
# (dove si applica la loro quota, es. balcone al 30%)
PERTINENZE = re.compile(r"balcon|terrazz|loggi|cantin|garage|box|autorimess|posto auto|soffitt|sottotett|"
                        r"magazzin|deposit|stenditoi|giardin|cortil|portic|lastrico", re.I)


def e_pertinenza(nome: str) -> bool:
    return bool(PERTINENZE.search(nome or ""))


def maggiorazione() -> float:
    try:
        return float(str(archivio.impostazioni().get("maggiorazione", MAGGIORAZIONE_PREDEFINITA)).replace(",", "."))
    except ValueError:
        return MAGGIORAZIONE_PREDEFINITA


def cartella_lavoro(v: archivio.Valutazione) -> Path:
    """Dati intermedi della planimetria (non toccati dalla generazione del Word)."""
    return v.cartella / ".planimetria"


def _cache(v: archivio.Valutazione) -> Path:
    return cartella_lavoro(v) / "planimetria.pkl"


def calcola(v: archivio.Valutazione, file: Path, porta_max: float = 1.1) -> dict:
    """Trova le zone della planimetria e prepara l'immagine numerata. Ritorna lo stato salvato."""
    r = pl.analizza(file, porta_max)
    letture = lt.leggi(r["img"])
    for i, t in enumerate(letture, 1):
        t["sigla"] = f"L{i}"
    cartella_lavoro(v).mkdir(parents=True, exist_ok=True)
    with open(_cache(v), "wb") as f:
        pickle.dump({"img": r["img"], "dpi": r["dpi"], "vani": r["vani"], "file": file.name,
                     "scala_barra": r["scala_barra"], "letture": letture}, f)
    stato = v.carica()
    precedente = stato.get("planimetria", {})
    stato["planimetria"] = {
        "file": file.name, "calcolata": datetime.now().isoformat(timespec="seconds"), "porta_max": porta_max,
        "scala": precedente.get("scala", "automatica") if precedente.get("file") == file.name else "automatica",
        "scelti": [], "nomi": {},
        # superfici scritte sulla planimetria: proposte già spuntate, nomi e mq correggibili
        "letture": [{"sigla": t["sigla"], "nome": t["nome"], "mq": t["mq"], "scelta": True} for t in letture],
    }
    v.salva(stato)
    aggiorna(v)
    return v.carica()["planimetria"]


def _carica_cache(v: archivio.Valutazione) -> dict | None:
    try:
        with open(_cache(v), "rb") as f:
            return pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError):
        return None


def scale(dati: dict) -> dict[str, float]:
    """Scale tra cui scegliere: quella della barra del PDF (se c'è) e quelle consuete."""
    valori = {pl.BARRA: dati["scala_barra"]} if dati.get("scala_barra") else {}
    return valori | pl.SCALE


def aggiorna(v: archivio.Valutazione, scelti: list[int] | None = None, nomi: dict | None = None,
             scala: str | None = None, letture: dict | None = None) -> dict | None:
    """letture: {sigla: {"scelta": bool, "nome": str, "mq": float}} dalle superfici scritte."""
    """Applica scelta delle stanze, nomi e scala; rigenera immagini e riepilogo."""
    stato = v.carica()
    p = stato.get("planimetria")
    dati = _carica_cache(v)
    if not p or not dati:
        return None
    if scelti is not None:
        p["scelti"] = sorted(set(scelti))
    if nomi is not None:
        p["nomi"] = {str(k): val.strip() for k, val in nomi.items() if val and val.strip()}
    if scala is not None:
        p["scala"] = scala
    p.setdefault("letture", [])
    for t in p["letture"]:
        nuovo = (letture or {}).get(t["sigla"])
        if letture is not None:
            t["scelta"] = bool(nuovo and nuovo.get("scelta"))
        if nuovo:
            t["nome"] = (nuovo.get("nome") or t["nome"]).strip()
            if nuovo.get("mq") is not None:
                t["mq"] = nuovo["mq"]
    vani = dati["vani"]
    dpi = dati["dpi"]
    valori = scale(dati)
    scelti_v = [x for x in vani if x.numero in p["scelti"]]
    proposta = pl.BARRA if pl.BARRA in valori else pl.scala_proposta(scelti_v or vani, dpi)
    scala_usata = p.get("scala", "automatica")
    if scala_usata not in valori:
        scala_usata = proposta
    px_m = pl.px_per_metro(dpi, valori[scala_usata])
    perc = maggiorazione()
    p.update({"scala_usata": scala_usata, "scala_proposta": proposta, "maggiorazione": perc,
              "scala_numero": f"1:{valori[scala_usata]:.0f}", "scale": list(valori)})
    p["zone"] = [{"n": x.numero, "mq": round(x.mq(px_m), 2), "lati": [round(l, 2) for l in x.lati(px_m)]}
                 for x in vani]
    righe, pertinenze = [], []
    voci = [(t["sigla"], t["nome"] or t["sigla"], float(t["mq"])) for t in p["letture"] if t.get("scelta")]
    voci += [(x.numero, p["nomi"].get(str(x.numero)) or f"Vano {x.numero}", x.mq(px_m)) for x in scelti_v]
    for n, nome, netta in voci:
        if e_pertinenza(nome):
            pertinenze.append({"n": n, "nome": nome, "calpestabile": round(netta, 2)})
        else:
            righe.append({"n": n, "nome": nome, "calpestabile": round(netta, 2),
                          "commerciale": round(netta * (1 + perc / 100), 2)})
    p["righe"] = righe
    p["pertinenze"] = pertinenze
    p["tot_calpestabile"] = round(sum(r["calpestabile"] for r in righe), 2)
    p["tot_commerciale"] = round(sum(r["commerciale"] for r in righe), 2)
    stato["planimetria"] = p
    v.salva(stato)

    # immagini: tutte le zone (per scegliere) e solo le stanze scelte, con i nomi
    tutte = dati.get("letture", [])
    lette = [t for t in tutte if any(x["sigla"] == t["sigla"] and x.get("scelta") for x in p["letture"])]
    pl.immagine_numerata(dati["img"], vani, px_m, cartella_lavoro(v) / "zone.png", letture=tutte)
    if righe or pertinenze:
        nomi_n = {x.numero: (p["nomi"].get(str(x.numero)) or "") for x in scelti_v}
        pl.immagine_numerata(dati["img"], vani, px_m, v.cartella / "Superfici - planimetria.png",
                             scelti={x.numero for x in scelti_v}, nomi=nomi_n, letture=lette)
        (v.cartella / "Superfici - planimetria.txt").write_text(riepilogo_testo(p), encoding="utf-8")
    return p


def riepilogo_testo(p: dict) -> str:
    misurate = any(isinstance(r["n"], int) for r in p["righe"] + p.get("pertinenze", []))
    scala = f" (scala {p['scala_usata']}, {p['scala_numero']})" if misurate else ""
    righe = [f"Superfici dalla planimetria {p['file']}{scala}",
             f"Superficie commerciale = calpestabile + {fmt_numero(p['maggiorazione'], 1)}%", "",
             f"{'Stanza':30s} {'Calpestabile':>14s} {'Commerciale':>14s}"]
    for r in p["righe"]:
        righe.append(f"{r['nome']:30s} {fmt_numero(r['calpestabile']):>11s} mq {fmt_numero(r['commerciale']):>11s} mq")
    righe += ["", f"{'Totale':30s} {fmt_numero(p['tot_calpestabile']):>11s} mq {fmt_numero(p['tot_commerciale']):>11s} mq"]
    if any(isinstance(r["n"], str) for r in p["righe"] + p.get("pertinenze", [])):
        righe += ["", "Le superfici calpestabili L1, L2... sono quelle scritte sulla planimetria."]
    if p.get("pertinenze"):
        righe += ["", "Pertinenze (senza maggiorazione: nell'Excel tra le pertinenze, con la loro quota)"]
        for r in p["pertinenze"]:
            righe.append(f"{r['nome']:30s} {fmt_numero(r['calpestabile']):>11s} mq")
    return "\n".join(righe) + "\n"
