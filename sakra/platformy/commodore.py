"""Commodore 64 (a VIC-20) – standardní zavaděč ROM.

Bit = dvojice pulzů (celé periody): krátký S ~390 µs, střední M ~536 µs, dlouhý L ~698 µs (TAP: 30h/42h/56h).
Bajt: značka L M, 8 bitů od LSB (S M = 0, M S = 1), paritní bit (1 XOR všech bitů); konec dat L S.
Blok: úvodní tón (S), odpočet 89h..81h (první kopie) nebo 09h..01h (opakování), data, XOR součet.
Hlavička 192 B: typ (1 = PRG přemístitelný, 3 = PRG, 4 = SEQ, 5 = konec pásky), začátek, konec (LE), jméno 16 znaků.
Každý blok je na pásce dvakrát – poškozená kopie se nahradí druhou.
Výstup: TAP v1 (čistý signál) a PRG (adresa + data).
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import periody, rady, xor
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, pripona, podil_v_pasmu

HODINY = 985248                     # PAL C64
TAP_S, TAP_M, TAP_L = 0x30, 0x42, 0x56
S_US = TAP_S * 8 / HODINY * 1e6
TYPY = {1: "PRG (přemístitelný)", 3: "PRG", 4: "SEQ", 5: "Konec pásky"}
PETSCII = {0xA0: " "}
PETSCII.update({0xC1 + i: chr(65 + i) for i in range(26)})


def _symboly(per: np.ndarray, s: float) -> np.ndarray:
    """0 = S, 1 = M, 2 = L, 3 = mimo (pauza nebo šum)."""
    m, l_ = s * TAP_M / TAP_S, s * TAP_L / TAP_S
    sym = np.full(len(per), 3, np.int8)
    sym[(per > 0.6 * s) & (per <= (s + m) / 2)] = 0
    sym[(per > (s + m) / 2) & (per <= (m + l_) / 2)] = 1
    sym[(per > (m + l_) / 2) & (per < 1.4 * l_)] = 2
    return sym


def _cti_bajty(sym: np.ndarray, i: int):
    """Od značky L M čte bajty. Vrací (bajty, chybné indexy, konec)."""
    out, chyby = [], []
    n = len(sym)
    while i + 20 <= n and sym[i] == 2 and sym[i + 1] == 1:
        bity = []
        spatne = False
        for q in range(9):
            a, b = sym[i + 2 + 2 * q], sym[i + 3 + 2 * q]
            if (a, b) == (0, 1):
                bity.append(0)
            elif (a, b) == (1, 0):
                bity.append(1)
            else:
                bity.append(0)
                spatne = True
        hod = sum(b << k for k, b in enumerate(bity[:8]))
        if spatne or bity[8] != 1 ^ (sum(bity[:8]) & 1):
            chyby.append(len(out))
        out.append(hod)
        i += 20
    return out, chyby, i


def bloky_c64(per: np.ndarray, zac: np.ndarray, rate: int) -> list[Blok]:
    out = []
    pilotni = (per > 0.7 * S_US) & (per < 1.3 * S_US)
    for a, b in rady(pilotni, 60):
        s = float(np.median(per[a:b]))
        sym = _symboly(per[b:b + 200000], s)
        bajty, chyby, konec = _cti_bajty(sym, 0)
        if len(bajty) < 10:
            continue
        odpocet = bajty[:9]
        if odpocet == list(range(0x89, 0x80, -1)):
            kopie = 1
        elif odpocet == list(range(0x09, 0x00, -1)):
            kopie = 2
        else:
            continue
        payload = bytes(bajty[9:-1])
        ok = not chyby and xor(payload) == bajty[-1]
        typ = "hlavička" if len(payload) == 192 and payload[0] in TYPY else "data"
        t0, t1 = float(zac[a]) / rate, float(zac[min(b + konec, len(zac) - 1)]) / rate
        blok = Blok(t0, t1, typ, kopie, payload, ok,
                    chybne_bajty=[] if ok else ([c - 9 for c in chyby if 9 <= c < len(bajty) - 1] or
                                                list(range(len(payload)))))
        blok.info_rychlost = S_US / s  # type: ignore[attr-defined]
        out.append(blok)
    return out


class Commodore64(Platforma):
    id = "c64-rom"
    pocitac = "Commodore 64"
    varianta = ""
    barva = "#6C5EB5"
    pripona = "tap"
    poradi = 40

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram
        return 0.7 if podil_v_pasmu(h, 140, 420) > 0.85 and podil_v_pasmu(h, 150, 240) > 0.3 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky: list[Blok] = []
        for u in useky:
            # perioda se měří mezi sestupnými hranami; při obrácené polaritě nahrávky mezi vzestupnými
            nalez = [bloky_c64(*periody(ktx.pulzy, u.i0, u.i1, smer), ktx.pulzy.rate) for smer in (-1, 1)]
            bloky += max(nalez, key=lambda bl: (sum(b.ok for b in bl), len(bl)))
        bloky.sort(key=lambda b: b.zacatek)
        soubory: list[Soubor] = []
        akt: Soubor | None = None
        for b in bloky:
            if b.typ == "hlavička":
                stejna = akt is not None and any(x.typ == "hlavička" and x.cislo == 1 for x in akt.bloky) \
                    and b.cislo == 2 and not any(x.typ == "data" for x in akt.bloky)
                if not stejna:
                    akt = Soubor(self.id, "", "", "")
                    soubory.append(akt)
            elif akt is None or b.zacatek - akt.konec > 30:
                akt = Soubor(self.id, "", "", "Bez hlavičky")
                soubory.append(akt)
            akt.bloky.append(b)
        rychlost = [getattr(b, "info_rychlost", 1.0) for b in bloky]
        for s in soubory:
            self.dokonci(s)
            s.info["rychlost"] = round(float(np.median(rychlost)), 3) if rychlost else 1.0
        return soubory

    def dokonci(self, s: Soubor) -> None:
        # opakovaná kopie na pásce opraví poškozenou
        for typ in ("hlavička", "data"):
            kopie = [b for b in s.bloky if b.typ == typ]
            dobra = next((b for b in kopie if b.ok), None)
            for b in kopie:
                if not b.ok and dobra is not None:
                    b.data, b.ok, b.chybne_bajty = dobra.data, True, []
                    b.oprava = f"převzato z {'opakované' if dobra.cislo == 2 else 'první'} kopie bloku na pásce"
        hl = next((b for b in s.bloky if b.typ == "hlavička" and b.ok), None)
        dat = next((b for b in s.bloky if b.typ == "data" and b.ok), None)
        if hl:
            h = hl.data
            s.nazev_bloku = jmeno(h[5:21], PETSCII)
            s.nazev = s.nazev_bloku or "(bez jména)"
            s.typ_bloku = TYPY.get(h[0], str(h[0]))
            zac, kon = h[1] | h[2] << 8, h[3] | h[4] << 8
            s.info.update({"typ": s.typ_bloku, "adresa": zac, "delka": kon - zac})
            s.kompletni = h[0] == 5 or (dat is not None and len(dat.data) == kon - zac)
            s.chybi = [] if dat or h[0] == 5 else [2]
        else:
            s.nazev = s.nazev or f"(bez hlavičky, {len(dat.data) if dat else 0} B)"
            s.kompletni = dat is not None
            s.chybi = []
        data = dat.data if dat else b""
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky), "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = [pripona(cil, ".tap")]
        out[0].write_bytes(tap_v1(s.bloky))
        hl = next((b for b in s.bloky if b.typ == "hlavička" and b.ok), None)
        dat = next((b for b in s.bloky if b.typ == "data" and b.ok), None)
        if hl and dat and hl.data[0] in (1, 3):
            out.append(pripona(cil, ".prg"))
            out[-1].write_bytes(hl.data[1:3] + dat.data)
        return out


def _pulzy_bloku(payload: bytes, kopie: int, hlavicka: bool) -> list[int]:
    if kopie == 1:
        pilot = 0x6A00 if hlavicka else 0x1A00
        odpocet = range(0x89, 0x80, -1)
    else:
        pilot = 0x4F
        odpocet = range(0x09, 0x00, -1)
    out = [TAP_S] * pilot
    for v in list(odpocet) + list(payload) + [xor(payload)]:
        out += [TAP_L, TAP_M]
        for q in range(8):
            out += [TAP_M, TAP_S] if v >> q & 1 else [TAP_S, TAP_M]
        out += [TAP_M, TAP_S] if 1 ^ (bin(v).count("1") & 1) else [TAP_S, TAP_M]
    out += [TAP_L, TAP_S]
    out += [TAP_S] * (0x4E if kopie == 2 else 0)
    return out


def tap_v1(bloky: list[Blok]) -> bytes:
    """Čistý TAP v1: každý blok v obou kopiích s jmenovitými délkami pulzů, pauzy 0 + takty (24 bitů)."""
    data = bytearray()
    for typ in ("hlavička", "data"):
        b = next((x for x in bloky if x.typ == typ and x.ok), None)
        if b is None:
            continue
        for kopie in (1, 2):
            data += bytes(_pulzy_bloku(b.data, kopie, typ == "hlavička"))
        data += b"\x00" + struct.pack("<I", HODINY // 2)[:3]      # pauza 0,5 s
    return b"C64-TAPE-RAW" + bytes([1, 0, 0, 0]) + struct.pack("<I", len(data)) + bytes(data)
