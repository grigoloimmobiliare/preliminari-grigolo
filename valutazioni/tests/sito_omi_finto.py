"""Imitazione del sito OMI (ricerca a passi con menu a tendina) per provare la navigazione."""

from urllib.parse import parse_qs, urlparse

SEMESTRI = [("20252", "2025 - Semestre 2"), ("20251", "2025 - Semestre 1"), ("20242", "2024 - Semestre 2")]
PROVINCE = [("TV", "TREVISO"), ("VE", "VENEZIA")]
COMUNI = {"TV": [("L407", "TREVISO"), ("F269", "MOGLIANO VENETO")], "VE": [("L736", "VENEZIA")]}
ZONE = [("B1", "B1/Centrale/CENTRO STORICO ALL'INTERNO DELLE MURA"), ("C1", "C1/Semicentrale/SAN ZENO"),
        ("D11", "D11/Periferica/S. ANTONINO")]
DESTINAZIONI = [("1", "Residenziale"), ("5", "Commerciale")]
VALORI = {
    "Residenziale": [("Abitazioni civili", "NORMALE", "2100", "2900", "7,5", "10,2"),
                     ("Box", "NORMALE", "1300", "1800", "5,8", "8"),
                     ("Ville e Villini", "NORMALE", "2400", "3200", "7,9", "10,8")],
    "Commerciale": [("Negozi", "NORMALE", "1900", "3200", "10", "17,5")],
}


def _select(nome, opzioni, scelto, auto=True):
    ch = ' onchange="this.form.submit()"' if auto else ""
    righe = ['<option value="">Seleziona...</option>'] + [
        f'<option value="{v}"{" selected" if v == scelto else ""}>{t}</option>' for v, t in opzioni]
    return f'<td>{nome.capitalize()}</td><td><select name="{nome}"{ch}>{"".join(righe)}</select></td>'


def pagina(url: str) -> str:
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if u.path.endswith("logo.png"):
        return None
    if u.path.endswith("risultato.php"):
        z = dict(ZONE)[q["fasciazona"]]
        d = dict(DESTINAZIONI)[q["destinazione"]]
        anno, sem = q["anno_semestre"][:4], q["anno_semestre"][4]
        righe = VALORI[d]
        corpo = "".join(f"<tr><td>{t}</td><td>{s}</td><td>{a}</td><td>{b}</td><td>L</td><td>{c}</td><td>{e}</td>"
                        f"<td>N</td></tr>" for t, s, a, b, c, e in righe)
        return f"""<html><body><div id="testata"><img src="/img/logo.png" alt="Agenzia delle Entrate"
        width="200" height="50"></div><div id="menu">Menu del sito</div>
        <h2>Risultato interrogazione: Anno {anno} - Semestre {sem}</h2>
        <table><tr><td>Provincia: TREVISO</td></tr><tr><td>Comune: TREVISO</td></tr>
        <tr><td>Fascia/zona: {z.split('/', 1)[1]}</td></tr><tr><td>Codice di zona: {q["fasciazona"]}</td></tr>
        <tr><td>Microzona catastale n.: 1</td></tr><tr><td>Tipologia prevalente: Abitazioni civili</td></tr>
        <tr><td>Destinazione: {d}</td></tr></table>
        <table border=1><tr><th rowspan=2>Tipologia</th><th rowspan=2>Stato conservativo</th>
        <th colspan=2>Valore Mercato (€/mq)</th><th rowspan=2>Superficie (L/N)</th>
        <th colspan=2>Valori Locazione (€/mq x mese)</th><th rowspan=2>Superficie (L/N)</th></tr>
        <tr><th>Min</th><th>Max</th><th>Min</th><th>Max</th></tr>{corpo}</table>
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
    # come sul sito vero: una finestra a comparsa che copre i pulsanti
    popup = ('<div class="modal-backdrop fade show" style="position:fixed;inset:0;background:rgba(0,0,0,.4)"></div>'
             '<div class="lfr-layout-structure-item-popup" style="position:fixed;inset:10%;background:#fff">'
             '<h3 class="card-title">Modalità di accesso</h3></div>')
    tr = "".join(f"<tr>{r}</tr>" for r in righe)
    return f"""<html><body><h1>Banca dati delle quotazioni immobiliari - Ricerca</h1>
    <form action="{azione}" method="get"><table>{tr}</table>{bottone}</form>{popup}</body></html>"""


def configura(ctx):
    def gestisci(route):
        if route.request.url.endswith("logo.png"):
            from io import BytesIO

            from PIL import Image, ImageDraw
            im = Image.new("RGB", (200, 50), (0, 70, 140))
            ImageDraw.Draw(im).text((10, 18), "Agenzia Entrate (finto)", fill="white")
            buf = BytesIO()
            im.save(buf, "PNG")
            route.fulfill(status=200, content_type="image/png", body=buf.getvalue())
            return
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=pagina(route.request.url))
    ctx.route("https://www1.agenziaentrate.gov.it/**", gestisci)
