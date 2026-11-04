"""Snímky obrazovky ZX Spectra z emulátoru: nahrávací obrazovka a obrazovka po spuštění programu.

Používá emulátor Spectra 48K z balíčku `zx` (I. Kosarev, MIT; ROM © Amstrad, šíření pro emulátory povoleno),
bez okna. Dva režimy:
* rychlý – všechny bloky jsou standardní: zachytí se rutina ROM LD-BYTES (0556h) a blok se rovnou zapíše
  do paměti (jako „rychlé nahrávání“ v emulátorech), trvá jednotky sekund;
* emulace pásky – program obsahuje turbo bloky: páska (TZX s naměřeným časováním) se přehrává do emulátoru,
  vlastní zavaděč ji čte jako na skutečném počítači (asi 4× rychleji než v reálném čase).
Nahrávací obrazovka = nejvíc „obrázkový“ snímek během nahrávání (u turba bývá v jiném formátu než SCREEN$).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np

from ..formaty import tzx

KROK_S = 0.5            # jak často se během nahrávání snímá obrazovka (emulovaný čas)
LIMIT_PASKY_S = 900     # nejdelší emulovaná páska (15 min záznamu)


def k_dispozici() -> str | None:
    """None = emulátor je k dispozici, jinak důvod, proč ne."""
    try:
        from zx._spectrum import Spectrum  # noqa: F401
        return None
    except Exception as e:  # noqa: BLE001
        return f"chybí balíček zx ({e})"


def skore_obrazovky(scr: bytes) -> float:
    """Jak moc obrazovka vypadá jako obrázek: podíl znakových polí s kresbou + počet barev."""
    if len(scr) < 6912:
        return 0.0
    b = np.frombuffer(scr[:6144], np.uint8)
    y = np.arange(192)
    adr = ((y & 0xC0) << 5) | ((y & 0x07) << 8) | ((y & 0x38) << 2)
    radky = b[adr[:, None] + np.arange(32)[None, :]]           # (192, 32)
    pole = radky.reshape(24, 8, 32).transpose(0, 2, 1)          # (24, 32, 8)
    kresba = ~((pole == 0).all(axis=2) | (pole == 255).all(axis=2))
    atr = np.frombuffer(scr[6144:6912], np.uint8)
    barvy = len(set(((atr & 7) | ((atr >> 3) & 7) << 3).tolist()))
    return float(kresba.mean()) + min(barvy, 16) / 32


def _spectrum():
    from zx._spectrum import Spectrum

    class Rychly(Spectrum):
        """Spectrum, které standardní bloky nahraje přímo do paměti (past na LD-BYTES)."""

        def priprav(self, bloky: list[bytes]) -> "Rychly":
            # (konstruktor nejde rozšířit – jádro v C++ nepřijímá další argumenty)
            self.bloky = list(bloky)
            self.snimky: list[bytes] = []
            self.set_breakpoint(0x0556)
            return self

        def on_breakpoint(self) -> None:
            if self.pc != 0x0556:
                return
            flag, adresa, delka = self.a, self.ix, self.de
            nahrat = bool(self.f & 1)                              # CF = LOAD (jinak VERIFY)
            while self.bloky and self.bloky[0][0] != flag:
                self.bloky.pop(0)                                  # ROM by blok s jiným příznakem přeskočila
            ok = False
            if self.bloky:
                b = self.bloky.pop(0)
                data = b[1:-1]
                if nahrat and len(data) >= delka:
                    self.write(adresa, data[:min(delka, 0x10000 - adresa)], ram_page=0)   # 48K: C000h+ = stránka 0
                ok = len(data) >= delka
                self.ix = (adresa + delka) & 0xFFFF
                self.de = 0
            f = (self.af & 0xFF) | 1 if ok else (self.af & 0xFE)    # CF = blok nahrán bez chyby
            self.af = (self.af & 0xFF00) | (f & 0xFF)
            sp = self.sp                                           # RET
            self.pc = int.from_bytes(bytes(self.read(sp, 2)), "little")
            self.sp = (sp + 2) & 0xFFFF
            self.snimky.append(bytes(self.read(0x4000, 6912)))

    return Spectrum, Rychly


def spust(bloky: list[bytes], casovani: list | None = None, sekund_po: float = 4.0) -> dict:
    """Nahraje a spustí program. Vrací {"nahravaci": bytes|None, "po_spusteni": bytes, "zpusob": str}
    (obrazovky jako 6912 B SCREEN$)."""
    duvod = k_dispozici()
    if duvod:
        raise RuntimeError(duvod)
    Spectrum, Rychly = _spectrum()
    from zx._file import parse_file
    turbo = casovani is not None and any(c is not None for c in casovani)
    if not turbo:
        s = Rychly(headless=True).priprav(bloky)
        s.reset_and_wait()
        s.generate_key_strokes("J", "SS+P", "SS+P", "ENTER")     # LOAD ""
        for _ in range(60):                                       # nejvýš 30 s emulace, než se načte vše
            s.run(duration=KROK_S, fast_forward=True)
            if not s.bloky:
                break
        snimky = s.snimky
        zpusob = "rychlé nahrání (ROM)"
    else:
        s = Spectrum(headless=True)
        soubor = Path(tempfile.gettempdir()) / f"sakra-emulace-{os.getpid()}.tzx"
        from .zx import _casovani_tzx
        tzx.zapis_tzx_turbo(soubor, [(b, _casovani_tzx(c)) for b, c in zip(bloky, casovani)])
        s.reset_and_wait()
        s.generate_key_strokes("J", "SS+P", "SS+P", "ENTER")
        s._Spectrum__load_tape_to_player(parse_file(str(soubor)))   # noqa: SLF001 – veřejné API to neumí
        s._Spectrum__unpause_tape()                                  # noqa: SLF001
        snimky = []
        cas = 0.0
        while not s._Spectrum__is_end_of_tape() and cas < LIMIT_PASKY_S:   # noqa: SLF001
            s.run(duration=KROK_S, fast_forward=True)
            cas += KROK_S
            snimky.append(bytes(s.read(0x4000, 6912)))
        soubor.unlink(missing_ok=True)
        zpusob = "emulace pásky (turbo)"
    s.run(duration=sekund_po, fast_forward=True)
    po = bytes(s.read(0x4000, 6912))
    return {"nahravaci": nahravaci_obrazovka(snimky), "po_spusteni": po, "zpusob": zpusob}


def nahravaci_obrazovka(snimky: list[bytes]) -> bytes | None:
    """Obrazovka, která během nahrávání vydržela nejdéle beze změny (hra ji ukazuje, zatímco se nahrává
    hlavní kód) a vypadá jako obrázek – ne prázdná obrazovka po CLS ani výpis BASICu."""
    nejlepsi, delka = None, 0
    i = 0
    while i < len(snimky):
        j = i
        while j + 1 < len(snimky) and snimky[j + 1] == snimky[i]:
            j += 1
        if j - i + 1 > delka and skore_obrazovky(snimky[i]) > 0.15:
            nejlepsi, delka = snimky[i], j - i + 1
        i = j + 1
    return nejlepsi

