"""Avvio del programma "Sintesi atti di provenienza" su un PC Windows.

Il programma sta nella cartella condivisa del server (\\\\SERVER\\Sintesi\\Programma) e viene
copiato sul PC da "Avvia Sintesi.bat"; i dati (una cartella per immobile, con l'atto e il PDF di
sintesi) restano nella cartella condivisa, passata come primo argomento.

Su ogni PC il programma risponde solo a quel PC (127.0.0.1) e si apre nel browser predefinito.
Riaprendo "Avvia Sintesi" mentre e' gia' in esecuzione si apre solo una nuova scheda.
Tesseract (lettura degli atti scansionati) e' incluso nel pacchetto, nella cartella "tesseract".
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

STATO = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sintesi Grigolo" / "in_esecuzione.json"


def _cartella_programma() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def _prepara_tesseract() -> None:
    tess = _cartella_programma() / "tesseract"
    if (tess / "tesseract.exe").exists():
        os.environ["PATH"] = str(tess) + os.pathsep + os.environ.get("PATH", "")
        os.environ["TESSDATA_PREFIX"] = str(tess / "tessdata")
        os.environ["TESSERACT_CMD"] = str(tess / "tesseract.exe")


def _cartella_dati() -> Path:
    argomenti = [a for a in sys.argv[1:] if not a.startswith("--")]
    if argomenti and argomenti[0].strip():
        return Path(argomenti[0].strip().strip('"'))
    if os.environ.get("SINTESI_DATI"):
        return Path(os.environ["SINTESI_DATI"])
    return Path(sys.executable).resolve().parent.parent / "Dati"


def _risponde(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/salute", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _porta_libera() -> int:
    for porta in range(8091, 8110):
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
    """Controllo del pacchetto: Tesseract incluso legge un testo? (usato dalla costruzione automatica)"""
    import cv2
    import numpy as np

    from app.estrazione import ocr
    img = np.full((300, 1400), 255, np.uint8)
    cv2.putText(img, "REPERTORIO 12345", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 5)
    letto = ocr.ocr(img, psm=6)
    print("TESSERACT", repr(letto))
    if "12345" not in letto:
        sys.exit(1)


def main() -> None:
    _prepara_tesseract()
    if "--prova-ocr" in sys.argv:
        prova_ocr()
        return
    dati = _cartella_dati()
    # gia' aperto su questo PC: basta una nuova scheda del browser
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

    os.environ["SINTESI_DATI"] = str(dati)
    from sintesi.main import app   # dopo aver impostato la cartella dei dati
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
        if "--senza-browser" not in sys.argv:
            webbrowser.open(url)

    threading.Thread(target=apri, daemon=True).start()
    print("\n  SINTESI ATTI DI PROVENIENZA - Grigolo Immobiliare")
    print(f"  Il programma è aperto nel browser: {url}")
    print(f"  Dati nella cartella condivisa: {dati}")
    print("  Gli atti copiati nella cartella condivisa vengono elaborati mentre questa finestra è aperta.")
    print("\n  Lascia aperta questa finestra mentre usi il programma; chiudila per terminare.\n")
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")


if __name__ == "__main__":
    main()
