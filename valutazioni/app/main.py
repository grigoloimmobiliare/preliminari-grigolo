"""Applicazione web interna per la compilazione automatica delle valutazioni immobiliari."""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from docx import Document
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import archivio, genera

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Valutazioni Grigolo", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "web" / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "web" / "templates")
templates.env.globals["CATEGORIE"] = archivio.CATEGORIE

MAX_FILE = 60 * 1024 * 1024
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _val(vid: str) -> archivio.Valutazione:
    try:
        return archivio.apri(vid)
    except FileNotFoundError:
        raise HTTPException(404, "Valutazione non trovata")


def _vai(url: str, msg: str = "") -> RedirectResponse:
    if msg:
        url += "?msg=" + re.sub(r"[^\w\s.,:'()àèéìòù\[\]-]", "", msg)[:300]
    return RedirectResponse(url, status_code=303)


@app.get("/salute")
def salute():
    return {"ok": True}


# ---------------------------------------------------------------- elenco

@app.get("/")
def home(request: Request, msg: str = ""):
    return templates.TemplateResponse(request, "index.html", {"valutazioni": archivio.elenco(), "msg": msg})


@app.post("/valutazioni")
def nuova(nome: str = Form(...)):
    v = archivio.crea(nome)
    return _vai(f"/valutazioni/{v.id}")


@app.post("/valutazioni/{vid}/elimina")
def elimina(vid: str, conferma: str = Form("")):
    v = _val(vid)
    if conferma.strip().lower() != "elimina":
        return _vai(f"/valutazioni/{vid}", "Per eliminare scrivi ELIMINA nella casella di conferma")
    cestino = archivio.DATI / "cestino"
    cestino.mkdir(parents=True, exist_ok=True)
    shutil.move(str(v.cartella), str(cestino / f"{v.id} - {datetime.now():%Y%m%d-%H%M%S}"))
    return _vai("/", "Valutazione spostata nel cestino")


# ---------------------------------------------------------------- valutazione

@app.get("/valutazioni/{vid}")
def pagina(request: Request, vid: str, msg: str = ""):
    v = _val(vid)
    stato = v.carica()
    file_cat = {c: v.file_categoria(c) for c in archivio.CATEGORIE}
    dati_excel = None
    if file_cat["excel"]:
        try:
            from . import excel
            dati_excel = excel.leggi(max(file_cat["excel"], key=lambda p: p.stat().st_mtime))
        except Exception as e:  # noqa: BLE001
            msg = msg or f"Excel non leggibile: {e}"
    par = genera.parametri_omi(v, dati_excel)
    if stato["generazione"].get("stato") == "in corso" and not genera.in_corso(v):
        stato["generazione"]["stato"] = "interrotta (programma riavviato): rigenera"
    return templates.TemplateResponse(request, "valutazione.html", {
        "v": v, "stato": stato, "file_cat": file_cat, "par": par, "msg": msg,
        "in_corso": genera.in_corso(v),
        "documenti": v.documenti(), "imp": archivio.impostazioni(),
    })


@app.post("/valutazioni/{vid}/carica/{cat}")
async def carica(vid: str, cat: str, files: list[UploadFile] = File(...)):
    v = _val(vid)
    if cat not in archivio.CATEGORIE:
        raise HTTPException(400, "Categoria non valida")
    scartati = []
    for f in files:
        if not f.filename:
            continue
        dati = await f.read()
        if Path(f.filename).suffix.lower() not in archivio.CATEGORIE[cat][2] or len(dati) > MAX_FILE:
            scartati.append(f.filename)
            continue
        v.aggiungi_file(cat, f.filename, dati)
    return _vai(f"/valutazioni/{vid}", f"File non accettati: {', '.join(scartati)}" if scartati else "")


@app.post("/valutazioni/{vid}/togli/{cat}/{nome}")
def togli(vid: str, cat: str, nome: str):
    v = _val(vid)
    try:
        v.file(cat, nome).unlink()
    except FileNotFoundError:
        raise HTTPException(404, "File non trovato")
    return _vai(f"/valutazioni/{vid}")


@app.get("/valutazioni/{vid}/file/{cat}/{nome}")
def mostra_file(vid: str, cat: str, nome: str):
    v = _val(vid)
    try:
        return FileResponse(v.file(cat, nome))
    except FileNotFoundError:
        raise HTTPException(404, "File non trovato")


@app.post("/valutazioni/{vid}/parametri")
def parametri(vid: str, provincia: str = Form(""), comune: str = Form("")):
    v = _val(vid)
    stato = v.carica()
    stato["provincia"], stato["comune"] = provincia.strip(), comune.strip()
    v.salva(stato)
    return _vai(f"/valutazioni/{vid}", "Dati per la ricerca OMI salvati")


