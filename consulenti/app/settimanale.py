"""Andamento settimanale dei consulenti rispetto alla settimana precedente e ai benchmark del mese.

- I **report personali** hanno una riga per giorno: i valori si sommano per settimana di calendario
  (da lunedì a domenica, la prima e l'ultima del mese possono essere parziali).
- I **benchmark** si caricano a inizio mese in un file Excel con una riga per consulente e una per
  l'ufficio (pagina *Benchmark*). Il benchmark mensile si divide tra le settimane in proporzione ai
  giorni lavorativi (da lunedì a sabato, esclusi i festivi nazionali).
- Il file prodotto ha un foglio per consulente, il foglio UFFICIO e il foglio SINTESI. Benchmark
  settimanali, scostamenti e variazioni sono formule: correggendo un valore si aggiorna tutto.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config
from .report_mensile import ErroreReport, _mese_spostato, _norm, descrizione_mese, \
    leggi_report_personale_mesi, mese_da_nome, nome_foglio

CARTELLA_BENCHMARK = config.DATI / "benchmark"

# (chiave, descrizione, chiavi del report personale da sommare, intestazioni accettate nel file benchmark).
# La prima intestazione è quella usata nel modello da compilare.
INDICATORI = [
    ("contatti", "Contatti", ["contatti"], ["CONTATTI"]),
    ("notizie", "Notizie", ["notizie"], ["NOTIZIE"]),
    ("profilazioni", "Profilazioni (richieste chiamate)", ["rich_nuove", "rich_vecchie"],
     ["PROFILAZIONI", "PROFILAZIONE", "RICHIESTE", "CHIAMATE"]),
    ("fissate", "Richieste fissate", ["rich_nuove_fissate", "rich_vecchie_fissate"],
     ["FISSATE", "RICHIESTE FISSATE", "APPUNTAMENTI FISSATI"]),
    ("acquisizioni", "Acquisizione - 1° appuntamento", ["acq_1"],
     ["1 APPUNTAMENTO", "I APPUNTAMENTO", "1° APPUNTAMENTO", "PRIMO APPUNTAMENTO", "ACQUISIZIONI",
      "ACQUISIZIONE", "PRIMI ACQUISIZIONE", "ACQ I APP"]),
    ("consegne", "Acquisizione - 2° appuntamento (consegne)", ["acq_2"],
     ["2 APPUNTAMENTO", "II APPUNTAMENTO", "2° APPUNTAMENTO", "SECONDO APPUNTAMENTO", "CONSEGNE", "CONSEGNA",
      "SECONDI", "ACQ II APP"]),
    ("esclusive", "Incarichi in esclusiva", ["esclusive"],
     ["INCARICO", "INCARICHI", "ESCLUSIVE", "EXCL", "ESCLUSIVA"]),
    ("gestioni", "Gestioni", ["gestioni"], ["GESTIONI", "GESTIONE"]),
    ("primi", "Vendita - I appuntamento (informativi)", ["vend_1"],
     ["I APP", "1 APP", "PRIMI", "INFORMATIVI", "PRIMI VENDITA", "VEND I APP"]),
    ("visite", "Vendita - II appuntamento (visite)", ["vend_2"],
     ["II APP", "2 APP", "VISITE", "VISITA", "VEND II APP"]),
    ("proposte", "Proposte", ["proposte"], ["PROPOSTE", "PROPOSTA"]),
    ("preliminari", "Preliminari", ["preliminari"], ["PRELIMINARI", "PRELIMINARE", "VENDITE"]),
    ("mutui", "Mutui", ["mutui"], ["MUTUI", "MUTUO"]),
    ("mandati", "Mandati (incarichi in esclusiva e non)", ["mandati"],
     ["MANDATI", "MANDATTI", "MANDATO", "INCARICHI TOTALI"]),
    ("budget", "Budget (€)", ["budget"], ["BUDGET"]),
]
EURO = {"budget"}  # indicatori in euro
INTESTAZIONI = {_norm(s): chiave for chiave, _, _, sinonimi in INDICATORI for s in sinonimi}
# Colonne del file benchmark che i report personali non misurano: vengono lette e mostrate, ma non confrontate.
NON_MISURATI: dict[str, str] = {}
NOMI_UFFICIO = {"UFFICIO", "TOTALE", "TOT", "TOTALE UFFICIO", "FILIALE", "AGENZIA", "COMPLESSIVO"}
CONSULENTI_PREDEFINITI = ["LAURA", "ELEONORA", "ALISSA", "SOFIA", "GIUSEPPE", "ROSSELLA",
                          "GIANLUCA", "TATIANA", "MATTIA"]

VOCI = ["Fatto", "Benchmark", "Scostamento vs benchmark", "Scostamento % vs benchmark",
        "Variazione vs settimana prec.", "Variazione % vs settimana prec."]


# ---------------------------------------------------------------- calendario

def _pasqua(anno: int) -> date:
    a, b, c = anno % 19, anno // 100, anno % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    return date(anno, mese, (h + l - 7 * m + 114) % 31 + 1)


def festivi(anno: int) -> set[date]:
    fissi = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)]
    return {date(anno, m, g) for m, g in fissi} | {_pasqua(anno) + timedelta(days=1)}


def lavorativo(g: date) -> bool:
    return g.weekday() < 6 and g not in festivi(g.year)  # da lunedì a sabato


@dataclass
class Settimana:
    inizio: date
    fine: date

    @property
    def giorni_lavorativi(self) -> int:
        return sum(lavorativo(self.inizio + timedelta(days=i)) for i in range((self.fine - self.inizio).days + 1))

    def etichetta(self) -> str:
        return f"{self.inizio:%d/%m} - {self.fine:%d/%m}"


def settimane(anno: int, mese: int) -> list[Settimana]:
    """Settimane da lunedì a domenica dentro il mese. Un pezzo senza giorni lavorativi (es. una
    domenica 1) si unisce alla settimana vicina."""
    primo = date(anno, mese, 1)
    ultimo = date(anno + (mese == 12), mese % 12 + 1, 1) - timedelta(days=1)
    elenco, g = [], primo
    while g <= ultimo:
        fine = min(g + timedelta(days=6 - g.weekday()), ultimo)
        elenco.append(Settimana(g, fine))
        g = fine + timedelta(days=1)
    if len(elenco) > 1 and elenco[0].giorni_lavorativi == 0:
        pezzo = elenco.pop(0)
        elenco[0].inizio = pezzo.inizio
    if len(elenco) > 1 and elenco[-1].giorni_lavorativi == 0:
        pezzo = elenco.pop()
        elenco[-1].fine = pezzo.fine
    return elenco


# ---------------------------------------------------------------- benchmark

@dataclass
class Benchmark:
    consulenti: dict[str, dict[str, float]]
    ufficio: dict[str, float] | None
    indicatori: list[str]
    avvisi: list[str] = field(default_factory=list)
    non_misurati: dict[str, dict[str, float]] = field(default_factory=dict)  # MANDATI -> {nome: valore}

    def ufficio_di(self, chiave: str):
        """Benchmark dell'ufficio: dalla riga/riquadro dell'ufficio, altrimenti None."""
        return (self.ufficio or {}).get(chiave)


def _valore(v):
    """Numero di una cella del benchmark: 30000, "30.000", "2,5", "€ 30.000"."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    if not isinstance(v, str):
        return None
    t = re.sub(r"[€\s]", "", v)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):  # separatore delle migliaia
        t = t.replace(".", "")
    try:
        n = float(t.replace(",", "."))
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def leggi_benchmark(contenuto: bytes, anno: int | None = None, mese: int | None = None) -> Benchmark:
    try:
        wb = load_workbook(io.BytesIO(contenuto), data_only=True)
    except Exception:
        raise ErroreReport("Il file dei benchmark non è un file Excel .xlsx leggibile")
    ws = next((w for w in wb.worksheets if anno and mese_da_nome(w.title) == (anno, mese)), wb.worksheets[0])

    # Riga delle intestazioni: quella con più nomi di indicatori (CONTATTI, I APP, ...).
    migliore, riga_int = 1, None
    for r in range(1, min(ws.max_row, 40) + 1):
        trovate = sum(_norm(ws.cell(r, c).value) in INTESTAZIONI for c in range(1, ws.max_column + 1))
        if trovate > migliore:
            migliore, riga_int = trovate, r
    if riga_int is None:
        attese = ", ".join(s[0] for *_, s in INDICATORI)
        raise ErroreReport(f"Nel file dei benchmark non trovo la riga delle intestazioni ({attese})")
    colonne, altre = {}, {}
    for c in range(1, ws.max_column + 1):
        intest = _norm(ws.cell(riga_int, c).value)
        if (k := INTESTAZIONI.get(intest)) and k not in colonne.values():
            colonne[c] = k
        elif intest in NON_MISURATI:
            altre[c] = NON_MISURATI[intest]
    col_nome = next((c for c in range(1, ws.max_column + 1)
                     if _norm(ws.cell(riga_int, c).value) in {"CONSULENTE", "NOME", "CONSULENTI"}), None)
    if col_nome is None:
        col_nome = next((c for c in range(1, min(colonne) if colonne else 2)
                         if any(isinstance(ws.cell(r, c).value, str) for r in range(riga_int + 1, ws.max_row + 1))), 1)

    consulenti, ufficio, avvisi = {}, {}, []
    non_misurati: dict[str, dict[str, float]] = {}
    for r in range(riga_int + 1, ws.max_row + 1):
        nome = _norm(ws.cell(r, col_nome).value)
        if not nome:
            continue
        valori = {k: v for c, k in colonne.items() if (v := _valore(ws.cell(r, c).value)) is not None}
        extra = {k: v for c, k in altre.items() if (v := _valore(ws.cell(r, c).value)) is not None}
        if not valori and not extra:
            continue
        chi = "UFFICIO" if nome in NOMI_UFFICIO else nome
        if chi == "UFFICIO":
            ufficio.update(valori)
        else:
            consulenti[nome] = valori
        for k, v in extra.items():
            non_misurati.setdefault(k, {})[chi] = v

    # Riquadro dell'ufficio sopra la tabella, una voce per riga: "1 APPUNTAMENTO | 50".
    for r in range(1, riga_int):
        for c in range(1, ws.max_column):
            etichetta = _norm(ws.cell(r, c).value)
            k = INTESTAZIONI.get(etichetta) or NON_MISURATI.get(etichetta)
            if not k:
                continue
            v = next((x for cc in range(c + 1, min(c + 4, ws.max_column + 1))
                      if (x := _valore(ws.cell(r, cc).value)) is not None), None)
            if v is None:
                continue
            if k in NON_MISURATI.values():
                non_misurati.setdefault(k, {})["UFFICIO"] = v
            else:
                ufficio[k] = v
            break

    if not consulenti and not ufficio:
        raise ErroreReport("Nel file dei benchmark non trovo righe con i valori dei consulenti")
    indicatori = [k for k, *_ in INDICATORI if k in ufficio or any(k in v for v in consulenti.values())]
    descr = {k: d for k, d, *_ in INDICATORI}
    if not ufficio:
        avvisi.append("Nel file dei benchmark non c'è l'obiettivo dell'ufficio: uso la somma dei consulenti")
    elif mancanti := [descr[k] for k in indicatori if k not in ufficio]:
        avvisi.append("Obiettivi dell'ufficio presi dal file: " + ", ".join(descr[k] for k in indicatori if k in ufficio)
                      + ". Per gli altri (" + ", ".join(mancanti) + ") uso la somma dei consulenti.")
    if non_misurati:
        avvisi.append(", ".join(sorted(non_misurati)) + ": letti dal file, ma i report personali non li misurano, "
                      "quindi non vengono confrontati.")
    return Benchmark(consulenti, ufficio or None, indicatori, avvisi, non_misurati)


