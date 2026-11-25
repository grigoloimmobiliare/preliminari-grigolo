"""Analisi degli atti di una pratica e punti di attenzione per la sintesi.

Una pratica puo' contenere piu' atti correlati: l'ultimo atto di provenienza e i titoli
precedenti (successioni, accettazioni, donazioni, divisioni, atti vecchi). Gli atti vengono
messi in ordine di data: il piu' recente e' l'atto principale (proprietari, immobile, dati
catastali); urbanistica e vincoli vengono raccolti da tutti gli atti, con l'indicazione
dell'atto da cui provengono; con le provenienze citate si ricostruisce la catena dei passaggi.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from app import testo as tx

from . import provenienza

log = logging.getLogger(__name__)


def firma_file(f: Path) -> list:
    st = f.stat()
    return [st.st_size, int(st.st_mtime)]


def analizza(file_atti: list[Path], oggi: date | None = None, cache: dict | None = None) -> dict:
    """Legge gli atti (riusando 'cache' {nome file: {"firma", "dati"}} per quelli gia' letti) e compone la sintesi."""
    atti, errori = [], []
    for f in file_atti:
        firma = firma_file(f)
        if cache is not None and cache.get(f.name, {}).get("firma") == firma:
            atti.append(cache[f.name]["dati"])
            continue
        try:
            dati = provenienza.estrai(f)
        except Exception as e:  # un file illeggibile non deve bloccare il resto
            log.exception("Atto non leggibile: %s", f)
            errori.append(f"{f.name}: lettura non riuscita ({e})")
            continue
        atti.append(dati)
        if cache is not None:
            cache[f.name] = {"firma": firma, "dati": dati}
    if cache is not None:
        for nome in [n for n in cache if n not in {f.name for f in file_atti}]:
            del cache[nome]   # file rimossi dalla pratica
    return componi(atti, errori, oggi)


def _anni(da: date | None, oggi: date) -> float | None:
    return (oggi - da).days / 365.25 if da else None


def _illeggibile(a: dict) -> bool:
    return "non riuscito" in (a.get("_metodo") or "")


def _etichetta(a: dict) -> str:
    tipo = (a.get("tipo_atto") or "atto").capitalize()
    return f"{tipo} del {a['data_atto']}" if a.get("data_atto") else f"{tipo} ({a.get('_file', '')})"


def _rep(s: str) -> str:
    return re.sub(r"\D", "", (s or "").split("/")[0])


# ------------------------------------------------------------------ avvisi di un atto

def _avvisi_atto(atto: dict, oggi: date) -> list[dict]:
    avvisi: list[dict] = []

    def avviso(tema: str, testo: str, livello: str = "attenzione"):
        avvisi.append({"livello": livello, "tema": tema, "testo": testo})

    data_atto = tx.parse_data(atto.get("data_atto"))

    # ------------------------------------------------------------ urbanistica
    note = {n["tema"]: n for n in atto.get("note_urbanistiche", [])}
    senza_urbanistica = atto.get("tipo_atto") in ("accettazione di eredità",) and not atto.get("titoli_edilizi")
    if senza_urbanistica:
        avviso("urbanistica", "Atto di accettazione di eredità: non contiene dichiarazioni urbanistiche. Recuperarle "
                              "dal titolo di provenienza del defunto o con accesso agli atti in Comune.", "info")
    elif not atto.get("titoli_edilizi") and not atto.get("ante_67"):
        avviso("urbanistica", "Negli atti non sono stati riconosciuti titoli edilizi né la dichiarazione di costruzione "
                              "ante 1° settembre 1967: verificare la dichiarazione urbanistica e richiedere l'accesso agli atti in Comune.",
               "errore")
    if any("sanatoria" in t["tipo"].lower() or t["tipo"].startswith(("Condono", "Accertamento"))
           for t in atto.get("titoli_edilizi", [])):
        avviso("urbanistica", "Presenti sanatorie o condoni: verificare che la pratica sia definita (titolo rilasciato, "
                              "oblazione e oneri pagati).")
    if "Difformità o abusi dichiarati" in note:
        avviso("urbanistica", "L'atto cita difformità o opere abusive: possibile ostacolo alla vendita, "
                              "da verificare con un tecnico prima del preliminare.", "errore")
    if "Sanatorie in corso" in note:
        avviso("urbanistica", "L'atto cita sanatorie non definite: verificare con un tecnico.", "errore")
    if not atto.get("agibilita_testo"):
        avviso("urbanistica", "Agibilità/abitabilità non citata negli atti: verificarne l'esistenza.", "info")
    if "Pratiche edilizie aperte e lavori in corso" in note:
        avviso("urbanistica", "L'atto cita pratiche edilizie aperte o lavori in corso: verificare stato della pratica, "
                              "fine lavori, agibilità e chi ne ha la titolarità prima di proporre l'immobile.")
    verifica = note.get("Verifica tecnica della regolarità urbanistica")
    if verifica and any(re.search(r"rinunci|esoner", f, re.I) for f in verifica["frasi"]):
        avviso("urbanistica", "Nell'atto la regolarità urbanistica non è stata verificata da un tecnico (rinuncia alla "
                              "relazione o esonero del notaio): si basa solo sulle dichiarazioni del venditore. "
                              "Consigliabile una verifica tecnica prima del preliminare.")
    ape = atto.get("ape") or {}
    scadenza = tx.parse_data(ape.get("scadenza"))
    if scadenza and scadenza < oggi:
        avviso("urbanistica", f"APE del {ape['data']} scaduto il {ape['scadenza']} (validità 10 anni): "
                              "serve un nuovo attestato per annunci, preliminare e rogito.", "errore")
    elif scadenza and (scadenza - oggi).days < 180:
        avviso("urbanistica", f"APE del {ape['data']} in scadenza il {ape['scadenza']}: verificare che sia valido al rogito.")
    elif atto.get("ape") is not None and not ape and not senza_urbanistica:
        avviso("urbanistica", "APE non citato negli atti: andrà predisposto per la vendita.", "info")

    # ------------------------------------------------------------ provenienza
    prov = atto.get("provenienza_precedente") or {}
    titoli = prov.get("titoli", [])
    if not prov.get("testo"):
        avviso("provenienza", "Provenienza precedente non trovata nell'atto: verificare come la parte venditrice "
                              "aveva acquistato (spesso indicata in un articolo 'Provenienza' o 'Titolo').", "errore")
    tipi = [t["tipo"] for t in titoli]
    if atto.get("continuita"):
        avviso("provenienza", "Il notaio segnala che MANCA LA CONTINUITÀ DELLE TRASCRIZIONI: prima di vendere vanno "
                              "trascritte le accettazioni di eredità mancanti. «" + atto["continuita"][:300] + "»", "errore")
    for t in titoli:
        if t.get("accettazione_in_corso"):
            avviso("provenienza", f"{t['tipo'].capitalize()}"
                   + (f" in morte di {t['defunto']}" if t.get("defunto") else "")
                   + ": accettazione dell'eredità ancora in corso di trascrizione. Verificare che sia trascritta prima "
                     "del rogito (continuità delle trascrizioni).", "errore")
    if any(t["tipo"] == "decreto di trasferimento" for t in titoli) or atto.get("tipo_atto") == "decreto di trasferimento":
        avviso("provenienza", "Provenienza da decreto di trasferimento (vendita giudiziaria/asta): verificare che le "
                              "formalità pregiudizievoli ordinate dal giudice siano state cancellate e che non ci siano "
                              "opposizioni pendenti.", "info")
    if any("testamento olografo" in t.get("note", []) for t in titoli):
        avviso("provenienza", "Nella provenienza c'è una successione per testamento olografo: se il testamento ha leso "
                              "i legittimari, possono agire in riduzione (10 anni dall'apertura della successione), "
                              "salvo rinuncia.", "info")
    if "successione" in tipi and not any(t.get("accettazione_eredita") or any("accettazione" in n for n in t.get("note", []))
                                         for t in titoli) and not atto.get("tipo_atto") == "accettazione di eredità":
        avviso("provenienza", "Provenienza per successione senza menzione dell'accettazione dell'eredità trascritta: "
                              "senza di essa la continuità delle trascrizioni non è garantita (art. 2650 c.c.). "
                              "Verificare ed eventualmente farla trascrivere prima del rogito.", "errore")
    donazioni = [t for t in titoli if t["tipo"] == "donazione"]
    if atto.get("tipo_atto") == "donazione":
        donazioni.insert(0, {"data": atto.get("data_atto", "")})
    for d in donazioni:
        data_don = tx.parse_data(d.get("data"))
        anni = _anni(data_don, oggi)
        if anni is None or anni < 20:
            limite = ""
            if data_don:
                try:
                    limite = f" (fino al {data_don.replace(year=data_don.year + 20):%d/%m/%Y} circa)"
                except ValueError:
                    limite = f" (fino al {data_don.replace(year=data_don.year + 20, day=28):%d/%m/%Y} circa)"
            avviso("provenienza", "Provenienza da DONAZIONE" + (f" del {d['data']}" if d.get("data") else "")
                   + ": per 20 anni dalla trascrizione" + limite + " i legittimari del donante possono agire in "
                     "riduzione e restituzione anche contro chi acquista (artt. 561-563 c.c.). Molte banche non concedono "
                     "il mutuo: valutare polizza, rinuncia all'opposizione o mutuo dissenso con il notaio.", "errore")

    # ------------------------------------------------------------ vincoli e gravami
    vincoli = atto.get("vincoli") or {}
    for v in vincoli.get("trovati", []):
        if v["categoria"].startswith("Provenienza donativa") and donazioni:
            continue  # gia' segnalata con la data della donazione
        if v["gravita"] == "alta":
            avviso("vincoli", f"{v['categoria']}: {v['nota']}" + (f" (da: {v['fonte']})" if v.get("fonte") else ""), "errore")
    if atto.get("prima_casa") and data_atto and _anni(data_atto, oggi) < 5:
        entro = data_atto.replace(year=data_atto.year + 5) if not (data_atto.month == 2 and data_atto.day == 29) \
            else data_atto.replace(year=data_atto.year + 5, day=28)
        avviso("vincoli", f"Acquisto con agevolazioni prima casa del {atto['data_atto']}: se l'attuale proprietario vende "
                          f"prima del {entro:%d/%m/%Y} decade dalle agevolazioni (imposte piene + sanzione 30%), "
                          "salvo riacquisto di un'altra prima casa entro un anno.")
    if not atto.get("trascrizione"):
        avviso("documenti", "Estremi di trascrizione dell'atto non trovati: verificarli (spesso nella nota a margine "
                            "o nella copia con annotazioni).", "info")
    return avvisi


# ------------------------------------------------------------------ piu' atti

def _unisci(principale: dict, precedenti: list[dict]) -> dict:
    """Vista unica per la sintesi: atto principale + urbanistica e vincoli degli atti precedenti, con la fonte."""
    vista = dict(principale)
    titoli = [dict(t) for t in principale.get("titoli_edilizi", [])]
    note = [dict(n) for n in principale.get("note_urbanistiche", [])]
    trovati = [dict(v) for v in (principale.get("vincoli") or {}).get("trovati", [])]
    for a in precedenti:
        fonte = _etichetta(a)
        for t in a.get("titoli_edilizi", []):
            if not any(t["tipo"] == x["tipo"] and t["numero"] == x["numero"] and t["data"] == x["data"] for x in titoli):
                titoli.append({**t, "fonte": fonte})
        for n in a.get("note_urbanistiche", []):
            if n["tema"].startswith("Verifica tecnica"):
                continue  # riguarda solo l'atto in cui e' scritta
            if not any(n["tema"] == x["tema"] for x in note):
                note.append({**n, "fonte": fonte})
        for v in (a.get("vincoli") or {}).get("trovati", []):
            if v["gravita"] == "info" or v["categoria"].startswith("Agevolazioni"):
                continue  # regolamento, prima casa del passato: riguardano l'atto in cui sono scritti
            if not any(v["categoria"] == x["categoria"] and v["frasi"][0][:60] == x["frasi"][0][:60] for x in trovati):
                trovati.append({**v, "fonte": fonte})
        if not vista.get("ante_67") and a.get("ante_67"):
            vista["ante_67"] = True
            vista["ante_67_fonte"] = fonte
        if not vista.get("agibilita_testo") and a.get("agibilita_testo"):
            vista["agibilita_testo"] = a["agibilita_testo"] + f" (da: {fonte})"
        if not vista.get("urbanistica_testo") and a.get("urbanistica_testo"):
            vista["urbanistica_testo"] = a["urbanistica_testo"]
            vista["urbanistica_fonte"] = fonte
        if not (vista.get("ape") or {}).get("classe") and (a.get("ape") or {}).get("classe"):
            vista["ape"] = {**a["ape"], "fonte": fonte}
    titoli.sort(key=lambda v: (tx.data_iso(v["data"]) or "9999", v["tipo"]))
    vista["titoli_edilizi"] = titoli
    vista["note_urbanistiche"] = note
    vista["vincoli"] = {**(principale.get("vincoli") or {}), "trovati": trovati}
    return vista


def _nomi(persone: list[dict], massimo: int = 4) -> str:
    nomi = [p["nominativo"] for p in persone]
    if len(nomi) > massimo:
        return ", ".join(nomi[:massimo]) + f" e altri {len(nomi) - massimo}"
    return ", ".join(nomi)


def _unita(a: dict) -> str:
    gruppi: dict[tuple, list[str]] = {}
    for u in a.get("catastali", []):
        gruppi.setdefault((u.get("foglio", ""), u.get("particella", "")), []).append(u.get("sub", ""))
    return "; ".join(f"Fg. {f} part. {p} sub " + ", ".join(s) for (f, p), s in gruppi.items())


def cronologia(atti: list[dict]) -> list[dict]:
    """Tutti i passaggi della pratica: atti caricati e titoli soltanto citati, in ordine di data."""
    voci: list[dict] = []
    for a in atti:
        if _illeggibile(a):
            voci.append({"data": "", "tipo": "atto non leggibile", "estremi": "scritto a mano o scansione illeggibile: "
                         "leggere manualmente", "passaggio": "", "unita": "", "fonte": a.get("_file", ""),
                         "caricato": True, "repertorio": ""})
            continue
        estremi = ", ".join(x for x in (f"notaio {a['notaio']}" if a.get("notaio") else "",
                                        f"rep. {a['repertorio']}" if a.get("repertorio") else "",
                                        a.get("trascrizione", "")) if x)
        passaggio = ""
        if a.get("cedenti") or a.get("intestatari"):
            passaggio = (f"da {_nomi(a.get('cedenti', []))} " if a.get("cedenti") else "") + \
                        (f"a {_nomi(a.get('intestatari', []))}" if a.get("intestatari") else "")
        if a.get("_altro_immobile"):
            estremi = "IMMOBILE DIVERSO dall'atto principale; " + estremi
        voci.append({"data": a.get("data_atto", ""), "tipo": a.get("tipo_atto") or "atto", "estremi": estremi,
                     "passaggio": passaggio.strip(), "unita": _unita(a), "fonte": a.get("_file", ""),
                     "caricato": True, "repertorio": _rep(a.get("repertorio"))})
    for a in atti:
        if a.get("_altro_immobile"):
            continue  # la sua provenienza riguarda un altro immobile
        for t in (a.get("provenienza_precedente") or {}).get("titoli", []):
            rep = _rep(t.get("repertorio"))
            data = t["data_decesso"] if t.get("data_decesso") else t.get("data", "")
            defunto = f"in morte di {t['defunto']}" if t.get("defunto") else ""
            doppione = next((v for v in voci if (rep and v["repertorio"] == rep) or
                             (defunto and v["passaggio"].lower() == defunto.lower()) or
                             (data and v["data"] == data and (v["tipo"] == t["tipo"] or not v["caricato"]))), None)
            if doppione:
                continue
            estremi = ", ".join(x for x in (f"notaio {t['notaio']}" if t.get("notaio") else "",
                                            f"rep. {t['repertorio']}" if t.get("repertorio") else "",
                                            f"trascritto {t['trascrizione']}" if t.get("trascrizione") else "") if x)
            if t.get("note"):
                estremi += ("; " if estremi else "") + "; ".join(t["note"])
            voci.append({"data": data, "tipo": t["tipo"],
                         "estremi": estremi, "passaggio": defunto,
                         "unita": "", "fonte": f"citato in: {_etichetta(a)}", "caricato": False, "repertorio": rep})
    voci.sort(key=lambda v: tx.data_iso(v["data"]) or "9999")
    return voci


def _particelle(a: dict) -> set:
    return {(u.get("foglio", "").lstrip("0"), u.get("particella", "").lstrip("0")) for u in a.get("catastali", [])
            if u.get("foglio") and u.get("particella")}


def _descrivi_particelle(a: dict) -> str:
    return ", ".join(f"Fg. {f} part. {p}" for f, p in sorted(_particelle(a)))


def _stessa_persona(p: dict, altre: list[dict]) -> bool:
    cf = p.get("codice_fiscale")
    nome = " ".join(sorted(re.sub(r"[^A-Z ]", "", p["nominativo"].upper()).split()))
    for q in altre:
        if cf and q.get("codice_fiscale") == cf:
            return True
        if nome and nome == " ".join(sorted(re.sub(r"[^A-Z ]", "", q["nominativo"].upper()).split())):
            return True
    return False


def componi(atti: list[dict], errori: list[str] | None = None, oggi: date | None = None) -> dict:
    oggi = oggi or date.today()
    avvisi: list[dict] = [{"livello": "errore", "tema": "documenti", "testo": e} for e in (errori or [])]

    def avviso(tema: str, testo: str, livello: str = "attenzione"):
        avvisi.append({"livello": livello, "tema": tema, "testo": testo})

    if not atti:
        avviso("documenti", "Nessun atto leggibile nella pratica.", "errore")
        return {"atto": {}, "atti": atti, "avvisi": avvisi, "eseguita": oggi.isoformat(), "cronologia": []}

    for a in atti:
        a.pop("_altro_immobile", None)   # ricalcolato a ogni analisi (gli atti letti vengono riusati)
    leggibili = [a for a in atti if not _illeggibile(a)]
    for a in atti:
        metodo = a.get("_metodo") or ""
        if metodo.startswith("OCR") and not _illeggibile(a):
            motivo = "testo del PDF illeggibile" if "illeggibile" in metodo else "PDF scansionato"
            avviso("documenti", f"{a.get('_file', 'Atto')}: {motivo}, letto con OCR. Verificare nomi, numeri e date "
                                "sull'originale.", "info")
        elif _illeggibile(a) and leggibili:
            avviso("documenti", f"{a.get('_file', 'Atto')}: sembra scritto a mano o la scansione è illeggibile; non è "
                                "stato letto automaticamente. Compare nella cronologia solo come documento caricato: "
                                "va letto manualmente.", "info")

    if not leggibili:
        # solo atti scritti a mano o scansioni illeggibili: gli altri controlli non avrebbero senso
        atto = atti[0]
        avvisi.insert(0, {"livello": "errore", "tema": "documenti",
                          "testo": f"{atto.get('_file', 'Atto')}: il documento sembra scritto a mano o la scansione è "
                                   "illeggibile. La lettura automatica non è possibile: l'atto va letto manualmente "
                                   "(i dati di questa sintesi non sono affidabili)."})
        return {"atto": atto, "atti": atti, "avvisi": avvisi, "eseguita": oggi.isoformat(), "illeggibile": True,
                "cronologia": cronologia(atti)}

    # l'atto principale e' il piu' recente tra quelli con estremi riconosciuti
    validi = [a for a in leggibili if a.get("repertorio") or a.get("notaio")] or leggibili
    principale = max(validi, key=lambda a: tx.data_iso(a.get("data_atto")) or "")
    # atti che riguardano un altro immobile (nessuna particella in comune): segnalati e tenuti separati
    altri_immobili = [a for a in leggibili if a is not principale and _particelle(a) and _particelle(principale)
                      and not _particelle(a) & _particelle(principale)]
    for a in altri_immobili:
        a["_altro_immobile"] = True
        avviso("documenti", f"{_etichetta(a)} ({a.get('_file', '')}) riguarda un immobile diverso "
                            f"({_descrivi_particelle(a)}) dall'atto principale ({_descrivi_particelle(principale)}): "
                            "è davvero della stessa pratica? Urbanistica e vincoli di quell'atto non sono stati uniti agli altri.")
    precedenti = sorted((a for a in leggibili if a is not principale and a not in altri_immobili),
                        key=lambda a: tx.data_iso(a.get("data_atto")) or "", reverse=True)
    vista = _unisci(principale, precedenti)

    avvisi.extend(_avvisi_atto(vista, oggi))
    # degli atti precedenti contano i problemi di provenienza e i vincoli che possono essere ancora attuali
    for a in precedenti:
        for x in _avvisi_atto(a, oggi):
            if x["tema"] not in ("provenienza", "vincoli") or x["testo"].startswith(
                    ("Provenienza precedente non trovata", "Acquisto con agevolazioni prima casa")):
                continue
            if x["tema"] == "vincoli" and x["livello"] == "errore":
                continue   # gia' riportati (con la fonte) nella vista unica
            x = {**x, "testo": f"{_etichetta(a)}: {x['testo']}"}
            if not any(y["testo"] == x["testo"] for y in avvisi):
                avvisi.append(x)

    voci = cronologia(atti)
    if len(atti) > 1:
        # continuita' dei passaggi: chi vende in un atto deve aver acquistato in uno degli atti precedenti caricati
        in_ordine = sorted((a for a in leggibili if a not in altri_immobili), key=lambda a: tx.data_iso(a.get("data_atto")) or "")
        for i, a in enumerate(in_ordine[1:], 1):
            prima = [p for b in in_ordine[:i] for p in (b.get("intestatari") or []) + (b.get("comparenti") or [])]
            mancanti = [p for p in a.get("cedenti") or [] if not _stessa_persona(p, prima)]
            if mancanti and prima:
                avviso("provenienza", f"{_etichetta(a)}: {_nomi(mancanti)} non risulta acquirente in nessuno degli atti "
                                      "precedenti caricati. Manca probabilmente un atto intermedio (o gli atti non "
                                      "riguardano lo stesso immobile).", "info")
    # ventennio sull'intera catena
    date_note = [tx.parse_data(v["data"]) for v in voci if v["data"]]
    date_note = [d for d in date_note if d]
    if date_note:
        piu_vecchio = min(date_note)
        if _anni(piu_vecchio, oggi) < 20:
            avviso("provenienza", f"La catena ricostruita dagli atti parte dal {piu_vecchio:%d/%m/%Y}: per coprire il "
                                  f"ventennio manca il titolo precedente (anteriore al {oggi.replace(year=oggi.year - 20):%d/%m/%Y}). "
                                  "Caricarlo nella pratica se disponibile.", "info")
    citati = [v for v in voci if not v["caricato"]]
    if citati and len(atti) > 1:
        avviso("documenti", f"{len(citati)} titoli della catena sono citati negli atti ma non caricati nella pratica "
                            "(vedi cronologia).", "info")

    ordine = {"errore": 0, "attenzione": 1, "info": 2}
    avvisi.sort(key=lambda a: ordine.get(a["livello"], 1))
    return {"atto": vista, "atti": atti, "avvisi": avvisi, "eseguita": oggi.isoformat(), "cronologia": voci,
            "principale": principale.get("_file", "")}