@app.post("/valutazioni/{vid}/genera")
def avvia_generazione(vid: str, omi: str = Form("si")):
    v = _val(vid)
    if not v.file_categoria("excel"):
        return _vai(f"/valutazioni/{vid}", "Carica prima il file Excel della stima")
    genera.avvia(v, cerca_omi=omi == "si")
    return _vai(f"/valutazioni/{vid}")


@app.get("/valutazioni/{vid}/scarica/{nome}")
def scarica(vid: str, nome: str):
    v = _val(vid)
    try:
        p = v.documento(nome)
    except FileNotFoundError:
        raise HTTPException(404, "File non trovato")
    return FileResponse(p, filename=p.name, media_type=DOCX if p.suffix == ".docx" else None)


# ---------------------------------------------------------------- impostazioni

@app.get("/impostazioni")
def pagina_impostazioni(request: Request, msg: str = ""):
    modello = archivio.file_modello("valutazione_modello.docx")
    return templates.TemplateResponse(request, "impostazioni.html", {
        "msg": msg, "imp": archivio.impostazioni(), "carta": archivio.carta_intestata(),
        "logo": archivio.logo_agenzia(),
        "modello": modello, "modello_data": datetime.fromtimestamp(modello.stat().st_mtime),
        "cartella": archivio.DATI,
    })


@app.post("/impostazioni")
def salva_impostazioni(provincia: str = Form(""), comune: str = Form(""), destinazioni: str = Form("")):
    archivio.salva_impostazioni({"provincia": provincia.strip(), "comune": comune.strip(),
                                 "destinazioni": destinazioni.strip()})
    return _vai("/impostazioni", "Impostazioni salvate")


@app.post("/impostazioni/modello")
async def carica_modello(file: UploadFile = File(...)):
    dati = await file.read()
    if not file.filename.lower().endswith(".docx"):
        return _vai("/impostazioni", "Il modello deve essere un file .docx (in Word: Salva con nome, Documento di Word)")
    tmp = archivio.CARTELLA_MODELLO / "~modello_nuovo.docx"
    tmp.write_bytes(dati)
    try:
        Document(str(tmp))
    except Exception:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return _vai("/impostazioni", "Il file caricato non è un documento Word valido")
    attuale = archivio.file_modello("valutazione_modello.docx")
    shutil.copy(attuale, archivio.CARTELLA_MODELLO / f"valutazione_modello - fino al {datetime.now():%Y-%m-%d %H%M}.docx")
    tmp.replace(attuale)
    return _vai("/impostazioni", "Nuovo modello Word salvato (il precedente è stato conservato nella stessa cartella)")


@app.post("/impostazioni/carta")
async def carica_carta(file: UploadFile = File(...)):
    dati = await file.read()
    if not file.filename.lower().endswith(".pdf"):
        return _vai("/impostazioni", "La carta intestata deve essere un PDF")
    archivio.CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)
    (archivio.CARTELLA_MODELLO / "carta_intestata.pdf").write_bytes(dati)
    return _vai("/impostazioni", "Carta intestata salvata")


@app.post("/impostazioni/logo")
async def carica_logo(file: UploadFile = File(...)):
    dati = await file.read()
    est = Path(file.filename or "").suffix.lower()
    if est not in (".png", ".jpg", ".jpeg"):
        return _vai("/impostazioni", "Il logo deve essere un'immagine PNG o JPG")
    archivio.CARTELLA_MODELLO.mkdir(parents=True, exist_ok=True)
    for vecchio in ("logo_agenzia_entrate.png", "logo_agenzia_entrate.jpg"):
        (archivio.CARTELLA_MODELLO / vecchio).unlink(missing_ok=True)
    nome = "logo_agenzia_entrate.png" if est == ".png" else "logo_agenzia_entrate.jpg"
    (archivio.CARTELLA_MODELLO / nome).write_bytes(dati)
    return _vai("/impostazioni", "Logo dell'Agenzia delle Entrate salvato")


@app.get("/impostazioni/logo")
def mostra_logo():
    p = archivio.logo_agenzia()
    if not p:
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/impostazioni/scarica/{nome}")
def scarica_modello(nome: str):
    if nome not in ("valutazione_modello.docx", "stima_modello.xlsx", "carta_intestata.pdf"):
        raise HTTPException(404)
    p = archivio.file_modello(nome)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name)


@app.get("/guida")
def guida(request: Request):
    return templates.TemplateResponse(request, "guida.html", {})
