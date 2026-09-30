"""Prepara il modello della valutazione a partire dalla bozza Word dell'agenzia.

Uso:  python strumenti/crea_modello.py VALUTAZIONE_TIPO.docx modelli/valutazione_modello.docx

La bozza ha già i dati tra parentesi quadre ([CLIENTE], [VALORE MQ], ...). Qui si
aggiungono i segnaposto per le parti che cambiano numero di righe:
- elenco dei vani (Soggiorno, Cucina, ...)       -> "[VANO]: mq [MQ VANO]"
- pertinenze (terrazza, garage, ...) nei due punti in cui compaiono
- principi di unicità e criticità
- "Valori OMI" (titolo nuovo) e le immagini dei valori OMI e dei comparabili.
Formattazione (carattere, grassetti, rientri, tabulazioni) ripresa dai paragrafi della bozza.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.excel import norm  # noqa: E402


def testo(p) -> str:
    return "".join(t.text or "" for t in p.iter(qn("w:t")))


def runs(p):
    return p.findall(qn("w:r"))


def run_con(p, indice_run, t: str):
    """Copia del run n. `indice_run` del paragrafo, con il testo `t`."""
    r = copy.deepcopy(runs(p)[indice_run])
    for figlio in list(r):
        if figlio.tag != qn("w:rPr"):
            r.remove(figlio)
    el = r.makeelement(qn("w:t"), {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
    el.text = t
    r.append(el)
    return r


def riscrivi(p, pezzi):
    """pezzi: lista di (indice del run da cui copiare il formato, testo)."""
    nuovi = [run_con(p, i, t) for i, t in pezzi]
    for figlio in list(p):
        if figlio.tag != qn("w:pPr"):
            p.remove(figlio)
    for r in nuovi:
        p.append(r)


def pulisci_copia(p):
    """Toglie da un paragrafo copiato segnalibri e identificativi, che devono essere unici."""
    for tag in ("w:bookmarkStart", "w:bookmarkEnd", "w:proofErr"):
        for x in list(p.iter(qn(tag))):
            x.getparent().remove(x)
    for att in list(p.attrib):
        if att.endswith("}paraId") or att.endswith("}textId"):
            del p.attrib[att]
    return p


def sostituisci_testo(p, vecchio: str, nuovo: str) -> None:
    """Sostituzione anche quando Word ha spezzato il testo su più run (resta il formato del primo)."""
    testi = list(p.iter(qn("w:t")))
    pieno = "".join(t.text or "" for t in testi)
    i = pieno.find(vecchio)
    if i < 0:
        raise SystemExit(f"Testo non trovato: {vecchio!r}")
    fine, pos = i + len(vecchio), 0
    for t in testi:
        n = len(t.text or "")
        a, b = max(i - pos, 0), min(fine - pos, n)
        if a < b:
            t.text = t.text[:a] + (nuovo if pos <= i < pos + n else "") + t.text[b:]
        pos += n


def trova(paragrafi, inizio: str, dopo=None):
    start = 0 if dopo is None else paragrafi.index(dopo) + 1
    for p in paragrafi[start:]:
        if norm(testo(p)).startswith(norm(inizio)):
            return p
    raise SystemExit(f"Paragrafo non trovato nella bozza: {inizio!r}")


def rimuovi(p):
    p.getparent().remove(p)


def main(bozza: Path, uscita: Path) -> None:
    doc = Document(str(bozza))
    P = list(doc.element.body.iter(qn("w:p")))

    # --- principi di unicità / criticità: il paragrafo vuoto sotto il titolo diventa l'elenco
    for titolo, segnaposto in (("Principi di unicità", "[PRINCIPIO DI UNICITA]"), ("Criticità", "[CRITICITA]")):
        t = trova(P, titolo)
        vuoto = t.getnext()
        riga = pulisci_copia(copy.deepcopy(t))
        riscrivi(riga, [(0, "- " + segnaposto)])
        rpr = riga.find(qn("w:r")).find(qn("w:rPr"))
        for tag in ("w:b", "w:u"):
            for x in rpr.findall(qn(tag)):
                rpr.remove(x)
        if vuoto is not None and not testo(vuoto).strip():
            vuoto.addprevious(riga)
        else:
            t.addnext(riga)

    # --- elenco dei vani: il primo vano fa da modello, gli altri si tolgono
    tipologia = trova(P, "[TIPOLOGIA]")
    totale = trova(P, "per un totale di mq", dopo=tipologia)
    vani = []
    x = tipologia.getnext()
    while x is not None and x is not totale:
        vani.append(x)
        x = x.getnext()
    primo = next(v for v in vani if testo(v).strip())
    base = copy.deepcopy(runs(primo)[0])
    riscrivi(primo, [(0, "[VANO]")])
    normale = copy.deepcopy(runs(primo)[0])
    rpr = normale.find(qn("w:rPr"))
    for x in rpr.findall(qn("w:b")):
        rpr.remove(x)
    normale.find(qn("w:t")).text = ": mq "
    mq = copy.deepcopy(base)
    mq.find(qn("w:t")).text = "[MQ VANO]"
    primo.append(normale)
    primo.append(mq)
    for v in vani:
        if v is not primo:
            rimuovi(v)

    # --- pertinenze (descrizione): "Terrazza per un totale di __ mq ..." fa da modello
    P = list(doc.element.body.iter(qn("w:p")))
    terrazza = trova(P, "Terrazza per un totale")
    riscrivi(terrazza, [(0, "[PERTINENZA]"), (2, " per un totale di "), (4, "[MQ PERTINENZA]"),
                        (2, " mq calcolati [QUOTA PERTINENZA] sul valore di mercato;")])
    garage = trova(P, "garage: per un totale", dopo=terrazza)
    rimuovi(garage)

    # --- pertinenze (calcolo): "- terrazze di __ mq" + "ad 1/3 di [VALORE MQ] €/mq ... €"
    P = list(doc.element.body.iter(qn("w:p")))
    t1 = trova(P, "- terrazze di")
    t2 = t1.getnext()
    riscrivi(t1, [(0, "- "), (1, "[PERTINENZA]"), (3, " di "), (3, "[MQ PERTINENZA]"), (3, " mq")])
    # riga del valore: si tiene la struttura a tabulazioni della riga dell'abitazione
    abit = trova(P, "a [VALORE MQ]")
    nuova = pulisci_copia(copy.deepcopy(abit))
    ppr_t2 = t2.find(qn("w:pPr"))
    if ppr_t2 is not None:
        vecchio = nuova.find(qn("w:pPr"))
        if vecchio is not None:
            nuova.remove(vecchio)
        nuova.insert(0, copy.deepcopy(ppr_t2))
    t2.addprevious(nuova)
    rimuovi(t2)
    sostituisci_testo(nuova, "[VALORE MQ]", "[VALORE MQ PERTINENZA]")
    sostituisci_testo(nuova, "[TOT VALORE TIPOLOGIA]", "[VALORE PERTINENZA]")
    for t in nuova.iter(qn("w:t")):
        if (t.text or "").strip() == "a":
            t.text = t.text.replace("a", "[QUOTA PERTINENZA DI]")
            break
    # "garage" nel calcolo: coperto dalla ripetizione delle pertinenze
    P = list(doc.element.body.iter(qn("w:p")))
    g1 = trova(P, "- garage", dopo=t1)
    g2 = g1.getnext()
    rimuovi(g1)
    rimuovi(g2)

    # --- Valori OMI e comparabili
    P = list(doc.element.body.iter(qn("w:p")))
    comp = trova(P, "Valori di Comparazione")
    titolo_omi = pulisci_copia(copy.deepcopy(comp))
    for t in titolo_omi.iter(qn("w:t")):
        t.text = ""
    next(titolo_omi.iter(qn("w:t"))).text = "Valori OMI"
    omi = copy.deepcopy(titolo_omi)
    next(omi.iter(qn("w:t"))).text = "[VALORI OMI]"
    for x in omi.iter(qn("w:rPr")):
        for tag in ("w:b", "w:u"):
            for y in x.findall(qn(tag)):
                x.remove(y)
    # la tabella OMI va dopo la metratura commerciale (pertinenze) e prima dei calcoli:
    # le righe vuote che nella bozza spingevano i calcoli alla pagina dopo diventano un salto pagina
    P = list(doc.element.body.iter(qn("w:p")))
    pertinenze = trova(P, "[PERTINENZA] per un totale")
    calcoli = trova(P, "Per cui andiamo a dare un valore", dopo=pertinenze)
    x = pertinenze.getnext()
    while x is not None and x is not calcoli:
        succ = x.getnext()
        if x.tag == qn("w:p") and not testo(x).strip():
            rimuovi(x)
        x = succ
    spazio = pulisci_copia(copy.deepcopy(pertinenze))
    for figlio in list(spazio):
        if figlio.tag != qn("w:pPr"):
            spazio.remove(figlio)
    pertinenze.addnext(spazio)
    spazio.addnext(titolo_omi)
    titolo_omi.addnext(omi)
    ppr = calcoli.find(qn("w:pPr"))
    if ppr is None:
        ppr = calcoli.makeelement(qn("w:pPr"), {})
        calcoli.insert(0, ppr)
    salto = ppr.makeelement(qn("w:pageBreakBefore"), {})
    ppr.insert(1 if ppr.find(qn("w:pStyle")) is not None else 0, salto)

    seg = copy.deepcopy(omi)
    next(seg.iter(qn("w:t"))).text = "[VALORI COMPARABILI]"
    succ = comp.getnext()
    if succ is not None and not testo(succ).strip():
        succ.addprevious(seg)
        rimuovi(succ)
    else:
        comp.addnext(seg)

    uscita.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(uscita))
    print(f"Modello salvato in {uscita}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
