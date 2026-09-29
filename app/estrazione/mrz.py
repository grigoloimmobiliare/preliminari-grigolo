"""Lettura della zona MRZ (carta d'identità elettronica TD1 e passaporto TD3),
con correzione degli errori OCR tramite le cifre di controllo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_PESI = [7, 3, 1]


def cifra_controllo(s: str) -> str:
    tot = 0
    for i, c in enumerate(s):
        if c.isdigit():
            v = int(c)
        elif c.isalpha():
            v = ord(c) - 55
        else:
            v = 0
        tot += v * _PESI[i % 3]
    return str(tot % 10)


_A_CIFRA = {"O": "0", "D": "0", "Q": "0", "U": "0", "I": "1", "L": "1", "J": "1", "Z": "2", "S": "5",
            "B": "8", "G": "6", "T": "7", "A": "4", "E": "3", "?": "7"}
_A_LETTERA = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "7": "T", "4": "A", "3": "E"}


def _cifre(s: str) -> str:
    return "".join(_A_CIFRA.get(c, c) for c in s)


def _lettere(s: str) -> str:
    return "".join(_A_LETTERA.get(c, c) for c in s)


def _pulisci(riga: str) -> str:
    r = riga.upper().replace(" ", "").replace("«", "<").replace("‹", "<")
    # il riempitivo '<' viene spesso letto come K, C, E, S, L, (, [ ...
    r = re.sub(r"(?<=<)[KCELS(\[{]+(?=<|$)", lambda m: "<" * len(m.group()), r)
    r = re.sub(r"[KCELS(\[{<]{4,}$", lambda m: "<" * len(m.group()), r)
    r = re.sub(r"[^A-Z0-9<]", "", r)
    return r


def _data(yymmdd: str, futuro: bool = False) -> date | None:
    try:
        yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    except ValueError:
        return None
    oggi = date.today().year % 100
    if futuro:
        anno = 2000 + yy
    else:
        anno = 1900 + yy if yy > oggi else 2000 + yy
    try:
        return date(anno, mm, dd)
    except ValueError:
        return None


@dataclass
class DatiMRZ:
    tipo: str = ""               # "C.I." / "Passaporto"
    numero_documento: str = ""
    numero_valido: bool = False
    data_nascita: date | None = None
    nascita_valida: bool = False
    sesso: str = ""
    scadenza: date | None = None
    scadenza_valida: bool = False
    cognome: str = ""
    nome: str = ""
    nazionalita: str = ""
    nomi_candidati: list = None  # [(cognome, nome), ...] da tutte le letture

    @property
    def affidabile(self) -> bool:
        return self.nascita_valida and self.scadenza_valida


def _numero_cie(grezzo: str) -> list[str]:
    """Il numero della CIE ha formato AA00000AA: forza lettere/cifre per posizione."""
    if len(grezzo) != 9:
        return [grezzo]
    return [_lettere(grezzo[:2]) + _cifre(grezzo[2:7]) + _lettere(grezzo[7:]), grezzo]


def leggi(testi: list[str]) -> DatiMRZ | None:
    """Cerca le righe MRZ in uno o piu' testi OCR e restituisce i dati migliori."""
    righe = []
    for t in testi:
        for r in (t or "").splitlines():
            r = _pulisci(r)
            if len(r) >= 20:
                righe.append(r)

    ris = DatiMRZ()
    trovato = False

    # riga 1 TD1: C<ITA + numero documento (9) + cifra controllo
    for r in righe:
        m = re.search(r"[CI1][<KCI]?[I1]T[A4]([A-Z0-9]{10,11})", r)
        if not m:
            continue
        blocco = m[1]
        # l'OCR a volte aggiunge un carattere: prova anche togliendone uno
        varianti = [blocco[:10]] + [(blocco[:i] + blocco[i + 1:])[:10] for i in range(len(blocco))]
        for v in varianti:
            if len(v) < 10:
                continue
            for num in _numero_cie(v[:9]):
                if v[9] in "0123456789O" and cifra_controllo(num) == v[9].replace("O", "0") and re.fullmatch(r"[A-Z]{2}\d{5}[A-Z]{2}|[A-Z]{2}\d{7}", num):
                    ris.tipo, ris.numero_documento, ris.numero_valido = "C.I.", num, True
                    trovato = True
                    break
            if ris.numero_valido:
                break
        if ris.numero_valido:
            break
        if not ris.numero_documento:
            ris.tipo, ris.numero_documento = "C.I.", _numero_cie(blocco[:9])[0]
            trovato = True

    # passaporto TD3 riga 2: numero(9)+cc+ITA+nascita(6)+cc+sesso+scadenza(6)+cc
    for r in righe:
        m = re.search(r"([A-Z0-9<]{9})([0-9])ITA(\w{6})(\w)([MF<])(\w{6})(\w)", r)
        if m and r.startswith(m[0][:9]) and not ris.numero_valido:
            num = m[1].replace("<", "")
            if cifra_controllo(m[1]) == m[2]:
                ris.tipo, ris.numero_documento, ris.numero_valido = "Passaporto", num, True
                trovato = True

    # riga 2 TD1 (o parte della TD3): nascita+cc+sesso+scadenza+cc+nazionalita'
    for r in righe:
        m = re.search(r"(\w{6})(\w)([MFH<])(\w{6})(\w)([A-Z0-9]{3})", r)
        if not m:
            continue
        if sum(c.isdigit() for c in m[1] + m[4]) < 9:
            continue
        nas, cn, sx, sca, cs = _cifre(m[1]), _cifre(m[2]), m[3], _cifre(m[4]), _cifre(m[5])
        if not (nas.isdigit() and sca.isdigit()):
            continue
        ok_n = cifra_controllo(nas) == cn
        ok_s = cifra_controllo(sca) == cs
        if (ok_n and ok_s) or not ris.data_nascita:
            ris.data_nascita, ris.nascita_valida = _data(nas), ok_n
            ris.scadenza, ris.scadenza_valida = _data(sca, futuro=True), ok_s
            ris.sesso = {"M": "M", "F": "F", "H": "M"}.get(sx, "")
            ris.nazionalita = _lettere(m[6])
            trovato = True
            if ok_n and ok_s:
                break

    # riga 3 TD1 / riga 1 TD3: COGNOME<<NOME<SECONDO
    ris.nomi_candidati = []
    for r in righe:
        r2 = re.sub(r"^P[<A-Z]ITA", "", r)
        m = re.match(r"^([A-Z]+(?:<[A-Z]+)*)<<([A-Z]+(?:<[A-Z]+)*)", r2)
        if not m or re.search(r"\d", r2[:len(m[0])]):
            continue
        if r2.startswith(("C<ITA", "CIITA", "I<ITA")):
            continue
        ris.nomi_candidati.append((m[1].replace("<", " "), m[2].replace("<", " ")))
        trovato = True
    if ris.nomi_candidati:
        ris.cognome, ris.nome = max(set(ris.nomi_candidati), key=ris.nomi_candidati.count)

    return ris if trovato else None
