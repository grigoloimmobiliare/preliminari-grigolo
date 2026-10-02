"""Superfici dalla planimetria per una valutazione: calcolo, scelta delle stanze, riepilogo.

Primo passo della valutazione: si carica la planimetria catastale, il programma trova le
zone chiuse e ne misura la superficie calpestabile; si spuntano le stanze dell'immobile e
si dà loro il nome; la superficie commerciale è quella calpestabile aumentata della
percentuale indicata nelle impostazioni (15% se non cambiata). I valori vanno poi riportati
a mano nell'Excel della stima.
"""

from __future__ import annotations

import pickle
from datetime import datetime
from pathlib import Path

from . import archivio, planimetria as pl
from .excel import fmt_numero

MAGGIORAZIONE_PREDEFINITA = 15.0


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
    cartella_lavoro(v).mkdir(parents=True, exist_ok=True)
    with open(_cache(v), "wb") as f:
        pickle.dump({"img": r["img"], "dpi": r["dpi"], "vani": r["vani"], "file": file.name,
                     "scala_barra": r["scala_barra"]}, f)
    stato = v.carica()
    precedente = stato.get("planimetria", {})
    stato["planimetria"] = {
        "file": file.name, "calcolata": datetime.now().isoformat(timespec="seconds"), "porta_max": porta_max,
        "scala": precedente.get("scala", "automatica") if precedente.get("file") == file.name else "automatica",
        "scelti": [], "nomi": {},
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
             scala: str | None = None) -> dict | None:
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
    righe = []
    for x in scelti_v:
        nome = p["nomi"].get(str(x.numero)) or f"Vano {x.numero}"
        netta = x.mq(px_m)
        righe.append({"n": x.numero, "nome": nome, "calpestabile": round(netta, 2),
                      "commerciale": round(netta * (1 + perc / 100), 2)})
    p["righe"] = righe
    p["tot_calpestabile"] = round(sum(r["calpestabile"] for r in righe), 2)
    p["tot_commerciale"] = round(sum(r["commerciale"] for r in righe), 2)
    stato["planimetria"] = p
    v.salva(stato)

    # immagini: tutte le zone (per scegliere) e solo le stanze scelte, con i nomi
    pl.immagine_numerata(dati["img"], vani, px_m, cartella_lavoro(v) / "zone.png")
    if scelti_v:
        nomi_n = {x.numero: (p["nomi"].get(str(x.numero)) or "") for x in scelti_v}
        pl.immagine_numerata(dati["img"], vani, px_m, v.cartella / "Superfici - planimetria.png",
                             scelti={x.numero for x in scelti_v}, nomi=nomi_n)
        (v.cartella / "Superfici - planimetria.txt").write_text(riepilogo_testo(p), encoding="utf-8")
    return p


def riepilogo_testo(p: dict) -> str:
    righe = [f"Superfici dalla planimetria {p['file']} (scala {p['scala_usata']}, {p['scala_numero']})",
             f"Superficie commerciale = calpestabile + {fmt_numero(p['maggiorazione'], 1)}%", "",
             f"{'Stanza':30s} {'Calpestabile':>14s} {'Commerciale':>14s}"]
    for r in p["righe"]:
        righe.append(f"{r['nome']:30s} {fmt_numero(r['calpestabile']):>11s} mq {fmt_numero(r['commerciale']):>11s} mq")
    righe += ["", f"{'Totale':30s} {fmt_numero(p['tot_calpestabile']):>11s} mq {fmt_numero(p['tot_commerciale']):>11s} mq"]
    return "\n".join(righe) + "\n"
