"""Avvio del server su Windows (usato dall'attivita' pianificata creata da installa.ps1).

Legge C:\\PreliminariGrigolo\\impostazioni.json (due cartelle sopra questo file)
e scrive il log in C:\\PreliminariGrigolo\\log\\server.log.
"""

import json
import os
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
PROGRAMMA = QUI.parent
RADICE = PROGRAMMA.parent

cartella_log = RADICE / "log"
cartella_log.mkdir(exist_ok=True)
file_log = cartella_log / "server.log"
if file_log.exists() and file_log.stat().st_size > 5 * 1024 * 1024:
    file_log.replace(cartella_log / "server.old.log")
# con pythonw.exe non c'e' console: tutto l'output va nel file di log
sys.stdout = sys.stderr = open(file_log, "a", encoding="utf-8", buffering=1)

impostazioni = json.loads((RADICE / "impostazioni.json").read_text(encoding="utf-8-sig"))
os.environ["PRELIMINARI_DATI"] = impostazioni["cartella_dati"]
if impostazioni.get("tesseract"):
    os.environ["TESSERACT_CMD"] = impostazioni["tesseract"]
if impostazioni.get("soffice"):
    os.environ["SOFFICE_CMD"] = impostazioni["soffice"]

os.chdir(PROGRAMMA)
sys.path.insert(0, str(PROGRAMMA))

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="0.0.0.0", port=int(impostazioni.get("porta", 8080)))
