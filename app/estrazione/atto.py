"""Estrazione dei dati dall'atto di provenienza (compravendita, donazione, ...)."""

from __future__ import annotations

import re
from pathlib import Path

from .. import testo as tx
from . import codice_fiscale as cfm
from . import ocr

TIPI_ATTO = ["COMPRAVENDITA", "DONAZIONE", "DIVISIONE", "PERMUTA", "SUCCESSIONE", "ASSEGNAZIONE",
             "CESSIONE", "RINUNCIA", "ACCETTAZIONE DI EREDITA", "DECRETO DI TRASFERIMENTO"]


def testo_atto(percorso: Path) -> tuple[str, str]:
    """Restituisce (testo, metodo). Usa il testo digitale del PDF, altrimenti l'OCR."""
    pagine = ocr.testo_pdf(percorso)
    if pagine and sum(len(p.strip()) for p in pagine) > 500:
        return "\n".join(pagine), "testo digitale"
    testi = []
    for i in range(ocr.numero_pagine(percorso)):
        testi.append(ocr.ocr(ocr.immagine_pagina(percorso, i, dpi=300), psm=3))
    return "\n".join(testi), "OCR"


def _pulisci(t: str) -> str:
    t = t.replace(" ", " ")
    t = re.sub(r"\n\s*-\s*\d+\s*-\s*\n", "\n", t)          # numeri di pagina "- 3 -"
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)                  # parole spezzate a fine riga
    t = re.sub(r"[ \t]*\n[ \t]*", " ", t)
    return re.sub(r"\s{2,}", " ", t)


def _data_in_lettere(s: str):
    """'il giorno ventidue del mese di aprile' + 'duemilaventicinque' -> date."""
    m = re.search(r"anno\s+([a-z]+)\s+(?:il\s+)?giorno\s+([a-z]+)\s+(?:del\s+)?mese\s+di\s+([a-z]+)", s.lower())
    if not m:
        return None
    anno, giorno = tx.lettere_in_numero(m[1]), tx.lettere_in_numero(m[2])
    if anno and giorno and m[3] in tx.MESI:
        return tx.parse_data(f"{giorno}/{tx.MESI.index(m[3]) + 1}/{anno}")
    return None


def _data_testo(s: str) -> str:
    """'24 settembre 2024' / '24/09/2024' / 'il 09 maggio 2025' -> '24/09/2024'."""
    return tx.formato_data(s)


def estrai(percorso: Path) -> dict:
    grezzo, metodo = testo_atto(percorso)
    return analizza_testo(grezzo, metodo)


