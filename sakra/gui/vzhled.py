"""Vzhled aplikace: barvy (podle systému / světlé / tmavé) a styl (klasický / podle návrhu SAKRA).

Styl „návrh“ přebírá barvy, tvary a písmo z maket v navrh/gui (maketa.css): jantarová hlavní tlačítka,
zaoblené panely, přepínač režimů jako segmenty, nadpisy sekcí šedě; volitelně i vlastní záhlaví okna
se třemi barevnými tečkami.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

JANTAR, JANTAR_2 = "#F2A93B", "#D98B12"

# barvy z maketa.css (.svetle / .tmave) a z maket jednotlivých obrazovek
SVETLE = dict(okno="#F4F5F7", panel="#FFFFFF", panel2="#F7F8FA", levy="#FBFBFC", okraj="#DDE0E5", text="#1F2430",
              slaby="#6B7385", menu="#ECEEF1", titulek="#E4E6EA", lista="#F4F5F7", tlacitko="#FFFFFF",
              tl_okraj="#D0D4DB", vstup="#FFFFFF", vyber="#FFF1DB", vyber_tab="#FDE7C4", segment="#E4E6EA",
              status="#ECEEF1", posuvnik="#C9CED6")
TMAVE = dict(okno="#1B1F27", panel="#1F242D", panel2="#232934", levy="#1A1E25", okraj="#2A303C", text="#DCE1EA",
             slaby="#8C95A6", menu="#171B22", titulek="#12151B", lista="#1D222A", tlacitko="#272D38",
             tl_okraj="#333B48", vstup="#14181E", vyber="#2D3542", vyber_tab="#3A3322", segment="#14181E",
             status="#12151B", posuvnik="#3E4859")


@dataclass
class Nastaveni:
    barvy: str = "system"        # system / svetle / tmave
    styl: str = "navrh"          # navrh / klasicky
    zahlavi: bool = False        # vlastní záhlaví okna (tečky) – jen ve stylu návrhu

    @classmethod
    def nacti(cls) -> "Nastaveni":
        s = QSettings("HerniArchiv", "SAKRA")
        return cls(s.value("vzhled/barvy", "system"), s.value("vzhled/styl", "navrh"),
                   s.value("vzhled/zahlavi", False, bool))

    def uloz(self) -> None:
        s = QSettings("HerniArchiv", "SAKRA")
        s.setValue("vzhled/barvy", self.barvy)
        s.setValue("vzhled/styl", self.styl)
        s.setValue("vzhled/zahlavi", self.zahlavi)


_aktualni = {"tmave": False, "navrh": True}


def je_tmave() -> bool:
    return _aktualni["tmave"]


def je_navrh() -> bool:
    return _aktualni["navrh"]


def barvy() -> dict:
    return TMAVE if je_tmave() else SVETLE


def _system_tmave(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:          # starší Qt
        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def _paleta(b: dict, tmava: bool) -> QPalette:
    p = QPalette()
    R = QPalette.ColorRole
    for role, k in ((R.Window, "okno"), (R.WindowText, "text"), (R.Base, "panel"), (R.AlternateBase, "panel2"),
                    (R.Text, "text"), (R.Button, "tlacitko"), (R.ButtonText, "text"), (R.ToolTipBase, "panel"),
                    (R.ToolTipText, "text"), (R.PlaceholderText, "slaby"), (R.Mid, "okraj"), (R.Dark, "okraj")):
        p.setColor(role, QColor(b[k]))
    p.setColor(R.Light, QColor(b["panel2"]))
    p.setColor(R.Midlight, QColor(b["tl_okraj"]))
    p.setColor(R.Shadow, QColor("#000000"))
    p.setColor(R.BrightText, QColor("#FFFFFF"))
    p.setColor(R.Highlight, QColor("#3E4859" if tmava else "#F6C77D"))
    p.setColor(R.HighlightedText, QColor(b["text"]))
    p.setColor(R.Link, QColor(JANTAR if tmava else JANTAR_2))
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(b["slaby"]))
    return p


def qss(b: dict) -> str:
    """Styl podle návrhu (maketa.css, b_pracovni_stul, a_pruvodce)."""
    return f"""
