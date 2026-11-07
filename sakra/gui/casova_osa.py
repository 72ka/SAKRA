"""Časová osa strany: vlna nahrávky, barevné úseky podle platformy, bloky, výběr, slabá místa signálu.
Kolečko = zoom, tažení = posun, Shift + tažení = výběr úseku, pravé tlačítko = označit výběr jako šum,
hudbu nebo řeč (ruční úseky analýza vynechá)."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QMenu, QToolTip, QWidget

from ..jadro.analyza import VysledekStrany
from ..jadro import audio
from ..jadro.model import DRUHY_ZVUKU, Nosna, cas_text
from ..jadro.slabe import slaba_mista_strany
from ..platformy import bloky_pro_zobrazeni, podle_id
from ..i18n import tr

KROKY = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
BARVA_NEZNAME = QColor("#8A93A3")
BARVA_AUDIO = QColor("#A8B8D8")
BARVA_SLABE = QColor("#F08A24")       # slabé čtení (pokles úrovně)
BARVA_VYPADEK = QColor("#E03A3A")     # výpadek
BARVA_START = QColor("#277DA8")
BARVA_STOP = QColor("#8C55B5")
PRUH_SLABYCH = (42, 46)               # y pruhu slabých míst nad vlnou
BARVY_RUCNI = {"šum": QColor("#9AA0A8"), "hudba": QColor("#9B6BC9"), "řeč": QColor("#3A9E9A")}


class CasovaOsa(QWidget):
    klik = Signal(float)          # čas, kam uživatel klikl
    uprava = Signal(float, bool)  # ruční úprava: čas kliknutí, True = pravé tlačítko (odebrat přechod)
    rozsah = Signal(float, float)  # změna zobrazeného úseku (od, do)
    mys = Signal(float)           # čas pod myší, NaN = myš odešla (None přes signál PySide na Pythonu 3.11 padá)
    oznaceni = Signal(float, float, str)  # ruční úsek od, do, druh (šum/hudba/řeč); "" = zrušit označení

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
        self.bajty_viditelne = True              # přepínatelná vrstva bajtů/start/stop při přiblížení
        self.pridane: set[int] = set()           # ručně přidané přechody (vzorky) – kreslí se zeleně
        self.slaba = []                          # slabá místa signálu (SlabeMisto)
        self.zobrazeni = "vstup"                 # stereo: vstup / levy / pravy / soucet / obe
        self.posun_nahled: float | None = None   # ladění posunu součtu (µs) před novou analýzou
        self._vyber_od: float | None = None      # Shift + tažení: začátek výběru

    # ---- data a pohled ----
    def nastav(self, v: VysledekStrany | None) -> None:
        self.v = v
        self.vyber = None
        self.slaba = slaba_mista_strany(v) if v else []
        self.cele()

    @property
    def delka(self) -> float:
        return self.v.nahravka.delka if self.v else 1.0

    def cele(self) -> None:
        self.od, self.do = 0.0, max(0.01, self.delka)
        self.update()
        self.rozsah.emit(self.od, self.do)

    def nastav_zobrazeni_bajtu(self, zobrazit: bool) -> None:
        self.bajty_viditelne = zobrazit
        self.update()

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
        self._vlny(p, w, horni, dolni)
        self._slaba(p, horni, dolni)
        self._bloky(p, horni, dolni)
        if self.vyber:
            a, b = self._x(self.vyber[0]), self._x(self.vyber[1])
            p.fillRect(QRectF(a, 22, max(2, b - a), h - 22), QColor(242, 169, 59, 50))
            p.setPen(QPen(QColor("#D98B12"), 1))
            p.drawLine(QPointF(a, 22), QPointF(a, h))
            p.drawLine(QPointF(b, 22), QPointF(b, h))
        self._bajty(p, horni, dolni)
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
            if krok >= 1:
                text = cas_text(t)[:5]
            elif krok >= 0.01:
                text = cas_text(t)
            else:                                 # milisekundy (jako cas_text, o řád přesněji)
                text = f"{int(t // 60):02d}:{t % 60:06.3f}"
            p.drawText(QPointF(x + 3, 12), text)
            t += krok

    def _oblasti(self, p: QPainter, w: int) -> None:
        for o in self.v.oblasti:
            if o.konec < self.od or o.zacatek > self.do:
                continue
            pl = podle_id(o.platforma) if o.platforma else None
            barva = self._barva_oblasti(o, pl)
            a, b = self._x(o.zacatek), self._x(o.konec)
            r = QRectF(a, 23, max(2.0, b - a), 18)
            p.fillRect(r, barva)
            if o.rucni:                       # ručně označený úsek: šrafování
                p.fillRect(r, QBrush(QColor(255, 255, 255, 90), Qt.BrushStyle.BDiagPattern))
            if b - a > 30:
                p.setPen(QColor("#ffffff") if pl or o.rucni else QColor("#1F2430"))
                text = o.nazev if pl else ("✎ " + tr(o.nazev) if o.rucni else
                                           tr("zvuk") if o.nazev == "audio" else tr("nerozpoznáno"))
                p.drawText(r.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(b - a - 6)))

        # IBG je rozpoznaná nosná, ale samostatný úsek bez datových bajtů.
        for s in self.v.soubory:
            for b in bloky_pro_zobrazeni(s):
                if not isinstance(b, Nosna) or b.konec < self.od or b.zacatek > self.do:
                    continue
                a, c = self._x(b.zacatek), self._x(b.konec)
                r = QRectF(a, 23, max(2.0, c - a), 18)
                p.fillRect(r, BARVA_NEZNAME)
                if c - a > 30:
                    p.setPen(QColor("#ffffff"))
                    p.drawText(r.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter, b.typ)

    @staticmethod
    def _barva_oblasti(o, pl) -> QColor:
        if o.rucni:
            return BARVY_RUCNI.get(o.nazev, BARVA_AUDIO)
        return QColor(pl.barva) if pl else (BARVA_AUDIO if o.nazev == "audio" else BARVA_NEZNAME)

    def rucni_oblast_v(self, t: float):
        """Ručně označený úsek v čase t, jinak None."""
        return next((o for o in (self.v.oblasti if self.v else []) if o.rucni and o.zacatek <= t <= o.konec), None)

    def _vlny(self, p: QPainter, w: int, horni: int, dolni: int) -> None:
        """Průběh podle volby zobrazení: vstup analýzy, levá / pravá stopa, jejich součet, obě pod sebou."""
        n = self.v.nahravka
        rezim = self.zobrazeni if n.stopy is not None and not self.rezim_upravy else "vstup"
        if rezim == "vstup":
            self._vlna(p, w, horni, dolni)
        elif rezim in ("levy", "pravy"):
            self._vlna(p, w, horni, dolni, n.stopy[:, 0 if rezim == "levy" else 1], hrany=False)
            self._stitek(p, horni, tr("L") if rezim == "levy" else tr("P"))
        elif rezim == "soucet":
            a = max(0, int(self.od * n.rate) - 64)
            b = min(len(n.stopy), int(self.do * n.rate) + 64)
            if b > a:
                kus = audio.soucet(n.stopy[a:b, 0], n.stopy[a:b, 1], self.posun_souctu() * 1e-6 * n.rate)
                self._vlna(p, w, horni, dolni, kus, x0=a, hrany=False)
            self._stitek(p, horni, tr("L+P"))
        else:                                                      # obě stopy pod sebou
            stred = (horni + dolni) // 2
            self._vlna(p, w, horni, stred - 2, n.stopy[:, 0], hrany=False)
            self._vlna(p, w, stred + 2, dolni, n.stopy[:, 1], hrany=False)
            self._stitek(p, horni, tr("L"))
            self._stitek(p, stred + 2, tr("P"))

    def posun_souctu(self) -> float:
        """Posun P proti L (µs) pro zobrazení součtu: použitý při analýze, jinak změřený."""
        if self.posun_nahled is not None:
            return self.posun_nahled
        sig = self.v.strana.signal or {}
        if self.v.nahravka.kanal == audio.SOUCET:
            return float(sig.get("posun_souctu_us") or 0.0)
        return float(self.v.nahravka.posun_us or 0.0)

    def _stitek(self, p: QPainter, y: int, text: str) -> None:
        p.setPen(self.palette().text().color())
        p.drawText(QPointF(4, y + 12), text)

    def _vlna(self, p: QPainter, w: int, horni: int, dolni: int, x=None, x0: int = 0, hrany: bool = True) -> None:
        """Vlna `x` (vzorky od indexu x0; výchozí: vstup analýzy) v pásu horni..dolni."""
        if x is None:
            x = self.v.nahravka.vzorky
        rate = self.v.nahravka.rate
        a = max(x0, int(self.od * rate))
        b = min(x0 + len(x), int(self.do * rate) + 1)
        stred = (horni + dolni) / 2
        vyska = (dolni - horni) / 2
        p.setPen(QPen(self.palette().mid().color(), 1))
        p.drawLine(QPointF(0, stred), QPointF(w, stred))
        if b - a < 2:
            return
        barva = QColor("#3B6FB6")
        p.setPen(QPen(barva, 1))
        kus = x[a - x0:b - x0]
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
            if hrany:
                self._hrany(p, horni, dolni)

    def _slaba(self, p: QPainter, horni: int, dolni: int) -> None:
        """Slabá místa: čárka nad vlnou (oranžová = slabé čtení, červená = výpadek), výpadek i podbarvený."""
        y0, y1 = PRUH_SLABYCH
        for m in self._slaba_v_pohledu():
            a, b = self._x(m.zacatek), self._x(m.konec)
            sirka = max(2.0, b - a)
            barva = BARVA_VYPADEK if m.vypadek else BARVA_SLABE
            p.fillRect(QRectF(a, y0, sirka, y1 - y0), barva)
            if m.vypadek:
                podklad = QColor(barva)
                podklad.setAlpha(28)
                p.fillRect(QRectF(a, horni, sirka, dolni - horni), podklad)

    def _slaba_v_pohledu(self):
        return [m for m in self.slaba if m.konec >= self.od and m.zacatek <= self.do]

    def slabe_misto_v(self, x: float):
        """Slabé místo pod souřadnicí x (s tolerancí 3 px), jinak None."""
        tol = 3 * (self.do - self.od) / max(1, self.width())
        t = self._t(x)
        return next((m for m in self._slaba_v_pohledu() if m.zacatek - tol <= t <= m.konec + tol), None)

    def _barvy_sloupcu(self, t0: float, krok: float, n: int) -> list[QColor]:
        """Barva vlny v každém sloupci: platforma úseku, šedá mimo data (jako v návrhu)."""
        mimo = QColor(self.palette().mid().color())
        out = [mimo] * n
        for o in self.v.oblasti:
            pl = podle_id(o.platforma) if o.platforma else None
            barva = self._barva_oblasti(o, pl)
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
            if s.konec < self.od or s.zacatek_signalu > self.do:
                continue
            for b in bloky_pro_zobrazeni(s):
                if b.konec < self.od or b.zacatek > self.do:
                    continue
                a, c = self._x(b.zacatek), self._x(b.konec)
                if isinstance(b, Nosna):
                    p.fillRect(QRectF(a, horni, max(2, c - a), dolni - horni), QColor(138, 147, 163, 60))
                elif not b.ok:
                    p.fillRect(QRectF(a, horni, max(2, c - a), dolni - horni), QColor(239, 91, 91, 60))
                elif b.oprava:
                    p.fillRect(QRectF(a, horni, max(2, c - a), dolni - horni), QColor(242, 193, 78, 50))
                p.setPen(QPen(QColor(0, 0, 0, 70), 1))
                p.drawLine(QPointF(a, horni), QPointF(a, dolni))
                if c - a > 60 and self.do - self.od < 40:
                    p.setPen(self.palette().text().color())
                    popis = f"{b.typ} {b.cislo}" if b.cislo is not None else b.typ
                    p.drawText(QPointF(a + 3, horni + 12), popis + ("" if b.ok else " ✗"))

    def viditelne_bajty(self):
        """Jen skutečně dekódované rámce s dostatkem místa; IBG žádné rámce nemá."""
        if not self.bajty_viditelne or not self.v or self.do - self.od > 0.25:
            return
        for s in self.v.soubory:
            for b in s.bloky:
                if b.konec <= self.od or b.zacatek >= self.do:
                    continue
                for i, h in enumerate(b.hranice_bitu):
                    if len(h) != 11 or i >= len(b.data) or h[-1] <= self.od or h[0] >= self.do:
                        continue
                    if self._x(h[-1]) - self._x(h[0]) >= 50:
                        yield b, i, h

    def _bajty(self, p: QPainter, horni: int, dolni: int) -> None:
        """Bajt v hexu; START modře, STOP fialově, datové bity v pořadí LSB → MSB."""
        p.save()
        p.setClipRect(QRectF(0, horni + 16, self.width(), max(0, dolni - horni - 16)))
        font = QFont(self.font())
        font.setPointSizeF(8)
        p.setFont(font)
        fm = p.fontMetrics()
        for b, i, h in self.viditelne_bajty():
            x = [self._x(t) for t in h]
            chyba = i in b.chybne_bajty
            barva = QColor("#C0392B") if chyba else self.palette().text().color()
            for q, (a, c) in enumerate(zip(x, x[1:])):
                if c <= 0 or a >= self.width():
                    continue
                role = BARVA_START if q == 0 else BARVA_STOP if q == 9 else None
                if role is not None:
                    pozadi = QColor(role)
                    pozadi.setAlpha(35)
                    p.fillRect(QRectF(a, horni + 32, c - a, dolni - horni - 32), pozadi)
                p.fillRect(QRectF(a, horni + 32, c - a, 16), role or self.palette().alternateBase().color())
                p.setPen(QPen(QColor(125, 135, 150, 110), 1, Qt.PenStyle.DotLine))
                p.drawLine(QPointF(a, horni + 32), QPointF(a, dolni))
                text = "START" if q == 0 else "STOP" if q == 9 else str((b.data[i] >> (q - 1)) & 1)
                if c - a >= fm.horizontalAdvance(text) + 4:
                    p.setPen(QColor("#ffffff") if role is not None else barva)
                    p.drawText(QRectF(a, horni + 32, c - a, 16), Qt.AlignmentFlag.AlignCenter, text)
            p.fillRect(QRectF(x[0], horni + 16, x[-1] - x[0], 16), self.palette().base())
            p.setPen(barva)
            kratky = f"{'! ' if chyba else ''}{b.data[i]:02X}"
            popis = f"#{i} · {kratky}"
            if x[-1] - x[0] < fm.horizontalAdvance(popis) + 6:
                popis = kratky
            p.drawText(QRectF(x[0], horni + 16, x[-1] - x[0], 16), Qt.AlignmentFlag.AlignCenter, popis)
            p.setPen(QPen(barva, 1.5))
            for a in (x[0], x[-1]):
                p.drawLine(QPointF(a, horni + 16), QPointF(a, dolni))
        p.restore()

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
        if (e.button() == Qt.MouseButton.LeftButton and self.v and not self.rezim_upravy
                and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._vyber_od = self._t(e.position().x())          # Shift + tažení: výběr úseku
            self.vyber = None
        elif e.button() == Qt.MouseButton.LeftButton:
            self._tah = (e.position().x(), self.od, self.do)
            self._posunuto = False
        elif e.button() == Qt.MouseButton.RightButton and self.rezim_upravy and self.v:
            self.uprava.emit(self._t(e.position().x()), True)
        elif e.button() == Qt.MouseButton.RightButton and self.v:
            self._nabidka(e)

    def _nabidka(self, e) -> None:
        """Pravé tlačítko: označit výběr jako šum / hudbu / řeč, zrušit ruční označení pod myší."""
        self.sestav_nabidku(self._t(e.position().x())).exec(e.globalPosition().toPoint())

    def sestav_nabidku(self, t: float) -> QMenu:
        m = QMenu(self)
        if self.vyber and self.vyber[1] - self.vyber[0] > 0.01:
            od, do = self.vyber
            m.addSection(tr("Výběr {0} – {1}").format(cas_text(od), cas_text(do)))
            for druh in DRUHY_ZVUKU:
                m.addAction(tr("Označit jako: {0}").format(tr(druh)),
                            lambda d=druh, od=od, do=do: self.oznaceni.emit(od, do, d))
        else:
            a = m.addAction(tr("Úsek vyberte Shift + tažením (nebo klikněte na program)"))
            a.setEnabled(False)
        o = self.rucni_oblast_v(t)
        if o is not None:
            m.addSeparator()
            m.addAction(tr("Zrušit označení „{0}“").format(tr(o.nazev)),
                        lambda o=o: self.oznaceni.emit(o.zacatek, o.konec, ""))
        return m

    def mouseMoveEvent(self, e):
        if self.v:
            self._mys = self._t(e.position().x())
            self.mys.emit(self._mys)
        if self._vyber_od is not None:
            t = self._t(e.position().x())
            self.vyber = (min(self._vyber_od, t), max(self._vyber_od, t))
        elif self._tah:
            x0, od, do = self._tah
            dx = e.position().x() - x0
            if abs(dx) > 3:
                self._posunuto = True
            posun = -dx / max(1, self.width()) * (do - od)
            self._nastav_rozsah(od + posun, do + posun)
        elif self.v:
            self._bublina_slabeho(e)
        self.update()

    def _bublina_slabeho(self, e) -> None:
        """Nad pruhem slabých míst (a pár bodů kolem) ukáže, jak moc signál klesl."""
        y0, y1 = PRUH_SLABYCH
        m = self.slabe_misto_v(e.position().x()) if y0 - 4 <= e.position().y() <= y1 + 4 else None
        if m is None:
            QToolTip.hideText()
            return
        druh = tr("Výpadek signálu") if m.vypadek else tr("Slabé čtení")
        text = tr("{0}: úroveň {1} % okolí, {2} ms").format(druh, round(m.uroven * 100),
                                                           max(1, round((m.konec - m.zacatek) * 1000)))
        QToolTip.showText(e.globalPosition().toPoint(), text, self)

    def mouseReleaseEvent(self, e):
        if self._vyber_od is not None:
            self._vyber_od = None
            if self.vyber and self.vyber[1] - self.vyber[0] < 0.005:
                self.vyber = None
            self.update()
            return
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