def percorso_benchmark(anno: int, mese: int) -> Path:
    return CARTELLA_BENCHMARK / f"{anno}-{mese:02d}.xlsx"


def benchmark_salvati() -> list[dict]:
    if not CARTELLA_BENCHMARK.exists():
        return []
    elenco = []
    for f in sorted(CARTELLA_BENCHMARK.glob("*.xlsx"), reverse=True):
        if m := re.fullmatch(r"(\d{4})-(\d{2})", f.stem):
            anno, mese = int(m.group(1)), int(m.group(2))
            if 1 <= mese <= 12:
                elenco.append({"anno": anno, "mese": mese, "nome": f.name,
                               "descrizione": descrizione_mese(anno, mese)})
    return elenco


def salva_benchmark(contenuto: bytes, anno: int, mese: int) -> Benchmark:
    bm = leggi_benchmark(contenuto, anno, mese)  # controlla il file prima di salvarlo
    CARTELLA_BENCHMARK.mkdir(parents=True, exist_ok=True)
    config.con_tentativi(lambda: percorso_benchmark(anno, mese).write_bytes(contenuto))
    return bm


def carica_benchmark(anno: int, mese: int) -> Benchmark | None:
    p = percorso_benchmark(anno, mese)
    return leggi_benchmark(p.read_bytes(), anno, mese) if p.exists() else None


