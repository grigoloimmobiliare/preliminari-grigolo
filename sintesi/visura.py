"""Lettura delle visure catastali in PDF (Agenzia delle Entrate / SISTER).

Gestisce i due formati in circolazione:
- formato "a tabella" (visure fino al 2022 circa): righe con foglio, particella, sub,
  categoria, classe, consistenza, rendita e blocco INTESTATI con i diritti;
- formato "a schede" (visure recenti): sezioni "> Dati identificativi",
  "> Dati di classamento", "> Intestati catastali", "Diritto di: Proprieta' per 1/1".

Di ogni visura si ricavano le unita' immobiliari, gli intestati attuali (il primo blocco
di intestati: nelle visure storiche quelli successivi sono passati) e i "dati derivanti da",
da cui si capisce se l'ultimo passaggio e' un atto notarile o una successione.
"""

from __future__ import annotations

import re
from pathlib import Path

from app import testo as tx
from app.estrazione import ocr

# codice fiscale di persona fisica (anche omocodico) e partita IVA / CF numerico di societa'
_CF = r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-EHLMPR-T][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]"
RE_CF = re.compile(r"\b(" + _CF + r")\b")
RE_CF_NUMERICO = re.compile(r"(?:\(CF\s*|\bC\.?F\.?:?\s*)?\b(\d{11})\b\*?")

_DIRITTI = (r"(?:Propriet[aà]['`’]?|Nuda\s+propriet[aà]['`’]?|Usufrutt\w*|Abitazione|Uso|Superficie|"
            r"Enfiteusi|Livello|Oneri|Servit[uù]['`’]?|Diritto\s+del\s+concedente|Comproprietari\w*)")
RE_DIRITTO = re.compile(r"(?:Diritto\s+di:?\s*)?(" + _DIRITTI + r"[^\n>]*?)(?=\s*\(deriva|\s*\n|\s*$|\s+\d{1,2}[.)]?\s+[A-Z]{2})",
                        re.I)


def testo_visura(percorso: Path) -> tuple[str, str]:
    pagine = ocr.testo_pdf(percorso)
    if pagine and sum(len(p.strip()) for p in pagine) > 200:
        return "\n".join(pagine), "testo digitale"
    testi = [ocr.ocr(ocr.immagine_pagina(percorso, i, dpi=300), psm=4) for i in range(ocr.numero_pagine(percorso))]
    return "\n".join(testi), "OCR"


def estrai(percorso: Path) -> dict:
    grezzo, metodo = testo_visura(percorso)
    d = analizza_testo(grezzo)
    d["_metodo"] = metodo
    d["_file"] = percorso.name
    return d


