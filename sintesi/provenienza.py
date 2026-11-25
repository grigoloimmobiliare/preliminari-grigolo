"""Analisi dell'atto di provenienza.

Gli estremi (notaio, data, repertorio, registrazione, trascrizione), le parti, i dati
catastali e la dichiarazione urbanistica sono letti dal modulo gia' usato per i
preliminari (app.estrazione.atto). Qui si aggiungono le tre parti su cui si concentra
la sintesi:
- URBANISTICA: costruzione ante '67, titoli edilizi con numero e data, condoni e
  sanatorie, agibilita', conformita' catastale, difformita' dichiarate;
- PROVENIENZA PRECEDENTE: il titolo con cui la parte venditrice aveva acquistato
  (atto, successione, donazione...) con notaio, data, repertorio e trascrizione;
- VINCOLI E GRAVAMI che possono limitare la circolazione dell'immobile (ipoteche,
  servitu', diritti reali di terzi, prelazioni, vincoli culturali, edilizia
  convenzionata, vincolo pertinenziale dei parcheggi, fondo patrimoniale, ...).
"""

from __future__ import annotations

import re
from pathlib import Path

from app import testo as tx
from app.estrazione import atto as atto_base


def estrai(percorso: Path) -> dict:
    grezzo, metodo = testo_atto(percorso)
    d = analizza_testo(grezzo, metodo)
    d["_file"] = percorso.name
    return d


# ------------------------------------------------------------------ testo

_PAROLE_COMUNI = {"di", "il", "la", "che", "del", "della", "in", "per", "al", "con", "dei", "le", "non", "una", "un",
                  "da", "nel", "alla", "sono", "atto", "dal", "ed", "lo", "gli", "parte", "quanto", "presente"}


def testo_leggibile(s: str) -> bool:
    """Il testo digitale di alcuni PDF (font con codifica interna) e' illeggibile: lo si riconosce
    dalla mancanza delle parole italiane piu' comuni."""
    parole = re.findall(r"[a-zà-ù]{2,}", s.lower())
    if len(parole) < 30:
        return False
    return sum(1 for p in parole if p in _PAROLE_COMUNI) / len(parole) > 0.08


_FINE_ATTO = re.compile(r"SEGUE QUANTO ALLEGATO|In originale firmato|consta di \w+ fogli|"
                        r"(?:scritto|dattiloscritto)\b.{0,60}\bfogli\b|\bF\.?\s?TO\b.{0,40}\bNOTAIO\b", re.I | re.S)


