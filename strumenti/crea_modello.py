"""Crea il modello con i segnaposto (modelli/preliminare_modello.docx) partendo dalla bozza
Word dell'agenzia, di cui mantiene impaginazione, margini, carattere e interlinea.

Uso:  python strumenti/crea_modello.py bozza.docx modelli/preliminare_modello.docx

Il testo del contratto e' quello della bozza, con i dati variabili sostituiti da segnaposto
(sintassi Jinja/docxtpl). Il modello risultante puo' poi essere modificato direttamente in
Word: vedi docs/GUIDA_MODELLO.md per l'elenco dei segnaposto.
"""

from __future__ import annotations

import copy
import re
import sys

import docx
from docx.oxml.ns import qn

# Ogni voce: (stile, testo). Nel testo **...** indica il grassetto.
# Stili: titolo, centro, testo, articolo, rientro, firme, tag (paragrafo di controllo docxtpl)
TESTO = [
    ("titolo", "**CONTRATTO PRELIMINARE DI COMPRAVENDITA IMMOBILIARE**"),
    ("centro", "Con la presente scrittura privata, da valere a tutti gli effetti e conseguenze di legge"),
    ("centro", "Tra"),
    ("tag", "{%p for p in venditori %}"),
    ("testo",
     "{% if p.societa %}La società **{{p.soc_denominazione}}** con sede in {{p.soc_sede}}, C.F./P.IVA {{p.soc_cf}}"
     "{% if p.soc_rea %}, {{p.soc_rea}}{% endif %}, in persona {{p.del_qualita}} {{p.soc_qualita}} {{p.art_min}} "
     "{% else %}{{p.art}} {% endif %}**{{p.nominativo}}** {{p.nato}} a {{p.luogo_nascita}} il {{p.data_nascita}}, "
     "Cod. Fisc. {{p.cf}}, documento d'identità {{p.doc_tipo}} N° {{p.doc_numero}}, {{p.rilasciato}} "
     "{{p.doc_ente}} in data {{p.doc_rilascio}} e scadente in data {{p.doc_scadenza}}, residente in {{p.residenza}}"
     "{% if loop.last %}, {{V.che_sara}} **\"Parte Promittente Venditrice\"**;{% else %};{% endif %}"),
    ("tag", "{%p endfor %}"),
    ("centro", "e"),
    ("tag", "{%p for p in acquirenti %}"),
    ("testo",
     "{% if p.societa %}La società **{{p.soc_denominazione}}** con sede in {{p.soc_sede}}, C.F./P.IVA {{p.soc_cf}}"
     "{% if p.soc_rea %}, {{p.soc_rea}}{% endif %}, in persona {{p.del_qualita}} {{p.soc_qualita}} {{p.art_min}} "
     "{% else %}{{p.art}} {% endif %}**{{p.nominativo}}** {{p.nato}} a {{p.luogo_nascita}} il {{p.data_nascita}}, "
     "Cod. Fisc. {{p.cf}}, documento d'identità {{p.doc_tipo}} N° {{p.doc_numero}}, {{p.rilasciato}} "
     "{{p.doc_ente}} in data {{p.doc_rilascio}} e scadente in data {{p.doc_scadenza}}, residente in {{p.residenza}}"
     "{% if loop.last %}, {{A_.che_sara}} **\"Parte Promissaria Acquirente\"**{% else %};{% endif %}"),
    ("tag", "{%p endfor %}"),
    ("centro", "si conviene e si stipula quanto segue:"),

    ("articolo", "Articolo 1"),
    ("testo",
     "1.1. La Parte Promittente Venditrice promette di cedere e vendere alla Parte Promissaria Acquirente, che "
     "promette di acquistare per sé stessa o persona da nominare, il seguente {{I.tipologia}} sito nel Comune di "
     "{{I.comune}} ({{I.prov}}), in {{I.indirizzo}}, costituito da {{I.descrizione}}, il tutto identificato al C.F. "
     "del Comune di {{I.comune}} ({{I.prov}}) come segue:"),
    ("tag", "{%p for g in I.gruppi %}"),
    ("testo", "**{{g.intestazione}}:**"),
    ("tag", "{%p for u in g.unita %}"),
    ("testo", "**- Sub. {{u.sub}}**, Cat. {{u.categoria}}, Classe {{u.classe}}, Consistenza {{u.consistenza}}, "
              "Rendita Euro {{u.rendita}}{% if u.ultima %}.{% else %};{% endif %}"),
    ("tag", "{%p endfor %}"),
    ("tag", "{%p endfor %}"),
    ("testo",
     "1.2 A migliore identificazione di quanto promesso in vendita, alla presente scrittura "
     "{% if I.n_planimetrie == 1 %}viene allegata 1 (una) planimetria catastale che ne costituisce parte integrante"
     "{% else %}vengono allegate {{I.planimetrie}} planimetrie catastali che ne costituiscono parte integrante"
     "{% endif %}. Inoltre si specifica che sono comprese le proporzionali quote di comproprietà sulle parti comuni "
     "ai sensi dell'articolo 1117 cod. civ."),
    ("testo",
     "1.3. {% if I.plurale %}Le unità immobiliari sopra descritte saranno trasferite{% else %}L’unità immobiliare "
     "sopra descritta sarà trasferita{% endif %} nello stato di fatto e di diritto in cui oggi si "
     "{% if I.plurale %}trovano{% else %}trova{% endif %}, con ogni annesso, connesso, pertinenza ed accessorio, "
     "diritto, azione e ragione, servitù attiva e passiva, così come {% if I.plurale %}viste e gradite"
     "{% else %}vista e gradita{% endif %} dalla Parte Promissaria Acquirente."),

    ("articolo", "Articolo 2"),
    ("testo",
     "2.1. {% if I.plurale %}Le unità immobiliari sono pervenute{% else %}L’unità immobiliare è pervenuta{% endif %} "
     "alla Parte Promittente Venditrice con atto di {{P.tipo_atto}} del Notaio {{P.notaio}}"
     "{% if P.notaio_sede %} di {{P.notaio_sede}}{% endif %} del {{P.data}}, rep. n. {{P.repertorio}}"
     "{% if P.raccolta %}, racc. n. {{P.raccolta}}{% endif %}{% if P.registrazione %}, {{P.registrazione}}{% endif %}"
     ", {{P.trascrizione}}."),

    ("articolo", "Articolo 3"),
    ("testo",
     "3.1. La vendita verrà effettuata a corpo e non a misura, il prezzo è convenuto tra le Parti, di comune "
     "accordo, nella somma complessiva di **{{A.prezzo}}** che la Parte Promissaria Acquirente si obbliga a pagare "
     "nei modi e nei termini seguenti:"),
    ("tag", "{%p if A.caparra %}"),
    ("rientro",
     "{{A.n_caparra}} quanto a **{{A.caparra}}** a titolo di caparra confirmatoria dalla Parte Promissaria "
     "Acquirente alla Parte Promittente Venditrice, {{A.caparra_dettaglio}}. La Parte Promittente Venditrice "
     "dichiarerà di ricevere la somma suddetta salvo buon esito dell’incasso dell’intera somma, restano in ogni "
     "caso riconosciuti tutti i diritti garantiti a favore delle Parti dall'art. 1385 del C.C.;"),
    ("tag", "{%p endif %}"),
    ("tag", "{%p for a in A.acconti %}"),
    ("rientro", "{{a.n}} quanto a **{{a.importo}}** a titolo di acconto prezzo, {{a.dettaglio}};"),
    ("tag", "{%p endfor %}"),
    ("rientro", "{{A.n_saldo}} quanto a **{{A.saldo}}**, a saldo, {{A.saldo_modalita}}."),
    ("tag", "{%p if A.mutuo %}"),
    ("rientro",
     "{{A.n_mutuo}} Il presente contratto è sottoposto alla condizione sospensiva dell’ottenimento, da parte della "
     "Parte Promissaria Acquirente, di un mutuo bancario per un importo non inferiore a **{{A.mutuo_importo}}** "
     "entro il {{A.mutuo_entro}}. In caso di mancato ottenimento del mutuo entro tale termine, documentato da "
     "diniego scritto dell’istituto di credito, il presente contratto si intenderà risolto e la Parte Promittente "
     "Venditrice restituirà alla Parte Promissaria Acquirente quanto ricevuto, senza interessi, penali o rivalse."),
    ("tag", "{%p endif %}"),

    ("articolo", "Articolo 4"),
    ("testo",
     "4.1. Il contratto definitivo di compravendita dovrà essere stipulato entro e non oltre il "
     "**{{A.data_rogito}}**, salvo diverso accordo tra le parti, presso lo studio di un Notaio da individuarsi a "
     "cura della {{A.notaio_scelta}}. {% if A.locato %}L’immobile è attualmente locato: la consegna avverrà "
     "contestualmente al rogito notarile, nello stato locativo in essere.{% else %}La consegna dell'immobile, "
     "libero da cose e persone, avverrà contestualmente al rogito notarile.{% endif %}"),
    ("testo",
     "4.2. Le spese relative all’atto notarile e le imposte in genere saranno a carico della Parte Promissaria "
     "Acquirente."),
    ("testo",
     "4.3. Le spese condominiali resteranno a carico della parte venditrice fino alla stipula dell'atto notarile "
     "di trasferimento. Eventuali spese straordinarie deliberate dal Venditore resteranno a carico dello stesso "
     "anche dopo il rogito notarile. La Parte Promittente Venditrice si obbliga a consegnare alla Parte "
     "Promissaria Acquirente una dichiarazione rilasciata dall'amministratore del condominio, da cui risulti "
     "l'avvenuto pagamento delle spese condominiali a loro carico fino alla data del rogito notarile."),

    ("articolo", "Articolo 5"),
    ("testo",
     "5.1. {% if I.plurale %}Le unità immobiliari sopra descritte, visitate, viste e piaciute dalla Parte "
     "Promissaria Acquirente, vengono promesse{% else %}L’unità immobiliare sopra descritta, visitata, vista e "
     "piaciuta dalla Parte Promissaria Acquirente, viene promessa{% endif %} in vendita a corpo e non a misura, "
     "nello stato e grado in cui attualmente si {% if I.plurale %}trovano{% else %}trova{% endif %}, con tutti i "
     "diritti, pertinenze ed eventuali servitù attive e passive, apparenti e non apparenti, così come "
     "{% if I.plurale %}pervenute{% else %}pervenuta{% endif %} alla Parte Promittente Venditrice in forza dei "
     "titoli di proprietà e del possesso."),
    ("testo",
     "5.2. La Parte Promittente Venditrice dichiara e garantisce sin da ora, di avere la piena proprietà e "
     "disponibilità, anche ai sensi della L. n. 151/1975, della stessa, la quale sarà trasferita libera da "
     "iscrizioni ipotecarie, trascrizioni pregiudizievoli, liti in corso, vizi, evizioni, da oneri reali fiscali "
     "in genere nonché da diritti di o verso terzi di qualunque natura."),
    ("testo",
     "5.3 La Parte Promittente Venditrice dichiara, ai sensi del D.P.R. 380/2001 e della L. 47/1985, che "
     "{{U.dichiarazione}}. {% if U.conforme %}Dichiara altresì che lo stato di fatto è conforme ai titoli "
     "abilitativi e alle planimetrie catastali depositate, ai sensi dell’art. 29, comma 1-bis, L. 52/1985. "
     "Qualora emergessero difformità prima del rogito, la Parte Promittente Venditrice si obbliga a regolarizzarle "
     "a propria cura e spese entro la data del rogito.{% else %}Le Parti danno atto che lo stato di fatto "
     "dell’immobile non corrisponde attualmente ai dati catastali e alle planimetrie depositate: la Parte "
     "Promittente Venditrice si obbliga ad aggiornarli a propria cura e spese entro la data del rogito notarile, "
     "ai sensi dell’art. 29, comma 1-bis, L. 52/1985.{% endif %}"),
    ("testo",
     "{% if U.agibile %}La Parte Promittente Venditrice dichiara che l’immobile è dotato di certificato di "
     "agibilità/abitabilità {{U.agibilita}}.{% else %}La Parte Promittente Venditrice dichiara che l’immobile non "
     "è dotato di certificato di agibilità.{% endif %}"),
    ("testo",
     "5.4. La Parte Promittente Venditrice dichiara che il bene oggetto del presente contratto è esente da vizi "
     "occulti che ne diminuiscano il valore."),
    ("testo",
     "5.5 {% if E.presente %}In base alle disposizioni previste dal D.Lgs. 192/2005, dal DM del 25 giugno 2009 e "
     "dal D.Lgs. n.63 del 04/06/2013, la Parte Promittente Venditrice consegna in data odierna copia originale "
     "dell'Attestato di Certificazione Energetica, dove si evince la classe energetica di appartenenza "
     "dell’immobile, classe “{{E.classe}}” con Ipe {{E.ipe}} kwh/mq anno redatta dal {{E.tecnico}} in data "
     "{{E.data}}.{% else %}In base alle disposizioni previste dal D.Lgs. 192/2005 e successive modifiche, la Parte "
     "Promittente Venditrice si obbliga a consegnare alla Parte Promissaria Acquirente, entro la data del rogito "
     "notarile, l’Attestato di Prestazione Energetica (APE) dell’immobile.{% endif %}"),
    ("testo",
     "5.6 Il presente preliminare potrà essere registrato e/o trascritto con spese a carico della parte "
     "Promissaria Acquirente, anche successivamente alla firma del presente."),
    ("tag", "{%p for c in clausole %}"),
    ("testo", "{{c.n}} {{c.testo}}"),
    ("tag", "{%p endfor %}"),

    ("articolo", "Articolo 6"),
    ("testo",
     "6.1. Ai fini della Legge 19 maggio 1975 n.151, si dichiara: {% for p in stato_civile %}{{p.art_min}} "
     "**{{p.nominativo}}** di essere di stato civile {{p.stato_civile}}{% if not loop.last %}"
     "{% if loop.revindex == 2 %} e {% else %}, {% endif %}{% endif %}{% endfor %}."),

    ("articolo", "Articolo 7"),
    ("testo",
     "7.1. Ai sensi del GDPR Ue 2016/679, entrambe le parti autorizzano al trattamento dei dati relativi al "
     "presente contratto anche a mezzo di professionisti, terzi, società di consulenza e di elaborazione dati. "
     "Entrambe le parti si impegnano a considerare ogni dato, notizia, fatto o circostanza di cui sono venute a "
     "conoscenza in ragione del presente contratto e, per l'effetto, si obbligano a non divulgare a terzi, né ad "
     "utilizzare quanto venuto a conoscenza per fini diversi da quelli strettamente connessi al presente atto."),

    ("articolo", "Articolo 8"),
    ("testo",
     "8.1. Le parti convengono che ogni controversia relativa all’interpretazione, alla patologia e "
     "all’esecuzione del presente contratto e, comunque, allo stesso in qualsiasi modo collegata, sarà devoluta "
     "alla competenza esclusiva del Foro di {{F.foro}}."),
    ("testo",
     "8.2. Il presente contratto preliminare, composto di {{F.pagine}} pagine, oltre "
     "{% if I.n_planimetrie == 1 %}alla 1 (una) planimetria allegata{% else %}alle {{I.planimetrie}} planimetrie "
     "allegate{% endif %}, viene sottoscritto dalle parti in triplice copia originale."),
    ("testo", "8.3. Qualunque modifica del presente atto dovrà essere approvata dalle Parti mediante atto scritto."),
    ("testo", "LETTO, CONFERMATO E SOTTOSCRITTO"),
    ("testo", "{{F.luogo}}, lì {{F.data}}"),
    ("firme", "\"Parte Promittente Venditrice\"\t\t\t                \"Parte Promissaria Acquirente\""),
]

