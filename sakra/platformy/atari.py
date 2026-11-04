"""Atari 8bit (400/800/XL/XE) – standardní záznam SIO 600 Bd.

FSK: značka (1) 5327 Hz, mezera (0) 3995 Hz. Bajt: start 0, 8 bitů od LSB, stop 1.
Záznam 132 B: 55h 55h (synchronizace rychlosti), řídicí bajt (FCh plný, FAh částečný – počet platných
bajtů je v posledním bajtu dat, FEh konec souboru), 128 B dat, součet (sčítání s přenosem přes všech 131 B).
Výstup: CAS (FUJI, baud, data – mezera před záznamem v ms) a podle obsahu XEX (binární soubor FFFFh),
BAS (tokenizovaný BASIC) nebo BIN (zaváděcí soubor).
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from .. import __version__
from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import dve_shluky
from ..jadro.texty import texty
from .zaklad import Kontext, Platforma, pripona, podil_v_pasmu

BAUD = 600
RIZENI = {0xFC: "plný", 0xFA: "částečný", 0xFE: "konec"}


def soucet_atari(data: bytes) -> int:
    s = 0
    for b in data:
        s += b
        if s > 255:
            s = (s & 0xFF) + 1
    return s


def uroven_fsk(p, i0: int, i1: int):
    """Časy (µs) hran a úroveň po každé hraně: 1 = značka, 0 = mezera (podle délky celé periody)."""
    t = (p.hrany[i0:i1 + 1] - p.hrany[i0]) * (1e6 / p.rate)
    r = np.diff(t)
    per = r[:-1] + r[1:]
    v = (per > 120) & (per < 340)
    if v.sum() < 500:
        return None
    a, b = dve_shluky(per[v])
    if b / max(a, 1) < 1.15:                  # jen jedna frekvence – není to FSK Atari
        prah = 219.0
    else:
        prah = (a + b) / 2
    hod = (per < prah).astype(np.int8)
    # medián přes 3 periody potlačí jednotlivé zákmity
    if len(hod) > 3:
        hod = ((hod[:-2] + hod[1:-1] + hod[2:]) >= 2).astype(np.int8)
        hod = np.concatenate(([hod[0]], hod, [hod[-1]]))
    ticho = per > 600
    hod[ticho] = 1
    return t[:-2], hod


def bajty_uart(t: np.ndarray, hod: np.ndarray, tb: float):
    """UART v čase: hledá přechody 1→0 (start bit) a vzorkuje středy bitů. Vrací [(čas startu, bajt, ok)]."""
    out = []
    zm = np.flatnonzero((hod[:-1] == 1) & (hod[1:] == 0)) + 1
    konec_predchoziho = -1e18
    for k in zm:
        t0 = t[k]
        if t0 < konec_predchoziho:
            continue
        casy = t0 + tb * (0.5 + np.arange(10))
        if casy[-1] > t[-1]:
            break
        idx = np.searchsorted(t, casy, side="right") - 1
        b = hod[idx]
        if b[0] != 0:
            continue
        v = int((b[1:9].astype(np.int32) << np.arange(8)).sum())
        out.append((t0, v, bool(b[9] == 1)))
        konec_predchoziho = t0 + 9.6 * tb
    return out


def zaznamy(ramce, tb: float) -> list[tuple[float, float, list, list]]:
    """Seskupí bajty do záznamů (mezi nimi mezera delší než 4 bajty)."""
    out = []
    akt: list = []
    for r in ramce:
        if akt and r[0] - akt[-1][0] > 40 * tb:
            out.append(akt)
            akt = []
        akt.append(r)
    if akt:
        out.append(akt)
    vysl = []
    for z in out:
        # začátek záznamu = první 55h 55h
        i = next((j for j in range(len(z) - 1) if z[j][1] == 0x55 and z[j + 1][1] == 0x55), None)
        if i is None:
            continue
        z = z[i:i + 132]
        vysl.append((z[0][0], z[-1][0] + 10 * tb, [x[1] for x in z], [x[2] for x in z]))
    return vysl


class Atari(Platforma):
    id = "atari-rom"
    pocitac = "Atari 8bit"
    varianta = ""
    barva = "#D35F8D"
    pripona = "cas"
    poradi = 48

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram
        return 0.7 if podil_v_pasmu(h, 60, 170) > 0.85 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        p = ktx.pulzy
        bloky: list[Blok] = []
        for u in useky:
            uv = uroven_fsk(p, u.i0, u.i1)
            if uv is None:
                continue
            t, hod = uv
            t0 = p.cas(u.i0)
            for zac, kon, hodn, oks in zaznamy(bajty_uart(t, hod, 1e6 / BAUD), 1e6 / BAUD):
                # zpřesnění rychlosti podle synchronizačních bajtů 55h 55h a nové čtení
                data = bytes(hodn)
                ok = len(data) == 132 and all(oks) and soucet_atari(data[:131]) == data[131]
                if not ok and len(hodn) >= 2:
                    for f in (0.94, 1.06, 0.97, 1.03, 0.9, 1.1):
                        tb = 1e6 / BAUD * f
                        z2 = [z for z in zaznamy(bajty_uart(t, hod, tb), tb) if abs(z[0] - zac) < 20 * tb]
                        if z2:
                            d2 = bytes(z2[0][2])
                            if len(d2) == 132 and all(z2[0][3]) and soucet_atari(d2[:131]) == d2[131]:
                                data, oks, ok = d2, z2[0][3], True
                                break
                if len(data) < 4 or data[2] not in RIZENI:
                    continue
                b = Blok(t0 + zac / 1e6, t0 + kon / 1e6, RIZENI[data[2]], None, data, ok,
                         chybne_bajty=[] if ok else [i for i, x in enumerate(oks) if not x] or list(range(len(data))))
                bloky.append(b)
        bloky.sort(key=lambda b: b.zacatek)
        soubory: list[Soubor] = []
        akt: Soubor | None = None
        for i, b in enumerate(bloky):
            b.cislo = None
            if akt is None or akt.info.get("_uzavren") or b.zacatek - akt.konec > 25:
                akt = Soubor(self.id, "", "", "")
                soubory.append(akt)
            b.cislo = len(akt.bloky) + 1
            akt.bloky.append(b)
            if b.typ == "konec":
                akt.info["_uzavren"] = True
        for s in soubory:
            s.info.pop("_uzavren", None)
            self.dokonci(s)
        return soubory

    def dokonci(self, s: Soubor) -> None:
        data = bytearray()
        konec = False
        for b in s.bloky:
            if b.typ == "plný":
                data += b.data[3:131]
            elif b.typ == "částečný":
                data += b.data[3:3 + min(b.data[130], 128)]
            elif b.typ == "konec":
                konec = True
        d = bytes(data)
        if d[:2] == b"\xff\xff":
            s.typ_bloku, s.info["pripona"] = "Binární (XEX)", ".xex"
        elif d[:2] == b"\x00\x00":
            s.typ_bloku, s.info["pripona"] = "BASIC", ".bas"
        else:
            s.typ_bloku, s.info["pripona"] = "Zaváděcí", ".bin"
        s.kompletni = konec
        s.chybi = []
        txt = texty(d)
        s.nazev = s.nazev_bloku or (txt[0][:24] if txt else "(bez jména)")
        s.info.update({"delka_dat": len(d), "zaznamu": len(s.bloky), "texty": txt})
        s._data = d  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        if not hasattr(s, "_data"):
            self.dokonci(s)
        out = [pripona(cil, ".cas"), pripona(cil, s.info.get("pripona", ".bin"))]
        out[0].write_bytes(cas_soubor([(b.data, b.zacatek) for b in s.bloky if b.ok], f"SAKRA {__version__}: {s.nazev}"))
        out[1].write_bytes(s._data)  # type: ignore[attr-defined]
        return out


def _chunk(typ: bytes, aux: int, data: bytes = b"") -> bytes:
    return typ + struct.pack("<HH", len(data), aux & 0xFFFF) + data


def cas_soubor(zaznamy_: list[tuple[bytes, float]], popis: str = "") -> bytes:
    out = _chunk(b"FUJI", 0, popis.encode("utf-8")) + _chunk(b"baud", BAUD)
    predchozi = None
    for data, t in zaznamy_:
        irg = 20000 if predchozi is None else int(max(0.0, t - predchozi) * 1000)
        out += _chunk(b"data", min(irg, 65535), data)
        predchozi = t + len(data) * 10 / BAUD
    return out
