"""POTAS – Počítač Operačně TAktického Stupně (ČSLA, navržen na VAAZ Brno; U880D/Z80, 64 KB RAM).

Záznam rozluštěný z nahrávek (kazeta s programy ČSLA, VAAZ Brno 1983–1989), dokumentace k formátu není:
* pevná bitová buňka ~204 µs (~4,9 kbit/s); v buňce s bitem 0 je puls (vzestupná hrana), u bitu 1 není nic,
* bajty těsně za sebou, od nejnižšího bitu, bez start/stop bitů,
* blok: úvodní tón ~1 s (samé nuly = puls v každé buňce), synchronizace FC 7E AA, data až do ticha,
* bez kontrolního součtu – programy se ukládaly 2–3×, kopie se porovnají (u tří a více většinové hlasování).
Soubory: textový editor EDIS (katedra 303 VAAZ) ukládá krátkou hlavičku 00 + 4 B + jméno + 0Dh a pak blok textu;
programy v BASICu (Microsoft BASIC pro 8080/Z80, tokeny FOR 81h, DIM 85h, REM 8Eh) začínají jménem a nulou;
strojové programy jménem a příkazem monitoru („viCALC    startIA800,GEFE0,G6020“).
Čeština v textech: 87h á, 88h é, 89h í, 8Bh ó, 8Ch ú, 8Dh ý, 8Fh ž, 97h č, 98h ď, 99h ě, 9Bh ň, 9Ch ř, 9Dh š, A1h ů.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.texty import hex_vypis
from .zaklad import Kontext, Platforma, podil_v_pasmu, pripona

BUNKA_US = 204.4
SYNC = bytes([0xFC, 0x7E, 0xAA])
SYNC_BITY = "".join(format(c, "08b")[::-1] for c in SYNC)
MAX_VYPADEK_S = 0.3
CESKY = {0x87: "á", 0x88: "é", 0x89: "í", 0x8B: "ó", 0x8C: "ú", 0x8D: "ý", 0x8F: "ž", 0x97: "č", 0x98: "ď",
         0x99: "ě", 0x9B: "ň", 0x9C: "ř", 0x9D: "š", 0xA1: "ů",
         0x80: "Á", 0x81: "É", 0x82: "Í", 0x8E: "Č", 0x90: "Ě", 0x93: "Ř", 0x94: "Š", 0x96: "Ž"}
# tokeny BASICu odvozené z programů na pásce (Microsoft BASIC pro 8080/Z80, tabulka se od Altair/NASCOM liší);
# nejisté tokeny se ve výpisu ukazují jako {XX}
TOKENY = {0x81: "FOR", 0x82: "NEXT", 0x83: "DATA", 0x84: "INPUT", 0x85: "DIM", 0x88: "GOTO", 0x8A: "IF",
          0x8C: "GOSUB", 0x8D: "RETURN", 0x8E: "REM", 0x91: "ON", 0x95: "PRINT", 0xB1: "TAB(", 0xB2: "TO",
          0xB5: "THEN", 0xB8: "-", 0xC0: "="}


def vypis_basic(data: bytes, nejvic_radku: int = 5000) -> str:
    """Výpis programu: jméno 00, pak řádky (odkaz 2 B, číslo 2 B, text, 00). Texty v uvozovkách, REM a DATA
    v češtině POTAS, tokeny podle TOKENY, ostatní {XX}."""
    k = data.find(b"\x00")
    i = k + 1 if 0 < k < 16 else 0
    radky = []
    while i + 4 < len(data) and len(radky) < nejvic_radku:
        odkaz = data[i] | data[i + 1] << 8
        cislo = data[i + 2] | data[i + 3] << 8
        j = data.find(b"\x00", i + 4)
        if odkaz == 0 or j < 0:
            break
        out, uvozovky, doslovne = [], False, False
        for c in data[i + 4:j]:
            if c == 0x22:
                uvozovky = not uvozovky
                out.append('"')
            elif uvozovky or doslovne:
                out.append(CESKY.get(c, chr(c) if 32 <= c < 127 else "·"))
            elif c in TOKENY:
                t = TOKENY[c]
                out.append(t if t in ("=", "-") else f" {t}" if t.endswith("(") else f" {t} ")
                doslovne = c in (0x83, 0x8E)                         # DATA, REM: zbytek doslova
            elif c >= 0x80:
                out.append(f"{{{c:02X}}}")
            else:
                out.append(chr(c) if 32 <= c < 127 else "·")
        radky.append(f"{cislo} " + re.sub(" +", " ", "".join(out)).strip())
        i = j + 1
    return "\n".join(radky)


def text_potas(data: bytes) -> str:
    """Text v kódování POTAS (ASCII + česká písmena) -> Unicode; řídicí znaky kromě konce řádku jako ·."""
    out = []
    for c in data:
        if 32 <= c < 127:
            out.append(chr(c))
        elif c == 13:
            out.append("\n")
        elif c == 10:
            continue
        else:
            out.append(CESKY.get(c, "·"))
    return "".join(out)


OKNO_MRIZKY = 64            # period pro poznání signálu mimo mřížku buňky


def bity_potas(hrany: np.ndarray, rate: int) -> tuple[str, np.ndarray, float]:
    """Vzestupné hrany -> bity (puls = 0, prázdná buňka = 1). Vrací (bity, vzorek začátku bitu, buňka µs)."""
    if len(hrany) < 2:
        return "", np.zeros(0), BUNKA_US
    per = np.diff(hrany) * 1e6 / rate
    jedn = per[(per > 0.7 * BUNKA_US) & (per < 1.3 * BUNKA_US)]
    T = float(np.median(jedn)) if len(jedn) > 100 else BUNKA_US
    q = per / T
    k = np.maximum(np.round(q).astype(int), 0)
    # signál mimo mřížku buňky (jiný formát, tón, řeč) a dlouhé mezery = ticho (jedničky ve skutečné délce)
    mimo = np.convolve(np.abs(q - k) > 0.3, np.ones(OKNO_MRIZKY) / OKNO_MRIZKY, "same") > 0.5
    ticho = mimo | (k > 64)
    ok = k >= 1
    kk = np.minimum(k[ok], 4096)
    bity = "".join("1" * m if t else "1" * (m - 1) + "0" for m, t in zip(kk.tolist(), ticho[ok].tolist())) \
        + "1" * 48
    poradi = np.arange(int(kk.sum())) - np.repeat(np.cumsum(kk) - kk, kk)      # pořadí bitu v mezeře
    zac = np.repeat(hrany[:-1][ok], kk) + poradi * T * rate / 1e6
    zac = np.concatenate([zac, hrany[-1] + np.arange(1, 49) * T * rate / 1e6])
    return bity, zac, T


def bajty_z_bitu(bity: str) -> bytes:
    """Bity (od LSB) -> bajty."""
    return bytes(int(bity[j:j + 8][::-1], 2) for j in range(0, len(bity) - 7, 8))


MAX_TICHO = 1024            # bitů (~0,2 s) bez pulzu = konec záznamu
MIN_UVOD = 1000             # bitů úvodního tónu před platnou synchronizací (tón má ~5000)
OKNO_KONCE = 256             # bitů: v datech bývá ~40 % nul, v šumu po konci záznamu skoro žádné
MIN_HUSTOTA_NUL = 0.12


def konec_dat(bity: str, i: int, j: int) -> int:
    """Konec dat v úseku bity[i:j]: za posledním oknem s dostatkem nul (pulzů), zarovnáno na bajt.
    Výpadek uprostřed dat (řada jedniček) blok neukončí – za ním data pokračují."""
    a = np.frombuffer(bity[i:j].encode(), np.uint8) == 48
    if len(a) < OKNO_KONCE:
        return i + len(a) // 8 * 8
    hustota = np.convolve(a, np.ones(OKNO_KONCE) / OKNO_KONCE, "valid")
    dobra = np.flatnonzero(hustota >= MIN_HUSTOTA_NUL)
    if not len(dobra):
        return i
    posl_nula = dobra[-1] + OKNO_KONCE - 1
    posl_nula = int(np.flatnonzero(a[:posl_nula + 1])[-1]) if a[:posl_nula + 1].any() else posl_nula
    return i + (posl_nula // 8 + 1) * 8


def bloky_potas(bity: str) -> list[tuple[int, int, bytes, str]]:
    """[(bit začátku dat, bit konce, data, bity dat)] – od synchronizace FC 7E AA po úvodním tónu do konce dat."""
    out = []
    # platná synchronizace má před sebou úvodní tón (≥ MIN_UVOD nul); jinde jde o náhodu v datech
    synchronizace = []
    for m in re.finditer(SYNC_BITY, bity):
        zac = m.start()
        pred = bity[max(0, zac - MIN_UVOD):zac]
        if len(pred) == MIN_UVOD and pred.count("1") <= MIN_UVOD // 100:     # tón smí mít ojedinělý výpadek
            uvod = zac
            while uvod >= 64 and bity[uvod - 64:uvod].count("1") <= 2:
                uvod -= 64
            synchronizace.append((uvod, m.end()))
    for n, (_, i) in enumerate(synchronizace):
        hranice = synchronizace[n + 1][0] if n + 1 < len(synchronizace) else len(bity)
        ticho = bity.find("1" * MAX_TICHO, i)                    # krátký výpadek data nepřeruší, dlouhé ticho ano
        if 0 <= ticho < hranice:
            hranice = ticho
        konec = konec_dat(bity, i, hranice)
        data = bajty_z_bitu(bity[i:konec])
        if len(data) >= 4:
            out.append((i, i + 8 * len(data), data, bity[i:konec]))
    return out


def rozbor(data: bytes) -> tuple[str, str, dict]:
    """(jméno, typ, info) podle začátku bloku."""
    if data[0] == 0x00 and len(data) < 4096:
        k = data.find(b"\r", 5)
        jm = text_potas(data[5:k if k > 0 else 40]).strip()
        return jm, "Hlavička EDIS", {}
    m = re.match(rb"([ -~]{1,12})\x00", data)
    if m and sum(chr(c).isalpha() for c in m.group(1)) >= 2:
        return m.group(1).decode().strip(), "BASIC", {}
    m = re.match(rb"([A-Za-z][ -~]{1,11}?) +(start[ -~]*)", data[:80])
    if m:
        return m.group(1).decode().strip(), "Strojový kód", {"spusteni": m.group(2).decode()}
    return "", "Data", {}


def spoj_kopie(bity: list[str]) -> tuple[str, list[int]]:
    """Kopie téhož záznamu bit po bitu (kopie na pásce nejsou vůči sobě posunuté, chyby jsou jen záměny bitů).
    Tři a více kopií: většina. Dvě: puls (0) vyhrává – chyby jsou skoro vždy chybějící pulzy při výpadku
    signálu (na kazetě RH… 119 ze 121). Vrací (spojené bity, počet změněných bitů v každé kopii)."""
    L = min(len(b) for b in bity)
    A = np.array([np.frombuffer(b[:L].encode(), np.uint8) - 48 for b in bity])
    if len(bity) >= 3:
        spol = (A.sum(axis=0) * 2 > len(bity)).astype(np.uint8)
    else:
        spol = A.min(axis=0)
    zmen = [int((A[k] != spol).sum()) for k in range(len(bity))]
    nejdelsi = max(bity, key=len)
    return "".join(map(str, spol.tolist())) + nejdelsi[L:], zmen


class POTAS(Platforma):
    id = "potas"
    pocitac = "POTAS"
    varianta = ""
    barva = "#7A8B3C"
    pripona = "bin"
    poradi = 43

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram                                       # půlvlny ~100 µs (puls) a jejich násobky
        return 0.7 if podil_v_pasmu(h, 60, 140) > 0.4 and podil_v_pasmu(h, 60, 500) > 0.85 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        p = ktx.pulzy
        skupiny: list[list[Usek]] = []
        for u in sorted(useky, key=lambda x: x.zacatek):
            if skupiny and u.zacatek - skupiny[-1][-1].konec < MAX_VYPADEK_S:
                skupiny[-1].append(u)
            else:
                skupiny.append([u])
        zaznamy: list[tuple[Blok, str, str, dict]] = []
        for sk in skupiny:
            a, b = sk[0].i0, sk[-1].i1
            hr = p.hrany[a:b + 1][p.urovne[a:b + 1] == 1]
            if len(hr) < 2000:
                continue
            bity, zac, T = bity_potas(hr, p.rate)
            if not (150 < T < 260):
                continue
            for i0, i1, data, bity_dat in bloky_potas(bity):
                t0 = float(zac[min(i0, len(zac) - 1)]) / p.rate
                t1 = float(zac[min(i1, len(zac) - 1)]) / p.rate
                jm, typ, info = rozbor(data)
                blok = Blok(t0, t1, "hlavička" if typ == "Hlavička EDIS" else "data", None, data, True)
                blok._bity = bity_dat  # type: ignore[attr-defined]
                zaznamy.append((blok, jm, typ, info))
        # hlavička EDIS + následující blok textu = jeden soubor
        soubory: list[Soubor] = []
        i = 0
        while i < len(zaznamy):
            blok, jm, typ, info = zaznamy[i]
            s = Soubor(self.id, "", jm, typ, bloky=[blok], overeno=False)
            s.info.update(info)
            if typ == "Hlavička EDIS" and i + 1 < len(zaznamy) and zaznamy[i + 1][2] == "Data" \
                    and zaznamy[i + 1][0].zacatek - blok.konec < 30:
                s.bloky.append(zaznamy[i + 1][0])
                s.typ_bloku = "Text (EDIS)"
                i += 1
            soubory.append(s)
            i += 1
        _porovnej_kopie(soubory)
        for s in soubory:
            self.dokonci(s)
        return soubory

    def dokonci(self, s: Soubor) -> None:
        data = s.bloky[-1].data
        s.nazev = s.nazev_bloku or s.nazev or f"(blok {len(data)} B)"
        s.nazev_bloku = s.nazev_bloku or s.nazev
        s.kompletni = True
        s.chybi = []
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky)})
        if s.typ_bloku == "Text (EDIS)":
            s.info["texty"] = [r for r in text_potas(data).splitlines() if sum(c.isalpha() for c in r) >= 4][:20]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = [pripona(cil, ".bin")]
        out[0].write_bytes(s.bloky[-1].data)
        if s.typ_bloku in ("Text (EDIS)", "BASIC"):
            t = pripona(cil, ".txt")
            d = s.bloky[-1].data
            t.write_text(vypis_basic(d) if s.typ_bloku == "BASIC" else text_potas(d), encoding="utf-8")
            out.append(t)
        return out

    def nahled(self, s: Soubor) -> dict:
        d = s.bloky[-1].data
        if s.typ_bloku == "BASIC":
            return {"obrazky": [], "texty": [("Výpis BASICu (nejisté tokeny jako {XX})", vypis_basic(d, 120))]}
        if s.typ_bloku == "Text (EDIS)":
            return {"obrazky": [], "texty": [("Text", text_potas(d[:3000]))]}
        return {"obrazky": [], "texty": [("Začátek dat", hex_vypis(d[:256]))]}


MAX_ROZDIL = 0.02            # víc rozdílných bitů = jiná verze se stejným začátkem, ne chyby čtení


def _porovnej_kopie(soubory: list[Soubor]) -> None:
    """Kopie = záznamy na téže straně s podobnou délkou, které se liší nejvýš v MAX_ROZDIL bitů (jméno nerozhoduje
    – i v něm bývá chyba čtení); spojí se bit po bitu (spoj_kopie) a výsledek dostanou všechny kopie.
    Záznam se stejným začátkem, ale jiným obsahem se označí jako možná jiná verze."""
    shluky: list[list[Soubor]] = []
    for s in soubory:
        b = getattr(s.bloky[-1], "_bity", None)
        if not b:
            continue
        for sh in shluky:
            b0 = sh[0].bloky[-1]._bity  # type: ignore[attr-defined]
            if abs(len(b0) - len(b)) <= max(128, len(b) // 100) and _podil_rozdilu(b0, b) <= MAX_ROZDIL:
                sh.append(s)
                break
        else:
            shluky.append([s])
    for sh in shluky:
        if len(sh) >= 2:
            _spoj_shluk(sh)
    for s in soubory:
        if not s.overeno and any(t is not s and t.bloky[-1].data[:32] == s.bloky[-1].data[:32] for t in soubory):
            s.info["kopie"] = "na pásce je záznam se stejným začátkem, ale jiným obsahem (jiná verze?)"


def _podil_rozdilu(a: str, b: str) -> float:
    L = min(len(a), len(b))
    if not L:
        return 1.0
    return float((np.frombuffer(a[:L].encode(), np.uint8) != np.frombuffer(b[:L].encode(), np.uint8)).mean())


def _spoj_shluk(sh: list[Soubor]) -> None:
    bity = [s.bloky[-1]._bity for s in sh]  # type: ignore[attr-defined]
    spojene, zmen = spoj_kopie(bity)
    data = bajty_z_bitu(spojene)
    pravidlo = "rozhodla většina" if len(sh) >= 3 else "chybějící pulzy doplněny z druhé kopie"
    for s, z in zip(sh, zmen):
        b = s.bloky[-1]
        if z:
            b.oprava = f"{z} bitů podle kopií ({pravidlo})"
        b.data = data
        s.overeno = True
        s.info["kopie"] = (f"{len(sh)} kopie, rozdílných bitů {sum(zmen)} ({pravidlo})"
                           if sum(zmen) else f"{len(sh)} shodné kopie")
