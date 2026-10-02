"""Elenco delle zone OMI di un comune, preso dal sito dell'Agenzia delle Entrate.

Uso:  python strumenti/zone_omi.py TV Treviso [--valori] [--uscita cartella]
Con --valori scarica anche i valori (tutte le destinazioni) di ogni zona.
Scrive zone_<comune>.json e zone_<comune>.md nella cartella di uscita.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import omi  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("provincia")
    ap.add_argument("comune")
    ap.add_argument("--valori", action="store_true")
    ap.add_argument("--uscita", default=".")
    a = ap.parse_args()
    uscita = Path(a.uscita)
    uscita.mkdir(parents=True, exist_ok=True)
    nome = omi.n(a.comune).replace(" ", "_").lower()

    r = omi.zone_disponibili(a.provincia, a.comune)
    print(f"Semestre: {r['semestre']}  -  {len(r['zone'])} zone")
    righe = [f"# Zone OMI di {a.comune} ({a.provincia}) - {r['semestre']}", "",
             "| Codice | Zona (come sul sito) |", "|---|---|"]
    for z in r["zone"]:
        print("  ", z)
        righe.append(f"| {omi.codice_zona(z)} | {z} |")

    if a.valori:
        r["valori"] = {}
        for z in r["zone"]:
            cod = omi.codice_zona(z)
            try:
                ris = omi.cerca(a.provincia, a.comune, cod, uscita / "schermate" / cod)
                r["valori"][cod] = ris.tabelle
                righe += ["", f"## {z}"]
                for t in ris.tabelle:
                    righe.append(f"**{t.get('destinazione', '')}**")
                    griglia = {}
                    for c in t["celle"]:
                        griglia.setdefault(c["r"], []).append(c["t"])
                    for rr in sorted(griglia):
                        righe.append("- " + " | ".join(griglia[rr]))
                print(f"OK {cod}: {len(ris.tabelle)} destinazioni")
            except Exception as e:  # noqa: BLE001 - si prosegue con le altre zone
                print(f"ERRORE {cod}: {e}")
                traceback.print_exc()

    (uscita / f"zone_{nome}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    (uscita / f"zone_{nome}.md").write_text("\n".join(righe) + "\n", encoding="utf-8")
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
