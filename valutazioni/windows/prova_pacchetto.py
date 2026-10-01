"""Prova del programma già avviato: crea una valutazione, carica un Excel, genera il Word.

Uso: python windows/prova_pacchetto.py http://127.0.0.1:8081 <cartella dati>
"""

import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import httpx
import openpyxl

base, dati = sys.argv[1], Path(sys.argv[2])
radice = Path(__file__).resolve().parent.parent

wb = openpyxl.load_workbook(radice / "modelli" / "stima_modello.xlsx")
ws = wb["Foglio2"]
ws["F4"], ws["B4"], ws["G5"], ws["F6"] = "Prova", "Via Roma 1", datetime(2026, 1, 1), "Firma Prova"
for cella, mq in {"B10": 6, "B11": 30}.items():
    ws[cella] = mq
excel = dati.parent / "prova.xlsx"
wb.save(excel)

c = httpx.Client(base_url=base, timeout=60)
r = c.post("/valutazioni", data={"nome": "Prova pacchetto"}, follow_redirects=False)
url = r.headers["location"]
c.post(f"{url}/carica/excel", files={"files": ("prova.xlsx", excel.read_bytes())})
c.post(f"{url}/genera", data={"omi": "no"})
cartella = dati / "valutazioni" / unquote(url.rsplit("/", 1)[1])
for _ in range(60):
    word = list(cartella.glob("Valutazione*.docx"))
    if word:
        break
    time.sleep(1)
assert word, f"Word non creato: {list(cartella.iterdir())}"
assert (dati / "modello" / "valutazione_modello.docx").exists()
assert c.get("/impostazioni").status_code == 200 and c.get("/guida").status_code == 200
print("PROVA OK:", word[0])
