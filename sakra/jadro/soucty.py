"""Kontrolní součty bloku pro detail: hodnota uložená na pásce a hodnota spočtená z přečtených dat.

Počítá se znovu z blok.data (funguje i u starších projektů), podle formátu platformy. Kde součet
v datech bloku není (Commodore, Sharp), bere se z blok.soucet_pasky, který vyplní dekodér.
"""
from __future__ import annotations

import struct

BEZ_SOUCTU = {"zx81", "oric", "potas", "sms-vuvt", "msx"}     # formát kontrolní součet nemá


class Soucet(tuple):
    """(popis, na pásce, spočteno, číslic hex); na pásce None = neznámé (chybí v datech)."""
    __slots__ = ()

    def __new__(cls, popis: str, pasek: int | None, spocteno: int, cislic: int = 2):
        return super().__new__(cls, (popis, pasek, spocteno, cislic))

    @property
    def sedi(self) -> bool:
        return self[1] == self[2]


def _xor(d: bytes) -> int:
    x = 0
    for v in d:
        x ^= v
    return x


def _soucet_atari(d: bytes) -> int:
    s = 0
    for b in d:
        s += b
        if s > 255:
            s = (s & 0xFF) + 1
    return s


def _crc16(d: bytes, start: int, konec_xor: int) -> int:
    crc = start
    for b in d:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc ^ konec_xor


def soucty_bloku(platforma: str, blok) -> list[Soucet] | None:
    """Součty bloku podle id platformy. [] = nejde určit (krátký či nestandardní blok),
    None = formát kontrolní součet nemá."""
    if platforma in BEZ_SOUCTU or blok.typ == "nestandardní":
        return None
    d = bytes(blok.data)
    try:
        return _soucty(platforma, blok, d)
    except (IndexError, ValueError, struct.error):
        return []


def _soucty(platforma: str, blok, d: bytes) -> list[Soucet]:
    if platforma == "sord-m5" and len(d) >= 2 and d[0] in b"HDEF":
        n = d[1] or 256
        if (d[0] != ord("H") or n == 31) and len(d) in (n + 2, n + 3):
            # Typ a délka nejsou součástí součtu. Chybějící poslední bajt
            # nehádat: úplná data lze sečíst i bez součtu přečteného z pásky.
            pasek = d[n + 2] if len(d) == n + 3 else None
            return [Soucet("součet", pasek, sum(d[2:n + 2]) & 0xFF)]
    if platforma in ("zx-rom", "zx-turbo", "atari-t2k") and len(d) >= 2:
        return [Soucet("XOR", d[-1], _xor(d[:-1]))]
    if platforma in ("ondra-tesla", "sapi1-mikos") and len(d) == 275:
        return [Soucet("součet", d[272], sum(d[3:272]) & 0xFF)]
    if platforma == "ondra-vili":
        if blok.typ == "H" and len(d) >= 25:
            return [Soucet("součet hlavičky", d[24], sum(d[1:24]) & 0xFF)]
        if blok.typ == "D" and len(d) >= 3:
            return [Soucet("součet dat", d[-1], sum(d[1:-1]) & 0xFF)]
    if platforma in ("pmd85", "mato"):
        if blok.typ == "hlavička" and len(d) == 63:
            return [Soucet("součet hlavičky", d[62], sum(d[48:62]) & 0xFF)]
        if blok.typ == "hlavička" and len(d) == 16:
            return [Soucet("součet hlavičky", d[15], sum(d[1:15]) & 0xFF)]
        if blok.typ == "data" and len(d) >= 2:
            return [Soucet("součet dat", d[-1], sum(d[:-1]) & 0xFF)]
    if platforma == "iq151":
        if blok.typ == "záznam" and d[:1] == b":":
            bb = bytes.fromhex(d[1:].decode("ascii"))
            return [Soucet("součet záznamu", bb[-1], -sum(bb[:-1]) & 0xFF)] if len(bb) >= 2 else []
        if blok.typ == "Komenium" and len(d) >= 8:
            delka, adresa = d[0] << 8 | d[1], d[2] << 8 | d[3]
            return [Soucet("kontrolní slovo", d[-4] << 8 | d[-3], (adresa + delka) & 0xFFFF, 4)]
    if platforma == "c64-rom" and blok.soucet_pasky is not None:
        return [Soucet("XOR", blok.soucet_pasky, _xor(d))]
    if platforma == "sharp-mz" and blok.soucet_pasky is not None:
        return [Soucet("počet jedniček", blok.soucet_pasky, sum(bin(b).count("1") for b in d) & 0xFFFF, 4)]
    if platforma == "atari-rom" and len(d) == 132:
        return [Soucet("součet", d[131], _soucet_atari(d[:131]))]
    if platforma == "acorn":
        k = d.index(0, 1, 12)
        delka = struct.unpack_from("<H", d, k + 1 + 10)[0]
        out = [Soucet("CRC hlavičky", d[k + 18] << 8 | d[k + 19], _crc16(d[1:k + 18], 0, 0), 4)]
        d0 = k + 20
        if delka and len(d) >= d0 + delka + 2:
            out.append(Soucet("CRC dat", d[d0 + delka] << 8 | d[d0 + delka + 1], _crc16(d[d0:d0 + delka], 0, 0), 4))
        return out
    if platforma == "cpc" and len(d) >= 259:
        out = []
        for j, i in enumerate(range(1, len(d) - 257, 258)):
            out.append(Soucet(f"CRC segmentu {j + 1}", d[i + 256] << 8 | d[i + 257],
                              _crc16(d[i:i + 256], 0xFFFF, 0xFFFF), 4))
        return out
    return []
