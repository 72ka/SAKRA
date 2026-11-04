"""Tesla Ondra SPO 186: kazetové formáty ROM Tesla (MIKOS) a ROM ViLi.

ROM Tesla (MIKOS) – stejný záznam používá i SAPI-1 se systémem MIKOS
  Manchester, půlbit ~204 µs. Bajt = rámec 11 bitů: 0, d0..d7, 1, 1. Před blokem ~960 bitů 1.
  Blok 275 B: 10 10 10, kód bloku, 255 B dat, jméno 11 B, číslo bloku, číslo souboru, součet bajtů 3..271, 10 10.
  Kódy: 01 hlavička, 42 data, 04 poslední; SAPI-1 navíc 3A název kazety, 41/0A/00 text, 0B binární data.
  SAPI-1 ukládá jména v 6bitovém kódu displeje MHB2501 (písmena 01h–1Ah). Podle sapi2wav (J. Heřman).
ROM ViLi
  Manchester, půlbit ~218 µs, úvod 768 bitů 1, start bit 0, bajt = 9 bitů: NOT(d0), d0..d7.
  Záznam: 'H' + 23 B hlavičky + součet, 'D' + data (≤1024 B) + součet; součet bez typového bajtu.
  Hlavička: jméno 12, '.', přípona 3, číslo záznamu 3 (ASCII), FFh = poslední, délka (LE), typ.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..formaty import csw
from ..jadro.manchester import manchester, odhad_pulbitu, pulbity, ramce, runy_z_pulbitu
from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Pulzy, Usek
from ..jadro.texty import jmeno, texty
from .zaklad import Kontext, Platforma, pripona, manchester_skore

POCITAC = "Ondra SPO 186"
ZNAKY = {0xEF: "Ó"}        # přípona „KÓD“ v hlavičce ViLi


def _cas(pos: np.ndarray, i: int, rate: int) -> float:
    return float(pos[min(max(i, 0), len(pos) - 1)]) / rate


def oprav_z_kopii(soubory: list[tuple[int, Soubor]], dokonci) -> None:
    """Doplní chybějící/poškozené bloky z jiné kopie se stejným jménem.

    Kopie se použije jen tehdy, když se s opravovaným souborem shoduje ve všech blocích,
    které jsou v obou v pořádku (a aspoň v jednom).
    """
    for strana, f in soubory:
        if f.ok:
            continue
        for strana2, g in soubory:
            if g is f or g.nazev_bloku != f.nazev_bloku or g.platforma != f.platforma:
                continue
            fm = {b.cislo: b for b in f.bloky if b.ok and b.cislo is not None}
            gm = {b.cislo: b for b in g.bloky if b.ok and b.cislo is not None}
            spolecne = set(fm) & set(gm)
            if not spolecne or any(fm[n].data != gm[n].data for n in spolecne):
                continue
            zmena = False
            cisla = [b.cislo for b in f.bloky]
            for n, gb in sorted(gm.items()):
                if n in fm:
                    continue
                kopie = Blok(gb.zacatek, gb.konec, gb.typ, gb.cislo, gb.data, True,
                             oprava=f"převzato z kopie (strana {strana2}, {gb.zacatek:.2f} s)")
                if n in cisla:                         # poškozený blok nahradit
                    i = cisla.index(n)
                    kopie.zacatek, kopie.konec = f.bloky[i].zacatek, f.bloky[i].konec
                    f.bloky[i] = kopie
                else:                                  # chybějící blok vložit na místo
                    i = next((j for j, c in enumerate(cisla) if c is not None and c > n), len(cisla))
                    # poškozený blok bez čísla na tom místě nahradit
                    if i > 0 and f.bloky[i - 1].cislo is None and not f.bloky[i - 1].ok:
                        i -= 1
                        kopie.zacatek, kopie.konec = f.bloky[i].zacatek, f.bloky[i].konec
                        f.bloky[i] = kopie
                    else:
                        okoli = f.bloky[i - 1] if i > 0 else f.bloky[0]
                        kopie.zacatek = kopie.konec = okoli.konec
                        f.bloky.insert(i, kopie)
                cisla = [b.cislo for b in f.bloky]
                zmena = True
            if zmena:
                dokonci(f)
            if f.ok:
                break


# =====================================================================  ROM Tesla (MIKOS)

TESLA_T_US = 204.0
DELKA = 275
TYPY = {0x01: "hlavička", 0x42: "data", 0x04: "konec",
        0x3A: "název kazety", 0x41: "text", 0x0A: "text", 0x00: "text", 0x0B: "data"}
KODY_SAPI = {0x3A, 0x41, 0x0A, 0x00, 0x0B}


def sapi_nazev(data: bytes) -> str:
    """Jméno v kódu MHB2501 (SAPI-1) -> text; podle get_blknazev ze sapi2wav."""
    out = []
    for b in data:
        b |= 0x40
        if not 32 <= b <= 95:
            b &= 0xBF
        out.append(" " if b == 64 else chr(b))
    return "".join(out).strip()


def je_sapi(s: Soubor) -> bool:
    """SAPI-1: kódy bloků, které Ondra nepoužívá, nebo jméno s písmeny v kódu MHB2501."""
    if any(b.ok and b.data[3] in KODY_SAPI for b in s.bloky):
        return True
    jm = next((b.data[259:270] for b in s.bloky if b.ok), b"")
    return sum(1 <= c <= 0x1A for c in jm) >= 2


def _kontrola_tesla(W):
    platny = (W[:, 0] == 0) & (W[:, 9] == 1) & (W[:, 10] == 1)
    hod = (W[:, 1:9].astype(np.int32) << np.arange(8)).sum(axis=1)
    return platny, hod


def soucet_tesla(o) -> int:
    return sum(o[3:272]) & 0xFF


def _cti_blok(platny, hod, k: int):
    """Čte rámce od k. Při sklouznutí (výpadek, zákmit) se zkusí znovu chytit a čte dál až do konce
    signálu, aby šel zbytek bloku zarovnat podle jeho konce. Vrací (úseky, konec)."""
    N = len(platny)
    useky: list[list[int]] = []
    while True:
        u: list[int] = []
        while k < N and platny[k] and (useky or len(u) < DELKA) and len(u) < 2 * DELKA:
            u.append(int(hod[k]))
            k += 11
        if u:
            useky.append(u)
        if sum(map(len, useky)) >= DELKA or len(useky) > 6:
            break
        for d in sorted(range(-10, 61), key=abs):
            kk = k + d
            if d and 0 <= kk and kk + 33 < N and platny[kk] and platny[kk + 11] and platny[kk + 22]:
                break
        else:
            break
        k = kk
    return useky, k


def _tisknutelne(b) -> bool:
    return all(v is not None and (32 <= v < 127 or v == 0) for v in b)


def _dopln_konec(u: list[int]) -> list[int]:
    """Poslední bajt (10h) mívá stop bity ztracené v následující pauze – rámec pak nejde přečíst.
    Pokud úsek končí „…jméno, číslo, ?, součet, 10“, druhé 10 se doplní."""
    if len(u) >= 15 and u[-1] == 0x10 and _tisknutelne(u[-15:-4]) and (len(u) < 2 or u[-2] != 0x10
                                                                       or not _tisknutelne(u[-16:-5])):
        return u + [0x10]
    return u


def _sestav_blok(useky: list[list[int]]):
    """Z přečtených úseků složí 275 B (None = neznámý bajt). Vrací (bajty, poznámka)."""
    if not useky:
        return None, ""
    useky = [_dopln_konec(u) for u in useky]
    s1 = useky[0][:DELKA]
    if len(useky) == 1:
        return s1 + [None] * (DELKA - len(s1)), ""
    s2 = useky[-1]
    # konec bloku: ...jméno (11), číslo, ?, součet, 10 10 – poslední úsek se zarovná na něj
    if s2[-2:] != [0x10, 0x10] or len(s2) < 16 or not _tisknutelne(s2[-16:-5]):
        return s1 + [None] * (DELKA - len(s1)), "výpadek signálu, zbytek bloku nejde zarovnat"
    s2 = s2[-(DELKA - len(s1)):] if len(s1) + len(s2) > DELKA else s2
    chybi = DELKA - len(s1) - len(s2)
    o = s1 + [None] * chybi + s2
    # Chybějící bajt nejde spolehlivě dopočítat z kontrolního součtu: kolem výpadku bývá
    # špatně přečtený i sousední bajt a dopočet by chybu skryl. Blok zůstane poškozený
    # a opraví se opakovaným čtením nebo z jiné kopie.
    if len(useky) == 2 and chybi == 0:
        return o, "sklouznutí signálu bez ztráty dat"
    return o, f"výpadek signálu, chybí {chybi} B"


def _blok_z_bajtu(o: list, poznamka: str, t0: float, t1: float, hrany) -> Blok:
    chybne = [i for i, v in enumerate(o) if v is None]
    data = bytes(0 if v is None else v for v in o)
    ok = not chybne and data[:3] == b"\x10\x10\x10" and data[273:] == b"\x10\x10" and soucet_tesla(data) == data[272]
    znamy = lambda a, b: all(i not in chybne for i in range(a, b))  # noqa: E731
    typ = TYPY.get(data[3], f"{data[3]:02X}") if znamy(3, 4) else "?"
    cislo = data[270] if znamy(270, 271) else None
    if not ok and not chybne:
        chybne = list(range(DELKA))        # součet nesedí – nevíme, který bajt je špatně
    b = Blok(t0, t1, typ, cislo, data, ok, oprava=poznamka if ok else "", chybne_bajty=[] if ok else chybne,
             hrany=hrany)
    return b


def bloky_tesla(p: Pulzy, i0: int, i1: int) -> list[Blok]:
    behy = np.diff(p.hrany[i0:i1 + 1])
    T = odhad_pulbitu(behy, TESLA_T_US * p.rate / 1e6)
    if T is None:
        return []
    out = []
    for hb, hp in pulbity(p, i0, i1, T):
        bity0, pos, _ = manchester(hb, hp)
        # v jednolitém úvodu nejde fáze (a tím polarita) poznat – zkusí se obě
        for bity in (bity0, 1 - bity0):
            out += _bloky_z_bitu(bity, pos, p.rate, i0, i1)
    for b in out:
        b.info_rychlost = TESLA_T_US / (T / p.rate * 1e6)  # type: ignore[attr-defined]
    return out


def _bloky_z_bitu(bity, pos, rate, i0, i1) -> list[Blok]:
    out = []
    platny, hod = ramce(bity, 11, _kontrola_tesla)
    if len(platny) < 40:
        return out
    N = len(platny)
    kandidati = np.flatnonzero(platny[: N - 33] & (hod[: N - 33] == 0x10))
    hotovo_do = -1
    for k in kandidati:
        if k < hotovo_do:
            continue
        if not (platny[k + 11] and hod[k + 11] == 0x10 and platny[k + 22] and hod[k + 22] == 0x10
                and platny[k + 33] and hod[k + 33] in TYPY):
            continue
        useky, konec = _cti_blok(platny, hod, int(k))
        o, pozn = _sestav_blok(useky)
        if o is None:
            continue
        t0 = _cas(pos, max(0, k - 962), rate)
        b = _blok_z_bajtu(o, pozn, t0, _cas(pos, konec, rate), (i0, i1))
        out.append(b)
        hotovo_do = konec
    return out


class OndraTesla(Platforma):
    id = "ondra-tesla"
    pocitac = POCITAC
    varianta = "Tesla ROM"
    barva = "#59C27A"
    pripona = "csw"
    poradi = 10

    def skore(self, usek: Usek, rate: int) -> float:
        return manchester_skore(usek.histogram, TESLA_T_US)

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky: list[Blok] = []
        for u in useky:
            bloky += bloky_tesla(ktx.pulzy, u.i0, u.i1)
        rychlosti = [getattr(b, "info_rychlost", 1.0) for b in bloky]
        for i, b in enumerate(bloky):
            if not b.ok:
                bloky[i] = self._precti_znovu(ktx, b)
        soubory = self._soubory(bloky)
        for s in soubory:
            s.info["rychlost"] = round(float(np.median(rychlosti)), 3) if rychlosti else 1.0
        return soubory

    def _precti_znovu(self, ktx: Kontext, b: Blok) -> Blok:
        for rel in (0.08, 0.25, 0.05, 0.35, 0.12):
            p2 = ktx.precti_znovu(b.zacatek - 0.05, b.konec + 0.05, rel)
            if len(p2.hrany) < 100:
                continue
            for nb in bloky_tesla(p2, 0, len(p2.hrany) - 1):
                if nb.ok and (b.cislo is None or nb.cislo == b.cislo):
                    nb.oprava = f"opakované čtení (práh {rel:.0%})"
                    nb.zacatek, nb.konec, nb.hrany = b.zacatek, b.konec, b.hrany
                    return nb
        return b

    def _soubory(self, bloky: list[Blok]) -> list[Soubor]:
        soubory: list[Soubor] = []
        akt: Soubor | None = None
        uzavreno = True
        for b in sorted(bloky, key=lambda x: x.zacatek):
            jm = jmeno(b.data[259:270]) if not any(259 <= i < 270 for i in b.chybne_bajty) else None
            if b.typ == "název kazety":
                s = Soubor(self.id, "", jm or "", "")
                s.bloky.append(b)
                soubory.append(s)
                continue
            if b.typ == "hlavička":
                akt = Soubor(self.id, "", jm or "", "")
                soubory.append(akt)
                uzavreno = False
            elif (akt is None or uzavreno or (jm and jm != akt.nazev_bloku)
                  or b.zacatek - akt.konec > 15):
                akt = Soubor(self.id, "", jm or "", "")
                soubory.append(akt)
                uzavreno = False
            akt.bloky.append(b)
            if not akt.nazev_bloku and jm:
                akt.nazev_bloku = jm
            if b.typ == "konec":
                uzavreno = True
        for s in soubory:
            self.dokonci(s)
        return soubory

    def dokonci(self, s: Soubor) -> None:
        """Přepočítá jméno, úplnost, data a informace souboru."""
        if je_sapi(s):
            return Sapi1.dokonci_sapi(s)
        hl = next((b for b in s.bloky if b.typ == "hlavička" and b.ok), None)
        s.nazev = jmeno(hl.data[4:259].split(b"\0")[0]) if hl else (s.nazev_bloku or "(bez jména)")
        cisla = [b.cislo for b in s.bloky if b.cislo is not None]
        posledni = next((b.cislo for b in s.bloky if b.typ == "konec" and b.cislo), None)
        horni = posledni or (max(cisla) if cisla else 0)
        s.chybi = [n for n in range(1, horni + 1) if n not in cisla]
        s.kompletni = bool(hl) and posledni is not None and not s.chybi
        data = b"".join(b.data[4:259] for b in sorted(s.bloky, key=lambda x: x.cislo or 0)
                        if b.typ in ("data", "konec"))
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky),
                       "cislo_souboru": s.bloky[0].data[271] if s.bloky else "",
                       "texty": texty(data)})
        s.info["basic"] = data[:4] == b"\xf6\xf6\xf6\x42"
        s.typ_bloku = "BASIC" if s.info["basic"] else "Kód"
        s._data = data  # type: ignore[attr-defined]

    def sluc_kopie(self, soubory: list[tuple[int, Soubor]]) -> None:
        oprav_z_kopii([(st, s) for st, s in soubory if s.platforma in (self.id, Sapi1.id)], self.dokonci)

    # ---- výstup ----
    POLARITA = 0       # první polovina bitu má jeho hodnotu (jako vzorové CSW FallingBlocks)
    RATE = 44100

    def runy(self, s: Soubor) -> tuple[list[int], int]:
        """Čistý signál souboru (pro CSW): ~960 bitů úvodu, rámce, pauzy mezi bloky."""
        T = TESLA_T_US * self.RATE / 1e6
        urovne: list = [("pauza", self.RATE // 2)]
        for b in sorted(s.bloky, key=lambda x: x.cislo or 0):
            bity = [1] * 962
            for x in b.data:
                bity += [0] + [(x >> q) & 1 for q in range(8)] + [1, 1]
            for bit in bity:
                v = bit ^ self.POLARITA
                urovne += [v, v ^ 1]
            urovne.append(("pauza", int((0.2 if b.typ == "hlavička" else 0.0435) * self.RATE)))
        urovne.append(("pauza", self.RATE))
        return runy_z_pulbitu(urovne, T)

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = [pripona(cil, ".csw"), pripona(cil, ".bin")]
        runy, uroven = self.runy(s)
        csw.zapis(out[0], self.RATE, runy, uroven)
        out[1].write_bytes(getattr(s, "_data", b"") or b"".join(b.data[4:259] for b in s.bloky[1:]))
        return out


class Sapi1(Platforma):
    """SAPI-1 se systémem MIKOS: záznam jako ROM Tesla Ondry; dekóduje ho OndraTesla a podle obsahu přeřadí sem."""
    id = "sapi1-mikos"
    pocitac = "SAPI-1"
    varianta = "MIKOS"
    barva = "#8FB339"
    pripona = "csw"
    poradi = 12

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        return []

    @staticmethod
    def dokonci_sapi(s: Soubor) -> None:
        """Podle extrahuj_data_z_bloku ze sapi2wav: text (41/0A/00) se ořízne na 1Ah, binární (42/0B) celé."""
        s.platforma = Sapi1.id
        bl = sorted(s.bloky, key=lambda x: x.cislo or 0)
        kazeta = next((b for b in bl if b.ok and b.data[3] == 0x3A), None)
        hl = next((b for b in bl if b.ok and b.data[3] == 0x01), None)
        prvni = next((b for b in bl if b.ok), None)
        s.nazev_bloku = sapi_nazev(prvni.data[259:270]) if prvni else s.nazev_bloku
        if kazeta:
            s.nazev = sapi_nazev(kazeta.data[4:68])
            s.typ_bloku = "Název kazety"
            s.kompletni = kazeta.ok
            s.chybi = []
            s.info.update({"bloku": 1, "cislo_souboru": kazeta.data[271]})
            s._data = b""  # type: ignore[attr-defined]
            return
        s.nazev = sapi_nazev(hl.data[4:79]) if hl else (s.nazev_bloku or "(bez jména)")
        textovy = None
        data = bytearray()
        for b in bl:
            k = b.data[3]
            if k in (0x01, 0x3A):
                continue
            d = b.data[4:259]
            if k in (0x41, 0x0A, 0x00):
                textovy = True if textovy is None else textovy
                d = d.split(b"\x1a")[0]
            elif k == 0x04:                      # poslední blok se ořízne na 1Ah vždy (jako sapi2wav)
                d = d.split(b"\x1a")[0]
            elif k in (0x42, 0x0B) and textovy is None:
                textovy = False
            data += d
        cisla = [b.cislo for b in bl if b.cislo is not None]
        posledni = next((b.cislo for b in bl if b.typ == "konec" and b.cislo), None)
        horni = posledni or (max(cisla) if cisla else 0)
        s.chybi = [n for n in range(1, horni + 1) if n not in cisla]
        s.kompletni = bool(hl) and posledni is not None and not s.chybi
        s.typ_bloku = "Text (ASCII)" if textovy else "Binární"
        if textovy:
            data = bytearray(bytes(data).replace(b"\x0c", b"").rstrip(b"\x1a\x03"))
        if hl:
            s.info["poznamka"] = sapi_nazev(hl.data[15:79])
        s.info.update({"delka_dat": len(data), "bloku": len(s.bloky), "cislo_souboru": bl[0].data[271],
                       "texty": texty(bytes(data))})
        s._data = bytes(data)  # type: ignore[attr-defined]

    def sluc_kopie(self, soubory: list[tuple[int, Soubor]]) -> None:
        pass  # dělá OndraTesla (stejný formát)

    def nahled(self, s: Soubor) -> dict:
        if not hasattr(s, "_data"):
            Sapi1.dokonci_sapi(s)
        if s.typ_bloku.startswith("Text"):
            text = s._data.decode("ascii", "replace").replace("\r\n", "\n").replace("\r", "\n")  # type: ignore
            return {"obrazky": [], "texty": [("Text", "\n".join(text.splitlines()[:200]))]}
        return super().nahled(s)

    RATE = OndraTesla.RATE

    def dokonci(self, s: Soubor) -> None:
        OndraTesla().dokonci(s)

    def runy(self, s: Soubor) -> tuple[list[int], int]:
        return OndraTesla().runy(s)

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        tesla = OndraTesla()
        out = [pripona(cil, ".csw")]
        runy, uroven = tesla.runy(s)
        csw.zapis(out[0], tesla.RATE, runy, uroven)
        if s.typ_bloku != "Název kazety":
            if not hasattr(s, "_data"):
                Sapi1.dokonci_sapi(s)
            out.append(pripona(cil, ".txt" if s.typ_bloku.startswith("Text") else ".bin"))
            out[-1].write_bytes(getattr(s, "_data", b""))
        return out


# =====================================================================  ROM ViLi

VILI_T_US = 218.0


def bloky_vili(p: Pulzy, i0: int, i1: int) -> list[Blok]:
    behy = np.diff(p.hrany[i0:i1 + 1])
    T = odhad_pulbitu(behy, VILI_T_US * p.rate / 1e6)
    if T is None:
        return []
    out = []
    for hb, hp in pulbity(p, i0, i1, T):
        bity, pos, _ = manchester(hb, hp)
        for b in (bity.tolist(), (1 - bity).tolist()):
            out += _zaznamy_z_bitu(b, pos, p.rate, i0, i1)
    return out


def _zaznamy_z_bitu(b: list[int], pos, rate: int, i0: int, i1: int) -> list[Blok]:
    out = []
    if True:
        N = len(b)
        nuly = [i for i in range(1, N) if b[i] == 0 and b[i - 1] == 1]
        hotovo_do = 0
        for z in nuly:
            if z < hotovo_do or z < 500 or not all(b[z - 500:z]):
                continue
            j = z + 1
            bajty = []
            while j + 9 <= N and b[j] == 1 - b[j + 1]:
                bajty.append(sum(b[j + 1 + q] << q for q in range(8)))
                j += 9
            hotovo_do = j
            if len(bajty) >= 3 and bajty[0] in (0x48, 0x44):
                out.append(Blok(_cas(pos, z - 768, rate), _cas(pos, j, rate), chr(bajty[0]), None,
                                bytes(bajty), False, hrany=(i0, i1)))
    return out


def _rozbor_vili(bloky: list[Blok]) -> None:
    """Doplní u záznamů H/D kontrolu součtu a číslo záznamu."""
    delka = None
    cislo = None
    for b in bloky:
        d = b.data
        if b.typ == "H" and len(d) >= 25:
            b.ok = (sum(d[1:24]) & 0xFF) == d[24]
            b.data = d[:25]
            try:
                cislo = int(d[17:20].decode("ascii"))
            except ValueError:
                cislo = None
            b.cislo = cislo
            delka = d[21] | d[22] << 8 if b.ok else None
        elif b.typ == "D":
            L = delka if delka is not None else len(d) - 3
            b.ok = delka is not None and len(d) >= L + 2 and (sum(d[1:1 + L]) & 0xFF) == d[1 + L]
            b.data = d[:L + 2]
            b.cislo = cislo
            delka = None
        if not b.ok:
            b.chybne_bajty = list(range(len(b.data)))


class OndraViLi(Platforma):
    id = "ondra-vili"
    pocitac = POCITAC
    varianta = "ViLi ROM"
    barva = "#3FA66A"
    pripona = "tap"
    poradi = 11

    def skore(self, usek: Usek, rate: int) -> float:
        return manchester_skore(usek.histogram, VILI_T_US)

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky: list[Blok] = []
        for u in useky:
            bloky += bloky_vili(ktx.pulzy, u.i0, u.i1)
        bloky.sort(key=lambda b: b.zacatek)
        _rozbor_vili(bloky)
        soubory: list[Soubor] = []
        akt = None
        for b in bloky:
            if b.typ == "H":
                jm = jmeno(b.data[1:13]) if b.ok else ""
                if akt is None or jm != akt.nazev_bloku or (b.cislo or 0) <= max(
                        (x.cislo or 0) for x in akt.bloky) or b.zacatek - akt.konec > 15:
                    akt = Soubor(self.id, "", jm, "")
                    soubory.append(akt)
            elif akt is None:
                akt = Soubor(self.id, "", "", "")
                soubory.append(akt)
            akt.bloky.append(b)
        for s in soubory:
            self.dokonci(s)
        return soubory

    def dokonci(self, s: Soubor) -> None:
        hl = [b for b in s.bloky if b.typ == "H" and b.ok]
        if hl:
            d = hl[0].data
            s.nazev = jmeno(d[1:13]) + "." + jmeno(d[14:17], ZNAKY)
        else:
            s.nazev = s.nazev_bloku or "(bez jména)"
        cisla = sorted({b.cislo for b in hl if b.cislo})
        eof = any(b.data[20] == 0xFF for b in hl)
        horni = max(cisla) if cisla else 0
        s.chybi = [n for n in range(1, horni + 1) if n not in cisla]
        dat_ok = all(b.ok for b in s.bloky)
        s.kompletni = bool(hl) and eof and not s.chybi and dat_ok
        data = b"".join(b.data[1:-1] for b in s.bloky if b.typ == "D" and b.ok)
        s.typ_bloku = "Kód" if hl and hl[0].data[23] == 0 else "Data"
        s.info.update({"delka_dat": len(data), "zaznamu": len(hl), "posledni_zaznam": eof,
                       "texty": texty(data)})
        if not eof and hl:
            s.info["poznamka"] = "chybí poslední záznam (FFh)"
        s._data = data  # type: ignore[attr-defined]

    def sluc_kopie(self, soubory: list[tuple[int, Soubor]]) -> None:
        pass  # záznamy ViLi nenesou jméno v datovém bloku; opravy z kopie zatím jen u ROM Tesla

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        tap = bytearray()
        for b in s.bloky:
            if b.ok:
                tap += b.data
        out = [pripona(cil, ".tap"), pripona(cil, ".bin")]
        out[0].write_bytes(bytes(tap))
        out[1].write_bytes(getattr(s, "_data", b""))
        return out
