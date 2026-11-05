"""Sharp MZ-700 / MZ-800 (a MZ-80A) – standardní záznam ROM (podle zdrojů MAME, mz_cas).

Bit = jedna perioda: krátká (~520 µs) = 0, dlouhá (~960 µs) = 1. Bajt = dlouhý start bit + 8 bitů od MSB.
Hlavička: 22 000 krátkých, značka 40 dlouhých + 40 krátkých + 1 dlouhý, 128 B, součet (počet jedniček, 2 B, vyšší
první), dlouhý, 256 krátkých, kopie hlavičky se součtem, dlouhý. Tělo stejně se značkou 20 + 20 + 1.
Hlavička: atribut, jméno 17 znaků (konec 0Dh), velikost, zaváděcí a spouštěcí adresa (LE), komentář.
Výstup: MZF (hlavička 128 B + data).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import dve_shluky, periody
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, pripona, podil_v_pasmu

TYPY = {1: "Strojový kód (OBJ)", 2: "BASIC (BTX)", 3: "Data BASICu (BSD)", 4: "BASIC (BRD)", 5: "RB"}


def _soucet(data: bytes) -> int:
    return sum(bin(b).count("1") for b in data) & 0xFFFF


def _cti(v: np.ndarray, k: int, n: int):
    """n bajtů od k (každý: start 1 + 8 bitů od MSB). Vrací (bajty, chybné indexy, konec)."""
    out, chyby = [], []
    for j in range(n):
        i = k + 9 * j
        if i + 9 > len(v):
            out += [0] * (n - j)
            chyby += list(range(j, n))
            return bytes(out), chyby, len(v)
        bity = v[i + 1:i + 9]
        if v[i] != 1 or not np.isin(bity, (0, 1)).all():       # neurčený bit (mimo 0/1) = chybný bajt
            chyby.append(j)
        out.append(int(((bity == 1).astype(np.int32) << np.arange(7, -1, -1)).sum()))
    return bytes(out), chyby, k + 9 * n


def _blok(v, zac, k: int, n: int, typ: str, rate: int) -> Blok:
    """Blok s kopií: vezme první čtení se správným součtem."""
    poznamka = ""
    for pokus, kk in enumerate((k, k + 9 * (n + 2) + 1 + 256)):
        d, chyby, konec = _cti(v, kk, n + 2)
        data, sc = d[:n], d[n] << 8 | d[n + 1]
        if not chyby and _soucet(data) == sc:
            poznamka = "převzato z kopie bloku na pásce" if pokus else ""
            b = Blok(float(zac[k]) / rate, float(zac[min(konec, len(zac) - 1)]) / rate, typ, None, data, True,
                     oprava=poznamka, soucet_pasky=sc)
            return b
        if pokus == 0:
            prvni = (data, chyby, konec, sc)
    data, chyby, konec, sc = prvni
    return Blok(float(zac[k]) / rate, float(zac[min(konec, len(zac) - 1)]) / rate, typ, None, data, False,
                chybne_bajty=[c for c in chyby if c < n] or list(range(n)), soucet_pasky=sc)


def bloky_mz(per: np.ndarray, zac: np.ndarray, rate: int, stav: dict) -> list[Blok]:
    """`stav["hl"]` = poslední přečtená hlavička (tělo bývá za pauzou v dalším úseku nahrávky)."""
    m = (per > 250) & (per < 2000)
    if m.sum() < 1000:
        return []
    kratka, dlouha = dve_shluky(per[m])
    if dlouha / max(kratka, 1) < 1.5:
        return []
    v = np.where(per > (kratka + dlouha) / 2, 1, 0).astype(np.int8)
    v[per > 2.5 * dlouha] = 2
    zm = np.flatnonzero(np.diff(np.concatenate(([-1], v, [-1]))))
    behy = list(zip(zm[:-1], zm[1:]))
    out = []
    for i in range(len(behy) - 2):
        (a1, b1), (a2, b2), (a3, _) = behy[i], behy[i + 1], behy[i + 2]
        n1, n2 = b1 - a1, b2 - a2
        if not (v[a1] == 1 and v[a2] == 0 and v[a3] == 1):
            continue
        if 30 <= n1 <= 45 and 30 <= n2 <= 45:
            b = _blok(v, zac, a3 + 1, 128, "hlavička", rate)
            out.append(b)
            stav["hl"] = b if b.ok else None
        elif 15 <= n1 <= 25 and 15 <= n2 <= 25:
            hl = stav.get("hl")
            n = (hl.data[0x12] | hl.data[0x13] << 8) if hl is not None else None
            if n:
                out.append(_blok(v, zac, a3 + 1, n, "data", rate))
    return out


class SharpMZ(Platforma):
    id = "sharp-mz"
    pocitac = "Sharp MZ-700/800"
    varianta = ""
    barva = "#5B9BD5"
    pripona = "mzf"
    poradi = 55

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram
        return 0.7 if podil_v_pasmu(h, 180, 600) > 0.85 and podil_v_pasmu(h, 180, 330) > 0.4 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky: list[Blok] = []
        stav: dict = {}
        for u in useky:
            nalez = []
            for smer in (1, -1):
                st = dict(stav)
                nalez.append((bloky_mz(*periody(ktx.pulzy, u.i0, u.i1, smer), ktx.pulzy.rate, st), st))
            nejlepsi, stav = max(nalez, key=lambda x: (sum(b.ok for b in x[0]), len(x[0])))
            bloky += nejlepsi
        soubory: list[Soubor] = []
        akt: Soubor | None = None
        for b in sorted(bloky, key=lambda x: x.zacatek):
            if b.typ == "hlavička" or akt is None:
                akt = Soubor(self.id, "", "", "")
                soubory.append(akt)
            akt.bloky.append(b)
        for s in soubory:
            self.dokonci(s)
        return soubory

    def dokonci(self, s: Soubor) -> None:
        hl = s.bloky[0] if s.bloky[0].typ == "hlavička" else None
        dat = next((b for b in s.bloky if b.typ == "data"), None)
        if hl:
            h = hl.data
            s.nazev_bloku = jmeno(h[1:18].split(b"\r")[0])
            s.nazev = s.nazev_bloku or "(bez jména)"
            s.typ_bloku = TYPY.get(h[0], f"{h[0]:02X}h")
            n = h[0x12] | h[0x13] << 8
            s.info.update({"adresa": h[0x14] | h[0x15] << 8, "spusteni": h[0x16] | h[0x17] << 8, "delka": n,
                           "komentar": jmeno(h[0x18:0x80])})
            s.kompletni = hl.ok and dat is not None and len(dat.data) == n
        else:
            s.nazev, s.kompletni = "(bez hlavičky)", False
        s.chybi = [] if dat else [2]
        data = dat.data if dat else b""
        s.info.update({"delka_dat": len(data), "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = pripona(cil, ".mzf")
        hl = s.bloky[0].data if s.bloky[0].typ == "hlavička" else bytes(128)
        dat = next((b.data for b in s.bloky if b.typ == "data"), b"")
        out.write_bytes(hl + dat)
        return [out]