# paragrafo della bozza da cui copiare la formattazione, per ogni stile
ORIGINE = {"titolo": 0, "centro": 1, "testo": 3, "articolo": 7, "rientro": 3, "firme": 41, "tag": 3}


def _rpr(paragrafo, grassetto: bool):
    for r in paragrafo.runs:
        if bool(r.bold) == grassetto and r._r.rPr is not None:
            return copy.deepcopy(r._r.rPr)
    r = paragrafo.runs[0]._r.rPr
    rpr = copy.deepcopy(r)
    if grassetto:
        b = rpr.makeelement(qn("w:b"), {})
        rpr.insert(1, b)
    return rpr


def crea(bozza: str, destinazione: str) -> None:
    doc = docx.Document(bozza)
    par = doc.paragraphs
    modelli = {k: par[i] for k, i in ORIGINE.items()}
    normale = {k: _rpr(p, False) for k, p in modelli.items()}
    grassetto = {k: _rpr(p, True) for k, p in modelli.items()}
    ppr = {k: copy.deepcopy(p._p.pPr) for k, p in modelli.items()}
    # il titolo e' sottolineato: il testo normale no
    for k in ("testo", "rientro", "tag", "centro"):
        for u in normale[k].findall(qn("w:u")) + grassetto[k].findall(qn("w:u")):
            u.getparent().remove(u)

    corpo = doc.element.body
    for p in list(corpo):
        if p.tag != qn("w:sectPr"):
            corpo.remove(p)
    sect = corpo.find(qn("w:sectPr"))

    for stile, testo in TESTO:
        p = corpo.makeelement(qn("w:p"), {})
        pp = copy.deepcopy(ppr[stile])
        num = pp.find(qn("w:numPr"))
        if num is not None:
            pp.remove(num)
        if stile == "rientro":
            ind = pp.makeelement(qn("w:ind"), {qn("w:left"): "708"})
            pp.insert(3, ind)
        p.append(pp)
        for i, pezzo in enumerate(re.split(r"\*\*", testo)):
            if not pezzo:
                continue
            r = p.makeelement(qn("w:r"), {})
            r.append(copy.deepcopy(grassetto[stile] if i % 2 else normale[stile]))
            t = r.makeelement(qn("w:t"), {qn("xml:space"): "preserve"})
            t.text = pezzo
            r.append(t)
            p.append(r)
        corpo.insert(list(corpo).index(sect), p)

    # niente dati personali nelle proprieta' del documento
    cp = doc.core_properties
    cp.author = "Grigolo Immobiliare"
    cp.last_modified_by = "Grigolo Immobiliare"
    cp.title = "Contratto preliminare di compravendita"
    cp.comments = ""
    doc.save(destinazione)
    _togli_duplicati(destinazione)


def _togli_duplicati(percorso: str) -> None:
    """I .docx convertiti da LibreOffice possono contenere due docProps/core.xml:
    si tiene solo l'ultimo (quello aggiornato), altrimenti Word segnala il file come danneggiato."""
    import zipfile
    with zipfile.ZipFile(percorso) as z:
        voci = {}
        for info in z.infolist():
            voci[info.filename] = (info, z.read(info))
    with zipfile.ZipFile(percorso, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, (info, dati) in voci.items():
            z.writestr(nome, dati)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    crea(sys.argv[1], sys.argv[2])
    print("Modello creato:", sys.argv[2])
