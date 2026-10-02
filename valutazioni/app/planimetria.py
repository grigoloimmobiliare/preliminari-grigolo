"""Superfici delle stanze da una planimetria catastale (PDF o immagine).

Procedimento:
1. la pagina viene letta a 300 dpi (o alla risoluzione della scansione contenuta nel PDF);
2. le linee nere sono i muri; le aperture delle porte (più strette di `porta_max` metri)
   vengono chiuse con una chiusura morfologica, così ogni stanza diventa una zona chiusa;
3. ogni zona bianca chiusa è un "vano": la sua area, fino al filo interno dei muri, è la
   superficie calpestabile (i muri e i pilastri chiusi dentro la stanza sono esclusi; le
   scritte dentro la stanza no);
4. la scala: quella del cartiglio (di solito 1:200). Molte planimetrie nascono su A3 e sono
   stampate ridotte su A4: la scala reale diventa circa 1:283 (1:200 × √2). Il programma lo
   propone da solo se a 1:200 le stanze risultano troppo strette; si può sempre cambiare.

Non si sceglie da soli quali zone sono l'unità da valutare (la planimetria contiene spesso
anche altri piani, vani scala, "altra unità"...): le zone vengono numerate sull'immagine e
nella pagina si spuntano quelle dell'immobile e si dà il nome alle stanze.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pymupdf

DPI = 300
SCALE = {"1:200": 200.0, "1:200 ridotta (A3 su A4)": 200.0 * math.sqrt(2), "1:100": 100.0, "1:500": 500.0}


@dataclass
class Vano:
    numero: int
    pixel: int
    cx: int
    cy: int
    lato_min_px: float
    lato_max_px: float
    contorno: np.ndarray

    def mq(self, px_m: float) -> float:
        return self.pixel / px_m ** 2

    def lati(self, px_m: float) -> tuple[float, float]:
        return self.lato_min_px / px_m, self.lato_max_px / px_m


def carica(percorso: Path) -> tuple[np.ndarray, float]:
    """Immagine in scala di grigi e risoluzione in punti per pollice."""
    if percorso.suffix.lower() == ".pdf":
        with pymupdf.open(percorso) as doc:
            pagina = doc[0]
            immagini = pagina.get_images(full=True)
            # scansione unica a tutta pagina: si usa così com'è, senza ricampionarla
            if len(immagini) == 1 and not pagina.get_drawings() and not pagina.get_text().strip():
                xref = immagini[0][0]
                rect = pagina.get_image_rects(xref)[0]
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n > 1 or pix.alpha:
                    pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
                img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w)
                larg_pollici = max(rect.width, rect.height) / 72
                dpi = max(pix.w, pix.h) / larg_pollici
                return _come_nel_pdf(img.copy(), pagina), dpi
            pix = pagina.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w).copy(), DPI
    img = cv2.imdecode(np.fromfile(str(percorso), np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Immagine non leggibile: {percorso.name}")
    return img, DPI


def _come_nel_pdf(img: np.ndarray, pagina) -> np.ndarray:
    """Gira la scansione nel verso in cui la mostra il lettore PDF (confronto con una miniatura)."""
    pix = pagina.get_pixmap(dpi=30, colorspace=pymupdf.csGRAY)
    rif = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w).astype(np.float32)
    migliore, errore = img, None
    for k in range(4):
        cand = np.rot90(img, k)
        if (cand.shape[0] > cand.shape[1]) != (rif.shape[0] > rif.shape[1]):
            continue
        picc = cv2.resize(cand, (rif.shape[1], rif.shape[0]), interpolation=cv2.INTER_AREA).astype(np.float32)
        e = float(np.mean(np.abs(picc - rif)))
        if errore is None or e < errore:
            migliore, errore = np.ascontiguousarray(cand), e
    return migliore


def px_per_metro(dpi: float, scala: float) -> float:
    return dpi / 25.4 * 1000 / scala


def _assottiglia(binaria: np.ndarray) -> np.ndarray:
    """Scheletro di linee spesse pochi pixel (algoritmo di Zhang-Suen, vettoriale)."""
    img = (binaria > 0).astype(np.uint8)
    img = np.pad(img, 1)
    while True:
        cambiato = False
        for passo in (0, 1):
            p = img
            p2, p3, p4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            p5, p6, p7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            p8, p9 = p[1:-1, :-2], p[:-2, :-2]
            c = p[1:-1, 1:-1]
            vicini = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            transizioni = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if passo == 0:
                cond = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                cond = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            togli = (c == 1) & (vicini >= 2) & (vicini <= 6) & (transizioni == 1) & cond
            if togli.any():
                c[togli] = 0
                cambiato = True
        if not cambiato:
            break
    return img[1:-1, 1:-1]


def chiudi_porte(nero: np.ndarray, px_m: float, porta_max: float = 1.1, px_m_porte: float | None = None) -> np.ndarray:
    """Chiude le aperture delle porte.

    I muri (spesso disegnati come due linee parallele) vengono prima riempiti; poi da ogni
    estremità di muro (stipite) si prolunga il muro nella sua direzione: se entro `porta_max`
    metri si incontra un altro muro, quella è una porta e si traccia la linea di chiusura.
    """
    spessore = max(3, int(round(0.30 * px_m)))
    pieni = cv2.morphologyEx(nero, cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (spessore, spessore)))
    sk = _assottiglia(pieni)
    vicini = cv2.filter2D(sk, -1, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT) - sk
    estremi = np.argwhere((sk == 1) & (vicini == 1))
    chiuso = pieni.copy()
    h, w = nero.shape
    dmax = porta_max * (px_m_porte or px_m)
    for y, x in estremi:
        # direzione del muro: dai pixel dello scheletro vicini verso l'estremità
        y0, y1, x0, x1 = max(y - 10, 0), min(y + 11, h), max(x - 10, 0), min(x + 11, w)
        ys, xs = np.nonzero(sk[y0:y1, x0:x1])
        if len(ys) < 5:
            continue
        dy, dx = y - (ys.mean() + y0), x - (xs.mean() + x0)
        norma = math.hypot(dx, dy)
        if norma < 2:
            continue
        dx, dy = dx / norma, dy / norma
        uscito, partenza, colpito = False, None, None
        for t in range(1, int(dmax + spessore * 2) + 1):
            xx, yy = int(round(x + dx * t)), int(round(y + dy * t))
            if not (0 <= xx < w and 0 <= yy < h):
                break
            if not uscito:
                if not pieni[yy, xx]:
                    uscito, partenza = True, (xx, yy)
                continue
            if pieni[yy, xx]:
                colpito = (xx, yy)
                break
            if math.hypot(xx - partenza[0], yy - partenza[1]) > dmax:
                break
        if colpito and math.hypot(colpito[0] - partenza[0], colpito[1] - partenza[1]) >= 0.3 * px_m:
            cv2.line(chiuso, (int(x), int(y)), colpito, 1, 2)
    return chiuso


def trova_vani(img: np.ndarray, dpi: float, porta_max: float = 1.1, scala: float | None = None) -> list[Vano]:
    """Zone chiuse della planimetria, dopo aver tolto le scritte e chiuso le porte."""
    # soglie (porte, scritte) calcolate per la scala 1:200 piena: valgono anche per le
    # planimetrie ridotte, dove porte e scritte risultano più piccole
    px_m = px_per_metro(dpi, scala or SCALE["1:200"])
    px_m_ridotta = px_per_metro(dpi, scala or SCALE["1:200 ridotta (A3 su A4)"])
    nero = (img < 140).astype(np.uint8)
    # le scritte e i puntini della scansione (pezzi neri piccoli e staccati) non sono muri;
    # soglia stretta, per non togliere i pezzetti di muro vicino alle porte
    nc, lc, sc, _ = cv2.connectedComponentsWithStats(nero, connectivity=8)
    piccoli = [k for k in range(1, nc) if max(sc[k][2], sc[k][3]) < 0.45 * px_m_ridotta]
    if piccoli:
        nero[np.isin(lc, piccoli)] = 0
    muri = chiudi_porte(nero, px_m_ridotta, porta_max, px_m_porte=px_m)
    bianco = (1 - muri).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bianco, connectivity=4)
    h, w = img.shape
    area_min = (1.2 * px_m) ** 2
    area_max = 0.25 * h * w
    vani = []
    for k in range(1, n):
        x, y, ww, hh, a = stats[k]
        if a < area_min or a > area_max or x == 0 or y == 0 or x + ww >= w or y + hh >= h:
            continue
        reg = (lab == k).astype(np.uint8) * 255
        reg = cv2.dilate(reg, np.ones((3, 3), np.uint8))            # fino a metà linea del muro
        cnts, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cnts, key=cv2.contourArea)
        (_, _), (l1, l2), _ = cv2.minAreaRect(c)
        if min(l1, l2) < 0.6 * px_m_ridotta:          # interno di un muro disegnato a contorno
            continue
        ys, xs = np.nonzero(reg)
        vani.append(Vano(0, int(len(xs)), int(xs.mean()), int(ys.mean()), min(l1, l2), max(l1, l2), c))
    vani.sort(key=lambda v: (round(v.cy / (2 * px_m)), v.cx))
    for i, v in enumerate(vani, 1):
        v.numero = i
    return vani


def scala_proposta(vani: list[Vano], dpi: float) -> str:
    """1:200, oppure 1:200 ridotta se a 1:200 le stanze risultano troppo strette per essere vere.

    Va calcolata sulle stanze dell'immobile (quelle spuntate), non su tutte le zone del foglio.
    """
    px_m = px_per_metro(dpi, SCALE["1:200"])
    stanze = [v for v in vani if 3 <= v.mq(px_m) <= 40]
    if not stanze:
        return "1:200"
    larghezze = sorted(v.lati(px_m)[0] for v in stanze)
    mediana = larghezze[len(larghezze) // 2]
    return "1:200 ridotta (A3 su A4)" if mediana < 2.2 else "1:200"


def immagine_numerata(img: np.ndarray, vani: list[Vano], px_m: float, dest: Path,
                      scelti: set[int] | None = None, nomi: dict[int, str] | None = None) -> Path:
    """Planimetria con le zone colorate e numerate; ritagliata attorno alle zone scelte (o a tutte)."""
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    colori = [(255, 200, 200), (200, 255, 200), (200, 200, 255), (255, 255, 170), (255, 170, 255),
              (170, 255, 255), (220, 220, 160), (160, 220, 220), (220, 160, 220)]
    mostra = [v for v in vani if not scelti or v.numero in scelti]
    for v in mostra:
        maschera = np.zeros(img.shape, np.uint8)
        cv2.drawContours(maschera, [v.contorno], -1, 255, -1)
        col = np.array(colori[v.numero % len(colori)])
        vis[maschera > 0] = (0.45 * vis[maschera > 0] + 0.55 * col).astype(np.uint8)
    scala_testo = max(0.5, img.shape[1] / 3000)
    for v in mostra:
        nome = (nomi or {}).get(v.numero, "")
        etichetta = f"{v.numero}" + (f" {nome}" if nome else "")
        for testo, dy in ((etichetta, 0), (f"{v.mq(px_m):.1f} mq", int(28 * scala_testo))):
            cv2.putText(vis, testo, (v.cx - int(30 * scala_testo), v.cy + dy), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7 * scala_testo, (0, 0, 170), max(1, int(2 * scala_testo)), cv2.LINE_AA)
    if mostra:
        pts = np.vstack([v.contorno.reshape(-1, 2) for v in mostra])
        x0, y0 = pts.min(axis=0) - 60
        x1, y1 = pts.max(axis=0) + 60
        vis = vis[max(y0, 0):y1, max(x0, 0):x1]
    if max(vis.shape[:2]) > 2200:
        f = 2200 / max(vis.shape[:2])
        vis = cv2.resize(vis, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", vis)
    dest.write_bytes(buf.tobytes())
    return dest


def analizza(percorso: Path, porta_max: float = 1.1) -> dict:
    """Zone chiuse della planimetria (le dimensioni restano in pixel: la scala si sceglie dopo)."""
    img, dpi = carica(percorso)
    vani = trova_vani(img, dpi, porta_max)
    return {"img": img, "dpi": dpi, "vani": vani}
