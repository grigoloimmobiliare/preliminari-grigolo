"""Prova del programma gia' avviato: dalla pagina (carica l'atto, crea il PDF) e dalla cartella
condivisa (PDF copiato in una cartella nuova -> sintesi creata da sola).

Uso: python sintesi/windows/prova_pacchetto.py http://127.0.0.1:8091 <cartella dati>
"""

import os
import sys
import time
from pathlib import Path

import httpx
import pymupdf

base, dati = sys.argv[1], Path(sys.argv[2])
radice = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(radice))
sys.path.insert(0, str(radice / "tests"))
from test_sintesi import ATTO  # noqa: E402


def pdf_da_testo(testo: str, percorso: Path) -> None:
    doc = pymupdf.open()
    righe = testo.split("\n")
    for i in range(0, len(righe), 55):
        doc.new_page().insert_text((40, 50), "\n".join(righe[i:i + 55]), fontsize=8)
    doc.save(percorso)


atto = dati.parent / "atto prova.pdf"
pdf_da_testo(ATTO, atto)

# 1) dalla pagina
c = httpx.Client(base_url=base, timeout=120)
r = c.post("/immobili", data={"nome": "Prova pagina"}, follow_redirects=False)
url = r.headers["location"]
c.post(f"{url}/carica/atto", files={"files": ("atto.pdf", atto.read_bytes(), "application/pdf")})
r = c.post(f"{url}/analizza", follow_redirects=False)
assert "Sintesi" in r.headers["location"] and "Errore" not in r.headers["location"], r.headers["location"]
creati = list(dati.glob("*Prova pagina*/Sintesi*.pdf"))
assert creati, list(dati.rglob("*"))
testo = "".join(p.get_text() for p in pymupdf.open(creati[0]))
for atteso in ("Provenienza precedente", "Vincoli e gravami", "Situazione urbanistica", "Licenza edilizia"):
    assert atteso in testo, atteso
print("PAGINA OK:", creati[0])

# 2) dalla cartella condivisa
cartella = dati / "Prova cartella"
cartella.mkdir()
copia = cartella / "atto notaio.pdf"
copia.write_bytes(atto.read_bytes())
vecchio = time.time() - 120          # come se la copia fosse finita da un po'
os.utime(copia, (vecchio, vecchio))
for _ in range(120):
    pdf = cartella / "Sintesi - Prova cartella.pdf"
    if pdf.exists():
        break
    time.sleep(1)
assert pdf.exists(), list(cartella.rglob("*"))
assert (cartella / "Atto_provenienza" / "atto notaio.pdf").exists()
assert c.get("/").status_code == 200
print("CARTELLA OK:", pdf)
