"""Applicazione web interna per la compilazione automatica dei preliminari di compravendita."""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analisi, genera, modello_dati, pratiche, verifiche
from . import testo as tx
from .estrazione import ocr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("preliminari")

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Preliminari Grigolo", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "web" / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "web" / "templates")
templates.env.globals.update(
    CATEGORIE=pratiche.CATEGORIE,
    CAMPI_PERSONA=modello_dati.CAMPI_PERSONA,
    CAMPI_SOCIETA=modello_dati.CAMPI_SOCIETA,
    CAMPI_UNITA=modello_dati.CAMPI_UNITA,
    MODALITA=modello_dati.MODALITA_PAGAMENTO,
)
templates.env.filters["euro"] = tx.euro_completo

MAX_FILE = 60 * 1024 * 1024


def _pratica(pid: str) -> pratiche.Pratica:
    try:
        return pratiche.apri(pid)
    except FileNotFoundError:
        raise HTTPException(404, "Pratica non trovata")


def _vai(pid: str, ancora: str = "", msg: str = "") -> RedirectResponse:
    url = f"/pratiche/{pid}"
    if msg:
        url += "?msg=" + re.sub(r"[^\w\s.,:'()àèéìòù-]", "", msg)[:200]
    if ancora:
        url += "#" + ancora
    return RedirectResponse(url, status_code=303)


# ---------------------------------------------------------------- elenco

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"pratiche": pratiche.elenco()})


@app.post("/pratiche")
def nuova(nome: str = Form(...)):
    p = pratiche.crea(nome)
    return _vai(p.id, "documenti")


@app.post("/pratiche/{pid}/elimina")
def elimina_pratica(pid: str, conferma: str = Form("")):
    p = _pratica(pid)
    if conferma.strip().lower() != "elimina":
        return _vai(pid, msg="Per eliminare la pratica scrivi ELIMINA nella casella di conferma")
    cestino = pratiche.DATI / "cestino"
    cestino.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p.cartella), str(cestino / f"{p.id} - {datetime.now():%Y%m%d-%H%M%S}"))
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------- pratica

@app.get("/pratiche/{pid}")
def pagina_pratica(request: Request, pid: str, msg: str = ""):
    p = _pratica(pid)
    stato = p.carica()
    if stato["analisi"].get("stato") == "in corso" and not analisi.in_corso(p):
        # il programma e' stato riavviato durante un'analisi
        stato["analisi"] = {"stato": "interrotta", "errore": "Analisi interrotta: rilanciala."}
        p.salva(stato)
    file_cat = {c: p.file_categoria(c) for c in pratiche.CATEGORIE}
    proposta = []
    for f in file_cat["proposta"]:
        for i, affiancate in enumerate(ocr.pagine_affiancate(f)):
            for parte in ((1, 2) if affiancate else (0,)):
                proposta.append({"nome": f.name, "pagina": i, "parte": parte})
    controlli = verifiche.controlla(stato, {c: len(v) for c, v in file_cat.items()}) \
        if stato["analisi"].get("stato") == "completata" or stato.get("salvato") else []
    return templates.TemplateResponse(request, "pratica.html", {
        "p": p, "stato": stato, "dati": stato["dati"], "file_cat": file_cat, "proposta": proposta,
        "controlli": controlli, "in_corso": analisi.in_corso(p),
        "generati": p.documenti_generati(), "msg": msg,
        "persona_vuota": modello_dati.persona_vuota(), "unita_vuota": modello_dati.unita_vuota(),
        "versamento_vuoto": modello_dati.versamento_vuoto(),
    })


