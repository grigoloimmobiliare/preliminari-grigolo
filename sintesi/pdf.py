"""Generazione del PDF di sintesi con ReportLab."""

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


def genera(nome: str, s: dict, destinazione: Path) -> Path:
    larg = A4[0] - 36 * mm
    atto = s.get("atto") or {}
    storia: list = []

    storia.append(Paragraph("Sintesi atto di provenienza e visure catastali", S_TITOLO))
    sotto = escape(nome)
    if atto.get("comune") or atto.get("indirizzo"):
        sotto += " · " + escape(", ".join(x for x in (atto.get("indirizzo"), atto.get("comune")) if x))
    storia.append(Paragraph(sotto, S_SOTTO))

    # ---------------------------------------------------------------- avvisi
    avvisi = s.get("avvisi", [])
    if avvisi:
        gravi = [a for a in avvisi if a["livello"] == "errore"]
        altri = [a for a in avvisi if a["livello"] != "errore"]
        contenuto = [Paragraph("<b>Punti da verificare</b>", S_TESTO), Spacer(1, 3)]
        for a in gravi + altri:
            colore = "#b3261e" if a["livello"] == "errore" else ("#6b6b6b" if a["livello"] == "info" else "#8a5a00")
            contenuto.append(Paragraph(f'<font color="{colore}">■</font> {escape(a["testo"])}', S_TESTO))
            contenuto.append(Spacer(1, 2))
        storia.append(_riquadro(contenuto, ROSSO_CHIARO if gravi else ARANCIO_CHIARO, ROSSO if gravi else ORO, larg))

    # ---------------------------------------------------------------- 1. proprietari
    storia.append(Paragraph("1. Proprietari attuali", S_H1))
    proprietari = s.get("proprietari", [])
    acquirenti = s.get("acquirenti", [])
    if proprietari:
        storia.append(Paragraph("Intestati catastali risultanti dalla visura", S_H2))
        righe = [[_p("Nominativo", S_INT), _p("Codice fiscale", S_INT), _p("Nascita / sede", S_INT), _p("Diritto e quota", S_INT)]]
        for p in proprietari:
            righe.append([_p(p["nominativo"], S_CELLA_B), _p(p.get("codice_fiscale"), S_CELLA),
                          _p(_persona_nascita(p), S_CELLA), _p("\n".join(p.get("diritti") or [p.get("diritto", "")]), S_CELLA)])
        storia.append(_tabella(righe, [48 * mm, 36 * mm, 46 * mm, larg - 130 * mm]))
    if acquirenti:
        storia.append(Paragraph("Acquirenti nell'atto di provenienza", S_H2))
        righe = [[_p("Nominativo", S_INT), _p("Codice fiscale", S_INT), _p("Nascita", S_INT), _p("Residenza e stato civile", S_INT)]]
        for c in acquirenti:
            res = c.get("residenza", "")
            if c.get("stato_civile"):
                res += ("\n" if res else "") + c["stato_civile"]
            righe.append([_p(c["nominativo"], S_CELLA_B), _p(c.get("codice_fiscale"), S_CELLA),
                          _p(_persona_nascita(c), S_CELLA), _p(res, S_CELLA)])
        storia.append(_tabella(righe, [48 * mm, 36 * mm, 40 * mm, larg - 124 * mm]))
    elif atto.get("intestatari_testo"):
        storia.append(_pb("Acquirenti nell'atto:", atto["intestatari_testo"]))
    if s.get("coincidono") is True:
        storia.append(Spacer(1, 3))
        storia.append(Paragraph('<font color="#2e7d32"><b>Gli intestati catastali coincidono con gli acquirenti '
                                "dell'atto di provenienza.</b></font>", S_TESTO))
    elif s.get("coincidono") is False:
        storia.append(Spacer(1, 3))
        storia.append(Paragraph('<font color="#b3261e"><b>Gli intestati catastali NON coincidono con gli acquirenti '
                                "dell'atto di provenienza</b></font> (vedi punti da verificare).", S_TESTO))
    for succ in s.get("successioni", []):
        storia.append(_pb("Successione in visura:", succ.get("testo", ""), S_PICCOLO))
    if not proprietari and not acquirenti:
        storia.append(_p(_vuoto("nessun proprietario riconosciuto: verificare i documenti")))

    # ---------------------------------------------------------------- 2. immobile e catasto
    storia.append(Paragraph("2. Immobile e dati catastali", S_H1))
    coppie = [("Comune", " ".join(x for x in (atto.get("comune") or (s["unita"][0].get("comune") if s.get("unita") else ""),
                                               f"({atto['prov']})" if atto.get("prov") else "") if x)),
              ("Indirizzo (atto)", atto.get("indirizzo", "")),
              ("Descrizione (atto)", atto.get("descrizione", ""))]
    storia.append(_schede(coppie, larg))
    unita = s.get("unita", [])
    if unita:
        fonte = "visura" if any(u.get("fonte") == "visura" for u in unita) else "atto"
        storia.append(Paragraph(f"Unità immobiliari (Catasto Fabbricati, da {fonte})", S_H2))
        righe = [[_p(x, S_INT) for x in ("Sez.", "Fg.", "Part.", "Sub", "Cat.", "Cl.", "Consist.", "Sup. mq", "Rendita €", "Indirizzo e piano")]]
        for u in unita:
            ind = u.get("indirizzo", "")
            if u.get("piano"):
                ind += f" – piano {u['piano']}" if ind else f"piano {u['piano']}"
            righe.append([_p(u.get(k, ""), S_CELLA) for k in ("sezione", "foglio", "particella", "sub", "categoria", "classe",
                                                               "consistenza", "superficie", "rendita")] + [_p(ind, S_CELLA)])
        storia.append(_tabella(righe, [10 * mm, 10 * mm, 13 * mm, 10 * mm, 12 * mm, 9 * mm, 18 * mm, 15 * mm, 18 * mm,
                                       larg - 115 * mm]))
    else:
        storia.append(_p(_vuoto("dati catastali non rilevati")))

    # ---------------------------------------------------------------- 3. urbanistica
    storia.append(Paragraph("3. Situazione urbanistica", S_H1))
    if atto.get("ante_67"):
        storia.append(Paragraph("<b>Costruzione iniziata in data anteriore al 1° settembre 1967</b> "
                                "(dichiarazione della parte venditrice nell'atto).", S_TESTO))
        storia.append(Spacer(1, 3))
    titoli = atto.get("titoli_edilizi", [])
    if titoli:
        storia.append(Paragraph("Titoli edilizi citati nell'atto", S_H2))
        righe = [[_p("Titolo", S_INT), _p("Numero", S_INT), _p("Data", S_INT), _p("Testo nell'atto", S_INT)]]
        for ti in titoli:
            righe.append([_p(ti["tipo"], S_CELLA_B), _p(ti["numero"] or "–", S_CELLA), _p(ti["data"] or "–", S_CELLA),
                          _p(ti["testo"], ParagraphStyle("c7", parent=S_CELLA, fontSize=7.5, leading=9.5))])
        storia.append(_tabella(righe, [36 * mm, 22 * mm, 21 * mm, larg - 79 * mm]))
    elif not atto.get("ante_67"):
        storia.append(_p(_vuoto("nessun titolo edilizio riconosciuto: verificare la dichiarazione urbanistica")))
    storia.append(Paragraph("Agibilità / abitabilità", S_H2))
    storia.append(_p(atto.get("agibilita_testo") or _vuoto("non citata nell'atto")))
    if atto.get("urbanistica_testo"):
        storia.append(Paragraph("Dichiarazione urbanistica dell'atto (testo integrale)", S_H2))
        storia.append(_p(atto["urbanistica_testo"], S_CITAZIONE))

    # ---------------------------------------------------------------- 4. provenienza
    storia.append(Paragraph("4. Estremi dell'atto di provenienza", S_H1))
    notaio = atto.get("notaio", "")
    if notaio and atto.get("notaio_sede"):
        notaio += f", notaio in {atto['notaio_sede']}"
    cedenti = "; ".join(c["nominativo"] + (f" (C.F. {c['codice_fiscale']})" if c.get("codice_fiscale") else "")
                        for c in atto.get("cedenti", []))
    coppie = [
        ("Tipo di atto", (atto.get("tipo_atto") or "").capitalize()),
        ("Notaio", notaio),
        ("Data", atto.get("data_atto", "")),
        ("Repertorio / Raccolta", " / ".join(x for x in (f"n. {atto['repertorio']}" if atto.get("repertorio") else "",
                                                          f"n. {atto['raccolta']}" if atto.get("raccolta") else "") if x)),
        ("Registrazione", atto.get("registrazione", "")),
        ("Trascrizione", atto.get("trascrizione", "")),
        ("Parte cedente", cedenti),
    ]
    if atto.get("prezzo"):
        coppie.append(("Prezzo dichiarato", f"Euro {atto['prezzo']}"))
    if atto.get("prima_casa"):
        coppie.append(("Agevolazioni", "acquisto con agevolazioni \"prima casa\""))
    for v in s.get("visure", []):
        if v.get("derivanti_da"):
            coppie.append((f"In visura ({v.get('_file', '')})", "dati derivanti da: " + v["derivanti_da"]))
    storia.append(_schede(coppie, larg))

    # ---------------------------------------------------------------- 5. clausole
    storia.append(Paragraph("5. Clausole particolari", S_H1))
    clausole = dict(atto.get("clausole") or {})
    rito = clausole.pop("_formule_di_rito", [])
    if clausole:
        for categoria, frasi in clausole.items():
            blocco = [Paragraph(escape(categoria), S_H2)]
            for f in frasi:
                blocco.append(Paragraph("“" + escape(f) + "”", S_CITAZIONE))
            storia.append(KeepTogether(blocco[:2]))
            storia.extend(blocco[2:])
    else:
        storia.append(_p("Nessuna clausola particolare individuata nell'atto."))
    if rito:
        storia.append(Spacer(1, 4))
        storia.append(_p("Presenti le consuete formule di rito (garanzia di libertà da pesi, ipoteche e trascrizioni "
                         "pregiudizievoli; servitù attive e passive se e come esistenti): " + ", ".join(rito).lower() + ".",
                         S_PICCOLO))
    storia.append(Spacer(1, 3))
    storia.append(_p("Le clausole sono individuate per parole chiave: rileggere comunque l'atto integrale.", S_PICCOLO))

    # ---------------------------------------------------------------- 6. documenti
    righe = [[_p("Documento", S_INT), _p("File", S_INT), _p("Lettura", S_INT), _p("Note", S_INT)]]
    for a in s.get("atti", []):
        righe.append([_p("Atto", S_CELLA), _p(a.get("_file"), S_CELLA), _p(a.get("_metodo"), S_CELLA),
                      _p(f"{(a.get('tipo_atto') or '').capitalize()} {a.get('data_atto', '')}".strip(), S_CELLA)])
    for v in s.get("visure", []):
        righe.append([_p("Visura", S_CELLA), _p(v.get("_file"), S_CELLA), _p(v.get("_metodo"), S_CELLA),
                      _p(f"visura {v.get('tipo', '')}" + (f" al {v['data']}" if v.get("data") else ""), S_CELLA)])
    storia.append(KeepTogether([Paragraph("6. Documenti analizzati", S_H1),
                                _tabella(righe, [24 * mm, 68 * mm, 25 * mm, larg - 117 * mm])]))

    destinazione.parent.mkdir(parents=True, exist_ok=True)
    tmp = destinazione.with_suffix(".tmp.pdf")
    doc = SimpleDocTemplate(str(tmp), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=20 * mm, bottomMargin=18 * mm,
                            title=f"Sintesi - {nome}", author=AGENZIA, subject="Sintesi atto di provenienza e visure")
    testata = f"Sintesi immobile · {nome}"
    doc.build(storia, canvasmaker=lambda *a, **k: _CanvasNumerato(*a, testata=testata, **k))
    try:
        tmp.replace(destinazione)
    except PermissionError:
        # PDF aperto su un altro PC: si salva con un nome diverso
        destinazione = destinazione.with_name(f"{destinazione.stem} ({datetime.now():%H%M%S}).pdf")
        tmp.replace(destinazione)
    return destinazione

