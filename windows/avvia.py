"""Avvio del programma dei preliminari su un PC Windows.

Il programma sta nella cartella condivisa del server (\\\\SERVER\\Preliminari\\Programma) e viene
copiato sul PC da "Avvia Preliminari.bat"; le pratiche e il modello Word restano nella cartella
condivisa (\\\\SERVER\\Preliminari\\Dati), passata come primo argomento.

Tesseract (OCR dei documenti, con l'italiano) è incluso nel pacchetto, nella cartella "tesseract".
Il numero di pagine del preliminare viene contato con Microsoft Word, se presente sul PC.
Su ogni PC il programma risponde solo a quel PC (127.0.0.1) e si apre nel browser predefinito.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

NOME = "Preliminari Grigolo"
STATO = Path(os.environ.get("LOCALAPPDATA", Path.home())) / NOME / "in_esecuzione.json"
PORTE = range(8181, 8200)


def _cartella_programma() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def _prepara_tesseract() -> None:
    tess = _cartella_programma() / "tesseract"
    if (tess / "tesseract.exe").exists():
        os.environ["PATH"] = str(tess) + os.pathsep + os.environ.get("PATH", "")
        os.environ["TESSDATA_PREFIX"] = str(tess / "tessdata")


def _cartella_dati() -> Path:
    argomenti = [a for a in sys.argv[1:] if not a.startswith("--")]
    if argomenti and argomenti[0].strip():
        return Path(argomenti[0].strip().strip('"'))
    if os.environ.get("PRELIMINARI_DATI"):
        return Path(os.environ["PRELIMINARI_DATI"])
    return _cartella_programma().parent / "Dati"


def _risponde(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/salute", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _porta_libera() -> int:
    for porta in PORTE:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", porta))
                return porta
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def prova_ocr() -> None:
    """Controllo del pacchetto: Tesseract con l'italiano risponde? (usato dalla costruzione automatica)"""
    import cv2
    import numpy as np
    import pytesseract

    lingue = pytesseract.get_languages(config="")
    img = np.full((160, 900, 3), 255, np.uint8)
    cv2.putText(img, "PRELIMINARE DI COMPRAVENDITA", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    testo = pytesseract.image_to_string(img, lang="ita")
    print("TESSERACT", pytesseract.get_tesseract_version(), "lingue:", lingue, "testo:", testo.strip())
    if "ita" not in lingue or "COMPRAVENDITA" not in testo.upper():
        sys.exit(1)


def main() -> None:
    _prepara_tesseract()
    if "--prova-ocr" in sys.argv:
        prova_ocr()
        return
    dati = _cartella_dati()
    try:
        stato = json.loads(STATO.read_text(encoding="utf-8"))
        if stato.get("dati") == str(dati) and _risponde(stato["porta"]):
            webbrowser.open(f"http://127.0.0.1:{stato['porta']}/")
            return
    except Exception:
        pass

    try:
        dati.mkdir(parents=True, exist_ok=True)
        (dati / ".prova_scrittura").write_text("ok", encoding="utf-8")
        (dati / ".prova_scrittura").unlink()
    except OSError as e:
        print(f"\n  Non riesco a scrivere nella cartella dei dati:\n  {dati}\n  ({e})\n")
        print("  Controlla di essere collegato alla rete dell'ufficio e di avere i permessi sulla cartella.")
        input("\n  Premi Invio per chiudere.")
        sys.exit(1)

    os.environ["PRELIMINARI_DATI"] = str(dati)
    from app.main import app   # dopo aver impostato la cartella dei dati
    import uvicorn

    porta = _porta_libera()
    STATO.parent.mkdir(parents=True, exist_ok=True)
    STATO.write_text(json.dumps({"porta": porta, "dati": str(dati), "pid": os.getpid()}), encoding="utf-8")
    url = f"http://127.0.0.1:{porta}/"

    def apri():
        for _ in range(40):
            if _risponde(porta):
                break
            time.sleep(0.25)
        webbrowser.open(url)

    threading.Thread(target=apri, daemon=True).start()
    print("\n  PRELIMINARI - Grigolo Immobiliare")
    print(f"  Il programma è aperto nel browser: {url}")
    print(f"  Pratiche nella cartella condivisa: {dati}")
    print("\n  Lascia aperta questa finestra mentre usi il programma; chiudila per terminare.\n")
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")


if __name__ == "__main__":
    main()