def ocr_pagina(percorso: Path, pagina: int) -> str:
    """OCR di una pagina d'atto: toglie le righe della carta notarile (che l'OCR legge come '|', 'i', 'I')
    e legge separatamente il corpo dell'atto e i margini, cosi' le annotazioni a margine
    (registrazione, trascrizione) non finiscono in mezzo alle frasi ma in fondo alla pagina."""
    import cv2
    import numpy as np

    from app.estrazione import ocr
    img = ocr.immagine_pagina(percorso, pagina, dpi=300)
    grigio = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    h, w = grigio.shape
    nero = cv2.threshold(grigio, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    # le righe della carta sono spesso chiare e sottili: soglia adattiva per trovarle
    tratti = cv2.adaptiveThreshold(grigio, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 10)
    verticali = cv2.morphologyEx(tratti, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 40)))
    orizzontali = cv2.morphologyEx(tratti, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (w // 8, 1)))
    righe = cv2.dilate(verticali | orizzontali, np.ones((5, 5), np.uint8))
    pulita = grigio.copy()
    pulita[righe > 0] = 255

    # colonne: le righe verticali lunghe (anche interrotte o un po' storte) separano corpo e margini
    somma = np.convolve(verticali.sum(axis=0) / 255, np.ones(15), "same")
    tagli = [0]
    for x in np.argsort(somma)[::-1]:
        if somma[x] < 0.25 * h:
            break
        if all(abs(x - t) > 0.05 * w for t in tagli[1:]):
            tagli.append(int(x))
    tagli = sorted(tagli) + [w]
    zone = [(a, b) for a, b in zip(tagli, tagli[1:]) if b - a > 0.08 * w]
    if not zone:
        zone = [(0, w)]
    corpo = max(zone, key=lambda z: z[1] - z[0])
    testo = ocr.ocr(pulita[:, corpo[0]:corpo[1]], psm=3)
    margini = []
    for a, b in zone:
        if (a, b) == corpo:
            continue
        inchiostro = ((nero[:, a:b] > 0) & (righe[:, a:b] == 0)).mean()
        if inchiostro > 0.002:
            margini.append(ocr.ocr(pulita[:, a:b], psm=4))
    return testo, "\n".join(margini)


def testo_atto(percorso: Path, massimo_ocr: int = 30) -> tuple[str, str]:
    """Restituisce (testo, metodo). Usa il testo digitale delle pagine leggibili e l'OCR per le altre.
    Le pagine scansionate in coda a un atto digitale (planimetrie, APE allegati) non vengono lette."""
    from app.estrazione import ocr
    pagine = ocr.testo_pdf(percorso)
    n = ocr.numero_pagine(percorso)
    if len(pagine) < n:
        pagine = pagine + [""] * (n - len(pagine))
    leggibili = [testo_leggibile(p) for p in pagine]
    con_testo = [len(p.strip()) > 50 for p in pagine]
    scansione = not any(con_testo)            # atto interamente scansionato
    testi, margini, ocr_usato, illeggibile = [], [], 0, False
    for i, p in enumerate(pagine):
        if leggibili[i]:
            testi.append(p)
        elif con_testo[i] or (scansione and ocr_usato < massimo_ocr):
            illeggibile = illeggibile or con_testo[i]
            p, margine = ocr_pagina(percorso, i)
            if margine.strip():
                margini.append(margine)
            ocr_usato += 1
            testi.append(p)
        else:
            continue                          # allegato scansionato di un atto digitale
        if _FINE_ATTO.search(testi[-1]):
            break                             # dopo la chiusura dell'atto ci sono solo gli allegati
    if not ocr_usato:
        return "\n".join(testi), "testo digitale"
    # annotazioni a margine (registrazione, trascrizione) in fondo, per non spezzare le frasi tra le pagine
    testo = "\n".join(testi) + ("\n\nANNOTAZIONI A MARGINE\n" + "\n".join(margini) if margini else "")
    return testo, "OCR (testo del PDF illeggibile)" if illeggibile else "OCR"


def _prepara(grezzo: str, metodo: str) -> str:
    """Toglie le righe di riempimento ('=====') e corregge errori tipici dell'OCR."""
    t = re.sub(r"[=_]{3,}", " ", grezzo)
    t = re.sub(r"(\w)-[ \t]*\n\s*(\w)", r"\1\2", t)        # parole spezzate a fine riga
    t = re.sub(r"[ \t]{2,}", " ", t)
    if metodo.startswith("OCR"):
        t = t.replace("|", " ")                                   # righe verticali della carta
        t = re.sub(r"(?m)^[ \t]*[‘\\ÎÌÍ`´]+", "", t)              # segni a inizio riga
        t = re.sub(r"(?m)^[ \t]*[^\w\s]{1,2}[ \t]*$", "", t)        # righe con un solo segno
        t = re.sub(r"(\w)-[ \t]*\n\s*(\w)", r"\1\2", t)
        t = re.sub(r"([a-zà-ù])-[ \t]+([a-zà-ù])", r"\1\2", t)      # "Co- mune" -> "Comune"
        t = re.sub(r"(?<=[a-zà-ù])0(?=[a-zà-ù])|(?<![\w])0(?=[a-zà-ù]{3})", "o", t)  # "0ggetto" -> "oggetto"
        t = t.replace("’", "'")
    return t


def analizza_testo(grezzo: str, metodo: str = "testo digitale") -> dict:
    grezzo = _prepara(grezzo, metodo)
    d = atto_base.analizza_testo(grezzo, metodo)
    t = atto_base._pulisci(grezzo)

    # parti: lettura propria (intestazioni "PARTE VENDITRICE/ACQUIRENTE", CF con spazi, nomi
    # in minuscolo); quella del modulo comune resta come riserva
    comparenti = comparenti_atto(t)
    if comparenti:
        d["comparenti"] = comparenti
        acquirenti = [c for c in comparenti if c.get("ruolo") == "acquirente"]
        if not acquirenti:
            acquirenti = _acquirenti_dal_verbo(t, comparenti)
        if acquirenti:
            d["intestatari"] = acquirenti
            d.pop("intestatari_testo", None)
    cf_intestatari = {c["codice_fiscale"] or c["nominativo"] for c in d.get("intestatari", [])}
    d["cedenti"] = [c for c in d.get("comparenti", []) if (c["codice_fiscale"] or c["nominativo"]) not in cf_intestatari] \
        if cf_intestatari else []

    d["data_atto"] = d.get("data_atto") or _data_atto(t)
    estremi = _estremi_atto(t)
    for k, v in estremi.items():
        if v and (not d.get(k) or k in ("tipo_atto", "notaio", "notaio_sede", "repertorio", "raccolta")):
            d[k] = v
    imm = _immobile(t)
    for k, v in imm.items():
        if v and (not d.get(k) or k in ("comune", "prov")):
            d[k] = v
    catastali = catastali_atto(t)
    if catastali:
        d["catastali"] = catastali

    d["prezzo"] = _prezzo(t)
    d["valori"] = _valori(t) if not d["prezzo"] else []
    d["prima_casa"] = bool(re.search(r"prima casa|nota II-bis|note? II bis|art(?:icolo|\.)\s*1,?\s*nota", t, re.I))
    d["ante_67"] = d.get("ante_67") or bool(re.search(
        r"anterior\w*\s+al(?:l')?\s*(?:giorno\s+)?0?1\s*°?\s*settembre\s+1967|prima\s+del\s+(?:giorno\s+)?0?1\s*°?\s*"
        r"settembre\s+1967|ante\s*['’]?\s*1?967|ante\s+1°?\s*settembre", t, re.I))
    d["urbanistica_testo"] = _dichiarazione_urbanistica(t, d.get("urbanistica_testo", ""))
    d["titoli_edilizi"] = titoli_edilizi(t)
    d["agibilita_testo"] = _agibilita(t) or d.get("agibilita") or ""
    d["note_urbanistiche"] = note_urbanistiche(t)
    d["ape"] = ape(t)
    d["provenienza_precedente"] = provenienza_precedente(t)
    d["trascrizione"] = _trascrizione_atto(t, d["provenienza_precedente"]["testo"]) or d.get("trascrizione", "")
    d["vincoli"] = vincoli_gravami(t)
    return d


# ------------------------------------------------------------------ parti

_RUOLI = re.compile(r"PARTE\s+(VENDITRICE|ALIENANTE|CEDENTE|DONANTE|ACQUIRENTE|ACQUISTANTE|CESSIONARIA|DONATARIA|"
                    r"COMPRATRICE|PROMITTENTE\s+VENDITRICE|PROMISSARIA\s+ACQUIRENTE)", re.I)
_RE_PERSONA = re.compile(
    r"(?:(?<=[\s:;(])|^)[-–•]?\s*(?:(?:il|la)\s+)?(?:signor[ae]?\s+|sig\.(?:ra)?\s+)?"
    r"([A-ZÀ-Ü][A-ZÀ-Ü'’]+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü'’]+){1,4}),?\s+nat[oa]\s+(?:a|in)\s+(.+?)\s+il\s+(?:giorno\s+)?"
    r"(\d{1,2}\s*°?\s+[a-zà-ù]+\s+\d{4}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})"
    r"(?:\s+e|,)?\s+(?:residente|domiciliat\w+)\s+(?:a|in)\s+((?:(?!\bnat[oa]\s+(?:a|in)\b).){1,160}?),?\s*(?:codice\s+fiscale|C\.\s?F\.)\s*:?\s*"
    r"([A-Z0-9](?:\s?[A-Z0-9]){15})")
_RE_SOCIETA = re.compile(
    r"[-–•]?\s*(?:la\s+(?:società\s+)?)?\"?([A-ZÀ-Ü0-9][A-ZÀ-Ü0-9&'’.\- ]{2,80}?\s(?:S\.?\s?R\.?\s?L\.?|S\.?\s?P\.?\s?A\.?|"
    r"S\.?\s?N\.?\s?C\.?|S\.?\s?A\.?\s?S\.?|S\.?\s?S\.?|SOCIETA'?\s+[A-Z ]+?)\b[^,]{0,40}?)\"?,?\s+con\s+sede\s+(?:legale\s+)?in\s+"
    r"(.+?),.{0,250}?(?:codice\s+fiscale|C\.\s?F\.|partita\s+IVA)[^0-9]{0,60}(\d{11})", re.I)


def _fine_comparizione(t: str) -> int:
    m = re.search(r"\bART(?:ICOLO)?\.?\s*1\b|convengono\s+e\s+stipulano|stipulano\s+(?:e\s+convengono\s+)?quanto\s+segue|"
                  r"premesso\s+che|PREMESSO", t, re.I)
    return m.start() if m else min(len(t), 6000)


def _ruolo(intro: str, pos: int) -> str:
    ruolo = ""
    for m in _RUOLI.finditer(intro, 0, pos):
        r = m[1].lower()
        ruolo = "acquirente" if re.match(r"acquirente|acquistante|cessionaria|donataria|compratrice|promissaria", r) \
            else "venditrice"
    return ruolo


def comparenti_atto(t: str) -> list[dict]:
    intro = t[:_fine_comparizione(t)]
    # i testimoni sono elencati prima di "SONO PRESENTI": si parte da li'
    mi = None
    for mi in re.finditer(r"SONO\s+(?:PRESENTI|COMPARSI|INTERVENUTI)|sono\s+(?:presenti|comparsi)\s+i\s+signori|COMPAIONO|"
                          r"è\s+(?:presente|comparso)", intro):
        pass
    inizio = mi.end() if mi else 0
    out = []
    for m in _RE_PERSONA.finditer(intro, inizio):
        cf = re.sub(r"\s", "", m[5]).upper()
        luogo, prov = m[2].strip(" ,"), ""
        mp = re.match(r"(.+?)\s*\((\w{2})\)", luogo)
        if mp:
            luogo, prov = mp[1], mp[2]
        coda = intro[m.end():m.end() + 300]
        prossimo = _RE_PERSONA.search(coda)
        if prossimo:
            coda = coda[:prossimo.start()]
        stato = ""
        ms = re.search(r"dichiara(?:no)?\s+di\s+essere\s+(?:di\s+stato\s+civile\s+)?(.{3,90}?)(?:\s+nonch[eé]|;|\.\s|,\s|"
                       r"\s+e\s+(?:di\s+)?libero|\s+[-–]\s|[\s:;]+(?:I|1|Le|Gli)\s+(?:comparenti|costituiti|parti)|\s+SONO\s|$)", coda)
        if ms:
            stato = ms[1].strip()
        res = re.sub(r"\s+", " ", m[4]).strip(" ,")
        out.append({
            "nominativo": re.sub(r"\s+", " ", m[1]).strip(),
            "luogo_nascita": tx.titolo(luogo),
            "prov_nascita": prov or tx.provincia_da_comune(luogo),
            "data_nascita": tx.formato_data(m[3]),
            "residenza": res,
            "codice_fiscale": cf,
            "stato_civile": stato,
            "ruolo": _ruolo(intro, m.start()),
        })
    for m in _RE_SOCIETA.finditer(intro):
        nome = re.sub(r"\s+", " ", m[1]).strip(" -\"")
        if any(nome in c["nominativo"] or c["nominativo"] in nome for c in out):
            continue
        out.append({"nominativo": nome, "sede": tx.titolo(m[2].strip()), "codice_fiscale": m[3], "luogo_nascita": "",
                    "prov_nascita": "", "data_nascita": "", "residenza": "", "stato_civile": "",
                    "ruolo": _ruolo(intro, m.start())})
    return out


def _acquirenti_dal_verbo(t: str, comparenti: list[dict]) -> list[dict]:
    """'... dona ... A) al figlio GEMIN ALBERTO, che accetta ... B) al figlio GEMIN MARIO, che accetta':
    ogni acquirente con le unita' descritte dopo il suo nome."""
    nomi = {c["nominativo"].upper(): c for c in comparenti}
    trovati = []
    for m in re.finditer(r"\b(?:a|al|alla|ai|alle|in\s+favore\s+d\w*|a\s+favore\s+d\w*)\s+(?:propri[oa]\s+)?"
                         r"(?:figli[oa]|nipote|coniuge|marito|moglie|fratello|sorella|signor[ae]?|sig\.(?:ra)?)?\s*"
                         r"([A-ZÀ-Ü][A-Za-zÀ-ü'’]+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü'’]+){1,3}),?\s+che\s+(?:accett|acquist)", t):
        nome = re.sub(r"\s+", " ", m[1]).upper()
        c = nomi.get(nome) or next((x for k, x in nomi.items() if k.split()[0] in nome and k.split()[-1] in nome), None)
        if c and all(c is not x[0] for x in trovati):
            trovati.append((c, m.end()))
    if not trovati:
        m = re.search(r"\b(?:vend\w*|don\w*|ced\w*|trasferisc\w*)\b(.{0,400}?)\bche\s+(?:accett|acquist)", t, re.I | re.S)
        if not m:
            return []
        blocco = m[1].upper()
        return [c for c in comparenti if c["nominativo"].split()[0].upper() in blocco]
    if len(trovati) > 1:
        for i, (c, pos) in enumerate(trovati):
            fine = trovati[i + 1][1] if i + 1 < len(trovati) else pos + 1500
            unita = catastali_atto(t[pos:fine], t[:pos])
            if unita:
                c["unita_ricevute"] = ", ".join(f"Fg. {u['foglio']} part. {u['particella']} sub {u['sub']}" for u in unita)
    return [c for c, _ in trovati]


def _data_atto(t: str) -> str:
    inizio = t[:2500]
    m = re.search(r"\((\d{1,2}\s*[./\-]\s*\d{1,2}\s*[./\-]\s*\d{4})\)", inizio)
    if m:
        return tx.formato_data(m[1])
    m = re.search(r"(?:il\s+)?giorno\s+([a-zà-ù']+)\s+(?:del\s+mese\s+di\s+)?([a-z]+)\s+(?:dell'anno\s+)?([a-z]+)", inizio, re.I)
    if m and m[2].lower() in tx.MESI:
        g, a = tx.lettere_in_numero(m[1]), tx.lettere_in_numero(m[3])
        if g and a:
            return tx.formato_data(f"{g}/{tx.MESI.index(m[2].lower()) + 1}/{a}")
    return ""


# ------------------------------------------------------------------ immobile

_TIPI_UNITA = (r"appartament\w+|garage|box|autorimess\w+|posto\s+auto(?:\s+(?:scoperto|coperto))?|magazzin\w+|cantin\w+|"
               r"negozi\w+|uffici\w+|villett\w+|villa|abitazion\w+|casa|terreno|laboratori\w+|capannon\w+|soffitt\w+|"
               r"locale|deposit\w+|porzione\s+di\s+fabbricato|unit[aà]\s+immobiliare")


def _titolo_comune(s: str) -> str:
    """'MASERADA SUL PIAVE' / 'Maserada sul Piave' -> 'Maserada sul Piave'."""
    parole = tx.titolo(s).split()
    return " ".join(p.lower() if i and p.lower() in ("sul", "sulla", "sui", "al", "alla", "di", "del", "della", "dei",
                                                       "in", "d'", "de", "nel", "sotto", "sopra") else p
                    for i, p in enumerate(parole))


def _immobile(t: str) -> dict:
    out = {}
    m = re.search(r"sit[oa]\s+in\s+(?:Comune\s+di\s+)?([A-ZÀ-Ü][\w'’]*(?:\s+(?:di|del|della|dei|sul|sulla|sui|al|in|d'|"
                  r"[A-ZÀ-Ü][\w'’]*))*?)\s*(?:\(([A-Z]{2})\))?,?\s+(?:alla\s+|in\s+|nella\s+)?"
                  r"((?:Via|Viale|Piazza|Piazzale|Corso|Vicolo|Largo|Strada|Contrada|Localit[aà]|Borgo|Riviera|Galleria)"
                  r"\s[^,;:]{2,60}?(?:n\.\s?\d+\w*(?:/\w+)?)?(?:\s*\([^)]{0,40}\))?)(?=[,;:]|\s+e\s+(?:più\s+)?precisamente)", t)
    if m:
        out["comune"] = _titolo_comune(m[1])
        out["prov"] = m[2] or tx.provincia_da_comune(m[1])
        out["indirizzo"] = m[3].strip()
    else:
        mc = re.search(r"sit[oa]\s+in\s+Comune\s+di\s+([A-ZÀ-Ü][\w'’]*(?:\s+(?:di|del|della|sul|sulla|al|in|[A-ZÀ-Ü][\w'’]*))*?)"
                       r"\s*(?:\(([A-Z]{2})\))?[,.;\s]", t)
        if mc:
            out["comune"] = _titolo_comune(mc[1])
            out["prov"] = mc[2] or tx.provincia_da_comune(mc[1])
        unita = catastali_atto(t)
        if unita and unita[0].get("indirizzo"):
            out["indirizzo"] = unita[0]["indirizzo"]
    elenco = re.findall(r"[-–•]\s*(" + _TIPI_UNITA + r")\b[^;:]{0,80}?\b(?:(?:posto|sit[oa]|ubicat[oa])\s+)?al\s+(piano\s+[\w\-]+(?:\s+e\s+[\w\-]+)?)",
                        t, re.I)
    if not elenco:
        elenco = re.findall(r"costituit[ao]\s+da\s+(" + _TIPI_UNITA + r")\b[^;:]{0,40}?\bal\s+(piano\s+[\w\-]+)", t, re.I)
    if elenco:
        voci = [f"{a.lower()} al {p}" for a, p in elenco]
        uniche = list(dict.fromkeys(voci))
        out["descrizione"] = "; ".join(v + (f" ({voci.count(v)} unità)" if voci.count(v) > 1 else "") for v in uniche)
    return out


_RE_UNITA_ATTO = re.compile(
    r"(?:particella|mappale|\bm\.?\s?n\.?(?=\s*\d)|mapp\.?|part\.|p\.lla|numero)\s*(?:n\.?\s*)?(\d+)[,\s\-]+"
    r"sub(?:alterno)?[.,]?\s*(?:n\.?\s*)?(\d+)", re.I)
_RE_BENI_COMUNI = re.compile(r"part[ei]\s+comun|custode|b\.?\s?c\.?\s?n\.?\s?c|bene\s+comune|quota\s+di\s+propriet|confinant", re.I)


def catastali_atto(t: str, prima: str = "") -> list[dict]:
    """Unita' al Catasto Fabbricati: 'Sezione C, Foglio n.5, particella n.218, sub.14, ... Cat. A/3, ...'
    oppure 'SEZIONE E - FOGLIO 2 / m.n. 1379 sub. 61 - ... categ. A/2 ...'. Foglio e sezione possono stare
    in un'intestazione precedente ('prima' = testo che precede, per i brani)."""
    trovate = list(_RE_UNITA_ATTO.finditer(t))
    unita = []
    for i, m in enumerate(trovate):
        fine = trovate[i + 1].start() if i + 1 < len(trovate) else m.end() + 700
        resto = t[m.end():min(fine, m.end() + 700)]
        cat = re.search(r"cat(?:egoria|eg\.?|\.)?\s*([A-F])\s*/\s*(\d{1,2})", resto, re.I)
        if not cat:
            continue  # beni comuni, confini: non sono unita' trasferite
        contesto = (prima + t[:m.start()])[-160:]
        if _RE_BENI_COMUNI.search(contesto[-110:]):
            continue
        precedente = (prima + t[:m.start()])[-600:]
        fogli = re.findall(r"Foglio\s*(?:n\.?\s*)?(\d+)", precedente, re.I)
        sezioni = re.findall(r"Sez(?:ione|\.)?\s*(?:urbana\s+|urb\.\s*)?([A-Z])\b", precedente, re.I)
        if not fogli:
            continue
        cl = re.search(r"cl(?:asse|\.)\s*(\w+)", resto, re.I)
        vani = re.search(r"vani\s*(?:catastali\s*)?([\d,.]+)", resto, re.I)
        cons = re.search(r"consistenza\s*(?:catastale\s*)?(?:di\s*)?mq\.?\s*([\d,.]+)|mq\.?\s*([\d,.]+)", resto, re.I)
        sup = re.search(r"superficie\s+catastale\s+(?:totale\s+)?(?:di\s+)?mq\.?\s*([\d,.]+)", resto, re.I)
        rendita = re.search(r"(?:R\.?\s?C\.?|rendita(?:\s+catastale)?)\s*(?:di\s*)?(?:Euro|€)?\s*([\d.]+,\d{2})", resto, re.I)
        piano = re.search(r"\bpiano\s+([\w\-]+)|\bP\.\s*([\w\-]+)", resto, re.I)
        indirizzo = re.search(r"((?:Via|Viale|Piazza|Piazzale|Corso|Vicolo|Largo|Strada|Contrada|Galleria|Borgo|Riviera|"
                              r"Localit[aà])\s[^,;\-]{2,50}?\s(?:n\.\s?)?\d+\w*(?:/\w+)?)", resto)
        consistenza = f"{vani[1].rstrip('.,')} vani" if vani else (f"{(cons[1] or cons[2]).rstrip('.,')} mq" if cons else "")
        u = {"sezione": sezioni[-1].upper() if sezioni else "", "foglio": fogli[-1], "particella": m[1], "sub": m[2],
             "categoria": f"{cat[1].upper()}/{cat[2]}", "classe": cl[1] if cl else "", "consistenza": consistenza,
             "superficie": sup[1].rstrip(".,") if sup else "", "rendita": rendita[1] if rendita else "",
             "piano": (piano[1] or piano[2]) if piano else "", "comune": "",
             "indirizzo": indirizzo[1].strip() if indirizzo else ""}
        if not any((x["foglio"], x["particella"], x["sub"]) == (u["foglio"], u["particella"], u["sub"]) for x in unita):
            unita.append(u)
    return unita


# ------------------------------------------------------------------ estremi dell'atto

def _estremi_atto(t: str) -> dict:
    """Notaio, repertorio, data, tipo e registrazione scritti in forme non lette dal modulo comune."""
    out = {}
    corpo = t
    m = re.search(r"(?:Davanti|Innanzi|Avanti)\s+a\s+me,?\s+(?:dott(?:or(?:essa)?|\.(?:ssa)?)?\.?\s*|dr\.?\s*)?"
                  r"([A-ZÀ-Ü][A-Za-zÀ-ü'’]+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü'’]+){1,3}),?\s+(?i:notaio)", t)
    if m:
        out["notaio"] = tx.titolo(m[1])
        corpo = t[max(0, m.start() - 1500):]
        ms = re.search(r"(?i:notai[oa])\s+(?:residente\s+)?(?:in|a)\s+([A-ZÀ-Ü][\w'’ ]+?)[,.]|"
                       r"Distretto\s+Notarile\s+di\s+([A-ZÀ-Ü][\w'’ ]+?),?\s+(?:mia|con)\s+(?:residenza|sede)", t[m.start():m.start() + 300])
        if ms:
            out["notaio_sede"] = tx.titolo(ms[1] or ms[2])
    mr = re.search(r"N\.?\s*([\d.]+)\s+di\s+Rep(?:ertorio|\.)", corpo, re.I)
    if mr:
        out["repertorio"] = mr[1].strip(".")
    mr = re.search(r"N\.?\s*([\d.]+)\s+di\s+Racc(?:olta|\.)", corpo, re.I)
    if mr:
        out["raccolta"] = mr[1].strip(".")
    md = re.search(r"L'anno\s+(\d{4})\s*(?:\([^)]*\))?\s*(?:il\s+)?giorno\s+(\d{1,2})\s*(?:\([^)]*\))?\s*"
                   r"(?:del\s+mese\s+di\s+)?([a-z]+)", corpo, re.I)
    if md and md[3].lower() in tx.MESI:
        out["data_atto"] = tx.formato_data(f"{md[2]}/{tx.MESI.index(md[3].lower()) + 1}/{md[1]}")
    mt = re.search(r"\b(COMPRAVENDITA|DONAZION[EI]|DIVISIONE|PERMUTA|ASSEGNAZIONE|CESSIONE|DECRETO DI TRASFERIMENTO)\b"
                   r"[\s\S]{0,40}?REPUBBLICA\s+ITALIANA", corpo)
    if mt:
        out["tipo_atto"] = "donazione" if mt[1].startswith("DONAZION") else mt[1].lower()
    mg = re.search(r"Registrat[oa]\s+il\s+(\d{1,2}/\d{1,2}/\d{4})\s+a\s+([A-ZÀ-Ü][\w' ]+?)\s+(?:al\s+)?n\.?,?\s*(\d+)\s*"
                   r"(?:serie\s+(\w+))?", t, re.I)
    if mg:
        out["registrazione"] = (f"registrato a {tx.titolo(mg[2])} il {tx.formato_data(mg[1])} al n. {mg[3]}"
                                + (f" serie {mg[4]}" if mg[4] else ""))
    return out


def _valori(t: str) -> list[str]:
    """Valori dichiarati negli atti senza prezzo (donazioni, divisioni)."""
    return [tx.formato_euro(v) for v in re.findall(r"(?:del\s+)?valore\s+(?:dichiarato\s+)?(?:di|pari\s+a)\s+(?:Euro|€)\s*([\d.]+(?:,\d{2})?)",
                                                   t, re.I) if tx.parse_importo(v)]


# ------------------------------------------------------------------ APE

def ape(t: str) -> dict:
    m = re.search(r"attestat\w+\s+di\s+(?:prestazione|certificazione)\s+energetica|\bA\.?\s?P\.?\s?E\.?\b|\bA\.?\s?C\.?\s?E\.?\b", t, re.I)
    if not m:
        return {}
    finestra = t[m.start():m.start() + 700]
    out = {"testo": _frase(t, m.start(), 700)}
    md = re.search(r"(?:in\s+data|redatto\s+il|del|datato)\s+" + r"(\d{1,2}\s*°?\s+[a-zà-ù]+\s+\d{4}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})",
                   finestra, re.I)
    if md:
        out["data"] = tx.formato_data(md[1])
        d = tx.parse_data(md[1])
        if d:
            try:
                out["scadenza"] = d.replace(year=d.year + 10).strftime("%d/%m/%Y")
            except ValueError:  # 29 febbraio
                out["scadenza"] = d.replace(year=d.year + 10, day=28).strftime("%d/%m/%Y")
    mc = re.search(r"classe\s+(?:energetica\s+)?(?:di\s+rendimento\s+)?[\"“”']?([A-G](?:\s?\d|\+{1,4})?)[\"“”']?(?![a-z])", t[m.start():m.start() + 1500], re.I)
    if mc:
        out["classe"] = mc[1].upper().replace(" ", "")
    mt = re.search(r"(?:dal|redatto\s+da|predisposto\s+.{0,40}?dal)\s+((?:Geom|Ing|Arch|Dott|Per\.?\s?Ind)\.?\s+[A-ZÀ-Ü][\w']+(?:\s+[A-ZÀ-Ü][\w']+)?)", finestra)
    if mt:
        out["tecnico"] = mt[1]
    return out


# ------------------------------------------------------------------ prezzo

def _prezzo(t: str) -> str:
    for m in re.finditer(r"\bprezzo\b", t, re.I):
        finestra = t[m.end():m.end() + 260]
        mi = re.search(r"(?:euro|€|eur)\.?\s*([\d.]{1,12}(?:,\d{2})?)(?!\d)", finestra, re.I)
        if mi and tx.parse_importo(mi[1]):
            return tx.formato_euro(mi[1])
    return ""


# ------------------------------------------------------------ titoli edilizi

TIPI_TITOLO = [
    ("Licenza edilizia", r"licenz[ae]\s+(?:edilizi[ae]|di\s+costruzione|per\s+(?:l[ae]\s+)?(?:costruzione|esecuzione))"),
    ("Nulla osta", r"nulla\s*-?\s*osta\s+(?:per\s+(?:l'esecuzione\s+di\s+)?lavori|edilizio)"),
    ("Concessione edilizia in sanatoria", r"concession[ei]\s+(?:edilizi[ae]\s+)?in\s+sanatoria"),
    ("Concessione edilizia", r"concession[ei]\s+(?:edilizi[ae]|ad\s+edificare)"),
    ("Permesso di costruire in sanatoria", r"permess[oi]\s+di\s+costruire\s+in\s+sanatoria"),
    ("Permesso di costruire", r"permess[oi]\s+di\s+costruire"),
    ("Autorizzazione edilizia", r"autorizzazion[ei]\s+edilizi[ae]"),
    ("Accertamento di conformità", r"accertament[oi]\s+di\s+conformit[aà]"),
    ("D.I.A.", r"\bD\.?\s?I\.?\s?A\.?(?=[\s,(n])|denuncia\s+di\s+inizio\s+(?:di\s+)?attivit[aà]"),
    ("S.C.I.A.", r"\bS\.?\s?C\.?\s?I\.?\s?A\.?(?=[\s,(n])|segnalazion[ei]\s+certificat[ae]\s+di\s+inizio\s+(?:di\s+)?attivit[aà]"),
    ("C.I.L.A.", r"\bC\.?\s?I\.?\s?L\.?\s?A\.?(?=[\s,(n])|comunicazion[ei]\s+(?:di\s+)?inizio\s+lavori\s+asseverat[ae]"),
    ("C.I.L.", r"\bC\.?\s?I\.?\s?L\.?(?=[\s,(n])|comunicazion[ei]\s+(?:di\s+)?inizio\s+lavori(?!\s+asseverat)"),
    ("Condono edilizio", r"condono\s+edilizio|domand[ae]\s+di\s+(?:condono|sanatoria)|istanz[ae]\s+di\s+(?:condono|sanatoria)"),
]

_RE_NUMERO = re.compile(r"\b(?:n\.?|numero|nr\.?|prot(?:ocollo)?\.?(?:\s+gen(?:erale)?\.?)?\s*n?\.?|pratica\s+(?:edilizia\s+)?n\.?)\s*([\w/.\-]*\d[\w/.\-]*)", re.I)
_RE_DATA = re.compile(r"\b(?:del|in\s+data|rilasciat\w+\s+(?:il|in\s+data)|il|presentat\w+\s+(?:il|in\s+data))\s+"
                      r"(\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4}|\d{1,2}\s*°?\s+[a-z]+\s+\d{4})", re.I)


def titoli_edilizi(t: str) -> list[dict]:
    trovati: list[dict] = []
    occupati: list[tuple[int, int]] = []
    for nome, regex in TIPI_TITOLO:
        for m in re.finditer(regex, t, re.I):
            if any(a <= m.start() < b for a, b in occupati):
                continue  # gia' preso da un tipo piu' specifico (es. "in sanatoria")
            if re.search(r"(?:variante|riferimento|relativ\w*|conform\w*)\s+(?:alla|al|all'|alle|ai)\s*$",
                         t[max(0, m.start() - 30):m.start()], re.I):
                continue  # rimando a un titolo gia' citato
            occupati.append((m.start(), m.end()))
            finestra = t[m.end():m.end() + 160]
            # la finestra si ferma al titolo successivo
            for stop in re.finditer(r";|(?-i:\.\s+[A-Z])|" + "|".join(r for _, r in TIPI_TITOLO), finestra, re.I):
                if stop.start() > 0 and not re.search(r"(?:variante|riferimento|relativ\w*)\s+(?:alla|al|all'|alle|ai)\s*$",
                                                      finestra[:stop.start()], re.I):
                    finestra = finestra[:stop.start()]
                    break
            numero = _RE_NUMERO.search(finestra)
            data = _RE_DATA.search(finestra)
            if not numero and not data:
                # citazione generica ("non sono state rilasciate concessioni"): si ignora
                continue
            dopo = t[m.end():m.end() + 40]
            if "sanatoria" not in nome.lower() and re.match(r"\s*in\s+sanatoria", dopo, re.I):
                nome_voce = nome + " in sanatoria"
            elif re.match(r"\s*in\s+variante", dopo, re.I):
                nome_voce = nome + " in variante"
            else:
                nome_voce = nome
            voce = {
                "tipo": nome_voce,
                "numero": numero[1].rstrip(".,") if numero else "",
                "data": tx.formato_data(data[1]) or data[1] if data else "",
                "testo": _taglia_al_titolo_successivo(_estratto(t, m.start()), m.end() - m.start()),
            }
            if any(v["tipo"] == voce["tipo"] and v["numero"] == voce["numero"] and v["data"] == voce["data"] for v in trovati):
                continue
            trovati.append(voce)
    trovati.sort(key=lambda v: (tx.data_iso(v["data"]) or "9999", v["tipo"]))
    return trovati


def _taglia_al_titolo_successivo(s: str, da: int) -> str:
    for m in re.finditer(r"\s+(?:e\s+(?:di\s+)?|nonch[eé]\s+|,\s*)?(?:" + "|".join(r for _, r in TIPI_TITOLO) + ")", s[da:], re.I):
        if re.search(r"(?:variante|riferimento|relativ\w*)\s+(?:alla|al|all'|alle|ai)$", s[:da + m.start()].rstrip(), re.I):
            continue  # "in variante alla concessione n. ...": stesso titolo
        return s[:da + m.start()].strip(" ,")
    return s


def _estratto(t: str, pos: int, massimo: int = 260) -> str:
    """Testo dalla posizione 'pos' fino al punto e virgola o alla fine della frase."""
    s = t[pos:pos + massimo]
    m = re.search(r";|(?<!\bn)(?<!\bprot)(?<!\bgen)(?<!\bart)\.\s+(?=[A-Z])", s)
    if m:
        return s[:m.start()].strip(" ,")
    return s.rsplit(" ", 1)[0].strip(" ,") + (" …" if len(t) > pos + massimo else "")


def _agibilita(t: str) -> str:
    frasi = []
    for m in re.finditer(r"agibilit\w*|abitabil\w*", t, re.I):
        f = _frase(t, m.start(), 700)
        if f in frasi or any(f in x for x in frasi) or re.search(r"segnalazione\s+certificata\s+di\s+agibilit\w+\.?$", f, re.I) \
                and "rilasciat" not in f:
            continue
        frasi.append(f)
        if len(frasi) >= 2:
            break
    return " ".join(frasi)


def _frase(t: str, pos: int, massimo: int = 500) -> str:
    """Frase che contiene la posizione 'pos' (delimitata da punto o punto e virgola)."""
    inizio = max(t.rfind(". ", 0, pos), t.rfind("; ", 0, pos), t.rfind(": ", 0, pos))
    inizio = 0 if inizio < 0 else inizio + 2
    if pos - inizio > massimo // 2:
        inizio = t.rfind(" ", 0, pos - massimo // 2) + 1
    fine = len(t)
    for sep in (". ", "; "):
        i = t.find(sep, pos)
        while i > 0 and re.search(r"(?:p\.A|r\.l|\.n\.c|\.a\.s|\bn|\bnn|\bvol|\bart|\bsig|\bdott|\bprot|\bgen|\bcod|\bciv|\bL|\bD\.P\.R|\bRep|\bRacc|\bpag|\bsez|\bmapp|\bsub)$", t[max(0, i - 6):i], re.I):
            i = t.find(sep, i + 2)
        if 0 < i < fine:
            fine = i + 1
    if fine - pos > massimo // 2 + 200:
        fine = t.find(" ", pos + massimo // 2 + 150)
        fine = len(t) if fine < 0 else fine
        return _senza_numero_articolo(t[inizio:fine].strip()) + " …"
    return _senza_numero_articolo(t[inizio:fine].strip())


def _senza_numero_articolo(f: str) -> str:
    """'4) La parte venditrice...' (resto di 'ART. 4)') -> 'La parte venditrice...'."""
    f = re.sub(r"^(?:ART(?:ICOLO)?\.?\s*)?\d+\s*[).°=-]\s*", "", f, flags=re.I)
    return re.sub(r"^(?:[A-ZÀ-Ü'’]{3,}\s+){1,4}(?=[A-ZÀ-Ü][a-zà-ù])", "", f)   # "PRECISAZIONI La vendita..."


_RE_URBANISTICA = (r"licenz\w+\s+(?:edilizi|di\s+costruzione)|concession\w+\s+edilizi|permess\w+\s+di\s+costruire|"
                   r"1\s*°?\s+settembre\s+1967|anteriorment\w+\s+al.{0,20}1967|D\.?P\.?R\.?\s*(?:n\.\s*)?380|"
                   r"47/(?:19)?85|urbanistic\w+|condono|sanatoria|\bS\.?C\.?I\.?A\b|\bD\.?I\.?A\b")


def _dichiarazione_urbanistica(t: str, letta: str) -> str:
    """Testo della dichiarazione urbanistica: quello letto dal modulo comune se parla davvero di
    urbanistica, altrimenti l'articolo dell'atto che contiene i riferimenti edilizi."""
    mt = re.search(r"\bART(?:ICOLO)?\.?\s*\d+\s*[).°-]?\s*(?:[A-ZÀ-Ü]+\s+){0,3}URBANISTIC[A-ZÀ-Ü]*(?:\s+[A-ZÀ-Ü]+\b)*", t)
    if mt:
        resto = t[mt.end():mt.end() + 3000]
        fine = re.search(r"\sART(?:ICOLO)?\.?\s*\d+\s*[).°-]", resto)
        return (resto[:fine.start()] if fine else resto).strip()
    if letta and re.search(_RE_URBANISTICA, letta, re.I) and not re.search(r"abitabil|agibil", letta[:200], re.I):
        return letta
    m = re.search(_RE_URBANISTICA, t, re.I)
    if not m:
        return ""
    articoli = [x.end() for x in re.finditer(r"(?:\bART(?:ICOLO)?|\bArticolo)\.?\s*\d+[\s).°=-]*", t[:m.start()])]
    if articoli and m.start() - articoli[-1] < 1500:
        inizio = articoli[-1]
    else:
        frasi = [x.end() for x in re.finditer(r"(?-i:\.\s+(?=[A-Z]))", t[max(0, m.start() - 600):m.start()])]
        inizio = max(0, m.start() - 600) + frasi[-1] if frasi else max(0, m.start() - 300)
    resto = t[inizio:inizio + 1500]
    fine = re.search(r"\sART(?:ICOLO)?\.?\s*\d+|\sREGISTRATO\b|\sANNOTAZIONI A MARGINE|Ciascuna parte", resto[20:])
    testo = resto[:20 + fine.start()] if fine else resto
    return testo.strip()


def _trascrizione_atto(t: str, brani_provenienza: list[str]) -> str:
    """Trascrizione dell'atto stesso: annotazione in testa o in fondo all'atto, esclusi i brani
    della provenienza (che citano le trascrizioni dei titoli precedenti)."""
    for b in brani_provenienza:
        t = t.replace(b, " ")
    # "Trascritto a: TREVISO il 26 luglio 2023 n. reg. generale: 28381 n. reg. particolare: 20380" (anche piu' note)
    note = []
    for m in re.finditer(r"Trascritt[oa]\s+a:?\s+([A-ZÀ-Üa-zà-ü ]+?)\s+(?:il|in\s+data)\s+" + _DATA +
                         r"\s+n\.?\s*reg(?:istro|\.)?\s*gen(?:erale|\.)?\s*:?\s*(\d+)\s+n\.?\s*reg(?:istro|\.)?\s*part(?:icolare|\.)?\s*:?\s*(\d+)",
                         t, re.I):
        note.append((m[1].strip(), tx.formato_data(m[2]) or m[2], f"{m[3]}/{m[4]}"))
    if not note:
        # note di trascrizione dell'Agenzia delle Entrate allegate all'atto
        for m in re.finditer(r"Registro\s+generale\s+n\.?\s*(\d+)\s+Registro\s+particolare\s+n\.?\s*(\d+)\s+"
                             r"Presentazione\s+n\.?\s*\d+\s+del\s+(\d{1,2}/\d{1,2}/\d{4})", t, re.I):
            luogo = re.search(r"Direzione\s+Provinciale\s+di\s+([A-ZÀ-Ü][\w' ]+?)\s+(?:Ufficio|Registro)", t[max(0, m.start() - 300):m.end()], re.I)
            note.append((luogo[1].strip() if luogo else "", m[3], f"{m[1]}/{m[2]}"))
    if note:
        unici = list(dict.fromkeys(note))
        luogo, data = unici[0][0], unici[0][1]
        numeri = " e ".join(n for _, _, n in unici)
        return f"trascritto a {tx.titolo(luogo)} il {data} ai nn. {numeri}".replace("a  il", "il")
    regex = re.compile(r"(trascritt[oa])\s+(?:presso\s+\S+\s+)?a\s+([A-ZÀ-Üa-zà-ü ]+?)\s+(?:in data|il)\s+"
                       r"(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\s+a[il]?\s+(?:nn?\.?|numeri)\s*([\d/ ]+)", re.I)
    tutte = list(regex.finditer(t))
    maiuscole = [x for x in tutte if x[1].isupper()]       # annotazione a margine "TRASCRITTO A ..."
    coda = [x for x in tutte if x.start() > len(t) - 2500]
    m = (maiuscole or coda or [x for x in tutte if x.start() < 1200] or [None])[-1 if not maiuscole else 0]
    if m:
        m = [m[0], m[2], m[3], m[4]]
    if not m:
        return ""
    return f"trascritto a {tx.titolo(m[1].strip())} il {tx.formato_data(m[2])} ai nn. {re.sub(r'\s+', '', m[3])}"


# ---------------------------------------------------------- urbanistica: note

NOTE_URBANISTICHE = [
    ("Conformità catastale", r"conformit[aà]\s+(?:allo\s+stato\s+di\s+fatto\s+)?(?:dei\s+dati\s+catastali|catastale|delle\s+planimetrie)|"
                             r"29,?\s+comma\s+1[\s-]*bis|planimetri\w+\s+depositat\w+\s+in\s+catasto"),
    ("Difformità o abusi dichiarati", r"difformit\w+|abus\w+\s+edilizi|opere\s+abusiv|non\s+conform\w+\s+(?:al|alla|ai|agli|urbanistic)|"
                                      r"in\s+assenza\s+(?:del|di)\s+(?:titol|permess|licenz)"),
    ("Sanatorie in corso", r"pratic\w+\s+(?:di\s+)?(?:sanatoria|condono)\s+(?:in\s+corso|non\s+ancora|pendent)|"
                           r"oblazion\w+|non\s+(?:ancora\s+)?(?:definit|rilasciat)\w+.{0,40}(?:sanatoria|condono)"),
    ("Certificato di destinazione urbanistica (terreni)", r"certificato\s+di\s+destinazione\s+urbanistica|\bC\.?D\.?U\.?\b"),
    ("Destinazione d'uso", r"destinazion\w+\s+d'uso|cambi\w+\s+(?:di\s+)?destinazion\w+"),
    ("Verifica tecnica della regolarità urbanistica", r"sopralluogo\s+da\s+parte\s+di\s+un\s+tecnico|relazione\s+(?:tecnica\s+)?"
                                                     r"(?:certificata|di\s+conformit[aà]\s+urbanistic)|tecnico\s+.{0,40}certifich|"
                                                     r"irregolarit\w+\s+edili\w*|attivit[aà]\s+tecnica\s+non\s+rientra|"
                                                     r"mi\s+esonera\w*\s+da\s+qualsiasi\s+responsabilit"),
]


def note_urbanistiche(t: str) -> list[dict]:
    out = []
    for nome, regex in NOTE_URBANISTICHE:
        frasi = []
        for m in re.finditer(regex, t, re.I):
            f = _frase(t, m.start(), 700)
            if nome.startswith("Difformit") and dichiarazione_negativa(f):
                continue  # "non sussistono difformità rilevanti"
            if f not in frasi and not any(f in x or x in f for x in frasi):
                frasi.append(f)
            if len(frasi) >= 3:
                break
        if frasi:
            out.append({"tema": nome, "frasi": frasi})
    return out


# ------------------------------------------------------ provenienza precedente

_DATA = r"(\d{1,2}\s*°?\s+[a-zà-ù]+\s+\d{4}|\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4})"
_TIPI_TITOLO_PROV = [
    ("successione", r"successione|in\s+morte\s+d|dichiarazione\s+di\s+successione|eredit[aà]|testament\w+"),
    ("donazione", r"donazion\w+"),
    ("divisione", r"divisione"),
    ("permuta", r"permuta"),
    ("decreto di trasferimento", r"decreto\s+di\s+trasferimento|asta|esecuzion\w+\s+immobiliar\w+"),
    ("assegnazione", r"assegnazion\w+"),
    ("conferimento", r"conferiment\w+"),
    ("usucapione", r"usucapion\w+"),
    ("costruzione su area propria", r"(?:edificat|costruit)\w+\s+(?:dalla\s+parte\s+venditrice\s+)?su\s+(?:area|terreno)"),
    ("compravendita", r"compravendit\w+|vendit\w+|acquist\w+"),
]

# frasi con cui l'atto introduce la provenienza
_RE_PROVENIENZA = re.compile(
    r"\bPROVENIENZA\b|pervenut[oaie]\b|titol\w+\s+di\s+provenienza|(?:quanto\s+in\s+oggetto|l'immobile|l'unit[aà]|"
    r"gli\s+immobili|le\s+unit[aà])\s+(?:è|e'|sono)\s+(?:di\s+)?propriet[aà]\s+.{0,80}?(?:in\s+forza|in\s+virt[uù]|per\s+(?:atto|successione))|"
    r"(?:ha|hanno)\s+acquistato\s+(?:quanto|l'immobile|gli\s+immobili|la\s+piena)", re.I)


def provenienza_precedente(t: str) -> dict:
    """Passaggi dell'atto che descrivono come la parte venditrice era diventata proprietaria."""
    brani: list[str] = []
    for m in _RE_PROVENIENZA.finditer(t):
        inizio = max(t.rfind(". ", 0, m.start()), t.rfind("; ", 0, m.start()))
        inizio = 0 if inizio < 0 else inizio + 2
        if m[0].upper() == "PROVENIENZA":
            inizio = m.start()
        # fino all'articolo successivo o a ~900 caratteri, chiudendo su una fine di frase
        resto = t[inizio:inizio + 1200]
        stop = re.search(r"\s(?:ART(?:ICOLO)?\.?\s*\d+|Articolo\s+\d+)|(?-i:\.\s+(?:La|Il|Le|I|Si|Ai|Per|Ciascuna|Quanto\s+venduto|Le\s+parti)\s)", resto[40:], re.I)
        brano = resto[:40 + stop.start()] if stop else resto
        if not stop and len(resto) >= 1200:
            brano = resto[:resto.rfind(". ", 0, 1200) + 1] or resto
        brano = _senza_numero_articolo(_FINE_ATTO.split(brano)[0].strip(" ;,"))
        fine_frase = re.search(r"\.\s+(?=[A-Z])", brano[30:])
        prima_frase = brano[:30 + fine_frase.start() + 1] if fine_frase else brano
        if not re.search(r"notai|rep(?:ertorio|\.)|trascritt|successione|in\s+morte|donazion|decreto|sentenza", prima_frase, re.I):
            continue  # cita la provenienza senza estremi (es. decadenza dalle agevolazioni)
        if any(brano in b or b in brano for b in brani):
            continue
        brani.append(brano)
        if len(brani) >= 3:
            break
    titoli = []
    for brano in brani:
        for pezzo in _spezza_titoli(brano):
            v = _titolo_provenienza(pezzo)
            if v and not any(_stesso_titolo(v, x) for x in titoli):
                titoli.append(v)
    return {"testo": brani, "titoli": titoli}


def _spezza_titoli(brano: str) -> list[str]:
    """Un brano puo' citare piu' titoli (es. successione e poi accettazione dell'eredita')."""
    punti = [m.start() for m in re.finditer(
        r"(?:in\s+forza\s+di|in\s+virt[uù]\s+di|giusta|per|con|mediante|a\s+seguito\s+di)\s+"
        r"(?:(?:l'|il|la)\s*)?(?:atto|successione|denuncia|dichiarazione\s+di\s+successione|decreto|sentenza|scrittura|"
        r"accettazione|verbale|donazione|testamento)|;\s+(?=[a-zA-Z])|(?<=[a-z0-9]\.)\s+(?=[A-Z])", brano, re.I)]
    if not punti:
        return [brano]
    # "n. 69.849 di rep. Notaio Rossi": dopo un'abbreviazione non e' una fine frase
    punti = [p for p in punti if not re.search(r"\b(?:rep|racc|n|nn|art|dott|sig|prot|vol|pag|reg)\.$", brano[:p].rstrip(), re.I)]
    punti = sorted(set([0] + punti))
    pezzi = [brano[a:b] for a, b in zip(punti, punti[1:] + [len(brano)])]
    # un pezzo senza estremi ("pervenuto al signor X", "Al de cuius l'immobile era pervenuto")
    # introduce il successivo: si uniscono
    uniti: list[str] = []
    attesa = ""
    for p in pezzi:
        if not re.search(r"notai|\brep(?:ertorio|\.)|trascritt|registrat|decedut|in\s+morte", p, re.I):
            attesa += p
            continue
        uniti.append(attesa + p)
        attesa = ""
    if attesa:
        if uniti:
            uniti[-1] += attesa
        else:
            uniti.append(attesa)
    # "per successione in morte di X ..." + "giusta dichiarazione di successione ...": stesso titolo
    out: list[str] = []
    for p in uniti:
        if out and re.search(r"^\s*(?:giusta|con|mediante)\s+(?:la\s+)?(?:dichiarazione|denuncia)\s+di\s+successione", p, re.I) \
                and re.search(r"successione|in\s+morte", out[-1], re.I) and not re.search(r"trascritt", out[-1], re.I):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def _titolo_provenienza(s: str) -> dict | None:
    v = {"tipo": "", "notaio": "", "data": "", "repertorio": "", "registrazione": "", "trascrizione": "",
         "defunto": "", "data_decesso": "", "accettazione_eredita": False, "testo": s.strip(" ;,")}
    if re.search(r"accettazion\w+\s+(?:tacit\w+\s+|espress\w+\s+)?(?:dell'|di\s+)?eredit", s, re.I):
        v["accettazione_eredita"] = True
    for nome, regex in _TIPI_TITOLO_PROV:
        if re.search(regex, s, re.I):
            v["tipo"] = nome
            break
    if v["accettazione_eredita"] and not re.search(r"successione|in\s+morte|dichiarazione", s, re.I):
        v["tipo"] = "accettazione di eredità"
    m = re.search(r"(?i:notai[oa])\s+(?:dott(?:or(?:essa)?|\.(?:ssa)?)?\.?\s*|dr\.?\s*)?([A-ZÀ-Ü][A-Za-zÀ-ü']+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü']+){0,3})"
                  r"(?:,?\s+(?:notaio\s+)?(?:di|in|con\s+sede\s+in|residente\s+in|da)\s+([A-ZÀ-Ü][A-Za-zÀ-ü']+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü']+)?))?"
                  r"(?=[\s,.;(]|$)", s)
    if m and m[1].lower() not in ("in", "di", "del", "della"):
        v["notaio"] = tx.titolo(m[1]) + (f" di {tx.titolo(m[2])}" if m[2] else "")
    for m in re.finditer(r"(?:in\s+data|del|datat\w+|stipulat\w+\s+il|il)\s+" + _DATA, s, re.I):
        prima = s[max(0, m.start() - 60):m.start()]
        if re.search(r"(?:nat[oa]|decedut\w+|mort[oa])(?:\s+a\s+[A-ZÀ-Ü][\w' ]*)?\s*$", prima, re.I):
            continue  # data di nascita o di morte, non del titolo
        v["data"] = tx.formato_data(m[1]) or m[1]
        break
    m = re.search(r"\brep(?:ertorio|\.)?\s*(?:n\.?|numero)?\s*(\d[\d.]*(?:/\d+)?)", s, re.I) or \
        re.search(r"\bn\.?\s*(\d[\d.]*)\s+di\s+rep", s, re.I)
    if m:
        v["repertorio"] = m[1].rstrip(".")
    m = re.search(r"registrat\w+\s+(?:presso\s+(?:l'|il\s+)?[^,]{0,60}?\s+)?(?:a|di)\s+([A-ZÀ-Ü][\w' ]+?)\s+(?:in\s+data|il)\s+"
                  + _DATA + r"(?:\s+a[il]?\s+(?:nn?\.?|numer[oi])\s*(\d[\w/]*(?:\s+vol(?:ume|\.)?\s*\d+)?(?:\s+serie\s+\w+)?))?", s, re.I)
    if m:
        v["registrazione"] = f"a {tx.titolo(m[1].strip())} il {tx.formato_data(m[2]) or m[2]}" + (f" al n. {m[3].strip()}" if m[3] else "")
    m = re.search(r"trascritt\w+\s+(?:presso\s+(?:l'|la\s+|il\s+)?[^,]{0,80}?\s+)?(?:a|di)\s+([A-ZÀ-Ü][\w' ]+?)\s+(?:in\s+data|il)\s+"
                  + _DATA + r"\s+a[il]?\s+(?:nn?\.?|n\.\s?ri|numer[oi])\s*([\d]+\s*/\s*[\d]+|[\d]+(?:\s+e\s+[\d]+)?)", s, re.I)
    if m:
        numeri = re.sub(r"\s+", "", m[3])
        v["trascrizione"] = f"a {tx.titolo(m[1].strip())} il {tx.formato_data(m[2]) or m[2]} ai nn. {numeri}"
    m = re.search(r"(?:in\s+morte|successione)\s+(?:legittima\s+|testamentaria\s+)?(?:del(?:la)?|di)\s+(?:propri[oa]\s+)?"
                  r"(?:(?:padre|madre|coniuge|marito|moglie|fratello|sorella|zi[oa]|nonn[oa])\s+)?(?:signor[ae]?\s+|sig\.(?:ra)?\s+)?"
                  r"([A-ZÀ-Ü][A-Za-zÀ-ü']+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü']+){1,3})", s)
    if m:
        v["defunto"] = tx.titolo(m[1])
    m = re.search(r"decedut\w+\s+(?:a\s+[A-ZÀ-Ü][\w' ]+?\s+)?(?:in\s+data|il)\s+" + _DATA, s, re.I)
    if m:
        v["data_decesso"] = tx.formato_data(m[1]) or m[1]
    if not (v["notaio"] or v["repertorio"] or v["trascrizione"] or v["defunto"] or v["data"]):
        return None
    if not v["tipo"]:
        v["tipo"] = "atto"
    return v


def _stesso_titolo(a: dict, b: dict) -> bool:
    if a["repertorio"] and a["repertorio"] == b["repertorio"]:
        return True
    return bool(a["tipo"] == b["tipo"] and a["data"] and a["data"] == b["data"])


# ---------------------------------------------------------- vincoli e gravami
# gravita': "alta" = puo' impedire o condizionare la vendita / il mutuo dell'acquirente;
#           "media" = da verificare e riportare nel preliminare; "info" = da conoscere.

CATEGORIE_VINCOLI = [
    ("Ipoteche, pignoramenti e trascrizioni pregiudizievoli", "alta",
     "Vanno cancellati o assentiti prima del rogito: verificare con ispezione ipotecaria aggiornata.",
     r"ipotec\w+|pignorament\w+|sequestr\w+|trascrizion\w+\s+pregiudizievol\w+|iscrizion\w+\s+ipotecari\w+|"
     r"domand\w+\s+giudizial\w+|privilegi\w*\s+(?:speciali|fiscali)"),
    ("Diritti reali di terzi (usufrutto, abitazione, uso)", "alta",
     "Chi vende potrebbe non avere la piena proprietà: serve il consenso o la rinuncia del titolare del diritto.",
     r"usufrutt\w+|nuda\s+propriet|diritto\s+di\s+abitazione|diritto\s+d'uso|si\s+riserva|riserv(?:a|ando)\s+(?:a\s+(?:se|favore)|il\s+diritto)|"
     r"diritto\s+di\s+superficie|enfiteusi|livello"),
    ("Edilizia convenzionata / PEEP", "alta",
     "Possibili prezzo massimo di cessione, requisiti dell'acquirente o divieti di vendita: verificare la convenzione e l'eventuale affrancazione.",
     r"edilizia\s+(?:economica|residenziale\s+pubblica|convenzionat\w+|agevolat\w+|sovvenzionat\w+)|"
     r"P\.?\s?E\.?\s?E\.?\s?P\.?\b|convenzione\s+(?:edilizia|urbanistica|con\s+il\s+Comune|ai\s+sensi)|"
     r"legge\s+(?:n\.\s*)?865|L\.\s*865/(?:19)?71|prezzo\s+massimo\s+di\s+cessione|affrancazion\w+|art(?:icolo|\.)\s*35.{0,30}865|"
     r"diritto\s+di\s+superficie.{0,60}comun"),
    ("Divieti di alienazione e diritti di riscatto", "alta",
     "La vendita può essere vietata per un periodo o soggetta a riscatto: verificare la scadenza.",
     r"divieto\s+di\s+(?:alienazione|vendita|alienare)|non\s+(?:potr\w+|possono)\s+(?:essere\s+)?(?:alienat|vendut|cedut)|"
     r"diritto\s+di\s+riscatto|patto\s+di\s+riscatto|riservato\s+dominio|inalienabil\w+"),
    ("Provenienza donativa: commerciabilità", "alta",
     "Le donazioni possono essere impugnate dai legittimari del donante (artt. 555-563 c.c.): molte banche non "
     "finanziano l'acquisto. Valutare polizza, rinuncia all'opposizione o mutuo dissenso.",
     r"commerciabilit\w+|art(?:icolo|\.)\s*563|azion\w+\s+di\s+(?:riduzione|restituzione)|opposizione\s+alla\s+donazione|"
     r"legittimari|edott\w+\s+della\s+disciplina.{0,40}donazion|donazion\w*\s+e\s+delle\s+conseguenze"),
    ("Vincoli culturali e paesaggistici", "alta",
     "Bene vincolato: la vendita va denunciata al Ministero e lo Stato ha diritto di prelazione (D.Lgs. 42/2004).",
     r"42/2004|codice\s+dei\s+beni\s+culturali|interesse\s+(?:storico|artistico|culturale)|1089/(?:19)?39|1497/(?:19)?39|"
     r"vincolo\s+(?:storico|artistico|monumentale|paesaggistic\w+|culturale|archeologic\w+)|Soprintendenza"),
    ("Diritti di prelazione", "alta",
     "Il titolare (Stato, affittuario agrario, confinante, conduttore, Comune) va interpellato prima della vendita.",
     r"prelazion\w+"),
    ("Fondo patrimoniale, trust e vincoli di destinazione", "alta",
     "Bene vincolato ai bisogni della famiglia o a uno scopo: la vendita può richiedere particolari consensi o l'autorizzazione del giudice.",
     r"fondo\s+patrimoniale|\btrust\b|2645[\s-]*ter|vincolo\s+di\s+destinazione"),
    ("Vincolo pertinenziale dei parcheggi (L. 122/1989)", "media",
     "Il posto auto o box non può essere venduto separatamente dall'unità a cui è legato.",
     r"vincolo\s+pertinenzial\w+|legge\s+(?:n\.\s*)?122(?:/|\s+del\s+)(?:19)?89|L\.\s*122/(?:19)?89|Tognoli|"
     r"9\s+della\s+legge.{0,30}122"),
    ("Servitù", "media",
     "Servitù specifiche da riportare nel preliminare e da far conoscere all'acquirente.",
     r"servit[uù]"),
    ("Locazioni, comodati e occupazione", "media",
     "Immobile occupato: verificare contratto, scadenza ed eventuale prelazione del conduttore.",
     r"\blocat[oaie]\b|contratt\w+\s+di\s+locazione|conduttor\w+|comodato|affittuari\w+"),
    ("Regolamento di condominio", "info",
     "Il regolamento contrattuale può limitare l'uso dell'immobile (attività vietate, destinazioni).",
     r"regolamento\s+(?:di|del|condominiale)\s*(?:condominio)?"),
    ("Agevolazioni fiscali (prima casa)", "info",
     "Vendita entro 5 anni dall'acquisto agevolato: il venditore decade salvo riacquisto entro un anno.",
     r"prima\s+casa|nota\s+II-?\s?bis|credito\s+d'imposta"),
    ("Patti e condizioni particolari", "media",
     "Patti tra le parti che possono avere effetti anche sui successivi acquirenti.",
     r"patto\s+(?:di|speciale|particolare)|patti\s+(?:speciali|particolari)|condizione\s+(?:sospensiva|risolutiva)|"
     r"clausola\s+(?:penale|risolutiva)|pattuiscono|convengono\s+(?:espressamente|inoltre|altresì)|obblig\w+\s+.{0,40}aventi\s+causa"),
]

# formule di rito presenti in quasi tutti gli atti: non sono vincoli effettivi
_ECCEZIONI = (r"ad\s+eccezione|eccett\w+|salvo\s+(?:quell|la|il|le|i)\b|salvo\s+quanto|tranne|ad\s+esclusione|fatt[aoie]\s+salv|"
              r"in\s+particolare|costituit\w+\s+(?:con|a\s+favore|per|mediante)|a\s+favore|a\s+carico\s+(?:del|della|dei|delle)\s+(?:fondo|mappale|particella|unit)|"
              r"iscritt\w+\s+(?:a|presso)\s+[A-Z].{0,40}(?:il|in\s+data)\s+\d")
_TERMINI_LIBERTA = ["pesi", "vincoli", "ipoteche", "servitù", "servitu", "oneri", "trascrizioni", "iscrizioni",
                    "privilegi", "gravami", "pignoramenti", "liti", "sequestri", "prelazioni"]


_ECCEZIONI_FORTI = r"ad\s+eccezione|eccett\w+|salvo\s+(?:quell|la|il|le|i)\b|salvo\s+quanto|tranne|ad\s+esclusione|fatt[aoie]\s+salv"
_NEGAZIONE = (r"\bnon\s+(?:sussist|esist|grava|gravano|risult|è\s+(?:locat|soggett|gravat|concess)|sono\s+(?:locat|soggett|gravat)|"
              r"ricorr|spett|vi\s+sono)\w*|\bnessun[oa]?\b|insussistenz|liber[oa]\s+da\s+persone|\bassenza\s+di\b")


def dichiarazione_negativa(frase: str) -> bool:
    """'l'immobile non è locato', 'non sussistono diritti di prelazione', senza eccezioni."""
    f = frase.lower()
    return bool(re.search(_NEGAZIONE, f)) and not re.search(_ECCEZIONI_FORTI, f)


def _formula_di_rito(frase: str) -> bool:
    f = frase.lower()
    if re.search(_ECCEZIONI, f):
        return False
    # "libero da pesi, vincoli, ipoteche, trascrizioni pregiudizievoli..."
    if re.search(r"\bliber[oaie]\b|\blibert[aà]\b|\bfranc[oaie]\b|garantisc\w+.{0,60}libert", f) and \
            sum(1 for x in _TERMINI_LIBERTA if x in f) >= 2:
        return True
    # "con tutte le servitù attive e passive se e come esistenti", "nello stato di fatto e di diritto"
    if re.search(r"servit[uù]\s+attive\s+e\s+passive", f) and \
            not re.search(r"passaggio|elettrodott|acquedott|veduta|metanodott|fognat|scarico|condott|gasdott", f):
        return True
    # rinuncia all'ipoteca legale ed esonero del conservatore: formule di rito
    if re.search(r"rinun[cz]i\w+.{0,60}ipoteca\s+legale|esonerando.{0,80}conservatore|esonero.{0,40}conservatore", f):
        return True
    # imposte "ipotecarie e catastali", dichiarazioni per le agevolazioni prima casa
    if re.search(r"ipotecari\w*\s+e\s+catastal|impost\w+\s+(?:di\s+registro,?\s+)?ipotecari", f):
        return True
    if re.search(r"altra\s+casa\s+di\s+abitazione|titolare.{0,80}(?:prima\s+casa|agevolazion)|\"?prima\s+casa\"?\s*;?$", f):
        return True
    # la vendita "a corpo, nello stato di fatto e di diritto ... con le servitù attive e passive"
    if re.search(r"servit[uù]\s+(?:attive\s+e\s+passive|legalmente\s+esistenti)|stato\s+di\s+fatto\s+e\s+di\s+diritto", f) and \
            not re.search(r"passaggio|elettrodott|acquedott|veduta|metanodott|fognat|scarico|condott|gasdott|pozzett", f):
        return True
    return False


def vincoli_gravami(t: str) -> dict:
    """{"trovati": [{categoria, gravita, nota, frasi}], "di_rito": [categorie],
        "negative": [frasi in cui la parte venditrice esclude un vincolo]}"""
    trovati = []
    di_rito: set[str] = set()
    negative: list[str] = []
    gia: list[str] = []
    for nome, gravita, nota, regex in CATEGORIE_VINCOLI:
        frasi: list[str] = []
        for m in re.finditer(regex, t, re.I):
            f = _frase(t, m.start(), 900)
            if dichiarazione_negativa(f):
                if f not in negative:
                    negative.append(f)
                continue
            vicino = t[max(0, m.start() - 120):m.end() + 120]
            if _formula_di_rito(f) or re.search(r"ipotecari\w*\s+e\s+catastal|impost\w+\s+(?:di\s+registro,?\s+)?ipotecari",
                                                 vicino, re.I):
                di_rito.add(nome)
                continue
            chiave = re.sub(r"\W+", "", f.lower())[:50]
            if any(f == x or f in x or x in f or re.sub(r"\W+", "", x.lower())[:50] == chiave for x in frasi) or f in gia:
                continue
            frasi.append(f)
            if len(frasi) >= 5:
                break
        if frasi:
            gia.extend(frasi)
            trovati.append({"categoria": nome, "gravita": gravita, "nota": nota, "frasi": frasi})
    return {"trovati": trovati, "di_rito": sorted(di_rito - {v["categoria"] for v in trovati}), "negative": negative}
