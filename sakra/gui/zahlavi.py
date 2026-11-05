"""Horní část okna podle návrhu: (volitelně) vlastní záhlaví se třemi tečkami, řádek s logem SAKRA,
nabídkou a přepínačem režimů (segmenty), a dialog Nastavení."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import i18n, nastaveni
from ..i18n import tr, tr_data
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
    """Nastavení: vzhled a jazyk, profily pracoviště, složky, umístění konfigurace a import/export.

    Vzhled vrací vysledek(), profily a složky zapíše uloz() (volá okno po OK). Přesun konfigurace a import
    nastavení se provedou hned a nastaví `restart` (okna drží otevřené nastavení – změna platí po restartu)."""

    def __init__(self, n: vzhled.Nastaveni, parent=None, zalozka: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("Nastavení"))
        self.setMinimumWidth(640)
        self.restart = False
        lay = QVBoxLayout(self)
        self.zalozky = QTabWidget()
        lay.addWidget(self.zalozky)
        self.zalozky.addTab(self._vzhled(n), tr("Vzhled"))
        self.zalozky.addTab(self._profily_ui(), tr("Profily pracoviště"))
        self.zalozky.addTab(self._slozky_ui(), tr("Složky"))
        self.zalozky.addTab(self._data_ui(), tr("Nastavení a data"))
        self.zalozky.setCurrentIndex({"profily": 1, "slozky": 2, "data": 3}.get(zalozka, 0))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # ---------------------------------------------------------------- vzhled
    def _vzhled(self, n: vzhled.Nastaveni) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
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
        for x in (self.navrh, self.zahlavi, self.klasicky):
            l2.addWidget(x)
        g3 = QGroupBox("Jazyk / Language")
        l3 = QVBoxLayout(g3)
        self.jazyk = QComboBox()
        for kod, nazev in i18n.JAZYKY.items():
            self.jazyk.addItem(nazev, kod)
        self.jazyk.setCurrentIndex(max(0, self.jazyk.findData(i18n.jazyk())))
        l3.addWidget(self.jazyk)
        l3.addWidget(QLabel(tr("Změna jazyka se projeví po restartu aplikace.")))
        for g in (g1, g2, g3):
            lay.addWidget(g)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- profily pracoviště
    def _profily_ui(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        self._profily = nastaveni.profily()
        self._vychozi = nastaveni.vychozi_profil()
        levy = QVBoxLayout()
        self.seznam_profilu = QListWidget()
        self.seznam_profilu.currentItemChanged.connect(self._vyber_profil)
        levy.addWidget(self.seznam_profilu, 1)
        r = QHBoxLayout()
        for text, fn in ((tr("Nový"), self._novy_profil), (tr("Přejmenovat…"), self._prejmenuj_profil),
                         (tr("Smazat"), self._smaz_profil)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r.addWidget(b)
        levy.addLayout(r)
        r = QHBoxLayout()
        for text, fn in ((tr("Importovat…"), self._importuj_profily), (tr("Exportovat…"), self._exportuj_profily)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r.addWidget(b)
        levy.addLayout(r)
        lay.addLayout(levy, 1)
        pravy = QVBoxLayout()
        f = QFormLayout()
        self.pole_profilu = {}
        for jm, popis in zip(nastaveni.POLE_PROFILU, (tr("Tape-deck (značka)"), tr("Tape-deck (model)"),
                                                      "Sound-card", "DI-box", tr("Autor digitalizace"))):
            e = QLineEdit()
            e.textEdited.connect(self._uprava_profilu)
            f.addRow(popis, e)
            self.pole_profilu[jm] = e
        pravy.addLayout(f)
        self.je_vychozi = QCheckBox(tr("Výchozí profil – předvyplní se do každé nové kazety"))
        self.je_vychozi.setToolTip(tr("Doplní jen prázdné údaje; platí i pro kazety zpracované v Dávkách."))
        self.je_vychozi.toggled.connect(self._prepni_vychozi)
        pravy.addWidget(self.je_vychozi)
        pravy.addStretch(1)
        lay.addLayout(pravy, 2)
        self._obnov_profily()
        return w

    def _obnov_profily(self, vybrat: str | None = None):
        vybrat = vybrat if vybrat is not None else (self.seznam_profilu.currentItem().data(Qt.ItemDataRole.UserRole)
                                                   if self.seznam_profilu.currentItem() else self._vychozi)
        self.seznam_profilu.blockSignals(True)
        self.seznam_profilu.clear()
        for jm in sorted(self._profily, key=str.lower):
            it = QListWidgetItem(("★ " if jm == self._vychozi else "") + jm)
            it.setData(Qt.ItemDataRole.UserRole, jm)
            self.seznam_profilu.addItem(it)
            if jm == vybrat:
                self.seznam_profilu.setCurrentItem(it)
        self.seznam_profilu.blockSignals(False)
        if self.seznam_profilu.currentItem() is None and self.seznam_profilu.count():
            self.seznam_profilu.setCurrentRow(0)
        else:
            self._vyber_profil()

    def _vybrany_profil(self) -> str | None:
        it = self.seznam_profilu.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _vyber_profil(self, *_):
        jm = self._vybrany_profil()
        p = self._profily.get(jm, {}) if jm else {}
        for k, e in self.pole_profilu.items():
            e.setText(p.get(k, ""))
            e.setEnabled(jm is not None)
        self.je_vychozi.blockSignals(True)
        self.je_vychozi.setChecked(jm is not None and jm == self._vychozi)
        self.je_vychozi.setEnabled(jm is not None)
        self.je_vychozi.blockSignals(False)

    def _uprava_profilu(self, *_):
        jm = self._vybrany_profil()
        if jm:
            self._profily[jm] = {k: e.text().strip() for k, e in self.pole_profilu.items()}

    def _prepni_vychozi(self, zapnuto: bool):
        jm = self._vybrany_profil()
        self._vychozi = jm if zapnuto and jm else ("" if jm == self._vychozi else self._vychozi)
        self._obnov_profily(jm)

    def _jmeno_profilu(self, titulek: str, text: str = "") -> str | None:
        jm, ok = QInputDialog.getText(self, titulek, tr("Název profilu (např. Pracoviště 1):"), text=text)
        jm = jm.strip()
        if not ok or not jm:
            return None
        if jm in self._profily and jm != text:
            QMessageBox.warning(self, "SAKRA", tr("Profil „{0}“ už existuje.").format(jm))
            return None
        return jm

    def _novy_profil(self):
        jm = self._jmeno_profilu(tr("Nový profil"))
        if jm:
            self._profily[jm] = {k: "" for k in nastaveni.POLE_PROFILU}
            self._obnov_profily(jm)

    def _prejmenuj_profil(self):
        stare = self._vybrany_profil()
        jm = stare and self._jmeno_profilu(tr("Přejmenovat profil"), stare)
        if jm and jm != stare:
            self._profily[jm] = self._profily.pop(stare)
            if self._vychozi == stare:
                self._vychozi = jm
            self._obnov_profily(jm)

    def _smaz_profil(self):
        jm = self._vybrany_profil()
        if jm and QMessageBox.question(self, "SAKRA", tr("Smazat profil „{0}“?").format(jm)) \
                == QMessageBox.StandardButton.Yes:
            del self._profily[jm]
            if self._vychozi == jm:
                self._vychozi = ""
            self._obnov_profily("")

    def _importuj_profily(self):
        c, _ = QFileDialog.getOpenFileName(self, tr("Importovat profily"), str(Path.home()), tr("JSON (*.json)"))
        if not c:
            return
        try:
            nove, vychozi = nastaveni.precti_profily(c)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "SAKRA", tr_data(str(e)))
            return
        self._profily.update(nove)
        if not self._vychozi and vychozi in self._profily:
            self._vychozi = vychozi
        self._obnov_profily(next(iter(nove), None))
        QMessageBox.information(self, "SAKRA", tr("Načteno profilů: {0}").format(len(nove)))

    def _exportuj_profily(self):
        c, _ = QFileDialog.getSaveFileName(self, tr("Exportovat profily"), str(Path.home() / "SAKRA-profily.json"),
                                           tr("JSON (*.json)"))
        if c:
            nastaveni.zapis_profily(c, self._profily, self._vychozi)

    # ---------------------------------------------------------------- složky
    def _slozky_ui(self) -> QWidget:
        from ..jadro import mezipamet
        w = QWidget()
        lay = QVBoxLayout(w)
        popis = QLabel(tr("Kde aplikace hledá nahrávky a kam ukládá výsledky. Prázdné = výchozí."))
        popis.setWordWrap(True)
        lay.addWidget(popis)
        f = QFormLayout()
        n = nastaveni.nastaveni()
        self.slozky = {}
        for klic, text in nastaveni.SLOZKY:
            e = QLineEdit(str(n.value(klic, "") or ""))
            if klic == "mezipamet/slozka":
                e.setPlaceholderText(str(mezipamet.vychozi_slozka()))
                if os.environ.get("SAKRA_CACHE"):
                    e.setEnabled(False)
                    e.setToolTip(tr("Určeno proměnnou prostředí SAKRA_CACHE"))
            b = QPushButton(tr("Vybrat…"))
            b.clicked.connect(lambda _=False, e=e, t=text: self._vyber_slozku(e, t))
            r = QHBoxLayout()
            r.addWidget(e, 1)
            r.addWidget(b)
            f.addRow(tr(text), r)
            self.slozky[klic] = e
        lay.addLayout(f)
        self.pamatovat = QCheckBox(tr("Pamatovat si naposledy použitou složku"))
        self.pamatovat.setToolTip(tr("Vypnuto: dialogy vždy začnou ve složkách nastavených výše a nemění je."))
        self.pamatovat.setChecked(nastaveni.pamatovat())
        lay.addWidget(self.pamatovat)
        lay.addStretch(1)
        return w

    def _vyber_slozku(self, e: QLineEdit, text: str):
        d = QFileDialog.getExistingDirectory(self, tr(text), e.text() or e.placeholderText() or str(Path.home()))
        if d:
            e.setText(d)

    # ---------------------------------------------------------------- umístění nastavení, import/export, analýzy
    def _data_ui(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox(tr("Soubor s nastavením"))
        lg = QVBoxLayout(g)
        self.umisteni = QLabel()
        self.umisteni.setWordWrap(True)
        self.umisteni.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lg.addWidget(self.umisteni)
        r = QHBoxLayout()
        self.do_souboru = QPushButton(tr("Uložit do souboru…"))
        self.do_souboru.setToolTip(tr("Nastavení se přesune do zvoleného souboru INI (např. na sdílený disk "
                                      "nebo do zálohované složky)"))
        self.do_souboru.clicked.connect(self._do_souboru)
        self.do_systemu = QPushButton(tr("Zpět do systému"))
        self.do_systemu.clicked.connect(lambda: self._presun(None))
        self.otevrit_nastaveni = otevrit = QPushButton(tr("Otevřít složku"))
        otevrit.clicked.connect(self._otevri_slozku_nastaveni)
        for b in (self.do_souboru, self.do_systemu, otevrit):
            r.addWidget(b)
        r.addStretch(1)
        lg.addLayout(r)
        info = QLabel(tr("Přenosná instalace: soubor {0} vedle programu – nastavení pak zůstává u programu "
                         "(např. na USB disku). Jinak lze cestu určit proměnnou prostředí {1}.")
                      .format(nastaveni.PRENOSNY, nastaveni.PROMENNA))
        info.setWordWrap(True)
        info.setStyleSheet("color:#8A93A3")
        lg.addWidget(info)
        lay.addWidget(g)
        g = QGroupBox(tr("Záloha a přenos"))
        lg = QHBoxLayout(g)
        b = QPushButton(tr("Exportovat nastavení…"))
        b.setToolTip(tr("Vzhled, jazyk, profily, složky a volby dialogů do souboru JSON"))
        b.clicked.connect(self._exportuj)
        lg.addWidget(b)
        b = QPushButton(tr("Importovat nastavení…"))
        b.clicked.connect(self._importuj)
        lg.addWidget(b)
        lg.addStretch(1)
        lay.addWidget(g)
        g4 = QGroupBox(tr("Uložené analýzy"))
        l4 = QVBoxLayout(g4)
        popis = QLabel(tr("Hotová analýza strany se ukládá, aby návrat ke kazetě (z dávky, otevření projektu) "
                          "nemusel nahrávku znovu číst a dekódovat. Po změně nahrávky nebo voleb se analyzuje znovu."))
        popis.setWordWrap(True)
        l4.addWidget(popis)
        self.vymazat = QPushButton()
        self.vymazat.clicked.connect(self._vymaz_analyzy)
        l4.addWidget(self.vymazat)
        self._obnov_analyzy()
        lay.addWidget(g4)
        lay.addStretch(1)
        self._obnov_umisteni()
        return w

    def _obnov_umisteni(self):
        druh, cesta = nastaveni.umisteni()
        popis = {"env": tr("určeno proměnnou {0}").format(nastaveni.PROMENNA),
                 "prenosne": tr("přenosná instalace"), "soubor": tr("vlastní soubor"),
                 "system": tr("systémové úložiště")}[druh]
        self.umisteni.setText(f"<b>{popis}</b><br>{cesta}")
        pevne = druh in ("env", "prenosne")
        self.do_souboru.setEnabled(not pevne)
        self.do_systemu.setEnabled(druh == "soubor")
        self.otevrit_nastaveni.setEnabled(not cesta.startswith("\\HKEY"))       # Windows registr není soubor

    def _do_souboru(self):
        c, _ = QFileDialog.getSaveFileName(self, tr("Soubor s nastavením"), str(Path.home() / "SAKRA.ini"),
                                           tr("Nastavení (*.ini)"))
        if c:
            self._presun(c)

    def _presun(self, cil):
        self.uloz()                                   # rozpracované profily a složky jdou s sebou
        nastaveni.presun(cil)
        self.restart = True
        self._obnov_umisteni()

    def _otevri_slozku_nastaveni(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(nastaveni.umisteni()[1]).parent)))

    def _exportuj(self):
        self.uloz()
        c, _ = QFileDialog.getSaveFileName(self, tr("Exportovat nastavení"),
                                           str(Path.home() / "SAKRA-nastaveni.json"), tr("JSON (*.json)"))
        if c:
            n = nastaveni.exportuj(c)
            QMessageBox.information(self, "SAKRA", tr("Uloženo položek: {0}").format(n))

    def _importuj(self):
        c, _ = QFileDialog.getOpenFileName(self, tr("Importovat nastavení"), str(Path.home()), tr("JSON (*.json)"))
        if not c:
            return
        try:
            n = nastaveni.importuj(c)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "SAKRA", tr_data(str(e)))
            return
        self.restart = True
        QMessageBox.information(self, "SAKRA", tr("Načteno položek: {0}. Projeví se po restartu aplikace.").format(n))
        self.reject()                                 # hodnoty dialogu by import přepsaly

    def _obnov_analyzy(self):
        from ..jadro import mezipamet
        d = mezipamet.slozka()
        soubory = list(d.glob("*" + mezipamet.PRIPONA)) if d and d.exists() else []
        mb = sum(f.stat().st_size for f in soubory) / 1024 ** 2
        self.vymazat.setText(tr("Vymazat uložené analýzy ({0} kazetových stran, {1} MB)").format(len(soubory), round(mb)))
        self.vymazat.setEnabled(bool(soubory))
        self.vymazat.setToolTip(str(d) if d else tr("Ukládání analýz je vypnuté (SAKRA_CACHE=0)"))

    def _vymaz_analyzy(self):
        from ..jadro import mezipamet
        mezipamet.vymaz()
        self._obnov_analyzy()

    # ---------------------------------------------------------------- výsledek
    def uloz(self) -> None:
        """Zapíše profily a složky (vzhled a jazyk ukládá okno)."""
        nastaveni.uloz_profily(self._profily, self._vychozi or None)
        n = nastaveni.nastaveni()
        for klic, e in self.slozky.items():
            if e.isEnabled():
                if e.text().strip():
                    n.setValue(klic, e.text().strip())
                else:
                    n.remove(klic)
        n.setValue(nastaveni.PAMATOVAT, self.pamatovat.isChecked())
        n.sync()

    def vybrany_jazyk(self) -> str:
        return self.jazyk.currentData()

    def vysledek(self) -> vzhled.Nastaveni:
        barvy = next(k for k, r in self.barvy.items() if r.isChecked())
        return vzhled.Nastaveni(barvy, "navrh" if self.navrh.isChecked() else "klasicky",
                                self.zahlavi.isChecked() and self.navrh.isChecked())
