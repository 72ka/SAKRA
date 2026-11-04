"""Spuštění: `python -m sakra` otevře aplikaci, `python -m sakra analyzuj …` zpracuje nahrávky bez GUI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _analyzuj(arg) -> int:
    from .balicek import exportuj
    from .jadro.analyza import popis_stavu
    from .jadro.model import Kazeta, cas_text
    from .metadata import excel
    from .projekt import cislo_strany, uloz, zpracuj

    kazeta = excel.importuj(Path(arg.excel)) if arg.excel else Kazeta()
    if arg.inv:
        kazeta.inventar.cislo = arg.inv
    if arg.platforma:
        kazeta.platforma = arg.platforma
    nahravky: dict[int, Path] = {}
    for i, c in enumerate(arg.nahravky, 1):
        n = cislo_strany(c, i)
        while n in nahravky:
            n += 1
        nahravky[n] = Path(c)

    def prubeh(x, t=""):
        print(f"\r{x * 100:5.1f} %  {t[:60]:<60}", end="", file=sys.stderr, flush=True)

    vysledky = zpracuj(kazeta, nahravky, prubeh)
    print(file=sys.stderr)
    for s in kazeta.strany:
        print(f"\nObsah ({s.cislo})  {Path(s.nahravka).name}  {s.vzorkovani}, {s.format}, {cas_text(s.delka)}")
        for z in s.zaznamy:
            stav = z.stav
            tech = popis_stavu(z.soubor) if z.soubor else ""
            print(f"  {cas_text(z.cas_od)}–{cas_text(z.cas_do)}  {z.platforma or '?':28.28} {z.nazev:24.24} "
                  f"{z.typ_bloku:8.8} {stav:12} {tech}")
    if arg.vystup:
        d = exportuj(kazeta, Path(arg.vystup), vysledky, prubeh=prubeh, kopirovat_zdroj=not arg.bez_zdroje)
        print(file=sys.stderr)
        print(f"\nBalíček: {d}")
    if arg.projekt:
        uloz(kazeta, Path(arg.projekt))
        print(f"Projekt: {arg.projekt}")
    return 0


def main(argv=None) -> int:
    from . import AKRONYM, AUTORSTVI, KONTAKT, LICENCE, URCENI, __version__
    ap = argparse.ArgumentParser(prog="sakra", description=f"SAKRA – {AKRONYM}. Digitalizace a archivace audiokazet.",
                                 epilog=f"{AUTORSTVI}. {URCENI}.")
    verze = (f"SAKRA {__version__} – {AKRONYM}. {AUTORSTVI}. {URCENI}. "
             f"Licence: {LICENCE} (komerčně jen se souhlasem autora, {KONTAKT}).")
    ap.add_argument("--version", action="version", version=verze)
    sub = ap.add_subparsers(dest="prikaz")
    a = sub.add_parser("analyzuj", help="zpracovat nahrávky bez grafického rozhraní")
    a.add_argument("nahravky", nargs="+", help="WAV/FLAC jednotlivých stran (strana se pozná z názvu, např. „(2)“)")
    a.add_argument("--inv", help="inventární číslo (jinak z názvu souboru)")
    from .platformy import POCITACE
    a.add_argument("--platforma", choices=POCITACE, metavar="POČÍTAČ",
                   help="pro jaký počítač kazeta je – zkusí se jen jeho dekodéry (rychlejší); "
                        "jinak automaticky. "
                        "Možnosti: " + ", ".join(POCITACE))
    a.add_argument("--excel", help="načíst metadata z tabulky podle vzoru")
    a.add_argument("--vystup", help="složka, kam vytvořit archivní balíček")
    a.add_argument("--bez-zdroje", action="store_true", help="do balíčku nekopírovat celou nahrávku")
    a.add_argument("--projekt", help="uložit projekt .sakra")
    g = sub.add_parser("gui", help="otevřít aplikaci (výchozí)")
    g.add_argument("soubor", nargs="?", help="projekt .sakra nebo nahrávka")
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] not in ("analyzuj", "gui") and not argv[0].startswith("-"):
        argv = ["gui"] + argv          # otevření souboru dvojklikem (asociace .sakra) nebo přetažením na ikonu
    arg = ap.parse_args(argv)
    if arg.prikaz == "analyzuj":
        return _analyzuj(arg)
    from . import i18n
    i18n.nacti()                       # před načtením oken – texty modulů se vyhodnotí při importu
    from .gui.aplikace import spust
    return spust(getattr(arg, "soubor", None))


if __name__ == "__main__":
    sys.exit(main())
