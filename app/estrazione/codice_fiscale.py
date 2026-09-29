"""Codice fiscale: validazione, correzione errori OCR, coerenza con i dati anagrafici."""

from __future__ import annotations

import re
from datetime import date

_DISPARI = {
    **dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
    **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [
        1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23,
    ])),
}
_PARI = {
    **{c: i for i, c in enumerate("0123456789")},
    **{c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
}
MESI_CF = "ABCDEHLMPRST"
# lettere usate al posto delle cifre nei casi di omocodia
_OMOCODIA = "LMNPQRSTUV"

# posizioni: L = lettera, N = cifra (o lettera di omocodia)
_SCHEMA = "LLLLLLNNLNNLNNNL"

_A_LETTERA = {"0": "O", "1": "I", "2": "Z", "3": "E", "4": "A", "5": "S", "6": "G", "7": "T", "8": "B", "9": "P"}
_A_CIFRA = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "J": "1", "Z": "2", "E": "3", "A": "4",
            "S": "5", "G": "6", "T": "7", "B": "8", "P": "9", "?": "7"}


def carattere_controllo(cf15: str) -> str:
    tot = 0
    for i, c in enumerate(cf15):
        tot += _DISPARI[c] if i % 2 == 0 else _PARI[c]
    return chr(ord("A") + tot % 26)


def valido(cf: str) -> bool:
    cf = (cf or "").upper().strip()
    if not re.fullmatch(r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]", cf):
        return False
    giorno = int(_normalizza_omocodia(cf)[9:11])
    if not (1 <= giorno <= 31 or 41 <= giorno <= 71):
        return False
    return carattere_controllo(cf[:15]) == cf[15]


def _coerci(s: str) -> str:
    out = []
    for c, tipo in zip(s, _SCHEMA):
        if tipo == "L" and c.isdigit():
            c = _A_LETTERA.get(c, c)
        elif tipo == "N" and not c.isdigit() and c not in _OMOCODIA:
            c = _A_CIFRA.get(c, c)
        out.append(c)
    return "".join(out)


_CONFUSIONI = {
    "D": "0O", "0": "DOQ", "O": "0DQ", "Q": "O0", "I": "1LJT", "1": "IL", "L": "I1", "J": "I",
    "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z", "G": "6", "6": "G", "E": "F3",
    "F": "E", "M": "NH", "N": "MH", "H": "NM", "V": "YU", "U": "V", "Y": "V", "T": "7", "7": "T",
    "A": "4", "4": "A", "R": "P", "P": "R",
}


def candidati(testo: str) -> list[str]:
    """Estrae dal testo OCR i codici fiscali validi (correggendo gli errori tipici)."""
    t = (testo or "").upper()
    trovati: list[str] = []
    # blocchi alfanumerici di 15-18 caratteri, anche con spazi interni (es. 'GMN MRA 64R11 L407C')
    grezzi = set(re.findall(r"[A-Z0-9?]{15,18}", t.replace(" ", "")))
    grezzi |= set(re.findall(r"\b[A-Z0-9?]{15,18}\b", t))
    grezzi |= {m.replace(" ", "") for m in re.findall(r"[A-Z]{3} ?[A-Z]{3} ?[0-9A-Z]{2}[A-Z][0-9A-Z]{2} ?[A-Z][0-9A-Z]{3}[A-Z]", t)}
    # testo senza spazi: il CF puo' essere spezzato da uno spazio in un punto qualsiasi
    grezzi |= set(re.findall(r"[A-Z0-9?]{16,}", t.replace(" ", "")))
    for g in grezzi:
        finestre = [g] if len(g) == 16 else [g[i:i + 16] for i in range(len(g) - 15)]
        # carattere in piu' o in meno: prova a toglierne uno
        if len(g) == 17:
            finestre += [g[:i] + g[i + 1:] for i in range(17)]
        for f in finestre:
            if len(f) != 16:
                continue
            c = _coerci(f)
            if valido(c):
                trovati.append(c)
    return trovati


