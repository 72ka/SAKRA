"""Detail vybraného programu: údaje z hlavičky, bloky, opravy, texty v datech."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ..jadro.analyza import popis_stavu
from ..jadro.model import Nosna, Zaznam, cas_text
from ..platformy import podle_id
from ..i18n import tr, tr_data
from . import ikony
from ..jadro.soucty import soucty_bloku
from .stul_panely import MrizkaBloku, nadpis_sekce


POPISY = {  # klíč v Soubor.info -> (popisek, převod hodnoty)
    "delka_dat": (tr("Délka dat"), lambda v: f"{v} B"),
    "bloku": (tr("Bloků"), str),
    "zaznamu": (tr("Záznamů"), str),
    "posledni_zaznam": (tr("Poslední záznam"), lambda v: "ano" if v else tr("chybí")),
    "cislo_souboru": (tr("Číslo souboru"), str),
    "rychlost": (tr("Rychlost pásky"), lambda v: tr("{0:.0f} % jmenovité").format(v * 100)),
    "typ": (tr("Typ (hlavička)"), str),
    "delka": (tr("Délka (hlavička)"), lambda v: f"{v} B"),
    "autostart": (tr("Autostart řádek"), str),
    "delka_programu": (tr("Délka programu"), lambda v: f"{v} B"),
    "adresa": (tr("Adresa"), lambda v: f"{v} ({v:04X}h)"),
    "poznamka": (tr("Poznámka"), str),
    "kopie": (tr("Kopie na pásce"), str),
    "rychlost_bd": (tr("Rychlost"), lambda v: f"{v} Bd"),
}
SKRYT = {"texty", "basic", "casti", "casovani", "turbo"}




def _soucty_html(platforma: str, blok) -> str:
    """Součty bloku: na pásce / spočteno (zeleně shoda, červeně rozdíl)."""
    if isinstance(blok, Nosna):
        return "—"
    soucty = soucty_bloku(platforma, blok)
    if soucty is None:
        return f"<span style='color:#8A93A3'>{html.escape(tr('bez součtu'))}</span>"
    radky = []
    for popis, pasek, spocteno, cislic in soucty:
        barva = "#2EA866" if pasek == spocteno else "#E04848"
        na_pasce = "?" if pasek is None else f"{pasek:0{cislic}X}"
        radky.append(f"{html.escape(tr_data(popis))}: {na_pasce} / "
                     f"<span style='color:{barva}'>{spocteno:0{cislic}X}</span>")
    return "<br>".join(radky)

class Prohlizec(QTextBrowser):
    """Text detailu; obrázky náhledu (src="nahled:N") bere z paměti."""

    def __init__(self):
        super().__init__()
        self.obrazky: dict[str, QImage] = {}

    def loadResource(self, typ, url):
        if typ == QTextDocument.ResourceType.ImageResource and url.scheme() == "nahled":
            return self.obrazky.get(url.toString())
        return super().loadResource(typ, url)


def _qimage(rgb, zvetseni: int = 1) -> QImage:
    v, s = rgb.shape[:2]
    img = QImage(rgb.tobytes(), s, v, 3 * s, QImage.Format.Format_RGB888).copy()
    return img.scaled(s * zvetseni, v * zvetseni, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.FastTransformation)


class Detail(QWidget):
    ulozit = Signal(object)     # Zaznam – uložit jen tento program
    emulovat = Signal(object)   # Zaznam – spustit program v emulátoru (snímek po spuštění)
    blok = Signal(object, object)   # Zaznam, Blok – klik na blok v mřížce

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = Prohlizec()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(lambda url: url.toString() == "sakra:emulovat" and self.z is not None
                                        and self.emulovat.emit(self.z))
        self.tlacitko = QPushButton(tr("Uložit tento program…"))
        self.tlacitko.setEnabled(False)
        self.tlacitko.clicked.connect(lambda: self.z is not None and self.ulozit.emit(self.z))
        lista = QHBoxLayout()
        lista.addStretch(1)
        lista.addWidget(self.tlacitko)
        # bloky dat graficky (zelená = bez chyby)
        self.nadpis_bloku = nadpis_sekce()
        self.mrizka = MrizkaBloku()
        self.mrizka.vybran.connect(lambda b: self.z is not None and self.blok.emit(self.z, b))
        self.nadpis_bloku.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.addWidget(nadpis_sekce(tr("VYBRANÝ SOUBOR")))
        lay.addWidget(self.text, 1)
        lay.addWidget(self.nadpis_bloku)
        lay.addWidget(self.mrizka)
        lay.addLayout(lista)
        self.z: Zaznam | None = None
        self.nastav(None)

    def nastav(self, z: Zaznam | None, blok=None) -> None:
        self.z = z
        self.tlacitko.setEnabled(bool(z and z.soubor))
        bloky = z.soubor.bloky if z is not None and z.soubor else []
        self.mrizka.nastav(bloky)
        self.nadpis_bloku.setVisible(bool(bloky))
        self.mrizka.setVisible(bool(bloky))
        if bloky:
            vadne = sum(not b.ok for b in bloky)
            oprav = sum(bool(b.ok and b.oprava) for b in bloky)
            self.nadpis_bloku.setText(
                tr(
                    "BLOKY DAT · {0}<br><span style='font-weight:normal'><span style='color:#2EA866'>■</span> bez chyby "
                    " <span style='color:#E3A72F'>■</span> opraveno{1}  <span style='color:#E04848'>■</span> "
                    "chyba{2}</span>"
                ).format(len(z.soubor.bloky), f' ({oprav})' if oprav else '', f' ({vadne})' if vadne else '')
            )
        if z is None:
            self.text.setHtml(
                tr("<p style='color:#8A93A3'>Vyberte program v tabulce, ve stromu nebo na časové ose.</p>")
            )
            return
        e = html.escape
        s = z.soubor
        hlavicka = tr("<h3 style='margin:0'>{0}</h3><p style='color:#8A93A3;margin:2px 0 8px'>{1} · {2}–{3}</p>")
        hlavicka = hlavicka.format(
            e(tr_data(z.nazev)),
            e(z.platforma or tr('žádná data' if z.typ == 'Audio' else 'nerozpoznáno')),
            cas_text(z.cas_od),
            cas_text(z.cas_do),
        )
        casti = ["<table cellspacing=0 cellpadding=0><tr><td valign=top style='padding-right:8px'>"
                 + ikony.html(ikony.klic_zaznamu(z), 36) + "</td><td>" + hlavicka + "</td></tr></table>"]
        if s is None:
            if z.typ == "Audio":
                casti.append(
                    tr(
                        "<p><b style='color:#8A93A3'>♪ žádná data</b> – šum, řeč nebo hudba. Do balíčku se "
                        "uloží jen jako výřez WAV.</p>"
                    )
                )
            else:
                casti.append(
                    tr(
                        "<p>Úsek se nepodařilo přiřadit žádné platformě. Do balíčku se uloží jako přesný "
                        "záznam pulzů (CSW) a výřez WAV. Platformu, nebo „žádná data“, jde určit ve sloupci "
                        "Platforma.</p>"
                    )
                )
            self.text.setHtml("".join(casti))
            return
        pl = podle_id(s.platforma)
        stav = popis_stavu(s)
        barva = {"ok": "#2EA866", "opraveno": "#D08A10", "neověřeno": "#4A86C8", "chyba": "#E04848"}[s.stav]
        casti.append(
            tr("<p><b style='color:{0}'>{1}</b>{2}</p>").format(
                barva, e(tr_data(s.stav)), ' – ' + e(tr_data(stav)) if stav else ''
            )
        )
        radky = [(tr("Název v bloku"), s.nazev_bloku), (tr("Typ bloku"), tr_data(s.typ_bloku)),
                 (tr("Výstupní formát"), pl.pripona.upper() if pl else "")]
        for k, v in s.info.items():
            if k in SKRYT or v in (None, ""):
                continue
            popisek, prevod = POPISY.get(k, (k.replace("_", " "), str))
            try:
                radky.append((popisek, tr_data(prevod(v))))
            except (TypeError, ValueError):
                radky.append((popisek, tr_data(str(v))))
        casti.append(tr("<table cellspacing=0 cellpadding=2>") + "".join(
            f"<tr><td style='color:#8A93A3;padding-right:12px'>{e(str(k))}</td><td>{e(str(v))}</td></tr>"
            for k, v in radky if v not in (None, "")) + "</table>")
        if s.info.get("casti"):
            casti.append(tr("<h4 style='margin:10px 0 4px'>Části programu</h4><ol style='margin-top:0'>")
                         + "".join(f"<li>{e(tr_data(c))}</li>" for c in s.info["casti"]) + "</ol>")
        if isinstance(blok, Nosna):
            self.text.obrazky.clear()
            casti.append(f"<h4>IBG · {cas_text(blok.zacatek)}–{cas_text(blok.konec)}</h4><p>"
                         + e(tr("Nosná log. 1 – bez datových bajtů a kontrolního součtu.")) + "</p>")
        else:
            casti.append(self._nahled(pl, s))
        casti.append(
            tr(
                "<h4 style='margin:10px 0 4px'>Bloky</h4><table cellspacing=0 cellpadding=2 "
                "style='border-collapse:collapse'><tr "
                "style='background:#F6B26B;color:#1B1F27'><th>Č.</th><th>Typ</th><th>Od</th><th>Do</th><th>B</th><th></th><th>Součet (pásek / spočteno)</th><th "
                "align=left>Oprava / chyba</th></tr>"
            )
        )
        for b in bloky:
            st = "—" if isinstance(b, Nosna) else "✓" if b.ok else "✗"
            bar = "#8A93A3" if isinstance(b, Nosna) else "#2EA866" if b.ok else "#E04848"
            pozn = tr_data(b.oprava) or (tr("neznámé bajty {0}").format(len(b.chybne_bajty)) if b.chybne_bajty else "")
            casti.append(
                tr(
                    "<tr><td align=right nowrap>{0}</td><td nowrap>{1}</td><td nowrap>{2}</td><td "
                    "nowrap>{3}</td><td align=right>{4}</td><td style='color:{5}' "
                    "align=center>{6}</td><td nowrap style='font-family:monospace'>{8}</td><td>{7}</td></tr>"
                ).format(
                    '' if b.cislo is None else b.cislo,
                    e(tr_data(b.typ)),
                    cas_text(b.zacatek),
                    cas_text(b.konec),
                    len(b.data),
                    bar,
                    st,
                    e(pozn),
                    _soucty_html(s.platforma, b),
                )
            )
        casti.append("</table>")
        if s.info.get("texty"):
            casti.append(tr("<h4 style='margin:10px 0 4px'>Texty v datech</h4><p style='font-family:monospace'>")
                         + "<br>".join(e(t) for t in s.info["texty"][:20]) + "</p>")
        if s.vystup:
            casti.append(tr("<h4 style='margin:10px 0 4px'>Exportované soubory</h4><p style='font-family:monospace'>")
                         + "<br>".join(f"{e(k)}  {v}" for k, v in s.vystup.items()) + "</p>")
        self.text.setHtml("".join(casti))

    def _nahled(self, pl, s) -> str:
        """Náhled programu: obrazovky jako obrázky, výpis BASICu nebo začátek dat."""
        self.text.obrazky.clear()
        try:
            n = pl.nahled(s) if pl else {"obrazky": [], "texty": []}
        except Exception as ex:  # noqa: BLE001 – náhled je jen pomůcka
            return tr("<p style='color:#E04848'>Náhled nejde vytvořit: {0}</p>").format(html.escape(str(ex)))
        emulace = n.get("emulace")
        if not n["obrazky"] and not n["texty"] and emulace in (None, "hotovo"):
            return ""
        e = html.escape
        out = [tr("<h4 style='margin:10px 0 4px'>Náhled</h4>")]
        for i, (popis, rgb) in enumerate(n["obrazky"]):
            klic = f"nahled:{i}"
            self.text.obrazky[klic] = _qimage(rgb)
            out.append(tr("<p style='margin:2px 0'>{0}<br><img src='{1}'></p>").format(e(tr_data(popis)), klic))
        if emulace == "lze":
            out.append(tr("<p style='margin:6px 0'><a href='sakra:emulovat'>▶ Spustit v emulátoru – nahrávací "
                          "obrazovka a obrazovka po spuštění</a></p>"))
        elif emulace not in (None, "hotovo"):
            out.append(
                tr("<p style='margin:6px 0;color:#8A93A3'>Emulátor není k dispozici: {0}</p>").format(
                    e(tr_data(emulace))
                )
            )
        for popis, text in n["texty"]:
            out.append(tr("<p style='margin:6px 0 2px;color:#8A93A3'>{0}</p><pre "
                          "style='margin:0;font-size:9pt'>{1}</pre>").format(e(tr_data(popis)), e(text)))
        return "".join(out)