def modello_benchmark(anno: int, mese: int) -> bytes:
    """File da compilare: una riga per consulente e la riga UFFICIO. Riprende nomi e valori
    dell'ultimo benchmark caricato, se c'è."""
    precedente = None
    for b in benchmark_salvati():
        if (b["anno"], b["mese"]) <= (anno, mese):
            try:
                precedente = carica_benchmark(b["anno"], b["mese"])
            except ErroreReport:
                precedente = None
            break
    nomi = list(precedente.consulenti) if precedente else CONSULENTI_PREDEFINITI

    wb = Workbook()
    ws = wb.active
    ws.title = nome_foglio(anno, mese)
    font, giallo = "Arial", PatternFill("solid", fgColor="FFF2CC")
    sottile = Side(style="thin", color="C9C2B5")
    bordo = Border(top=sottile, bottom=sottile, left=sottile, right=sottile)
    ws.cell(1, 1, f"BENCHMARK MENSILI - {descrizione_mese(anno, mese).upper()}").font = Font(name=font, bold=True, size=14)
    ws.cell(2, 1, "Compila le celle gialle con l'obiettivo del mese di ogni consulente e dell'ufficio. "
                  "Lascia vuoto un indicatore senza obiettivo. Puoi aggiungere o togliere consulenti.").font = \
        Font(name=font, italic=True, size=9, color="666666")
    intest = ["CONSULENTE"] + [s[0] for *_, s in INDICATORI]
    for i, h in enumerate(intest, 1):
        c = ws.cell(4, i, h)
        c.font, c.fill, c.border = Font(name=font, bold=True), PatternFill("solid", fgColor="E8DCC6"), bordo
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = 16 if i == 1 else 13
    for r, nome in enumerate(nomi + ["UFFICIO"], 5):
        ws.cell(r, 1, nome).font = Font(name=font, bold=True)
        ws.cell(r, 1).border = bordo
        valori = (precedente.ufficio if nome == "UFFICIO" else precedente.consulenti.get(nome)) if precedente else None
        for i, (k, *_) in enumerate(INDICATORI, 2):
            c = ws.cell(r, i, (valori or {}).get(k))
            c.fill, c.border, c.font = giallo, bordo, Font(name=font, color="0000FF")
            c.alignment = Alignment(horizontal="center")
    ws.row_dimensions[4].height = 30
    ws.freeze_panes = "B5"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- elaborazione

