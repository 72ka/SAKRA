"""Záznamy s úvodním tónem a pulzní šířkovou modulací (bit = dvojice stejných půlvln, 0 úzká, 1 široká, od MSB).

Tímto schématem zapisuje:
* turbozavaděče ZX Spectra (časování jiné než ROM, blok s příznakem a XOR součtem),
* Atari Turbo 2000 (OldComp wiki): úvod ≥ 256 širokých pulzů, úzký synchronizační pulz, hlavička 19 B
  (00h, typ 01/03/04/FFh, jméno 10, zaváděcí a spouštěcí adresa, délka, XOR), blok dat (FFh, data, XOR);
  „Kilobytové bloky“ = řada stejně dlouhých bloků dat bez hlaviček,
* Amstrad CPC (firmware): úvod 2048 bitů 1, bit 0, synchronizační bajt (2Ch hlavička, 16h data), segmenty po 256 B
  s CRC-16 (CCITT, 0xFFFF, negované, vyšší bajt první), na konci 32 bitů 1.
Časování se měří z nahrávky, výstupy ho zachovávají (TZX/CDT blok 11h, CAS bloky pwm*).
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from .. import __version__
from ..formaty import tzx
from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import bajty_msb, behy_us, dve_shluky, rady, xor
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, pripona, podil_v_pasmu
from .zx import BIT0 as ZX_BIT0, PILOT as ZX_PILOT, TYPY_HLAVICKY as ZX_TYPY
from .zx import dokonci_program, nahled_programu, snimky_programu, zapis_program

TAKT = 3.5      # taktů Z80 na µs (TZX)
T2K_TYPY = {0x01: "Data", 0x03: "Monolitický strojový program", 0x04: "Binární soubor", 0xFF: "BASIC (tokenizovaný)"}
CPC_TYPY = {0: "BASIC", 1: "BASIC (chráněný)", 2: "Binární", 3: "Binární (chráněný)", 0x16: "ASCII"}


def crc_cpc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc ^ 0xFFFF


def pwm_bloky(p, u: Usek) -> list[dict]:
    """Všechny bloky „úvodní tón + synchronizace + PWM data“ v úseku."""
    r = behy_us(p, u.i0, u.i1)
    if len(r) < 600:
        return []
    pomer = np.concatenate(([0.0], r[1:] / np.maximum(r[:-1], 1e-6)))
    m = (r > 120) & (r < 1500) & (pomer > 0.85) & (pomer < 1.18)
    out = []
    for a, b in rady(m, 400):
        P = float(np.median(r[a:b]))
        # synchronizace: 1–3 kratší půlvlny; data začínají tam, kde jsou dvojice nejvyrovnanější
        nejlepsi = None
        for o in (1, 2, 3):
            j = b + o
            d = r[j:j + 128]
            if len(d) < 32:
                continue
            x, y = d[0::2][:len(d) // 2], d[1::2][:len(d) // 2]
            vyrovnane = float(np.mean(np.abs(x - y) < 0.25 * np.maximum(x, y)))
            if nejlepsi is None or vyrovnane > nejlepsi[0] + 0.05:
                nejlepsi = (vyrovnane, j)
        if nejlepsi is None or nejlepsi[0] < 0.8:
            continue
        j = nejlepsi[1]
        n = (len(r) - j) // 2
        sumy = r[j:j + 2 * n:2] + r[j + 1:j + 2 * n:2]
        # odhad délek bitů jen z věrohodných dvojic (bez pauzy za blokem)
        vzorek = sumy[:4000]
        vzorek = vzorek[vzorek < 4 * float(np.median(vzorek[:200]))]
        nula, jedna = dve_shluky(vzorek)
        if jedna / max(nula, 1) < 1.4:
            continue
        # tón stejně dlouhý jako bit 0 nejde od dat odlišit – to není úvodní tón, ale třeba klidová úroveň
        # signálu FSK (Kansas City: 2400 Hz) a „data“ za ním by byla náhoda
        if abs(P / (nula / 2) - 1) < 0.15:
            continue
        platne = (sumy > 0.55 * nula) & (sumy < 1.45 * jedna)
        k = int(np.argmin(platne)) if not platne.all() else len(sumy)
        bity = (sumy[:k] > (nula + jedna) / 2).astype(np.uint8)
        data = bajty_msb(bity)
        # krátké útržky a bloky s neobvyklým příznakem by byly častěji náhoda než data
        if len(data) < 4 or (data[0] not in (0x00, 0xFF, 0x2C, 0x16) and len(data) < 64):
            continue
        out.append({"t0": p.cas(u.i0 + a), "t1": p.cas(u.i0 + min(j + 2 * k, len(r))), "data": data,
                    "pilot": P, "pilot_pocet": b - a, "sync": [float(x) for x in r[b:j]],
                    "nula": nula / 2, "jedna": jedna / 2})
    return out


def _je_rom_zx(b: dict) -> bool:
    return abs(b["pilot"] / ZX_PILOT - 1) < 0.15 and abs(b["nula"] / ZX_BIT0 - 1) < 0.18


def _cpc_rozbor(data: bytes):
    """Vrací (typ záznamu, užitečná data, segmenty v pořádku, počet segmentů) nebo None."""
    if not data or data[0] not in (0x2C, 0x16):
        return None
    seg_ok, obsah = [], b""
    i = 1
    while i + 258 <= len(data):
        seg = data[i:i + 256]
        crc = data[i + 256] << 8 | data[i + 257]
        if crc_cpc(seg) != crc:
            if not seg_ok:
                return None
            seg_ok.append(False)
        else:
            seg_ok.append(True)
        obsah += seg
        i += 258
        if data[0] == 0x2C:
            break
    if not seg_ok:
        return None
    return ("hlavička" if data[0] == 0x2C else "data"), obsah, seg_ok


class Turbo(Platforma):
    """ZX Spectrum s turbozavaděčem; dekóduje i Atari Turbo 2000 a Amstrad CPC (stejné schéma záznamu)."""
    id = "zx-turbo"
    pocitac = "ZX Spectrum"
    varianta = ""
    barva = "#F08A5D"
    pripona = "tzx"
    poradi = 21

    def skore(self, usek: Usek, rate: int) -> float:
        return 0.6 if podil_v_pasmu(usek.histogram, 60, 1500) > 0.8 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky = []
        for u in useky:
            bloky += [b for b in pwm_bloky(ktx.pulzy, u) if not _je_rom_zx(b)]
        bloky.sort(key=lambda b: b["t0"])
        cpc = [b for b in bloky if _cpc_rozbor(b["data"])]
        ostatni = [b for b in bloky if b not in cpc]
        return _cpc_soubory(cpc) + _xor_soubory(ostatni)

    def turbo(self, s: Soubor) -> str:
        return "Turbo"

    def dokonci(self, s: Soubor) -> None:
        dokonci_program(s)

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        return zapis_program(s, cil)

    def nahled(self, s: Soubor) -> dict:
        return nahled_programu(s)

    def snimky(self, s: Soubor) -> dict:
        return snimky_programu(s)


def _casovani(s: Soubor, i: int) -> dict:
    c = s.info.get("casovani", [])
    c = c[i] if i < len(c) else (c[-1] if c else {})
    sync = c.get("sync") or [c.get("nula", 244)] * 2
    return {"pilot": c.get("pilot", 619) * TAKT, "pilot_pocet": c.get("pilot_pocet", 3223),
            "sync1": sync[0] * TAKT, "sync2": (sync[1] if len(sync) > 1 else sync[0]) * TAKT,
            "nula": c.get("nula", 244) * TAKT, "jedna": c.get("jedna", 489) * TAKT, "pauza_ms": 1000}


def _blok_xor(b: dict) -> Blok:
    d = b["data"]
    ok = xor(d) == 0
    typ = "hlavička" if d[0] == 0 and len(d) == 19 else "data"
    return Blok(b["t0"], b["t1"], typ, None, d, ok, chybne_bajty=[] if ok else list(range(len(d))))


def _xor_soubory(bloky: list[dict]) -> list[Soubor]:
    # rozhodnutí ZX × Atari Turbo 2000 podle typů v hlavičkách na této straně
    hl = [b["data"] for b in bloky if b["data"][0] == 0 and len(b["data"]) == 19 and xor(b["data"]) == 0]
    atari = sum(h[1] in (0x04, 0xFF) for h in hl)
    zx = sum(h[1] in (0x00, 0x02) for h in hl)
    platforma = AtariT2K.id if atari > zx else Turbo.id
    soubory: list[Soubor] = []
    akt: Soubor | None = None
    for b in bloky:
        blok = _blok_xor(b)
        cas = {k: b[k] for k in ("pilot", "pilot_pocet", "sync", "nula", "jedna")}
        if blok.typ == "hlavička" and blok.ok:
            akt = Soubor(platforma, "", "", "")
            soubory.append(akt)
        elif akt is None or len(akt.bloky) != 1 or akt.bloky[0].typ != "hlavička" or blok.zacatek - akt.konec > 15:
            akt = Soubor(platforma, "", "", "Bez hlavičky")
            soubory.append(akt)
        akt.bloky.append(blok)
        akt.info.setdefault("casovani", []).append(cas)
    # Atari: řada bloků bez hlavičky stejné délky = Turbo 2000 – kilobytové bloky
    if platforma == AtariT2K.id:
        spojene: list[Soubor] = []
        for s in soubory:
            if spojene and s.typ_bloku == "Bez hlavičky" and spojene[-1].typ_bloku in ("Bez hlavičky", "Kb bloky") \
                    and s.zacatek - spojene[-1].konec < 15:
                spojene[-1].bloky += s.bloky
                spojene[-1].info["casovani"] += s.info["casovani"]
                spojene[-1].typ_bloku = "Kb bloky"
            else:
                spojene.append(s)
        soubory = spojene
    for s in soubory:
        _dokonci_xor(s)
    return soubory


def _dokonci_xor(s: Soubor) -> None:
    hl = s.bloky[0] if s.bloky and s.bloky[0].typ == "hlavička" and s.bloky[0].ok else None
    dat = [b for b in s.bloky if b.typ == "data"]
    data = b"".join(b.data[1:-1] for b in dat)
    atari = s.platforma == AtariT2K.id
    if hl:
        h = hl.data
        s.nazev_bloku = jmeno(h[2:12])
        s.nazev = s.nazev_bloku or "(bez jména)"
        a1, a2, delka = struct.unpack_from("<HHH", h, 12)
        if atari:
            s.typ_bloku = T2K_TYPY.get(h[1], f"{h[1]:02X}h")
            s.info.update({"adresa": a1, "spusteni": a2, "delka": delka, "turbo": "T2K"})
        else:
            s.typ_bloku = ZX_TYPY.get(h[1], str(h[1]))
            s.info["delka"] = a1
            if h[1] == 3:
                s.info["adresa"] = a2
            elif h[1] == 0 and a2 < 32768:
                s.info["autostart"] = a2
        ocek = s.info["delka"]
        s.kompletni = len(dat) == 1 and dat[0].ok and len(dat[0].data) - 2 == ocek
        s.chybi = [] if dat else [2]
    else:
        s.nazev = s.nazev or f"(bez hlavičky, {len(data)} B)"
        s.kompletni = bool(dat) and all(b.ok for b in dat)
        s.chybi = []
        if atari:
            s.info["turbo"] = "T2K - Kb bloky" if s.typ_bloku == "Kb bloky" else "T2K - Nestandardní"
    c = s.info.get("casovani") or [{}]
    s.info.update({"delka_dat": len(data), "bloku": len(s.bloky), "texty": texty(data),
                   "rychlost_bd": round(2e6 / (c[-1].get("nula", 1) + c[-1].get("jedna", 1))) if c[-1] else None})
    s._data = data  # type: ignore[attr-defined]


class AtariT2K(Platforma):
    id = "atari-t2k"
    pocitac = "Atari 8bit"
    varianta = ""
    barva = "#B8467A"
    pripona = "cas"
    poradi = 49

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        return []        # dekóduje Turbo (stejné schéma záznamu)

    def turbo(self, s: Soubor) -> str:
        return s.info.get("turbo", "T2K - Nestandardní")

    def dokonci(self, s: Soubor) -> None:
        _dokonci_xor(s)

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = [pripona(cil, ".cas")]
        out[0].write_bytes(cas_pwm(s))
        if not hasattr(s, "_data"):
            _dokonci_xor(s)
        out.append(pripona(cil, ".bin"))
        out[-1].write_bytes(s._data)  # type: ignore[attr-defined]
        return out


def _chunk(typ: bytes, aux: int, data: bytes = b"") -> bytes:
    return typ + struct.pack("<HH", len(data), aux & 0xFFFF) + data


def cas_pwm(s: Soubor, rate: int = 44100) -> bytes:
    """CAS (a8cas) s turbo bloky: pwms (MSB první, vzorkování), pwmc (úvod a synchronizace), pwmd (data)."""
    vz = lambda us: max(1, min(255, int(round(us * rate / 1e6))))  # noqa: E731
    out = _chunk(b"FUJI", 0, f"SAKRA {__version__}: {s.nazev} (Turbo 2000)".encode("utf-8"))
    out += _chunk(b"pwms", 0b101, struct.pack("<H", rate))
    for i, b in enumerate(s.bloky):
        c = _casovani(s, i)
        pilot = vz(c["pilot"] / TAKT)
        sync = vz(c["sync1"] / TAKT)
        out += _chunk(b"pwmc", 1000 if i else 2000, struct.pack("<BH", pilot, int(c["pilot_pocet"] // 2))
                      + struct.pack("<BH", sync, 1))
        out += b"pwmd" + struct.pack("<HBB", len(b.data), vz(c["nula"] / TAKT), vz(c["jedna"] / TAKT)) + b.data
    return out


# =====================================================================  Amstrad CPC

def _cpc_soubory(bloky: list[dict]) -> list[Soubor]:
    soubory: list[Soubor] = []
    akt: Soubor | None = None
    for b in bloky:
        typ, obsah, seg_ok = _cpc_rozbor(b["data"])
        ok = all(seg_ok)
        # synchronizační bajt + segmenty s CRC; závěrečný tón (32 bitů 1) do dat nepatří
        blok = Blok(b["t0"], b["t1"], typ, None, b["data"][:1 + 258 * len(seg_ok)], ok,
                    chybne_bajty=[] if ok else [i for i, x in enumerate(seg_ok) if not x])
        if typ == "hlavička":
            jm = jmeno(obsah[:16])
            blok.cislo = obsah[16]
            if akt is None or jm != akt.nazev_bloku or obsah[23] or b["t0"] - akt.konec > 30:
                akt = Soubor(CPC.id, "", jm, "")
                soubory.append(akt)
        elif akt is None:
            akt = Soubor(CPC.id, "", "", "Bez hlavičky")
            soubory.append(akt)
        akt.bloky.append(blok)
        akt.info.setdefault("casovani", []).append({k: b[k] for k in ("pilot", "pilot_pocet", "sync", "nula", "jedna")})
    for s in soubory:
        CPC().dokonci(s)
    return soubory


class CPC(Platforma):
    id = "cpc"
    pocitac = "Amstrad CPC"
    varianta = ""
    barva = "#2E9C9C"
    pripona = "cdt"
    poradi = 50

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        return []        # dekóduje Turbo (stejné schéma záznamu)

    def dokonci(self, s: Soubor) -> None:
        hlavicky = [_cpc_rozbor(b.data)[1] for b in s.bloky if b.typ == "hlavička" and b.ok]
        data = b""
        prvni = hlavicky[0] if hlavicky else None
        posledni = any(h[17] for h in hlavicky)
        for i, b in enumerate(s.bloky):
            if b.typ != "data":
                continue
            h = s.bloky[i - 1] if i and s.bloky[i - 1].typ == "hlavička" else None
            obsah = _cpc_rozbor(b.data)[1]
            delka = len(obsah)
            if h is not None and h.ok:
                hh = _cpc_rozbor(h.data)[1]
                delka = hh[19] | hh[20] << 8
            data += obsah[:delka]
        if prvni is not None:
            s.typ_bloku = CPC_TYPY.get(prvni[18], f"{prvni[18]:02X}h")
            logicka = prvni[24] | prvni[25] << 8
            s.info.update({"adresa": prvni[21] | prvni[22] << 8, "spusteni": prvni[26] | prvni[27] << 8,
                           "delka": logicka})
            data = data[:logicka] if logicka else data
        cisla = sorted(h[16] for h in hlavicky)
        s.chybi = [n for n in range(1, (max(cisla) if cisla else 0) + 1) if n not in cisla]
        s.kompletni = bool(prvni) and posledni and not s.chybi and \
            len([b for b in s.bloky if b.typ == "data"]) == len(hlavicky)
        s.nazev = s.nazev_bloku or "(bez jména)"
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky), "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = [pripona(cil, ".cdt")]
        tzx.zapis_tzx_turbo(out[0], [(b.data + b"\xff" * 4, _casovani(s, i)) for i, b in enumerate(s.bloky)],
                            popis=f"SAKRA: {s.nazev}")
        if not hasattr(s, "_data"):
            self.dokonci(s)
        out.append(pripona(cil, ".bin"))
        out[-1].write_bytes(s._data)  # type: ignore[attr-defined]
        return out
