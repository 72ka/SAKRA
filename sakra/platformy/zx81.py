"""Sinclair ZX81 – standardní záznam ROM a domácí turbo FASTSAVER (podle zx81fastwav2p, J. Heřman).

ROM: bit = dávka pulzů (150 µs + 150 µs) a ticho 1300 µs; 4 pulzy = 0, 9 pulzů = 1. Bajty od MSB bez rámců.
  Soubor: jméno (poslední znak má bit 7), pak data od adresy 4009h do E_LINE (systémová proměnná 4014h).
FASTSAVER: bit = perioda (mezi vzestupnými průchody nulou) ~250 µs = 0, ~500 µs = 1; úvod aspoň 50 krátkých,
  dlouhý start bit, pak bity od MSB. Data jsou rovnou obsah souboru .P.
Výstup: .P (data od 4009h). Úplnost se ověří délkou podle E_LINE (záznam nemá kontrolní součet).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import bajty_msb, behy_us, periody
from .zaklad import Kontext, Platforma, pripona, podil_v_pasmu

ZNAKY = {0x00: " ", 0x0B: '"', 0x0C: "£", 0x0D: "$", 0x0E: ":", 0x0F: "?", 0x10: "(", 0x11: ")", 0x12: ">",
         0x13: "<", 0x14: "=", 0x15: "+", 0x16: "-", 0x17: "*", 0x18: "/", 0x19: ";", 0x1A: ",", 0x1B: "."}
ZNAKY.update({0x1C + i: str(i) for i in range(10)})
ZNAKY.update({0x26 + i: chr(65 + i) for i in range(26)})

# FASTSAVER: meze z zx81fastwav2p (vzorky při 44,1 kHz) převedené na µs
S1 = 1e6 / 4000
F_L1 = (44100 / 4000 - 3) / 44100 * 1e6       # 182 µs
F_RES = 1.5 * 44100 / 4000 / 44100 * 1e6        # 375 µs
F_H2 = (2 * 44100 / 4000 + 4) / 44100 * 1e6     # 591 µs


def text_zx81(data: bytes) -> str:
    return "".join(ZNAKY.get(b & 0x7F, "?") for b in data)


def _delka_p(data: bytes) -> int | None:
    """Očekávaná délka .P podle E_LINE (4014h, tj. posun 0Bh od 4009h)."""
    if len(data) < 0x0D:
        return None
    e_line = data[0x0B] | data[0x0C] << 8
    n = e_line - 0x4009
    return n if 0x74 < n <= 0xBFF7 else None


def _texty(data: bytes) -> list[str]:
    out = []
    for kus in text_zx81(data).split("?"):
        kus = kus.strip()
        if len(kus) >= 5 and sum(c.isalpha() for c in kus) >= 3 and kus not in out:
            out.append(kus)
    return out[:30]


def rom_bity(r: np.ndarray) -> tuple[list[int], list[int], int]:
    """Dávky krátkých běhů oddělené tichem -> bity. Vrací (bity, index běhu začátku bitu, nejasných dávek)."""
    kratke = r < 450
    bity, kde, nejasne = [], [], 0
    i = 0
    n = len(r)
    while i < n:
        if not kratke[i]:
            i += 1
            continue
        j = i
        while j < n and kratke[j]:
            j += 1
        pulzu = (j - i + 1) // 2
        if pulzu >= 2:
            if not (3 <= pulzu <= 5 or 8 <= pulzu <= 10):
                nejasne += 1
            bity.append(1 if pulzu >= 7 else 0)
            kde.append(i)
        i = j
    return bity, kde, nejasne


def fast_bity(per: np.ndarray, pul: np.ndarray | None = None):
    """FASTSAVER: úvod ≥ 50 krátkých, dlouhý start bit, pak bity. Vrací (bity, index periody, nejisté indexy).

    Poslední bit před tichem nemá koncovou hranu periody – určí se z jeho první půlvlny (`pul[k]`)."""
    kratke = (per > F_L1) & (per < F_RES)
    for i in range(50, len(per)):
        if per[i] >= F_RES and kratke[i - 50:i].all():
            zac = i + 1
            break
    else:
        return [], [], []
    bity, kde, nejiste = [], [], []
    spatnych = 0
    pred_chybou = 0                     # délka proudu před poslední řadou chybných period
    for k in range(zac, len(per)):
        d = per[k]
        if F_L1 < d < F_H2:
            bity.append(0 if d < F_RES else 1)
            spatnych = 0
        else:
            if spatnych == 0:
                pred_chybou = len(bity)
            spatnych += 1
            if spatnych >= 8 or d > 4 * F_H2:          # konec záznamu
                break
            bity.append(0 if d <= F_RES else 1)
            nejiste.append(len(bity) - 1)
        kde.append(k)
    if spatnych:                        # chybné periody na konci = už ticho nebo šum, ne data
        del bity[pred_chybou:], kde[pred_chybou:]
        nejiste = [x for x in nejiste if x < pred_chybou]
    konec = kde[-1] + 1 if kde else zac
    if len(bity) % 8 == 7 and pul is not None and konec < len(pul) and F_L1 < 2 * pul[konec] < F_H2:
        bity.append(0 if 2 * pul[konec] < F_RES else 1)
        kde.append(konec)
    n = len(bity) // 8 * 8
    return bity[:n], kde[:n], [x for x in nejiste if x < n]


class ZX81(Platforma):
    id = "zx81"
    pocitac = "ZX81"
    varianta = ""
    barva = "#9C5BD1"
    pripona = "p"
    poradi = 25

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram
        rom = podil_v_pasmu(h, 90, 260) > 0.6 and podil_v_pasmu(h, 1000, 2500) > 0.03
        fast = podil_v_pasmu(h, 80, 330) > 0.85
        return 0.8 if rom or fast else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        p = ktx.pulzy
        out = []
        for u in useky:
            r = behy_us(p, u.i0, u.i1)
            bity, kde, nejasne = rom_bity(r)
            if len(bity) >= 8 * 0x80:
                s = self._rom(bity, kde, nejasne, p, u)
                if s:
                    out.append(s)
                    continue
            for smer in (1, -1):          # zx81fastwav2p měří od vzestupných průchodů nulou
                per, zac = periody(p, u.i0, u.i1, smer)
                hr = np.flatnonzero(p.urovne[u.i0:u.i1 + 1] == smer) + u.i0
                hr = hr[hr < u.i1]
                pul = (p.hrany[hr + 1] - p.hrany[hr]) * 1e6 / p.rate
                bity, kde, nejiste = fast_bity(per, pul)
                s = self._fast(bity, kde, nejiste, zac, p.rate) if len(bity) >= 8 * 0x80 else None
                if s and s.bloky[0].ok:
                    out.append(s)
                    break
        return out

    def _rom(self, bity, kde, nejasne, p, u) -> Soubor | None:
        b = bajty_msb(np.array(bity, np.uint8))
        konec_jmena = next((i for i, x in enumerate(b[:127]) if x & 0x80), None)
        if konec_jmena is None:
            return None
        jm, data = b[:konec_jmena + 1], b[konec_jmena + 1:]
        n = _delka_p(data)
        ok = n is not None and len(data) >= n and not nejasne
        if n is None:
            return None
        t0 = p.cas(u.i0 + kde[0])
        t1 = p.cas(u.i0 + kde[min(len(kde) - 1, 8 * (konec_jmena + 1 + n))])
        blok = Blok(t0, t1, "data", None, bytes(jm + data[:n]), ok)
        s = Soubor(self.id, "", text_zx81(jm), "Program", bloky=[blok], overeno=False)
        s.info.update({"delka_jmena": len(jm), "nejasnych_davek": nejasne})
        self.dokonci(s)
        return s

    def _fast(self, bity, kde, nejiste, zac, rate) -> Soubor | None:
        data = bajty_msb(np.array(bity, np.uint8))
        n = _delka_p(data)
        if n is None:
            return None
        ok = len(data) >= n and not [x for x in nejiste if x < 8 * n]
        t0 = float(zac[max(0, kde[0] - 52)]) / rate
        t1 = float(zac[kde[min(len(kde) - 1, 8 * n)]]) / rate
        blok = Blok(t0, t1, "data", None, data[:n], ok,
                    chybne_bajty=sorted({x // 8 for x in nejiste if x < 8 * n}))
        s = Soubor(self.id, "", "", "Program", bloky=[blok], overeno=False)
        s.info.update({"turbo": "FASTSAVER", "nejistych_bitu": len(nejiste)})
        self.dokonci(s)
        return s

    def dokonci(self, s: Soubor) -> None:
        b = s.bloky[0]
        dj = s.info.get("delka_jmena", 0)
        data = b.data[dj:]
        n = _delka_p(data)
        s.kompletni = n is not None and len(data) >= n
        s.chybi = []
        txt = _texty(data)
        s.nazev = s.nazev_bloku or (txt[0][:24] if txt else "(bez jména)")
        s.info.update({"delka_dat": len(data), "texty": txt})
        s._data = data  # type: ignore[attr-defined]

    def turbo(self, s: Soubor) -> str:
        return s.info.get("turbo", "Není v Turbo")

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = pripona(cil, ".p")
        out.write_bytes(s.bloky[0].data[s.info.get("delka_jmena", 0):])
        return [out]
