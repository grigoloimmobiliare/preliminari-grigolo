"""Analisi dell'atto di provenienza per la sintesi.

Gli estremi (notaio, data, repertorio, registrazione, trascrizione), le parti, i dati
catastali e la dichiarazione urbanistica sono letti dal modulo gia' usato per i
preliminari (app.estrazione.atto). Qui si aggiungono:
- parte cedente e prezzo;
- titoli edilizi (licenze, concessioni, permessi, DIA/SCIA, condoni) con numero e data;
- agibilita' / abitabilita';
- clausole particolari (servitu', vincoli, ipoteche, prelazioni, usufrutto, convenzioni,
  agevolazioni "prima casa", regolamento di condominio, ...), cercate per parole chiave.
"""

from __future__ import annotations

import re
from pathlib import Path

from app import testo as tx
from app.estrazione import atto as atto_base


def estrai(percorso: Path) -> dict:
    grezzo, metodo = atto_base.testo_atto(percorso)
    d = analizza_testo(grezzo, metodo)
    d["_file"] = percorso.name
    return d


def analizza_testo(grezzo: str, metodo: str = "testo digitale") -> dict:
    d = atto_base.analizza_testo(grezzo, metodo)
    t = atto_base._pulisci(grezzo)

    cf_intestatari = {c["codice_fiscale"] for c in d.get("intestatari", [])}
    d["cedenti"] = [c for c in d.get("comparenti", []) if c["codice_fiscale"] not in cf_intestatari] \
        if cf_intestatari else []
    d["prezzo"] = _prezzo(t)
    d["prima_casa"] = bool(re.search(r"prima casa|nota II-bis|note? II bis|art(?:icolo|\.)\s*1,?\s*nota", t, re.I))
    d["titoli_edilizi"] = titoli_edilizi(t)
    d["agibilita_testo"] = d.get("agibilita") or _agibilita(t)
    d["clausole"] = clausole(t)
    return d


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
            occupati.append((m.start(), m.end()))
            finestra = t[m.end():m.end() + 160]
            # la finestra si ferma al titolo successivo
            stop = re.search(r";|(?-i:\.\s+[A-Z])|" + "|".join(r for _, r in TIPI_TITOLO), finestra, re.I)
            if stop and stop.start() > 0:
                finestra = finestra[:stop.start()]
            numero = _RE_NUMERO.search(finestra)
            data = _RE_DATA.search(finestra)
            if not numero and not data:
                # citazione generica ("non sono state rilasciate concessioni"): si ignora
                continue
            voce = {
                "tipo": nome,
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
    m = re.search(r"\s+(?:e\s+(?:di\s+)?|nonch[eé]\s+|,\s*)?(?:" + "|".join(r for _, r in TIPI_TITOLO) + ")", s[da:], re.I)
    return s[:da + m.start()].strip(" ,") if m else s


def _estratto(t: str, pos: int, massimo: int = 260) -> str:
    """Testo dalla posizione 'pos' fino al punto e virgola o alla fine della frase."""
    s = t[pos:pos + massimo]
    m = re.search(r";|(?<!\bn)(?<!\bprot)(?<!\bgen)(?<!\bart)\.\s+(?=[A-Z])", s)
    if m:
        return s[:m.start()].strip(" ,")
    return s.rsplit(" ", 1)[0].strip(" ,") + (" …" if len(t) > pos + massimo else "")


def _agibilita(t: str) -> str:
    m = re.search(r"[^.;]*(?:certificato\s+di\s+|segnalazione\s+certificata\s+(?:di|per\s+l')\s*)?(?:agibilit|abitabilit)[^.;]*[.;]", t, re.I)
    return m[0].strip() if m else ""


def _frase(t: str, pos: int, massimo: int = 500) -> str:
    """Frase che contiene la posizione 'pos' (delimitata da punto o punto e virgola)."""
    inizio = max(t.rfind(". ", 0, pos), t.rfind("; ", 0, pos), t.rfind(": ", 0, pos))
    inizio = 0 if inizio < 0 else inizio + 2
    if pos - inizio > massimo // 2:
        inizio = t.rfind(" ", 0, pos - massimo // 2) + 1
    fine = len(t)
    for sep in (". ", "; "):
        i = t.find(sep, pos)
        while i > 0 and re.search(r"(?:\bn|\bart|\bsig|\bdott|\bprot|\bgen|\bcod|\bciv|\bL|\bD\.P\.R|\bRep|\bRacc|\bpag|\bsez|\bmapp|\bsub)$", t[max(0, i - 6):i], re.I):
            i = t.find(sep, i + 2)
        if 0 < i < fine:
            fine = i + 1
    if fine - pos > massimo // 2 + 200:
        fine = t.find(" ", pos + massimo // 2 + 150)
        fine = len(t) if fine < 0 else fine
        return t[inizio:fine].strip() + " …"
    return t[inizio:fine].strip()


# -------------------------------------------------------- clausole particolari

CATEGORIE_CLAUSOLE = [
    ("Servitù", r"servit[uù]"),
    ("Ipoteche, pignoramenti e gravami", r"ipotec\w+|pignorament\w+|sequestr\w+|trascrizion\w+\s+pregiudizievol\w+|"
                                         r"iscrizion\w+\s+ipotecari\w+|privilegi\w*\s+(?:speciali|fiscali)"),
    ("Vincoli", r"vincol\w+(?!\s+pertinenzial)"),
    ("Pertinenze e posti auto (L. 122/1989)", r"vincolo\s+pertinenzial\w+|legge\s+(?:n\.\s*)?122(?:/|\s+del\s+)(?:19)?89|L\.\s*122/(?:19)?89|Tognoli"),
    ("Diritti di prelazione", r"prelazion\w+"),
    ("Usufrutto, abitazione e diritti riservati", r"usufrutt\w+|nuda\s+propriet|diritto\s+di\s+abitazione|diritto\s+d'uso|"
                                                 r"si\s+riserva|riserv(?:a|ando)\s+(?:a\s+(?:se|favore)|il\s+diritto)"),
    ("Edilizia convenzionata / PEEP", r"edilizia\s+(?:economica|residenziale\s+pubblica|convenzionat\w+|agevolat\w+)|"
                                      r"P\.?\s?E\.?\s?E\.?\s?P\.?\b|convenzione\s+(?:edilizia|urbanistica|con\s+il\s+Comune)|"
                                      r"legge\s+(?:n\.\s*)?865|L\.\s*865/(?:19)?71|prezzo\s+massimo\s+di\s+cessione"),
    ("Regolamento di condominio e parti comuni", r"regolamento\s+(?:di|del|condominiale)\s*(?:condominio)?|tabell\w+\s+millesimal\w+|"
                                                 r"parti\s+comuni|millesim\w+"),
    ("Agevolazioni fiscali (prima casa)", r"prima\s+casa|nota\s+II-?\s?bis|credito\s+d'imposta|agevolazion\w+\s+fiscal\w+"),
    ("Locazioni e occupazione", r"\blocat[oaie]\b|contratt\w+\s+di\s+locazione|conduttor\w+|comodato"),
    ("Fondo patrimoniale, trust e destinazioni", r"fondo\s+patrimoniale|\btrust\b|2645[\s-]*ter|vincolo\s+di\s+destinazione"),
    ("Patti e condizioni particolari", r"patto\s+(?:di|speciale|particolare)|patti\s+(?:speciali|particolari)|"
                                       r"condizione\s+(?:sospensiva|risolutiva)|riservato\s+dominio|clausola\s+(?:penale|risolutiva)|"
                                       r"diritto\s+di\s+riscatto|pattuiscono|convengono\s+(?:espressamente|inoltre|altresì)"),
]

# formule di rito presenti in quasi tutti gli atti: non sono clausole particolari
_ECCEZIONI = r"ad\s+eccezione|eccett\w+|salvo\s+(?:quell|la|il|le|i)\b|salvo\s+quanto|tranne|ad\s+esclusione|fatt[aoie]\s+salv|ad\s+esempio|in\s+particolare|costituit\w+|a\s+favore|a\s+carico\s+(?:del|della|dei|delle)\s+(?:fondo|mappale|particella|unit)"
_TERMINI_LIBERTA = ["pesi", "vincoli", "ipoteche", "servitù", "servitu", "oneri", "trascrizioni", "iscrizioni",
                    "privilegi", "gravami", "pignoramenti", "liti", "sequestri"]


def _formula_di_rito(frase: str) -> bool:
    f = frase.lower()
    if re.search(_ECCEZIONI, f):
        return False
    # "libero da pesi, vincoli, ipoteche, trascrizioni pregiudizievoli..."
    if re.search(r"\bliber[oaie]\b|\bfranc[oaie]\b|garantisc\w+.{0,60}libert", f) and \
            sum(1 for x in _TERMINI_LIBERTA if x in f) >= 2:
        return True
    # "con tutte le servitù attive e passive se e come esistenti", "nello stato di fatto e di diritto"
    if re.search(r"servit[uù]\s+attive\s+e\s+passive", f) and not re.search(r"passaggio|elettrodott|acquedott|veduta|metanodott|fognat|scarico|condott", f):
        return True
    # rinuncia all'ipoteca legale: formula di rito
    if re.search(r"rinunci\w+.{0,40}ipoteca\s+legale|esonerando.{0,80}conservatore", f):
        return True
    # "il presente atto ... non è soggetto a prelazione" e simili restano: sono informativi
    return False


def clausole(t: str) -> dict:
    """{categoria: [frasi]} per le clausole particolari; le formule di rito sono riassunte a parte."""
    out: dict[str, list[str]] = {}
    rito: set[str] = set()
    for nome, regex in CATEGORIE_CLAUSOLE:
        frasi: list[str] = []
        for m in re.finditer(regex, t, re.I):
            f = _frase(t, m.start())
            if _formula_di_rito(f):
                rito.add(nome)
                continue
            if any(f == x or f in x or x in f for x in frasi):
                continue
            # una frase gia' riportata in un'altra categoria non si ripete
            if any(f == x for lista in out.values() for x in lista):
                continue
            frasi.append(f)
            if len(frasi) >= 6:
                break
        if frasi:
            out[nome] = frasi
    if rito:
        out["_formule_di_rito"] = sorted(rito)
    return out
