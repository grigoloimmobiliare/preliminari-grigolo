"""Sintesi immobili: applicazione web interna che analizza atto di provenienza e visure
catastali e crea un PDF di sintesi, salvato nella cartella condivisa."""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import archivio, pdf, servizio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sintesi")

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Sintesi immobili", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "web" / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "web" / "templates")
templates.env.globals.update(CATEGORIE=archivio.CATEGORIE, AGENZIA=pdf.AGENZIA)

MAX_FILE = 60 * 1024 * 1024


@app.on_event("startup")
def _avvio():
    # PDF copiati direttamente nella cartella condivisa: sintesi automatica
    if os.environ.get("SINTESI_SORVEGLIANZA", "1") != "0":
        servizio.avvia_sorveglianza()


def _sintesi(sid: str) -> archivio.Sintesi:
    try:
        return archivio.apri(sid)
    except FileNotFoundError:
        raise HTTPException(404, "Immobile non trovato")


def _vai(sid: str, msg: str = "", ancora: str = "") -> RedirectResponse:
    url = f"/immobili/{sid}"
    if msg:
        url += "?msg=" + re.sub(r"[^\w\s.,:'()àèéìòù/-]", "", msg)[:250]
    if ancora:
        url += "#" + ancora
    return RedirectResponse(url, status_code=303)


@app.get("/")
def home(request: Request, msg: str = ""):
    return templates.TemplateResponse(request, "index.html", {"elenco": archivio.elenco(), "msg": msg,
                                                              "cartella": str(archivio.DATI)})


@app.post("/immobili")
def nuovo(nome: str = Form(...)):
    s = archivio.crea(nome)
    return _vai(s.id)


@app.get("/immobili/{sid}")
def pagina(request: Request, sid: str, msg: str = ""):
    s = _sintesi(sid)
    stato = s.carica()
    file_cat = {c: s.file_categoria(c) for c in archivio.CATEGORIE}
    pdf_file = s.pdf()
    return templates.TemplateResponse(request, "immobile.html", {
        "s": s, "stato": stato, "ris": stato.get("risultato"), "file_cat": file_cat, "msg": msg,
        "pdf": pdf_file.name if pdf_file else "",
    })


@app.post("/immobili/{sid}/carica/{cat}")
async def carica(sid: str, cat: str, files: list[UploadFile] = File(...)):
    s = _sintesi(sid)
    if cat not in archivio.CATEGORIE:
        raise HTTPException(400, "Categoria non valida")
    caricati, scartati = 0, []
    for f in files:
        if not f.filename:
            continue
        if Path(f.filename).suffix.lower() not in archivio.ESTENSIONI:
            scartati.append(f.filename)
            continue
        contenuto = await f.read()
        if len(contenuto) > MAX_FILE:
            scartati.append(f.filename)
            continue
        s.aggiungi_file(cat, f.filename, contenuto)
        caricati += 1
    msg = f"Caricati {caricati} file"
    if scartati:
        msg += f". Scartati (solo PDF, max 60 MB): {', '.join(scartati)}"
    return _vai(sid, msg, "documenti")


@app.post("/immobili/{sid}/rimuovi/{cat}/{nome}")
def rimuovi(sid: str, cat: str, nome: str):
    s = _sintesi(sid)
    try:
        f = s.file(cat, nome)
    except (FileNotFoundError, KeyError):
        raise HTTPException(404)
    cestino = s.cartella / ".rimossi"
    cestino.mkdir(exist_ok=True)
    shutil.move(str(f), str(cestino / f"{datetime.now():%Y%m%d-%H%M%S} {f.name}"))
    return _vai(sid, f"Rimosso {nome}", "documenti")


@app.get("/immobili/{sid}/file/{cat}/{nome}")
def file_originale(sid: str, cat: str, nome: str):
    s = _sintesi(sid)
    try:
        return FileResponse(s.file(cat, nome), media_type="application/pdf")
    except (FileNotFoundError, KeyError):
        raise HTTPException(404)


@app.post("/immobili/{sid}/analizza")
def analizza(sid: str):
    s = _sintesi(sid)
    servizio.smista(s)
    try:
        stato = servizio.crea_sintesi(s)
    except ValueError as e:
        return _vai(sid, str(e), "documenti")
    except Exception as e:
        log.exception("Creazione della sintesi fallita")
        return _vai(sid, f"Errore durante l'analisi: {e}")
    ris = stato["risultato"]
    gravi = sum(1 for a in ris["avvisi"] if a["livello"] == "errore")
    msg = "Sintesi creata"
    if gravi:
        msg += f": {gravi} punti importanti da verificare"
    return _vai(sid, msg, "risultato")


@app.get("/immobili/{sid}/pdf/{nome}")
def scarica_pdf(sid: str, nome: str, scarica: int = 0):
    s = _sintesi(sid)
    f = (s.cartella / nome).resolve()
    if f.parent != s.cartella.resolve() or not f.is_file() or f.suffix.lower() != ".pdf":
        raise HTTPException(404)
    if scarica:
        return FileResponse(f, filename=f.name, media_type="application/pdf")
    return FileResponse(f, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.post("/immobili/{sid}/elimina")
def elimina(sid: str, conferma: str = Form("")):
    s = _sintesi(sid)
    if conferma.strip().lower() != "elimina":
        return _vai(sid, "Per eliminare scrivi ELIMINA nella casella di conferma")
    cestino = archivio.DATI / "cestino"
    cestino.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s.cartella), str(cestino / f"{s.id} - {datetime.now():%Y%m%d-%H%M%S}"))
    return RedirectResponse("/?msg=Immobile spostato nel cestino", status_code=303)


@app.get("/salute")
def salute():
    return Response("ok", media_type="text/plain")
