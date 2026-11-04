"""Avvio di "Sintesi immobili" su Windows (usato dall'attivita' pianificata creata da installa.ps1).

Legge C:\\SintesiGrigolo\\impostazioni.json e scrive il log in C:\\SintesiGrigolo\\log\\server.log.
Il programma e' copiato in C:\\SintesiGrigolo\\programma (questo file e' in programma\\sintesi\\windows).
"""

import base64
import json
import os
import subprocess
import sys
import threading
import time
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



def _decifra(testo: str) -> str:
    """Password del NAS cifrata dall'installazione con DPAPI (ambito: questo PC)."""
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    dati = base64.b64decode(testo)
    buffer = ctypes.create_string_buffer(dati, len(dati))
    ingresso = BLOB(len(dati), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    uscita = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(ingresso), None, None, None, None, 0,
                                                     ctypes.byref(uscita)):
        raise OSError("password del NAS non decifrabile: rilancia riconfigura_sintesi.bat")
    try:
        return ctypes.string_at(uscita.pbData, uscita.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(uscita.pbData)


def collega_nas() -> bool:
    """Collega la cartella del NAS con le credenziali salvate (il programma gira come SYSTEM)."""
    cartella = impostazioni["cartella_dati"]
    if os.path.isdir(cartella):
        return True
    utente = impostazioni.get("nas_utente")
    condivisione = impostazioni.get("nas_condivisione")
    if not (utente and condivisione):
        return False
    try:
        password = _decifra(impostazioni.get("nas_password", ""))
        esito = subprocess.run(["net", "use", condivisione, password, f"/user:{utente}", "/persistent:no"],
                               capture_output=True, text=True, creationflags=0x08000000)  # senza finestra
        if esito.returncode != 0:
            print(f"Collegamento al NAS {condivisione} non riuscito: {(esito.stdout + esito.stderr).strip()}")
    except Exception as e:
        print(f"Collegamento al NAS non riuscito: {e}")
    return os.path.isdir(cartella)


def _sorveglia_nas():
    # all'accensione la rete puo' non essere ancora pronta: si riprova ogni 10 secondi,
    # poi si ricontrolla ogni 5 minuti (senza bloccare l'avvio della pagina web)
    pronto = False
    while True:
        ok = collega_nas()
        if ok != pronto:
            print(("Cartella dati raggiungibile: " if ok else "ATTENZIONE: cartella dati non raggiungibile: ")
                  + impostazioni["cartella_dati"])
            pronto = ok
        time.sleep(300 if ok else 10)


if impostazioni.get("cartella_dati", "").startswith("\\\\"):
    collega_nas()
    threading.Thread(target=_sorveglia_nas, daemon=True).start()

os.chdir(PROGRAMMA)
sys.path.insert(0, str(PROGRAMMA))

import uvicorn  # noqa: E402

uvicorn.run("sintesi.main:app", host="0.0.0.0", port=int(impostazioni.get("porta", 8081)))
