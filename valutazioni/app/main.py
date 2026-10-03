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

from . import archivio, genera, planimetria, ricerca_omi, superfici

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
    url, _, ancora = url.partition("#")
    if msg:
        url += "?msg=" + re.sub(r"[^\w\s.,:'()àèéìòù\[\]-]", "", msg)[:300]
    return RedirectResponse(url + (f"#{ancora}" if ancora else ""), status_code=303)


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
        stato["generazione"]["stato"] = "in corso su un altro PC, oppure interrotta: aggiorna la pagina tra poco o rigenera"
    return templates.TemplateResponse(request, "valutazione.html", {
        "v": v, "stato": stato, "file_cat": file_cat, "par": par, "msg": msg,
        "in_corso": genera.in_corso(v),
        "documenti": v.documenti(), "imp": archivio.impostazioni(),
        "pl": stato.get("planimetria"), "SCALE": list(planimetria.SCALE),
        "omi_stato": stato.get("omi", {}), "omi_in_corso": ricerca_omi.in_corso(v),
        "omi_valori": _valori_per_pagina(v),
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


def _salva_parametri(v, provincia: str, comune: str, zona: str) -> None:
    stato = v.carica()
    stato["provincia"], stato["comune"], stato["zona"] = provincia.strip(), comune.strip(), zona.strip()
    v.salva(stato)


def _par_omi(v):
    from . import excel
    fogli = v.file_categoria("excel")
    d = None
    if fogli:
        try:
            d = excel.leggi(max(fogli, key=lambda p: p.stat().st_mtime))
        except Exception:  # noqa: BLE001 - senza Excel valgono i dati scritti nella pagina
            d = None
    return genera.parametri_omi(v, d)


@app.post("/valutazioni/{vid}/parametri")
def parametri(vid: str, provincia: str = Form(""), comune: str = Form(""), zona: str = Form(""),
              azione: str = Form("salva")):
    v = _val(vid)
    _salva_parametri(v, provincia, comune, zona)
    if azione == "salva":
        return _vai(f"/valutazioni/{vid}#omi", "Dati per la ricerca OMI salvati")
    par = _par_omi(v)
    if not par["comune"] or not par["provincia"]:
        return _vai(f"/valutazioni/{vid}#omi", "Scrivi il comune (e la provincia se non la trova da sola)")
    if azione == "zone":
        ok = ricerca_omi.avvia_zone(v, par["provincia"], par["comune"])
    else:
        if not par["zona"]:
            return _vai(f"/valutazioni/{vid}#omi", "Scegli o scrivi prima la zona OMI")
        ok = ricerca_omi.avvia_valori(v, par["provincia"], par["comune"], par["zona"])
    return _vai(f"/valutazioni/{vid}#omi", "Ricerca OMI avviata: la pagina si aggiorna da sola" if ok
                else "C'è già una ricerca OMI in corso per questa valutazione")


def _valori_per_pagina(v) -> dict | None:
    dati = ricerca_omi.valori(v)
    if not dati or not dati.get("dalla_pagina"):
        return None
    for t in dati["tabelle"]:
        t["righe_dati"] = ricerca_omi.righe_dati(t)
        t["intest"] = ricerca_omi.righe_dati({**t, "intestazione": 0, "righe": t["intestazione"]}, ripeti=False)
    return dati


@app.post("/valutazioni/{vid}/omi/scelta")
async def omi_scelta(request: Request, vid: str):
    v = _val(vid)
    form = await request.form()
    ricerca_omi.salva_scelta(v, dict(form))
    return _vai(f"/valutazioni/{vid}#omi", "Scelta dei valori OMI salvata: verrà usata nel Word")


@app.post("/valutazioni/{vid}/omi/scarta")
def omi_scarta(vid: str):
    v = _val(vid)
    ricerca_omi.file_valori(v).unlink(missing_ok=True)
    return _vai(f"/valutazioni/{vid}#omi", "Valori OMI tolti: la creazione del Word rifarà la ricerca")


@app.post("/valutazioni/{vid}/genera")
def avvia_generazione(vid: str, omi: str = Form("si")):
    v = _val(vid)
    if not v.file_categoria("excel"):
        return _vai(f"/valutazioni/{vid}", "Carica prima il file Excel della stima")
    genera.avvia(v, cerca_omi=omi == "si")
    return _vai(f"/valutazioni/{vid}")


# ---------------------------------------------------------------- planimetria

@app.post("/valutazioni/{vid}/planimetria/calcola")
def planimetria_calcola(vid: str, porta_max: str = Form("1,1")):
    v = _val(vid)
    files = v.file_categoria("planimetria")
    if not files:
        return _vai(f"/valutazioni/{vid}", "Carica prima la planimetria")
    try:
        apertura = min(max(float(porta_max.replace(",", ".")), 0.6), 2.0)
    except ValueError:
        apertura = 1.1
    try:
        superfici.calcola(v, max(files, key=lambda p: p.stat().st_mtime), apertura)
    except Exception as e:  # noqa: BLE001 - errore mostrato nella pagina
        logging.getLogger("valutazioni").exception("Planimetria")
        return _vai(f"/valutazioni/{vid}", f"Planimetria non leggibile: {e}")
    if v.carica().get("planimetria", {}).get("letture"):
        return _vai(f"/valutazioni/{vid}", "Sulla planimetria ci sono le superfici scritte: controllale e salva")
    return _vai(f"/valutazioni/{vid}", "Zone trovate: spunta le stanze dell'immobile, dai loro un nome e salva")


@app.post("/valutazioni/{vid}/planimetria/salva")
async def planimetria_salva(request: Request, vid: str):
    v = _val(vid)
    form = await request.form()
    scelti = [int(k.split("_", 1)[1]) for k in form if k.startswith("scegli_")]
    nomi = {k.split("_", 1)[1]: str(val) for k, val in form.items() if k.startswith("nome_")}
    scala = str(form.get("scala", "automatica"))
    if scala != "automatica" and scala not in planimetria.SCALE and scala not in (planimetria.BARRA,
                                                                                  superfici.RIFERIMENTO):
        scala = "automatica"
    letture = {}
    for k, val in form.items():
        if k.startswith("lmq_"):
            sigla = k[4:]
            try:
                mq = round(float(str(val).replace(".", "").replace(",", ".")) if "," in str(val)
                           else float(str(val)), 2)
            except ValueError:
                mq = None
            letture[sigla] = {"scelta": f"lscegli_{sigla}" in form, "nome": str(form.get(f"lnome_{sigla}", "")), "mq": mq}
    manuali = {k[7:]: {"scelta": f"mscegli_{k[7:]}" in form, "nome": str(val)}
               for k, val in form.items() if k.startswith("mnome_")}
    superfici.aggiorna(v, scelti, nomi, scala, letture, manuali)
    return _vai(f"/valutazioni/{vid}", "Superfici aggiornate")


def _punti(testo: str, vista: float) -> list[list[float]]:
    """"x,y;x,y;..." in pixel della pagina.png -> pixel del file della planimetria."""
    punti = []
    for coppia in testo.split(";"):
        if coppia.strip():
            x, y = (float(c) for c in coppia.split(","))
            punti.append([x / vista, y / vista])
    return punti


def _metri(testo: str) -> float:
    t = testo.strip().lower().replace("m", "").strip()
    return float(t.replace(".", "").replace(",", ".") if "," in t else t)


@app.post("/valutazioni/{vid}/planimetria/riferimento")
def planimetria_riferimento(vid: str, punti: str = Form(...), metri: str = Form(...)):
    v = _val(vid)
    p = v.carica().get("planimetria") or {}
    try:
        pts, m = _punti(punti, p.get("vista", 1.0)), _metri(metri)
    except ValueError:
        return _vai(f"/valutazioni/{vid}", "Misura di riferimento non valida")
    if len(pts) != 2 or m <= 0:
        return _vai(f"/valutazioni/{vid}", "Per la scala servono due punti e la distanza in metri")
    superfici.imposta_riferimento(v, pts, m)
    return _vai(f"/valutazioni/{vid}#misura", "Scala impostata: ora puoi ricalcolare le zone o disegnare le stanze")


@app.post("/valutazioni/{vid}/planimetria/stanza")
def planimetria_stanza(vid: str, punti: str = Form(...), nome: str = Form("")):
    v = _val(vid)
    p = v.carica().get("planimetria") or {}
    try:
        pts = _punti(punti, p.get("vista", 1.0))
    except ValueError:
        pts = []
    if len(pts) < 3:
        return _vai(f"/valutazioni/{vid}#misura", "Per una stanza servono almeno tre angoli")
    superfici.aggiungi_stanza(v, pts, nome)
    return _vai(f"/valutazioni/{vid}#misura", "Stanza aggiunta")


@app.post("/valutazioni/{vid}/planimetria/stanza/{sigla}/togli")
def planimetria_togli_stanza(vid: str, sigla: str):
    superfici.togli_stanza(_val(vid), sigla)
    return _vai(f"/valutazioni/{vid}#misura", "Stanza tolta")


@app.get("/valutazioni/{vid}/planimetria/{quale}.png")
def planimetria_immagine(vid: str, quale: str):
    v = _val(vid)
    p = {"zone": superfici.cartella_lavoro(v) / "zone.png", "pagina": superfici.cartella_lavoro(v) / "pagina.png",
         "superfici": v.cartella / "Superfici - planimetria.png"}.get(quale)
    if not p or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "no-store"})


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
def salva_impostazioni(provincia: str = Form(""), comune: str = Form(""), destinazioni: str = Form(""),
                       maggiorazione: str = Form("15")):
    archivio.salva_impostazioni({"provincia": provincia.strip(), "comune": comune.strip(),
                                 "destinazioni": destinazioni.strip(),
                                 "maggiorazione": maggiorazione.strip().replace(",", ".") or "15"})
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
