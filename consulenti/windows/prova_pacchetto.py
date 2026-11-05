"""Prova del programma già avviato: benchmark, report di un collaboratore, andamento e report mensile.

Uso: python windows/prova_pacchetto.py http://127.0.0.1:8091 <cartella dati>
"""

import io
import sys
from pathlib import Path

import httpx
from openpyxl import load_workbook

base, dati = sys.argv[1], Path(sys.argv[2])
radice = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(radice))
sys.path.insert(0, str(radice / "tests"))
from test_report_mensile import _mensile  # noqa: E402
from test_settimanale import _benchmark, _report_nuovo_formato  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
c = httpx.Client(base_url=base, timeout=60, follow_redirects=True)

r = c.post("/benchmark", data={"anno": 2026, "mese": 10},
           files={"file": ("bm.xlsx", _benchmark({"TATIANA": [27, 40, 25], "UFFICIO": [54, 200, 120]}), XLSX)})
assert r.status_code == 200 and "valori letti" in r.text, r.text[:500]
assert (dati / "benchmark" / "2026-10.xlsx").exists()

r = c.post("/collaboratori", files=[("files", ("REPORT_TATIANA.xlsx", _report_nuovo_formato(), XLSX))])
assert "Salvati i report di TATIANA" in r.text, r.text[:500]
assert (dati / "report_collaboratori" / "TATIANA.xlsx").exists()

r = c.post("/settimanale", data={"anno": 2026, "mese": 10})
assert "pronto" in r.text, r.text[:800]
f = dati / "risultati" / "Andamento settimanale ott 26.xlsx"
assert f.exists() and load_workbook(f).sheetnames == ["SINTESI", "UFFICIO", "TATIANA"]

r = c.post("/report", data={"anno": 2026, "mese": 10}, files={"mensile": ("mensile.xlsx", _mensile(), XLSX)})
assert "pronto" in r.text, r.text[:800]
uscita = list((dati / "risultati").glob("mensile - ott 26.xlsx"))
assert uscita and "CONFRONTO" in load_workbook(io.BytesIO(uscita[0].read_bytes())).sheetnames

for pagina in ("/", "/collaboratori", "/settimanale", "/benchmark", "/report"):
    assert c.get(pagina).status_code == 200, pagina
print("PROVA OK:", sorted(p.name for p in (dati / "risultati").iterdir()))
