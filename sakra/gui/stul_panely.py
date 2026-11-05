"""Panely Pracovního stolu: přehled kazety (všechny strany), pulzy, histogram délek a mřížka bloků dat."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..jadro.analyza import VysledekStrany
from ..jadro.model import cas_text
from ..platformy import podle_id
from ..i18n import tr

BARVA_NEZNAME = QColor("#8A93A3")
BARVA_AUDIO = QColor("#A8B8D8")
OK, OPRAVENO, CHYBA = QColor("#2EA866"), QColor("#E3A72F"), QColor("#E04848")


def nadpis_sekce(text: str = "") -> QLabel:
    """Nadpis sekce jako v ostatních částech okna: malá šedá tučná verzálka."""
    lab = QLabel(text)
    lab.setObjectName("nadpisSekce")
    lab.setTextFormat(Qt.TextFormat.RichText)
    f = lab.font()
    f.setPointSizeF(max(7.5, f.pointSizeF() - 1.5))
    f.setBold(True)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
    lab.setFont(f)
    lab.setStyleSheet("color:#8C95A6")
    return lab


def barva_oblasti(o) -> QColor:
    pl = podle_id(o.platforma) if o.platforma else None
    return QColor(pl.barva) if pl else (BARVA_AUDIO if o.nazev == "audio" else BARVA_NEZNAME)


def _oblast_v_case(v: VysledekStrany, t: float):
    return next((o for o in v.oblasti if o.zacatek <= t <= o.konec and o.platforma), None) or \
        next((o for o in v.oblasti if o.zacatek <= t <= o.konec), None)


# =====================================================================  přehled kazety
class PrehledKazety(QWidget):
    """Všechny strany pod sebou jako obálka signálu obarvená podle platformy; rámeček = co ukazuje detail strany.
    Klik vybere stranu a místo."""
    klik = Signal(int, float)            # strana, čas

    SLOUPCU = 1600
    VYSKA_PRUHU = 38
    ODSTUP = 6
    LEVY = 34            # číslo strany + písmeno stopy (L/P)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.strany: list[tuple[int, VysledekStrany]] = []
        self.vyber: tuple[int, float, float] | None = None       # strana, od, do
        self._obalky: dict[int, tuple] = {}
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._vyska()

    def _vyska(self):
        n = max(1, len(self.strany))
        self.setFixedHeight(n * (self.VYSKA_PRUHU + self.ODSTUP) + 18)

    def nastav(self, vysledky: dict[int, VysledekStrany]) -> None:
        self.strany = sorted(vysledky.items())
        self._obalky = {}
        for c, v in self.strany:
            self._obalky[c] = self._obalka(v)
        self._vyska()
        self.update()

    def nastav_vyber(self, strana: int | None, od: float, do: float) -> None:
        self.vyber = (strana, od, do) if strana is not None else None
        self.update()

    def _obalka(self, v: VysledekStrany) -> list[tuple[str, np.ndarray, list, float]]:
        """Stopy strany: (popis, špičky 0..1, barvy sloupců nebo None = nezpracovaná stopa, čas sloupce).
        U sterea obě stopy z obálky celého souboru; zpracovaná barevně podle platforem, druhá šedě."""
        n = v.nahravka
        rate = n.rate
        if n.obalky is not None and n.obalky.shape[0] > 1 and n.obalky.shape[1]:
            ob = n.obalky
            krok = max(1, ob.shape[1] // self.SLOUPCU)
            m = ob.shape[1] // krok
            stopy = ob[:, : m * krok].reshape(ob.shape[0], m, krok).max(axis=2)
            dt = krok * n.krok_obalky
            barvy = self._barvy(v, m, dt)
            pouzite = {0, 1} if n.kanal < 0 else {n.kanal}          # součet: obě stopy
            return [("LP"[c] if c < 2 else str(c + 1), stopy[c], barvy if c in pouzite else None, dt)
                    for c in range(ob.shape[0])]
        x = n.vzorky
        krok = max(1, len(x) // self.SLOUPCU)
        m = min(self.SLOUPCU, len(x) // krok)
        mx = np.abs(x[: m * krok].reshape(m, krok)).max(axis=1).astype(np.float32) / 32768.0
        return [("", mx, self._barvy(v, m, krok / rate), krok / rate)]

    @staticmethod
    def _barvy(v: VysledekStrany, m: int, dt: float) -> list:
        barvy: list[QColor | None] = [None] * m
        for o in v.oblasti:
            a = max(0, int(o.zacatek / dt))
            b = min(m, int(o.konec / dt) + 1)
            c = barva_oblasti(o)
            for i in range(a, b):
                if barvy[i] is None or o.platforma:
                    barvy[i] = c
        return barvy

    @property
    def _delka(self) -> float:
        return max((v.nahravka.delka for _, v in self.strany), default=1.0)

    def _x(self, t: float) -> float:
        return self.LEVY + t / self._delka * (self.width() - self.LEVY - 4)

    def _t(self, x: float) -> float:
        return max(0.0, (x - self.LEVY) / max(1, self.width() - self.LEVY - 4) * self._delka)

    def paintEvent(self, _):
        p = QPainter(self)
        pal = self.palette()
        p.fillRect(self.rect(), pal.window())
        if not self.strany:
            p.setPen(pal.placeholderText().color())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Žádná nahrávka"))
            return
        f = QFont(self.font())
        f.setBold(True)
        ticho = pal.mid().color()
        sede = QColor(pal.mid().color())
        sede.setAlpha(150)
        male = QFont(self.font())
        male.setPointSizeF(max(6.5, male.pointSizeF() - 2))
        for r, (c, v) in enumerate(self.strany):
            y0 = r * (self.VYSKA_PRUHU + self.ODSTUP) + 2
            p.setFont(f)
            p.setPen(pal.placeholderText().color())
            p.drawText(QRectF(0, y0, 18, self.VYSKA_PRUHU), Qt.AlignmentFlag.AlignCenter, str(c))
            stopy = self._obalky[c]
            vyska = (self.VYSKA_PRUHU - 2 * (len(stopy) - 1)) / len(stopy)
            for k_, (popis, mx, barvy, dt) in enumerate(stopy):
                ys = y0 + k_ * (vyska + 2)
                stred = ys + vyska / 2
                k = vyska / 2 - 0.5
                if popis:
                    p.setFont(male)
                    p.setPen(pal.placeholderText().color() if barvy is not None else sede)
                    p.drawText(QRectF(17, ys, self.LEVY - 18, vyska), Qt.AlignmentFlag.AlignCenter, popis)
                akt = None
                for i in range(len(mx)):
                    x = self._x(i * dt)
                    if x > self.width() - 4:
                        break
                    b = (barvy[i] or ticho) if barvy is not None else sede
                    if b is not akt:
                        p.setPen(QPen(b, 1))
                        akt = b
                    h = max(0.5, float(mx[i]) * k)
                    p.drawLine(QPointF(x, stred - h), QPointF(x, stred + h))
            if self.vyber and self.vyber[0] == c:
                a, b = self._x(self.vyber[1]), self._x(self.vyber[2])
                p.setPen(QPen(pal.text().color(), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(QRectF(a, y0, max(3.0, b - a), self.VYSKA_PRUHU), 2, 2)
        # časová osa
        p.setFont(self.font())
        p.setPen(pal.placeholderText().color())
        y = self.height() - 3
        delka = self._delka
        krok = next((k for k in (10, 30, 60, 120, 300, 600, 900, 1800) if delka / k <= 8), 3600)
        konec = cas_text(delka)[:5]
        x_konce = self.width() - p.fontMetrics().horizontalAdvance(konec) - 4
        sirka_popisu = p.fontMetrics().horizontalAdvance("00:00") + 8
        t = 0.0
        while self._x(t) + sirka_popisu < x_konce:
            p.drawText(QPointF(self._x(t) + 1, y), cas_text(t)[:5])
            t += krok
        p.drawText(QPointF(x_konce, y), konec)

    def mousePressEvent(self, e):
        if not self.strany or e.button() != Qt.MouseButton.LeftButton:
            return
        r = int((e.position().y() - 2) // (self.VYSKA_PRUHU + self.ODSTUP))
        if 0 <= r < len(self.strany):
            self.klik.emit(self.strany[r][0], self._t(e.position().x()))

    def mouseMoveEvent(self, e):
        self.setToolTip(cas_text(self._t(e.position().x())) if self.strany else "")


# =====================================================================  pulzy
class PulzyPohled(QWidget):
    """Průběh pulzů (úrovně mezi přechody) v okolí jednoho místa; chyba bloku červeně."""
    POCET = 48           # kolik přechodů na každou stranu od místa

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self.v: VysledekStrany | None = None
        self.t: float | None = None
        self.chyby: list[float] = []
        self.popis = ""

    def nastav(self, v: VysledekStrany | None, t: float | None, chyby: list[float] | None = None) -> None:
        self.v, self.t = v, t
        self.chyby = chyby or []
        self.update()

    def _okno(self):
        pz = self.v.pulzy
        i = int(np.searchsorted(pz.hrany, self.t * pz.rate))
        a, b = max(0, i - self.POCET), min(len(pz.hrany), i + self.POCET)
        if b - a < 2:
            return None
        hr = pz.hrany[a:b]
        # ticho okolo: nejvýš 30 ms na každou stranu
        t0 = max(hr[0], self.t * pz.rate - 0.03 * pz.rate)
        t1 = min(hr[-1], self.t * pz.rate + 0.03 * pz.rate)
        if t1 - t0 < 10:
            return None
        return a, b, t0, t1

    def text_popisu(self) -> str:
        """Pro nadpis: nejčastější délky půlvln v okně."""
        if not self.v or self.t is None:
            return ""
        o = self._okno()
        if o is None:
            return tr("bez signálu")
        a, b, _, _ = o
        us = np.diff(self.v.pulzy.hrany[a:b]) * 1e6 / self.v.pulzy.rate
        us = us[us < 3000]
        if not len(us):
            return tr("bez signálu")
        h = np.bincount((us / 20).astype(int))
        vrch = [int(i) for i in np.argsort(h)[::-1] if h[i] >= max(2, h.max() * 0.25)][:3]
        vrch = sorted(vrch, key=lambda i: i)
        return tr("nejčastější půlvlny: ") + ", ".join(f"{i * 20 + 10} µs" for i in vrch)

    def paintEvent(self, _):
        p = QPainter(self)
        pal = self.palette()
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), pal.base())
        if not self.v or self.t is None:
            p.setPen(pal.placeholderText().color())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Najeďte myší na průběh strany"))
            return
        o = self._okno()
        if o is None:
            p.setPen(pal.placeholderText().color())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "ticho")
            return
        a, b, t0, t1 = o
        pz = self.v.pulzy
        sx = lambda s: (s - t0) / (t1 - t0) * (w - 8) + 4  # noqa: E731
        horni, dolni = 8, h - 8
        ob = _oblast_v_case(self.v, self.t)
        barva = barva_oblasti(ob) if ob else pal.text().color()
        # chyby (konec vadného bloku = místo, kde se čtení zastavilo)
        for c in self.chyby:
            x = sx(c * pz.rate)
            if 0 <= x <= w:
                p.setPen(QPen(CHYBA, 1.5))
                p.setBrush(QColor(224, 72, 72, 40))
                p.drawRoundedRect(QRectF(x - 14, 3, 28, h - 6), 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(barva, 1.4))
        hr, ur = pz.hrany[a:b], pz.urovne[a:b]
        pred = None
        for s, u in zip(hr, ur):
            x = sx(s)
            y = horni if u > 0 else dolni
            if pred is not None:
                px, py = pred
                p.drawLine(QPointF(px, py), QPointF(x, py))
                p.drawLine(QPointF(x, py), QPointF(x, y))
            pred = (x, y)
        if pred is not None:
            p.drawLine(QPointF(pred[0], pred[1]), QPointF(w - 4, pred[1]))
        x = sx(self.t * pz.rate)
        p.setPen(QPen(pal.text().color(), 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(x, 0), QPointF(x, h))


# =====================================================================  histogram délek
class HistogramDelek(QWidget):
    """Histogram délek půlvln ve viditelném úseku strany (po 10 µs); vrcholy s popisem."""
    KROK = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self.h: np.ndarray | None = None
        self.barva = QColor("#E39A2B")

    def nastav(self, v: VysledekStrany | None, od: float, do: float) -> None:
        self.h = None
        if v is not None:
            pz = v.pulzy
            a, b = np.searchsorted(pz.hrany, [od * pz.rate, do * pz.rate])
            if b - a > 8:
                us = np.diff(pz.hrany[a:b]) * 1e6 / pz.rate
                us = us[us < 3000]
                if len(us) > 8:
                    self.h = np.bincount((us / self.KROK).astype(int), minlength=300)[:300]
            ob = _oblast_v_case(v, (od + do) / 2)
            self.barva = barva_oblasti(ob) if ob else QColor("#E39A2B")
        self.update()

    def vrcholy(self) -> list[int]:
        """Délky (µs) výrazných vrcholů."""
        if self.h is None:
            return []
        h = self.h.astype(float)
        hl = np.convolve(h, [1, 2, 1], "same")
        kand = [i for i in range(1, len(hl) - 1) if hl[i] >= hl[i - 1] and hl[i] > hl[i + 1]
                and hl[i] >= 0.12 * hl.max()]
        vys = []
        for i in sorted(kand, key=lambda i: -hl[i]):
            if all(abs(i - j) > 6 for j in vys):
                vys.append(i)
        return sorted(i * self.KROK + self.KROK // 2 for i in vys[:4])

    def paintEvent(self, _):
        p = QPainter(self)
        pal = self.palette()
        w, hgt = self.width(), self.height()
        p.fillRect(self.rect(), pal.base())
        if self.h is None or not self.h.any():
            p.setPen(pal.placeholderText().color())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("bez pulzů"))
            return
        nz = np.flatnonzero(self.h)
        posl = int(min(len(self.h), max(40, np.searchsorted(np.cumsum(self.h), 0.995 * self.h.sum()) * 1.15 + 5)))
        h = self.h[:posl].astype(float)
        mx = h.max()
        dole = hgt - 14
        dx = (w - 4) / posl
        p.setPen(Qt.PenStyle.NoPen)
        c = QColor(self.barva)
        c.setAlpha(220)
        p.setBrush(c)
        for i in nz:
            if i >= posl:
                break
            v = h[i] / mx * (dole - 12)
            p.drawRect(QRectF(2 + i * dx, dole - v, max(1.0, dx - 0.6), v))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.5))
        p.setFont(f)
        p.setPen(pal.text().color())
        for us in self.vrcholy():
            i = us // self.KROK
            if i < posl:
                v = h[i] / mx * (dole - 12)
                p.drawText(QPointF(2 + i * dx - 8, max(10.0, dole - v - 3)), f"{us}")
        p.setPen(pal.placeholderText().color())
        p.drawText(QPointF(2, hgt - 2), "0")
        konec = f"{posl * self.KROK} µs"
        p.drawText(QPointF(w - p.fontMetrics().horizontalAdvance(konec) - 2, hgt - 2), konec)


# =====================================================================  mřížka bloků
class MrizkaBloku(QWidget):
    """Bloky vybraného programu jako barevná políčka: zelená = bez chyby, oranžová = opraveno, červená = chyba."""
    vybran = Signal(object)        # Blok
    BUNKA, MEZERA = 14, 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bloky: list = []
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def nastav(self, bloky: list) -> None:
        self.bloky = list(bloky)
        self.updateGeometry()
        self.update()

    def _na_radek(self, w: int | None = None) -> int:
        return max(1, ((w or self.width()) + self.MEZERA) // (self.BUNKA + self.MEZERA))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        radku = max(1, -(-len(self.bloky) // self._na_radek(w)))
        return radku * (self.BUNKA + self.MEZERA)

    def sizeHint(self) -> QSize:
        return QSize(260, self.heightForWidth(260))

    def _rect(self, i: int) -> QRectF:
        n = self._na_radek()
        r, s = divmod(i, n)
        return QRectF(s * (self.BUNKA + self.MEZERA), r * (self.BUNKA + self.MEZERA), self.BUNKA, self.BUNKA - 4)

    @staticmethod
    def barva(b) -> QColor:
        return CHYBA if not b.ok else OPRAVENO if b.oprava else OK

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        for i, b in enumerate(self.bloky):
            p.setBrush(self.barva(b))
            p.drawRoundedRect(self._rect(i), 2, 2)

    def _blok_na(self, pos) -> int | None:
        for i in range(len(self.bloky)):
            if self._rect(i).adjusted(-1, -1, 1, 3).contains(pos):
                return i
        return None

    def mouseMoveEvent(self, e):
        i = self._blok_na(e.position())
        if i is None:
            self.setToolTip("")
            return
        b = self.bloky[i]
        stav = "chyba" if not b.ok else (tr("opraveno – ") + b.oprava) if b.oprava else tr("bez chyby")
        cislo = f" {b.cislo}" if b.cislo is not None else f" {i + 1}"
        self.setToolTip(f"{b.typ}{cislo} · {len(b.data)} B · {cas_text(b.zacatek)}–{cas_text(b.konec)} · {stav}")

    def mousePressEvent(self, e):
        i = self._blok_na(e.position())
        if i is not None:
            self.vybran.emit(self.bloky[i])
