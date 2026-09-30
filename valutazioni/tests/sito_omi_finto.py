"""Imitazione del sito OMI (ricerca a passi con menu a tendina) per provare la navigazione."""

from urllib.parse import parse_qs, urlparse

SEMESTRI = [("20252", "2025 - Semestre 2"), ("20251", "2025 - Semestre 1"), ("20242", "2024 - Semestre 2")]
PROVINCE = [("TV", "TREVISO"), ("VE", "VENEZIA")]
COMUNI = {"TV": [("L407", "TREVISO"), ("F269", "MOGLIANO VENETO")], "VE": [("L736", "VENEZIA")]}
ZONE = [("B1", "B1/Centrale/CENTRO STORICO ALL'INTERNO DELLE MURA"), ("C1", "C1/Semicentrale/SAN ZENO"),
        ("D11", "D11/Periferica/S. ANTONINO")]
DESTINAZIONI = [("1", "Residenziale"), ("5", "Commerciale")]


def _select(nome, opzioni, scelto, auto=True):
    ch = ' onchange="this.form.submit()"' if auto else ""
    righe = ['<option value="">Seleziona...</option>'] + [
        f'<option value="{v}"{" selected" if v == scelto else ""}>{t}</option>' for v, t in opzioni]
    return f'<td>{nome.capitalize()}</td><td><select name="{nome}"{ch}>{"".join(righe)}</select></td>'


def pagina(url: str) -> str:
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if u.path.endswith("risultato.php"):
        z = dict(ZONE)[q["fasciazona"]]
        d = dict(DESTINAZIONI)[q["destinazione"]]
        sem = dict(SEMESTRI)[q["anno_semestre"]]
        return f"""<html><body><div id="menu">Menu del sito</div>
        <h2>Risultato interrogazione: {sem}</h2>
        <table><tr><td>Provincia: TREVISO</td></tr><tr><td>Comune: TREVISO</td></tr>
        <tr><td>Fascia/zona: {z}</td></tr><tr><td>Destinazione: {d}</td></tr></table>
        <table border=1><tr><th>Tipologia</th><th>Stato conservativo</th><th>Valore Mercato (€/mq) Min</th>
        <th>Max</th></tr><tr><td>Abitazioni civili</td><td>NORMALE</td><td>2100</td><td>2900</td></tr></table>
        <a href="ricerca.htm?level=0">Nuova ricerca</a></body></html>"""
    prov, com = q.get("provincia", ""), q.get("comune", "")
    righe = [_select("anno_semestre", SEMESTRI, q.get("anno_semestre", ""), auto=False),
             _select("provincia", PROVINCE, prov)]
    if prov:
        righe.append(_select("comune", COMUNI[prov], com))
    azione = "ricerca.htm"
    if prov and com:
        righe.append(_select("fasciazona", ZONE, q.get("fasciazona", ""), auto=False))
        righe.append(_select("destinazione", DESTINAZIONI, q.get("destinazione", ""), auto=False))
        azione = "risultato.php"
    bottone = '<input type="submit" value="Ricerca">' if azione.endswith("php") else ""
    tr = "".join(f"<tr>{r}</tr>" for r in righe)
    return f"""<html><body><h1>Banca dati delle quotazioni immobiliari - Ricerca</h1>
    <form action="{azione}" method="get"><table>{tr}</table>{bottone}</form></body></html>"""


def configura(ctx):
    def gestisci(route):
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=pagina(route.request.url))
    ctx.route("https://www1.agenziaentrate.gov.it/**", gestisci)
