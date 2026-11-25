"""Analisi dell'atto di provenienza e punti di attenzione per la sintesi."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from app import testo as tx

from . import provenienza

log = logging.getLogger(__name__)


def analizza(file_atti: list[Path], oggi: date | None = None) -> dict:
    atti, errori = [], []
    for f in file_atti:
        try:
            atti.append(provenienza.estrai(f))
        except Exception as e:  # un file illeggibile non deve bloccare il resto
            log.exception("Atto non leggibile: %s", f)
            errori.append(f"{f.name}: lettura non riuscita ({e})")
    return componi(atti, errori, oggi)


def _anni(da: date | None, oggi: date) -> float | None:
    return (oggi - da).days / 365.25 if da else None


def componi(atti: list[dict], errori: list[str] | None = None, oggi: date | None = None) -> dict:
    oggi = oggi or date.today()
    avvisi: list[dict] = [{"livello": "errore", "tema": "documenti", "testo": e} for e in (errori or [])]

    def avviso(tema: str, testo: str, livello: str = "attenzione"):
        avvisi.append({"livello": livello, "tema": tema, "testo": testo})

    # l'atto di provenienza e' il piu' recente tra quelli con estremi riconosciuti
    validi = [a for a in atti if a.get("repertorio") or a.get("notaio")] or atti
    atto = max(validi, key=lambda a: tx.data_iso(a.get("data_atto")) or "", default={})

    if not atti:
        avviso("documenti", "Nessun atto di provenienza leggibile.", "errore")
    for a in atti:
        if (a.get("_metodo") or "").startswith("OCR"):
            motivo = "testo del PDF illeggibile" if "illeggibile" in a["_metodo"] else "PDF scansionato"
            avviso("documenti", f"{a.get('_file', 'Atto')}: {motivo}, letto con OCR. Verificare nomi, numeri e date "
                                "sull'originale.", "info")
    if not atto:
        return {"atto": {}, "atti": atti, "avvisi": avvisi, "eseguita": oggi.isoformat()}

    data_atto = tx.parse_data(atto.get("data_atto"))

    # ------------------------------------------------------------ urbanistica
    note = {n["tema"]: n for n in atto.get("note_urbanistiche", [])}
    if not atto.get("titoli_edilizi") and not atto.get("ante_67"):
        avviso("urbanistica", "Nell'atto non sono stati riconosciuti titoli edilizi né la dichiarazione di costruzione "
                              "ante 1° settembre 1967: verificare la dichiarazione urbanistica e richiedere l'accesso agli atti in Comune.",
               "errore")
    if any("sanatoria" in t["tipo"].lower() or t["tipo"].startswith(("Condono", "Accertamento"))
           for t in atto.get("titoli_edilizi", [])):
        avviso("urbanistica", "Presenti sanatorie o condoni: verificare che la pratica sia definita (titolo rilasciato, "
                              "oblazione e oneri pagati).")
    if "Difformità o abusi dichiarati" in note:
        avviso("urbanistica", "L'atto cita difformità o opere abusive: possibile ostacolo alla vendita, "
                              "da verificare con un tecnico prima del preliminare.", "errore")
    if "Sanatorie in corso / nullità urbanistica" in note:
        avviso("urbanistica", "L'atto cita sanatorie non definite o norme sulla nullità urbanistica: verificare con un tecnico.",
               "errore")
    if not atto.get("agibilita_testo"):
        avviso("urbanistica", "Agibilità/abitabilità non citata nell'atto: verificarne l'esistenza.", "info")
    verifica = note.get("Verifica tecnica della regolarità urbanistica")
    if verifica and any(re.search(r"rinunci", f, re.I) for f in verifica["frasi"]):
        avviso("urbanistica", "Nell'atto le parti hanno rinunciato alla relazione di un tecnico sulla regolarità "
                              "urbanistica: la conformità si basa solo sulle dichiarazioni del venditore. "
                              "Consigliabile una verifica tecnica prima del preliminare.")
    ape = atto.get("ape") or {}
    scadenza = tx.parse_data(ape.get("scadenza"))
    if scadenza and scadenza < oggi:
        avviso("urbanistica", f"APE del {ape['data']} scaduto il {ape['scadenza']} (validità 10 anni): "
                              "serve un nuovo attestato per annunci, preliminare e rogito.", "errore")
    elif scadenza and (scadenza - oggi).days < 180:
        avviso("urbanistica", f"APE del {ape['data']} in scadenza il {ape['scadenza']}: verificare che sia valido al rogito.")
    elif atto.get("ape") is not None and not ape:
        avviso("urbanistica", "APE non citato nell'atto: andrà predisposto per la vendita.", "info")

    # ------------------------------------------------------------ provenienza
    prov = atto.get("provenienza_precedente") or {}
    titoli = prov.get("titoli", [])
    if not prov.get("testo"):
        avviso("provenienza", "Provenienza precedente non trovata nell'atto: verificare come la parte venditrice "
                              "aveva acquistato (spesso indicata in un articolo 'Provenienza' o 'Titolo').", "errore")
    tipi = [t["tipo"] for t in titoli]
    if "successione" in tipi and not any(t.get("accettazione_eredita") for t in titoli):
        avviso("provenienza", "Provenienza per successione senza menzione dell'accettazione dell'eredità trascritta: "
                              "senza di essa la continuità delle trascrizioni non è garantita (art. 2650 c.c.). "
                              "Verificare ed eventualmente farla trascrivere prima del rogito.", "errore")
    donazioni = [t for t in titoli if t["tipo"] == "donazione"]
    if atto.get("tipo_atto") == "donazione":
        donazioni.insert(0, {"data": atto.get("data_atto", "")})
    for d in donazioni:
        anni = _anni(tx.parse_data(d.get("data")), oggi)
        if anni is None or anni < 20:
            avviso("provenienza", "Provenienza da DONAZIONE" + (f" del {d['data']} ({anni:.0f} anni fa)" if anni is not None else "")
                   + ": i legittimari del donante possono agire in riduzione/restituzione fino a 20 anni dalla trascrizione "
                     "(art. 563 c.c.). Le banche spesso non finanziano: valutare rinuncia all'opposizione o polizza.", "errore")
    # ventennio: il titolo precedente piu' vecchio citato
    date_titoli = [tx.parse_data(t.get("data")) for t in titoli if t.get("data")]
    date_titoli = [d for d in date_titoli if d and (not data_atto or d < data_atto)]
    if date_titoli and _anni(min(date_titoli), oggi) < 20:
        avviso("provenienza", f"Il titolo più vecchio citato è del {min(date_titoli):%d/%m/%Y}: per coprire il ventennio "
                              "servirà risalire anche alla provenienza precedente.", "info")

    # ------------------------------------------------------------ vincoli e gravami
    vincoli = atto.get("vincoli") or {}
    for v in vincoli.get("trovati", []):
        if v["gravita"] == "alta":
            avviso("vincoli", f"{v['categoria']}: {v['nota']}", "errore")
    if atto.get("prima_casa") and data_atto and _anni(data_atto, oggi) < 5:
        entro = data_atto.replace(year=data_atto.year + 5) if not (data_atto.month == 2 and data_atto.day == 29) \
            else data_atto.replace(year=data_atto.year + 5, day=28)
        avviso("vincoli", f"Acquisto con agevolazioni prima casa del {atto['data_atto']}: se l'attuale proprietario vende "
                          f"prima del {entro:%d/%m/%Y} decade dalle agevolazioni (imposte piene + sanzione 30%), "
                          "salvo riacquisto di un'altra prima casa entro un anno.")
    if not atto.get("trascrizione"):
        avviso("documenti", "Estremi di trascrizione dell'atto non trovati: verificarli (spesso nella nota a margine "
                            "o nella copia con annotazioni).", "info")

    ordine = {"errore": 0, "attenzione": 1, "info": 2}
    avvisi.sort(key=lambda a: ordine.get(a["livello"], 1))
    return {"atto": atto, "atti": atti, "avvisi": avvisi, "eseguita": oggi.isoformat()}
