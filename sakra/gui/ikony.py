"""Ikony platforem kreslené programem (jednotný styl v celé aplikaci).

Zaoblený čtverec v barvě platformy se zkratkou počítače; podle druhu stroje drobný motiv: klávesnice
(domácí počítač), kufřík s držadlem (ŠMS VÚVT, POTAS), deska s čipy (PMI-80). Zvláštní ikony: automatické
rozpoznání, nerozpoznaný úsek, žádná data. Nekreslí se loga výrobců – jen zkratka a barva.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from ..jadro.model import VOLBY_ZVUKU, ZADNA_DATA
from ..platformy import VSECHNY, podle_id

AUTO = "auto"
NEROZPOZNANO = "nerozpoznano"
ZADNA = "zadna_data"

# počítač -> (zkratka, barva, motiv); barvy z modulů platforem, ostatní doplněné
_STYL: dict[str, tuple[str, str, str]] = {
    "Ondra SPO 186": ("ON", "", "klavesnice"),
    "SAPI-1": ("S1", "", "klavesnice"),
    "ZX Spectrum": ("ZX", "", "klavesnice"),
    "ZX81": ("81", "", "klavesnice"),
    "PMD 85": ("PMD", "", "klavesnice"),
    "Maťo": ("MA", "", "klavesnice"),
    "IQ 151": ("IQ", "", "klavesnice"),
    "Commodore 64": ("64", "", "klavesnice"),
    "Commodore C16/Plus4": ("16", "#8E7CC3", "klavesnice"),
    "POTAS": ("PT", "", "kufr"),
    "ŠMS VÚVT": ("ŠMS", "", "kufr"),
    "MSX": ("MSX", "", "klavesnice"),
    "BBC Micro / Acorn Electron": ("BBC", "", "klavesnice"),
    "Oric": ("OR", "", "klavesnice"),
    "Sord m5": ("M5", "", "klavesnice"),
    "Atari 8bit": ("A8", "", "klavesnice"),
    "Amstrad CPC": ("CPC", "", "klavesnice"),
    "Sharp MZ-700/800": ("MZ", "", "klavesnice"),
    "PMI-80": ("PMI", "#5D7A8C", "deska"),
    "jiná": ("…", "#8A93A3", "klavesnice"),
}
_SEDA = "#8A93A3"
_cache: dict[tuple[str, int, float], QPixmap] = {}
_soubory: dict[tuple[str, int], str] = {}
_slozka: Path | None = None


def _barva_pocitace(pocitac: str) -> str:
    vlastni = _STYL.get(pocitac, ("", "", ""))[1]
    if vlastni:
        return vlastni
    return next((p.barva for p in VSECHNY if p.pocitac == pocitac), _SEDA)


def klic(hodnota: str | None) -> str:
    """Id platformy, název počítače, ruční volba („ZX Spectrum“, „žádná data…“) nebo ""/"?" -> klíč
    ikony."""
    if not hodnota or hodnota in ("?", "(neznámá)", "(nerozpoznáno)"):
        return NEROZPOZNANO
    if hodnota in (ZADNA_DATA, "žádná data", "audio", ZADNA, *VOLBY_ZVUKU):
        return ZADNA
    if hodnota in (AUTO, NEROZPOZNANO):
        return hodnota
    pl = podle_id(hodnota)
    if pl is not None:
        return pl.pocitac
    for p in VSECHNY:                    # celý název s variantou („Ondra SPO 186 – Tesla ROM“)
        if hodnota == p.nazev:
            return p.pocitac
    return hodnota


def klic_zaznamu(z) -> str:
    """Klíč ikony pro záznam obsahu pásky."""
    if z.soubor is not None:
        return klic(z.soubor.platforma)
    if z.typ == "Audio":
        return ZADNA
    return klic(z.platforma)


def _motiv(p: QPainter, motiv: str, k: float, s: float) -> None:
    bila = QColor(255, 255, 255, 215)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bila)
    if motiv == "klavesnice":                    # dvě řady kláves dole
        sirka, mezera = 6.2 * k, 1.6 * k
        for rada, (y, odsazeni, pocet) in enumerate(((43 * k, 9 * k, 6), (50.5 * k, 12 * k, 5))):
            for i in range(pocet):
                p.drawRoundedRect(QRectF(odsazeni + i * (sirka + mezera), y, sirka, 5 * k), 1.2 * k, 1.2 * k)
        p.drawRoundedRect(QRectF(19 * k, 57 * k, 26 * k, 3 * k), 1.2 * k, 1.2 * k)     # mezerník
    elif motiv == "kufr":                        # držadlo nahoře a zámky dole
        pero = QPen(bila, 3 * k)
        pero.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pero)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cesta = QPainterPath(QPointF(23 * k, 11 * k))
        cesta.cubicTo(QPointF(23 * k, 4 * k), QPointF(41 * k, 4 * k), QPointF(41 * k, 11 * k))
        p.drawPath(cesta)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bila)
        p.drawRect(QRectF(8 * k, 47 * k, 48 * k, 2.2 * k))
        for x in (14 * k, 44 * k):
            p.drawRoundedRect(QRectF(x, 51 * k, 6 * k, 6 * k), 1.2 * k, 1.2 * k)
    elif motiv == "deska":                       # čip s vývody
        p.drawRoundedRect(QRectF(18 * k, 44 * k, 28 * k, 12 * k), 1.5 * k, 1.5 * k)
        for i in range(6):
            x = 20 * k + i * 4.3 * k
            p.drawRect(QRectF(x, 40.5 * k, 1.8 * k, 3 * k))
            p.drawRect(QRectF(x, 56.5 * k, 1.8 * k, 3 * k))


def _kresli(klic_: str, s: int) -> QPixmap:
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    k = s / 64
    if klic_ == AUTO:
        barva, zkratka, motiv = "#F2A93B", "", "auto"
    elif klic_ == NEROZPOZNANO:
        barva, zkratka, motiv = _SEDA, "?", ""
    elif klic_ == ZADNA:
        barva, zkratka, motiv = "#A7AEBB", "♪", ""
    else:
        zkratka, _, motiv = _STYL.get(klic_, (klic_[:3].upper(), "", "klavesnice"))
        barva = _barva_pocitace(klic_)
    zaklad = QColor(barva)
    gr = QLinearGradient(0, 0, 0, s)
    gr.setColorAt(0, zaklad.lighter(118))
    gr.setColorAt(1, zaklad.darker(112))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gr))
    p.drawRoundedRect(QRectF(0.5 * k, 0.5 * k, 63 * k, 63 * k), 14 * k, 14 * k)
    podrobne = s >= 28 and motiv
    if motiv == "auto":                          # vlna signálu a lupa
        pero = QPen(QColor("white"), 3.4 * k)
        pero.setCapStyle(Qt.PenCapStyle.RoundCap)
        pero.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pero)
        cesta = QPainterPath(QPointF(8 * k, 30 * k))
        for i, (x, y) in enumerate(((14, 30), (14, 18), (22, 18), (22, 42), (30, 42), (30, 24), (36, 24))):
            cesta.lineTo(QPointF(x * k, y * k))
        p.drawPath(cesta)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(42 * k, 36 * k), 10 * k, 10 * k)
        p.drawLine(QPointF(49.5 * k, 43.5 * k), QPointF(57 * k, 51 * k))
    else:
        if podrobne:
            _motiv(p, motiv, k, s)
        f = QFont()
        f.setBold(True)
        delka = len(zkratka)
        velikost = (30 if delka <= 2 else 21) if podrobne else (36 if delka <= 1 else 30 if delka <= 2 else 22)
        if podrobne and motiv == "kufr":
            velikost = 25 if delka <= 2 else 19
        if zkratka == "♪":
            velikost = 38
        f.setPixelSize(max(6, int(velikost * k)))
        p.setFont(f)
        p.setPen(QColor("white"))
        oblast = QRectF(0, (17 if motiv == "kufr" else 6) * k, s, (27 if motiv == "kufr" else 28) * k) if podrobne \
            else QRectF(0, 0, s, s)
        p.drawText(oblast, Qt.AlignmentFlag.AlignCenter, zkratka)
    p.end()
    return pm


def pixmapa(hodnota: str | None, velikost: int = 32, dpr: float = 1.0) -> QPixmap:
    """Ikona jako QPixmap (`hodnota` viz klic())."""
    k = klic(hodnota)
    pk = (k, velikost, dpr)
    if pk not in _cache:
        pm = _kresli(k, max(8, int(round(velikost * dpr))))
        pm.setDevicePixelRatio(dpr)
        _cache[pk] = pm
    return _cache[pk]


def ikona(hodnota: str | None) -> QIcon:
    ik = QIcon()
    for n in (16, 20, 24, 32, 48, 64):
        ik.addPixmap(pixmapa(hodnota, n))
    return ik


def soubor(hodnota: str | None, velikost: int = 16) -> str:
    """Cesta k PNG ikony (pro HTML v QLabel / QTextBrowser); kreslí se dvojnásobně kvůli ostrosti."""
    global _slozka
    k = klic(hodnota)
    if (k, velikost) not in _soubory:
        if _slozka is None:
            _slozka = Path(tempfile.mkdtemp(prefix="sakra-ikony-"))
        cesta = _slozka / f"{abs(hash(k)) & 0xFFFFFFFF:08x}-{velikost}.png"
        _kresli(k, velikost * 2).save(str(cesta))
        _soubory[(k, velikost)] = str(cesta)
    return _soubory[(k, velikost)]


def html(hodnota: str | None, velikost: int = 16) -> str:
    """<img> ikony pro rich text."""
    return f"<img src='{soubor(hodnota, velikost)}' width={velikost} height={velikost} style='vertical-align:middle'>"
