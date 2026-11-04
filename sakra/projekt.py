"""Projekt kazety (.sakra = JSON) a zpracování více stran najednou."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .jadro.analyza import VysledekStrany, analyzuj_stranu, doplnit_kazetu, oprav_kopiemi
from .jadro.model import Kazeta, kazeta_do_json, kazeta_z_json

PRIPONA = ".sakra"


def cislo_strany(cesta: str | Path, vychozi: int = 1) -> int:
    """Strana z názvu souboru: „… (2)…“, „strana B“, „side 2“, „-B.wav“…"""
    n = Path(cesta).stem
    for vzor in (r"\((\d)\)", r"(?:strana|side|str)[ _-]*([12ABab])\b", r"[ _-]([ABab])$"):
        m = re.search(vzor, n, re.IGNORECASE)
        if m:
            v = m.group(1).upper()
            return {"A": 1, "B": 2}.get(v, int(v) if v.isdigit() else vychozi)
    return vychozi


def inventarni_cislo(cesta: str | Path) -> str:
    m = re.search(r"\b([A-Z]{1,3}\d{4,6})\b", Path(cesta).stem)
    return m.group(1) if m else ""


def analyzuj_strany(nahravky: dict[int, Path], prubeh=None,
                    volby: dict[int, tuple[str, str]] | None = None, platforma: str = "") -> dict[int, VysledekStrany]:
    """Jen analýza (nesahá na kazetu – jde pustit ve vlákně). `volby`: strana -> (kanál, polarita);
    `platforma`: počítač kazety (jen jeho dekodéry), prázdná = automaticky."""
    pr = prubeh or (lambda x, t="": None)
    vysledky: dict[int, VysledekStrany] = {}
    pocet = max(1, len(nahravky))
    for i, (cislo, cesta) in enumerate(sorted(nahravky.items())):
        kanal, polarita = (volby or {}).get(cislo, ("auto", "auto"))
        vysledky[cislo] = analyzuj_stranu(
            cesta, cislo, prubeh=lambda x, t="", i=i, c=cislo: pr((i + x) / pocet, f"Strana {c}: {t}"),
            volba_kanalu=kanal, polarita=polarita, platforma=platforma)
    return vysledky


def vloz_vysledky(kazeta: Kazeta, nove: dict[int, VysledekStrany],
                  ostatni: dict[int, VysledekStrany] | None = None) -> None:
    """Opraví soubory z kopií (i mezi stranami) a vloží nové výsledky do kazety."""
    vse = {**(ostatni or {}), **nove}
    oprav_kopiemi(list(vse.values()))
    doplnit_kazetu(kazeta, list(nove.values()))
    if not kazeta.inventar.cislo:
        kazeta.inventar.cislo = next((inventarni_cislo(v.strana.nahravka) for v in nove.values()
                                      if inventarni_cislo(v.strana.nahravka)), "")


def zpracuj(kazeta: Kazeta, nahravky: dict[int, Path], prubeh=None) -> dict[int, VysledekStrany]:
    """Analyzuje strany, opraví soubory z kopií a vloží výsledky do kazety."""
    vysledky = analyzuj_strany(nahravky, prubeh, platforma=kazeta.platforma)
    vloz_vysledky(kazeta, vysledky)
    return vysledky


def uloz(kazeta: Kazeta, cesta: Path) -> None:
    Path(cesta).write_text(json.dumps(kazeta_do_json(kazeta), ensure_ascii=False, indent=1), encoding="utf-8")


def otevri(cesta: Path) -> Kazeta:
    return kazeta_z_json(json.loads(Path(cesta).read_text(encoding="utf-8")))
