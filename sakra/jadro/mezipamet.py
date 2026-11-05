"""Mezipaměť hotové analýzy strany: návrat ke kazetě (z dávky, otevření projektu) nemusí znovu číst a dekódovat.

Ukládá se celý VysledekStrany (načtený signál, pulzy, programy, bloky) hned po analýze, dřív než ho
upraví opravy z kopií nebo ruční zásahy. Klíč: cesta, velikost a čas změny souboru, číslo strany,
volby analýzy (kanál, polarita, platforma, ručně označené úseky) a otisk zdrojů dekodérů – po změně
programu se starý výsledek nepoužije. Složka: SAKRA_CACHE (cesta; "0" = vypnuto), jinak mezipaměť
systému (~/.cache/sakra, %LOCALAPPDATA%\\SAKRA\\cache). Velikost se drží pod LIMIT_B (maže nejstarší).
"""
from __future__ import annotations

import hashlib
import os
import pickle
import sys
from functools import lru_cache
from pathlib import Path

LIMIT_B = 4 * 1024 ** 3          # 4 GB
PRIPONA = ".analyza"
VERZE = 1


def slozka() -> Path | None:
    nast = os.environ.get("SAKRA_CACHE", "")
    if nast == "0":
        return None
    if nast:
        return Path(nast)
    try:                                        # složka zvolená v Nastavení
        from ..nastaveni import nastaveni
        vlastni = nastaveni().value("mezipamet/slozka", "") or ""
    except ImportError:
        vlastni = ""
    if vlastni:
        return Path(vlastni)
    return vychozi_slozka()


def vychozi_slozka() -> Path:
    if sys.platform.startswith("win"):
        zaklad = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SAKRA" / "cache"
    elif sys.platform == "darwin":
        zaklad = Path.home() / "Library" / "Caches" / "SAKRA"
    else:
        zaklad = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "sakra"
    return zaklad / "analyzy"


@lru_cache(maxsize=1)
def otisk_zdroju() -> str:
    """Otisk zdrojů, na kterých výsledek analýzy závisí (jádro a dekodéry)."""
    from .. import __version__
    koren = Path(__file__).resolve().parents[1]
    h = hashlib.sha1(f"{VERZE} {__version__}".encode())     # sestavená aplikace .py nemá: aspoň verze
    for f in sorted([*koren.glob("jadro/*.py"), *koren.glob("platformy/*.py")]):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def klic(cesta, cislo: int, **volby) -> str | None:
    """Klíč výsledku, None když soubor nejde přečíst."""
    try:
        p = Path(cesta).resolve()
        st = p.stat()
    except OSError:
        return None
    rucni = tuple((round(r.zacatek, 4), round(r.konec, 4), r.druh) for r in (volby.pop("rucni_useky", None) or []))
    popis = repr((str(p), st.st_size, st.st_mtime_ns, cislo, sorted(volby.items()), rucni, otisk_zdroju()))
    return hashlib.sha1(popis.encode("utf-8")).hexdigest()


def nacti(k: str | None):
    """Uložený výsledek, nebo None (chybí, poškozený, vypnuto)."""
    d = slozka()
    if k is None or d is None:
        return None
    f = d / (k + PRIPONA)
    try:
        with open(f, "rb") as fh:
            v = pickle.load(fh)
        os.utime(f)                      # naposledy použito (úklid maže nejstarší)
        return v
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 – poškozený nebo nečitelný soubor: analyzovat znovu
        try:
            f.unlink()
        except OSError:
            pass
        return None


def uloz(k: str | None, v) -> None:
    d = slozka()
    if k is None or d is None:
        return
    try:
        d.mkdir(parents=True, exist_ok=True)
        docasny = d / (k + ".tmp")
        with open(docasny, "wb") as fh:
            pickle.dump(v, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(docasny, d / (k + PRIPONA))
        uklid(d)
    except Exception:  # noqa: BLE001 – mezipaměť je jen zrychlení, analýza nesmí kvůli ní selhat
        pass


def uklid(d: Path, limit: int = LIMIT_B) -> None:
    soubory = sorted(d.glob("*" + PRIPONA), key=lambda f: f.stat().st_mtime)
    celkem = sum(f.stat().st_size for f in soubory)
    for f in soubory:
        if celkem <= limit:
            break
        celkem -= f.stat().st_size
        try:
            f.unlink()
        except OSError:
            pass


def vymaz() -> int:
    """Smaže celou mezipaměť, vrátí počet smazaných výsledků."""
    d = slozka()
    if d is None or not d.exists():
        return 0
    n = 0
    for f in d.glob("*" + PRIPONA):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n
