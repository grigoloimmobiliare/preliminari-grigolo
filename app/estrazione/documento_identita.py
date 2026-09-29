"""Estrazione dei dati anagrafici da documenti d'identità (CIE, passaporto, tessera sanitaria).

Ogni tessera trovata nei file viene letta piu' volte con l'OCR; i valori sono scelti per
maggioranza e, dove possibile, validati con le cifre di controllo (MRZ, codice fiscale).
Le tessere della stessa persona (fronte, retro, tessera sanitaria) vengono poi unite."""

from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .. import testo as tx
from . import codice_fiscale as cfm
from . import mrz as mrzm
from . import ocr

_INDIRIZZO = r"(?:VIA|VIALE|V\.LE|PIAZZA|PIAZZALE|P\.ZZA|CORSO|BORGO|VICOLO|STRADA|LOCALITA'?|LOC\.|CONTRA'?|GALLERIA|RIVIERA|LARGO|CALLE|FRAZIONE|SESTIERE|SALIZADA|FONDAMENTA|CAMPO|MASO|CONTRADA|RUGA)"


@dataclass
class Frammento:
    """Dati letti da una singola tessera (es. il fronte della carta d'identità)."""
    file: str
    testi: list[str]
    tipo: Counter = field(default_factory=Counter)
    mrz: mrzm.DatiMRZ | None = None
    cf: Counter = field(default_factory=Counter)
    numeri_doc: Counter = field(default_factory=Counter)
    cognomi: Counter = field(default_factory=Counter)
    nomi: Counter = field(default_factory=Counter)
    nascite: Counter = field(default_factory=Counter)     # (luogo, prov, data)
    date: Counter = field(default_factory=Counter)
    comuni_rilascio: Counter = field(default_factory=Counter)
    residenze: Counter = field(default_factory=Counter)

    @property
    def testo_unico(self) -> str:
        return "\n".join(self.testi).upper()


def _righe(testo: str) -> list[str]:
    return [r.strip() for r in (testo or "").upper().splitlines() if r.strip()]