QMainWindow, QDialog {{ background: {b['okno']}; }}
QWidget {{ color: {b['text']}; }}
QToolTip {{ background: {b['panel']}; color: {b['text']}; border: 1px solid {b['okraj']}; padding: 4px; }}
QWidget#zahlavi {{ background: {b['titulek']}; }}
QLabel#titulek_okna {{ color: {b['slaby']}; }}
QWidget#menu_radek {{ background: {b['menu']}; border-bottom: 1px solid {b['okraj']}; }}
QMenuBar {{ background: transparent; border: none; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {b['vyber']}; }}
QMenu {{ background: {b['panel']}; border: 1px solid {b['okraj']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {b['vyber']}; }}
QMenu::separator {{ height: 1px; background: {b['okraj']}; margin: 4px 8px; }}
QToolBar {{ background: {b['lista']}; border: none; border-bottom: 1px solid {b['okraj']}; spacing: 6px; padding: 5px 8px; }}
QToolBar::separator {{ width: 1px; background: {b['tl_okraj']}; margin: 4px 6px; }}
QToolButton {{ background: {b['tlacitko']}; border: 1px solid {b['tl_okraj']}; border-radius: 6px; padding: 5px 12px; }}
QToolButton:hover {{ border-color: {JANTAR}; }}
QToolButton:checked {{ background: {b['vyber']}; }}
QToolButton[primarni="true"] {{ background: {JANTAR}; color: #1B1F27; border-color: {JANTAR}; font-weight: bold; }}
QPushButton {{ background: {b['tlacitko']}; border: 1px solid {b['tl_okraj']}; border-radius: 8px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {JANTAR}; }}
QPushButton:pressed {{ background: {b['vyber']}; }}
QPushButton:disabled {{ color: {b['slaby']}; border-color: {b['okraj']}; }}
QPushButton[primarni="true"] {{ background: {JANTAR}; color: #1B1F27; border-color: {JANTAR}; font-weight: bold; }}
QPushButton[primarni="true"]:hover {{ background: #F5B755; }}
QPushButton[primarni="true"]:disabled {{ background: {b['okraj']}; color: {b['slaby']}; border-color: {b['okraj']}; }}
QFrame#segmenty {{ background: {b['segment']}; border-radius: 9px; }}
QPushButton#segment {{ background: transparent; border: none; border-radius: 7px; padding: 5px 13px; }}
QPushButton#segment:checked {{ background: {b['panel']}; font-weight: bold; }}
QLineEdit, QComboBox, QSpinBox, QDateEdit {{ background: {b['vstup']}; border: 1px solid {b['tl_okraj']};
    border-radius: 6px; padding: 4px 8px; selection-background-color: {b['vyber_tab']}; selection-color: {b['text']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{ border-color: {JANTAR}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {b['panel']}; border: 1px solid {b['okraj']}; selection-background-color: {b['vyber']}; }}
QTableView, QTreeView, QTreeWidget, QListView, QListWidget, QTextBrowser, QPlainTextEdit {{ background: {b['panel']};
    alternate-background-color: {b['panel2']}; border: 1px solid {b['okraj']}; border-radius: 8px;
    gridline-color: {b['okraj']}; selection-background-color: {b['vyber_tab']}; selection-color: {b['text']}; }}
QTreeView::item:selected, QTreeWidget::item:selected {{ background: {b['vyber']}; }}
QHeaderView::section {{ background: {b['panel2']}; color: {b['slaby']}; border: none;
    border-bottom: 1px solid {b['okraj']}; border-right: 1px solid {b['okraj']}; padding: 5px 8px; font-weight: bold; }}
QTableCornerButton::section {{ background: {b['panel2']}; border: none; }}
QTabWidget::pane {{ border: 1px solid {b['okraj']}; border-radius: 8px; top: -1px; background: {b['panel']}; }}
QTabBar::tab {{ background: transparent; color: {b['slaby']}; padding: 8px 14px; border: none; }}
QTabBar::tab:selected {{ color: {b['text']}; border-bottom: 2px solid {JANTAR}; }}
QTabBar::tab:hover {{ color: {b['text']}; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {b['levy']}; padding: 9px 12px; border-bottom: 1px solid {b['okraj']}; }}
QGroupBox {{ background: {b['panel']}; border: 1px solid {b['okraj']}; border-radius: 10px; margin-top: 22px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 4px;
    color: {b['slaby']}; font-weight: bold; }}
QProgressBar {{ background: {b['okraj']}; border: none; border-radius: 4px; max-height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {JANTAR}; border-radius: 4px; }}
QStatusBar {{ background: {b['status']}; color: {b['slaby']}; border-top: 1px solid {b['okraj']}; }}
QStatusBar QLabel {{ color: {b['slaby']}; }}
QSplitter::handle {{ background: {b['okraj']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {b['posuvnik']}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QListWidget#kroky {{ background: {b['levy']}; border: none; border-right: 1px solid {b['okraj']}; border-radius: 0; padding: 12px 8px; }}
QListWidget#kroky::item {{ padding: 8px 10px; border-radius: 10px; margin: 2px 0; }}
QListWidget#kroky::item:selected {{ background: {b['vyber']}; color: {b['text']}; }}
QTextBrowser#napoveda {{ background: {b['levy']}; border: none; border-left: 1px solid {b['okraj']}; border-radius: 0; padding: 10px; }}
QFrame#karta {{ background: {b['panel']}; border: 1px solid {b['okraj']}; border-radius: 12px; }}
QFrame#karta[stav="pozor"] {{ border: 2px solid #F2C14E; }}
QFrame#karta[stav="chyba"] {{ border: 2px solid #EF5B5B; }}
QFrame#karta QLabel {{ background: transparent; border: none; }}
"""


def pouzij(app: QApplication, n: Nastaveni | None = None, koren=None) -> Nastaveni:
    """Nastaví vzhled aplikace; `koren` = okno, jehož widgety se mají přepočítat při změně za běhu."""
    n = n or Nastaveni.nacti()
    tmave = _system_tmave(app) if n.barvy == "system" else n.barvy == "tmave"
    _aktualni.update(tmave=tmave, navrh=n.styl == "navrh")
    app.setStyle("Fusion")
    b = TMAVE if tmave else SVETLE
    if n.styl == "navrh":
        app.setPalette(_paleta(b, tmave))
        f = QFont()
        f.setFamilies(["DejaVu Sans", "Segoe UI", "Helvetica Neue", "Arial"])
        f.setPointSizeF(9.75)
        app.setFont(f)
        app.setStyleSheet(qss(b))
    else:
        app.setFont(QFont())
        app.setStyleSheet("")
        app.setPalette(_paleta(b, True) if tmave else app.style().standardPalette())
    # při přepnutí za běhu: widgety okna si jinak nechají barvy z předchozího stylu
    if koren is not None:
        from PySide6.QtWidgets import QWidget
        styl = app.style()
        for w in [koren] + koren.findChildren(QWidget):
            styl.unpolish(w)
            styl.polish(w)
            w.setPalette(app.palette())
            w.update()
    return n
