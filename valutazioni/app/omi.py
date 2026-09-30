"""Ricerca delle quotazioni OMI sul sito dell'Agenzia delle Entrate e schermata del risultato.

Pagina: https://www1.agenziaentrate.gov.it/servizi/Consultazione/ricerca.htm?level=0
La ricerca testuale si fa scegliendo, un passo alla volta, semestre, provincia, comune,
fascia/zona e destinazione. Il programma non si affida a nomi fissi dei campi: a ogni
passo guarda i menu a tendina (o i link) presenti, riconosce a cosa servono dal nome e
dalle voci, sceglie il valore giusto e prosegue fino alla pagina del risultato.
Semestre: sempre l'ultimo disponibile. Destinazione: tutte quelle della zona
(una schermata per ciascuna), oppure solo quelle indicate.

In caso di errore vengono salvati la pagina e la schermata dell'ultimo passo, utili per
capire cosa è cambiato sul sito.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("valutazioni.omi")

URL_RICERCA = "https://www1.agenziaentrate.gov.it/servizi/Consultazione/ricerca.htm?level=0"
TIMEOUT_MS = 45_000
PASSI_MAX = 14

SIGLE = {
    "AG": "AGRIGENTO", "AL": "ALESSANDRIA", "AN": "ANCONA", "AO": "AOSTA", "AR": "AREZZO", "AP": "ASCOLI PICENO",
    "AT": "ASTI", "AV": "AVELLINO", "BA": "BARI", "BT": "BARLETTA ANDRIA TRANI", "BL": "BELLUNO", "BN": "BENEVENTO",
    "BG": "BERGAMO", "BI": "BIELLA", "BO": "BOLOGNA", "BZ": "BOLZANO", "BS": "BRESCIA", "BR": "BRINDISI",
    "CA": "CAGLIARI", "CL": "CALTANISSETTA", "CB": "CAMPOBASSO", "CE": "CASERTA", "CT": "CATANIA", "CZ": "CATANZARO",
    "CH": "CHIETI", "CO": "COMO", "CS": "COSENZA", "CR": "CREMONA", "KR": "CROTONE", "CN": "CUNEO", "EN": "ENNA",
    "FM": "FERMO", "FE": "FERRARA", "FI": "FIRENZE", "FG": "FOGGIA", "FC": "FORLI CESENA", "FR": "FROSINONE",
    "GE": "GENOVA", "GO": "GORIZIA", "GR": "GROSSETO", "IM": "IMPERIA", "IS": "ISERNIA", "AQ": "L AQUILA",
    "SP": "LA SPEZIA", "LT": "LATINA", "LE": "LECCE", "LC": "LECCO", "LI": "LIVORNO", "LO": "LODI", "LU": "LUCCA",
    "MC": "MACERATA", "MN": "MANTOVA", "MS": "MASSA CARRARA", "MT": "MATERA", "ME": "MESSINA", "MI": "MILANO",
    "MO": "MODENA", "MB": "MONZA E DELLA BRIANZA", "NA": "NAPOLI", "NO": "NOVARA", "NU": "NUORO", "OR": "ORISTANO",
    "PD": "PADOVA", "PA": "PALERMO", "PR": "PARMA", "PV": "PAVIA", "PG": "PERUGIA", "PU": "PESARO E URBINO",
    "PE": "PESCARA", "PC": "PIACENZA", "PI": "PISA", "PT": "PISTOIA", "PN": "PORDENONE", "PZ": "POTENZA",
    "PO": "PRATO", "RG": "RAGUSA", "RA": "RAVENNA", "RC": "REGGIO CALABRIA", "RE": "REGGIO EMILIA", "RI": "RIETI",
    "RN": "RIMINI", "RM": "ROMA", "RO": "ROVIGO", "SA": "SALERNO", "SS": "SASSARI", "SV": "SAVONA", "SI": "SIENA",
    "SR": "SIRACUSA", "SO": "SONDRIO", "SU": "SUD SARDEGNA", "TA": "TARANTO", "TE": "TERAMO", "TR": "TERNI",
    "TO": "TORINO", "TP": "TRAPANI", "TN": "TRENTO", "TV": "TREVISO", "TS": "TRIESTE", "UD": "UDINE",
    "VA": "VARESE", "VE": "VENEZIA", "VB": "VERBANO CUSIO OSSOLA", "VC": "VERCELLI", "VR": "VERONA",
    "VV": "VIBO VALENTIA", "VI": "VICENZA", "VT": "VITERBO",
}


class ErroreOMI(Exception):
    pass


@dataclass
class RisultatoOMI:
    immagini: list[Path] = field(default_factory=list)
    semestre: str = ""
    destinazioni: list[str] = field(default_factory=list)
    note: list[str] = field(default_factory=list)


def n(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", s)).strip()


def nome_provincia(p: str) -> str:
    p = n(p)
    return SIGLE.get(p, p)


def codice_zona(z: str) -> str:
    """"B1", "zona B1", "B1 - Centro storico", "B1/Centrale" -> "B1"."""
    m = re.search(r"\b([A-Z]\d{1,2})\b", n(z).replace("ZONA ", ""))
    return m.group(1) if m else n(z)


# ------------------------------------------------------------ scelta delle voci

def _periodo(testo: str) -> tuple[int, int] | None:
    t = n(testo)
    anno = re.search(r"(19|20)\d\d", t)
    if not anno:
        return None
    sem = 0
    if re.search(r"\b(2|II|SECONDO|2O)\b", t.replace(anno.group(0), "")):
        sem = 2
    elif re.search(r"\b(1|I|PRIMO|1O)\b", t.replace(anno.group(0), "")):
        sem = 1
    return int(anno.group(0)), sem


def scegli_semestre(opzioni: list[tuple[str, str]]) -> tuple[str, str] | None:
    validi = [(p, o) for o in opzioni if (p := _periodo(o[1]))]
    return max(validi, key=lambda x: x[0])[1] if validi else None


def punteggio_zona(testo: str, codice: str) -> int:
    t = n(testo)
    if not re.search(rf"(^|[^A-Z0-9]){codice}([^A-Z0-9]|$)", t):
        return 0
    if t.startswith(codice):
        return 3
    if re.search(rf"\b(ZONA|CODICE ZONA|COD ZONA)\s*{codice}\b", t) or f"({codice})" in testo.upper():
        return 2
    return 1


def scegli(opzioni: list[tuple[str, str]], target: str, tipo: str) -> tuple[str, str] | None:
    """opzioni: (value, testo). Restituisce l'opzione da selezionare per il tipo di menu."""
    if tipo == "semestre":
        return scegli_semestre(opzioni)
    if tipo == "zona":
        cod = codice_zona(target)
        migliori = sorted(((punteggio_zona(t, cod), (v, t)) for v, t in opzioni), key=lambda x: -x[0])
        return migliori[0][1] if migliori and migliori[0][0] > 0 else None
    t = n(target)
    for v, testo in opzioni:
        if n(testo) == t:
            return v, testo
    for v, testo in opzioni:            # "TREVISO (TV)", "TV - TREVISO"...
        if t and re.search(rf"(^|\s){re.escape(t)}(\s|$)", n(testo)):
            return v, testo
    return None