@app.post("/pratiche/{pid}/carica/{cat}")
async def carica(pid: str, cat: str, files: list[UploadFile] = File(...)):
    p = _pratica(pid)
    if cat not in pratiche.CATEGORIE:
        raise HTTPException(400, "Categoria non valida")
    caricati, scartati = 0, []
    for f in files:
        if not f.filename:
            continue
        if Path(f.filename).suffix.lower() not in ocr.ESTENSIONI_AMMESSE:
            scartati.append(f.filename)
            continue
        dati = await f.read()
        if len(dati) > MAX_FILE:
            scartati.append(f.filename)
            continue
        p.aggiungi_file(cat, f.filename, dati)
        caricati += 1
    msg = f"Caricati {caricati} file"
    if scartati:
        msg += f". Scartati (formato non ammesso o troppo grandi): {', '.join(scartati)}"
    return _vai(pid, "documenti", msg)


@app.post("/pratiche/{pid}/rimuovi/{cat}/{nome}")
def rimuovi(pid: str, cat: str, nome: str):
    p = _pratica(pid)
    try:
        f = p.file(cat, nome)
    except (FileNotFoundError, KeyError):
        raise HTTPException(404)
    cestino = p.cartella / ".rimossi"
    cestino.mkdir(exist_ok=True)
    shutil.move(str(f), str(cestino / f"{datetime.now():%Y%m%d-%H%M%S} {f.name}"))
    return _vai(pid, "documenti", f"Rimosso {nome}")


@app.get("/pratiche/{pid}/file/{cat}/{nome}")
def file_originale(pid: str, cat: str, nome: str):
    p = _pratica(pid)
    try:
        return FileResponse(p.file(cat, nome))
    except (FileNotFoundError, KeyError):
        raise HTTPException(404)


@app.get("/pratiche/{pid}/anteprima/{cat}/{nome}/{pagina}.png")
def anteprima(pid: str, cat: str, nome: str, pagina: int, larghezza: int = 1100, parte: int = 0):
    p = _pratica(pid)
    try:
        f = p.file(cat, nome)
    except (FileNotFoundError, KeyError):
        raise HTTPException(404)
    larghezza = max(300, min(larghezza, 2400))
    parte = parte if parte in (0, 1, 2) else 0
    cache = p.cartella / ".anteprime" / f"{cat}-{f.name}-{pagina}-{parte}-{larghezza}.png"
    if not cache.exists() or cache.stat().st_mtime < f.stat().st_mtime:
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(ocr.anteprima_png(f, pagina, larghezza, parte))
    return FileResponse(cache, media_type="image/png")


@app.post("/pratiche/{pid}/analizza")
def avvia_analisi(pid: str, sovrascrivi: str = Form("")):
    p = _pratica(pid)
    if not analisi.avvia(p, sovrascrivi=bool(sovrascrivi)):
        return _vai(pid, "analisi", "Analisi già in corso")
    return _vai(pid, "analisi")


@app.get("/pratiche/{pid}/stato")
def stato_analisi(pid: str):
    p = _pratica(pid)
    s = p.carica()["analisi"]
    s["in_corso"] = analisi.in_corso(p)
    return JSONResponse(s)


# ------------------------------------------------------------ salvataggio dati

def _form_annidato(elementi: list[tuple[str, str]]) -> dict:
    """Converte i campi 'venditori.0.cognome' in una struttura annidata.
    Gli indici numerici diventano liste (ordinate per indice)."""
    radice: dict = {}
    for chiave, valore in elementi:
        if not chiave or chiave.startswith("_azione"):
            continue
        parti = chiave.split(".")
        nodo = radice
        for i, parte in enumerate(parti):
            ultimo = i == len(parti) - 1
            if ultimo:
                nodo[parte] = valore  # l'ultimo valore vince (checkbox dopo il campo nascosto)
            else:
                nodo = nodo.setdefault(parte, {})

    def a_liste(n):
        if isinstance(n, dict):
            if n and all(k.lstrip("-").isdigit() for k in n):
                return [a_liste(n[k]) for k in sorted(n, key=int)]
            return {k: a_liste(v) for k, v in n.items()}
        return n
    return a_liste(radice)


def _bool(v) -> bool:
    return str(v).lower() in ("1", "true", "on", "si", "sì")