def _normalizza(t: str) -> str:
    t = t.replace(" ", " ").replace("’", "'").replace("`", "'")
    t = re.sub(r"(?<=\d)\s*m(?:²|2|q)(?=\W|$)", " mq", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return t


def _piatto(t: str) -> str:
    return re.sub(r"\s+", " ", t)


def _cerca(regex: str, t: str, flags=re.I) -> str:
    m = re.search(regex, t, flags)
    return m[1].strip() if m else ""


def analizza_testo(grezzo: str) -> dict:
    t = _normalizza(grezzo)
    p = _piatto(t)
    dati: dict = {"avvisi": []}

    # --------------------------------------------------------- intestazione
    dati["tipo"] = "storica" if re.search(r"visura\s+storica", p, re.I) else "attuale"
    if re.search(r"visura\s+(?:attuale\s+|storica\s+)?per\s+soggetto", p, re.I):
        dati["tipo"] += " per soggetto"
    elif re.search(r"visura\s+(?:attuale\s+|storica\s+)?per\s+immobile", p, re.I):
        dati["tipo"] += " per immobile"
    dati["data"] = tx.formato_data(
        _cerca(r"Situazione degli atti informatizzati (?:al|dall'impianto meccanografico al)\s+(\d{2}/\d{2}/\d{4})", p)
        or _cerca(r"\bData:?\s*(\d{2}/\d{2}/\d{4})", p))
    dati["catasto"] = "Terreni" if re.search(r"Catasto\s+Terreni", p, re.I) and not re.search(r"Catasto\s+Fabbricati", p, re.I) \
        else "Fabbricati"
    m = re.search(r"Comune\s+di\s+([A-ZÀ-Ü][A-ZÀ-Ü' .\-]+?)\s*\(\s*(?:Codice:?\s*)?([A-Z]\d{3})\s*\)(?:\s*\(([A-Z]{2})\))?", p)
    if m:
        dati["comune"] = tx.titolo(m[1].strip())
        dati["codice_comune"] = m[2]
        dati["prov"] = m[3] or ""
    if not dati.get("prov"):
        dati["prov"] = tx.provincia_da_comune(dati.get("comune", "")) or \
            _sigla_provincia(_cerca(r"Provincia\s+di\s+([A-ZÀ-Ü][A-ZÀ-Ü' ]+?)(?:\s+Catasto|\s+Immobile|\s*$|\s+Dati)", p))

    # --------------------------------------------------------- unita'
    dati["unita"] = _unita(t, p, dati)

    # --------------------------------------------------------- intestati
    blocco, resto = _blocco_intestati(t)
    dati["intestati"] = _intestati(blocco)
    dati["derivanti_da"] = _derivanti_da(resto)
    dati["successione"] = _successione(dati["derivanti_da"])

    if not dati["unita"]:
        dati["avvisi"].append("Nessuna unità immobiliare riconosciuta nella visura.")
    if not dati["intestati"]:
        dati["avvisi"].append("Nessun intestato riconosciuto nella visura.")
    return dati


def _sigla_provincia(nome: str) -> str:
    return tx.provincia_da_comune(nome)


# ------------------------------------------------------------------ unita'

_RE_IDENTIFICATIVI = re.compile(
    r"(?:Sez(?:ione)?\.?\s*Urb(?:ana|\.)?:?\s*([A-Z0-9]{1,3})\s+)?"
    r"Foglio:?\s*(\d+)\s+(?:Particella|Mappale|Numero|Part\.):?\s*(\d+)"
    r"(?:\s+(?:Subalterno|Sub\.?):?\s*(\d+))?", re.I)

# riga della tabella del vecchio formato:
#   1 | E | 2 | 100 | 5 | [zona] [micro] | A/2 | 4 | 5,5 vani | Totale: 95 mq ... | Euro 500,00
_RE_RIGA_TABELLA = re.compile(
    r"(?:^|\s)(?:\d{1,2}\s+)?(?:([A-Z])\s+)?(\d{1,4})\s+(\d{1,5})\s+(\d{1,4})\s+(?:\w{1,3}\s+){0,2}"
    r"([A-F]/\d{1,2})\s+(\w{1,2})\s+([\d.,]+\s*(?:vani|mq|metri quadri))"
    r"(?:\s+Totale:?\s*([\d.,]+)\s*mq)?"
    r".{0,120}?(?:Euro|€|L\.)\s*([\d.]+,\d{2})")


def _classamento(s: str) -> dict:
    u = {}
    u["categoria"] = _cerca(r"Categoria:?\s*([A-F]\s*/\s*\d{1,2})", s).replace(" ", "")
    u["classe"] = _cerca(r"Classe:?\s*([0-9U]{1,2})\b", s)
    u["consistenza"] = _cerca(r"Consistenza:?\s*([\d.,]+\s*(?:vani|mq|metri quadri))", s)
    u["superficie"] = _cerca(r"(?:Superficie catastale\s*)?Totale:?\s*([\d.,]+)\s*mq", s)
    u["rendita"] = _cerca(r"Rendita:?\s*(?:Euro|€)\s*([\d.]+,\d{2})", s)
    return u


def _indirizzo(s: str) -> str:
    m = re.search(r"Indirizzo:?\s*\n?\s*(.+?)(?:\n|$)", s, re.I)
    if not m:
        return ""
    ind = m[1].strip(" >")
    if not ind or re.match(r"(?:Notifica|Partita|Mod\.58|Annotazioni)", ind, re.I):
        return ""
    ind = re.split(r"\s+(?:Notifica|Partita|Mod\.\s*58|Annotazioni|Dati derivanti)", ind, flags=re.I)[0]
    return tx.titolo(ind.strip(" ,"))


def _unita(t: str, p: str, dati: dict) -> list[dict]:
    unita: list[dict] = []
    visti = set()

    def aggiungi(u: dict):
        chiave = (u.get("sezione", ""), u["foglio"], u["particella"], u.get("sub", ""))
        if chiave in visti:
            # completa i dati mancanti dell'unita' gia' vista
            for x in unita:
                if (x.get("sezione", ""), x["foglio"], x["particella"], x.get("sub", "")) == chiave:
                    for k, v in u.items():
                        if v and not x.get(k):
                            x[k] = v
            return
        visti.add(chiave)
        unita.append(u)

    # formato a schede: una sezione per immobile, a partire dai "Dati identificativi"
    schede = re.split(r"(?:>\s*)?Dati identificativi\b", t, flags=re.I)
    if len(schede) > 1:
        for s in schede[1:]:
            # nelle visure storiche dopo la situazione attuale c'e' la storia: si ferma li'
            s = re.split(r"Storia degli intestati|Situazione dell'unit[aà] immobiliare (?:che ha originato|dal)|"
                         r"Situazione degli intestati dal", s, flags=re.I)[0]
            sp = _piatto(s)
            m = _RE_IDENTIFICATIVI.search(sp)
            if not m:
                continue
            u = {"sezione": (m[1] or "").upper(), "foglio": m[2], "particella": m[3], "sub": m[4] or ""}
            u.update(_classamento(sp))
            ind = _indirizzo(s)
            u["piano"] = _cerca(r"\bPiano:?\s*([\w\-]+(?:\s*-\s*\w+)?)", ind) or \
                _cerca(r"\bPiano:?\s*([\w\-]+(?:\s*-\s*\w+)?)", sp)
            u["indirizzo"] = re.sub(r"\s+Piano\s+.*$", "", ind, flags=re.I)
            aggiungi(u)
        if unita:
            return unita

    # formato a tabella
    for m in _RE_RIGA_TABELLA.finditer(p):
        u = {"sezione": m[1] or "", "foglio": m[2], "particella": m[3], "sub": m[4],
             "categoria": m[5], "classe": m[6], "consistenza": m[7].strip(),
             "superficie": m[8] or "", "rendita": m[9]}
        dopo = p[m.end():m.end() + 400]
        mi = re.search(r"Indirizzo:?\s*(.+?)(?:\s+(?:Notifica|Partita|Mod\.\s*58|Annotazioni|Situazione|INTESTATI|Dati derivanti|Mappali|N\.\s+DATI)|$)", dopo, re.I)
        if mi:
            u["indirizzo"] = tx.titolo(re.sub(r"\s+Piano\s+.*$", "", mi[1], flags=re.I).strip(" ,"))
            u["piano"] = _cerca(r"\bPiano\s+([\w\-]+(?:\s*-\s*\w+)?)", mi[1])
        aggiungi(u)
        if dati["tipo"].startswith("storica"):
            break  # nelle visure storiche la prima riga e' la situazione attuale

    # dati della richiesta (visura per immobile): identificativi certi anche se la tabella non si legge
    if not unita:
        m = re.search(r"Dati della richiesta.{0,250}?" + _RE_IDENTIFICATIVI.pattern, p, re.I)
        if m:
            u = {"sezione": (m[1] or "").upper(), "foglio": m[2], "particella": m[3], "sub": m[4] or ""}
            u.update(_classamento(p))
            u["indirizzo"] = _indirizzo(t)
            aggiungi(u)
    return unita


# ------------------------------------------------------------------ intestati

_INIZIO_INTESTATI = re.compile(
    r"(?:>\s*)?Intestati catastali|\bINTESTATI\b|Situazione degli intestati(?: dal \d{2}/\d{2}/\d{4})?|"
    r"(?:N\.\s*)?DATI ANAGRAFICI\s+CODICE FISCALE", re.I)
_FINE_INTESTATI = re.compile(
    r"(?:>\s*)?Dati derivanti da|DATI DERIVANTI DA|Storia degli intestati|Situazione degli intestati dal|"
    r"Situazione dell'unit|Unit[aà] immobiliari? n\.|Immobile\s+\d+|Totale:?\s+vani|Rilasciata da|"
    r"Visura telematica|Mappali Terreni", re.I)


def _blocco_intestati(t: str) -> tuple[str, str]:
    m = _INIZIO_INTESTATI.search(t)
    if not m:
        return "", ""
    resto = t[m.end():]
    # salta l'eventuale riga di intestazione della tabella
    resto = re.sub(r"^\s*(?:dal \d{2}/\d{2}/\d{4})?\s*(?:N\.\s*)?(?:DATI ANAGRAFICI)?\s*(?:CODICE FISCALE)?\s*"
                   r"(?:DIRITTI E ONERI REALI)?", "", resto, flags=re.I)
    f = _FINE_INTESTATI.search(resto)
    if f:
        return resto[:f.start()], resto[f.start():]
    return resto[:3000], resto[3000:]


def _intestati(blocco: str) -> list[dict]:
    if not blocco.strip():
        return []
    # ogni intestato inizia con il numero d'ordine: "1 ROSSI Mario" oppure "> 1. ROSSI Mario"
    voci = re.split(r"(?:^|\n|\s)>?\s*(?=\d{1,2}[.)]?\s+[A-ZÀ-Ü][A-ZÀ-Ü'])", "\n" + blocco)
    out = []
    for v in voci:
        v = _piatto(v).strip()
        m = re.match(r"(\d{1,2})[.)]?\s+(.+)", v)
        if not m:
            continue
        corpo = m[2]
        cf = RE_CF.search(corpo)
        cfn = None if cf else re.search(r"(?:\(CF\s*|\bC\.?F\.?:?\s*|\s)(\d{11})\b", corpo)
        if not cf and not cfn and not re.search(r"\bnat[oa]\b|\bsede\b|" + _DIRITTI, corpo, re.I):
            continue
        # nominativo: fino a "(CF", "nato", "con sede", "sede in" o al codice fiscale
        nom = re.split(r"\s*\(CF|\s+nat[oa]\s|\s+con sede|\s+sede\s+in|\s+" + _CF + r"|\s+\d{11}\b", corpo, maxsplit=1)[0]
        nom = nom.strip(" ,-")
        persona = {
            "nominativo": nom,
            "codice_fiscale": cf[1] if cf else (cfn[1] if cfn else ""),
            "societa": bool(cfn) or bool(re.search(r"\bsede\b", corpo, re.I)),
            "luogo_nascita": "", "data_nascita": "", "sede": "",
            "diritto": "",
        }
        mn = re.search(r"nat[oa]\s+a\s+(.+?)\s*(?:\((\w{2})\))?\s+il\s+(\d{2}/\d{2}/\d{4})", corpo, re.I)
        if mn:
            persona["luogo_nascita"] = tx.titolo(mn[1]) + (f" ({mn[2]})" if mn[2] else "")
            persona["data_nascita"] = mn[3]
        ms = re.search(r"sede\s+in\s+(.+?)(?:\s*\(CF|\s+\d{11}|\s+Diritto|\s+" + _DIRITTI + r"|$)", corpo, re.I)
        if ms:
            persona["sede"] = tx.titolo(ms[1].strip(" ,"))
        md = RE_DIRITTO.search(corpo + "\n")
        if md:
            persona["diritto"] = _pulisci_diritto(md[1])
        out.append(persona)
    return out


def _pulisci_diritto(s: str) -> str:
    s = re.sub(r"\(\d+\)", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.*")
    s = re.sub(r"^Propriet[aà]['`’]?", "Proprietà", s, flags=re.I)
    s = re.sub(r"^Nuda\s+propriet[aà]['`’]?", "Nuda proprietà", s, flags=re.I)
    s = re.sub(r"\s+(?:in regime|bene personale|in comunione).*$", lambda m: m[0], s)
    return s


def quota(diritto: str) -> tuple[int, int] | None:
    m = re.search(r"(\d+)\s*/\s*(\d+)", diritto or "")
    if not m or int(m[2]) == 0:
        return None
    return int(m[1]), int(m[2])


# ------------------------------------------------------------- dati derivanti

def _derivanti_da(resto: str) -> str:
    if not resto:
        return ""
    m = re.search(r"(?:>\s*)?Dati derivanti da:?\s*(.+?)(?:\n\s*\n|Situazione degli|Storia degli|Unit[aà] immobiliar|"
                  r"Immobile\s+\d|Mappali|Visura telematica|Rilasciata da|\n\s*>\s*\d|$)", resto, re.I | re.S)
    if not m:
        return ""
    s = _piatto(m[1]).strip(" .")
    s = re.sub(r"^\d\.\s*", "", s)
    return s[:600]


def _successione(derivanti: str) -> dict:
    if not re.search(r"causa di morte|successione|denunzia|testament|riunione di usufrutto", derivanti or "", re.I):
        return {}
    out = {"testo": derivanti}
    m = re.search(r"SUCCESSIONE\s+(?:LEGITTIMA\s+|TESTAMENTARIA\s+)?(?:DI|IN MORTE DI)\s+([A-ZÀ-Ü' ]+?)(?:\s+Voltura|\s+n\.|\s+Sede|\s+in atti|\s*[.;(]|$)", derivanti, re.I)
    if m:
        out["defunto"] = m[1].strip().upper()
    m = re.search(r"del\s+(\d{2}/\d{2}/\d{4})", derivanti)
    if m:
        out["data"] = m[1]
    return out


def estremi_atto_derivante(derivanti: str) -> dict:
    """Da 'Atto del 10/03/2024 Pubblico ufficiale NERI PAOLO Sede TREVISO (TV) Repertorio n. 1234 - COMPRAVENDITA'."""
    out = {}
    m = re.search(r"Atto\s+(?:pubblico\s+)?del\s+(\d{2}/\d{2}/\d{4})", derivanti or "", re.I)
    if m:
        out["data"] = m[1]
    m = re.search(r"Pubblico ufficiale\s+([A-ZÀ-Ü' ]+?)\s+Sede", derivanti or "", re.I)
    if m:
        out["notaio"] = tx.titolo(m[1])
    m = re.search(r"Repertorio\s+n\.?\s*([\d.]+)", derivanti or "", re.I)
    if m:
        out["repertorio"] = m[1].strip(".")
    return out