@dataclass
class Risultato:
    contenuto: bytes
    nome_file: str
    consulenti: list[dict]
    settimane: list[Settimana]
    avvisi: list[str]
    con_benchmark: bool


def _somma(giorni: dict[int, dict[str, float]], s: Settimana, chiavi: list[str]):
    tot = 0
    g = s.inizio
    while g <= s.fine:
        valori = giorni.get(g.day, {})
        tot += sum(valori.get(k, 0) for k in chiavi)
        g += timedelta(days=1)
    return int(tot) if float(tot).is_integer() else tot


def _nome_foglio_valido(nome: str, usati: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\']", " ", nome).strip()[:28] or "CONSULENTE"
    nome, i = base, 2
    while nome.upper() in usati or nome.upper() in {"UFFICIO", "SINTESI"}:
        nome, i = f"{base} {i}", i + 1
    usati.add(nome.upper())
    return nome


def elabora(personali: list[tuple[str, bytes]], anno: int, mese: int, benchmark: Benchmark | None) -> Risultato:
    if not personali:
        raise ErroreReport("Carica almeno un report personale")
    prec = _mese_spostato(anno, mese, -1)
    sett = settimane(anno, mese)
    sett_prec = settimane(*prec)[-1]
    avvisi = list(benchmark.avvisi) if benchmark else [
        f"Non c'è il benchmark di {descrizione_mese(anno, mese).lower()}: caricalo dalla pagina Benchmark. "
        "Il file contiene solo l'andamento e il confronto con la settimana precedente."]

    dati = []
    for nome_file, contenuto in personali:
        try:
            mesi = leggi_report_personale_mesi(contenuto, [prec, (anno, mese)], nome_file)
        except ErroreReport as e:
            avvisi.append(str(e))
            continue
        if (anno, mese) not in mesi:
            avvisi.append(f"{nome_file}: non c'è il foglio di {descrizione_mese(anno, mese).lower()}")
            continue
        rp = mesi[(anno, mese)]
        if any(d["consulente"] == rp.consulente for d in dati):
            avvisi.append(f"{rp.consulente}: caricato più di un report, vale l'ultimo ({nome_file})")
            dati = [d for d in dati if d["consulente"] != rp.consulente]
        avvisi.extend(rp.avvisi)
        valori = {k: [_somma(rp.giorni, s, chiavi) for s in sett] for k, _, chiavi, _ in INDICATORI}
        if prec in mesi:
            precedente = {k: _somma(mesi[prec].giorni, sett_prec, chiavi) for k, _, chiavi, _ in INDICATORI}
        else:
            precedente = None
            avvisi.append(f"{rp.consulente}: nel report non c'è {descrizione_mese(*prec).lower()}, la prima "
                          "settimana non ha il confronto con la settimana precedente")
        bm = benchmark.consulenti.get(rp.consulente) if benchmark else None
        if benchmark and bm is None:
            avvisi.append(f"{rp.consulente}: non è nel file dei benchmark")
        mancanti = [n for k, n in (("mandati", "MANDATI"), ("budget", "BUDGET"))
                     if bm and bm.get(k) is not None and k not in rp.totali]
        if mancanti:
            avvisi.append(f"{rp.consulente}: nel report di {descrizione_mese(anno, mese).lower()} manca la colonna "
                          + " e la colonna ".join(mancanti) + ", risulta 0")
        dati.append({"consulente": rp.consulente, "valori": valori, "precedente": precedente, "benchmark": bm})
    if not dati:
        raise ErroreReport("Nessun report personale utilizzabile. " + " ".join(avvisi))
    dati.sort(key=lambda d: d["consulente"])

    wb = _crea_file(dati, anno, mese, sett, sett_prec, benchmark)
    out = io.BytesIO()
    wb.save(out)
    riepilogo = [{"consulente": d["consulente"],
                  "settimane": [sum(d["valori"][k][i] for k in ("acquisizioni", "primi", "visite", "proposte"))
                                for i in range(len(sett))],
                  "benchmark": d["benchmark"] is not None} for d in dati]
    return Risultato(out.getvalue(), f"Andamento settimanale {nome_foglio(anno, mese)}.xlsx", riepilogo, sett,
                     avvisi, benchmark is not None)


# ---------------------------------------------------------------- file Excel

FONT = "Arial"
_sottile = Side(style="thin", color="C9C2B5")
BORDO = Border(top=_sottile, bottom=_sottile, left=_sottile, right=_sottile)
F_TITOLO = Font(name=FONT, bold=True, size=14, color="FFFFFF")
F_GRASSETTO = Font(name=FONT, bold=True)
F_NORMALE = Font(name=FONT)
F_INPUT = Font(name=FONT, color="0000FF")
F_NOTA = Font(name=FONT, italic=True, size=9, color="666666")
FONDO_TITOLO = PatternFill("solid", fgColor="7F6033")
FONDO_INTEST = PatternFill("solid", fgColor="E8DCC6")
FONDO_IND = PatternFill("solid", fgColor="F4EEE3")
FONDO_FATTO = PatternFill("solid", fgColor="FFFFFF")
PERC = '+0.0%;-0.0%;0.0%'
DIFF = '+0;-0;0'
CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)
VERDE = Font(name=FONT, color="1E7B34", bold=True)
ROSSO = Font(name=FONT, color="C0392B", bold=True)


