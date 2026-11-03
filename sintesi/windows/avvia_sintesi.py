"""Avvio di "Sintesi immobili" su Windows (usato dall'attivita' pianificata creata da installa.ps1).

Legge C:\\SintesiGrigolo\\impostazioni.json e scrive il log in C:\\SintesiGrigolo\\log\\server.log.
Il programma e' copiato in C:\\SintesiGrigolo\\programma (questo file e' in programma\\sintesi\\windows).
"""

import json
import os
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
PROGRAMMA = QUI.parent.parent
RADICE = PROGRAMMA.parent

cartella_log = RADICE / "log"
cartella_log.mkdir(exist_ok=True)
file_log = cartella_log / "server.log"
if file_log.exists() and file_log.stat().st_size > 5 * 1024 * 1024:
    file_log.replace(cartella_log / "server.old.log")
sys.stdout = sys.stderr = open(file_log, "a", encoding="utf-8", buffering=1)

impostazioni = json.loads((RADICE / "impostazioni.json").read_text(encoding="utf-8-sig"))
os.environ["SINTESI_DATI"] = impostazioni["cartella_dati"]
if impostazioni.get("agenzia"):
    os.environ["SINTESI_AGENZIA"] = impostazioni["agenzia"]
if impostazioni.get("tesseract"):
    os.environ["TESSERACT_CMD"] = impostazioni["tesseract"]

os.chdir(PROGRAMMA)
sys.path.insert(0, str(PROGRAMMA))

import uvicorn  # noqa: E402

uvicorn.run("sintesi.main:app", host="0.0.0.0", port=int(impostazioni.get("porta", 8081)))