def tipo_menu(nome: str, etichetta: str, opzioni: list[tuple[str, str]]) -> str | None:
    chiave = n(f"{nome} {etichetta}")
    testi = " | ".join(n(t) for _, t in opzioni[:40])
    if re.search(r"SEMEST|ANNO|PERIOD", chiave) or sum(1 for _, t in opzioni if _periodo(t)) >= max(2, len(opzioni) // 2):
        return "semestre"
    if re.search(r"PROV", chiave):
        return "provincia"
    if re.search(r"COMUN", chiave):
        return "comune"
    if re.search(r"ZON|FASC", chiave):
        return "zona"
    if re.search(r"DEST|USO|TIPOLOG", chiave) or re.search(r"RESIDENZIAL|COMMERCIAL|TERZIARI|PRODUTTIV", testi):
        return "destinazione"
    return None


def _vuota(v: str, t: str) -> bool:
    return not v.strip() or n(t) in ("", "SELEZIONA", "SCEGLI", "TUTTE", "TUTTI") or n(t).startswith(("SELEZION", "SCEGLI"))


# ------------------------------------------------------------ navigazione

JS_MENU = """() => Array.from(document.querySelectorAll('select')).filter(s => {
    const r = s.getBoundingClientRect(); return !s.disabled && (r.width > 0 || r.height > 0);
}).map((s, i) => {
    let et = '';
    if (s.id) { const l = document.querySelector(`label[for="${s.id}"]`); if (l) et = l.innerText; }
    if (!et) { const td = s.closest('td,div,p,li'); const prev = td && td.previousElementSibling;
               if (prev) et = prev.innerText; }
    if (!et && s.parentElement) et = s.parentElement.innerText.split('\\n')[0];
    return {indice: i, nome: (s.name || '') + ' ' + (s.id || ''), etichetta: (et || '').slice(0, 80),
            valore: s.value, opzioni: Array.from(s.options).map(o => [o.value, o.text.trim()])};
})"""


def _e_risultato(page) -> bool:
    try:
        testo = n(page.inner_text("body", timeout=5000))
    except Exception:
        return False
    return ("VALORE MERCATO" in testo or "VALORI DI MERCATO" in testo) and "STATO CONSERVATIVO" in testo


def _attendi(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    except Exception:
        page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_MS)


def _clicca_ricerca(page) -> bool:
    for sel in ("input[type=submit]", "button[type=submit]", "input[type=button]", "button", "input[type=image]", "a"):
        for el in page.query_selector_all(sel):
            try:
                if not el.is_visible():
                    continue
                testo = n((el.get_attribute("value") or "") + " " + (el.inner_text() or "") + " "
                          + (el.get_attribute("alt") or "") + " " + (el.get_attribute("title") or ""))
            except Exception:
                continue
            if re.search(r"\b(RICERCA|CERCA|VISUALIZZA|CONFERMA|INVIA|AVANTI|PROSEGUI|MOSTRA)\b", testo) \
                    and not re.search(r"NUOVA RICERCA|ANNULLA|TORNA", testo):
                el.click()
                _attendi(page)
                return True
    return False


def _clicca_link(page, target: str, tipo: str) -> bool:
    """Alcune versioni della ricerca elencano province/comuni/zone come link."""
    links = page.query_selector_all("a")
    opzioni = []
    for i, a in enumerate(links):
        try:
            if a.is_visible():
                opzioni.append((str(i), a.inner_text().strip()))
        except Exception:
            pass
    scelta = scegli(opzioni, target, tipo)
    if not scelta:
        return False
    links[int(scelta[0])].click()
    _attendi(page)
    return True


def _naviga(page, obiettivi: dict[str, str], note: list[str], esplora: bool = False) -> list[str] | None:
    """Sceglie le voci passo passo finché compare il risultato.

    Con `esplora`, se compare il menu delle destinazioni si ferma e ne restituisce le voci.
    """
    page.goto(URL_RICERCA, timeout=TIMEOUT_MS)
    _attendi(page)
    fatti_link: set[str] = set()
    for _ in range(PASSI_MAX):
        if _e_risultato(page):
            return None
        mosso = False
        menu = page.evaluate(JS_MENU)
        for m in menu:
            opz = [(v, t) for v, t in m["opzioni"] if not _vuota(v, t)]
            if not opz:
                continue
            tipo = tipo_menu(m["nome"], m["etichetta"], opz)
            if tipo is None:
                # menu senza nome riconoscibile: lo si prova coi valori in ordine
                tipo = next((k for k in ("provincia", "comune", "zona")
                             if k in obiettivi and scegli(opz, obiettivi[k], k)), None)
                if tipo is None:
                    continue
            if tipo == "destinazione" and not obiettivi.get("destinazione"):
                if esplora:
                    return [t for _, t in opz]
                continue
            scelta = scegli(opz, obiettivi.get(tipo, ""), tipo)
            if not scelta:
                if tipo in ("provincia", "comune", "zona", "destinazione"):
                    disponibili = ", ".join(t for _, t in opz[:60])
                    raise ErroreOMI(f"{tipo.capitalize()} '{obiettivi.get(tipo)}' non trovata tra le voci del sito: "
                                    f"{disponibili}")
                continue
            if tipo == "semestre" and f"Semestre: {scelta[1]}" not in note:
                note.append(f"Semestre: {scelta[1]}")
            if m["valore"] == scelta[0]:
                continue
            sel = page.locator("select").nth(m["indice"])
            with_nav = False
            try:
                with page.expect_navigation(timeout=2000):
                    sel.select_option(value=scelta[0])
                with_nav = True
            except Exception:
                pass
            if not with_nav:
                page.wait_for_timeout(800)
            _attendi(page)
            mosso = True
            break
        if mosso:
            continue
        # nessun menu da cambiare: link oppure pulsante di ricerca
        for tipo in ("provincia", "comune", "zona"):
            if tipo not in fatti_link and _clicca_link(page, obiettivi[tipo], tipo):
                fatti_link.add(tipo)
                mosso = True
                break
        if mosso:
            continue
        if not _clicca_ricerca(page):
            break
    if not _e_risultato(page):
        raise ErroreOMI("La pagina del risultato OMI non è comparsa: il sito potrebbe essere cambiato.")
    return None


def _schermata(page, dest: Path) -> None:
    """Schermata della parte con i dati: intestazione (provincia, comune, zona...) e tabella dei valori."""
    box = page.evaluate("""() => {
        const chiavi = ['STATO CONSERVATIVO', 'VALORE MERCATO', 'VALORI DI MERCATO', 'FASCIA', 'PROVINCIA',
                        'COMUNE', 'DESTINAZIONE', 'SEMESTRE', 'RISULTATO'];
        const norm = s => (s || '').toUpperCase().normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '');
        let els = Array.from(document.querySelectorAll('table')).filter(t => {
            const tx = norm(t.innerText); return chiavi.some(k => tx.includes(k));
        });
        // solo le tabelle più interne (senza tabelle figlie che già corrispondono)
        els = els.filter(t => !els.some(o => o !== t && t.contains(o)));
        if (!els.length) return null;
        // titolo del risultato (es. "Risultato interrogazione: Anno 2025 - Semestre 2")
        for (const h of document.querySelectorAll('h1,h2,h3,h4,caption,legend,.titolo,.title')) {
            const tx = norm(h.innerText);
            if (/RISULTATO|SEMESTRE|QUOTAZIONI/.test(tx) && tx.length < 200) els.push(h);
        }
        let x0 = 1e9, y0 = 1e9, x1 = 0, y1 = 0;
        for (const e of els) {
            const r = e.getBoundingClientRect();
            if (r.width < 50 || r.height < 10) continue;
            x0 = Math.min(x0, r.left + scrollX); y0 = Math.min(y0, r.top + scrollY);
            x1 = Math.max(x1, r.right + scrollX); y1 = Math.max(y1, r.bottom + scrollY);
        }
        return x1 > x0 ? {x: x0, y: y0, w: x1 - x0, h: y1 - y0} : null;
    }""")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if box:
        m = 12
        page.screenshot(path=str(dest), full_page=True, clip={
            "x": max(box["x"] - m, 0), "y": max(box["y"] - m, 0), "width": box["w"] + 2 * m, "height": box["h"] + 2 * m})
    else:
        page.screenshot(path=str(dest), full_page=True)
    from PIL import Image
    from .immagini import ritaglia_bianco
    with Image.open(dest) as im:
        ritagliata = ritaglia_bianco(im, margine=16)
    ritagliata.save(dest)


def cerca(provincia: str, comune: str, zona: str, cartella: Path, destinazioni: list[str] | None = None,
          prefisso: str = "auto_OMI", configura=None) -> RisultatoOMI:
    """Esegue la ricerca e salva una schermata per ogni destinazione (Residenziale, Commerciale...)."""
    from playwright.sync_api import sync_playwright

    ris = RisultatoOMI()
    obiettivi = {"provincia": nome_provincia(provincia), "comune": comune, "zona": zona}
    cartella.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(locale="it-IT", viewport={"width": 1200, "height": 900}, device_scale_factor=2,
                                  user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                             "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
        if configura:            # usato dai test per simulare il sito
            configura(ctx)
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        try:
            note: list[str] = []
            elenco = destinazioni or _naviga(page, obiettivi, note, esplora=True)
            if not elenco:        # risultato raggiunto senza scegliere la destinazione
                dest = cartella / f"{prefisso}.png"
                _schermata(page, dest)
                ris.immagini.append(dest)
            else:
                for i, d in enumerate(elenco, 1):
                    _naviga(page, {**obiettivi, "destinazione": d}, note)
                    dest = cartella / f"{prefisso} {i} - {re.sub(r'[^A-Za-z ]', '', d).strip()}.png"
                    _schermata(page, dest)
                    ris.immagini.append(dest)
                    ris.destinazioni.append(d)
            ris.semestre = next((x.split(": ", 1)[1] for x in note if x.startswith("Semestre")), "")
        except Exception as e:
            try:
                (cartella / "errore_OMI.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(cartella / "errore_OMI.png"), full_page=True)
            except Exception:
                pass
            if isinstance(e, ErroreOMI):
                raise
            raise ErroreOMI(f"Ricerca OMI non riuscita: {e}") from e
        finally:
            browser.close()
    return ris
