"""Report consulenti: andamento settimanale, benchmark e report mensile dai report personali.

Programma dell'agenzia come "Preliminari", "Valutazioni" e "Sintesi". I dati (report dei
collaboratori, benchmark, file prodotti) stanno nella cartella indicata da CONSULENTI_DATI.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import archivio, config, report_mensile, settimanale

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("consulenti")

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Report consulenti", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "web" / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "web" / "templates")


@app.get("/")
def home(request: Request):
    anno, mese = _mese_corrente()
    salvati = archivio.elenco()
    return templates.TemplateResponse(request, "index.html", {
        "report": salvati, "anno": anno, "mese": mese,
        "descrizione": report_mensile.descrizione_mese(anno, mese),
        "benchmark": settimanale.percorso_benchmark(anno, mese).exists(),
        "risultati": config.risultati_recenti(), "dati": config.DATI})


# ---------------------------------------------------------------- report mensile della filiale

MAX_REPORT = 20 * 1024 * 1024


def _mese_predefinito() -> tuple[int, int]:
    """Il mese appena chiuso: a novembre si compila il report di ottobre."""
    oggi = datetime.now()
    return (oggi.year, oggi.month - 1) if oggi.month > 1 else (oggi.year - 1, 12)


def _pagina_report(request: Request, **extra):
    anno, mese = _mese_predefinito()
    return templates.TemplateResponse(request, "report.html", {
        "mesi": report_mensile.MESI, "anno": anno, "mese": mese, **extra})


@app.get("/report")
def pagina_report(request: Request):
    return _pagina_report(request)


@app.post("/report")
async def elabora_report(request: Request, mensile: UploadFile = File(...),
                         personali: list[UploadFile] = File(default=[]),
                         anno: int = Form(...), mese: int = Form(...)):
    def errore(testo: str):
        return _pagina_report(request, errore=testo, anno_scelto=anno, mese_scelto=mese)

    if not 1 <= mese <= 12 or not 2000 <= anno <= 2100:
        return errore("Mese o anno non validi")
    file_personali = []
    for f in personali:
        if not f.filename:
            continue
        if not f.filename.lower().endswith((".xlsx", ".xlsm")):
            return errore(f"{f.filename}: i report devono essere file Excel .xlsx")
        dati = await f.read()
        if len(dati) > MAX_REPORT:
            return errore(f"{f.filename}: file troppo grande")
        file_personali.append((f.filename, dati))
    if not file_personali:  # nessun file scelto: si usano i report salvati nella cartella
        try:
            file_personali = archivio.file_per_elaborare()
        except report_mensile.ErroreReport as e:
            return errore(str(e))
    dati_mensile = await mensile.read()
    if not mensile.filename or not mensile.filename.lower().endswith((".xlsx", ".xlsm")) or len(dati_mensile) > MAX_REPORT:
        return errore("Il report mensile deve essere un file Excel .xlsx")
    try:
        ris = report_mensile.elabora(dati_mensile, mensile.filename, file_personali, anno, mese)
    except report_mensile.ErroreReport as e:
        return errore(str(e))
    except Exception as e:
        log.exception("Errore nell'elaborazione dei report")
        return errore(f"Errore imprevisto nella lettura dei file: {str(e)[:200]}")

    return _pagina_report(request, risultato=ris, scarica="/risultati/" + config.salva_risultato(ris.contenuto, ris.nome_file),
                          anno_scelto=anno, mese_scelto=mese,
                          descrizione=report_mensile.descrizione_mese(anno, mese))


async def _leggi_excel(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    letti = []
    for f in files:
        if not f.filename:
            continue
        if not f.filename.lower().endswith((".xlsx", ".xlsm")):
            raise report_mensile.ErroreReport(f"{f.filename}: i report devono essere file Excel .xlsx")
        dati = await f.read()
        if len(dati) > MAX_REPORT:
            raise report_mensile.ErroreReport(f"{f.filename}: file troppo grande")
        letti.append((f.filename, dati))
    return letti


# ---------------------------------------------------------------- benchmark e andamento settimanale

def _mese_corrente() -> tuple[int, int]:
    oggi = datetime.now()
    return oggi.year, oggi.month


def _pagina_benchmark(request: Request, **extra):
    anno, mese = _mese_corrente()
    return templates.TemplateResponse(request, "benchmark.html", {
        "mesi": report_mensile.MESI, "anno": anno, "mese": mese,
        "salvati": settimanale.benchmark_salvati(),
        "cartella": settimanale.CARTELLA_BENCHMARK,
        "indicatori": settimanale.INDICATORI, **extra})


@app.get("/benchmark")
def pagina_benchmark(request: Request, msg: str = "", vedi: str = ""):
    extra = {"msg": msg}
    if m := re.fullmatch(r"(\d{4})-(\d{2})", vedi):
        try:
            bm = settimanale.carica_benchmark(int(m.group(1)), int(m.group(2)))
            if bm:
                extra.update(anteprima=bm, anteprima_mese=report_mensile.descrizione_mese(int(m.group(1)), int(m.group(2))))
        except report_mensile.ErroreReport as e:
            extra["errore"] = str(e)
    return _pagina_benchmark(request, **extra)


@app.post("/benchmark")
async def carica_benchmark(request: Request, file: UploadFile = File(...), anno: int = Form(...), mese: int = Form(...)):
    if not 1 <= mese <= 12 or not 2000 <= anno <= 2100:
        return _pagina_benchmark(request, errore="Mese o anno non validi")
    try:
        letti = await _leggi_excel([file])
        if not letti:
            raise report_mensile.ErroreReport("Scegli il file dei benchmark")
        settimanale.salva_benchmark(letti[0][1], anno, mese)
    except report_mensile.ErroreReport as e:
        return _pagina_benchmark(request, errore=str(e))
    desc = report_mensile.descrizione_mese(anno, mese)
    return RedirectResponse(f"/benchmark?vedi={anno}-{mese:02d}&msg=Benchmark di {desc} salvato", 303)


@app.get("/benchmark/modello")
def modello_benchmark(anno: int, mese: int):
    if not 1 <= mese <= 12:
        raise HTTPException(400)
    contenuto = settimanale.modello_benchmark(anno, mese)
    nome = f"Benchmark {report_mensile.nome_foglio(anno, mese)}.xlsx"
    return Response(contenuto, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.get("/benchmark/file/{nome}")
def scarica_benchmark(nome: str):
    if not re.fullmatch(r"\d{4}-\d{2}\.xlsx", nome) or not (f := settimanale.CARTELLA_BENCHMARK / nome).is_file():
        raise HTTPException(404)
    return FileResponse(f, filename=f"Benchmark {nome}")


def _pagina_settimanale(request: Request, **extra):
    anno, mese = _mese_corrente()
    salvati = {(b["anno"], b["mese"]) for b in settimanale.benchmark_salvati()}
    return templates.TemplateResponse(request, "settimanale.html", {
        "mesi": report_mensile.MESI, "anno": anno, "mese": mese,
        "benchmark_presenti": sorted(salvati, reverse=True)[:12],
        "descrizione_mese": report_mensile.descrizione_mese, **extra})


@app.get("/settimanale")
def pagina_settimanale(request: Request):
    return _pagina_settimanale(request)


@app.post("/settimanale")
async def elabora_settimanale(request: Request, personali: list[UploadFile] = File(default=[]),
                              anno: int = Form(...), mese: int = Form(...)):
    def errore(testo: str):
        return _pagina_settimanale(request, errore=testo, anno_scelto=anno, mese_scelto=mese)

    if not 1 <= mese <= 12 or not 2000 <= anno <= 2100:
        return errore("Mese o anno non validi")
    try:
        file_personali = await _leggi_excel(personali) or archivio.file_per_elaborare()
        bm = settimanale.carica_benchmark(anno, mese)
        ris = settimanale.elabora(file_personali, anno, mese, bm)
    except report_mensile.ErroreReport as e:
        return errore(str(e))
    except Exception as e:
        log.exception("Errore nell'andamento settimanale")
        return errore(f"Errore imprevisto nella lettura dei file: {str(e)[:200]}")
    return _pagina_settimanale(request, risultato=ris, scarica="/risultati/" + config.salva_risultato(ris.contenuto, ris.nome_file),
                               anno_scelto=anno, mese_scelto=mese,
                               descrizione=report_mensile.descrizione_mese(anno, mese))


# ---------------------------------------------------------------- cartella dei report collaboratori

@app.get("/collaboratori")
def pagina_collaboratori(request: Request, msg: str = ""):
    anno, mese = _mese_corrente()
    return templates.TemplateResponse(request, "collaboratori.html", {
        "report": archivio.elenco(), "cartella": archivio.CARTELLA, "msg": msg,
        "mesi": report_mensile.MESI, "anno": anno, "mese": mese,
        "benchmark": settimanale.percorso_benchmark(anno, mese).exists()})


@app.post("/collaboratori")
async def carica_collaboratori(request: Request, files: list[UploadFile] = File(...)):
    salvati, errori = [], []
    try:
        letti = await _leggi_excel(files)
    except report_mensile.ErroreReport as e:
        letti, errori = [], [str(e)]
    for nome, dati in letti:
        try:
            salvati.append(archivio.salva(nome, dati).consulente)
        except report_mensile.ErroreReport as e:
            errori.append(str(e))
    msg = ("Salvati i report di " + ", ".join(salvati) + "." if salvati else "") + \
          (" Non salvati: " + " ".join(errori) if errori else "")
    return RedirectResponse("/collaboratori?msg=" + re.sub(r"[^\w\s.,:'()àèéìòù-]", "", msg)[:400], status_code=303)


@app.get("/collaboratori/file/{nome}")
def scarica_collaboratore(nome: str):
    if (f := archivio.percorso(nome)) is None:
        raise HTTPException(404)
    return FileResponse(f, filename=f.name)


@app.post("/collaboratori/togli/{nome}")
def togli_collaboratore(nome: str):
    ok = archivio.elimina(nome)
    return RedirectResponse("/collaboratori?msg=" + ("Report spostato in archivio" if ok else "File non trovato"), 303)


@app.get("/risultati/{nome}")
def scarica_risultato(nome: str):
    f = (config.cartella_risultati() / nome).resolve()
    if f.parent != config.cartella_risultati().resolve() or not f.is_file() or f.suffix.lower() != ".xlsx":
        raise HTTPException(404)
    return FileResponse(f, filename=f.name)


@app.get("/salute")
def salute():
    return Response("ok", media_type="text/plain")
