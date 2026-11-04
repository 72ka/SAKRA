"""Jazyk uživatelského rozhraní: čeština (zdrojové texty) a angličtina (sakra/preklady/en.py).

Texty v kódu jsou česky a obalují se `tr()`; texty se složenými hodnotami jako šablona
`tr("Strana {0}").format(n)`.
Jazyk se nastaví při startu před načtením oken (texty na úrovni modulů se vyhodnotí při importu),
změna se proto projeví po restartu aplikace. Výstupy pro archiv (Excel podle vzoru, protokol, názvy souborů)
zůstávají česky – odpovídají vzoru Herního archivu.
"""
from __future__ import annotations

import locale
import os
import re

JAZYKY = {"cs": "Čeština", "en": "English"}
_jazyk = "cs"
_slovnik: dict[str, str] = {}
_vzory: list[tuple[re.Pattern, str]] = []


def vychozi() -> str:
    """Podle jazyka systému: čeština a slovenština -> čeština, jinak angličtina."""
    for promenna in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(promenna, "")
        if v and v not in ("C", "POSIX", "C.UTF-8"):
            return "cs" if v[:2].lower() in ("cs", "sk") else "en"
    try:
        kod = locale.getlocale()[0] or ""
    except ValueError:
        kod = ""
    return "cs" if kod[:2].lower() in ("cs", "sk") or kod.startswith(("Czech", "Slovak")) else "en"


def nastav(jazyk: str) -> None:
    global _jazyk, _slovnik, _vzory
    _jazyk = jazyk if jazyk in JAZYKY else "cs"
    if _jazyk == "en":
        from .preklady import en
        _slovnik = en.TEXTY
        _vzory = [(re.compile(v), n) for v, n in en.VZORY]
    else:
        _slovnik, _vzory = {}, []


def jazyk() -> str:
    return _jazyk


def nacti() -> str:
    """Jazyk z nastavení aplikace (nebo proměnné SAKRA_JAZYK), jinak podle systému; rovnou ho nastaví."""
    j = os.environ.get("SAKRA_JAZYK", "")
    if j not in JAZYKY:
        try:
            from PySide6.QtCore import QSettings
            j = QSettings("HerniArchiv", "SAKRA").value("jazyk", "") or ""
        except ImportError:
            j = ""
    nastav(j if j in JAZYKY else vychozi())
    return _jazyk


def uloz(jazyk: str) -> None:
    from PySide6.QtCore import QSettings
    QSettings("HerniArchiv", "SAKRA").setValue("jazyk", jazyk)


def tr(text: str) -> str:
    """Překlad textu rozhraní; neznámý text se vrátí beze změny (česky)."""
    if _jazyk == "cs" or not text:
        return text
    t = _slovnik.get(text)
    if t is not None:
        return t
    for vzor, nahrada in _vzory:
        m = vzor.fullmatch(text)
        if m:
            return nahrada(m) if callable(nahrada) else m.expand(nahrada)
    return text


def tr_data(text) -> str:
    """Překlad hodnoty z dat (stav, typ, poznámka dekodéru) pro zobrazení; data sama zůstávají česky.
    Složený popis („…; …“) se překládá po částech."""
    if not isinstance(text, str) or _jazyk == "cs":
        return text
    if "; " in text and text not in _slovnik:
        return "; ".join(tr(c) for c in text.split("; "))
    return tr(text)
