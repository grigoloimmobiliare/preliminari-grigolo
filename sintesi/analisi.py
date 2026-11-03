"""Unisce atto di provenienza e visure in un'unica sintesi e fa i controlli di coerenza."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from app import testo as tx

from . import provenienza, visura

log = logging.getLogger(__name__)


def _norm_nome(s: str) -> str:
    return " ".join(sorted(re.sub(r"[^A-Z ]", "", (s or "").upper().replace("'", " ")).split()))


def _chiave_unita(u: dict) -> tuple:
    return (u.get("foglio", "").lstrip("0"), u.get("particella", "").lstrip("0"), (u.get("sub") or "").lstrip("0"))


def _etichetta_unita(u: dict) -> str:
    s = f"Fg. {u.get('foglio', '?')} part. {u.get('particella', '?')}"
    if u.get("sub"):
        s += f" sub {u['sub']}"
    if u.get("sezione"):
        s = f"Sez. {u['sezione']} " + s
    return s


def analizza(file_atti: list[Path], file_visure: list[Path], oggi: date | None = None) -> dict:
    oggi = oggi or date.today()
    atti, visure, errori = [], [], []
    for f in file_atti:
        try:
            atti.append(provenienza.estrai(f))
        except Exception as e:  # un file illeggibile non deve bloccare il resto
            log.exception("Atto non leggibile: %s", f)
            errori.append(f"{f.name}: lettura non riuscita ({e})")
    for f in file_visure:
        try:
            visure.append(visura.estrai(f))
        except Exception as e:
            log.exception("Visura non leggibile: %s", f)
            errori.append(f"{f.name}: lettura non riuscita ({e})")
    return componi(atti, visure, errori, oggi)


def componi(atti: list[dict], visure: list[dict], errori: list[str] | None = None, oggi: date | None = None) -> dict:
    oggi = oggi or date.today()
    avvisi: list[dict] = [{"livello": "errore", "testo": e} for e in (errori or [])]

    def avviso(testo: str, livello: str = "attenzione"):
        avvisi.append({"livello": livello, "testo": testo})

    # l'atto di provenienza e' il primo che contiene estremi riconosciuti
    atto = next((a for a in atti if a.get("repertorio") or a.get("notaio")), atti[0] if atti else {})

    # ------------------------------------------------------------ catastali
    unita: list[dict] = []
    for v in visure:
        for u in v.get("unita", []):
            if not any(_chiave_unita(x) == _chiave_unita(u) for x in unita):
                unita.append({**u, "comune": v.get("comune", ""), "fonte": "visura"})
    unita_atto = atto.get("catastali", []) if atto else []
    if not unita:
        unita = [{**u, "superficie": "", "indirizzo": "", "fonte": "atto"} for u in unita_atto]
        if unita:
            avviso("Dati catastali presi dall'atto (nessuna visura leggibile): potrebbero non essere aggiornati.")

    # ------------------------------------------------------------ proprietari attuali (visura)
    proprietari: dict[str, dict] = {}
    for v in visure:
        etich = ", ".join(_etichetta_unita(u) for u in v.get("unita", [])) or v.get("_file", "")
        for i in v.get("intestati", []):
            k = i["codice_fiscale"] or _norm_nome(i["nominativo"])
            p = proprietari.setdefault(k, {**i, "diritti": []})
            if i.get("diritto"):
                voce = i["diritto"] + (f" ({etich})" if len(visure) > 1 else "")
                if voce not in p["diritti"]:
                    p["diritti"].append(voce)
    proprietari_l = list(proprietari.values())

    # ------------------------------------------------------------ controlli
    if not atti:
        avviso("Nessun atto di provenienza caricato.", "errore")
    if not visure:
        avviso("Nessuna visura catastale caricata.", "errore")

    for a in atti:
        if a.get("_metodo") == "OCR":
            avviso(f"{a.get('_file', 'Atto')}: il PDF non contiene testo, è stato letto con OCR. Verificare i dati con attenzione.")
    for v in visure:
        if v.get("_metodo") == "OCR":
            avviso(f"{v.get('_file', 'Visura')}: il PDF non contiene testo, è stata letta con OCR. Verificare i dati.")
        for x in v.get("avvisi", []):
            avviso(f"{v.get('_file', 'Visura')}: {x}")
        d = tx.parse_data(v.get("data"))
        if d and (oggi - d).days > 90:
            avviso(f"{v.get('_file', 'Visura')}: visura del {v['data']}, più vecchia di 3 mesi. Conviene richiederne una aggiornata.")
        # somma delle quote di proprieta'
        quote = [visura.quota(i.get("diritto", "")) for i in v.get("intestati", []) if re.match(r"propriet", i.get("diritto", ""), re.I)]
        quote = [q for q in quote if q]
        if quote:
            from fractions import Fraction
            tot = sum(Fraction(n, d) for n, d in quote)
            if tot != 1:
                avviso(f"{v.get('_file', 'Visura')}: la somma delle quote di proprietà è {tot}, non 1/1. Verificare gli intestati.")

    # acquirenti dell'atto vs intestati catastali
    acquirenti = atto.get("intestatari", []) if atto else []
    coincidono = None
    successioni = [v["successione"] for v in visure if v.get("successione")]
    if acquirenti and proprietari_l:
        cf_atto = {c["codice_fiscale"] for c in acquirenti if c.get("codice_fiscale")}
        cf_vis = {p["codice_fiscale"] for p in proprietari_l if p.get("codice_fiscale")}
        if cf_atto and cf_vis:
            coincidono = cf_atto == cf_vis
        else:
            coincidono = {_norm_nome(c["nominativo"]) for c in acquirenti} == {_norm_nome(p["nominativo"]) for p in proprietari_l}
        if not coincidono:
            testo = "Gli intestati della visura NON coincidono con gli acquirenti dell'atto di provenienza."
            if successioni:
                s = successioni[0]
                testo += " In visura risulta una successione" + (f" di {tx.titolo(s['defunto'])}" if s.get("defunto") else "") + \
                         (f" del {s['data']}" if s.get("data") else "") + \
                         ": serve anche la dichiarazione di successione con accettazione dell'eredità (trascritta)."
            else:
                testo += " Possibile successione o passaggio successivo all'atto: verificare la provenienza aggiornata."
            avviso(testo, "errore")
    elif successioni:
        avviso("In visura l'ultimo passaggio risulta una successione: verificare dichiarazione di successione "
               "e accettazione dell'eredità.", "errore")

    # l'atto citato in visura e' quello caricato?
    if atto and atto.get("repertorio"):
        for v in visure:
            e = visura.estremi_atto_derivante(v.get("derivanti_da", ""))
            if e.get("repertorio") and e["repertorio"].replace(".", "") != atto["repertorio"].replace(".", ""):
                avviso(f"{v.get('_file', 'Visura')}: gli intestati derivano dall'atto rep. {e['repertorio']}"
                       f"{' del ' + e['data'] if e.get('data') else ''}, diverso dall'atto caricato (rep. {atto['repertorio']}).")

    # unita' dell'atto e della visura
    if unita_atto and any(u.get("fonte") == "visura" for u in unita):
        chiavi_vis = {_chiave_unita(u) for u in unita}
        for u in unita_atto:
            if _chiave_unita(u) not in chiavi_vis:
                avviso(f"L'unità {_etichetta_unita(u)} dell'atto non compare nelle visure caricate "
                       "(visura mancante, oppure soppressa/variata dopo l'atto).")
        chiavi_atto = {_chiave_unita(u) for u in unita_atto}
        for u in unita:
            if _chiave_unita(u) not in chiavi_atto:
                avviso(f"L'unità {_etichetta_unita(u)} della visura non è citata nell'atto di provenienza "
                       "(nuovo identificativo dopo una variazione o immobile diverso).", "info")
            else:
                ua = next(x for x in unita_atto if _chiave_unita(x) == _chiave_unita(u))
                if ua.get("categoria") and u.get("categoria") and ua["categoria"] != u["categoria"]:
                    avviso(f"{_etichetta_unita(u)}: categoria {ua['categoria']} nell'atto, {u['categoria']} in visura "
                           "(variazione catastale successiva all'atto).", "info")

    # tipo di provenienza
    data_atto = tx.parse_data(atto.get("data_atto")) if atto else None
    if atto and atto.get("tipo_atto") == "donazione":
        testo = "Provenienza da DONAZIONE: possibili azioni di riduzione dei legittimari"
        if data_atto:
            anni = (oggi - data_atto).days / 365.25
            testo += f" (donazione di {anni:.0f} anni fa; il rischio si riduce trascorsi 20 anni dalla trascrizione, art. 563 c.c.)"
        testo += ". Verificare con il notaio e con la banca dell'acquirente in caso di mutuo."
        avviso(testo, "errore")
    if atto and atto.get("prima_casa") and data_atto and (oggi - data_atto).days < 5 * 365:
        avviso(f"Acquisto con agevolazioni prima casa del {atto['data_atto']}: rivendita entro 5 anni, "
               "il venditore decade dalle agevolazioni salvo riacquisto di altra prima casa entro un anno.")
    if atto and not atto.get("trascrizione"):
        avviso("Estremi di trascrizione dell'atto non trovati: verificarli (spesso sono nella nota a margine "
               "o nella copia con annotazioni).", "info")

    ordine = {"errore": 0, "attenzione": 1, "info": 2}
    avvisi.sort(key=lambda a: ordine.get(a["livello"], 1))
    return {
        "atto": atto,
        "atti": atti,
        "visure": visure,
        "unita": unita,
        "proprietari": proprietari_l,
        "acquirenti": acquirenti,
        "coincidono": coincidono,
        "successioni": successioni,
        "avvisi": avvisi,
        "eseguita": oggi.isoformat(),
    }
