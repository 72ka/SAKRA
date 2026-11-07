"""Záznam Sord m5, CAS (SORDM5) + BIN.

Bit 1 = perioda 3150 Hz, bit 0 = perioda 1575 Hz (proměnná délka bitu).
Bajt: start 0, 8 bitů LSB, stop 1. Před každým blokem nosná 3150 Hz.
Blok: typ H/D/E/F, délka (00h = 256), data, součet dat modulo 256.
H má 31 B: typ souboru, jméno 9 B, adresa/délka/start (3× LE16), 15 B.
CAS: značka SORDM5 + 10 nul, pak původní bloky včetně součtů.

Popis formátu: MAME src/lib/formats/sord_cas.cpp a z88dk src/appmake/m5.c.
E/F (nesouvislá data) se zachovají v CAS; BIN a úplnost se určují jen pro H/D.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Nosna, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import behy_us, rady
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, podil_v_pasmu, pripona

CAS_HLAVICKA = b"SORDM5" + bytes(10)
PUL_1 = 1e6 / 3150 / 2
# Monitor Handling Manual 6-5: perioda log. 1 = d1 + STDLY × 8,929 µs.
STDLY_D1_US = 35.36
STDLY_KROK_US = 8.929


def bloky_sord(p, u: Usek) -> list[Blok]:
    """Čte jednotlivé bloky za nosnou; chybný rámec nezmění zarovnání dalších bajtů."""
    r = behy_us(p, u.i0, u.i1)
    # Rychlost odvozujeme z dlouhé nosné, nikoli z mediánu datových půlvln.
    # U rychlejšího záznamu by se do pevného pásma dostala i část dlouhých
    # pulzů a konec nosné by se posunul doprostřed start bitu.
    nejdelsi = (0, 0)
    for t in np.arange(0.5 * PUL_1, 1.5 * PUL_1, 10.0):
        for a, b in rady((r > 0.75 * t) & (r < 1.25 * t), 120):
            if b - a > nejdelsi[1] - nejdelsi[0]:
                nejdelsi = (a, b)
    a, b = nejdelsi
    if b == a:
        return []
    # Průměr dlouhé nosné zachová zlomky vzorku (např. 2,4 vzorku/půlvlnu
    # při 22,05 kHz); medián by časování zaokrouhlil na 2 nebo 3 vzorky.
    s = float(np.mean(r[a:b]))
    # Při nízkém vzorkování může zaokrouhlení prodloužit půlvlnu o vzorek.
    horni = max(1.4 * s, s + 1e6 / p.rate)
    nosne = rady((r > 0.65 * s) & (r < horni), 120)
    out = []
    for a, b in nosne:
        s = float(np.mean(r[a:b]))
        # Nosná končí prvním dlouhým start bitem. Dvojice půlvln se čtou od něj,
        # bez závislosti na polaritě nebo lichém počtu půlvln úvodního tónu.
        data = bytearray()
        chyby = []
        hranice_bitu = []
        i, n = b, None
        konec = p.cas(u.i0 + b)
        while i + 18 <= len(r):
            pulzy = r[i:i + 20]
            # Poslední stop bit může přejít do ticha (nebo mít delší druhou půlvlnu).
            # Pro něj stačí první půlvlna; obsah i součet mají vždy celé periody.
            if len(pulzy) < 19:
                break
            periody = pulzy[:18].reshape(9, 2)
            bity = (periody.mean(axis=1) < 1.5 * s).astype(np.uint8)
            platne = ((periody > 0.55 * s) & (periody < 2.7 * s)).all()
            # Průchod nulou se u zkreslené nahrávky posouvá: půlvlny nemusí
            # být stejně dlouhé, i když jejich součet stále přesně určuje bit.
            soumerne = (np.abs(periody[:, 0] - periody[:, 1]) < 1.1 * s).all()
            ok = platne and soumerne and bity[0] == 0 and 0.55 * s < pulzy[18] < 1.5 * s
            v = sum(int(bit) << q for q, bit in enumerate(bity[1:]))
            data.append(v)
            if not ok:
                chyby.append(len(data) - 1)
            konec = p.cas(u.i0 + min(i + 20, len(r)))
            if len(pulzy) < 20 or pulzy[19] > 1.5 * s:
                # Stop bit přecházející do ticha nemá koncovou hranu.
                # Jeho konec odhadneme z nosné, nikoli až z dalšího signálu.
                konec = p.cas(u.i0 + i + 18) + 2 * s / 1e6
            hranice_bitu.append([p.cas(u.i0 + i + 2 * q) for q in range(10)] + [konec])
            i += 20
            if len(data) == 1 and v not in b"HDEF":
                break
            if len(data) == 2:
                n = (v or 256) + 3
                if data[0] == ord("H") and v != 31:
                    break
            if n is not None and len(data) == n:
                break
            # Delší nosná či mezera uvnitř očekávaného bloku znamená useknutí.
            if i + 20 <= len(r) and (np.all(r[i:i + 20] < 1.5 * s) or r[i] > 3 * s):
                break
        if n is None or data[0] not in b"HDEF" or (data[0] == ord("H") and data[1] != 31):
            continue
        ok = len(data) == n and not chyby and sum(data[2:-1]) & 255 == data[-1]
        # Blok začíná první log. 0 po IBG a končí za stop bitem součtu.
        # Jedničky na konci součtu mohou splývat s následující nosnou.
        nosna_zacatek = max(p.cas(u.i0 + a), out[-1].konec if out else 0.0)
        out.append(Blok(p.cas(u.i0 + b), konec,
                        chr(data[0]), None, bytes(data), bool(ok), chybne_bajty=chyby,
                        nosna_zacatek=nosna_zacatek, hranice_bitu=hranice_bitu))
    return out


class SordM5(Platforma):
    id = "sord-m5"
    pocitac = "Sord m5"
    barva = "#C85B60"
    pripona = "cas"
    poradi = 43

    def skore(self, usek: Usek, rate: int) -> float:
        # Zákmity kratší než polovina krátké půlvlny nejsou bity Sordu.
        # V zašuměných mezerách mohou početně převážit nad skutečnými daty.
        h = usek.histogram.copy()
        h[:8] = 0  # histogram má krok 10 µs; krátká půlvlna má asi 159 µs
        return 0.7 if podil_v_pasmu(h, 80, 560) > 0.85 and podil_v_pasmu(h, 80, 280) > 0.3 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky = sorted((b for u in useky for b in bloky_sord(ktx.pulzy, u)), key=lambda b: b.zacatek)
        out: list[Soubor] = []
        for b in bloky:
            if b.typ == "H" or not out or out[-1].kompletni:
                out.append(Soubor(self.id, "", "", ""))
            out[-1].bloky.append(b)
            self.dokonci(out[-1])
        for s in out:
            periody = []
            for b in s.bloky:
                if b.nosna_zacatek is None or b.nosna_zacatek >= b.zacatek:
                    continue
                # IBG jsou pouze jedničky. Průměr přes celou nosnou zachová
                # přesnost pod vzorek a nezávisí na střídě signálu.
                vzorky = np.rint(np.array([b.nosna_zacatek, b.zacatek]) * ktx.pulzy.rate)
                a, c = np.searchsorted(ktx.pulzy.hrany, vzorky)
                if c > a:
                    periody.append(2 * float(np.mean(ktx.pulzy.behy(int(a), int(c)))) * 1e6 / ktx.pulzy.rate)
            if periody:
                perioda = float(np.median(periody))
                stdly = int(round((perioda - STDLY_D1_US) / STDLY_KROK_US))
                if 0 <= stdly <= 255:
                    s.info["casovani"] = {"stdly": stdly, "perioda_1_us": perioda}
        return out

    def turbo(self, soubor: Soubor) -> str:
        casovani = soubor.info.get("casovani", {})
        stdly = casovani.get("stdly") if isinstance(casovani, dict) else None
        return f"STDLY ≈ {stdly}" if stdly is not None else "STDLY ?"

    def bloky_pro_zobrazeni(self, s: Soubor) -> list[Blok]:
        out = []
        for b in s.bloky:
            if b.nosna_zacatek is not None and b.nosna_zacatek < b.zacatek:
                out.append(Nosna(b.nosna_zacatek, b.zacatek, "IBG", None, b"", True))
            out.append(b)
        return out

    def dokonci(self, s: Soubor) -> None:
        hl = s.bloky[0] if s.bloky and s.bloky[0].typ == "H" else None
        dat = [b for b in s.bloky if b.typ != "H"]
        data = b"".join(b.data[2:-1] if len(b.data) == (b.data[1] or 256) + 3 else b.data[2:]
                        for b in dat)
        standardni = all(b.typ == "D" for b in dat)
        cele = all(len(b.data) == (b.data[1] or 256) + 3 for b in s.bloky)
        s.kompletni = False
        s.chybi = []
        if hl and len(hl.data) == 34:
            h = hl.data[2:-1]
            s.nazev_bloku = jmeno(h[1:10].split(b"\0", 1)[0])
            s.nazev = s.nazev_bloku or "(bez jména)"
            s.typ_bloku = {3: "Strojový kód", 0x60: "BASIC"}.get(h[0], f"{h[0]:02X}h")
            adresa, delka, start = struct.unpack_from("<HHH", h, 10)
            s.info.update({"adresa": adresa, "delka": delka, "spusteni": start, "typ": h[0]})
            # Poslední blok může být doplněn do 256 B (např. kazety vytvořené z88dk).
            s.kompletni = bool(dat) and standardni and cele and delka <= len(data) < delka + 256
            if standardni:
                data = data[:delka]
        else:
            s.nazev = "(bez hlavičky)"
            s.typ_bloku = "Bez hlavičky"
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky), "texty": texty(data)})
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        self.dokonci(s)
        out = [pripona(cil, ".cas")]
        out[0].write_bytes(CAS_HLAVICKA + b"".join(b.data for b in s.bloky))
        if all(b.typ in ("H", "D") for b in s.bloky) and getattr(s, "_data", b""):
            out.append(pripona(cil, ".bin"))
            out[-1].write_bytes(s._data)
        return out
