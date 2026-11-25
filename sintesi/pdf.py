"""Generazione del PDF di sintesi dell'atto di provenienza con ReportLab."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

AGENZIA = os.environ.get("SINTESI_AGENZIA", "Grigolo Immobiliare")

ORO = colors.HexColor("#b8894a")
ORO_CHIARO = colors.HexColor("#f4ead9")
MARRONE = colors.HexColor("#5a3d17")
GRIGIO = colors.HexColor("#6b6b6b")
ROSSO = colors.HexColor("#b3261e")
ROSSO_CHIARO = colors.HexColor("#fdecea")
ARANCIO_CHIARO = colors.HexColor("#fff4e0")
BLU_CHIARO = colors.HexColor("#eef3f8")
VERDE = colors.HexColor("#2e7d32")


# ------------------------------------------------------------------ caratteri

def _registra_font() -> tuple[str, str]:
    """Usa DejaVu Sans o Arial se presenti (accenti e simboli completi), altrimenti Helvetica."""
    candidati = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ]
    for normale, grassetto in candidati:
        if Path(normale).is_file() and Path(grassetto).is_file():
            try:
                pdfmetrics.registerFont(TTFont("Sintesi", normale))
                pdfmetrics.registerFont(TTFont("Sintesi-Bold", grassetto))
                pdfmetrics.registerFontFamily("Sintesi", normal="Sintesi", bold="Sintesi-Bold",
                                              italic="Sintesi", boldItalic="Sintesi-Bold")
                return "Sintesi", "Sintesi-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_B = _registra_font()

S_TITOLO = ParagraphStyle("titolo", fontName=FONT_B, fontSize=17, leading=21, textColor=MARRONE, spaceAfter=2)
S_SOTTO = ParagraphStyle("sotto", fontName=FONT, fontSize=9.5, leading=12, textColor=GRIGIO, spaceAfter=8)
S_H1 = ParagraphStyle("h1", fontName=FONT_B, fontSize=12, leading=15, textColor=MARRONE, spaceBefore=12, spaceAfter=5)
S_H2 = ParagraphStyle("h2", fontName=FONT_B, fontSize=10, leading=13, textColor=colors.black, spaceBefore=6, spaceAfter=3)
S_TESTO = ParagraphStyle("testo", fontName=FONT, fontSize=9, leading=11.8, alignment=TA_LEFT)
S_PICCOLO = ParagraphStyle("piccolo", parent=S_TESTO, fontSize=8, leading=10, textColor=GRIGIO)
S_CITAZIONE = ParagraphStyle("cit", parent=S_TESTO, fontSize=8.5, leading=11, leftIndent=8, borderPadding=0,
                             textColor=colors.HexColor("#333333"), spaceAfter=4)
S_CELLA = ParagraphStyle("cella", fontName=FONT, fontSize=8.5, leading=10.5)
S_CELLA_B = ParagraphStyle("cellab", parent=S_CELLA, fontName=FONT_B)
S_INT = ParagraphStyle("int", parent=S_CELLA, fontName=FONT_B, textColor=colors.white)


def _p(s, stile=S_TESTO) -> Paragraph:
    return Paragraph(escape(str(s or "")).replace("\n", "<br/>"), stile)


def _pb(etichetta: str, valore: str, stile=S_TESTO) -> Paragraph:
    return Paragraph(f"<b>{escape(etichetta)}</b> {escape(str(valore or ''))}", stile)


def _vuoto(s: str = "non rilevato") -> str:
    return f"[{s}]"


# ------------------------------------------------------------------ pagina

class _CanvasNumerato(rl_canvas.Canvas):
    """Canvas che scrive 'Pagina X di Y' a fine documento."""

    def __init__(self, *args, testata: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._pagine = []
        self._testata = testata

    def showPage(self):
        self._pagine.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        totale = len(self._pagine)
        for stato in self._pagine:
            self.__dict__.update(stato)
            self._decora(totale)
            super().showPage()
        super().save()

    def _decora(self, totale: int):
        w, h = A4
        self.setStrokeColor(ORO)
        self.setLineWidth(1.2)
        self.line(18 * mm, h - 14 * mm, w - 18 * mm, h - 14 * mm)
        self.setFont(FONT_B, 8.5)
        self.setFillColor(MARRONE)
        self.drawString(18 * mm, h - 12 * mm, AGENZIA)
        self.setFont(FONT, 8.5)
        self.setFillColor(GRIGIO)
        self.drawRightString(w - 18 * mm, h - 12 * mm, self._testata[:90])
        self.setLineWidth(0.4)
        self.line(18 * mm, 13 * mm, w - 18 * mm, 13 * mm)
        self.setFont(FONT, 7.5)
        self.drawString(18 * mm, 9 * mm,
                        f"Generata il {datetime.now():%d/%m/%Y %H:%M} con lettura automatica dei documenti: "
                        "verificare sempre sugli originali.")
        self.drawRightString(w - 18 * mm, 9 * mm, f"Pagina {self._pageNumber} di {totale}")


def _tabella(righe: list[list], larghezze: list[float], intestazione: bool = True) -> Table:
    t = Table(righe, colWidths=larghezze, repeatRows=1 if intestazione else 0, hAlign="LEFT")
    stile = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#ddd6ca")),
    ]
    if intestazione:
        stile += [("BACKGROUND", (0, 0), (-1, 0), ORO)]
    t.setStyle(TableStyle(stile))
    return t


def _schede(coppie: list[tuple[str, str]], larghezza: float) -> Table:
    """Tabella a due colonne etichetta / valore."""
    righe = [[_p(k, S_CELLA_B), _p(v if v else _vuoto(), S_CELLA)] for k, v in coppie]
    t = Table(righe, colWidths=[45 * mm, larghezza - 45 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), ORO_CHIARO),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#ddd6ca")),
    ]))
    return t


def _riquadro(contenuto: list, sfondo, bordo, larghezza: float) -> Table:
    t = Table([[contenuto]], colWidths=[larghezza], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), sfondo),
        ("LINEBEFORE", (0, 0), (0, -1), 3, bordo),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


# ------------------------------------------------------------------ contenuto

def _persona_nascita(p: dict) -> str:
    if p.get("sede"):
        return f"sede in {p['sede']}"
    luogo = p.get("luogo_nascita", "")
    if p.get("prov_nascita") and "(" not in luogo:
        luogo += f" ({p['prov_nascita']})"
    if luogo or p.get("data_nascita"):
        return f"{luogo} il {p.get('data_nascita', '')}".strip()
    return ""


TEMI = {"urbanistica": "Urbanistica", "provenienza": "Provenienza", "vincoli": "Vincoli e gravami", "documenti": "Documento"}
COLORE_LIVELLO = {"errore": "#b3261e", "attenzione": "#8a5a00", "info": "#6b6b6b"}
GRAVITA = {"alta": ("PUÒ LIMITARE LA VENDITA", ROSSO), "media": ("DA VERIFICARE", colors.HexColor("#8a5a00")),
           "info": ("DA CONOSCERE", GRIGIO)}


def _estremi_titolo(t: dict) -> str:
    parti = []
    if t.get("defunto"):
        parti.append(f"in morte di {t['defunto']}" + (f" (deceduto il {t['data_decesso']})" if t.get("data_decesso") else ""))
    if t.get("notaio"):
        parti.append(f"notaio {t['notaio']}")
    if t.get("data") and t["data"] not in (t.get("registrazione", "") + t.get("trascrizione", "")):
        parti.append(f"del {t['data']}")
    if t.get("repertorio"):
        parti.append(f"rep. n. {t['repertorio']}")
    if t.get("registrazione"):
        parti.append(f"registrato {t['registrazione']}")
    if t.get("trascrizione"):
        parti.append(f"trascritto {t['trascrizione']}")
    return ", ".join(parti)


def genera(nome: str, s: dict, destinazione: Path) -> Path:
    larg = A4[0] - 36 * mm
    atto = s.get("atto") or {}
    storia: list = []

    storia.append(Paragraph("Sintesi dell'atto di provenienza", S_TITOLO))
    sotto = escape(nome)
    if atto.get("comune") or atto.get("indirizzo"):
        sotto += " · " + escape(", ".join(x for x in (atto.get("indirizzo"), atto.get("comune")) if x))
    storia.append(Paragraph(sotto, S_SOTTO))

    # ---------------------------------------------------------------- punti di attenzione
    avvisi = s.get("avvisi", [])
    gravi = [a for a in avvisi if a["livello"] == "errore"]
    contenuto = [Paragraph("<b>Punti di attenzione</b>", S_TESTO), Spacer(1, 3)]
    if avvisi:
        for a in avvisi:
            tema = TEMI.get(a.get("tema", ""), "")
            contenuto.append(Paragraph(
                f'<font color="{COLORE_LIVELLO.get(a["livello"], "#8a5a00")}">■</font> '
                + (f"<b>{escape(tema)}</b> – " if tema else "") + escape(a["testo"]), S_TESTO))
            contenuto.append(Spacer(1, 2))
    else:
        contenuto.append(Paragraph('<font color="#2e7d32">Nessun punto critico rilevato automaticamente.</font> '
                                   "Rileggere comunque l'atto integrale.", S_TESTO))
    storia.append(_riquadro(contenuto, ROSSO_CHIARO if gravi else ARANCIO_CHIARO if avvisi else colors.HexColor("#eaf4ea"),
                            ROSSO if gravi else ORO if avvisi else VERDE, larg))

    # ---------------------------------------------------------------- 1. atto e parti
    storia.append(Paragraph("1. Estremi dell'atto e parti", S_H1))
    notaio = atto.get("notaio", "")
    if notaio and atto.get("notaio_sede"):
        notaio += f", notaio in {atto['notaio_sede']}"
    coppie = [
        ("Atto", " – ".join(x for x in ((atto.get("tipo_atto") or "").capitalize(), notaio,
                                         f"del {atto['data_atto']}" if atto.get("data_atto") else "") if x)),
        ("Repertorio / Raccolta", " / ".join(x for x in (f"n. {atto['repertorio']}" if atto.get("repertorio") else "",
                                                          f"n. {atto['raccolta']}" if atto.get("raccolta") else "") if x)),
        ("Registrazione", atto.get("registrazione", "")),
        ("Trascrizione", atto.get("trascrizione", "")),
    ]
    if atto.get("prezzo"):
        coppie.append(("Prezzo dichiarato", f"Euro {atto['prezzo']}"))
    coppie += [("Immobile", ", ".join(x for x in (atto.get("comune"), atto.get("indirizzo")) if x)),
               ("Descrizione", atto.get("descrizione", ""))]
    storia.append(_schede(coppie, larg))

    def tabella_persone(titolo: str, persone: list[dict]):
        storia.append(Paragraph(titolo, S_H2))
        righe = [[_p("Nominativo", S_INT), _p("Codice fiscale", S_INT), _p("Nascita", S_INT), _p("Residenza e stato civile", S_INT)]]
        for c in persone:
            res = c.get("residenza", "")
            if c.get("stato_civile"):
                res += ("\n" if res else "") + c["stato_civile"]
            righe.append([_p(c["nominativo"], S_CELLA_B), _p(c.get("codice_fiscale"), S_CELLA),
                          _p(_persona_nascita(c), S_CELLA), _p(res, S_CELLA)])
        storia.append(_tabella(righe, [46 * mm, 36 * mm, 38 * mm, larg - 120 * mm]))

    if atto.get("intestatari"):
        tabella_persone("Parte acquirente (attuali proprietari)", atto["intestatari"])
    elif atto.get("intestatari_testo"):
        storia.append(_pb("Parte acquirente:", atto["intestatari_testo"]))
    if atto.get("cedenti"):
        tabella_persone("Parte venditrice / dante causa", atto["cedenti"])
    if not atto.get("intestatari") and not atto.get("intestatari_testo"):
        storia.append(_p(_vuoto("parti non riconosciute: verificare l'atto")))

    unita = atto.get("catastali", [])
    if unita:
        storia.append(Paragraph("Dati catastali indicati nell'atto", S_H2))
        righe = [[_p(x, S_INT) for x in ("Sez.", "Foglio", "Part.", "Sub", "Cat.", "Classe", "Consistenza", "Rendita €", "Piano")]]
        for u in unita:
            righe.append([_p(u.get(k, ""), S_CELLA) for k in ("sezione", "foglio", "particella", "sub", "categoria", "classe",
                                                               "consistenza", "rendita", "piano")])
        storia.append(_tabella(righe, [12 * mm, 15 * mm, 15 * mm, 12 * mm, 14 * mm, 14 * mm, 24 * mm, 20 * mm, larg - 126 * mm]))

    # ---------------------------------------------------------------- 2. urbanistica
    storia.append(Paragraph("2. Situazione urbanistica", S_H1))
    if atto.get("ante_67"):
        storia.append(Paragraph("<b>Costruzione iniziata in data anteriore al 1° settembre 1967</b> "
                                "(dichiarazione della parte venditrice).", S_TESTO))
        storia.append(Spacer(1, 3))
    titoli = atto.get("titoli_edilizi", [])
    if titoli:
        storia.append(Paragraph("Titoli edilizi citati", S_H2))
        righe = [[_p("Titolo", S_INT), _p("Numero", S_INT), _p("Data", S_INT), _p("Testo nell'atto", S_INT)]]
        for ti in titoli:
            righe.append([_p(ti["tipo"], S_CELLA_B), _p(ti["numero"] or "–", S_CELLA), _p(ti["data"] or "–", S_CELLA),
                          _p(ti["testo"], ParagraphStyle("c7", parent=S_CELLA, fontSize=7.5, leading=9.5))])
        storia.append(_tabella(righe, [36 * mm, 22 * mm, 21 * mm, larg - 79 * mm]))
    elif not atto.get("ante_67"):
        storia.append(_p(_vuoto("nessun titolo edilizio riconosciuto")))
    storia.append(Paragraph("Agibilità / abitabilità", S_H2))
    storia.append(_p(atto.get("agibilita_testo") or _vuoto("non citata nell'atto")))
    for n in atto.get("note_urbanistiche", []):
        storia.append(Paragraph(escape(n["tema"]), S_H2))
        for f in n["frasi"]:
            storia.append(Paragraph("“" + escape(f) + "”", S_CITAZIONE))
    if atto.get("urbanistica_testo"):
        storia.append(Paragraph("Dichiarazione urbanistica (testo integrale)", S_H2))
        storia.append(_p(atto["urbanistica_testo"], S_CITAZIONE))

    # ---------------------------------------------------------------- 3. provenienza precedente
    intestazione_prov = Paragraph("3. Provenienza precedente", S_H1)
    prov = atto.get("provenienza_precedente") or {}
    if prov.get("titoli"):
        righe = [[_p("Titolo", S_INT), _p("Estremi", S_INT)]]
        for t in prov["titoli"]:
            righe.append([_p(t["tipo"].capitalize(), S_CELLA_B), _p(_estremi_titolo(t) or _vuoto("estremi non rilevati"), S_CELLA)])
        storia.append(KeepTogether([intestazione_prov,
                                    Paragraph("Come la parte venditrice era diventata proprietaria (dal più recente):", S_TESTO),
                                    Spacer(1, 3), _tabella(righe, [40 * mm, larg - 40 * mm])]))
    else:
        storia.append(intestazione_prov)
    if prov.get("testo"):
        storia.append(Paragraph("Testo dell'atto", S_H2))
        for b in prov["testo"]:
            storia.append(Paragraph("“" + escape(b) + "”", S_CITAZIONE))
    else:
        storia.append(_p(_vuoto("provenienza precedente non trovata nell'atto")))

    # ---------------------------------------------------------------- 4. vincoli e gravami
    storia.append(Paragraph("4. Vincoli e gravami che possono limitare la circolazione", S_H1))
    vincoli = atto.get("vincoli") or {}
    trovati = sorted(vincoli.get("trovati", []), key=lambda v: ["alta", "media", "info"].index(v["gravita"]))
    if trovati:
        for v in trovati:
            etichetta, colore = GRAVITA.get(v["gravita"], GRAVITA["media"])
            testata = Paragraph(f'{escape(v["categoria"])} &nbsp;<font size="7" color="{colore.hexval().replace("0x", "#")}">'
                                f"[{etichetta}]</font>", S_H2)
            blocco = [testata, Paragraph(f"<i>{escape(v['nota'])}</i>", S_PICCOLO), Spacer(1, 2)]
            frasi = [Paragraph("“" + escape(f) + "”", S_CITAZIONE) for f in v["frasi"]]
            storia.append(KeepTogether(blocco + frasi[:1]))
            storia.extend(frasi[1:])
    else:
        storia.append(_p("Nessun vincolo o gravame particolare individuato nell'atto."))
    if vincoli.get("negative"):
        storia.append(Paragraph("Dichiarazioni di assenza di vincoli", S_H2))
        for f in vincoli["negative"]:
            storia.append(Paragraph("“" + escape(f) + "”", S_CITAZIONE))
    if vincoli.get("di_rito"):
        storia.append(Spacer(1, 3))
        storia.append(_p("Presenti le consuete formule di rito (garanzia di libertà da pesi, ipoteche e trascrizioni "
                         "pregiudizievoli; servitù attive e passive se e come esistenti) per: "
                         + ", ".join(vincoli["di_rito"]).lower() + ".", S_PICCOLO))
    storia.append(Spacer(1, 3))
    storia.append(_p("Vincoli e gravami sono individuati per parole chiave nel testo dell'atto: rileggere comunque l'atto "
                     "integrale e verificare la situazione attuale con visure e ispezioni ipotecarie aggiornate.", S_PICCOLO))

    # ---------------------------------------------------------------- documenti
    righe = [[_p("File", S_INT), _p("Lettura", S_INT), _p("Atto", S_INT)]]
    for a in s.get("atti", []):
        righe.append([_p(a.get("_file"), S_CELLA), _p(a.get("_metodo"), S_CELLA),
                      _p(f"{(a.get('tipo_atto') or '').capitalize()} {a.get('data_atto', '')}".strip()
                         + (" (analizzato)" if a is atto else ""), S_CELLA)])
    storia.append(KeepTogether([Paragraph("Documenti analizzati", S_H1),
                                _tabella(righe, [80 * mm, 28 * mm, larg - 108 * mm])]))

    destinazione.parent.mkdir(parents=True, exist_ok=True)
    tmp = destinazione.with_name(destinazione.stem + ".tmp.pdf")
    doc = SimpleDocTemplate(str(tmp), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=20 * mm, bottomMargin=18 * mm,
                            title=f"Sintesi - {nome}", author=AGENZIA, subject="Sintesi dell'atto di provenienza")
    testata = f"Sintesi atto di provenienza · {nome}"
    doc.build(storia, canvasmaker=lambda *a, **k: _CanvasNumerato(*a, testata=testata, **k))
    try:
        tmp.replace(destinazione)
    except PermissionError:
        # PDF aperto su un altro PC: si salva con un nome diverso
        destinazione = destinazione.with_name(f"{destinazione.stem} ({datetime.now():%H%M%S}).pdf")
        tmp.replace(destinazione)
    return destinazione
