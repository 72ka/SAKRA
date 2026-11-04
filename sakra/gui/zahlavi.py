"""Horní část okna podle návrhu: (volitelně) vlastní záhlaví se třemi tečkami, řádek s logem SAKRA,
nabídkou a přepínačem režimů (segmenty), a dialog Nastavení vzhledu."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..i18n import tr
from . import vzhled


class Tecka(QPushButton):
    def __init__(self, barva: str, tip: str):
        super().__init__()
        self.setFixedSize(QSize(12, 12))
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(f"QPushButton{{background:{barva};border:none;border-radius:6px;padding:0;min-width:12px;"
                           f"max-width:12px;min-height:12px;max-height:12px}}QPushButton:hover{{border:1px solid rgba(0,0,0,70)}}")


class Zahlavi(QWidget):
    """Kontejner pro QMainWindow.setMenuWidget()."""

    def __init__(self, okno, menu: QMenuBar, rezimy: list[tuple[str, str]], prepni):
        super().__init__(okno)
        self.okno = okno
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1) záhlaví okna ve stylu návrhu (bez rámu systému)
        self.titulek = QWidget()
        self.titulek.setObjectName("zahlavi")
        self.titulek.setFixedHeight(34)
        lt = QHBoxLayout(self.titulek)
        lt.setContentsMargins(14, 0, 14, 0)
        lt.setSpacing(7)
        zavrit, min_, max_ = (
            Tecka("#FF5F57", tr("Zavřít")),
            Tecka("#FEBC2E", tr("Minimalizovat")),
            Tecka("#28C840", tr("Maximalizovat")),
        )
        zavrit.clicked.connect(okno.close)
        min_.clicked.connect(okno.showMinimized)
        max_.clicked.connect(self._maximalizuj)
        for t in (zavrit, min_, max_):
            lt.addWidget(t)
        self.nazev = QLabel()
        self.nazev.setObjectName("titulek_okna")
        self.nazev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lt.addWidget(self.nazev, 1)
        lt.addSpacing(50)
        okno.windowTitleChanged.connect(self.nazev.setText)
        self.titulek.hide()
        lay.addWidget(self.titulek)

        # 2) logo, nabídka, přepínač režimů
        radek = QWidget()
        radek.setObjectName("menu_radek")
        lr = QHBoxLayout(radek)
        lr.setContentsMargins(12, 4, 12, 4)
        lr.setSpacing(8)
        from .aplikace import ikona_zahlavi
        logo = QLabel()
        logo.setPixmap(ikona_zahlavi(26, self.devicePixelRatioF()))
        text = QLabel("SAKRA")
        f = QFont(text.font())
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
        f.setPointSizeF(f.pointSizeF() + 1.5)
        text.setFont(f)
        text.setStyleSheet(f"color:{vzhled.JANTAR}")
        lr.addWidget(logo)
        lr.addWidget(text)
        lr.addSpacing(10)
        menu.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        lr.addWidget(menu)
        lr.addStretch(1)
        seg = QFrame()
        seg.setObjectName("segmenty")
        ls = QHBoxLayout(seg)
        ls.setContentsMargins(3, 3, 3, 3)
        ls.setSpacing(2)
        self.segmenty = {}
        skupina = QButtonGroup(self)
        for klic, popis in rezimy:
            b = QPushButton(popis)
            b.setObjectName("segment")
            tucne = QFont(b.font())
            tucne.setBold(True)
            from PySide6.QtGui import QFontMetrics
            b.setMinimumWidth(QFontMetrics(tucne).horizontalAdvance(popis) + 30)   # vybraný segment je tučně
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=klic: prepni(k))
            skupina.addButton(b)
            ls.addWidget(b)
            self.segmenty[klic] = b
        lr.addWidget(seg)
        lay.addWidget(radek)
        self._tah = None

    def nastav_rezim(self, klic: str) -> None:
        if klic in self.segmenty:
            self.segmenty[klic].setChecked(True)

    def _maximalizuj(self):
        self.okno.showNormal() if self.okno.isMaximized() else self.okno.showMaximized()

    # přesun okna za vlastní záhlaví a dvojklik = maximalizace
    def mousePressEvent(self, e):
        if self.titulek.isVisible() and e.button() == Qt.MouseButton.LeftButton and \
                self.titulek.geometry().contains(e.position().toPoint()):
            h = self.okno.windowHandle()
            if h is not None:
                h.startSystemMove()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.titulek.isVisible() and self.titulek.geometry().contains(e.position().toPoint()):
            self._maximalizuj()
        super().mouseDoubleClickEvent(e)


class DialogNastaveni(QDialog):
    def __init__(self, n: vzhled.Nastaveni, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Nastavení"))
        lay = QVBoxLayout(self)
        g1 = QGroupBox(tr("Barvy"))
        l1 = QVBoxLayout(g1)
        self.barvy = {}
        for k, t in (("system", tr("Podle systému")), ("svetle", tr("Světlé")), ("tmave", tr("Tmavé"))):
            r = QRadioButton(t)
            r.setChecked(n.barvy == k)
            l1.addWidget(r)
            self.barvy[k] = r
        g2 = QGroupBox(tr("Styl"))
        l2 = QVBoxLayout(g2)
        self.navrh = QRadioButton(tr("Moderní (zaoblené panely, jantarová tlačítka, přepínač režimů jako segmenty)"))
        self.klasicky = QRadioButton(tr("Klasický (Fusion)"))
        (self.navrh if n.styl == "navrh" else self.klasicky).setChecked(True)
        self.zahlavi = QCheckBox(tr("Vlastní záhlaví okna (tři barevné tečky místo rámu systému)"))
        self.zahlavi.setChecked(n.zahlavi)
        self.zahlavi.setToolTip(tr("Velikost okna pak jde měnit úchytem vpravo dole nebo dvojklikem na záhlaví."))
        self.navrh.toggled.connect(self.zahlavi.setEnabled)
        self.zahlavi.setEnabled(n.styl == "navrh")
        for w in (self.navrh, self.zahlavi, self.klasicky):
            l2.addWidget(w)
        g3 = QGroupBox("Jazyk / Language")
        l3 = QVBoxLayout(g3)
        self.jazyk = QComboBox()
        for kod, nazev in i18n.JAZYKY.items():
            self.jazyk.addItem(nazev, kod)
        self.jazyk.setCurrentIndex(max(0, self.jazyk.findData(i18n.jazyk())))
        l3.addWidget(self.jazyk)
        l3.addWidget(QLabel(tr("Změna jazyka se projeví po restartu aplikace.")))
        lay.addWidget(g1)
        lay.addWidget(g2)
        lay.addWidget(g3)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def vybrany_jazyk(self) -> str:
        return self.jazyk.currentData()

    def vysledek(self) -> vzhled.Nastaveni:
        barvy = next(k for k, r in self.barvy.items() if r.isChecked())
        return vzhled.Nastaveni(barvy, "navrh" if self.navrh.isChecked() else "klasicky",
                                self.zahlavi.isChecked() and self.navrh.isChecked())
