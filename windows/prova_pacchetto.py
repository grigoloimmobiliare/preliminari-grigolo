"""Prova del programma dei preliminari già avviato: crea una pratica, carica un documento, genera il Word.

Uso: python windows/prova_pacchetto.py http://127.0.0.1:8181 <cartella dati>
"""

import sys
import time
from pathlib import Path
from urllib.parse import unquote

import cv2
import httpx
import numpy as np

base, dati = sys.argv[1], Path(sys.argv[2])
c = httpx.Client(base_url=base, timeout=120)
r = c.post("/pratiche", data={"nome": "Prova pacchetto"}, follow_redirects=False)
pid = unquote(r.headers["location"].split("/pratiche/", 1)[1].split("#")[0].split("?")[0])
cartella = dati / "pratiche" / pid
for sotto in ("01_Proposta", "02_Documenti_venditori", "03_Documenti_acquirenti", "04_Atto_provenienza",
              "05_Planimetrie"):
    assert (cartella / sotto).is_dir(), sotto

# un "documento" con del testo, per far lavorare l'OCR durante l'analisi
img = np.full((900, 1400, 3), 255, np.uint8)
cv2.putText(img, "REPUBBLICA ITALIANA - CARTA DI IDENTITA", (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
ok, png = cv2.imencode(".png", img)
c.post(f"/pratiche/{pid}/carica/venditori", files={"files": ("documento.png", png.tobytes(), "image/png")})
assert (cartella / "02_Documenti_venditori" / "documento.png").exists()

c.post(f"/pratiche/{pid}/analizza")
for _ in range(120):
    stato = c.get(f"/pratiche/{pid}/stato").json()
    if not stato.get("in_corso") and stato.get("stato") != "in corso":
        break
    time.sleep(1)
print("ANALISI:", stato)

c.post(f"/pratiche/{pid}/genera")
word = list(cartella.glob("Preliminare*.docx"))
assert word, f"Word non creato: {list(cartella.iterdir())}"
assert c.get("/modello").status_code == 200
print("PROVA OK:", word[0])