def _solo_nome(s: str) -> str:
    s = re.sub(r"[^A-ZÀ-Ü' ]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def _dopo_etichetta(righe: list[str], etichetta: str, max_salto: int = 2) -> list[str]:
    out = []
    for i, r in enumerate(righe):
        if re.search(etichetta, r):
            resto = re.split(etichetta, r, maxsplit=1)[-1]
            resto = re.sub(r"^[\s/:.\-]*[A-Z' ]*?(SURNAME|NAME|MUNICIPALITY)\b", "", resto).strip(" /:.-")
            if len(resto) >= 3:
                out.append(resto)
            for j in range(i + 1, min(len(righe), i + 1 + max_salto)):
                out.append(righe[j])
    return out


def analizza_tessera(file: str, testi: list[str]) -> Frammento:
    f = Frammento(file=file, testi=testi)
    tutto = f.testo_unico

    if "CARTA DI IDENTIT" in tutto or "IDENTITY CARD" in tutto:
        f.tipo["C.I."] += 3
    if "TESSERA SANITARIA" in tutto or "ASSICURAZIONE MALATTIA" in tutto:
        f.tipo["Tessera sanitaria"] += 3
    if "PASSAPORTO" in tutto or "PASSPORT" in tutto:
        f.tipo["Passaporto"] += 3
    if "PATENTE" in tutto or "DRIVING LICEN" in tutto:
        f.tipo["Patente"] += 3

    f.mrz = mrzm.leggi(testi)
    if f.mrz and f.mrz.tipo:
        f.tipo[f.mrz.tipo] += 1

    for t in testi:
        for c in cfm.candidati(t):
            f.cf[c] += 1
        for m in re.finditer(r"\b([A-Z0-9]{2})\s?([0-9OIlSZB]{5})\s?([A-Z0-9]{2})\b", t.upper()):
            num = mrzm._lettere(m[1]) + mrzm._cifre(m[2]) + mrzm._lettere(m[3])
            if re.fullmatch(r"[A-Z]{2}\d{5}[A-Z]{2}", num):
                f.numeri_doc[num] += 1
        righe = _righe(t)
        for r in _dopo_etichetta(righe, r"COGNOME\s*/?\s*(SURNAME)?|^3\s+COGNOME", 1):
            n = _solo_nome(r)
            if 2 <= len(n) <= 40 and "NOME" not in n:
                f.cognomi[n] += 1
        for r in _dopo_etichetta(righe, r"(?<!COG)NOME\s*/\s*NAME|^4\s+NOME|^NOME\b", 1):
            n = _solo_nome(r)
            if 2 <= len(n) <= 40 and "COGNOME" not in n:
                f.nomi[n] += 1
        # tessera sanitaria: "Cognome ROSSI" sulla stessa riga
        for m in re.finditer(r"^COGNOME\s+([A-Z' ]{2,})$", t.upper(), re.M):
            f.cognomi[_solo_nome(m[1])] += 1
        for m in re.finditer(r"^NOME\s+([A-Z' ]{2,})$", t.upper(), re.M):
            f.nomi[_solo_nome(m[1])] += 1
        for m in re.finditer(r"([A-Z][A-Z' ]{1,30}?)\s*[\(\{\[]\s*([A-Z0-9]{2})\s*[\)\}\]]\s*(\d{2}\s?[.,:]\s?\d{2}\s?[.,: ]\s?\d{4})", t.upper()):
            d = tx.parse_data(re.sub(r"[\s.,:]+", "/", m[3]))
            f.nascite[(_solo_nome(m[1]), tx.correggi_provincia(m[2]), d)] += 1
        for m in re.finditer(r"(\d{2})\s?[.,/:]\s?(\d{2})\s?[.,/:]\s?(\d{4})", t):
            d = tx.parse_data(f"{m[1]}/{m[2]}/{m[3]}")
            if d and 1900 < d.year < 2100:
                f.date[d] += 1
        for r in _dopo_etichetta(righe, r"COMUNE DI\s*/?\s*(?:MUNICIPALITY)?", 3):
            n = _solo_nome(r)
            etichette = ("MUNICIPALITY", "COMUNE", "COGNOME", "SURNAME", "CARTA DI IDENTITA", "IDENTITY CARD",
                         "REPUBBLICA ITALIANA", "MINISTERO DELL'INTERNO", "NOME", "NAME")
            if 3 <= len(n) <= 35 and not any(
                    difflib.SequenceMatcher(None, n, e).ratio() > 0.6 or e in n for e in etichette):
                f.comuni_rilascio[n] += 1
        for r in righe:
            m = re.search(_INDIRIZZO + r"\b[A-Z' .]+,?\s*(?:N\.?\s*)?\d+\S*\s+[|I]?\s*[A-Z' ]{3,}.*", r)
            if m:
                f.residenze[re.sub(r"\s+", " ", m[0]).strip()] += 1
    return f


def estrai_da_file(percorso: Path) -> list[Frammento]:
    frammenti = []
    for p in range(ocr.numero_pagine(percorso)):
        img = ocr.immagine_pagina(percorso, p, dpi=400)
        for tessera in ocr.trova_tessere(img):
            frammenti.append(analizza_tessera(percorso.name, ocr.ocr_tessera(tessera)))
    return frammenti


# ------------------------------------------------------------------ persone

@dataclass
class Persona:
    frammenti: list[Frammento] = field(default_factory=list)

    def cognomi(self) -> Counter:
        c = Counter()
        for f in self.frammenti:
            c.update(f.cognomi)
            if f.mrz:
                for cog, _ in f.mrz.nomi_candidati or []:
                    c[cog] += 2
        return c

    def cognome_principale(self) -> str:
        """Il cognome piu' probabile: preferibilmente quello coerente con un codice fiscale letto."""
        cognomi = self.cognomi()
        cf = [c for f in self.frammenti for c in f.cf]
        coerenti = [c for c in cognomi if any(cfm.codice_cognome(c) == x[:3] for x in cf)]
        if coerenti:
            return max(coerenti, key=cognomi.get)
        return _top(cognomi) or ""


def _identita(f: Frammento) -> set[str]:
    """Identificativi verificati di una tessera: servono a unire fronte, retro e tessera
    sanitaria della stessa persona senza confonderla con altre."""
    k = set()
    cognomi = set(f.cognomi) | {c for c, _ in (f.mrz.nomi_candidati or [])} if f.mrz else set(f.cognomi)
    for c in f.cf:
        # un CF con carattere di controllo corretto puo' comunque essere una lettura casuale
        # dello sfondo: vale solo se coerente con un cognome letto sulla stessa tessera
        if not any(cfm.codice_cognome(cog) == c[:3] for cog in cognomi):
            continue
        k.add("CF:" + c)
        d = cfm.data_nascita(c)
        if d:
            k.add(f"NASCITA:{d.isoformat()}{cfm.sesso(c)}")
    if f.mrz:
        if f.mrz.numero_valido:
            k.add("DOC:" + f.mrz.numero_documento)
        if f.mrz.nascita_valida and f.mrz.data_nascita:
            k.add(f"NASCITA:{f.mrz.data_nascita.isoformat()}{f.mrz.sesso}")
    # i numeri letti sul fronte non sono verificabili (lo sfondo genera letture spurie): non si usano
    return k


def _somiglianza(f: Frammento, p: Persona) -> float:
    cognome = p.cognome_principale()
    if not cognome:
        return 0.0
    parole = set(re.findall(r"[A-Z]{3,}", f.testo_unico)) | set(f.cognomi)
    return max((difflib.SequenceMatcher(None, cognome, w).ratio() for w in parole), default=0.0)


def raggruppa(frammenti: list[Frammento]) -> list[Persona]:
    # 1) tessere con identificativi verificati: stessa persona se ne condividono almeno uno
    gruppi: list[tuple[set[str], list[Frammento]]] = []
    senza: list[Frammento] = []
    for f in frammenti:
        k = _identita(f)
        if not k:
            senza.append(f)
            continue
        uniti = [g for g in gruppi if g[0] & k]
        chiavi, lista = set(k), [f]
        for g in uniti:
            chiavi |= g[0]
            lista = g[1] + lista
            gruppi.remove(g)
        gruppi.append((chiavi, lista))
    persone = [Persona(frammenti=g[1]) for g in gruppi]

    # 2) tessere senza dati verificati (es. un fronte poco leggibile): alla persona col cognome piu' simile
    for f in senza:
        if len(persone) == 1:
            persone[0].frammenti.append(f)
            continue
        if persone:
            migliore = max(persone, key=lambda p: _somiglianza(f, p))
            if _somiglianza(f, migliore) >= 0.75:
                migliore.frammenti.append(f)
                continue
        if f.cognomi or f.nascite or f.numeri_doc:
            persone.append(Persona(frammenti=[f]))
    return persone


_SIMILI = {"T": "I", "I": "TLJ1", "L": "I", "1": "I", "0": "O", "O": "0D", "D": "O", "5": "S",
           "8": "B", "U": "V", "V": "U", "M": "N", "N": "M", "H": "N", "E": "F", "F": "E", "C": "G", "G": "C"}


def _varianti(s: str) -> list[str]:
    out = [s]
    for i, ch in enumerate(s):
        for alt in _SIMILI.get(ch, ""):
            if alt.isalpha():
                out.append(s[:i] + alt + s[i + 1:])
    return out


def _top(c: Counter):
    return c.most_common(1)[0][0] if c else None


def risolvi(p: Persona) -> dict:
    """Sceglie i valori finali di una persona e annota la fonte di ciascuno."""
    dati: dict = {"tipo": "fisica"}
    fonti: dict = {}
    avvisi: list[str] = []
    file_usati = sorted({f.file for f in p.frammenti})

    mrz_validi = [f.mrz for f in p.frammenti if f.mrz and f.mrz.affidabile]
    mrz_tutti = [f.mrz for f in p.frammenti if f.mrz]

    # --- tipo e numero documento
    tipi = Counter()
    for f in p.frammenti:
        tipi.update(f.tipo)
    tipo_doc = "C.I."
    for t in ("C.I.", "Passaporto", "Patente"):
        if tipi.get(t):
            tipo_doc = t
            break
    dati["doc_tipo"] = tipo_doc

    numeri = Counter()
    for f in p.frammenti:
        numeri.update(f.numeri_doc)
    num_mrz = [m.numero_documento for m in mrz_tutti if m.numero_valido]
    grezzi_mrz = [m.numero_documento for m in mrz_tutti if m.numero_documento]
    if num_mrz:
        dati["doc_numero"] = num_mrz[0]
        fonti["doc_numero"] = "MRZ (verificato)"
    elif numeri and grezzi_mrz:
        # il numero stampato sul fronte piu' simile a quello letto (male) nella MRZ
        dati["doc_numero"] = max(numeri, key=lambda n: (
            max(difflib.SequenceMatcher(None, n, g).ratio() for g in grezzi_mrz), numeri[n]))
        fonti["doc_numero"] = "OCR fronte (confrontato con MRZ)"
    elif numeri:
        dati["doc_numero"] = _top(numeri)
        fonti["doc_numero"] = "OCR fronte"
    elif mrz_tutti and mrz_tutti[0].numero_documento:
        dati["doc_numero"] = mrz_tutti[0].numero_documento
        fonti["doc_numero"] = "MRZ (non verificato)"

    # --- nascita, sesso, scadenza
    if mrz_validi:
        m = mrz_validi[0]
        dati["data_nascita"] = tx.formato_data(m.data_nascita)
        dati["sesso"] = m.sesso
        dati["doc_scadenza"] = tx.formato_data(m.scadenza)
        fonti.update(data_nascita="MRZ (verificato)", sesso="MRZ", doc_scadenza="MRZ (verificato)")
    else:
        for m in mrz_tutti:
            if m.nascita_valida and "data_nascita" not in dati:
                dati["data_nascita"] = tx.formato_data(m.data_nascita)
                dati["sesso"] = m.sesso
                fonti["data_nascita"] = "MRZ (verificato)"
            if m.scadenza_valida and "doc_scadenza" not in dati:
                dati["doc_scadenza"] = tx.formato_data(m.scadenza)
                fonti["doc_scadenza"] = "MRZ (verificato)"

    nascite = Counter()
    for f in p.frammenti:
        nascite.update(f.nascite)
    if nascite:
        # preferisci la lettura con la data coerente con la MRZ
        dn = tx.parse_data(dati.get("data_nascita"))
        scelte = [n for n in nascite if dn and n[2] == dn] or list(nascite)
        luogo, prov, d = max(scelte, key=lambda n: nascite[n])
        d = d if d and d.year > 1900 else None
        luoghi = Counter({n[0]: c for n, c in nascite.items() if n in scelte})
        dati["luogo_nascita"] = tx.titolo(_top(luoghi) or luogo)
        province = Counter()
        for n, c in nascite.items():
            if n in scelte and n[1] in tx.PROVINCE:
                province[n[1]] += c
        dati["prov_nascita"] = _top(province) or tx.provincia_da_comune(dati["luogo_nascita"]) or prov
        fonti["luogo_nascita"] = "OCR fronte"
        if "data_nascita" not in dati and d:
            dati["data_nascita"] = tx.formato_data(d)
            fonti["data_nascita"] = "OCR fronte"

    # --- nomi e codice fiscale
    cognomi, nomi, coppie = Counter(), Counter(), Counter()
    cf = Counter()
    for f in p.frammenti:
        cognomi.update(f.cognomi)
        nomi.update(f.nomi)
        cf.update(f.cf)
        if f.mrz:
            for c, n in f.mrz.nomi_candidati or []:
                coppie[(c, n)] += 1
                cognomi[c] += 1
                nomi[n] += 1
    for c in cognomi:
        for n in nomi:
            coppie[(c, n)] += 0
    dn = tx.parse_data(dati.get("data_nascita"))
    sx = dati.get("sesso", "")

    cf_scelto = None
    coppia = None
    # 1) un CF letto correttamente e coerente con una coppia cognome/nome
    for cf_c, _ in cf.most_common():
        ok = [cp for cp in coppie if cfm.codice_cognome(cp[0]) == cf_c[:3] and cfm.codice_nome(cp[1]) == cf_c[3:6]]
        if ok:
            cf_scelto = cf_c
            coppia = max(ok, key=lambda cp: cognomi[cp[0]] + nomi[cp[1]])
            fonti["codice_fiscale"] = "OCR (carattere di controllo verificato)"
            break
    # 2) ricostruzione del CF dai dati MRZ, provando le coppie cognome/nome lette
    if not cf_scelto and dn and sx:
        testi = [t for f in p.frammenti for t in f.testi]
        ordinate = sorted(coppie, key=lambda cp: -(cognomi[cp[0]] + nomi[cp[1]]))
        # poi le varianti con una lettera corretta (es. MAPIO -> MARIO): valgono solo se
        # il codice fiscale ricostruito trova conferma nel testo letto
        ordinate += [(c2, n2) for c, n in ordinate[:6] for c2 in _varianti(c) for n2 in _varianti(n)
                     if (c2, n2) != (c, n)]
        for cp in ordinate:
            r = cfm.ricostruisci(testi, cp[0], cp[1], dn, sx)
            if r:
                cf_scelto, coppia = r, cp
                fonti["codice_fiscale"] = "ricostruito da MRZ + OCR (verificato)"
                break
    if not cf_scelto:
        plausibili = Counter({c: n for c, n in cf.items()
                              if any(cfm.codice_cognome(cog) == c[:3] for cog in cognomi)})
        if plausibili:
            cf_scelto = _top(plausibili)
            fonti["codice_fiscale"] = "OCR (da verificare)"
    if coppia is None and (cognomi or nomi):
        coppia = (_top(cognomi) or "", _top(nomi) or "")
        avvisi.append("Nome e cognome letti con OCR senza verifica: controllarli")
    if coppia:
        dati["cognome"], dati["nome"] = coppia
        fonti.setdefault("cognome", "OCR / MRZ")
    if cf_scelto:
        dati["codice_fiscale"] = cf_scelto
        if not dati.get("sesso"):
            dati["sesso"] = cfm.sesso(cf_scelto)
        if not dati.get("data_nascita"):
            dati["data_nascita"] = tx.formato_data(cfm.data_nascita(cf_scelto))
            fonti["data_nascita"] = "dal codice fiscale"

    # --- data di rilascio: data del fronte diversa da nascita e scadenza, precedente alla scadenza
    tutte = Counter()
    for f in p.frammenti:
        if f.tipo.get("Tessera sanitaria") and not f.tipo.get("C.I."):
            continue
        tutte.update(f.date)
    sca = tx.parse_data(dati.get("doc_scadenza"))
    oggi = date.today()
    cand = Counter({d: c for d, c in tutte.items()
                    if d != dn and d != sca and d <= oggi and (not sca or (sca.year - 12 <= d.year < sca.year))})
    if cand:
        dati["doc_rilascio"] = tx.formato_data(_top(cand))
        fonti["doc_rilascio"] = "OCR fronte"
    if not sca:
        cand_s = Counter({d: c for d, c in tutte.items() if d > oggi})
        if cand_s:
            dati["doc_scadenza"] = tx.formato_data(_top(cand_s))
            fonti["doc_scadenza"] = "OCR fronte"

    # --- residenza (retro della CIE)
    residenze = Counter()
    for f in p.frammenti:
        residenze.update(f.residenze)
    if residenze:
        vie, civici, com_, prov_ = Counter(), Counter(), Counter(), Counter()
        for r, n in residenze.items():
            via, civ, com, prov = dividi_residenza(r)
            vie[via] += n
            civici[civ] += n if civ else 0
            com_[com] += n if com else 0
            if prov in tx.PROVINCE:
                prov_[prov] += n
        via, civ, com = _top(vie), _top(+civici) or "", _top(+com_) or ""
        dati["res_indirizzo"] = f"{via} n. {civ}" if civ else via
        dati["res_comune"] = com
        dati["res_prov"] = tx.provincia_da_comune(com) or _top(prov_) or ""
        fonti["res_indirizzo"] = "OCR retro documento (verificare il civico)"

    # --- ente di rilascio
    comuni = Counter()
    for f in p.frammenti:
        comuni.update(f.comuni_rilascio)
    if comuni:
        # l'OCR del comune e' spesso sporco: si confronta con i comuni noti
        # (elenco interno + comune di residenza e di nascita appena letti)
        noti = set(tx.COMUNE_PROVINCIA) | {c.upper() for c in (dati.get("res_comune"), dati.get("luogo_nascita")) if c}
        migliore, punteggio = None, 0.0
        for cand, n in comuni.items():
            for noto in noti:
                r = difflib.SequenceMatcher(None, cand, noto).ratio()
                if r > punteggio or (r == punteggio and migliore and n > comuni.get(migliore, 0)):
                    migliore, punteggio = noto, r
        if migliore and punteggio >= 0.7:
            dati["doc_ente"] = "Comune di " + tx.titolo(migliore)
            fonti["doc_ente"] = "OCR fronte (confrontato con elenco comuni)"
        else:
            scelto = max(comuni, key=lambda c: comuni[c] * min(len(c), 10))
            dati["doc_ente"] = "Comune di " + tx.titolo(scelto)
            fonti["doc_ente"] = "OCR fronte (da verificare)"
    elif tipo_doc == "Passaporto":
        dati["doc_ente"] = "Ministero degli Affari Esteri"

    dati["_fonti"] = fonti
    dati["_avvisi"] = avvisi
    dati["_file"] = file_usati
    return dati


def dividi_residenza(s: str) -> tuple[str, str, str, str]:
    """'VIA ROMA, 16/F TREVISO (TV)' -> ('Via Roma', '16/F', 'Treviso', 'TV')."""
    s = re.sub(r"\s+", " ", s.upper()).strip(" -_|")
    prov = ""
    m = re.search(r"[\(\{\[]?\s*([A-Z0-9]{2})\s*[\)\}\]]?\s*[-_|.]*$", s)
    if m and (m[0].strip()[0] in "({[" or m[0].strip()[-1:] in ")}]"):
        prov = tx.correggi_provincia(m[1])
        s = s[:m.start()].strip()
    elif m and s[:m.start()].rstrip().endswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")) is False \
            and len(s.split()) > 3:
        prov = tx.correggi_provincia(m[1])
        s = s[:m.start()].strip()
    m = re.match(r"(.*?)[, ]+(?:N\.?\s*)?(\d+\s*(?:/\s*[A-Z0-9]{1,2}|[A-Z]\b)?)\s+[|]?\s*(?:I\s+)?(.+)$", s)
    if m:
        via = m[1].strip(" ,")
        civico = m[2].replace(" ", "")
        comune = m[3].strip(" |")
        return tx.titolo(via), civico, tx.titolo(comune), prov
    return tx.titolo(s), "", "", prov


def estrai_persone(percorsi: list[Path]) -> list[dict]:
    frammenti = []
    for p in percorsi:
        frammenti += estrai_da_file(p)
    return [risolvi(p) for p in raggruppa(frammenti)]
