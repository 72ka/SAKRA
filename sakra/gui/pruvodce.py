"""Průvodce digitalizací (návrh A): šest kroků pro dobrovolníky. Výsledek se dá otevřít na Pracovním stole."""
from __future__ import annotations

import html
from pathlib import Path

import shiboken6
import soundfile as sf
from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                               QScrollArea, QSpinBox, QStackedWidget, QStyle, QStyledItemDelegate, QTableView,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from .. import AKRONYM, AUTORSTVI, WEB, __version__
from ..jadro.analyza import popis_stavu
from ..jadro.model import DRUHY_ZVUKU, VOLBY_ZVUKU, ZADNA_DATA, Zaznam, cas_text, urci_platformu
from ..jadro.texty import pocet
from ..platformy import RUCNI, podle_id
from ..projekt import cislo_strany, inventarni_cislo
from .. import nastaveni
from ..i18n import tr, tr_data
from . import ikony, vzhled
from .karta import KartaKazety, posuvne
from .obsah import SLOUPCE, STAVY, VolbyDelegat
from .vyber_platformy import POPIS, VyberPlatformy

KROKY = [
    (tr("Nahrávka"), tr("soubory stran")),
    (tr("Kazeta"), tr("údaje do evidence")),
    (tr("Platforma"), tr("co je na pásce")),
    (tr("Programy"), tr("názvy a obsah")),
    (tr("Kontrola"), tr("chyby a opravy")),
    (tr("Uložit do archivu"), tr("balíček a protokol")),
]
NAPOVEDA = [
    (
        tr(
            "Každou stranu kazety nahrajte do samostatného souboru WAV nebo FLAC. Stranu SAKRA pozná z názvu („HH08518 "
            "(1).wav“, „… strana B.wav“), jinak ji nastavte v tabulce."
        ),
        [
            tr("Nahrávejte bez úprav – bez filtrů, normalizace a komprese."),
            tr("Inventární číslo pojmenuje balíček i soubory."),
            tr("Soubory můžete do okna i přetáhnout."),
        ],
    ),
    (
        tr(
            "Údaje o pracovišti a kazetě jdou do hlavičky tabulky Herního archivu. Uložený profil pracoviště vyplní "
            "magnetofon, převodník a autora jedním kliknutím."
        ),
        [
            tr("Vzorkování a formát se vyplní z nahrávky."),
            tr("Fotky kazety se uloží do balíčku a vytisknou v protokolu."),
        ],
    ),
    (
        tr(
            "Každý počítač ukládal data na kazetu jinak. SAKRA podle tvaru signálu odhadne platformu a potvrdí ji tím, že "
            "přečte hlavičku souboru se správným kontrolním součtem."
        ),
        [
            tr("Na jedné kazetě může být víc počítačů – to je v pořádku."),
            tr("Když si nejste jistí, úsek si pusťte."),
            tr(
                "Nerozpoznané úseky se uloží jako přesný záznam pulzů (CSW) – nic se neztratí a dají se dekódovat později."
            ),
        ],
    ),
    (
        tr(
            "Seznam programů tak, jak je SAKRA přečetla. Doplňte nebo opravte název a vyberte, co program obsahuje (Hra, "
            "Program, Data…)."
        ),
        [
            tr("Sloupce s rozbalovacím seznamem nabízejí hodnoty podle vzoru Herního archivu."),
            tr("Názvy z hlaviček zůstanou ve sloupci „Název bloku“."),
        ],
    ),
    (
        tr("Tady je všechno, co potřebuje lidské oko: poškozené bloky, opravy z kopií a úseky bez platformy."),
        [
            tr("Poškozený program často opraví druhá kopie na kazetě – nahrajte i druhou stranu."),
            tr("„Bez součtu“ znamená, že formát nemá kontrolní součet; úplnost je ověřená jen délkou."),
            tr("Podrobnosti ukáže Pracovní stůl."),
        ],
    ),
    (
        tr(
            "Archivní balíček je jeden soubor 7z (nebo složka) pojmenovaný inventárním číslem: programy ve "
            "formátech pro emulátory, výřezy WAV, bezztrátová kopie nahrávky, tabulka podle vzoru, protokol "
            "(HTML a PDF) a kontrolní součty."
        ),
        [
            tr("Hotový balíček se dá kdykoli vytvořit znovu z uloženého projektu."),
            tr("Pracovní stůl ukáže výsledek podrobně, včetně vlny nahrávky."),
        ],
    ),
]


def _karta_ramecek(stav: str = "") -> QFrame:
    """Karta (rámeček se zaoblenými rohy); `stav` pozor/chyba = barevný okraj jako v návrhu."""
    f = QFrame()
    f.setObjectName("karta")
    f.setProperty("stav", stav)
    if not vzhled.je_navrh():
        okraj = {"pozor": "2px solid #F2C14E", "chyba": "2px solid #EF5B5B"}.get(stav, "1px solid palette(mid)")
        f.setStyleSheet(f"QFrame#karta{{border:{okraj};border-radius:6px;background:palette(base)}}"
                        "QFrame#karta QLabel{border:none;background:transparent}")
    return f


