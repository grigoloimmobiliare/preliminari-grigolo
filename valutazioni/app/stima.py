"""Foglio di calcolo della stima dentro il programma (al posto dell'Excel compilato a mano).

I dati si scrivono nella pagina della valutazione (punto 3), con i calcoli in tempo reale; salvando,
il programma crea l'Excel della stima nella cartella 01_Excel ("Stima (programma).xlsx"), con le
stesse etichette e formule del modello: il resto (Word, totali, vetustà...) funziona come con un
Excel compilato a mano, e l'Excel si può aprire, controllare e anche modificare.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from . import archivio
from .excel import numero

NOME_FILE = "Stima (programma).xlsx"
AUTORE = "Valutazioni Grigolo"          # nelle proprietà dell'Excel: riconosce i file creati qui

VANI = ["Ingresso", "Soggiorno", "Cucina", "Camera 1", "Camera 2", "Camera 3", "Bagno 1", "Bagno 2", "Ripostiglio"]
PERTINENZE = [("Garage", 1.0, False), ("Cantina", 1 / 3, False), ("Magazzino", 1 / 3, False),
              ("Terrazzi/Poggioli", 1 / 3, False), ("Giardino", 0.1, False), ("Posto auto", None, True),
              ("Box auto", None, True)]


def vuota(par: dict | None = None) -> dict:
    """Stima di partenza: righe del modello, comune e zona OMI dal punto 1, data di oggi."""
    par = par or {}
    return {
        "zona": "", "tipologia": "", "indirizzo": "", "cliente": "", "firma": "",
        "zona_omi": par.get("zona", ""), "comune": par.get("comune_nome") or par.get("comune", ""),
        "data": datetime.now().strftime("%Y-%m-%d"),
        "valore_mq": None, "valore_mq_garage": None, "vetusta": 0.0,
        "vani": [{"nome": n, "mq": None, "perc": 1.0} for n in VANI],
        "pertinenze": [{"nome": n, "mq": None, "perc": p, "a_corpo": c, "valore": None} for n, p, c in PERTINENZE],
        "valore_commerciale": None, "unicita": [], "criticita": [],
    }


def da_form(form) -> dict:
    """Stima dai campi della pagina (numeri all'italiana: 2.300,50)."""
    def testo(k):
        return str(form.get(k, "") or "").strip()

    def num(k):
        return numero(testo(k).replace("%", "")) if testo(k) else None

    def righe(prefisso):
        out, i = [], 0
        while f"{prefisso}_nome_{i}" in form:
            out.append({"nome": testo(f"{prefisso}_nome_{i}"), "mq": num(f"{prefisso}_mq_{i}"),
                        "perc": (num(f"{prefisso}_perc_{i}") or 0) / 100 if testo(f"{prefisso}_perc_{i}") else None,
                        "a_corpo": f"{prefisso}_corpo_{i}" in form, "valore": num(f"{prefisso}_valore_{i}")})
            i += 1
        return [r for r in out if r["nome"]]

    def elenco(k):
        return [x.strip() for x in testo(k).splitlines() if x.strip()]

    return {
        **{k: testo(k) for k in ("zona", "tipologia", "indirizzo", "cliente", "firma", "zona_omi", "comune", "data")},
        "valore_mq": num("valore_mq"), "valore_mq_garage": num("valore_mq_garage"), "vetusta": num("vetusta") or 0.0,
        "vani": [{k: r[k] for k in ("nome", "mq", "perc")} for r in righe("vano")],
        "pertinenze": righe("pert"),
        "valore_commerciale": num("valore_commerciale"),
        "unicita": elenco("unicita"), "criticita": elenco("criticita"),
    }


def _garage(nome: str) -> bool:
    n = nome.upper()
    return any(k in n for k in ("GARAGE", "BOX", "AUTO"))


def calcola(s: dict) -> dict:
    """Gli stessi conti dell'Excel (servono anche alla pagina per i totali)."""
    vmq, vgar = s.get("valore_mq") or 0, s.get("valore_mq_garage") or s.get("valore_mq") or 0
    vani = [(r["mq"] or 0) * (1 if r.get("perc") is None else r["perc"]) * vmq for r in s["vani"]]
    pert = []
    for r in s["pertinenze"]:
        if r.get("a_corpo"):
            pert.append(r.get("valore") or 0)
        else:
            pert.append((r["mq"] or 0) * (1 if r.get("perc") is None else r["perc"]) * (vgar if _garage(r["nome"]) else vmq))
    nuovo = sum(vani) + sum(pert)
    coeff = 1 - (s.get("vetusta") or 0) / 100
    attuale = nuovo * coeff
    commerciale = s.get("valore_commerciale") or attuale * 1.10
    return {"vani": vani, "pertinenze": pert, "tot_mq": sum(r["mq"] or 0 for r in s["vani"]),
            "tot_vani": sum(vani), "nuovo": nuovo, "vetusta": nuovo - attuale, "attuale": attuale,
            "commerciale": commerciale}


# ---------------------------------------------------------------- Excel

_SOTTILE = Side(style="thin", color="999999")
_BORDO = Border(bottom=_SOTTILE)
_GRASSETTO = Font(bold=True)


def scrivi_excel(s: dict, dest: Path) -> Path:
    """Excel della stima con le etichette e le formule del modello."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Foglio2"
    wb.properties.creator = AUTORE
    for col, larg in zip("ABCDEFGH", (24, 12, 20, 12, 16, 12, 12, 16)):
        ws.column_dimensions[col].width = larg

    def cella(rif, valore, grassetto=False, formato=None, bordo=False):
        c = ws[rif]
        c.value = valore
        if grassetto:
            c.font = _GRASSETTO
        if formato:
            c.number_format = formato
        if bordo:
            c.border = _BORDO
        return c

    ws.merge_cells("A1:H2")
    cella("A1", "STIMA COMMERCIALE DI IMMOBILE RESIDENZIALE", True).alignment = Alignment(horizontal="center",
                                                                                         vertical="center")
    ws["A1"].font = Font(bold=True, size=14)
    for r, (e1, k1, e2, k2) in {3: ("ZONA:", "zona", "TIPOLOGIA:", "tipologia"),
                                4: ("INDIRIZZO:", "indirizzo", "CLIENTE:", "cliente")}.items():
        cella(f"A{r}", e1, True)
        cella(f"B{r}", s.get(k1) or None, bordo=True)
        ws.merge_cells(f"B{r}:D{r}")
        cella(f"E{r}", e2, True)
        cella(f"F{r}", s.get(k2) or None, bordo=True)
        ws.merge_cells(f"F{r}:H{r}")
    cella("A5", "ZONA OMI", True)
    cella("B5", s.get("zona_omi") or None, bordo=True)
    cella("C5", "COMUNE:", True)
    cella("D5", s.get("comune") or None, bordo=True)
    cella("F5", "DATA:", True)
    try:
        data = datetime.strptime(s.get("data") or "", "%Y-%m-%d")
    except ValueError:
        data = None
    cella("G5", data, formato="DD/MM/YYYY", bordo=True)
    cella("A6", "Valore al mq")
    cella("B6", s.get("valore_mq"), formato="#,##0", bordo=True)
    cella("C6", "Valore al mq GARAGE")
    cella("D6", s.get("valore_mq_garage") or s.get("valore_mq"), formato="#,##0", bordo=True)
    cella("E6", "FIRMA:", True)
    cella("F6", s.get("firma") or None, bordo=True)
    ws.merge_cells("F6:H6")
    cella("A7", "Indice di vetusta")
    # indice come nel modello: 0,7 = il valore attuale è il 70% del nuovo (vetustà del 30%); 1 = non applicata
    cella("B7", round(1 - (s.get("vetusta") or 0) / 100, 6), formato="0.00", bordo=True)

    for col, t in zip("BCDE", ("Mq", "Percentuale", "Valore", "Valore")):
        cella(f"{col}9", t, True)
    r = 10
    righe_vani = []
    for v in s["vani"]:
        cella(f"A{r}", v["nome"].upper())
        cella(f"B{r}", v["mq"], formato="#,##0.00")
        cella(f"C{r}", 1 if v.get("perc") is None else v["perc"], formato="0%")
        cella(f"D{r}", "=$B$6", formato="#,##0")
        cella(f"E{r}", f"=B{r}*C{r}*D{r}", formato="#,##0.00")
        righe_vani.append(r)
        r += 1
    cella(f"A{r}", "TOT VALORE TIPOLOGIA", True)
    cella(f"E{r}", f"=SUM(E{righe_vani[0]}:E{righe_vani[-1]})" if righe_vani else 0, True, "#,##0.00")
    r += 1
    righe_pert = []
    for p in s["pertinenze"]:
        cella(f"A{r}", p["nome"])
        if p.get("a_corpo"):
            cella(f"B{r}", "A CORPO")
            cella(f"E{r}", p.get("valore"), formato="#,##0.00")
        else:
            cella(f"B{r}", p["mq"], formato="#,##0.00")
            cella(f"C{r}", 1 if p.get("perc") is None else p["perc"], formato="0%")
            cella(f"D{r}", "=$D$6" if _garage(p["nome"]) else "=$B$6", formato="#,##0")
            cella(f"E{r}", f"=B{r}*C{r}*D{r}", formato="#,##0.00")
        righe_pert.append(r)
        r += 1
    r += 1
    cella(f"A{r}", "TOT MQ TIPOLOGIA", True)
    cella(f"B{r}", f"=SUM(B{righe_vani[0]}:B{righe_vani[-1]})" if righe_vani else 0, True, "#,##0.00")
    r += 1
    somma = "+".join(f"E{x}" for x in righe_vani + righe_pert) or "0"
    r_nuovo, r_vet, r_att, r_comm = r, r + 1, r + 2, r + 4
    cella(f"C{r_nuovo}", "Valore a Nuovo", True)
    cella(f"E{r_nuovo}", f"={somma}", True, "#,##0.00")
    cella(f"C{r_vet}", "Vetustà")
    cella(f"E{r_vet}", f"=E{r_nuovo}-E{r_att}", formato="#,##0.00")
    cella(f"C{r_att}", "Valore attuale", True)
    cella(f"E{r_att}", f"=E{r_nuovo}*B7", True, "#,##0.00")
    cella(f"B{r_comm}", "Valore commerciale", True)
    cella(f"D{r_comm}", s.get("valore_commerciale"), True, "#,##0.00")
    ws[f"D{r_comm}"].fill = PatternFill("solid", fgColor="FFF2CC")
    r = r_comm + 3
    for etichetta, chiave in (("Principi di unicità", "unicita"), ("Criticità", "criticita")):
        cella(f"A{r}", etichetta, True)
        voci = s.get(chiave) or []
        for i, testo in enumerate(voci or [None]):
            cella(f"C{r + i}", testo)
        r += max(len(voci), 1) + 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)
    return dest


def salva(v: archivio.Valutazione, s: dict) -> Path:
    """Salva la stima nella valutazione e crea l'Excel nella cartella 01_Excel."""
    stato = v.carica()
    stato["stima"] = deepcopy(s)
    stato["stima"]["salvata"] = datetime.now().isoformat(timespec="seconds")
    v.salva(stato)
    return scrivi_excel(s, v.cartella_categoria("excel") / NOME_FILE)


def creato_dal_programma(percorso: Path) -> bool:
    try:
        return openpyxl.load_workbook(percorso, read_only=True).properties.creator == AUTORE
    except Exception:  # noqa: BLE001
        return False
