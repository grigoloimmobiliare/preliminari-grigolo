"""Struttura dei dati di una pratica (quello che finisce nel preliminare)."""

from __future__ import annotations

import copy

CAMPI_PERSONA = [
    # chiave, etichetta, obbligatorio
    ("sesso", "Sesso (M/F)", True),
    ("cognome", "Cognome", True),
    ("nome", "Nome", True),
    ("luogo_nascita", "Luogo di nascita", True),
    ("prov_nascita", "Prov. nascita", False),
    ("data_nascita", "Data di nascita", True),
    ("codice_fiscale", "Codice fiscale", True),
    ("doc_tipo", "Tipo documento", True),
    ("doc_numero", "N. documento", True),
    ("doc_ente", "Rilasciato da", True),
    ("doc_rilascio", "Data rilascio", True),
    ("doc_scadenza", "Data scadenza", True),
    ("res_indirizzo", "Indirizzo di residenza", True),
    ("res_comune", "Comune di residenza", True),
    ("res_prov", "Prov. residenza", False),
    ("stato_civile", "Stato civile / regime patrimoniale", True),
]

CAMPI_SOCIETA = [
    ("soc_denominazione", "Denominazione società", True),
    ("soc_sede", "Sede legale (comune e indirizzo)", True),
    ("soc_cf", "C.F. / P.IVA società", True),
    ("soc_rea", "Iscrizione Registro Imprese / REA", False),
    ("soc_qualita", "Qualità del firmatario (es. legale rappresentante)", True),
]

CAMPI_UNITA = [
    ("sezione", "Sez."), ("foglio", "Foglio"), ("particella", "Particella"), ("sub", "Sub."),
    ("categoria", "Cat."), ("classe", "Classe"), ("consistenza", "Consistenza"), ("rendita", "Rendita €"),
]

MODALITA_PAGAMENTO = {
    "assegno_agenzia": "Assegno consegnato all'agenzia",
    "assegno": "Assegno non trasferibile",
    "bonifico": "Bonifico bancario",
    "bonifico_agenzia": "Bonifico sul c/c dell'agenzia",
    "altro": "Altro (testo libero)",
}


def persona_vuota() -> dict:
    p = {k: "" for k, _, _ in CAMPI_PERSONA + CAMPI_SOCIETA}
    p["tipo"] = "fisica"
    p["doc_tipo"] = "C.I."
    p["soc_qualita"] = "legale rappresentante"
    return p


def unita_vuota() -> dict:
    return {k: "" for k, _ in CAMPI_UNITA}


def versamento_vuoto(tipo: str = "caparra") -> dict:
    return {"tipo": tipo, "importo": "", "modalita": "bonifico", "stato": "da_versare",
            "riferimento": "", "scadenza": "", "testo_libero": ""}


DATI_VUOTI = {
    "venditori": [],
    "acquirenti": [],
    "immobile": {
        "tipologia": "fabbricato residenziale",
        "comune": "", "prov": "", "indirizzo": "", "descrizione": "",
        "unita": [],
        "n_planimetrie": "",
    },
    "provenienza": {
        "tipo_atto": "compravendita", "notaio": "", "notaio_sede": "", "data": "",
        "repertorio": "", "raccolta": "", "registrazione": "", "trascrizione": "",
    },
    "accordi": {
        "prezzo": "",
        "versamenti": [],
        "saldo_modalita": "a mezzo assegni circolari o bonifico bancario istantaneo al momento del rogito notarile, anche per mezzo di intervento di istituto mutuante",
        "mutuo_condizione": False, "mutuo_importo": "", "mutuo_entro": "",
        "data_rogito": "",
        "notaio_scelta": "Parte Promissaria Acquirente",
        "stato_occupazione": "libero",
        "spese_condominiali_annue": "",
        "clausole": [],
    },
    "urbanistica": {
        "dichiarazione": "",
        "ante_67": False,
        "conformita_catastale": True,
        "agibilita_presente": True,
        "agibilita": "",
    },
    "ape": {"classe": "", "ipe": "", "tecnico": "", "data": ""},
    "firma": {"luogo": "Treviso (TV)", "data": "", "foro": "Treviso"},
}


def dati_vuoti() -> dict:
    return copy.deepcopy(DATI_VUOTI)


def completa(dati: dict) -> dict:
    """Aggiunge le chiavi mancanti (utile quando il modello dati si evolve)."""
    base = dati_vuoti()
    for k, v in base.items():
        if k not in dati:
            dati[k] = v
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                dati[k].setdefault(k2, v2)
    for ruolo in ("venditori", "acquirenti"):
        for p in dati[ruolo]:
            for k, v in persona_vuota().items():
                p.setdefault(k, v)
    for u in dati["immobile"]["unita"]:
        for k, v in unita_vuota().items():
            u.setdefault(k, v)
    for v in dati["accordi"]["versamenti"]:
        for k, x in versamento_vuoto().items():
            v.setdefault(k, x)
    return dati
