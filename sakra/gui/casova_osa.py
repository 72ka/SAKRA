"""Časová osa strany: vlna nahrávky, barevné úseky podle platformy, bloky, výběr. Kolečko = zoom, tažení = posun."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..jadro.analyza import VysledekStrany
from ..jadro.model import cas_text
from ..platformy import podle_id
from ..i18n import tr

KROKY = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
BARVA_NEZNAME = QColor("#8A93A3")
BARVA_AUDIO = QColor("#A8B8D8")


class CasovaOsa(QWidget):
    klik = Signal(float)          # čas, kam uživatel klikl
    uprava = Signal(float, bool)  # ruční úprava: čas kliknutí, True = pravé tlačítko (odebrat přechod)
    rozsah = Signal(float, float)  # změna zobrazeného úseku (od, do)
    mys = Signal(float)           # čas pod myší, NaN = myš odešla (None přes signál PySide na Pythonu 3.11 padá)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self.v: VysledekStrany | None = None
        self.od, self.do = 0.0, 1.0
        self.vyber: tuple[float, float] | None = None
        self._tah: tuple[float, float, float] | None = None
        self._mys: float | None = None
        self._posunuto = False
        self.prehravani: float | None = None     # kurzor přehrávání (s)
        self.rezim_upravy = False                # klik přidává / odebírá přechody
        self.pridane: set[int] = set()           # ručně přidané přechody (vzorky) – kreslí se zeleně

    # ---- data a pohled ----
    def nastav(self, v: VysledekStrany | None) -> None:
        self.v = v
        self.vyber = None
        self.cele()

    @property
    def delka(self) -> float:
        return self.v.nahravka.delka if self.v else 1.0

    def cele(self) -> None:
        self.od, self.do = 0.0, max(0.01, self.delka)
        self.update()
        self.rozsah.emit(self.od, self.do)

    def viditelny_usek(self) -> tuple[float, float]:
        """Co přehrát: vybraný úsek, jinak to, co je vidět (nejvýš 60 s)."""
        if self.vyber:
            return self.vyber
        return self.od, min(self.do, self.od + 60)

    def ukaz(self, od: float, do: float, vybrat: bool = True) -> None:
        """Přiblíží na úsek od..do s okrajem a označí ho."""
        if vybrat:
            self.vyber = (od, do)
        okraj = max(0.3, 0.08 * (do - od))
        self._nastav_rozsah(od - okraj, do + okraj)

    def _nastav_rozsah(self, od: float, do: float) -> None:
        sirka = min(max(do - od, 0.005), self.delka)
        od = min(max(0.0, od), max(0.0, self.delka - sirka))
        self.od, self.do = od, od + sirka
        self.update()
        self.rozsah.emit(self.od, self.do)

    def _x(self, t: float) -> float:
        return (t - self.od) / (self.do - self.od) * self.width()

    def _t(self, x: float) -> float:
        return self.od + x / max(1, self.width()) * (self.do - self.od)

    # ---- kreslení ----
    def paintEvent(self, _):
        p = QPainter(self)
        pal = self.palette()
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), pal.base())
        if not self.v:
            p.setPen(pal.placeholderText().color())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Otevřete nahrávku strany kazety (WAV, FLAC)"))
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._pravitko(p, w)
        self._oblasti(p, w)
        horni, dolni = 46, h - 6
        self._vlna(p, w, horni, dolni)
        self._bloky(p, horni, dolni)
        if self.vyber:
            a, b = self._x(self.vyber[0]), self._x(self.vyber[1])
            p.fillRect(QRectF(a, 22, max(2, b - a), h - 22), QColor(242, 169, 59, 50))
            p.setPen(QPen(QColor("#D98B12"), 1))
            p.drawLine(QPointF(a, 22), QPointF(a, h))
            p.drawLine(QPointF(b, 22), QPointF(b, h))
        if self.prehravani is not None:
            x = self._x(self.prehravani)
            p.setPen(QPen(QColor("#1F9254"), 2))
            p.drawLine(QPointF(x, 22), QPointF(x, h))
        if self._mys is not None:
            x = self._x(self._mys)
            p.setPen(QPen(pal.text().color(), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x, 22), QPointF(x, h))
            p.setPen(pal.text().color())
            p.drawText(QPointF(min(x + 4, w - 70), h - 8), cas_text(self._mys))

    def _pravitko(self, p: QPainter, w: int) -> None:
        pal = self.palette()
        p.fillRect(QRectF(0, 0, w, 20), pal.alternateBase())
        sirka = self.do - self.od
        krok = next((k for k in KROKY if k / sirka * w >= 90), KROKY[-1])
        p.setPen(pal.text().color())
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        p.setFont(f)
        t = math.floor(self.od / krok) * krok
        while t <= self.do:
            x = self._x(t)
            p.drawLine(QPointF(x, 14), QPointF(x, 20))
            text = cas_text(t) if krok < 1 else cas_text(t)[:5]
            p.drawText(QPointF(x + 3, 12), text)
            t += krok

    def _oblasti(self, p: QPainter, w: int) -> None:
        for o in self.v.oblasti:
            if o.konec < self.od or o.zacatek > self.do:
                continue
            pl = podle_id(o.platforma) if o.platforma else None
            barva = QColor(pl.barva) if pl else (BARVA_AUDIO if o.nazev == "audio" else BARVA_NEZNAME)
            a, b = self._x(o.zacatek), self._x(o.konec)
            r = QRectF(a, 23, max(2.0, b - a), 18)
            p.fillRect(r, barva)
            if b - a > 30:
                p.setPen(QColor("#ffffff") if pl else QColor("#1F2430"))
                text = o.nazev if pl else (tr("zvuk") if o.nazev == "audio" else tr("nerozpoznáno"))
                p.drawText(r.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(b - a - 6)))

    def _vlna(self, p: QPainter, w: int, horni: int, dolni: int) -> None:
        x = self.v.nahravka.vzorky
        rate = self.v.nahravka.rate
        a = max(0, int(self.od * rate))
        b = min(len(x), int(self.do * rate) + 1)
        stred = (horni + dolni) / 2
        vyska = (dolni - horni) / 2
        p.setPen(QPen(self.palette().mid().color(), 1))
        p.drawLine(QPointF(0, stred), QPointF(w, stred))
        if b - a < 2:
            return
        barva = QColor("#3B6FB6")
        p.setPen(QPen(barva, 1))
        kus = x[a:b]
        k = 1.0 / 32768 * vyska
        if b - a > 2 * w:                         # obálka: min/max na sloupec, barva podle platformy úseku
            sloupcu = w
            krok = (b - a) // sloupcu
            v = kus[: krok * sloupcu].reshape(sloupcu, krok)
            mn, mx = v.min(axis=1), v.max(axis=1)
            x0 = self._x(a / rate)
            dx = krok / rate / (self.do - self.od) * w
            barvy = self._barvy_sloupcu(a / rate, krok / rate, sloupcu)
            for i in range(sloupcu):
                if i == 0 or barvy[i] is not barvy[i - 1]:
                    p.setPen(QPen(barvy[i], 1))
                xx = x0 + i * dx
                p.drawLine(QPointF(xx, stred - mx[i] * k), QPointF(xx, stred - mn[i] * k + 0.5))
        else:                                     # jednotlivé vzorky
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            casy = (np.arange(a, b) / rate - self.od) / (self.do - self.od) * w
            poly = QPolygonF([QPointF(float(cx), float(stred - v * k)) for cx, v in zip(casy, kus)])
            p.drawPolyline(poly)
            if (b - a) < w / 4:
                p.setBrush(barva)
                for pt in poly:
                    p.drawEllipse(pt, 1.5, 1.5)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            self._hrany(p, horni, dolni)

    def _barvy_sloupcu(self, t0: float, krok: float, n: int) -> list[QColor]:
        """Barva vlny v každém sloupci: platforma úseku, šedá mimo data (jako v návrhu)."""
        mimo = QColor(self.palette().mid().color())
        out = [mimo] * n
        for o in self.v.oblasti:
            pl = podle_id(o.platforma) if o.platforma else None
            barva = QColor(pl.barva) if pl else (BARVA_AUDIO if o.nazev == "audio" else BARVA_NEZNAME)
            a = max(0, int((o.zacatek - t0) / krok))
            b = min(n, int((o.konec - t0) / krok) + 1)
            for i in range(a, b):
                out[i] = barva
        return out

    def vzorku_na_pixel(self) -> float:
        return (self.do - self.od) * (self.v.nahravka.rate if self.v else 1) / max(1, self.width())

    def _hrany(self, p: QPainter, horni: int, dolni: int) -> None:
        """Při velkém přiblížení: nalezené přechody signálu (ručně přidané zeleně)."""
        pz = self.v.pulzy
        a, b = np.searchsorted(pz.hrany, [self.od * pz.rate, self.do * pz.rate])
        bezne = (QPen(QColor(242, 169, 59, 230), 1) if self.rezim_upravy
                 else QPen(QColor(217, 139, 18, 120), 1, Qt.PenStyle.DashLine))
        pridane = QPen(QColor("#2EA866"), 2)
        for hr in pz.hrany[a:b]:
            x = self._x(hr / pz.rate)
            p.setPen(pridane if int(hr) in self.pridane else bezne)
            p.drawLine(QPointF(x, horni), QPointF(x, dolni))

    def _bloky(self, p: QPainter, horni: int, dolni: int) -> None:
        if self.do - self.od > 120:
            return
        for s in self.v.soubory:
            if s.konec < self.od or s.zacatek > self.do:
                continue
            for b in s.bloky:
                if b.konec < self.od or b.zacatek > self.do:
                    continue
                a, c = self._x(b.zacatek), self._x(b.konec)
                if not b.ok:
                    p.fillRect(QRectF(a, horni, max(2, c - a), dolni - horni), QColor(239, 91, 91, 60))
                elif b.oprava:
                    p.fillRect(QRectF(a, horni, max(2, c - a), dolni - horni), QColor(242, 193, 78, 50))
                p.setPen(QPen(QColor(0, 0, 0, 70), 1))
                p.drawLine(QPointF(a, horni), QPointF(a, dolni))
                if c - a > 60 and self.do - self.od < 40:
                    p.setPen(self.palette().text().color())
                    popis = f"{b.typ} {b.cislo}" if b.cislo is not None else b.typ
                    p.drawText(QPointF(a + 3, horni + 12), popis + ("" if b.ok else " ✗"))

    # ---- ovládání ----
    def wheelEvent(self, e):
        if not self.v:
            return
        t = self._t(e.position().x())
        f = 0.8 ** (e.angleDelta().y() / 120)
        od = t - (t - self.od) * f
        do = t + (self.do - t) * f
        self._nastav_rozsah(od, do)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._tah = (e.position().x(), self.od, self.do)
            self._posunuto = False
        elif e.button() == Qt.MouseButton.RightButton and self.rezim_upravy and self.v:
            self.uprava.emit(self._t(e.position().x()), True)

    def mouseMoveEvent(self, e):
        if self.v:
            self._mys = self._t(e.position().x())
            self.mys.emit(self._mys)
        if self._tah:
            x0, od, do = self._tah
            dx = e.position().x() - x0
            if abs(dx) > 3:
                self._posunuto = True
            posun = -dx / max(1, self.width()) * (do - od)
            self._nastav_rozsah(od + posun, do + posun)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._tah and not self._posunuto and self.v:
            if self.rezim_upravy:
                self.uprava.emit(self._t(e.position().x()), False)
            else:
                self.klik.emit(self._t(e.position().x()))
        self._tah = None

    def mouseDoubleClickEvent(self, e):
        if self.rezim_upravy:                 # při úpravách by dvojklik zrušil přiblížení
            return
        self.vyber = None
        self.cele()

    def leaveEvent(self, e):
        self._mys = None
        self.mys.emit(math.nan)
        self.update()
