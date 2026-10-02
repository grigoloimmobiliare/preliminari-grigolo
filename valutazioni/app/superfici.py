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
PERTINENZE = re.compile(r"balcon|poggiol|terrazz|loggi|cantin|garage|box|autorimess|posto auto|soffitt|sottotett|"
                        r"magazzin|deposit|sgomber|stenditoi|giardin|cortil|portic|lastrico|sottoscala|"
                        r"centrale termica|\bc\.\s*t\b|vano contatori|accessori", re.I)


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


RIFERIMENTO = "misura di riferimento"


def _px_m_riferimento(p: dict) -> float | None:
    """Pixel per metro del file, dalla misura di riferimento (due punti e la loro distanza reale)."""
    r = (p or {}).get("riferimento")
    if not r or not r.get("metri"):
        return None
    (x0, y0), (x1, y1) = r["punti"]
    d = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return d / r["metri"] if d > 0 else None


def calcola(v: archivio.Valutazione, file: Path, porta_max: float = 1.1) -> dict:
    """Trova le zone della planimetria e prepara l'immagine numerata. Ritorna lo stato salvato.

    Ricalcolando la stessa planimetria restano la misura di riferimento e le stanze disegnate a
    mano; con la misura di riferimento anche la ricerca delle zone usa la scala giusta."""
    stato = v.carica()
    precedente = stato.get("planimetria", {})
    stesso = precedente.get("file") == file.name
    r = pl.analizza(file, porta_max, _px_m_riferimento(precedente) if stesso else None)
    letture = lt.leggi(r["img"])
    for i, t in enumerate(letture, 1):
        t["sigla"] = f"L{i}"
    cartella_lavoro(v).mkdir(parents=True, exist_ok=True)
    with open(_cache(v), "wb") as f:
        pickle.dump({"img": r["img"], "dpi": r["dpi"], "vani": r["vani"], "file": file.name,
                     "scala_barra": r["scala_barra"], "letture": letture, "fattore": r["fattore"]}, f)
    vista = pl.vista(r["img"], cartella_lavoro(v) / "pagina.png")
    stato = v.carica()
    stato["planimetria"] = {
        "file": file.name, "calcolata": datetime.now().isoformat(timespec="seconds"), "porta_max": porta_max,
        "scala": precedente.get("scala", "automatica") if stesso else "automatica",
        "scelti": [], "nomi": {},
        # superfici scritte sulla planimetria: proposte già spuntate, nomi e mq correggibili
        "letture": [{"sigla": t["sigla"], "nome": t["nome"], "mq": t["mq"], "scelta": True} for t in letture],
        # misura a mano: coordinate in pixel del file; "vista" = pixel della pagina.png per pixel del file
        "vista": vista * r["fattore"],
        "riferimento": precedente.get("riferimento") if stesso else None,
        "manuali": precedente.get("manuali", []) if stesso else [],
    }
    v.salva(stato)
    aggiorna(v)
    return v.carica()["planimetria"]


def imposta_riferimento(v: archivio.Valutazione, punti: list, metri: float) -> dict | None:
    """Scala da due punti della planimetria e dalla loro distanza reale in metri."""
    stato = v.carica()
    p = stato.get("planimetria")
    if not p:
        return None
    p["riferimento"] = {"punti": [[float(a) for a in q] for q in punti], "metri": float(metri)}
    p["scala"] = RIFERIMENTO
    v.salva(stato)
    return aggiorna(v)


def aggiungi_stanza(v: archivio.Valutazione, punti: list, nome: str = "") -> dict | None:
    """Stanza disegnata a mano (angoli in pixel del file)."""
    stato = v.carica()
    p = stato.get("planimetria")
    if not p or len(punti) < 3:
        return None
    usate = {int(m["sigla"][1:]) for m in p.get("manuali", [])}
    n = next(i for i in range(1, len(usate) + 2) if i not in usate)
    p.setdefault("manuali", []).append({"sigla": f"M{n}", "nome": nome.strip() or f"Stanza {n}",
                                        "punti": [[float(a) for a in q] for q in punti], "scelta": True})
    v.salva(stato)
    return aggiorna(v)


def togli_stanza(v: archivio.Valutazione, sigla: str) -> dict | None:
    stato = v.carica()
    p = stato.get("planimetria")
    if not p:
        return None
    p["manuali"] = [m for m in p.get("manuali", []) if m["sigla"] != sigla]
    v.salva(stato)
    return aggiorna(v)


def _carica_cache(v: archivio.Valutazione) -> dict | None:
    try:
        with open(_cache(v), "rb") as f:
            return pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError):
        return None


def scale(dati: dict, p: dict | None = None) -> dict[str, float]:
    """Scale tra cui scegliere: quella della misura di riferimento e quella della barra del PDF
    (se ci sono) e quelle consuete."""
    valori = {}
    px_m = _px_m_riferimento(p)
    if px_m:
        valori[RIFERIMENTO] = pl.scala_da_px_m(dati["dpi"], px_m * dati.get("fattore", 1.0))
    if dati.get("scala_barra"):
        valori[pl.BARRA] = dati["scala_barra"]
    return valori | pl.SCALE


