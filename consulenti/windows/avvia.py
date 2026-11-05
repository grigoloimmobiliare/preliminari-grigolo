"""Avvio del programma Report consulenti su un PC Windows.

Il programma sta nella cartella condivisa (\\\\NAS\\Consulenti\\Programma) e viene copiato sul PC da
"Avvia Report consulenti.bat"; i dati (report dei collaboratori, benchmark, file prodotti) restano
nella cartella condivisa, passata come primo argomento.

Su ogni PC il programma risponde solo a quel PC (127.0.0.1) e si apre nel browser predefinito.
Riaprendo "Avvia Report consulenti" mentre è già in esecuzione si apre solo una nuova scheda.
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

STATO = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Report consulenti Grigolo" / "in_esecuzione.json"


def _cartella_dati() -> Path:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return Path(sys.argv[1].strip().strip('"'))
    if os.environ.get("CONSULENTI_DATI"):
        return Path(os.environ["CONSULENTI_DATI"])
    return Path(sys.executable).resolve().parent.parent / "Dati"


def _risponde(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/salute", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _porta_libera() -> int:
    for porta in range(8091, 8110):   # 8081-8090 sono usate da Valutazioni
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", porta))
                return porta
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    dati = _cartella_dati()
    # già aperto su questo PC: basta una nuova scheda del browser
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

    os.environ["CONSULENTI_DATI"] = str(dati)
    from app.main import app   # dopo aver impostato la cartella dei dati
    import uvicorn

    porta = int(os.environ.get("CONSULENTI_PORTA") or _porta_libera())
    STATO.parent.mkdir(parents=True, exist_ok=True)
    STATO.write_text(json.dumps({"porta": porta, "dati": str(dati), "pid": os.getpid()}), encoding="utf-8")
    url = f"http://127.0.0.1:{porta}/"

    def apri():
        for _ in range(40):
            if _risponde(porta):
                break
            time.sleep(0.25)
        if not os.environ.get("CONSULENTI_SENZA_BROWSER"):
            webbrowser.open(url)

    threading.Thread(target=apri, daemon=True).start()
    print("\n  REPORT CONSULENTI - Grigolo Immobiliare")
    print(f"  Il programma è aperto nel browser: {url}")
    print(f"  Dati nella cartella condivisa: {dati}")
    print("\n  Lascia aperta questa finestra mentre usi il programma; chiudila per terminare.\n")
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")


if __name__ == "__main__":
    main()
