"""Frekvenční modulace 1200/2400 Hz: MSX a Acorn (BBC Micro, Electron).

Bit 0 = jedna perioda 1200 Hz (dvě dlouhé půlvlny), bit 1 = dvě periody 2400 Hz (čtyři krátké); při 2400 Bd
(MSX) poloviční délky. Bajt: start 0, 8 bitů od LSB, stop 1 (MSX 2 stop bity). Před blokem nosná 2400 Hz.
MSX: hlavička 16 B = 10× typ (D3h BASIC, EAh ASCII, D0h binární) + jméno 6 znaků; pak datové bloky.
  Formát nemá kontrolní součet. Výstup CAS (fMSX): před každým blokem značka 1F A6 DE BA CC 13 7D 74
  zarovnaná na násobek 8 B.
Acorn: blok 2Ah, jméno (≤ 10 znaků, 00h), načítací a spouštěcí adresa (4+4 B), číslo bloku, délka (2+2 B),
  příznak (bit 7 = poslední), 4 B, CRC hlavičky, data, CRC dat (CRC-16 0x1021, vyšší bajt první).
  Výstup UEF (nosná 0110h, data 0100h, pauza 0116h).
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import behy_us, rady, uart
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, pripona, podil_v_pasmu

CAS_ZNACKA = bytes([0x1F, 0xA6, 0xDE, 0xBA, 0xCC, 0x13, 0x7D, 0x74])
TYPY_MSX = {0xD3: "BASIC", 0xEA: "ASCII", 0xD0: "Binární"}


def fsk_bity(r: np.ndarray, s: float) -> tuple[list[int], list[int]]:
    """Půlvlny -> bity (LL = 0, SSSS = 1). Vrací (bity, index půlvlny začátku bitu)."""
    tr = np.where((r > 0.55 * s) & (r <= 1.5 * s), 0, np.where((r > 1.5 * s) & (r < 2.8 * s), 1, 2))
    t = tr.tolist()
    n = len(t)
    bity, kde = [], []
    i = 0
    while i + 1 < n:
        if t[i] == 1 and t[i + 1] == 1:
            bity.append(0)
            kde.append(i)
            i += 2
        elif i + 3 < n and t[i] == t[i + 1] == t[i + 2] == t[i + 3] == 0:
            bity.append(1)
            kde.append(i)
            i += 4
        else:
            i += 1
    return bity, kde


def crc_acorn(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def bloky_fsk(p, u: Usek) -> list[tuple[float, float, list[int], list[bool], float]]:
    """Bloky za nosnou: (začátek, konec, bajty, rámec v pořádku, délka krátké půlvlny µs)."""
    r = behy_us(p, u.i0, u.i1)
    kr = r[(r > 60) & (r < 330)]
    if len(kr) < 200:
        return []
    s0 = float(np.median(kr))
    nosne = rady((r > 0.7 * s0) & (r < 1.35 * s0), 300)
    out = []
    for j, (a, b) in enumerate(nosne):
        s = float(np.median(r[a:b]))
        # stop bit posledního bajtu splývá s následující nosnou – vezme se i kousek z ní
        konec = nosne[j + 1][0] + 16 if j + 1 < len(nosne) else len(r)
        bity, kde = fsk_bity(r[b - 8:konec], s)          # kousek nosné kvůli prvnímu start bitu
        if len(bity) < 20:
            continue
        ramce = uart(np.array(bity, np.int8), 8, 1)
        if not ramce:
            continue
        # jen souvislý začátek bloku (za ním může být šum nebo ticho)
        hod, oks, posl = [], [], ramce[0][0] - 10
        for i, v, ok in ramce:
            if i - posl > 40:
                break
            hod.append(v)
            oks.append(ok)
            posl = i
        t0 = p.cas(u.i0 + a)
        t1 = p.cas(u.i0 + b - 8 + kde[min(len(kde) - 1, posl + 10)])
        out.append((t0, t1, hod, oks, s))
    return out


class MSX(Platforma):
    id = "msx"
    pocitac = "MSX"
    varianta = ""
    barva = "#4F81BD"
    pripona = "cas"
    poradi = 45

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram
        return 0.7 if podil_v_pasmu(h, 80, 500) > 0.85 and podil_v_pasmu(h, 80, 250) > 0.4 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky = []
        for u in useky:
            bloky += bloky_fsk(ktx.pulzy, u)
        return _msx_soubory(bloky) + _acorn_soubory(bloky)

    def dokonci(self, s: Soubor) -> None:
        hl = s.bloky[0] if s.bloky and s.bloky[0].typ == "hlavička" else None
        dat = [b for b in s.bloky if b.typ == "data"]
        if hl:
            s.nazev_bloku = jmeno(hl.data[10:16])
            s.nazev = s.nazev_bloku or "(bez jména)"
            s.typ_bloku = TYPY_MSX.get(hl.data[0], f"{hl.data[0]:02X}h")
        else:
            s.nazev = s.nazev or "(bez hlavičky)"
            s.typ_bloku = s.typ_bloku or "Bez hlavičky"
        data = b"".join(b.data for b in dat)
        s.kompletni = bool(dat) and (hl is not None or True)
        if hl and hl.data[0] == 0xD0 and dat:
            d = dat[0].data
            if len(d) >= 6:
                z, k, sp = struct.unpack_from("<HHH", d)
                s.info.update({"adresa": z, "konec": k, "spusteni": sp})
                s.kompletni = len(d) >= 6 + k - z + 1
        if hl and hl.data[0] == 0xEA:
            s.kompletni = b"\x1a" in data
        if hl and hl.data[0] == 0xD3:
            s.kompletni = bool(dat) and b"\x00" * 3 in dat[-1].data[-10:]
        s.chybi = [] if dat else [2]
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky), "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        cas = bytearray()
        for b in s.bloky:
            while len(cas) % 8:
                cas.append(0)
            cas += CAS_ZNACKA + b.data
        out = [pripona(cil, ".cas")]
        out[0].write_bytes(bytes(cas))
        return out


def _blok(t0, t1, hod, oks, typ, cislo=None) -> Blok:
    ok = all(oks)
    return Blok(t0, t1, typ, cislo, bytes(hod), ok, chybne_bajty=[i for i, x in enumerate(oks) if not x])


def _msx_soubory(bloky) -> list[Soubor]:
    soubory: list[Soubor] = []
    akt: Soubor | None = None
    for t0, t1, hod, oks, s in bloky:
        if hod and hod[0] == 0x2A:            # blok Acorn
            akt = None
            continue
        hlav = len(hod) >= 16 and hod[0] in TYPY_MSX and len(set(hod[:10])) == 1
        if hlav:
            akt = Soubor(MSX.id, "", "", "", overeno=False)
            akt.bloky.append(_blok(t0, t1, hod[:16], oks[:16], "hlavička"))
            akt.info["baud"] = 1200 if s > 150 else 2400
            soubory.append(akt)
            continue
        if akt is None or (akt.bloky and t0 - akt.konec > 30) or _msx_hotovo(akt):
            akt = Soubor(MSX.id, "", "", "Bez hlavičky", overeno=False)
            soubory.append(akt)
        akt.bloky.append(_blok(t0, t1, hod, oks, "data"))
    out = []
    for s in soubory:
        MSX().dokonci(s)
        # blok bez hlavičky nejde odlišit od náhodně „přečtené“ nosné nebo cizího signálu
        if s.bloky[0].typ == "hlavička":
            out.append(s)
    return out


def _msx_hotovo(s: Soubor) -> bool:
    hl = s.bloky[0] if s.bloky[0].typ == "hlavička" else None
    dat = [b for b in s.bloky if b.typ == "data"]
    if not dat or hl is None:
        return bool(dat)
    if hl.data[0] == 0xEA:
        return any(b"\x1a" in b.data for b in dat)
    return True


# =====================================================================  Acorn

def _acorn_blok(hod: list[int], oks: list[bool]):
    """Rozbor bloku od 2Ah. Vrací (jméno, hlavička, data, číslo, poslední, ok, chybné) nebo None."""
    if len(hod) < 20 or hod[0] != 0x2A:
        return None
    try:
        k = hod.index(0, 1, 12)
    except ValueError:
        return None
    jm = bytes(hod[1:k])
    h = bytes(hod[k + 1:k + 1 + 17])
    if len(h) < 17:
        return None
    nacti, spust, cislo, delka, priznak = struct.unpack_from("<IIHHB", h)
    hcrc = hod[k + 18] << 8 | hod[k + 19] if k + 19 < len(hod) else -1
    h_ok = crc_acorn(bytes(hod[1:k + 18])) == hcrc
    d0 = k + 20
    data = bytes(hod[d0:d0 + delka])
    dcrc = hod[d0 + delka] << 8 | hod[d0 + delka + 1] if d0 + delka + 1 < len(hod) else -1
    d_ok = delka == 0 or (len(data) == delka and crc_acorn(data) == dcrc)
    surove = bytes(hod[:d0 + delka + (2 if delka else 0)])
    ok = h_ok and d_ok and all(oks[:len(surove)])
    return jm, nacti, spust, cislo, delka, priznak, data, surove, ok


def _acorn_soubory(bloky) -> list[Soubor]:
    soubory: list[Soubor] = []
    akt: Soubor | None = None
    for t0, t1, hod, oks, _ in bloky:
        r = _acorn_blok(hod, oks)
        if r is None:
            continue
        jm, nacti, spust, cislo, delka, priznak, data, surove, ok = r
        b = Blok(t0, t1, "data", cislo, surove, ok, chybne_bajty=[] if ok else list(range(len(surove))))
        nazev = jmeno(jm)
        if akt is None or cislo == 0 or nazev != akt.nazev_bloku or t0 - akt.konec > 30:
            akt = Soubor(Acorn.id, "", nazev, "")
            soubory.append(akt)
        akt.bloky.append(b)
    for s in soubory:
        Acorn().dokonci(s)
    return soubory


class Acorn(Platforma):
    """BBC Micro / Acorn Electron – dekóduje MSX (stejná modulace), soubory se sem přeřadí podle obsahu."""
    id = "acorn"
    pocitac = "BBC Micro / Acorn Electron"
    varianta = ""
    barva = "#C0504D"
    pripona = "uef"
    poradi = 46

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        return []

    def dokonci(self, s: Soubor) -> None:
        s.nazev = s.nazev_bloku or "(bez jména)"
        rozbory = [(_acorn_blok(list(b.data), [True] * len(b.data)), b) for b in s.bloky]
        data = b""
        cisla = []
        posledni = False
        for r, b in rozbory:
            if r is None:
                continue
            jm, nacti, spust, cislo, delka, priznak, d, _, _ = r
            if b.ok:
                data += d
            cisla.append(cislo)
            posledni |= bool(priznak & 0x80)
            if cislo == 0:
                s.info.update({"adresa": nacti & 0xFFFF, "spusteni": spust & 0xFFFF})
        horni = max(cisla) if cisla else -1
        s.chybi = [n for n in range(0, horni + 1) if n not in cisla]
        s.kompletni = posledni and not s.chybi and 0 in cisla
        s.typ_bloku = "Soubor"
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky), "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = [pripona(cil, ".uef")]
        out[0].write_bytes(uef([b.data for b in s.bloky]))
        if not hasattr(s, "_data"):
            self.dokonci(s)
        out.append(pripona(cil, ".bin"))
        out[-1].write_bytes(s._data)  # type: ignore[attr-defined]
        return out


def _chunk(cislo: int, data: bytes) -> bytes:
    return struct.pack("<HI", cislo, len(data)) + data


def uef(bloky: list[bytes]) -> bytes:
    out = bytearray(b"UEF File!\x00" + bytes([10, 0]))
    for i, b in enumerate(bloky):
        out += _chunk(0x0110, struct.pack("<H", 12000 if i == 0 else 1440))   # nosná (periody 2400 Hz)
        out += _chunk(0x0100, b)
        out += _chunk(0x0110, struct.pack("<H", 600))
        out += _chunk(0x0116, struct.pack("<f", 1.0 if i + 1 < len(bloky) else 2.0))
    return bytes(out)