def _znacka(hodnota: str | None, velikost: int = 56) -> QLabel:
    """Ikona platformy (počítač, nerozpoznáno, žádná data) – viz ikony.py."""
    z = QLabel()
    z.setPixmap(ikony.pixmapa(hodnota, velikost, z.devicePixelRatioF()))
    z.setFixedSize(velikost, velikost)
    return z


class KrokDelegat(QStyledItemDelegate):
    """Krok průvodce jako v návrhu: kroužek (✓ / číslo), tučný název, šedý podtitul."""

    def __init__(self, pruvodce):
        super().__init__(pruvodce)
        self.p = pruvodce

    def sizeHint(self, option, index):
        return QSize(200, 58)

    def paint(self, painter: QPainter, option, index):
        i = index.row()
        nazev, pod = KROKY[i]
        r = QRectF(option.rect).adjusted(4, 3, -4, -3)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = option.palette
        if i == self.p.krok:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(vzhled.barvy()["vyber"]))
            painter.drawRoundedRect(r, 10, 10)
        hotovo, akt = i < self.p.krok, i == self.p.krok
        dostupny = i <= self.p.navstiveno
        kruh = QRectF(r.left() + 8, r.center().y() - 15, 30, 30)
        if hotovo:
            painter.setBrush(QColor("#2EA866" if vzhled.je_tmave() else "#DDF3E6"))
            barva_textu = QColor("#FFFFFF" if vzhled.je_tmave() else "#2EA866")
        elif akt:
            painter.setBrush(QColor(vzhled.JANTAR))
            barva_textu = QColor("#FFFFFF")
        else:
            painter.setBrush(QColor(vzhled.barvy()["okraj"]))
            barva_textu = QColor(vzhled.barvy()["slaby"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(kruh)
        f = QFont(option.font)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QPen(barva_textu))
        painter.drawText(kruh, Qt.AlignmentFlag.AlignCenter, "✓" if hotovo else str(i + 1))
        text = pal.text().color() if dostupny else QColor(vzhled.barvy()["slaby"])
        painter.setPen(text)
        x = kruh.right() + 12
        painter.drawText(QRectF(x, r.top() + 8, r.right() - x, 20), Qt.AlignmentFlag.AlignLeft, nazev)
        f.setBold(False)
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        painter.setFont(f)
        painter.setPen(QColor(vzhled.barvy()["slaby"]))
        painter.drawText(QRectF(x, r.top() + 28, r.right() - x, 18), Qt.AlignmentFlag.AlignLeft, pod)
        painter.restore()


class Pruvodce(QWidget):
    def __init__(self, okno, parent=None):
        super().__init__(parent)
        self.okno = okno
        self.nastaveni = nastaveni.nastaveni()
        self.setAcceptDrops(True)
        self.soubory: list[Path] = []
        self._analyzovano: tuple | None = None
        self._hraje: QPushButton | None = None      # tlačítko, jehož úsek se právě přehrává
        okno.prehravani_skoncilo.connect(self._poslech_skoncil)
        self.krok = 0
        self.navstiveno = 0

        # kroky vlevo
        self.seznam = QListWidget()
        self.seznam.setObjectName("kroky")
        self.seznam.setItemDelegate(KrokDelegat(self))
        self.seznam.setMinimumWidth(170)
        self.seznam.setMaximumWidth(250)
        self.seznam.currentRowChanged.connect(self._klik_na_krok)
        # obsah
        self.stranky = QStackedWidget()
        for tvorba in (self._s_nahravka, self._s_kazeta, self._s_platforma, self._s_programy, self._s_kontrola,
                       self._s_ulozit):
            self.stranky.addWidget(posuvne(tvorba()))
        # nápověda vpravo
        self.napoveda = QTextBrowser()
        self.napoveda.setObjectName("napoveda")
        self.napoveda.setMinimumWidth(160)
        self.napoveda.setMaximumWidth(300)
        self.napoveda.setOpenLinks(False)
        self.napoveda.anchorClicked.connect(self._odkaz)
        # spodní lišta
        self.popis_kroku = QLabel()
        self.ukazatel = QProgressBar()
        self.ukazatel.setRange(0, len(KROKY))
        self.ukazatel.setMaximumWidth(260)
        self.ukazatel.setMaximumHeight(8)
        self.ukazatel.setTextVisible(False)
        self.ukazatel.setProperty("bez_textu", True)
        self.zpet = QPushButton(tr("← Zpět"))
        self.zpet.clicked.connect(lambda: self.jdi(self.krok - 1))
        self.dale = QPushButton()
        self.dale.setDefault(True)
        self.dale.setProperty("primarni", True)
        self.dale.setMinimumHeight(36)
        self.zpet.setMinimumHeight(36)
        self.dale.clicked.connect(lambda: self.jdi(self.krok + 1))
        dole = QHBoxLayout()
        dole.addWidget(self.popis_kroku)
        dole.addWidget(self.ukazatel)
        dole.addStretch(1)
        dole.addWidget(self.zpet)
        dole.addWidget(self.dale)

        stred = QVBoxLayout()
        stred.setContentsMargins(18, 14, 18, 10)
        stred.addWidget(self.stranky, 1)
        stred.addLayout(dole)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.seznam)
        lay.addLayout(stred, 1)
        lay.addWidget(self.napoveda)
        self.jdi(0)

    # ------------------------------------------------------------ poslech úseku
    POSLECH, ZASTAVIT = tr("▶ Poslechnout"), tr("■ Zastavit")

    def _tlacitko_poslechu(self, strana: int, od: float, do: float) -> QPushButton:
        """Tlačítko pro poslech (nejvýš 20 s úseku); během přehrávání ho zastaví."""
        b = QPushButton(self.POSLECH)
        b.clicked.connect(lambda _=False: self._poslech(b, strana, od, min(do, od + 20)))
        return b

    def _poslech(self, b: QPushButton, strana: int, od: float, do: float):
        if self._hraje is b:
            self.okno.zastav_prehravani()             # -> _poslech_skoncil
            return
        if self._hraje is not None:
            self.okno.zastav_prehravani()
        if self.okno.prehraj(strana, od, do):
            self._hraje = b
            b.setText(self.ZASTAVIT)

    def _poslech_skoncil(self):
        b, self._hraje = self._hraje, None
        if b is not None and shiboken6.isValid(b):     # stránka mohla být mezitím postavena znovu
            b.setText(self.POSLECH)

    def _odkaz(self, url: QUrl):
        if url.toString() == "sakra:navod":
            self.okno.otevri_navod()
        else:
            QDesktopServices.openUrl(url)

    # ------------------------------------------------------------ navigace
    def _obnov_seznam(self):
        self.seznam.blockSignals(True)
        self.seznam.clear()
        for i, (nazev, pod) in enumerate(KROKY):
            it = QListWidgetItem(nazev)
            if i > self.navstiveno:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.seznam.addItem(it)
        self.seznam.setCurrentRow(self.krok)
        self.seznam.blockSignals(False)

    def _klik_na_krok(self, i: int):
        self.seznam.viewport().update()
        if 0 <= i <= self.navstiveno:
            self.jdi(i)

    def jdi(self, i: int):
        if i < 0 or i >= len(KROKY):
            return
        if i > self.krok and not self._muze_dal():
            return
        self.krok = i
        self.navstiveno = max(self.navstiveno, i)
        self.stranky.setCurrentIndex(i)
        uvod, tipy = NAPOVEDA[i]
        nadpis = lambda t: (
            tr("<p style='margin:16px 0 6px;color:#8A93A3;font-size:11px;font-weight:bold'>{0}</p>").format(t.upper())
        )
        k = self.okno.kazeta
        strany = [s for s in k.strany if s.nahravka]
        udaje = [(tr("Kazeta"), k.inventar.cislo or "–"),
                 (tr("Nahrávka"), strany[0].vzorkovani + (" · " + strany[0].format if strany[0].format else "")
                  if strany else ", ".join(c.name for c in self.soubory[:2]) or "–"),
                 (tr("Délka"), " · ".join(f"{s.cislo}: {cas_text(s.delka)[:5]}" for s in strany) or "–")]
        okraj = vzhled.barvy()["okraj"]
        self.napoveda.setHtml(
            tr("<table width='100%' cellpadding=4 style='border:1px solid {0};border-radius:8px'>").format(okraj)
            + "".join(f"<tr><td style='color:#8A93A3'>{a}</td><td><b>{html.escape(b)}</b></td></tr>" for a, b in udaje)
            + "</table>"
            + nadpis(tr("Co se děje v tomto kroku"))
            + f"<p>{html.escape(uvod)}</p>"
            + nadpis(tr("Tipy"))
            + tr("<ul style='margin-left:-20px'>")
            + "".join(f"<li>{html.escape(t)}</li>" for t in tipy)
            + "</ul>"
            + nadpis(tr("Potřebujete víc?"))
            + tr(
                "<p>Přepínačem <b>Pracovní stůl</b> nahoře se dostanete k podrobnému "
                "zobrazení se vším, co SAKRA o kazetě ví.</p><p>Podrobný <a "
                "href='sakra:navod'>návod v PDF</a> (Nápověda → Návod, F1).</p><p "
                "style='margin-top:18px;color:#8A93A3;font-size:11px'>SAKRA "
                "{0}<br><i>{1}</i><br>{2}<br>pro potřeby Herního archivu<br><a "
                "href='https://{3}'>{4}</a></p>"
            ).format(__version__, AKRONYM, html.escape(AUTORSTVI), WEB, WEB)
        )
        self.popis_kroku.setText(tr("Krok {0} z {1}").format(i + 1, len(KROKY)))
        self.ukazatel.setValue(i + 1)
        self.zpet.setEnabled(i > 0)
        self.dale.setVisible(i < len(KROKY) - 1)
        self.dale.setText(tr("Pokračovat: {0} →").format(KROKY[i + 1][0].lower()) if i < len(KROKY) - 1 else "")
        pri_vstupu = {1: self._na_kazetu, 2: self._na_platformu, 4: self._na_kontrolu, 5: self._na_ulozeni}.get(i)
        if pri_vstupu:
            pri_vstupu()
        self._obnov_seznam()
        self._aktualizuj_tlacitka()

    def _muze_dal(self) -> bool:
        if self.krok == 0:
            return bool(self.soubory)
        if self.krok == 2:
            return self._analyzovano == self._podpis() and not self._bezi()
        return True

    def _aktualizuj_tlacitka(self):
        self.dale.setEnabled(self._muze_dal())

    def _bezi(self) -> bool:
        return bool(self.okno.ukol and self.okno.ukol.isRunning())

    def obnov(self):
        """Volá okno, když se změnila kazeta (nová, otevřený projekt, výsledek analýzy)."""
        self.karta.nastav(self.okno.kazeta)
        self.obnov_inv()
        if self.krok in (2, 4):
            self.jdi(self.krok)

    # ------------------------------------------------------------ 1 nahrávka
    def _s_nahravka(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._nadpis(tr("Nahrávka kazety"), tr("Vyberte nahrávky stran kazety (WAV nebo FLAC).")))
        vyber = QPushButton(tr("  Vybrat nahrávky…  "))
        vyber.setMinimumHeight(44)
        vyber.clicked.connect(self._vyber_soubory)
        nahrat = QPushButton(tr("  Nahrát z magnetofonu…  "))
        nahrat.setMinimumHeight(44)
        nahrat.clicked.connect(self._nahraj)
        r = QHBoxLayout()
        r.addWidget(vyber)
        r.addWidget(nahrat)
        r.addWidget(QLabel(tr("  …nebo soubory přetáhněte do okna.")))
        r.addStretch(1)
        lay.addLayout(r)
        self.tab_soubory = QTableWidget(0, 4)
        self.tab_soubory.setHorizontalHeaderLabels([tr("Soubor"), tr("Strana"), tr("Délka"), tr("Formát")])
        self.tab_soubory.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tab_soubory.verticalHeader().hide()
        lay.addWidget(self.tab_soubory, 1)
        lay.addWidget(QLabel(f"<b>{tr('Pro jaký počítač je kazeta?')}</b>"))
        popis = QLabel(POPIS)
        popis.setWordWrap(True)
        popis.setStyleSheet("color:#8A93A3")
        lay.addWidget(popis)
        self.vyber_platformy = VyberPlatformy(6, 28)
        self.vyber_platformy.zmeneno.connect(self.okno.nastav_platformu)
        lay.addWidget(self.vyber_platformy)
        f = QHBoxLayout()
        f.addWidget(QLabel(tr("Inventární číslo:")))
        self.inv = QLineEdit()
        self.inv.setPlaceholderText(tr("např. HH08518"))
        self.inv.setMaximumWidth(200)
        self.inv.textEdited.connect(self._zmena_inv)
        f.addWidget(self.inv)
        f.addStretch(1)
        lay.addLayout(f)
        return w

    def _zmena_inv(self, t: str):
        self._nastav_inv(t)

    def _nastav_inv(self, t: str):
        """Inventární číslo z kteréhokoli pole (krok 1, krok 2, krok 6) – do kazety a do všech polí."""
        self.okno.kazeta.inventar.cislo = t.strip()
        self.obnov_inv()
        self.okno._titulek()

    def obnov_inv(self):
        """Pole s inventárním číslem podle kazety (i po změně na pracovním stole) a stav ukládání."""
        cislo = self.okno.kazeta.inventar.cislo
        for pole in (self.inv, self.karta.cislo, self.inv_ulozeni, self.okno.karta.cislo):
            if pole.text().strip() != cislo:
                pole.setText(cislo)
        self._na_ulozeni()

    def _vyber_soubory(self):
        cesty, _ = QFileDialog.getOpenFileNames(self, tr("Nahrávky stran kazety"), self.okno._slozka(),
                                                tr("Nahrávky (*.wav *.flac *.aif *.aiff *.ogg);;Všechny soubory (*)"))
        if cesty:
            self.okno._pamatuj(cesty[0])
            self.pridej_soubory([Path(c) for c in cesty])

    def _nahraj(self):
        from .nahravani import DialogNahravani
        d = DialogNahravani(self.okno.kazeta.inventar.cislo, self.okno._slozka(), self)
        if d.exec() == QDialog.DialogCode.Accepted and d.hotove:
            self.okno._pamatuj(str(d.hotove[0]))
            self.pridej_soubory(d.hotove)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        cesty = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        cesty = [c for c in cesty if c.suffix.lower() in (".wav", ".flac", ".aif", ".aiff", ".ogg")]
        if cesty:
            self.pridej_soubory(cesty)

    def pridej_soubory(self, cesty: list[Path]):
        for c in cesty:
            if c not in self.soubory:
                self.soubory.append(c)
        self.tab_soubory.setRowCount(len(self.soubory))
        pouzite: set[int] = set()
        for r, c in enumerate(self.soubory):
            self.tab_soubory.setItem(r, 0, QTableWidgetItem(c.name))
            sp = QSpinBox()
            sp.setRange(1, 9)
            n = cislo_strany(c, 0) or next(i for i in range(1, 10) if i not in pouzite)
            pouzite.add(n)
            sp.setValue(n)
            sp.valueChanged.connect(self._aktualizuj_tlacitka)
            self.tab_soubory.setCellWidget(r, 1, sp)
            try:
                info = sf.info(str(c))
                self.tab_soubory.setItem(r, 2, QTableWidgetItem(cas_text(info.duration)))
                self.tab_soubory.setItem(
                    r,
                    3,
                    QTableWidgetItem(
                        tr("{0:g} kHz · {1} · {2}").format(
                            info.samplerate / 1000, info.subtype_info, 'stereo' if info.channels == 2 else 'mono'
                        )
                    ),
                )
            except Exception as ex:  # noqa: BLE001
                self.tab_soubory.setItem(r, 3, QTableWidgetItem(tr("nejde přečíst: {0}").format(ex)))
        if not self.inv.text():
            inv = next((inventarni_cislo(c) for c in self.soubory if inventarni_cislo(c)), "")
            self.inv.setText(inv)
            self._zmena_inv(inv)
        self._aktualizuj_tlacitka()

    def _nahravky(self) -> dict[int, Path]:
        out = {}
        for r, c in enumerate(self.soubory):
            out[self.tab_soubory.cellWidget(r, 1).value()] = c
        return out

    def _podpis(self) -> tuple:
        return tuple(sorted((k, str(v)) for k, v in self._nahravky().items())) + (self.okno.kazeta.platforma,)

    # ------------------------------------------------------------ 2 kazeta
    def _s_kazeta(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            self._nadpis(
                tr("Údaje o kazetě"), tr("Pracoviště, inventář a popis kazety – hlavička tabulky Herního archivu.")
            )
        )
        self.karta = KartaKazety()
        self.karta.spravovat_profily.connect(lambda: self.okno.nastaveni_vzhledu("profily"))
        self.karta.cislo.textEdited.connect(self._nastav_inv)
        lay.addWidget(self.karta, 1)
        return w

    def _na_kazetu(self):
        self.karta.nastav(self.okno.kazeta)

    # ------------------------------------------------------------ 3 platforma (spustí analýzu)
    def _s_platforma(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._nadpis(tr("Jaká je to platforma?"),
                                   tr("SAKRA na kazetě našla tyto úseky a odhadla, pro který počítač jsou. "
                                      "Zkontrolujte hlavně úseky s chybou a nerozpoznané.")))
        self.stav_analyzy = QLabel()
        self.prubeh = QProgressBar()
        self.prubeh.setRange(0, 1000)
        lay.addWidget(self.stav_analyzy)
        lay.addWidget(self.prubeh)
        self.karty_platforem = QVBoxLayout()
        obal = QWidget()
        obal.setLayout(self.karty_platforem)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(obal)
        lay.addWidget(sc, 1)
        return w

    def _na_platformu(self):
        if self._analyzovano != self._podpis() and not self._bezi():
            self.prubeh.show()
            self.prubeh.setValue(0)
            self.stav_analyzy.setText(tr("Čtu nahrávky…"))
            self._vycisti(self.karty_platforem)
            podpis = self._podpis()

            def hotovo():
                self._analyzovano = podpis
                self.jdi(2)
            self.okno.analyzuj(self._nahravky(), dale=hotovo,
                               prubeh=lambda x, t: (self.prubeh.setValue(int(x * 1000)), self.stav_analyzy.setText(t)))
            return
        if self._bezi():
            return
        self.prubeh.hide()
        k = self.okno.kazeta
        n = sum(len(s.zaznamy) for s in k.strany)
        self.stav_analyzy.setText(
            tr("Nalezeno: {0}, {1}.").format(
                pocet(n, 'položka', 'položky', 'položek'), pocet(len(k.strany), 'strana', 'strany', 'stran')
            )
            if n
            else tr("Na nahrávce SAKRA nenašla žádná data.")
        )
        self._vycisti(self.karty_platforem)
        for s in k.strany:
            skupiny: dict[str, list[Zaznam]] = {}
            for z in s.zaznamy:
                klic = z.soubor.platforma if z.soubor else ("?" + str(id(z)))
                skupiny.setdefault(klic, []).append(z)
            for klic, zz in skupiny.items():
                self.karty_platforem.addWidget(self._karta_platformy(s.cislo, klic, zz))
        self.karty_platforem.addStretch(1)
        self._aktualizuj_tlacitka()

    def _karta_platformy(self, strana: int, klic: str, zz: list[Zaznam]) -> QWidget:
        od, do = min(z.cas_od or 0 for z in zz), max(z.cas_do or 0 for z in zz)
        pl = podle_id(klic) if not klic.startswith("?") else None
        if pl:
            ok = [z for z in zz if z.stav in ("ok", "opraveno", "neověřeno")]
            spatne = [z for z in zz if z.stav == "chyba"]
            bez_souctu = [z for z in zz if z.stav == "neověřeno"]
            f = _karta_ramecek("chyba" if spatne else "pozor" if bez_souctu else "")
            g = QGridLayout(f)
            g.setContentsMargins(16, 12, 16, 12)
            g.setHorizontalSpacing(14)
            hl = ", ".join(f"„{z.nazev}“" for z in ok[:4]) + ("…" if len(ok) > 4 else "")
            g.addWidget(_znacka(pl.id), 0, 0, 3, 1, Qt.AlignmentFlag.AlignVCenter)
            stitek = (
                (
                    tr(
                        " &nbsp;<span "
                        "style='background:#FDF0CF;color:#8A5A00;border-radius:8px'>&nbsp;zkontrolujte&nbsp;</span>"
                    )
                )
                if spatne or bez_souctu
                else ""
            )
            g.addWidget(
                QLabel(
                    tr(
                        "<span style='font-size:15px'><b>{0}</b></span>{1}<br><span "
                        "style='color:#8A93A3'>Strana {2} · {3} – {4} · {5}</span>"
                    ).format(
                        html.escape(pl.nazev),
                        stitek,
                        strana,
                        cas_text(od),
                        cas_text(do),
                        pocet(len(zz), 'program', 'programy', 'programů'),
                    )
                ),
                0,
                1,
            )
            # pruh: kolik programů se přečetlo bez chyby
            r = QHBoxLayout()
            pruh = QProgressBar()
            pruh.setRange(0, len(zz))
            pruh.setValue(len(ok) - len(bez_souctu))
            pruh.setTextVisible(False)
            pruh.setProperty("bez_textu", True)
            pruh.setMaximumHeight(8)
            barva = "#EF5B5B" if spatne and not ok else "#F2C14E" if spatne or bez_souctu else "#46C27D"
            pruh.setStyleSheet(f"QProgressBar{{background:{vzhled.barvy()['okraj']};border:none;border-radius:4px}}"
                               f"QProgressBar::chunk{{background:{barva};border-radius:4px}}")
            r.addWidget(pruh, 1)
            r.addWidget(QLabel(tr("<b>{0} z {1}</b> v pořádku").format(len(ok), len(zz))))
            g.addLayout(r, 1, 1)
            radek = []
            if ok:
                radek.append(tr("<span style='color:#2EA866'>✓ Potvrzeno: přečteno {0} se správným součtem nebo "
                                "strukturou</span>").format(hl))
            if spatne:
                radek.append(
                    tr("<span style='color:#E04848'>✗ {0} s chybou – podrobnosti v kroku Kontrola</span>").format(
                        len(spatne)
                    )
                )
            lab = QLabel("<br>".join(radek))
            lab.setWordWrap(True)
            g.addWidget(lab, 2, 1)
        else:
            z = zz[0]
            f = _karta_ramecek("chyba" if z.typ != "Audio" else "")
            g = QGridLayout(f)
            g.setContentsMargins(16, 12, 16, 12)
            g.setHorizontalSpacing(14)
            g.addWidget(_znacka(ikony.klic_zaznamu(z)), 0, 0, 2, 1, Qt.AlignmentFlag.AlignVCenter)
            druh = (
                (tr("Žádná data") if z.nazev == "(žádná data)" else tr("Zvukový záznam"))
                if z.typ == "Audio"
                else tr("Nerozpoznáno")
            )
            g.addWidget(
                QLabel(
                    tr(
                        "<span style='font-size:15px'><b>{0}</b></span><br><span "
                        "style='color:#8A93A3'>Strana {1} · {2} – {3} · {4:.0f} s</span>"
                    ).format(druh, strana, cas_text(od), cas_text(do), do - od)
                ),
                0,
                1,
            )
            lab = QLabel(
                tr(
                    "Signál nesedí na žádný známý formát. Vyberte platformu, pokud ji znáte – úsek se uloží "
                    "jako přesný záznam pulzů (CSW), nic se neztratí."
                )
                if z.typ != "Audio"
                else tr("Bez dat (šum, řeč, hudba – návod, znělka). Do balíčku se uloží jen jako výřez WAV.")
            )
            lab.setWordWrap(True)
            g.addWidget(lab, 1, 1)
            cb = QComboBox()
            for hodnota in ["(neznámá)", ZADNA_DATA, *VOLBY_ZVUKU] + RUCNI:     # zobrazí se přeloženě, uloží česky
                cb.addItem(ikony.ikona(hodnota), tr(hodnota), hodnota)
            druh = next((v for d, v in zip(DRUHY_ZVUKU, VOLBY_ZVUKU) if z.nazev == f"({d})"), ZADNA_DATA)
            vybrano = druh if z.typ == "Audio" else z.platforma if z.platforma not in ("", "?") else "(neznámá)"
            cb.setCurrentIndex(max(0, cb.findData(vybrano)))
            cb.setToolTip(tr("Platforma úseku, pokud ji znáte – nebo „žádná data“, když na pásce není program"))
            cb.currentIndexChanged.connect(lambda i, z=z, cb=cb: self._rucni_platforma(z, cb.itemData(i)))
            g.addWidget(cb, 0, 2)
        posl = self._tlacitko_poslechu(strana, od, do)
        g.addWidget(posl, 1, 2, Qt.AlignmentFlag.AlignTop)
        g.setColumnStretch(1, 1)
        return f

    def _rucni_platforma(self, z: Zaznam, t: str):
        bylo = z.typ
        urci_platformu(z, t)
        self.okno.model.obnov()
        self.okno.obnov_oblasti()
        if z.typ != bylo:                              # jiný druh úseku -> karta jinak (po návratu ze signálu)
            QTimer.singleShot(0, lambda: self.jdi(self.krok))

    # ------------------------------------------------------------ 4 programy
    def _s_programy(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(
            self._nadpis(tr("Programy na kazetě"), tr("Doplňte názvy a obsah. Ostatní sloupce vyplnila SAKRA."))
        )
        self.tab_programy = QTableView()
        self.tab_programy.setModel(self.okno.model)
        self.tab_programy.setItemDelegate(VolbyDelegat(self.tab_programy))
        self.tab_programy.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab_programy.verticalHeader().hide()
        ukazat = {"_strana", "_stav", "cas_od", "platforma", "nazev", "obsah", "funkcni_orig", "typ_bloku"}
        for i, (_, pole) in enumerate(SLOUPCE):
            self.tab_programy.setColumnHidden(i, pole not in ukazat)
        self.tab_programy.setColumnWidth([pole for _, pole in SLOUPCE].index("_strana"), 50)
        self.tab_programy.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.tab_programy, 1)
        return w

    # ------------------------------------------------------------ 5 kontrola
    def _s_kontrola(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._nadpis(tr("Kontrola"), tr("Co by měl vidět člověk, než se kazeta uloží do archivu.")))
        self.souhrn = QLabel()
        lay.addWidget(self.souhrn)
        self.problemy = QVBoxLayout()
        obal = QWidget()
        obal.setLayout(self.problemy)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(obal)
        lay.addWidget(sc, 1)
        return w

    def _na_kontrolu(self):
        self._vycisti(self.problemy)
        vse = [(s.cislo, z) for s in self.okno.kazeta.strany for z in s.zaznamy]
        pocty = {}
        for _, z in vse:
            pocty[z.stav] = pocty.get(z.stav, 0) + 1
        self.souhrn.setText("   ".join(f"<span style='color:{STAVY.get(k, (k, 'gray'))[1]}'>"
                                       f"{STAVY.get(k, (k, ''))[0]}: <b>{v}</b></span>" for k, v in pocty.items()))
        sporne = [(c, z) for c, z in vse if z.stav in ("chyba", "opraveno", "neověřeno", "nerozpoznáno")]
        if not sporne:
            self.problemy.addWidget(QLabel(tr("<h3 style='color:#2EA866'>✓ Vše v pořádku – můžete uložit do "
                                              "archivu.</h3>")))
        for c, z in sporne:
            f = _karta_ramecek({"chyba": "chyba", "nerozpoznáno": "chyba"}.get(z.stav, "pozor"))
            g = QGridLayout(f)
            text, barva = STAVY.get(z.stav, (z.stav, "gray"))
            vysvetleni = {
                "chyba": tr("Program se nepodařilo přečíst celý. ")
                + (tr_data(popis_stavu(z.soubor)) if z.soubor else ""),
                "opraveno": tr("Opraveno: ") + (tr_data(popis_stavu(z.soubor)) if z.soubor else ""),
                "neověřeno": tr("Formát nemá kontrolní součet – úplnost ověřena jen délkou a strukturou."),
                "nerozpoznáno": tr("Úsek bez platformy – uloží se jako přesný záznam pulzů (CSW) a výřez WAV."),
            }[z.stav]
            radek = tr("<b style='color:{0}'>{1}</b> &nbsp; <b>{2}</b> <span style='color:gray'>strana {3} "
                       "· {4}–{5}</span>").format(barva, text, html.escape(tr_data(z.nazev)), c, cas_text(z.cas_od),
                                                  cas_text(z.cas_do))
            g.addWidget(QLabel(ikony.html(ikony.klic_zaznamu(z), 18) + " &nbsp;" + radek), 0, 0)
            lab = QLabel(html.escape(vysvetleni))
            lab.setWordWrap(True)
            g.addWidget(lab, 1, 0)
            posl = self._tlacitko_poslechu(c, z.cas_od or 0, z.cas_do or 0)
            otev = QPushButton(tr("Otevřít na pracovním stole"))
            otev.clicked.connect(lambda _=False, z=z: (self.okno.prepni_rezim("stul"), self.okno._vyber_zaznam(z)))
            g.addWidget(posl, 0, 1)
            g.addWidget(otev, 1, 1)
            g.setColumnStretch(0, 1)
            self.problemy.addWidget(f)
        self.problemy.addStretch(1)

    # ------------------------------------------------------------ 6 uložit
    def _s_ulozit(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._nadpis(tr("Uložit do archivu"), tr("Vytvoří archivní balíček kazety.")))
        r = QHBoxLayout()
        r.addWidget(QLabel(tr("Složka archivu:")))
        self.kam = QLineEdit(self.nastaveni.value("archiv", str(Path.home())))
        r.addWidget(self.kam, 1)
        b = QPushButton(tr("Vybrat…"))
        b.clicked.connect(self._vyber_kam)
        r.addWidget(b)
        lay.addLayout(r)
        ri = QHBoxLayout()                      # číslo jde doplnit i tady – bez vracení na předchozí kroky
        ri.addWidget(QLabel(tr("Inventární číslo:")))
        self.inv_ulozeni = QLineEdit()
        self.inv_ulozeni.setPlaceholderText(tr("např. HH08518"))
        self.inv_ulozeni.setMaximumWidth(200)
        self.inv_ulozeni.setToolTip(tr("Inventární číslo pojmenuje balíček i soubory."))
        self.inv_ulozeni.textEdited.connect(self._nastav_inv)
        ri.addWidget(self.inv_ulozeni)
        ri.addStretch(1)
        lay.addLayout(ri)
        self.volba_zdroj = QCheckBox(tr("Přiložit bezztrátovou kopii celé nahrávky (FLAC)"))
        self.volba_zdroj.setChecked(True)
        self.volba_cisty = QCheckBox(tr("WAV programů jako čistý signál (u opravených programů vždy)"))
        self.volba_snimky = QCheckBox(
            tr("Snímky z emulátoru: nahrávací obrazovka a obrazovka po spuštění (ZX Spectrum)")
        )
        self.volba_snimky.setChecked(True)
        self.volba_7z = QCheckBox(tr("Zabalit balíček do jednoho souboru 7z"))
        self.volba_7z.setToolTip(tr("Místo složky vznikne jeden soubor 7z pojmenovaný inventárním číslem, se stejným obsahem."))
        self.volba_7z.setChecked(True)
        lay.addWidget(self.volba_7z)
        lay.addWidget(self.volba_zdroj)
        lay.addWidget(self.volba_cisty)
        lay.addWidget(self.volba_snimky)
        self.ulozit = QPushButton(tr("  Vytvořit archivní balíček  "))
        self.ulozit.setProperty("primarni", True)
        self.ulozit.setMinimumHeight(44)
        self.ulozit.clicked.connect(self._uloz)
        r2 = QHBoxLayout()
        r2.addWidget(self.ulozit)
        r2.addStretch(1)
        lay.addLayout(r2)
        self.vysledek = QLabel()
        self.vysledek.setWordWrap(True)
        lay.addWidget(self.vysledek)
        r3 = QHBoxLayout()
        self.otevrit_slozku = QPushButton(tr("Otevřít složku balíčku"))
        self.otevrit_slozku.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(
            str(self._balicek if self._balicek.is_dir() else self._balicek.parent))))      # u .7z jeho složku
        self.na_stul = QPushButton(tr("Pokračovat na Pracovní stůl"))
        self.na_stul.clicked.connect(lambda: self.okno.prepni_rezim("stul"))
        self.znovu = QPushButton(tr("Další kazeta"))
        self.znovu.clicked.connect(self.dalsi_kazeta)
        for x in (self.otevrit_slozku, self.na_stul, self.znovu):
            x.hide()
            r3.addWidget(x)
        r3.addStretch(1)
        lay.addLayout(r3)
        lay.addStretch(1)
        self._balicek: Path | None = None
        return w

    def _na_ulozeni(self):
        cislo = self.okno.kazeta.inventar.cislo
        if self.inv_ulozeni.text().strip() != cislo:
            self.inv_ulozeni.setText(cislo)
        self.ulozit.setEnabled(bool(cislo))
        if not cislo:
            self.vysledek.setText(tr("<span style='color:#E04848'>Vyplňte inventární číslo – pojmenuje balíček "
                                     "i soubory.</span>"))
            self._varovani = True
        elif getattr(self, "_varovani", False):     # číslo doplněné: varování zmizí (výsledek uložení zůstává)
            self.vysledek.clear()
            self._varovani = False

    def _vyber_kam(self):
        d = QFileDialog.getExistingDirectory(self, tr("Složka archivu"), self.kam.text())
        if d:
            self.kam.setText(d)

    def _uloz(self):
        kam = Path(self.kam.text())
        nastaveni.zapamatuj_slozku("archiv", kam)
        self._varovani = False
        self.vysledek.setText(tr("Ukládám…"))

        def hotovo(d):
            self._balicek = d
            self.vysledek.setText(
                tr("<b style='color:#2EA866'>✓ Balíček je hotový:</b> {0}").format(html.escape(str(d)))
            )
            for x in (self.otevrit_slozku, self.na_stul, self.znovu):
                x.show()
        self.okno.export_balicku(kam, kopirovat_zdroj=self.volba_zdroj.isChecked(),
                                 cisty_wav=self.volba_cisty.isChecked(), dale=hotovo,
                                 snimky=self.volba_snimky.isChecked(), sbalit_7z=self.volba_7z.isChecked())

    def dalsi_kazeta(self):
        self.okno.nova()
        self.soubory = []
        self._analyzovano = None
        self.tab_soubory.setRowCount(0)
        self.inv.clear()
        self.vysledek.clear()
        for x in (self.otevrit_slozku, self.na_stul, self.znovu):
            x.hide()
        self.navstiveno = 0
        self.jdi(0)

    # ------------------------------------------------------------ pomocné
    @staticmethod
    def _nadpis(nadpis: str, text: str) -> QLabel:
        lab = QLabel(
            tr("<h2 style='margin-bottom:2px'>{0}</h2><span style='color:gray'>{1}</span>").format(
                html.escape(nadpis), html.escape(text)
            )
        )
        lab.setWordWrap(True)
        return lab

    @staticmethod
    def _vycisti(lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.hide()               # smaže se až v hlavní smyčce – do té doby by prosvítal
                w.setParent(None)
                w.deleteLater()
