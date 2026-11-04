"""PMD 85 (a Didaktik Alfa, Consul 2717) a Maťo.

PMD 85 – podle pmd2ptp (J. Heřman), formátu PTP z PMD 85 Infoserveru a zdrojů MAME
  Bifázová modulace (Manchester), 1200 Bd: půlbit 1/2400 s ≈ 417 µs. Bajt = rámec 11 bitů: 0, d0..d7, 1, 1.
  Úvodní tón ze samých 1. Hlavička 63 B: 16× FFh, 16× 00h, 16× 55h, číslo souboru, typ (znak),
  adresa (LE), délka − 1 (LE), jméno 8 znaků, součet bajtů 48..61. Za pauzou (samé 1) tělo:
  délka + 1 bajtů dat a součet. Za tělem mohou být nestandardní bloky bez kontroly (dohrávané části).
Maťo – podle matowav2ptp (J. Heřman)
  Bit = jedna perioda (měřená mezi sestupnými průchody nulou): do ~1180 µs = 0, delší = 1.
  Bajt = start bit 1 a 8 bitů od LSB. Hlavička 16 B: 55h, číslo, '>', 01h 24h (adresa 2401h), délka,
  jméno 8, součet bajtů 1..14. Tělo: délka + 2 B, první bajt je posunutý o bit vpravo, poslední je součet.
  Výstupem je PTP s hlavičkou PMD 85 (16× FFh, 16× 00h, 15× 55h + hlavička Maťa).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..formaty import ptp
from ..jadro.manchester import hrany_z_jedne_polarity, manchester, odhad_pulbitu, pulbity, ramce, runy_z_pulbitu
from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Pulzy, Usek
from ..jadro.signaly import periody
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, manchester_skore, pripona, podil_v_pasmu

PMD_T_US = 1e6 / 2400
UVOD = bytes([0xFF] * 16 + [0x00] * 16 + [0x55] * 16)
TYPY_PMD = {
    "?": "Monitor (MGSV)", ">": "BASIC", "D": "Data BASICu", "P": "Pascal", ":": "Pascal (pokračování)",
    "%": "Assembler DAM-0000", "A": "Assembler DAM+2", "M": "Hudba (MUSICA)", "T": "Text (KASWORD/TEXTED)",
    "X": "Komprimovaný text (KASWORD)", "C": "Obrázek (GRED, komprimovaný)", "S": "Obrázek (GRED)",
    "W": "Výřez okna (GRED)", "G": "Sprajt (GREP)", "E": "Databáze (EVIDENCE)",
}


def _kontrola(W):
    platny = (W[:, 0] == 0) & (W[:, 9] == 1) & (W[:, 10] == 1)
    hod = (W[:, 1:9].astype(np.int32) << np.arange(8)).sum(axis=1)
    return platny, hod


def _cas(pos, i, rate) -> float:
    return float(pos[min(max(int(i), 0), len(pos) - 1)]) / rate


def _dalsi_start(bity: np.ndarray, od: int, nejvic: int) -> int | None:
    """Index dalšího start bitu (0) za klidem (samé 1), nejvýš `nejvic` bitů daleko."""
    kus = bity[od:od + nejvic]
    z = np.flatnonzero(kus == 0)
    return od + int(z[0]) if len(z) else None


def _ramec_na_konci(bity: np.ndarray, i: int) -> int | None:
    """Poslední bajt před pauzou mívá stop bity ztracené v tichu – stačí start bit a 8 datových bitů."""
    if i + 9 <= len(bity) < i + 11 and bity[i] == 0:
        return int((bity[i + 1:i + 9].astype(np.int32) << np.arange(8)).sum())
    return None


def _cti(platny, hod, k: int, n: int, bity: np.ndarray) -> list[int | None]:
    out: list[int | None] = []
    for j in range(n):
        i = k + 11 * j
        out.append(int(hod[i]) if i < len(platny) and platny[i] else _ramec_na_konci(bity, i))
    return out


def bloky_pmd(p: Pulzy, i0: int, i1: int) -> list[list[Blok]]:
    """Soubory PMD 85 v úseku: [hlavička, tělo, nestandardní bloky…]. Nevyjde-li čtení celé, zkusí se
    hrany jen jedné polarity s dopočtenými opačnými (pomalý náběh po pásce posouvá průchody nulou)."""
    soubory = _bloky_pmd(p, i0, i1)
    if soubory and all(b.ok for s in soubory for b in s):
        return soubory
    behy = np.diff(p.hrany[i0:i1 + 1])
    T = odhad_pulbitu(behy, PMD_T_US * p.rate / 1e6)
    if T is None:
        return soubory
    nejlepsi = soubory
    for uroven in (1, -1):
        q = hrany_z_jedne_polarity(p, i0, i1, T, uroven)
        if len(q.hrany) < 100:
            continue
        s2 = _bloky_pmd(q, 0, len(q.hrany) - 1)
        if _kvalita(s2) > _kvalita(nejlepsi):
            nejlepsi = s2
    return nejlepsi


def _kvalita(soubory: list[list[Blok]]) -> tuple[int, int]:
    return sum(b.ok for s in soubory for b in s), sum(len(s) for s in soubory)


def _bloky_pmd(p: Pulzy, i0: int, i1: int) -> list[list[Blok]]:
    behy = np.diff(p.hrany[i0:i1 + 1])
    T = odhad_pulbitu(behy, PMD_T_US * p.rate / 1e6)
    if T is None:
        return []
    soubory: list[list[Blok]] = []
    for hb, hp in pulbity(p, i0, i1, T):
        b0, pos, _ = manchester(hb, hp)
        for bity in (b0, 1 - b0):      # v jednolitém úvodu nejde fáze poznat – zkusí se obě polarity
            soubory += _soubory_z_bitu(bity, pos, p.rate)
    rychlost = PMD_T_US / (T / p.rate * 1e6)
    for s in soubory:
        for b in s:
            b.info_rychlost = rychlost  # type: ignore[attr-defined]
    return soubory


def _soubory_z_bitu(bity: np.ndarray, pos: np.ndarray, rate: int) -> list[list[Blok]]:
    platny, hod = ramce(bity, 11, _kontrola)
    N = len(platny)
    if N < 63 * 11:
        return []
    vzor = np.frombuffer(UVOD, np.uint8)
    out: list[list[Blok]] = []
    k_min = 0
    for k in np.flatnonzero(platny[:N - 63 * 11] & (hod[:N - 63 * 11] == 0xFF)):
        if k < k_min:
            continue
        idx = k + 11 * np.arange(48)
        if not (platny[idx].all() and (hod[idx] == vzor).all()):
            continue
        h = _cti(platny, hod, int(k), 63, bity)
        hdata = bytes(0 if v is None else v for v in h)
        h_ok = None not in h and (sum(hdata[48:62]) & 0xFF) == hdata[62]
        konec = k + 63 * 11
        hl = Blok(_cas(pos, k, rate), _cas(pos, konec, rate), "hlavička", hdata[48], hdata, h_ok,
                  chybne_bajty=[] if h_ok else [i for i, v in enumerate(h) if v is None] or list(range(48, 63)))
        soubor = [hl]
        if h_ok:
            delka = hdata[52] | hdata[53] << 8
            s = _dalsi_start(bity, konec, 20000)
            if s is not None:
                d = _cti(platny, hod, s, delka + 2, bity)
                ddata = bytes(0 if v is None else v for v in d)
                d_ok = None not in d and (sum(ddata[:-1]) & 0xFF) == ddata[-1]
                konec = s + (delka + 2) * 11
                soubor.append(Blok(_cas(pos, s, rate), _cas(pos, konec, rate), "data", hdata[48], ddata, d_ok,
                                   chybne_bajty=[] if d_ok else ([i for i, v in enumerate(d) if v is None]
                                                                 or list(range(len(d))))))
                konec = _nestandardni(bity, platny, hod, pos, rate, konec, soubor)
        out.append(soubor)
        k_min = konec
    return out


def _nestandardni(bity, platny, hod, pos, rate, od: int, soubor: list[Blok]) -> int:
    """Za tělem čte další rámce, dokud jsou platné (dohrávané části bez kontroly) – jako pmd2ptp."""
    data: list[int] = []
    s = _dalsi_start(bity, od, 2000)
    zac = s
    k = s
    while k is not None:
        if k < len(platny) and platny[k]:
            data.append(int(hod[k]))
        else:
            posledni = _ramec_na_konci(bity, k)
            if posledni is not None:
                data.append(posledni)
                k += 11
            break
        if len(data) >= 32 and bytes(data[-32:]) == UVOD[:32]:    # začíná další soubor
            data = data[:-32]
            k -= 31 * 11
            break
        k = _dalsi_start(bity, k + 11, 2000)
    if len(data) > 2 and zac is not None:
        konec = k if k is not None else zac + 11 * len(data)
        soubor.append(Blok(_cas(pos, zac, rate), _cas(pos, konec, rate), "nestandardní", None, bytes(data), True))
        return konec
    return od


class PMD85(Platforma):
    id = "pmd85"
    pocitac = "PMD 85"
    varianta = ""
    barva = "#C9A227"
    pripona = "ptp"
    poradi = 30

    def skore(self, usek: Usek, rate: int) -> float:
        return manchester_skore(usek.histogram, PMD_T_US)

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        nalezeno: list[list[Blok]] = []
        for u in useky:
            nalezeno += bloky_pmd(ktx.pulzy, u.i0, u.i1)
        # obě polarity mohou najít totéž – ponechá se lepší čtení
        nalezeno.sort(key=lambda s: (s[0].zacatek, -sum(b.ok for b in s)))
        soubory: list[Soubor] = []
        for bl in nalezeno:
            if soubory and abs(soubory[-1].bloky[0].zacatek - bl[0].zacatek) < 0.05:
                continue
            s = Soubor(self.id, "", "", "", bloky=bl)
            self.dokonci(s)
            s.info["rychlost"] = round(float(getattr(bl[0], "info_rychlost", 1.0)), 3)
            soubory.append(s)
        return soubory

    def dokonci(self, s: Soubor) -> None:
        hl = s.bloky[0]
        h = hl.data
        typ = chr(h[49]) if 32 <= h[49] < 127 else f"{h[49]:02X}h"
        s.nazev_bloku = jmeno(h[54:62])
        s.nazev = s.nazev_bloku or "(bez jména)"
        s.typ_bloku = f"{typ} {TYPY_PMD[typ]}" if typ in TYPY_PMD else typ
        delka = h[52] | h[53] << 8
        telo = next((b for b in s.bloky if b.typ == "data"), None)
        s.chybi = [] if telo else [2]
        s.kompletni = hl.ok and telo is not None and len(telo.data) == delka + 2
        data = telo.data[:-1] if telo else b""
        s.info.update({"cislo_souboru": h[48], "adresa": h[50] | h[51] << 8, "delka_dat": delka + 1,
                       "bloku": len(s.bloky), "texty": texty(data)})
        nest = [b for b in s.bloky if b.typ == "nestandardní"]
        if nest:
            s.info["poznamka"] = f"{len(nest)} nestandardní blok(y) bez kontroly, celkem {sum(len(b.data) for b in nest)} B"
            s.overeno = False
        s._data = data  # type: ignore[attr-defined]

    def sluc_kopie(self, soubory: list[tuple[int, Soubor]]) -> None:
        for _, f in soubory:
            if f.platforma != self.id or f.ok:
                continue
            for _, g in soubory:
                if g is f or g.platforma != self.id or g.nazev_bloku != f.nazev_bloku or not g.ok:
                    continue
                if g.bloky[0].data != f.bloky[0].data and f.bloky[0].ok:
                    continue
                f.bloky = [Blok(fb.zacatek, fb.konec, gb.typ, gb.cislo, gb.data, gb.ok,
                                oprava="" if fb.ok and fb.data == gb.data else
                                f"převzato z kopie ({gb.zacatek:.2f} s)") for fb, gb in zip(f.bloky, g.bloky)] \
                    + g.bloky[len(f.bloky):]
                self.dokonci(f)
                break

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = [pripona(cil, ".ptp")]
        ptp.zapis(out[0], [b.data for b in s.bloky])
        if getattr(s, "_data", None) is None:
            self.dokonci(s)
        out.append(pripona(cil, ".bin"))
        out[-1].write_bytes(s._data)  # type: ignore[attr-defined]
        return out

    RATE = 44100

    def runy(self, s: Soubor) -> tuple[list[int], int]:
        """Čistý signál (jako export_to_wav v pmd2ptp / MAME): úvod 3600 bitů 1, bloky, pauzy 600 bitů 1."""
        T = PMD_T_US * self.RATE / 1e6
        bity = [1] * 3600
        for i, b in enumerate(s.bloky):
            if i:
                bity += [1] * (1200 if b.typ == "data" else 600)
            for x in b.data:
                bity += [0] + [(x >> q) & 1 for q in range(8)] + [1, 1]
        urovne: list = [("pauza", self.RATE // 2)]
        for bit in bity:
            urovne += [bit ^ 1, bit]        # 1 = nízká→vysoká (MAME)
        urovne.append(("pauza", self.RATE))
        return runy_z_pulbitu(urovne, T)


# =====================================================================  Maťo

MATO_PRAH_US = 26 / 22050 * 1e6          # matowav2ptp: --samples-thresh 26 při 22,05 kHz
PREFIX_PMD = bytes([0xFF] * 16 + [0x00] * 16 + [0x55] * 15)


def _shr8(v: int) -> int:
    return (v >> 1) & 0x7F


def bajty_mato(p: Pulzy, i0: int, i1: int, smer: int = -1) -> tuple[list[int], list[int]]:
    """Bajty a jejich vzorky: bit = perioda (0 krátká / 1 dlouhá), start bit 1, 8 bitů od LSB.

    matowav2ptp měří periody mezi sestupnými průchody nulou; při obrácené polaritě nahrávky (smer=+1)
    mezi vzestupnými."""
    per, zac = periody(p, i0, i1, smer)
    m = per < 2 * MATO_PRAH_US
    bity = (per[m] > MATO_PRAH_US).astype(np.int8)
    poz = zac[m]
    out, kde = [], []
    b = bity.tolist()
    i = 0
    n = len(b)
    while i + 9 <= n:
        if b[i] != 1:
            i += 1
            continue
        kde.append(int(poz[i]))
        i += 1
        out.append(sum(b[i + q] << q for q in range(8)))
        i += 8
    return out, kde


class Mato(Platforma):
    id = "mato"
    pocitac = "Maťo"
    varianta = ""
    barva = "#B88A1E"
    pripona = "ptp"
    poradi = 31

    def skore(self, usek: Usek, rate: int) -> float:
        return 0.6 if podil_v_pasmu(usek.histogram, 330, 1500) > 0.8 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        soubory: list[Soubor] = []
        for u in useky:
            for smer in (-1, 1):
                d, kde = bajty_mato(ktx.pulzy, u.i0, u.i1, smer)
                nalez = self._soubory(d, kde, ktx.pulzy.rate)
                if nalez:
                    soubory += nalez
                    break
        return soubory

    def _soubory(self, data: list[int], kde: list[int], rate: int) -> list[Soubor]:
        """Hledání hlaviček a těl – process_bytes z matowav2ptp."""
        out = []
        i = 0
        n = len(data)
        while i < n - 5:
            if not (data[i] == 0x55 and data[i + 2] == 0x3E and data[i + 3] == 0x01 and data[i + 4] == 0x24):
                i += 1
                continue
            if i + 15 >= n:
                break
            if sum(data[i + 1:i + 15]) % 256 != data[i + 15]:
                i += 1
                continue
            delka = data[i + 5] | data[i + 6] << 8
            zac = i + 16
            konec = zac + delka + 1
            if konec >= n:
                break
            hl = Blok(kde[i] / rate, kde[zac] / rate, "hlavička", data[i + 1], bytes(data[i:i + 16]), True)
            blok = bytearray(data[zac:zac + delka + 2])
            blok[0] = _shr8(blok[0])
            ok = sum(blok[:-1]) % 256 == blok[-1]
            telo = Blok(kde[zac] / rate, kde[min(konec, n - 1)] / rate, "data", data[i + 1], bytes(blok), ok,
                        chybne_bajty=[] if ok else list(range(len(blok))))
            s = Soubor(self.id, "", "", "", bloky=[hl, telo])
            self.dokonci(s)
            out.append(s)
            i = konec + 1
        return out

    def dokonci(self, s: Soubor) -> None:
        h = s.bloky[0].data
        s.nazev_bloku = jmeno(h[7:15])
        s.nazev = s.nazev_bloku or "(bez jména)"
        s.typ_bloku = "BASIC" if h[2] == 0x3E else chr(h[2])
        delka = h[5] | h[6] << 8
        telo = s.bloky[1] if len(s.bloky) > 1 else None
        s.chybi = [] if telo else [2]
        s.kompletni = telo is not None and len(telo.data) == delka + 2
        data = telo.data[:-1] if telo else b""
        s.info.update({"cislo_souboru": h[1], "adresa": h[3] | h[4] << 8, "delka_dat": delka + 1,
                       "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        """PTP jako matowav2ptp: hlavička PMD 85 (63 B) + tělo."""
        hl, telo = s.bloky[0].data, (s.bloky[1].data if len(s.bloky) > 1 else b"")
        out = [pripona(cil, ".ptp"), pripona(cil, ".bin")]
        ptp.zapis(out[0], [PREFIX_PMD + hl, telo])
        out[1].write_bytes(telo[:-1])
        return out
