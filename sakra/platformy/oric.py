"""Oric-1 / Atmos.

Rychlý záznam: bit 1 = jedna perioda 2400 Hz (krátká + krátká půlvlna), bit 0 = krátká + dlouhá (1200 Hz).
Pomalý záznam: bit 0 = 4 periody 1200 Hz, bit 1 = 8 period 2400 Hz.
Bajt: start 0, 8 bitů od LSB, parita (1 při sudém počtu jedniček), 3–4 stop bity 1.
Soubor: úvod 16h…, synchronizace 24h, hlavička 9 B (typ, autostart, konec a začátek – big endian),
jméno ukončené 00h, data (konec − začátek + 1 B). Kontrolní součet záznam nemá – kontroluje se parita bajtů.
Výstup: TAP (16 16 16 24 + hlavička + jméno + 00 + data).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import behy_us, uart
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, pripona, podil_v_pasmu


def _parita(v: int) -> int:
    return 1 ^ (bin(v).count("1") & 1)


def bity_rychle(r: np.ndarray, s: float):
    t = np.where((r > 0.55 * s) & (r <= 1.5 * s), 0, np.where((r > 1.5 * s) & (r < 2.6 * s), 1, 2)).tolist()
    bity, kde = [], []
    i = 0
    while i + 1 < len(t):
        if t[i] == 0 and t[i + 1] in (0, 1):
            bity.append(1 - t[i + 1])
            kde.append(i)
            i += 2
        else:
            i += 1
    return bity, kde


def bity_pomale(r: np.ndarray, s: float):
    t = np.where((r > 0.55 * s) & (r <= 1.5 * s), 0, np.where((r > 1.5 * s) & (r < 2.6 * s), 1, 2))
    bity, kde = [], []
    zm = np.flatnonzero(np.diff(np.concatenate(([-1], t, [-1]))))
    for a, b in zip(zm[:-1], zm[1:]):
        c = int(t[a]) if a < len(t) else 2
        n = b - a
        if c == 1:
            k = int(round(n / 8))
            bity += [0] * k
            kde += [a + 8 * j for j in range(k)]
        elif c == 0:
            k = int(round(n / 16))
            bity += [1] * k
            kde += [a + 16 * j for j in range(k)]
    return bity, kde


def _ramec(v: int) -> str:
    return "0" + "".join(str(v >> q & 1) for q in range(8)) + str(_parita(v))


# 16h 16h 24h s libovolným počtem stop bitů – podle něj se zarovnají rámce (úvod se opakuje, takže
# špatně zarovnané rámce by jinak mohly vycházet „platně“)
SYNC = re.compile(_ramec(0x16) + "1{1,8}" + _ramec(0x16) + "1{1,8}(" + _ramec(0x24) + ")")


def soubory_z_bitu(bity: list[int], cas) -> list[dict]:
    retezec = "".join(map(str, bity))
    pole = np.array(bity, np.int8)
    out = []
    konec = 0
    for m in SYNC.finditer(retezec):
        if m.start(1) < konec:
            continue
        ramce = uart(pole, 8, 1, parita=_parita, od=m.start(1))
        f = _soubor(ramce, cas)
        if f:
            out.append(f)
            konec = f["konec_bitu"]
    return out


def _soubor(ramce, cas) -> dict | None:
    """Rámce od synchronizačního 24h: hlavička 9 B, jméno do 00h, data."""
    hod = [v for _, v, _ in ramce]
    oks = [ok for _, _, ok in ramce]
    h = hod[1:10]
    if len(h) < 9:
        return None
    k = 10
    jm = []
    while k < len(hod) and hod[k] != 0 and len(jm) < 17:
        jm.append(hod[k])
        k += 1
    k += 1
    zac, kon = h[6] << 8 | h[7], h[4] << 8 | h[5]
    n = kon - zac + 1
    if n <= 0 or n > 0xC000:
        return None
    data = hod[k:k + n]
    posl = ramce[min(k + n, len(ramce) - 1)][0]
    return {"h": bytes(h), "jmeno": bytes(jm), "data": bytes(data), "ok": all(oks[:k + n]) and len(data) == n,
            "t0": cas(max(0, ramce[0][0] - 14 * 40)), "t1": cas(posl), "konec_bitu": posl,
            "chybne": [x - k for x in range(k, min(k + n, len(oks))) if not oks[x]]}


class Oric(Platforma):
    id = "oric"
    pocitac = "Oric"
    varianta = ""
    barva = "#E07B39"
    pripona = "tap"
    poradi = 47

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram
        return 0.7 if podil_v_pasmu(h, 120, 520) > 0.85 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        p = ktx.pulzy
        out: list[Soubor] = []
        for u in useky:
            r = behy_us(p, u.i0, u.i1)
            kr = r[(r > 120) & (r < 300)]
            if len(kr) < 200:
                continue
            s = float(np.median(kr))
            for rychlost, fce in (("rychlý", bity_rychle), ("pomalý", bity_pomale)):
                bity, kde = fce(r, s)
                if len(bity) < 13 * 20:
                    continue
                cas = lambda bi: p.cas(u.i0 + kde[min(bi, len(kde) - 1)])  # noqa: E731
                nalez = soubory_z_bitu(bity, cas)
                for f in nalez:
                    data = f["h"] + f["jmeno"] + b"\0" + f["data"]
                    b = Blok(f["t0"], f["t1"], "data", None, data, f["ok"],
                             chybne_bajty=[] if f["ok"] else [9 + len(f["jmeno"]) + 1 + c for c in f["chybne"]])
                    s_ = Soubor(self.id, "", jmeno(f["jmeno"]), "", bloky=[b], overeno=False)
                    s_.info["zaznam"] = rychlost
                    self.dokonci(s_)
                    out.append(s_)
                if nalez:
                    break
        return out

    def dokonci(self, s: Soubor) -> None:
        d = s.bloky[0].data
        h = d[:9]
        k = d.index(0, 9) if 0 in d[9:] else len(d)
        data = d[k + 1:]
        zac, kon = h[6] << 8 | h[7], h[4] << 8 | h[5]
        s.nazev = s.nazev_bloku or "(bez jména)"
        s.typ_bloku = "BASIC" if h[2] == 0 else "Strojový kód" if h[2] == 0x80 else f"{h[2]:02X}h"
        s.kompletni = len(data) == kon - zac + 1
        s.chybi = []
        s.info.update({"adresa": zac, "konec": kon, "autostart": "ano" if h[3] else "ne",
                       "delka_dat": len(data), "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = pripona(cil, ".tap")
        out.write_bytes(b"\x16\x16\x16\x24" + s.bloky[0].data)
        return [out]