def _colori(ws, intervallo: str):
    ws.conditional_formatting.add(intervallo, CellIsRule(operator="greaterThan", formula=["0"], font=VERDE))
    ws.conditional_formatting.add(intervallo, CellIsRule(operator="lessThan", formula=["0"], font=ROSSO))


def _var(nuovo: str, vecchio: str) -> str:
    return f'=IF(ISNUMBER({vecchio}),IF({vecchio}=0,IF({nuovo}=0,0,"nuovo"),({nuovo}-{vecchio})/{vecchio}),"n.d.")'


def _layout(n_sett: int):
    """Colonne e righe comuni a tutti i fogli, così il foglio UFFICIO somma le stesse celle."""
    col_prec = 3
    col_sett = list(range(4, 4 + n_sett))
    col_tot = 4 + n_sett
    righe = {}
    r = 8
    for k, *_ in INDICATORI:
        righe[k] = r  # riga "Fatto"; le altre voci seguono
        r += len(VOCI) + 1
    return col_prec, col_sett, col_tot, righe


def _foglio(wb, titolo_foglio: str, titolo: str, sett, sett_prec, anno, mese,
            fatto, precedente, benchmark_mese, nota: str):
    """Scrive un foglio. fatto/precedente/benchmark_mese: funzioni (chiave, indice) -> valore o formula."""
    ws = wb.create_sheet(titolo_foglio)
    col_prec, col_sett, col_tot, righe = _layout(len(sett))
    ultima = col_tot
    L = get_column_letter

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ultima)
    ws.cell(1, 1, titolo).font = F_TITOLO
    ws.cell(1, 1).fill = FONDO_TITOLO
    ws.row_dimensions[1].height = 24
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ultima)
    ws.cell(2, 1, nota).font = F_NOTA
    ws.cell(2, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 40

    intest = {1: "Indicatore", 2: "Voce", col_prec: f"Sett. precedente\n{sett_prec.etichetta()}",
              col_tot: f"Totale {descrizione_mese(anno, mese).lower()}"}
    for i, s in enumerate(sett):
        intest[col_sett[i]] = f"Settimana {i + 1}\n{s.etichetta()}"
    for c, t in intest.items():
        cella = ws.cell(4, c, t)
        cella.font, cella.fill, cella.alignment, cella.border = F_GRASSETTO, FONDO_INTEST, CENTRO, BORDO
    ws.row_dimensions[4].height = 32

    ws.cell(5, 2, "Giorni lavorativi (lun-sab)").font = F_NORMALE
    ws.cell(6, 2, "Quota del benchmark mensile").font = F_NORMALE
    ws.cell(5, col_prec, sett_prec.giorni_lavorativi)
    for i, s in enumerate(sett):
        c = col_sett[i]
        ws.cell(5, c, s.giorni_lavorativi)
        ws.cell(6, c, f"={L(c)}5/${L(col_tot)}$5").number_format = "0.0%"
    ws.cell(5, col_tot, f"=SUM({L(col_sett[0])}5:{L(col_sett[-1])}5)")
    ws.cell(6, col_tot, f"=SUM({L(col_sett[0])}6:{L(col_sett[-1])}6)").number_format = "0.0%"
    for r in (5, 6):
        for c in range(2, ultima + 1):
            ws.cell(r, c).border, ws.cell(r, c).alignment = BORDO, Alignment(horizontal="center")
            ws.cell(r, c).font = F_NOTA

    for k, desc, *_ in INDICATORI:
        r0 = righe[k]
        rf, rb, rs, rsp, rv, rvp = range(r0, r0 + 6)
        ws.merge_cells(start_row=r0, start_column=1, end_row=r0 + 5, end_column=1)
        cella = ws.cell(r0, 1, desc)
        cella.font, cella.fill = F_GRASSETTO, FONDO_IND
        cella.alignment = Alignment(vertical="center", wrap_text=True)
        for i, voce in enumerate(VOCI):
            ws.cell(r0 + i, 2, voce).font = F_GRASSETTO if i == 0 else F_NORMALE
        tot = L(col_tot)
        # Fatto
        v = precedente(k)
        ws.cell(rf, col_prec, v if v is not None else "n.d.")
        for i, c in enumerate(col_sett):
            ws.cell(rf, c, fatto(k, i))
        ws.cell(rf, col_tot, f"=SUM({L(col_sett[0])}{rf}:{L(col_sett[-1])}{rf})")
        # Benchmark del mese nella colonna del totale, ripartito sulle settimane con la quota
        bm = benchmark_mese(k)
        ws.cell(rb, col_tot, bm if bm is not None else "n.d.")
        if isinstance(bm, (int, float)):
            ws.cell(rb, col_tot).font = F_INPUT
        for c in col_sett + [col_tot]:
            x = L(c)
            if c != col_tot:
                ws.cell(rb, c, f'=IF(ISNUMBER(${tot}{rb}),${tot}{rb}*{x}$6,"n.d.")')
            ws.cell(rs, c, f'=IF(ISNUMBER({x}{rb}),{x}{rf}-{x}{rb},"n.d.")')
            ws.cell(rsp, c, f'=IF(ISNUMBER({x}{rb}),IF({x}{rb}=0,IF({x}{rf}=0,0,"nuovo"),'
                            f'({x}{rf}-{x}{rb})/{x}{rb}),"n.d.")')
        for c in col_sett:
            x, p = L(c), L(c - 1)
            ws.cell(rv, c, f'=IF(ISNUMBER({p}{rf}),{x}{rf}-{p}{rf},"n.d.")')
            ws.cell(rvp, c, _var(f"{x}{rf}", f"{p}{rf}"))
        # Formati
        for r in range(r0, r0 + 6):
            for c in range(2, ultima + 1):
                cella = ws.cell(r, c)
                cella.border = BORDO
                if c > 2:
                    cella.alignment = Alignment(horizontal="center")
                    if not (r == rb and c == col_tot):
                        cella.font = F_GRASSETTO if r == rf else F_NORMALE
            if r in (rf, rb) and k in EURO:
                for c in range(3, ultima + 1):
                    ws.cell(r, c).number_format = '#,##0 €'
            elif r == rb:
                for c in range(3, ultima + 1):
                    ws.cell(r, c).number_format = "0.0"
            if r in (rs, rv):
                for c in range(3, ultima + 1):
                    ws.cell(r, c).number_format = '+#,##0 €;-#,##0 €;0 €' if k in EURO else '+0.0;-0.0;0'
            if r in (rsp, rvp):
                for c in range(3, ultima + 1):
                    ws.cell(r, c).number_format = PERC
        for r in (rs, rsp, rv, rvp):
            _colori(ws, f"{L(col_prec)}{r}:{L(col_tot)}{r}")

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 30
    for c in range(3, ultima + 1):
        ws.column_dimensions[L(c)].width = 15
    ws.freeze_panes = "C5"
    return ws


def _crea_file(dati, anno, mese, sett, sett_prec, benchmark: Benchmark | None) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    mese_desc = descrizione_mese(anno, mese)
    nota = ("Settimane da lunedì a domenica. Il benchmark del mese (colonna del totale, in blu) è diviso tra le "
            "settimane in base ai giorni lavorativi, da lunedì a sabato esclusi i festivi. \"nuovo\" = prima era 0, "
            "\"n.d.\" = dato non disponibile.")
    sintesi = wb.create_sheet("SINTESI")
    usati: set[str] = set()
    fogli = []
    for d in dati:
        nome = _nome_foglio_valido(d["consulente"], usati)
        _foglio(wb, nome, f"ANDAMENTO SETTIMANALE - {d['consulente']} - {mese_desc.upper()}", sett, sett_prec,
                anno, mese,
                fatto=lambda k, i, d=d: d["valori"][k][i],
                precedente=lambda k, d=d: d["precedente"][k] if d["precedente"] else None,
                benchmark_mese=lambda k, d=d: (d["benchmark"] or {}).get(k) if d["benchmark"] else None,
                nota=nota)
        fogli.append(nome)

    col_prec, col_sett, col_tot, righe = _layout(len(sett))

    def somma(r, c):
        return "=" + "+".join(f"N('{f}'!{get_column_letter(c)}{r})" for f in fogli)

    def bm_ufficio(k):
        if not benchmark:
            return None
        if (v := benchmark.ufficio_di(k)) is not None:
            return v
        if any(k in v for v in benchmark.consulenti.values()):  # somma dei benchmark dei consulenti
            return somma(righe[k] + 1, col_tot)
        return None

    nota_uff = nota + " Il fatto dell'ufficio è la somma dei consulenti caricati (" + ", ".join(fogli) + ")."
    _foglio(wb, "UFFICIO", f"ANDAMENTO SETTIMANALE - UFFICIO - {mese_desc.upper()}", sett, sett_prec, anno, mese,
            fatto=lambda k, i: somma(righe[k], col_sett[i]),
            precedente=lambda k: somma(righe[k], col_prec) if any(d["precedente"] for d in dati) else None,
            benchmark_mese=bm_ufficio, nota=nota_uff)
    wb.move_sheet("UFFICIO", offset=-(len(wb.sheetnames) - 2))

    # SINTESI: per ogni indicatore, scostamento % dal benchmark per consulente e settimana.
    ws = sintesi
    n_col = len(sett) + (2 if benchmark else 1)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_col)
    ws.cell(1, 1, f"SINTESI {mese_desc.upper()} - SCOSTAMENTO % DAL BENCHMARK").font = F_TITOLO
    ws.cell(1, 1).fill = FONDO_TITOLO
    ws.row_dimensions[1].height = 24
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_col)
    ws.cell(2, 1, ("Verde: sopra il benchmark della settimana, rosso: sotto. I dettagli (valori, benchmark e "
                   "variazioni rispetto alla settimana precedente) sono nei fogli dei consulenti e in UFFICIO."
                   if benchmark else "Manca il benchmark del mese: qui è riportata la variazione % rispetto "
                                     "alla settimana precedente.")).font = F_NOTA
    ws.cell(2, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 40
    voce = 3 if benchmark else 5  # riga dentro il blocco: scostamento % o variazione %
    r = 4
    for k, desc, *_ in INDICATORI:
        if benchmark and not any((v or {}).get(k) for v in [benchmark.ufficio, *benchmark.consulenti.values()]):
            continue  # indicatore senza benchmark per nessuno
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=n_col)
        ws.cell(r, 1, desc).font = Font(name=FONT, bold=True, size=12, color="7F6033")
        ws.cell(r, 1).fill = FONDO_IND
        r += 1
        intest = ["Consulente"] + [f"Sett. {i + 1}\n{s.etichetta()}" for i, s in enumerate(sett)] + (["Mese"] if benchmark else [])
        for i, t in enumerate(intest, 1):
            c = ws.cell(r, i, t)
            c.font, c.fill, c.alignment, c.border = F_GRASSETTO, FONDO_INTEST, CENTRO, BORDO
        ws.row_dimensions[r].height = 30
        r += 1
        inizio = r
        for f in fogli + ["UFFICIO"]:
            ws.cell(r, 1, f).font = F_GRASSETTO
            ws.cell(r, 1).border = BORDO
            for i, c in enumerate(col_sett + ([col_tot] if benchmark else [])):
                cella = ws.cell(r, i + 2, f"='{f}'!{get_column_letter(c)}{righe[k] + voce}")
                cella.number_format, cella.alignment, cella.border, cella.font = PERC, CENTRO, BORDO, F_NORMALE
            if f == "UFFICIO":
                for c in range(1, n_col + 1):
                    ws.cell(r, c).fill = FONDO_IND
            r += 1
        _colori(ws, f"B{inizio}:{get_column_letter(n_col)}{r - 1}")
        r += 1
    ws.column_dimensions["A"].width = 18
    for c in range(2, n_col + 1):
        ws.column_dimensions[get_column_letter(c)].width = 15
    wb.move_sheet("SINTESI", offset=-wb.index(wb["SINTESI"]))
    for f in wb.worksheets:
        f.sheet_view.tabSelected = False
        # In stampa: orizzontale, tutte le settimane nella larghezza del foglio.
        f.page_setup.orientation = "landscape"
        f.page_setup.paperSize = f.PAPERSIZE_A4
        f.sheet_properties.pageSetUpPr.fitToPage = True
        f.page_setup.fitToWidth, f.page_setup.fitToHeight = 1, 0
        f.print_title_rows = "4:4"
    wb.active = 0
    wb.worksheets[0].sheet_view.tabSelected = True
    wb.calculation.fullCalcOnLoad = True
    return wb