def ricostruisci(testi: list[str], cognome: str, nome: str, nascita: date, sesso_: str) -> str | None:
    """Ricostruisce il codice fiscale partendo da dati anagrafici certi (es. da MRZ)
    e leggendo dal testo OCR solo il codice del comune di nascita, verificato col
    carattere di controllo."""
    if not (cognome and nome and nascita and sesso_):
        return None
    prefisso = codice_cognome(cognome) + codice_nome(nome) + codice_data_sesso(nascita, sesso_)
    ds = prefisso[6:]
    voti: dict[str, int] = {}
    for t in testi:
        t = re.sub(r"[^A-Z0-9?]", "", (t or "").upper())
        for i in range(0, max(0, len(t) - 9)):
            if _coerci("AAAAAA" + t[i:i + 5] + "A0000A")[6:11] != ds:
                continue
            belf = _coerci("AAAAAA00A00" + t[i + 5:i + 9] + "A")[11:15]
            if not re.fullmatch(r"[A-Z][0-9]{3}", belf):
                continue
            cf = prefisso + belf
            cf += carattere_controllo(cf)
            if t[i + 9:i + 10] == cf[15]:
                voti[cf] = voti.get(cf, 0) + 1
    if not voti:
        return None
    return max(voti, key=voti.get)


def codice_cognome(cognome: str) -> str:
    s = re.sub(r"[^A-Z]", "", _senza_accenti(cognome.upper()))
    cons = [c for c in s if c not in "AEIOU"]
    voc = [c for c in s if c in "AEIOU"]
    return ("".join(cons + voc) + "XXX")[:3]


def codice_nome(nome: str) -> str:
    s = re.sub(r"[^A-Z]", "", _senza_accenti(nome.upper()))
    cons = [c for c in s if c not in "AEIOU"]
    voc = [c for c in s if c in "AEIOU"]
    if len(cons) >= 4:
        return cons[0] + cons[2] + cons[3]
    return ("".join(cons + voc) + "XXX")[:3]


def codice_data_sesso(nascita: date, sesso: str) -> str:
    giorno = nascita.day + (40 if (sesso or "").upper() == "F" else 0)
    return f"{nascita.year % 100:02d}{MESI_CF[nascita.month - 1]}{giorno:02d}"


def _senza_accenti(s: str) -> str:
    return s.translate(str.maketrans("ÀÁÈÉÌÍÒÓÙÚ", "AAEEIIOOUU"))


def _normalizza_omocodia(cf: str) -> str:
    out = list(cf)
    for i in (6, 7, 9, 10, 12, 13, 14):
        if out[i] in _OMOCODIA:
            out[i] = str(_OMOCODIA.index(out[i]))
    return "".join(out)


def sesso(cf: str) -> str:
    if not valido(cf):
        return ""
    return "F" if int(_normalizza_omocodia(cf)[9:11]) > 40 else "M"


def data_nascita(cf: str) -> date | None:
    if not valido(cf):
        return None
    n = _normalizza_omocodia(cf)
    anno = int(n[6:8])
    mese = MESI_CF.index(n[8]) + 1
    giorno = int(n[9:11]) % 40
    anno += 1900 if anno > date.today().year % 100 else 2000
    try:
        return date(anno, mese, giorno)
    except ValueError:
        return None


def coerenza(cf: str, cognome: str = "", nome: str = "", nascita: date | None = None, sesso_: str = "") -> list[str]:
    """Restituisce l'elenco delle incoerenze tra codice fiscale e dati anagrafici."""
    problemi = []
    if not cf:
        return problemi
    cf = cf.upper().replace(" ", "")
    if not valido(cf):
        return ["codice fiscale non valido (carattere di controllo errato)"]
    if cognome and codice_cognome(cognome) != cf[:3]:
        problemi.append(f"il cognome '{cognome}' non corrisponde al codice fiscale")
    if nome and codice_nome(nome) != cf[3:6]:
        problemi.append(f"il nome '{nome}' non corrisponde al codice fiscale")
    if nascita and sesso_ and codice_data_sesso(nascita, sesso_) != _normalizza_omocodia(cf)[6:11]:
        problemi.append("data di nascita o sesso non corrispondono al codice fiscale")
    return problemi