def analizza_testo(grezzo: str, metodo: str = "testo digitale") -> dict:
    t = _pulisci(grezzo)
    dati: dict = {}
    fonti: dict = {}
    avvisi: list[str] = []
    inizio = t[:2500]

    # ---------------------------------------------------------- estremi
    m = re.search(r"Repertorio\s*(?:N\.?|n\.?)?\s*(\d[\d.]*)", t, re.I) or re.search(r"\bRep\.?\s*n\.?\s*(\d[\d.]*)", t, re.I)
    if m:
        dati["repertorio"] = m[1].strip(".")
    m = re.search(r"Raccolta\s*(?:N\.?|n\.?)?\s*(\d[\d.]*)", t, re.I) or re.search(r"\bRacc\.?\s*n\.?\s*(\d[\d.]*)", t, re.I)
    if m:
        dati["raccolta"] = m[1].strip(".")

    for tipo in TIPI_ATTO:
        if re.search(r"\b" + tipo + r"\b", inizio, re.I):
            dati["tipo_atto"] = tipo.lower()
            break

    d = None
    m = re.search(r"L'anno[^()]{5,120}\((\d{1,2}/\d{1,2}/\d{4})\)", inizio, re.I)
    if m:
        d = tx.parse_data(m[1])
    d = d or _data_in_lettere(inizio)
    if d:
        dati["data_atto"] = tx.formato_data(d)

    m = re.search(r"(?:dottor(?:essa)?|dott\.(?:ssa)?|dr\.?)\s+([A-ZÀ-Ü][A-Za-zÀ-ü' ]+?),?\s+notaio\s+(?:in|residente in|con sede in)\s+([A-ZÀ-Ü][\w' ]+?)[,.]", inizio, re.I)
    if m:
        dati["notaio"] = tx.titolo(m[1].strip())
        dati["notaio_sede"] = tx.titolo(m[2].strip())

    # registrazione (annotazione a margine) e trascrizione
    m = re.search(r"REGISTRATO\s+A\s+([A-ZÀ-Ü ]+?)\s+(?:Atti Pubblici\s+)?[Ii]l\s+(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\s+al\s+n\.?\s*([\d/]+)\s*(?:serie\s+(\w+))?", t)
    if m:
        dati["registrazione"] = (f"registrato a {tx.titolo(m[1].strip())} il {_data_testo(m[2])} "
                                 f"al n. {m[3]}" + (f" serie {m[4]}" if m[4] else ""))
    # la trascrizione dell'atto stesso compare in testa o in coda (non nel corpo, dove
    # vengono citate le trascrizioni degli atti precedenti)
    zona = t[:1200] + " " + t[-2500:]
    m = re.search(r"[Tt]rascritt[oa]\s+(?:presso\s+\S+\s+)?a\s+([A-ZÀ-Üa-zà-ü ]+?)\s+(?:in data|il)\s+(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\s+a[il]?\s+nn?\.?\s*([\d/ ]+)", zona)
    if m:
        dati["trascrizione"] = f"trascritto a {tx.titolo(m[1].strip())} il {_data_testo(m[2])} ai nn. {m[3].strip()}"

    # --------------------------------------------------------- comparenti
    comparenti = []
    for m in re.finditer(
            r"-\s*([A-ZÀ-Ü][A-ZÀ-Ü' ]{3,60}?),\s+nat[oa]\s+(?:a|in)\s+(.+?)\s+il\s+(?:giorno\s+)?(.+?),\s+"
            r"residente\s+(?:a|in)\s+(.+?),\s+(.{0,250}?)codice fiscale\s+([A-Z0-9]{16})"
            r"((?:(?!\s-\s*[A-ZÀ-Ü]{2,}[A-ZÀ-Ü' ]*,\s+nat).){0,260})", t):
        nominativo = m[1].strip()
        luogo = m[2].strip()
        prov = ""
        mp = re.match(r"(.+?)\s*\((\w{2})\)", luogo)
        if mp:
            luogo, prov = mp[1], mp[2]
        stato = ""
        coda = m[7]
        ms = re.search(r"dichiara di essere\s+(.+?)(?:[.;]|, precisando)", coda)
        if ms:
            stato = re.sub(r"^di stato civile\s+", "", ms[1].strip())
        res = (m[4] + ", " + m[5]).split(", cittadin")[0].split(", munit")[0].strip(" ,")
        comparenti.append({
            "nominativo": nominativo,
            "luogo_nascita": tx.titolo(luogo),
            "prov_nascita": prov or tx.provincia_da_comune(luogo),
            "data_nascita": tx.formato_data(m[3]),
            "residenza": res,
            "codice_fiscale": m[6],
            "stato_civile": stato,
        })
    dati["comparenti"] = comparenti

    # chi acquista (o riceve) nell'atto di provenienza = attuale proprietario
    m = re.search(r"\b(?:vend\w*|don\w*|ced\w*|trasferisc\w*)\s+(?:a|al|alla|ai|alle)\s+(?:signor[ae]?|signori|sig\.(?:ra)?|coniugi)?\s*(.+?)\s+che\s+(?:acquist|accett)", t, re.I)
    intestatari = []
    if m:
        blocco = m[1].upper()
        for c in comparenti:
            if c["nominativo"].upper() in blocco:
                intestatari.append(c)
        if not intestatari:
            dati["intestatari_testo"] = m[1].strip()
    dati["intestatari"] = intestatari

    # ------------------------------------------------------------ immobile
    m = re.search(r"(?:fabbricat\w+|immobil\w+|edifici\w+|complesso)\s+sit[oa]\s+in\s+(?:Comune\s+di\s+)?([A-ZÀ-Ü][\w' ]+?),\s*(.+?),\s*e più precisamente\s+(.+?),?\s+identificat", t, re.I)
    if m:
        dati["comune"] = tx.titolo(m[1])
        dati["indirizzo"] = m[2].strip()
        dati["descrizione"] = _descrizione_nominale(m[3])
    else:
        m = re.search(r"sit[oa]\s+in\s+(?:Comune\s+di\s+)?([A-ZÀ-Ü][\w']+(?: [A-ZÀ-Ü][\w']+)*)", t)
        if m:
            dati["comune"] = tx.titolo(m[1])
    if dati.get("comune"):
        dati["prov"] = tx.provincia_da_comune(dati["comune"])

    dati["catastali"] = estrai_catastali(t)

    # ----------------------------------------------------------- urbanistica
    m = re.search(r"(dichiara che (?:le opere di costruzione|la costruzione|il fabbricato|l'immobile).+?)(?:Ciascuna parte|La parte acquirente d[àa] atto|ART\.\s*\d)", t, re.I)
    if m:
        dati["urbanistica_testo"] = m[1].strip()
    dati["ante_67"] = bool(re.search(r"anteriormente al (?:giorno )?1\s*°?\s*settembre 1967|ante(?:riore)? 1/9/1967|prima del 1\s*°?\s*settembre 1967", t, re.I))
    if dati.get("urbanistica_testo"):
        dati["urbanistica"] = _dichiarazione_urbanistica(dati["urbanistica_testo"])
    m = re.search(r"(?:abitabilit|agibilit)\w*\s+(?:originaria\s+)?(?:è stata|e' stata|risulta)?\s*rilasciat\w+\s+(dal Comune di [\w' ]+?\s+in data\s+.+?)(?:\.\s+(?-i:[A-Z])|\.?$)", t, re.I)
    if m:
        dati["agibilita"] = "rilasciato " + m[1].strip()

    dati["_metodo"] = metodo
    dati["_fonti"] = fonti
    dati["_avvisi"] = avvisi
    return dati


