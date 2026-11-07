"""Rozhraní zásuvného modulu platformy: detekce, dekódování, zápis výstupních formátů."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..jadro.audio import Nahravka
from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import HIST_KROK_US, Pulzy, Usek, najdi_pulzy, odecti_stred
from ..jadro.texty import hex_vypis


@dataclass
class Kontext:
    """Co dostane dekodér: nahrávka jedné strany, její pulzy a úseky."""
    nahravka: Nahravka
    pulzy: Pulzy
    strana: int = 1

    def precti_znovu(self, zacatek: float, konec: float, rel: float, stred_us: float | None = None) -> Pulzy:
        """Opakované čtení části nahrávky s jiným prahem hystereze (`stred_us` = odečíst plovoucí střed)."""
        a = max(0, int(zacatek * self.nahravka.rate))
        b = min(len(self.nahravka.vzorky), int(konec * self.nahravka.rate))
        x = self.nahravka.vzorky[a:b]
        if stred_us:
            # úsek je celý signál (bez ticha) – spodní mez prahu se z něj odhadnout nedá
            return najdi_pulzy(odecti_stred(x, self.nahravka.rate, stred_us), self.nahravka.rate, rel=rel,
                               posun=a, podlaha_rel=0.02)
        return najdi_pulzy(x, self.nahravka.rate, rel=rel, posun=a)


class Platforma:
    id = ""
    pocitac = ""          # hodnota sloupce „Platforma“ (bez varianty)
    varianta = ""         # např. „Tesla ROM“
    barva = "#8A93A3"     # barva na časové ose
    pripona = ""          # hlavní archivní formát
    poradi = 50           # pořadí zkoušení (menší dřív)

    @property
    def nazev(self) -> str:
        return f"{self.pocitac} – {self.varianta}" if self.varianta else self.pocitac

    def skore(self, usek: Usek, rate: int) -> float:
        """Rychlý odhad 0..1 podle histogramu délek pulzů (potvrdí se dekódováním)."""
        return 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        raise NotImplementedError

    def sluc_kopie(self, soubory: list[tuple[int, Soubor]]) -> None:
        """Oprava poškozených bloků z jiných kopií téhož programu (i z druhé strany)."""

    def zapis(self, soubor: Soubor, cil: Path) -> list[Path]:
        """Zapíše výstupní soubory; `cil` je cesta bez přípony. Vrací vytvořené soubory."""
        return []

    def turbo(self, soubor: Soubor) -> str:
        return "Není v Turbo"

    def bloky_pro_zobrazeni(self, s: Soubor) -> list[Blok]:
        """Datové bloky a případné pomocné úseky signálu pouze pro GUI."""
        return s.bloky

    def nahled(self, s: Soubor) -> dict:
        """Náhled programu: {"obrazky": [(popis, RGB pole)], "texty": [(popis, text)]}.
        Výchozí: začátek dat hexadecimálně (moduly mohou ukázat výpis BASICu, obrazovku…)."""
        if not hasattr(s, "_data"):
            self.dokonci(s)
        data = getattr(s, "_data", b"") or b"".join(b.data for b in s.bloky if b.ok)
        adr = s.info.get("adresa", 0) if isinstance(s.info.get("adresa", 0), int) else 0
        return {"obrazky": [], "texty": [("Začátek dat", hex_vypis(data, adr))] if data else []}


def pripona(cil: Path, pripona_: str) -> Path:
    """Přidá příponu (jméno programu může obsahovat tečku, např. „BASIC V5.0“)."""
    return cil.parent / (cil.name + pripona_)


def podil_v_pasmu(h: np.ndarray, od_us: float, do_us: float) -> float:
    """Kolik běhů (podíl) leží v pásmu od..do µs."""
    celkem = h.sum()
    if not celkem:
        return 0.0
    return float(h[int(od_us / HIST_KROK_US):int(do_us / HIST_KROK_US) + 1].sum() / celkem)


def manchester_skore(h: np.ndarray, t_us: float) -> float:
    """Manchester: skoro všechny běhy jsou T nebo 2T (pro T v okolí t_us ±25 %)."""
    nejlepsi = 0.0
    for f in np.arange(0.8, 1.21, 0.04):
        t = t_us * f
        s = podil_v_pasmu(h, 0.7 * t, 1.3 * t) + podil_v_pasmu(h, 1.7 * t, 2.35 * t)
        kr = podil_v_pasmu(h, 0.7 * t, 1.3 * t)
        if kr > 0.3:
            nejlepsi = max(nejlepsi, s)
    return nejlepsi