def _dati_da_form(nuovi: dict, vecchi: dict) -> dict:
    dati = modello_dati.dati_vuoti()
    for ruolo in ("venditori", "acquirenti"):
        lista = []
        for p in nuovi.get(ruolo, []) or []:
            if not isinstance(p, dict):
                continue
            persona = modello_dati.persona_vuota()
            persona.update({k: (v or "").strip() for k, v in p.items() if not k.startswith("_")})
            if persona.get("codice_fiscale"):
                persona["codice_fiscale"] = persona["codice_fiscale"].replace(" ", "").upper()
            # ripristina le annotazioni sulle fonti (non modificabili dal modulo)
            origine = p.get("_origine", "")
            if origine.isdigit() and int(origine) < len(vecchi.get(ruolo, [])):
                v = vecchi[ruolo][int(origine)]
                for k in ("_fonti", "_avvisi", "_residenza_atto"):
                    if k in v:
                        persona[k] = v[k]
            if any(str(persona.get(k, "")).strip() for k, _, _ in modello_dati.CAMPI_PERSONA if k not in ("doc_tipo", "sesso")):
                lista.append(persona)
        dati[ruolo] = lista

    imm = nuovi.get("immobile", {})
    for k in ("tipologia", "comune", "prov", "indirizzo", "descrizione", "n_planimetrie"):
        dati["immobile"][k] = (imm.get(k) or "").strip()
    dati["immobile"]["unita"] = [
        {k: (u.get(k) or "").strip() for k, _ in modello_dati.CAMPI_UNITA}
        for u in (imm.get("unita") or []) if isinstance(u, dict) and any((v or "").strip() for v in u.values())
    ]
    for k in dati["provenienza"]:
        dati["provenienza"][k] = (nuovi.get("provenienza", {}).get(k) or "").strip()

    acc = nuovi.get("accordi", {})
    a = dati["accordi"]
    for k in ("prezzo", "saldo_modalita", "mutuo_importo", "mutuo_entro", "data_rogito", "notaio_scelta",
              "stato_occupazione", "spese_condominiali_annue"):
        a[k] = (acc.get(k) or "").strip()
    a["mutuo_condizione"] = _bool(acc.get("mutuo_condizione"))
    a["versamenti"] = []
    for v in acc.get("versamenti") or []:
        if isinstance(v, dict) and ((v.get("importo") or "").strip() or (v.get("testo_libero") or "").strip()):
            ver = modello_dati.versamento_vuoto()
            ver.update({k: (x or "").strip() for k, x in v.items()})
            a["versamenti"].append(ver)
    a["clausole"] = [c.strip() for c in (acc.get("clausole") or []) if isinstance(c, str) and c.strip()]

    u = nuovi.get("urbanistica", {})
    dati["urbanistica"] = {
        "dichiarazione": (u.get("dichiarazione") or "").strip(),
        "ante_67": _bool(u.get("ante_67")),
        "conformita_catastale": _bool(u.get("conformita_catastale")),
        "agibilita_presente": _bool(u.get("agibilita_presente")),
        "agibilita": (u.get("agibilita") or "").strip(),
    }
    for k in dati["ape"]:
        dati["ape"][k] = (nuovi.get("ape", {}).get(k) or "").strip()
    for k in dati["firma"]:
        dati["firma"][k] = (nuovi.get("firma", {}).get(k) or "").strip()
    return dati


@app.post("/pratiche/{pid}/dati")
async def salva_dati(request: Request, pid: str):
    p = _pratica(pid)
    form = await request.form()
    elementi = list(form.multi_items())
    azione = form.get("_azione", "salva")
    stato = p.carica()
    stato["dati"] = _dati_da_form(_form_annidato(elementi), stato["dati"])
    stato["salvato"] = datetime.now().isoformat(timespec="seconds")
    p.salva(stato)
    if azione == "genera":
        return _genera(p, stato)
    return _vai(pid, "controlli", "Dati salvati")


