from docx import Document
from docx.oxml.ns import qn

from app import excel, immagini, word
from conftest import RADICE, immagine

MODELLO = RADICE / "modelli" / "valutazione_modello.docx"


def _testo(doc):
    return "\n".join(p.text for p in doc.paragraphs)


def test_compilazione_completa(tmp_path, excel_compilato, carta_pdf):
    d = excel.leggi(excel_compilato)
    omi = [immagine(tmp_path / "omi1.png"), immagine(tmp_path / "omi2.png")]
    comp = [immagine(tmp_path / "comp.png", 900, 1200)]
    carta = immagini.carta_intestata_png(carta_pdf, tmp_path / "carta.png")
    out = tmp_path / "out.docx"
    r = word.compila(MODELLO, d, out, oggi="01/10/2026", immagini_omi=omi, immagini_comparabili=comp,
                     carta_intestata=carta)
    assert r["mancanti"] == [] and r["avvisi"] == []
    doc = Document(str(out))
    t = _testo(doc)
    assert "[" not in t
    assert "Sig. Mario Rossi" in t and "Treviso (TV), lì 30/09/2026" in t
    for riga in ("Soggiorno: mq 30,5", "Camera 2: mq 11", "per un totale di mq 75,5",
                 "Garage per un totale di 18 mq calcolati per intero",
                 "Terrazzi/Poggioli per un totale di 9 mq calcolati ad 1/3",
                 "- Posizione centrale", "- Assenza di ascensore", "indice di vetustà del 30%"):
        assert riga in t, riga
    assert "Salotto" not in t and "Tinello" not in t
    # immagini: 3 nel corpo, dopo i rispettivi titoli (che restano)
    paragrafi = doc.paragraphs
    titoli = [p.text for p in paragrafi]
    i_omi, i_comp = titoli.index("Valori OMI"), titoli.index("Valori di Comparazione")
    con_img = [i for i, p in enumerate(paragrafi) if p._p.findall(".//" + qn("w:drawing"))]
    assert con_img == [i_omi + 1, i_omi + 2, i_comp + 1]
    # carta intestata dietro al testo, a tutta pagina
    ancore = doc.sections[0].header._element.findall(".//" + qn("wp:anchor"))
    assert len(ancore) == 1 and ancore[0].get("behindDoc") == "1"


def test_dati_mancanti_evidenziati(tmp_path):
    from conftest import RADICE as R
    d = excel.leggi(R / "modelli" / "stima_modello.xlsx")    # Excel vuoto
    out = tmp_path / "out.docx"
    r = word.compila(MODELLO, d, out, oggi="01/10/2026", immagini_omi=[], immagini_comparabili=[],
                     carta_intestata=None)
    assert "CLIENTE" in r["mancanti"] and "INDIRIZZO" in r["mancanti"]
    doc = Document(str(out))
    evidenziati = [r.text for p in doc.paragraphs for r in p.runs
                   if r._r.find(qn("w:rPr")) is not None and r._r.find(qn("w:rPr")).find(qn("w:highlight")) is not None]
    assert "[CLIENTE]" in evidenziati and "[VALORI OMI]" in evidenziati
    assert "Treviso (TV), lì 01/10/2026" in _testo(doc)


def test_segnaposto_spezzato_su_piu_run(tmp_path, excel_compilato):
    doc = Document()
    p = doc.add_paragraph()
    for pezzo in ("Cliente: [", "CLIEN", "TE] fine", " e [ZONA OMI]."):
        p.add_run(pezzo).bold = pezzo.startswith("CLIEN")
    doc.save(tmp_path / "m.docx")
    d = excel.leggi(excel_compilato)
    word.compila(tmp_path / "m.docx", d, tmp_path / "o.docx", oggi="", immagini_omi=[],
                 immagini_comparabili=[], carta_intestata=None)
    assert Document(str(tmp_path / "o.docx")).paragraphs[0].text == "Cliente: Sig. Mario Rossi fine e B1."