def _descrizione_nominale(s: str) -> str:
    """'dell'appartamento posto al quinto piano ... e del pertinenziale garage'
    -> 'appartamento posto al quinto piano ... e pertinenziale garage'."""
    s = s.strip().rstrip(",")
    s = re.sub(r"\b(?:dell'|dello |della |dei |degli |delle |del )", "", s)
    return s.strip()


def _dichiarazione_urbanistica(testo: str) -> str:
    """Riprende la dichiarazione urbanistica dell'atto notarile, adattandola al preliminare:
    'dichiara che le opere ... ; La parte venditrice dichiara inoltre che: * ...'."""
    s = re.sub(r"^dichiara che\s+", "", testo.strip(), flags=re.I)
    # la frase sull'abitabilita' viene gestita a parte
    s = re.split(r"\.?\s*La parte (?:venditrice|alienante) dichiara che l'(?:abitabilit|agibilit)", s, flags=re.I)[0]
    s = re.sub(r"\.?\s*La parte (?:venditrice|alienante) dichiara inoltre che:?\s*", "; inoltre ", s, flags=re.I)
    s = re.sub(r"\s*\*\s*", " ", s)
    s = re.sub(r"\s+in oggetto\b", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .;")
    return s


_RE_UNITA = re.compile(
    r"(?:mappale|particella|mapp\.|part\.|p\.lla|n\.)\s*(\d+)\s*(?:sub\.?|subalterno)\s*(\d+)(.*?)(?=(?:mappale|particella|mapp\.|part\.|p\.lla)\s*\d+\s*(?:sub|subalterno)|Confini|Nel trasferimento|$)",
    re.I)


def estrai_catastali(t: str) -> list[dict]:
    """Individua le unità immobiliari al Catasto Fabbricati."""
    m = re.search(r"Catasto\s+(?:dei\s+)?Fabbricati(.{0,2500})", t, re.I)
    if not m:
        return []
    blocco = m[1]
    comune = ""
    mc = re.search(r"COMUNE DI\s+([A-ZÀ-Ü' ]+?)\s*(?:=|-|\(|Sez|Foglio|,)", blocco, re.I)
    if mc:
        comune = tx.titolo(mc[1])
    sezione = ""
    ms = re.search(r"Sez(?:ione|\.)?\s*(?:urbana|urb\.)?\s*([A-Z])\b", blocco, re.I)
    if ms:
        sezione = ms[1].upper()
    foglio = ""
    mf = re.search(r"Foglio\s+(\d+)", blocco, re.I)
    if mf:
        foglio = mf[1]
    unita = []
    for mu in _RE_UNITA.finditer(blocco):
        resto = mu[3]
        cat = re.search(r"cat\.?\s*([A-Z])\s*/\s*(\d+)", resto, re.I)
        cl = re.search(r"cl(?:asse|\.)\s*(\w+)", resto, re.I)
        vani = re.search(r"vani\s+([\d,.]+)", resto, re.I)
        mq = re.findall(r"mq\.?\s*([\d,.]+)", resto, re.I)
        rendita = re.search(r"(?:R\.C\.|rendita(?: catastale)?)\s*(?:Euro|€)?\s*([\d.]+,\d{2})", resto, re.I)
        piano = re.search(r"P\.\s*([\w\-]+)", resto)
        mf2 = re.search(r"Foglio\s+(\d+)", blocco[:mu.start()], re.I)
        consistenza = ""
        if vani:
            consistenza = f"{vani[1].rstrip('.')} vani"
        elif mq:
            consistenza = f"{mq[-1].rstrip('.')} mq"
        unita.append({
            "comune": comune,
            "sezione": sezione,
            "foglio": (mf2[1] if mf2 else foglio),
            "particella": mu[1],
            "sub": mu[2],
            "categoria": f"{cat[1].upper()}/{cat[2]}" if cat else "",
            "classe": cl[1] if cl else "",
            "consistenza": consistenza,
            "rendita": rendita[1] if rendita else "",
            "piano": piano[1] if piano else "",
        })
    return unita


def persona_da_comparente(c: dict) -> dict:
    """Converte un comparente dell'atto nel formato 'persona' del preliminare."""
    parti = c["nominativo"].split()
    cf = c.get("codice_fiscale", "")
    cognome, nome = c["nominativo"], ""
    # separa cognome e nome usando il codice fiscale
    for i in range(1, len(parti)):
        cog, no = " ".join(parti[:i]), " ".join(parti[i:])
        if cfm.valido(cf) and cfm.codice_cognome(cog) == cf[:3] and cfm.codice_nome(no) == cf[3:6]:
            cognome, nome = cog, no
            break
    else:
        if len(parti) >= 2:
            cognome, nome = parti[0], " ".join(parti[1:])
    return {
        "tipo": "fisica",
        "cognome": cognome,
        "nome": nome,
        "sesso": cfm.sesso(cf),
        "luogo_nascita": c.get("luogo_nascita", ""),
        "prov_nascita": c.get("prov_nascita", ""),
        "data_nascita": c.get("data_nascita", ""),
        "codice_fiscale": cf,
        "stato_civile": c.get("stato_civile", ""),
        "_residenza_atto": c.get("residenza", ""),
    }
