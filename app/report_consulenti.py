"""Report mensile della filiale compilato dai report personali dei consulenti.

Il report personale di ogni consulente (es. ``REPORT_TATIANA_MENSILE_2026.xlsx``) ha un foglio
per mese con una riga per giorno. Il programma somma le colonne del mese scelto e scrive i
totali nella riga del consulente del report mensile della filiale
(es. ``mensile_Analisi_Filiale_GRIGOLO_IMM_26.xlsx``), nel foglio del mese (``ott 26``):
se il foglio non c'è viene creato copiando l'ultimo mese presente.

Viene poi aggiunto un foglio ``CONFRONTO`` con, per l'ufficio e per ogni consulente, il valore
del mese, quello del mese precedente e dello stesso mese dell'anno prima, le variazioni
percentuali e il progressivo da inizio anno. Tutto il confronto è fatto con formule che puntano
ai fogli dei mesi, quindi le correzioni fatte a mano nel foglio del mese si riflettono da sole.

I fogli vengono letti cercando le intestazioni (CONTATTI, I APP, PRIMO, ...) e non le
posizioni fisse, così il programma regge colonne o righe aggiunte.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

MESI = ["GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO",
        "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE"]
# Abbreviazioni usate nei nomi dei fogli del report mensile ("sett 26", "ott 26").
ABBREVIAZIONI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "sett", "ott", "nov", "dic"]

# Totale del report personale -> colonna del report mensile, come (intestazione, occorrenza).
# L'occorrenza distingue le intestazioni ripetute: "I APP" compare prima in ACQUISIZIONE e poi
# in VENDITA, "FISSATE" prima per le richieste nuove e poi per le vecchie.
DESTINAZIONI = {
    "contatti": ("CONTATTI", 0),
    "notizie": ("NOTIZIE", 0),
    "acq_1": ("I APP", 0),
    "acq_2": ("II APP", 0),
    "esclusive": ("INCARICO", 0),
    "gestioni": ("GESTIONE", 0),
    "rich_nuove": ("NUOVE", 0),
    "rich_nuove_fissate": ("FISSATE", 0),
    "rich_vecchie": ("VECCHIE", 0),
    "rich_vecchie_fissate": ("FISSATE", 1),
    "vend_1": ("I APP", 1),
    "vend_2": ("II APP", 1),
    "proposte": ("PROPOSTE", 0),
    "preliminari": ("VEND. ALTRI", 0),
    "mutui": ("FISSATI", 0),
}

# Indicatori del foglio CONFRONTO: (descrizione, intestazione, occorrenza).
INDICATORI = [
    ("Contatti", "CONTATTI", 0),
    ("Notizie", "NOTIZIE", 0),
    ("Acquisizione - I appuntamento", "I APP", 0),
    ("Acquisizione - II appuntamento", "II APP", 0),
    ("Acquisizione - incarichi", "INCARICO", 0),
    ("Gestioni", "GESTIONE", 0),
    ("Richieste assegnate", "ASSEGNATE", 0),
    ("Richieste nuove", "NUOVE", 0),
    ("Richieste nuove fissate", "FISSATE", 0),
    ("Richieste vecchie", "VECCHIE", 0),
    ("Richieste vecchie fissate", "FISSATE", 1),
    ("Vendita - I appuntamento", "I APP", 1),
    ("Vendita - II appuntamento", "II APP", 1),
    ("Proposte", "PROPOSTE", 0),
    ("Vendite subentro", "VEND. SUB", 0),
    ("Vendite altri", "VEND. ALTRI", 0),
    ("Vendite proprie", "VEND. PROP.", 0),
    ("Vendite I.E.", "VENDITA IE", 0),
    ("Mutui fissati", "FISSATI", 0),
    ("Mutui incarico", "INCARICO", 1),
    ("Mutui erogati", "EROGATO", 0),
]
DESCRIZIONI = {(intest, n): desc for desc, intest, n in INDICATORI}
# Indicatori del foglio VARIAZIONI (tabella compatta consulenti x indicatori).
INDICATORI_SINTESI = ["Contatti", "Notizie", "Acquisizione - I appuntamento", "Acquisizione - incarichi",
                      "Richieste nuove", "Richieste vecchie", "Vendita - I appuntamento",
                      "Vendita - II appuntamento", "Proposte", "Vendite altri"]

FOGLIO_CONFRONTO = "CONFRONTO"
FOGLIO_VARIAZIONI = "VARIAZIONI"


class ErroreReport(ValueError):
    """Errore da mostrare all'utente così com'è."""


# ---------------------------------------------------------------- utilità

def _norm(v) -> str:
    """Testo maiuscolo senza accenti e spazi doppi, per confrontare intestazioni e nomi."""
    if v is None:
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def mese_da_nome(nome: str) -> tuple[int, int] | None:
    """(anno, mese) dal nome di un foglio: "ott 26", "SETT 25", "OTTOBRE_26", "GIUGNO_2026"."""
    s = _norm(nome)
    m = re.match(r"([A-Z]+)[\s_\-.]*(\d{2}|\d{4})\b", s)
    if not m:
        return None
    parola, anno = m.group(1), int(m.group(2))
    for i, mese in enumerate(MESI):
        if len(parola) >= 3 and mese.startswith(parola[:3]) and (len(parola) <= 4 or mese.startswith(parola)):
            return (2000 + anno if anno < 100 else anno), i + 1
    return None


def nome_foglio(anno: int, mese: int) -> str:
    return f"{ABBREVIAZIONI[mese - 1]} {anno % 100:02d}"


def descrizione_mese(anno: int, mese: int) -> str:
    return f"{MESI[mese - 1].capitalize()} {anno}"


def _mese_spostato(anno: int, mese: int, delta: int) -> tuple[int, int]:
    n = anno * 12 + mese - 1 + delta
    return n // 12, n % 12 + 1


def _numero(v) -> tuple[float, bool]:
    """Valore numerico di una cella del report personale e se era un testo da interpretare.

    Un testo che inizia con un numero vale quel numero ("1 villa dei Cedri" = 1), un altro testo
    non vuoto vale 1 (il consulente ha annotato l'attività invece di contarla).
    """
    if v is None or isinstance(v, bool):
        return 0, False
    if isinstance(v, (int, float)):
        return v, False
    s = str(v).strip()
    if not s or s.startswith("="):
        return 0, False
    m = re.match(r"(\d+(?:[.,]\d+)?)", s)
    if m:
        return float(m.group(1).replace(",", ".")), True
    return 1, True


def _intero(v: float):
    return int(v) if float(v).is_integer() else v


class _Celle:
    """Lettura di un foglio con le celle unite che restituiscono il valore della prima cella."""

    def __init__(self, ws: Worksheet):
        self.ws = ws
        self.unite = {}
        for r in ws.merged_cells.ranges:
            for riga in range(r.min_row, r.max_row + 1):
                for col in range(r.min_col, r.max_col + 1):
                    self.unite[(riga, col)] = (r.min_row, r.min_col)

    def __call__(self, riga: int, col: int):
        riga, col = self.unite.get((riga, col), (riga, col))
        return self.ws.cell(riga, col).value


# ---------------------------------------------------------------- report personale

@dataclass
class ReportPersonale:
    consulente: str
    foglio: str
    totali: dict[str, float]
    proposte: list[dict]
    avvisi: list[str] = field(default_factory=list)
    giorni: dict[int, dict[str, float]] = field(default_factory=dict)  # giorno del mese -> valori


# Colonna dei mandati (tutti gli incarichi, in esclusiva e non) del report personale.
MANDATI = {"MANDATI", "MANDATO", "MANDATTI", "INCARICHI TOTALI", "TOTALE INCARICHI"}


def _chiave_personale(gruppo: str, sotto: str, voce: str) -> str | None:
    if {gruppo, sotto, voce} & MANDATI:
        return "mandati"
    if gruppo == "CONTATTI":
        return "contatti"
    if gruppo == "NOTIZIE":
        return "notizie"
    if gruppo == "RICHIESTE":
        if voce == "CHIAMATE":
            return {"NUOVE": "rich_nuove", "VECCHIE": "rich_vecchie"}.get(sotto)
        if voce == "FISSATE":
            return {"NUOVE": "rich_nuove_fissate", "VECCHIE": "rich_vecchie_fissate"}.get(sotto)
        return None  # MESSAGGI: non c'è una colonna corrispondente nel report mensile
    if gruppo == "APPUNTAMENTI":
        if sotto == "ACQUISIZIONE":
            return {"PRIMO": "acq_1", "SECONDO": "acq_2"}.get(voce)
        if sotto == "VENDITA":
            return {"INFORMATIVO": "vend_1", "VISITA": "vend_2"}.get(voce)
        # Le colonne RIF PROP / RIF ESCL / RIFA MAND / RIF PREL hanno i riferimenti e non si sommano.
        return {"PROPOSTE": "proposte", "EXCL": "esclusive", "ESCLUSIVE": "esclusive",
                "PRELIMINARI": "preliminari", "MUTUI": "mutui", "MUTUO": "mutui",
                "GESTIONE": "gestioni", "GESTIONI": "gestioni",
                "BUDGET": "budget", "BUDGET FATTO": "budget", "FATTURATO": "budget"}.get(sotto)
    return None


def _foglio_del_mese(wb, anno: int, mese: int) -> Worksheet | None:
    trovati = [ws for ws in wb.worksheets if mese_da_nome(ws.title) == (anno, mese)]
    if not trovati:  # fogli senza anno nel nome ("OTTOBRE"): vale il mese
        trovati = [ws for ws in wb.worksheets if _norm(ws.title) == MESI[mese - 1]]
    return trovati[-1] if trovati else None


def mesi_disponibili(contenuto: bytes) -> list[tuple[int, int]]:
    wb = load_workbook(io.BytesIO(contenuto), read_only=True)
    return sorted({m for ws in wb.worksheets if (m := mese_da_nome(ws.title))})


def _apri_report(contenuto: bytes, nome_file: str):
    try:
        return load_workbook(io.BytesIO(contenuto), data_only=True)
    except Exception:
        raise ErroreReport(f"{nome_file}: non è un file Excel .xlsx leggibile")


def leggi_report_personale(contenuto: bytes, anno: int, mese: int, nome_file: str = "", wb=None) -> ReportPersonale:
    wb = wb or _apri_report(contenuto, nome_file)
    ws = _foglio_del_mese(wb, anno, mese)
    if ws is None:
        raise ErroreReport(f"{nome_file}: non c'è il foglio di {descrizione_mese(anno, mese).lower()} "
                           f"(fogli presenti: {', '.join(wb.sheetnames)})")
    return _leggi_foglio(ws, nome_file)


def leggi_report_personale_mesi(contenuto: bytes, mesi: list[tuple[int, int]], nome_file: str = "") -> dict:
    """I mesi richiesti presenti nel report personale: {(anno, mese): ReportPersonale}."""
    wb = _apri_report(contenuto, nome_file)
    trovati = {}
    for anno, mese in mesi:
        if _foglio_del_mese(wb, anno, mese) is not None:
            trovati[(anno, mese)] = leggi_report_personale(contenuto, anno, mese, nome_file, wb)
    return trovati


def _leggi_foglio(ws: Worksheet, nome_file: str) -> ReportPersonale:
    cella = _Celle(ws)
    avvisi = []

    # Nome del consulente: la cella dopo "CONSULENTE", altrimenti dal nome del file.
    consulente = ""
    for riga in ws.iter_rows(min_row=1, max_row=4):
        for c in riga:
            if _norm(c.value) == "CONSULENTE":
                for col in range(c.column + 1, c.column + 6):
                    if (v := _norm(cella(c.row, col))) and v != "CONSULENTE":
                        consulente = v
                        break
        if consulente:
            break
    if not consulente:
        parole = [p for p in re.split(r"[\W_]+", _norm(Path(nome_file).stem))
                  if p and p not in {"REPORT", "MENSILE", "PERSONALE"} and not p.isdigit()]
        consulente = parole[0] if parole else ""
    if not consulente:
        raise ErroreReport(f"{nome_file}: non trovo il nome del consulente (cella CONSULENTE)")

    # Riga dei gruppi: quella con CONTATTI e NOTIZIE.
    riga_gruppi = None
    for r in range(1, 10):
        valori = {_norm(cella(r, c)) for c in range(1, 40)}
        if "CONTATTI" in valori and "NOTIZIE" in valori:
            riga_gruppi = r
            break
    if riga_gruppi is None:
        raise ErroreReport(f"{nome_file}, foglio {ws.title}: non trovo le intestazioni CONTATTI / NOTIZIE")

    colonne: dict[int, str] = {}
    for col in range(1, ws.max_column + 1):
        gruppo, sotto, voce = (_norm(cella(riga_gruppi + i, col)) for i in range(3))
        if not gruppo and not ({sotto, voce} & MANDATI):  # una colonna MANDATI può stare fuori dai gruppi
            continue
        chiave = _chiave_personale(gruppo, sotto, voce)
        if chiave:
            colonne[col] = chiave

    # Righe dei giorni: dalla prima dopo le intestazioni fino al riepilogo in fondo (MARKETING / PROF).
    prima = riga_gruppi + 3
    fine = ws.max_row + 1
    for r in range(prima, ws.max_row + 1):
        if any(_norm(ws.cell(r, c).value) in {"MARKETING", "GESTIONALE", "PROF", "FISS"} for c in colonne):
            fine = r
            break

    totali = {k: 0 for k in [*DESTINAZIONI, *colonne.values()]}
    giorni: dict[int, dict[str, float]] = {}
    giorno = None
    for r in range(prima, fine):
        g = ws.cell(r, 1).value
        if isinstance(g, (int, float)) and not isinstance(g, bool) and 1 <= g <= 31 and float(g).is_integer():
            giorno = int(g)
        valori_riga = {}
        for col, chiave in colonne.items():
            v = ws.cell(r, col).value
            n, da_testo = _numero(v)
            if not n:
                continue
            totali[chiave] += n
            valori_riga[chiave] = valori_riga.get(chiave, 0) + n
            if da_testo:
                avvisi.append(f"{consulente}: nella cella {ws.cell(r, col).coordinate} del foglio {ws.title} "
                              f"c'è il testo \"{str(v).strip()}\", contato come {_intero(n)}")
        if valori_riga:
            if giorno is None:
                avvisi.append(f"{consulente}: la riga {r} del foglio {ws.title} non ha il giorno, contata nel primo giorno")
            elif ws.cell(r, 1).value is None:
                avvisi.append(f"{consulente}: la riga {r} del foglio {ws.title} non ha il giorno, "
                              f"contata nel giorno {giorno}")
            giorno_riga = giorno or 1
            del_giorno = giorni.setdefault(giorno_riga, {})
            for k, v in valori_riga.items():
                del_giorno[k] = del_giorno.get(k, 0) + v
    totali = {k: _intero(v) for k, v in totali.items()}

    # Tabella delle proposte (PROPOSTA / RIF / NOME / OFFERTA / ESITO).
    proposte = []
    for riga in ws.iter_rows():
        for c in riga:
            if _norm(c.value) == "RIF" and c.column > 1:
                intest = {_norm(ws.cell(c.row, k).value): k for k in range(c.column - 1, c.column + 5)}
                for r in range(c.row + 1, ws.max_row + 1):
                    rif = ws.cell(r, c.column).value
                    nome = ws.cell(r, intest.get("NOME", c.column + 1)).value
                    if rif is None and nome is None:
                        continue
                    proposte.append({
                        "rif": str(rif).strip() if rif is not None else "",
                        "nome": str(nome).strip() if nome is not None else "",
                        "offerta": ws.cell(r, intest.get("OFFERTA", c.column + 2)).value,
                        "esito": str(ws.cell(r, intest.get("ESITO", c.column + 3)).value or "").strip(),
                    })
                break
        else:
            continue
        break

    return ReportPersonale(consulente, ws.title, totali, proposte, avvisi, giorni)


# ---------------------------------------------------------------- report mensile

@dataclass
class FoglioMensile:
    ws: Worksheet
    riga_intestazioni: int
    colonne: dict[tuple[str, int], int]   # (intestazione, occorrenza) -> colonna
    righe: dict[str, int]                 # consulente -> riga
    righe_libere: list[int]               # righe consulente senza nome
    prima_riga: int
    ultima_riga: int                      # ultima riga dei consulenti (prima di MKTG / TOT)
    riga_tot: int | None


def analizza_foglio_mensile(ws: Worksheet) -> FoglioMensile | None:
    riga_int = None
    for r in range(1, 10):
        valori = [_norm(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
        if "CONTATTI" in valori and "I APP" in valori:
            riga_int = r
            break
    if riga_int is None:
        return None
    colonne, conta = {}, {}
    for c in range(2, ws.max_column + 1):
        v = _norm(ws.cell(riga_int, c).value)
        if v:
            n = conta.get(v, 0)
            conta[v] = n + 1
            colonne[(v, n)] = c
    righe, libere, ultima, tot = {}, [], riga_int, None
    for r in range(riga_int + 1, ws.max_row + 1):
        nome = _norm(ws.cell(r, 1).value)
        if nome in {"MKTG", "TOT", "TOTALE", "OBIETTIVO"}:
            if nome in {"TOT", "TOTALE"}:
                tot = r
            else:
                for r2 in range(r + 1, min(r + 6, ws.max_row + 1)):
                    if _norm(ws.cell(r2, 1).value) in {"TOT", "TOTALE"}:
                        tot = r2
                        break
            break
        ultima = r
        if nome:
            righe.setdefault(nome, r)
        else:
            libere.append(r)
    return FoglioMensile(ws, riga_int, colonne, righe, libere, riga_int + 1, ultima, tot)


def _fogli_mensili(wb) -> dict[tuple[int, int], FoglioMensile]:
    fogli = {}
    for ws in wb.worksheets:
        m = mese_da_nome(ws.title)
        if m and (f := analizza_foglio_mensile(ws)):
            fogli[m] = f  # se un mese compare due volte vale l'ultimo foglio
    return fogli


def _svuota_dati_mese(f: FoglioMensile):
    """Nel foglio appena copiato dal mese precedente toglie i numeri del mese (non obiettivi e formule)."""
    ws = f.ws
    ultima_col = max(f.colonne.values())
    for r in range(f.prima_riga, f.ultima_riga + 1):
        for c in range(2, ultima_col + 1):
            cella = ws.cell(r, c)
            if isinstance(cella.value, str) and cella.value.startswith("="):
                continue
            if c in f.colonne.values():
                cella.value = None
    # Tabella marketing e "fatte" sotto i totali: i valori del mese si azzerano, gli obiettivi restano.
    da_svuotare = {"INVESTIM", "RICHIESTE", "ESCL FATTE", "ACQ FATTE", "VENDITE FATTE", "EXCL", "VEND"}
    inizio = (f.riga_tot or f.ultima_riga) + 3
    for r in range(inizio, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            if _norm(ws.cell(r, c).value) in da_svuotare:
                for r2 in range(r + 1, ws.max_row + 1):
                    cella = ws.cell(r2, c)
                    if isinstance(cella.value, (int, float)) and not isinstance(cella.value, bool):
                        cella.value = 0


def _copia_foglio(wb, origine: FoglioMensile, titolo: str) -> FoglioMensile:
    nuovo = wb.copy_worksheet(origine.ws)
    nuovo.title = titolo
    nuovo.sheet_view.zoomScale = origine.ws.sheet_view.zoomScale
    nuovo.freeze_panes = origine.ws.freeze_panes
    # Il nuovo mese va subito dopo quello da cui è copiato.
    wb.move_sheet(nuovo, offset=wb.index(origine.ws) + 1 - wb.index(nuovo))
    f = analizza_foglio_mensile(nuovo)
    _svuota_dati_mese(f)
    return f


# ---------------------------------------------------------------- elaborazione

@dataclass
class Risultato:
    contenuto: bytes
    nome_file: str
    foglio: str
    foglio_creato: bool
    consulenti: list[dict]
    avvisi: list[str]


def elabora(mensile: bytes, nome_mensile: str, personali: list[tuple[str, bytes]], anno: int, mese: int) -> Risultato:
    try:
        wb = load_workbook(io.BytesIO(mensile))
    except Exception:
        raise ErroreReport("Il report mensile non è un file Excel .xlsx leggibile")
    if not personali:
        raise ErroreReport("Carica almeno un report personale")

    report, avvisi = [], []
    for nome, dati in personali:
        try:
            rp = leggi_report_personale(dati, anno, mese, nome)
        except ErroreReport as e:
            avvisi.append(str(e))
            continue
        if any(r.consulente == rp.consulente for r in report):
            avvisi.append(f"{rp.consulente}: caricato più di un report, vale l'ultimo ({nome})")
            report = [r for r in report if r.consulente != rp.consulente]
        report.append(rp)
    if not report:
        raise ErroreReport("Nessun report personale utilizzabile. " + " ".join(avvisi))

    fogli = _fogli_mensili(wb)
    if not fogli:
        raise ErroreReport("Nel report mensile non trovo fogli dei mesi con le intestazioni CONTATTI / I APP")
    creato = False
    if (anno, mese) in fogli:
        f = fogli[(anno, mese)]
    else:
        precedenti = [m for m in fogli if m < (anno, mese)] or list(fogli)
        modello = fogli[max(precedenti)]
        titolo = nome_foglio(anno, mese)
        if titolo in wb.sheetnames:
            raise ErroreReport(f"Il foglio \"{titolo}\" esiste già ma non ha la struttura del report mensile")
        f = _copia_foglio(wb, modello, titolo)
        fogli[(anno, mese)] = f
        creato = True

    giallo = PatternFill("solid", fgColor="FFF2CC")
    riepilogo = []
    for rp in report:
        riga = f.righe.get(rp.consulente)
        if riga is None:
            if not f.righe_libere:
                avvisi.append(f"{rp.consulente}: nel foglio {f.ws.title} non c'è la riga del consulente "
                              f"e non ci sono righe libere. Aggiungi una riga col nome e rielabora.")
                continue
            riga = f.righe_libere.pop(0)
            f.ws.cell(riga, 1, rp.consulente)
            f.righe[rp.consulente] = riga
            avvisi.append(f"{rp.consulente}: aggiunto nella riga {riga} del foglio {f.ws.title}, che era vuota")
        valori = {}
        for chiave, (intest, n) in DESTINAZIONI.items():
            col = f.colonne.get((intest, n))
            if col is None:
                if rp.totali.get(chiave):
                    avvisi.append(f"{rp.consulente}: il foglio {f.ws.title} non ha la colonna {intest} "
                                  f"({rp.totali[chiave]} non riportati)")
                continue
            f.ws.cell(riga, col).value = rp.totali[chiave]
            valori[DESCRIZIONI.get((intest, n), intest)] = rp.totali[chiave]
        rif = [p["rif"] or p["nome"] for p in rp.proposte]
        accettate = [p["rif"] or p["nome"] for p in rp.proposte if _norm(p["esito"]).startswith("ACCETTAT")]
        if (col := f.colonne.get(("RIF PROPOSTA", 0))) and rif:
            f.ws.cell(riga, col).value = "/".join(rif)
        if (col := f.colonne.get(("ACCETTATA", 0))) and accettate:
            f.ws.cell(riga, col).value = "/".join(accettate)
        if (col := f.colonne.get(("ASSEGNATE", 0))) and f.ws.cell(riga, col).value is None:
            f.ws.cell(riga, col).fill = giallo
            f.ws.cell(riga, col).comment = Comment(
                "Le richieste assegnate non sono nel report personale: inseriscile a mano.", "Report consulenti")
        avvisi.extend(rp.avvisi)
        riepilogo.append({"consulente": rp.consulente, "foglio": rp.foglio, "riga": riga,
                          "valori": valori, "proposte": rif, "accettate": accettate})

    crea_confronto(wb, fogli, anno, mese)
    wb.calculation.fullCalcOnLoad = True  # Excel ricalcola tutte le formule all'apertura
    out = io.BytesIO()
    wb.save(out)
    stem = Path(nome_mensile).stem or "report_mensile"
    return Risultato(out.getvalue(), f"{stem} - {nome_foglio(anno, mese)}.xlsx", f.ws.title, creato, riepilogo, avvisi)


# ---------------------------------------------------------------- confronto

def _rif(f: FoglioMensile, col: int, riga: int) -> str:
    return f"'{f.ws.title}'!{get_column_letter(col)}{riga}"


def _formula_valore(f: FoglioMensile | None, intest: str, n: int, consulente: str | None) -> str | None:
    """Formula che legge un indicatore da un foglio mensile: un consulente o tutto l'ufficio."""
    if f is None or (col := f.colonne.get((intest, n))) is None:
        return None
    if consulente is None:
        lettera = get_column_letter(col)
        return f"=SUM('{f.ws.title}'!{lettera}{f.prima_riga}:{lettera}{f.ultima_riga})"
    riga = f.righe.get(consulente)
    return f"=N({_rif(f, col, riga)})" if riga else None


def _formula_progressivo(fogli: list[FoglioMensile], intest: str, n: int, consulente: str | None) -> str | None:
    parti = []
    for f in fogli:
        v = _formula_valore(f, intest, n, consulente)
        if v:
            parti.append(v[1:])
    return "=" + "+".join(parti) if parti else None


def _variazione(nuovo: str, vecchio: str) -> str:
    return f'=IF(ISNUMBER({vecchio}),IF({vecchio}=0,IF({nuovo}=0,0,"nuovo"),({nuovo}-{vecchio})/{vecchio}),"n.d.")'


def crea_confronto(wb, fogli: dict[tuple[int, int], FoglioMensile], anno: int, mese: int):
    for nome in (FOGLIO_CONFRONTO, FOGLIO_VARIAZIONI):
        if nome in wb.sheetnames:
            del wb[nome]
    ws = wb.create_sheet(FOGLIO_CONFRONTO, 0)
    wv = wb.create_sheet(FOGLIO_VARIAZIONI, 1)
    attuale = fogli[(anno, mese)]
    prec = fogli.get(_mese_spostato(anno, mese, -1))
    anno_prec = fogli.get((anno - 1, mese))
    progressivo = [fogli[m] for m in sorted(fogli) if m[0] == anno and m[1] <= mese]

    font = "Arial"
    titolo = Font(name=font, bold=True, size=14, color="FFFFFF")
    grassetto = Font(name=font, bold=True)
    normale = Font(name=font)
    nota = Font(name=font, italic=True, size=9, color="666666")
    fondo_titolo = PatternFill("solid", fgColor="7F6033")
    fondo_intest = PatternFill("solid", fgColor="E8DCC6")
    fondo_blocco = PatternFill("solid", fgColor="F4EEE3")
    sottile = Side(style="thin", color="C9C2B5")
    bordo = Border(top=sottile, bottom=sottile, left=sottile, right=sottile)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    perc = '+0.0%;-0.0%;0.0%'

    mese_desc = descrizione_mese(anno, mese)
    desc_prec = descrizione_mese(*_mese_spostato(anno, mese, -1))
    desc_ap = descrizione_mese(anno - 1, mese)
    intest = ["Indicatore", mese_desc, desc_prec, f"Var. % su {desc_prec.lower()}",
              desc_ap, f"Var. % su {desc_ap.lower()}", f"Progressivo {anno}"]

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(intest))
    ws.cell(1, 1, f"CONFRONTO ATTIVITÀ - {mese_desc.upper()}").font = titolo
    ws.cell(1, 1).fill = fondo_titolo
    ws.row_dimensions[1].height = 24
    fonti = [f"Mese: foglio \"{attuale.ws.title}\"",
             f"mese precedente: " + (f"foglio \"{prec.ws.title}\"" if prec else "foglio non presente"),
             f"anno precedente: " + (f"foglio \"{anno_prec.ws.title}\"" if anno_prec else "foglio non presente"),
             "progressivo: " + ", ".join(f.ws.title for f in progressivo)]
    ws.cell(2, 1, "; ".join(fonti) + ". \"nuovo\" = prima era 0, \"n.d.\" = dato non disponibile.").font = nota
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(intest))

    consulenti = sorted(attuale.righe, key=lambda c: attuale.righe[c])
    celle_var = {}  # (consulente o None, descrizione indicatore) -> cella della var. % sul mese precedente
    r = 4
    for consulente in [None] + consulenti:
        etichetta = "UFFICIO (tutti i consulenti)" if consulente is None else consulente
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(intest))
        c = ws.cell(r, 1, etichetta)
        c.font = Font(name=font, bold=True, size=12, color="7F6033")
        c.fill = fondo_blocco
        r += 1
        for i, testo in enumerate(intest, 1):
            c = ws.cell(r, i, testo)
            c.font, c.fill, c.alignment, c.border = grassetto, fondo_intest, centro, bordo
        r += 1
        for desc, etich, n in INDICATORI:
            if (etich, n) not in attuale.colonne:
                continue
            valori = [
                _formula_valore(attuale, etich, n, consulente),
                _formula_valore(prec, etich, n, consulente),
                _formula_valore(anno_prec, etich, n, consulente),
                _formula_progressivo(progressivo, etich, n, consulente),
            ]
            ws.cell(r, 1, desc)
            ws.cell(r, 2, valori[0])
            ws.cell(r, 3, valori[1] if valori[1] else "n.d.")
            ws.cell(r, 4, _variazione(f"B{r}", f"C{r}"))
            ws.cell(r, 5, valori[2] if valori[2] else "n.d.")
            ws.cell(r, 6, _variazione(f"B{r}", f"E{r}"))
            ws.cell(r, 7, valori[3])
            for col in range(1, 8):
                cella = ws.cell(r, col)
                cella.font, cella.border = (grassetto if col == 2 else normale), bordo
                if col > 1:
                    cella.alignment = Alignment(horizontal="center")
                if col in (4, 6):
                    cella.number_format = perc
            celle_var[(consulente, desc)] = f"D{r}"
            r += 1
        r += 1

    for lettera in ("D", "F"):
        intervallo = f"{lettera}4:{lettera}{r}"
        ws.conditional_formatting.add(intervallo, CellIsRule(operator="greaterThan", formula=["0"],
                                                             font=Font(name=font, color="1E7B34", bold=True)))
        ws.conditional_formatting.add(intervallo, CellIsRule(operator="lessThan", formula=["0"],
                                                             font=Font(name=font, color="C0392B", bold=True)))
    ws.column_dimensions["A"].width = 32
    for lettera in "BCDEFG":
        ws.column_dimensions[lettera].width = 17
    ws.freeze_panes = "B4"

    # VARIAZIONI: consulenti (righe) x indicatori principali (colonne), var. % sul mese precedente.
    sintesi = [d for d in INDICATORI_SINTESI if (None, d) in celle_var]
    wv.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(sintesi) + 1)
    wv.cell(1, 1, f"VARIAZIONI % {mese_desc.upper()} RISPETTO A {desc_prec.upper()}").font = titolo
    wv.cell(1, 1).fill = fondo_titolo
    wv.row_dimensions[1].height = 24
    wv.cell(2, 1, "Valori calcolati nel foglio CONFRONTO, dove ci sono anche i numeri assoluti "
                  "e il confronto con lo stesso mese dell'anno precedente.").font = nota
    wv.cell(4, 1, "Consulente")
    for i, d in enumerate(sintesi, 2):
        wv.cell(4, i, d)
    for col in range(1, len(sintesi) + 2):
        c = wv.cell(4, col)
        c.font, c.fill, c.alignment, c.border = grassetto, fondo_intest, centro, bordo
    wv.row_dimensions[4].height = 45
    riga = 5
    for consulente in consulenti + [None]:
        wv.cell(riga, 1, consulente or "UFFICIO").font = grassetto
        wv.cell(riga, 1).border = bordo
        if consulente is None:
            wv.cell(riga, 1).fill = fondo_blocco
        for i, d in enumerate(sintesi, 2):
            c = wv.cell(riga, i, f"={FOGLIO_CONFRONTO}!{celle_var[(consulente, d)]}" if (consulente, d) in celle_var else "n.d.")
            c.number_format, c.alignment, c.border, c.font = perc, Alignment(horizontal="center"), bordo, normale
            if consulente is None:
                c.fill = fondo_blocco
        riga += 1
    intervallo = f"B5:{get_column_letter(len(sintesi) + 1)}{riga}"
    wv.conditional_formatting.add(intervallo, CellIsRule(operator="greaterThan", formula=["0"],
                                                         font=Font(name=font, color="1E7B34", bold=True)))
    wv.conditional_formatting.add(intervallo, CellIsRule(operator="lessThan", formula=["0"],
                                                         font=Font(name=font, color="C0392B", bold=True)))
    wv.column_dimensions["A"].width = 16
    for i in range(2, len(sintesi) + 2):
        wv.column_dimensions[get_column_letter(i)].width = 14
    wv.freeze_panes = "B5"
    for foglio in wb.worksheets:
        foglio.sheet_view.tabSelected = False
    ws.sheet_view.tabSelected = True
    wb.active = 0
