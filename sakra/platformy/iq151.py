"""IQ 151 – standardní záznam (Intel HEX v textu) a zavaděče Komenia. Podle iq151kom2hex (J. Heřman).

Bifázová modulace, půlbit ~500 µs.
Standardní záznam: úvodní tón (samé 1), znaky po 9 bitech: 0, 7 bitů od LSB, 1 bit. Řádek Intel HEX
  ':' LL AAAA TT data… CC CR; program končí záznamem typu 01, jehož adresa je vstupní bod.
Komenium: za zavaděčem (Intel HEX) následují bloky s úvodem ze samých 0 a znakem 'L', pak bajty po 8 bitech
  od MSB bez start/stop bitů: hlavička 4 B (délka, adresa – big endian; u některých zavaděčů 5 B),
  délka + 4 B dat; předposlední dvojice = adresa + délka (kontrola), poslední dvojice = startovní adresa.
Výstupem je Intel HEX (pro emulátory a modul SD-ROM, se zachovanou nahrávací obrazovkou).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..jadro.manchester import manchester, odhad_pulbitu, pulbity
from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import bajt_lsb, bajt_msb
from ..jadro.texty import texty
from .zaklad import Kontext, Platforma, manchester_skore, pripona

IQ_T_US = 500.0
SYNC_STD = bytes([1] * 24 + [0, 0, 1, 0, 1, 1, 1, 0, 1])           # úvod + ':'
DVOJTECKA = bytes([1, 0, 0, 1, 0, 1, 1, 1, 0, 1])                  # klid + ':'
SYNC_KOM = bytes([0] * 22 + [1, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0])      # úvod + 'L'
# vstupní adresa zavaděče -> typ bloků Komenia (1 = hlavička 4 B, 2 = 5 B); neznámý zavaděč = 5 B
ZAVADECE = {"7934": 1, "3FAE": 1, "7AE2": 1, "7010": 1, "0226": 2, "7A6B": 2, "024D": 2, "605E": 2}
BAJTU_NA_RADEK = 80


def _najdi(b: bytes, vzor: bytes, od: int = 0, do: int | None = None):
    i = b.find(vzor, od, do if do is not None else len(b))
    while i >= 0:
        yield i
        i = b.find(vzor, i + 1, do if do is not None else len(b))


def _znak(b: bytes, k: int):
    if k + 9 > len(b):
        return None, False
    return bajt_lsb(b[k + 1:k + 8]), b[k] == 0


def _zaznam(b: bytes, k: int):
    """Řádek od start bitu ':' na k. Vrací (text bez ':' a CR, konec, rámce v pořádku)."""
    znaky = []
    ok = True
    j = k + 9
    for _ in range(600):
        c, platny = _znak(b, j)
        if c is None:
            return "".join(znaky), j, False
        j += 9
        ok &= platny
        if c == 0x0D:
            return "".join(znaky), j, ok
        znaky.append(chr(c))
    return "".join(znaky), j, False


def _hex_ok(text: str) -> bool:
    try:
        bb = bytes.fromhex(text)
    except ValueError:
        return False
    return len(bb) >= 5 and sum(bb) & 0xFF == 0 and bb[0] == len(bb) - 5


def _udalosti(bity: np.ndarray, pos: np.ndarray, rate: int):
    """Standardní programy a místa bloků Komenia v jednom souvislém kusu signálu."""
    b = bity.astype(np.uint8).tobytes()
    cas = lambda i: float(pos[min(max(i, 0), len(pos) - 1)]) / rate  # noqa: E731
    out = []
    hotovo = 0
    for i in _najdi(b, SYNC_STD):
        k = i + 24
        if k < hotovo:
            continue
        zaznamy = []
        while True:
            text, konec, ok = _zaznam(b, k)
            zaznamy.append(Blok(cas(k), cas(konec), "záznam", len(zaznamy) + 1, (":" + text).encode("ascii", "replace"),
                                ok and _hex_ok(text)))
            hotovo = konec
            if len(text) >= 8 and text[6:8] == "01" or not ok:
                break
            dalsi = b.find(DVOJTECKA, konec, konec + 5000)
            if dalsi < 0:
                break
            k = dalsi + 1
        out.append(("std", zaznamy[0].zacatek, zaznamy))
    for i in _najdi(b, SYNC_KOM):
        out.append(("kom", cas(i), (b, i + len(SYNC_KOM), pos, rate)))
    return out


def _blok_komenia(b: bytes, k: int, pos, rate, typ: int) -> Blok:
    def bajt(j):
        return bajt_msb(b[j:j + 8]) if j + 8 <= len(b) else 0
    hl_delka = 4 if typ == 1 else 5
    hl = [bajt(k + 8 * j) for j in range(hl_delka)]
    delka, adresa = hl[0] << 8 | hl[1], hl[2] << 8 | hl[3]
    zac = k + 8 * hl_delka
    n = delka + 4
    kompletni = zac + 8 * n <= len(b)
    data = bytes(bajt(zac + 8 * j) for j in range(n))
    ok = kompletni and n >= 4 and (data[-4] << 8 | data[-3]) == (adresa + delka) & 0xFFFF
    cas = lambda i: float(pos[min(max(i, 0), len(pos) - 1)]) / rate  # noqa: E731
    blok = Blok(cas(k - len(SYNC_KOM)), cas(zac + 8 * n), "Komenium", None, bytes(hl) + data, ok,
                chybne_bajty=[] if ok else list(range(hl_delka + n)))
    return blok


def _adresa_komenia(blok: Blok, typ: int) -> tuple[int, int, bytes]:
    hl_delka = 4 if typ == 1 else 5
    h = blok.data
    return h[0] << 8 | h[1], h[2] << 8 | h[3], h[hl_delka:]


class IQ151(Platforma):
    id = "iq151"
    pocitac = "IQ 151"
    varianta = ""
    barva = "#D9822B"
    pripona = "hex"
    poradi = 32

    def skore(self, usek: Usek, rate: int) -> float:
        return manchester_skore(usek.histogram, IQ_T_US)

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        p = ktx.pulzy
        udalosti = []
        for u in useky:
            behy = np.diff(p.hrany[u.i0:u.i1 + 1])
            T = odhad_pulbitu(behy, IQ_T_US * p.rate / 1e6)
            if T is None:
                continue
            for hb, hp in pulbity(p, u.i0, u.i1, T):
                b0, pos, _ = manchester(hb, hp)
                for bity in (b0, 1 - b0):
                    udalosti += _udalosti(bity, pos, p.rate)
        # obě polarity najdou totéž; z blízkých stejných událostí se nechá jedna (lepší)
        udalosti.sort(key=lambda u: u[1])
        ciste = []
        for u in udalosti:
            if ciste and ciste[-1][0] == u[0] and abs(ciste[-1][1] - u[1]) < 0.05:
                if u[0] == "std" and sum(b.ok for b in u[2]) > sum(b.ok for b in ciste[-1][2]):
                    ciste[-1] = u
                continue
            ciste.append(u)
        soubory: list[Soubor] = []
        akt: Soubor | None = None
        for druh, _, obsah in ciste:
            if druh == "std":
                akt = Soubor(self.id, "", "", "Intel HEX", bloky=list(obsah))
                soubory.append(akt)
            else:
                b, k, pos, rate = obsah
                typ = akt.info.get("typ_komenia", 999) if akt else 999
                if akt is None:
                    akt = Soubor(self.id, "", "", "Komenium")
                    soubory.append(akt)
                akt.bloky.append(_blok_komenia(b, k, pos, rate, typ))
            self.dokonci(akt)
        for s in soubory:
            self.dokonci(s)
        return soubory

    def dokonci(self, s: Soubor) -> None:
        zaznamy = [b for b in s.bloky if b.typ == "záznam"]
        kom = [b for b in s.bloky if b.typ == "Komenium"]
        eof = next((b for b in zaznamy if b.data[7:9] == b"01"), None)
        vstup = eof.data[3:7].decode("ascii", "replace") if eof else ""
        typ = ZAVADECE.get(vstup.upper(), 999)
        s.info.update({"zaznamu": len(zaznamy), "vstupni_adresa": vstup})
        if kom or typ != 999:
            s.info["typ_komenia"] = typ
        if kom:
            s.typ_bloku = "Komenium"
            delky = [_adresa_komenia(b, typ) for b in kom]
            s.info.update({"bloku_komenia": len(kom), "delka_dat": sum(d for d, _, _ in delky),
                           "adresa": delky[0][1],
                           "zavadec": f"Komenium ({vstup or 'neznámý'}, hlavička {4 if typ == 1 else 5} B)"})
            data = b"".join(x for _, _, x in delky)
            s.kompletni = bool(eof) and all(b.ok for b in kom)
        else:
            s.typ_bloku = "Intel HEX"
            s.kompletni = eof is not None
            data = b""
            for z in zaznamy:
                try:
                    bb = bytes.fromhex(z.data[1:].decode("ascii"))
                    if len(bb) > 5 and bb[3] == 0:
                        data += bb[4:-1]
                except ValueError:
                    pass
            s.info["delka_dat"] = len(data)
        s.chybi = []
        s.info["texty"] = texty(data)
        s.nazev = s.nazev or (texty(data, 1)[0][:30] if texty(data, 1) else f"(IQ 151, vstup {vstup or '?'})")
        s._data = data  # type: ignore[attr-defined]

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = pripona(cil, ".hex")
        out.write_text(intel_hex(s), encoding="ascii", newline="")
        return [out]


def intel_hex(s: Soubor) -> str:
    """Standardní program: řádky, jak byly na pásce. Komenium: data bloků po 80 B + koncový záznam
    se startovní adresou (export_to_intel_hex z iq151kom2hex)."""
    kom = [b for b in s.bloky if b.typ == "Komenium"]
    if not kom:
        return "".join(b.data.decode("ascii", "replace") + "\r\n" for b in s.bloky if b.typ == "záznam")
    typ = s.info.get("typ_komenia", 999)
    radky = []
    posledni = b""
    for b in kom:
        _, adresa, data = _adresa_komenia(b, typ)
        posledni = data
        for i in range(0, len(data), BAJTU_NA_RADEK):
            kus = data[i:i + BAJTU_NA_RADEK]
            radky.append(_radek(len(kus), adresa + i, 0, kus))
    start = (posledni[-2] << 8 | posledni[-1]) if len(posledni) >= 2 else 0
    radky.append(_radek(0, start, 1, b""))
    return "".join(r + "\n" for r in radky)


def _radek(n: int, adresa: int, typ: int, data: bytes) -> str:
    bb = bytes([n, adresa >> 8 & 0xFF, adresa & 0xFF, typ]) + data
    return ":" + bb.hex().upper() + f"{-sum(bb) & 0xFF:02X}"
