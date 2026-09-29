"""Funzioni di formattazione in italiano: importi, numeri in lettere, date."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_UNITA = [
    "zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove",
    "dieci", "undici", "dodici", "tredici", "quattordici", "quindici", "sedici",
    "diciassette", "diciotto", "diciannove",
]
_DECINE = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"]

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def _sotto_cento(n: int) -> str:
    if n < 20:
        return _UNITA[n]
    d, u = divmod(n, 10)
    base = _DECINE[d]
    if u == 0:
        return base
    if u in (1, 8):  # ventuno, ventotto: cade la vocale finale della decina
        base = base[:-1]
    parola = _UNITA[u]
    if u == 3:
        parola = "tré"
    return base + parola


def _sotto_mille(n: int) -> str:
    c, r = divmod(n, 100)
    if c == 0:
        return _sotto_cento(r)
    cento = "cento" if c == 1 else _UNITA[c] + "cento"
    if r == 0:
        return cento
    resto = _sotto_cento(r)
    if resto.startswith("otta") or resto == "otto":  # centottanta, centotto
        cento = cento[:-1]
    return cento + resto


def numero_in_lettere(n: int) -> str:
    """Converte un intero non negativo in lettere (es. 190000 -> 'centonovantamila')."""
    if n < 0:
        raise ValueError("numero negativo")
    if n == 0:
        return "zero"
    parti = []
    miliardi, n = divmod(n, 1_000_000_000)
    milioni, n = divmod(n, 1_000_000)
    migliaia, unita = divmod(n, 1000)
    if miliardi:
        parti.append("unmiliardo" if miliardi == 1 else _sotto_mille(miliardi) + "miliardi")
    if milioni:
        parti.append("unmilione" if milioni == 1 else _sotto_mille(milioni) + "milioni")
    if migliaia:
        parti.append("mille" if migliaia == 1 else _sotto_mille(migliaia) + "mila")
    if unita:
        parti.append(_sotto_mille(unita))
    testo = "".join(parti)
    # "tré" accentato solo in fondo alla parola (ventitré, ma ventitremila)
    testo = testo.replace("tré", "tre")
    if testo.endswith("tre") and len(testo) > 3:
        testo = testo[:-3] + "tré"
    return testo


def parse_importo(valore) -> Decimal | None:
    """Interpreta un importo scritto in vari formati (190.000,00 / 190000 / 190'000,00)."""
    if valore is None:
        return None
    if isinstance(valore, (int, float, Decimal)):
        return Decimal(str(valore)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    s = str(valore).strip().replace("€", "").replace("Euro", "").replace("euro", "")
    s = s.replace("'", "").replace("`", "").replace("’", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") >= 1 and len(s.split(".")[-1]) == 3:
        s = s.replace(".", "")
    try:
        return Decimal(s).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except InvalidOperation:
        return None


def formato_euro(valore) -> str:
    """Decimal -> '190.000,00'."""
    d = parse_importo(valore)
    if d is None:
        return ""
    intero, dec = f"{d:.2f}".split(".")
    gruppi = []
    while len(intero) > 3:
        gruppi.insert(0, intero[-3:])
        intero = intero[:-3]
    gruppi.insert(0, intero)
    return ".".join(gruppi) + "," + dec


def euro_in_lettere(valore) -> str:
    """Decimal -> 'centonovantamila/00'."""
    d = parse_importo(valore)
    if d is None:
        return ""
    intero = int(d)
    cent = int((d - intero) * 100)
    return f"{numero_in_lettere(intero)}/{cent:02d}"


def euro_completo(valore) -> str:
    """'Euro 190.000,00 (centonovantamila/00)'."""
    if parse_importo(valore) is None:
        return ""
    return f"Euro {formato_euro(valore)} ({euro_in_lettere(valore)})"


# ---------------------------------------------------------------- date

_RE_DATA = re.compile(r"(\d{1,2})\s*[./\-,:]\s*(\d{1,2})\s*[./\-,:]\s*(\d{2,4})")


def parse_data(valore) -> date | None:
    """Interpreta '13/01/1956', '13.01.1956', '2026-09-29', '9 dicembre 1973'."""
    if valore is None:
        return None
    if isinstance(valore, datetime):
        return valore.date()
    if isinstance(valore, date):
        return valore
    s = str(valore).strip().lower()
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = _RE_DATA.search(s)
    if m:
        g, me, a = int(m[1]), int(m[2]), int(m[3])
        if a < 100:
            a += 2000 if a < 50 else 1900
        try:
            return date(a, me, g)
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s*(?:°|º)?\s+(" + "|".join(MESI) + r")\s+(\d{4})", s)
    if m:
        try:
            return date(int(m[3]), MESI.index(m[2]) + 1, int(m[1]))
        except ValueError:
            return None
    return None


def formato_data(valore) -> str:
    d = parse_data(valore)
    return d.strftime("%d/%m/%Y") if d else ""


def data_iso(valore) -> str:
    d = parse_data(valore)
    return d.isoformat() if d else ""


# numeri scritti in lettere negli atti notarili ("il giorno ventidue", "duemilaventicinque")
def lettere_in_numero(testo: str) -> int | None:
    t = testo.lower().strip().replace("'", "").replace(" ", "")
    t = t.replace("é", "e").replace("è", "e")
    if not t:
        return None
    if t in ("primo", "uno", "un"):
        return 1
    for n in range(0, 3000):
        if numero_in_lettere(n).replace("é", "e") == t:
            return n
    return None


# --------------------------------------------------------- sigle province

PROVINCE = {
    "AG", "AL", "AN", "AO", "AP", "AQ", "AR", "AT", "AV", "BA", "BG", "BI", "BL", "BN", "BO",
    "BR", "BS", "BT", "BZ", "CA", "CB", "CE", "CH", "CL", "CN", "CO", "CR", "CS", "CT", "CZ",
    "EN", "FC", "FE", "FG", "FI", "FM", "FR", "GE", "GO", "GR", "IM", "IS", "KR", "LC", "LE",
    "LI", "LO", "LT", "LU", "MB", "MC", "ME", "MI", "MN", "MO", "MS", "MT", "NA", "NO", "NU",
    "OR", "PA", "PC", "PD", "PE", "PG", "PI", "PN", "PO", "PR", "PT", "PU", "PV", "PZ", "RA",
    "RC", "RE", "RG", "RI", "RM", "RN", "RO", "SA", "SI", "SO", "SP", "SR", "SS", "SU", "SV",
    "TA", "TE", "TN", "TO", "TP", "TR", "TS", "TV", "UD", "VA", "VB", "VC", "VE", "VI", "VR",
    "VT", "VV", "EE",
}

# capoluoghi e comuni frequenti in zona, per dedurre la provincia quando manca
COMUNE_PROVINCIA = {
    "TREVISO": "TV", "VENEZIA": "VE", "MESTRE": "VE", "PADOVA": "PD", "VICENZA": "VI",
    "VERONA": "VR", "ROVIGO": "RO", "BELLUNO": "BL", "PORDENONE": "PN", "UDINE": "UD",
    "TRIESTE": "TS", "GORIZIA": "GO", "TRENTO": "TN", "BOLZANO": "BZ", "MILANO": "MI",
    "ROMA": "RM", "TORINO": "TO", "BOLOGNA": "BO", "FIRENZE": "FI", "NAPOLI": "NA",
    "MOGLIANO VENETO": "TV", "ODERZO": "TV", "CASTELFRANCO VENETO": "TV", "MONTEBELLUNA": "TV",
    "CONEGLIANO": "TV", "VITTORIO VENETO": "TV", "PAESE": "TV", "PREGANZIOL": "TV",
    "VILLORBA": "TV", "PONZANO VENETO": "TV", "SILEA": "TV", "CASIER": "TV", "QUINTO DI TREVISO": "TV",
    "CARBONERA": "TV", "SPRESIANO": "TV", "ZERO BRANCO": "TV", "MORGANO": "TV", "ISTRANA": "TV",
    "RONCADE": "TV", "MARCON": "VE", "SCORZE'": "VE", "SCORZÈ": "VE", "NOALE": "VE",
    "MIRANO": "VE", "SPINEA": "VE", "MARTELLAGO": "VE", "JESOLO": "VE", "SAN DONA' DI PIAVE": "VE",
}


def correggi_provincia(sigla: str) -> str:
    """Corregge errori OCR tipici su una sigla di provincia (TU -> TV)."""
    s = (sigla or "").upper().strip()
    if s in PROVINCE:
        return s
    sostituzioni = {"U": "V", "0": "O", "1": "I", "5": "S", "8": "B", "Y": "V"}
    cand = "".join(sostituzioni.get(c, c) for c in s)
    return cand if cand in PROVINCE else s


def provincia_da_comune(comune: str) -> str:
    return COMUNE_PROVINCIA.get((comune or "").upper().strip(), "")


def titolo(s: str) -> str:
    """'VIALE TRENTO E TRIESTE' -> 'Viale Trento e Trieste'."""
    minuscole = {"e", "di", "del", "della", "dei", "delle", "da", "in", "al", "alla", "d", "n."}
    parole = []
    for i, w in enumerate((s or "").lower().split()):
        if i > 0 and w in minuscole:
            parole.append(w)
        else:
            parole.append("'".join(p[:1].upper() + p[1:] for p in w.split("'")))
    return " ".join(parole)