def aggiorna(v: archivio.Valutazione, scelti: list[int] | None = None, nomi: dict | None = None,
             scala: str | None = None, letture: dict | None = None, manuali: dict | None = None) -> dict | None:
    """Applica scelta delle stanze, nomi e scala; rigenera immagini e riepilogo.

    letture: {sigla: {"scelta", "nome", "mq"}} per le superfici scritte sulla planimetria;
    manuali: {sigla: {"scelta", "nome"}} per le stanze disegnate a mano."""
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
    p.setdefault("manuali", [])
    for m in p["manuali"]:
        nuovo = (manuali or {}).get(m["sigla"])
        if manuali is not None:
            m["scelta"] = bool(nuovo and nuovo.get("scelta"))
        if nuovo and (nuovo.get("nome") or "").strip():
            m["nome"] = nuovo["nome"].strip()
    vani = dati["vani"]
    dpi = dati["dpi"]
    fattore = dati.get("fattore", 1.0)
    valori = scale(dati, p)
    scelti_v = [x for x in vani if x.numero in p["scelti"]]
    proposta = next((k for k in (RIFERIMENTO, pl.BARRA) if k in valori), None) \
        or pl.scala_proposta(scelti_v or vani, dpi)
    scala_usata = p.get("scala", "automatica")
    if scala_usata not in valori:
        scala_usata = proposta
    px_m = pl.px_per_metro(dpi, valori[scala_usata])
    perc = maggiorazione()
    p.update({"scala_usata": scala_usata, "scala_proposta": proposta, "maggiorazione": perc,
              "scala_numero": (f"1:{valori[scala_usata]:.0f}" if scala_usata != RIFERIMENTO
                               else f"{_px_m_riferimento(p):.1f} pixel per metro"), "scale": list(valori)})
    p["zone"] = [{"n": x.numero, "mq": round(x.mq(px_m), 2), "lati": [round(l, 2) for l in x.lati(px_m)]}
                 for x in vani]
    righe, pertinenze = [], []
    voci = [(t["sigla"], t["nome"] or t["sigla"], float(t["mq"])) for t in p["letture"] if t.get("scelta")]
    voci += [(x.numero, p["nomi"].get(str(x.numero)) or f"Vano {x.numero}", x.mq(px_m)) for x in scelti_v]
    poligoni = []
    for m in p["manuali"]:
        punti = [[a * fattore for a in q] for q in m["punti"]]
        m["mq"] = round(pl.area_poligono(punti) / px_m ** 2, 2)
        poligoni.append({"sigla": m["sigla"], "nome": m["nome"], "punti": punti, "mq": m["mq"], "scelta": m["scelta"]})
        if m.get("scelta"):
            voci.append((m["sigla"], m["nome"], m["mq"]))
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
    rif = p.get("riferimento")
    rif_img = [[a * fattore for a in q] for q in rif["punti"]] if rif else None
    pl.immagine_numerata(dati["img"], vani, px_m, cartella_lavoro(v) / "zone.png", letture=tutte,
                         poligoni=poligoni, riferimento=rif_img)
    if righe or pertinenze:
        nomi_n = {x.numero: (p["nomi"].get(str(x.numero)) or "") for x in scelti_v}
        pl.immagine_numerata(dati["img"], vani, px_m, v.cartella / "Superfici - planimetria.png",
                             scelti={x.numero for x in scelti_v}, nomi=nomi_n, letture=lette,
                             poligoni=[q for q in poligoni if q["scelta"]])
        (v.cartella / "Superfici - planimetria.txt").write_text(riepilogo_testo(p), encoding="utf-8")
    return p


def riepilogo_testo(p: dict) -> str:
    larg = max([30] + [len(r["nome"]) + 1 for r in p["righe"] + p.get("pertinenze", [])])
    misurate = any(not str(r["n"]).startswith("L") for r in p["righe"] + p.get("pertinenze", []))
    scala = f" (scala {p['scala_usata']}, {p['scala_numero']})" if misurate else ""
    righe = [f"Superfici dalla planimetria {p['file']}{scala}",
             f"Superficie commerciale = calpestabile + {fmt_numero(p['maggiorazione'], 1)}%", "",
             f"{'Stanza':{larg}s} {'Calpestabile':>14s} {'Commerciale':>14s}"]
    for r in p["righe"]:
        righe.append(f"{r['nome']:{larg}s} {fmt_numero(r['calpestabile']):>11s} mq {fmt_numero(r['commerciale']):>11s} mq")
    righe += ["", f"{'Totale':{larg}s} {fmt_numero(p['tot_calpestabile']):>11s} mq {fmt_numero(p['tot_commerciale']):>11s} mq"]
    if any(str(r["n"]).startswith("M") for r in p["righe"] + p.get("pertinenze", [])):
        righe += ["", "Le superfici M1, M2... sono stanze disegnate a mano sulla planimetria."]
    if any(str(r["n"]).startswith("L") for r in p["righe"] + p.get("pertinenze", [])):
        righe += ["", "Le superfici calpestabili L1, L2... sono quelle scritte sulla planimetria."]
    if p.get("pertinenze"):
        righe += ["", "Pertinenze (senza maggiorazione: nell'Excel tra le pertinenze, con la loro quota)"]
        for r in p["pertinenze"]:
            righe.append(f"{r['nome']:{larg}s} {fmt_numero(r['calpestabile']):>11s} mq")
    return "\n".join(righe) + "\n"