def _genera(p: pratiche.Pratica, stato: dict):
    nome = f"Preliminare - {pratiche._nome_sicuro(stato.get('nome', p.id))}.docx"
    dest = p.cartella / nome
    try:
        ris = genera.genera(stato["dati"], pratiche.percorso_modello(), dest)
    except Exception as e:
        log.exception("Generazione fallita")
        return _vai(p.id, "genera", f"Errore nella generazione del Word: {e}")
    controlli = verifiche.controlla(stato, {c: len(p.file_categoria(c)) for c in pratiche.CATEGORIE})
    (p.cartella / "Controlli.txt").write_text(
        f"Controlli del {datetime.now():%d/%m/%Y %H:%M}\n\n" + verifiche.testo_riepilogo(controlli), encoding="utf-8")
    stato["generato"] = {"file": nome, "quando": datetime.now().isoformat(timespec="seconds"), **ris}
    p.salva(stato)
    msg = f"Preliminare generato ({ris.get('pagine') or '?'} pagine)"
    if ris["mancanti"]:
        msg += f": {ris['mancanti']} dati mancanti evidenziati in giallo nel Word"
    return _vai(p.id, "genera", msg)


@app.post("/pratiche/{pid}/genera")
def genera_word(pid: str):
    p = _pratica(pid)
    return _genera(p, p.carica())


@app.get("/pratiche/{pid}/scarica/{nome}")
def scarica(pid: str, nome: str):
    p = _pratica(pid)
    f = (p.cartella / nome).resolve()
    if f.parent != p.cartella.resolve() or not f.is_file() or f.suffix.lower() not in (".docx", ".txt"):
        raise HTTPException(404)
    return FileResponse(f, filename=f.name)


# ---------------------------------------------------------------- modello

@app.get("/modello")
def pagina_modello(request: Request, msg: str = ""):
    m = pratiche.percorso_modello()
    archivio = sorted((pratiche.CARTELLA_MODELLO / "archivio").glob("*.docx"), reverse=True) \
        if (pratiche.CARTELLA_MODELLO / "archivio").exists() else []
    guida = (BASE.parent / "docs" / "GUIDA_MODELLO.md")
    return templates.TemplateResponse(request, "modello.html", {
        "modello": m, "modificato": datetime.fromtimestamp(m.stat().st_mtime), "archivio": archivio[:10],
        "guida": guida.read_text(encoding="utf-8") if guida.exists() else "", "msg": msg})


@app.get("/modello/scarica")
def scarica_modello():
    return FileResponse(pratiche.percorso_modello(), filename="preliminare_modello.docx")


@app.post("/modello")
async def carica_modello(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        return RedirectResponse("/modello?msg=Il modello deve essere un file .docx (in Word: Salva con nome, Documento Word)", 303)
    contenuto = await file.read()
    # prova di compilazione con dati vuoti prima di sostituire il modello in uso
    with tempfile.TemporaryDirectory() as tmp:
        prova = Path(tmp) / "modello.docx"
        prova.write_bytes(contenuto)
        try:
            genera._render(prova, genera.contesto(modello_dati.dati_vuoti()), Path(tmp) / "out.docx")
        except Exception as e:
            return RedirectResponse(f"/modello?msg=Modello non valido, non è stato sostituito. Errore: {str(e)[:150]}", 303)
    attuale = pratiche.percorso_modello()
    archivio = pratiche.CARTELLA_MODELLO / "archivio"
    archivio.mkdir(exist_ok=True)
    shutil.copy(attuale, archivio / f"preliminare_modello_{datetime.now():%Y%m%d-%H%M%S}.docx")
    attuale.write_bytes(contenuto)
    return RedirectResponse("/modello?msg=Modello aggiornato. La versione precedente è stata archiviata.", 303)


@app.get("/salute")
def salute():
    return Response("ok", media_type="text/plain")
