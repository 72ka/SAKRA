"""Generátory testovacích signálů dalších platforem (podle specifikací v modulech sakra/platformy)."""
from __future__ import annotations

import struct

import numpy as np

from sakra.jadro.manchester import runy_z_pulbitu


def pulzy_z_us(delky_us, rate: int) -> list[int]:
    """Délky půlvln v µs -> vzorky se zaokrouhlováním kumulativního času (bez ujíždění)."""
    t = np.cumsum(np.asarray(delky_us, np.float64)) * rate / 1e6
    r = np.diff(np.concatenate(([0], np.rint(t)))).astype(np.int64)
    return [max(1, int(x)) for x in r]


TICHO = 1_000_000.0      # 1 s ticha (délka půlvlny nad 5 ms = ticho v signal_z_pulzu)


# ---------------------------------------------------------------- PMD 85 (MAME pmd_cas)

def pmd_hlavicka(cislo: int, typ: str, adresa: int, data: bytes, jmeno: bytes) -> bytes:
    h = bytes([0xFF] * 16 + [0] * 16 + [0x55] * 16)
    t = bytes([cislo, ord(typ)]) + struct.pack("<HH", adresa, len(data) - 1) + jmeno.ljust(8)[:8]
    return h + t + bytes([sum(t) & 0xFF])


def pmd_telo(data: bytes) -> bytes:
    return data + bytes([sum(data) & 0xFF])


def pulzy_pmd(bloky: list[bytes], rate: int = 44100, rychlost: float = 1.0) -> list[int]:
    T = 1e6 / 2400 * rate / 1e6 / rychlost
    urovne: list = [("pauza", rate // 2)]
    bity = [1] * 3600
    for i, b in enumerate(bloky):
        if i:
            bity += [1] * 1200
        for x in b:
            bity += [0] + [(x >> q) & 1 for q in range(8)] + [1, 1]
    for bit in bity:
        urovne += [bit ^ 1, bit]
    urovne.append(("pauza", rate))
    return runy_z_pulbitu(urovne, T)[0]


# ---------------------------------------------------------------- Maťo

def pulzy_mato(cislo: int, jmeno: bytes, data: bytes, rate: int = 44100) -> list[int]:
    """Perioda 833 µs = 0, 1667 µs = 1; bajt = 1 + 8 bitů od LSB; klid = 0."""
    hl = bytes([cislo, 0x3E, 0x01, 0x24]) + struct.pack("<H", len(data) - 1) + jmeno.ljust(8)[:8]
    hl = b"\x55" + hl + bytes([sum(hl) & 0xFF])
    telo = bytearray(data + bytes([sum(data) & 0xFF]))
    telo[0] = (telo[0] << 1) & 0xFF            # na pásce je první bajt posunutý (matowav2ptp ho vrací)
    bity = [0] * 300
    for x in bytes([0x55] * 20) + hl:
        bity += [1] + [(x >> q) & 1 for q in range(8)]
    bity += [0] * 50
    for x in telo:
        bity += [1] + [(x >> q) & 1 for q in range(8)]
    bity += [0] * 50
    us = [TICHO]
    for b in bity:
        us += [833.0, 833.0] if b else [416.5, 416.5]
    us.append(TICHO)
    return pulzy_z_us(us, rate)


# ---------------------------------------------------------------- IQ 151

def iq_radek(n_adresa: int, typ: int, data: bytes) -> str:
    bb = bytes([len(data), n_adresa >> 8, n_adresa & 0xFF, typ]) + data
    return ":" + bb.hex().upper() + f"{-sum(bb) & 0xFF:02X}"


def pulzy_iq151(radky: list[str], kom: list[tuple[int, bytes, int]] | None = None, rate: int = 44100) -> list[int]:
    """Standardní záznam (řádky Intel HEX) a volitelně bloky Komenia (adresa, data, start)."""
    T = 500e-6 * rate
    urovne: list = [("pauza", rate // 2)]
    bity = [1] * 400
    for r in radky:
        for c in (r + "\r").encode("ascii"):
            bity += [0] + [(c >> q) & 1 for q in range(7)] + [1]
        bity += [1] * 20
    for bit in bity:
        urovne += [bit, bit ^ 1]
    urovne.append(("pauza", rate))
    for adresa, data, start in kom or []:
        n = len(data)
        payload = bytes([n >> 8, n & 0xFF, adresa >> 8, adresa & 0xFF]) + data
        payload += bytes([(adresa + n) >> 8 & 0xFF, (adresa + n) & 0xFF, start >> 8, start & 0xFF])
        b2 = [0] * 300 + [1, 0, 0] + [(0x4C >> q) & 1 for q in range(7, -1, -1)]
        for x in payload:
            b2 += [(x >> q) & 1 for q in range(7, -1, -1)]
        b2 += [0] * 20
        for bit in b2:
            urovne += [bit, bit ^ 1]
        urovne.append(("pauza", rate // 2))
    return runy_z_pulbitu(urovne, T)[0]


# ---------------------------------------------------------------- ZX81

def zx81_p(n: int, seed: int = 3) -> bytes:
    """Data .P délky n s E_LINE odpovídající délce."""
    d = bytearray(np.random.default_rng(seed).integers(0, 64, n, dtype=np.uint8).tobytes())
    e = 0x4009 + n
    d[0x0B], d[0x0C] = e & 0xFF, e >> 8
    d[20:30] = bytes([0x38, 0x2A, 0x37, 0x2A, 0x32, 0x38, 0x2A, 0x00, 0x2B, 0x26])   # „SEREMSE FA“ ve znacích ZX81
    return bytes(d)


def pulzy_zx81(jmeno: bytes, data: bytes, rate: int = 44100) -> list[int]:
    us = [TICHO]
    for x in jmeno[:-1] + bytes([jmeno[-1] | 0x80]) + data:
        for q in range(7, -1, -1):
            n = 9 if (x >> q) & 1 else 4
            us += [150.0] * (2 * n - 1) + [150.0 + 1300.0]
    us.append(TICHO)
    return pulzy_z_us(us, rate)


def pulzy_zx81_fast(data: bytes, rate: int = 44100) -> list[int]:
    us = [TICHO] + [125.0] * 400 + [250.0, 250.0]
    for x in data:
        for q in range(7, -1, -1):
            us += [250.0, 250.0] if (x >> q) & 1 else [125.0, 125.0]
    us.append(TICHO)
    return pulzy_z_us(us, rate)


# ---------------------------------------------------------------- Commodore 64

def c64_hlavicka(typ: int, start: int, data: bytes, jmeno: bytes) -> bytes:
    return (bytes([typ]) + struct.pack("<HH", start, start + len(data)) + jmeno.ljust(16, b" ")[:16]).ljust(192, b" ")


def pulzy_c64(hlavicka: bytes, data: bytes, rate: int = 44100, rychlost: float = 1.0) -> list[int]:
    from sakra.platformy.commodore import HODINY, _pulzy_bloku
    us = [TICHO]
    for payload, hl in ((hlavicka, True), (data, False)):
        for kopie in (1, 2):
            for v in _pulzy_bloku(payload, kopie, hl):
                t = v * 8 / HODINY * 1e6 / rychlost
                us += [t / 2, t / 2]
        us.append(400000.0)
    us.append(TICHO)
    return pulzy_z_us(us, rate)


# ---------------------------------------------------------------- MSX a Acorn (FSK 1200 Bd)

def _fsk_bajty(bajty: bytes, stop: int) -> list[float]:
    us = []
    for x in bajty:
        for b in [0] + [(x >> q) & 1 for q in range(8)] + [1] * stop:
            us += [208.33] * 4 if b else [416.67] * 2
    return us


def pulzy_msx(bloky: list[bytes], rate: int = 44100) -> list[int]:
    us = [TICHO]
    for i, b in enumerate(bloky):
        us += [208.33] * (16000 if i == 0 else 4000)
        us += _fsk_bajty(b, 2)
        us.append(800000.0)
    us.append(TICHO)
    return pulzy_z_us(us, rate)


def acorn_blok(jmeno: bytes, cislo: int, data: bytes, posledni: bool, nacti: int = 0x1900) -> bytes:
    from sakra.platformy.fsk import crc_acorn
    h = jmeno + b"\0" + struct.pack("<IIHHB", nacti, 0x8023, cislo, len(data), 0x80 if posledni else 0) + bytes(4)
    out = b"\x2a" + h + struct.pack(">H", crc_acorn(h))
    if data:
        out += data + struct.pack(">H", crc_acorn(data))
    return out


def pulzy_acorn(bloky: list[bytes], rate: int = 44100) -> list[int]:
    us = [TICHO]
    for i, b in enumerate(bloky):
        us += [208.33] * (12000 if i == 0 else 1500)
        us += _fsk_bajty(b, 1)
        us += [208.33] * 300
        us.append(500000.0)
    us.append(TICHO)
    return pulzy_z_us(us, rate)


# ---------------------------------------------------------------- Oric (rychlý záznam)

def oric_tap(typ: int, start: int, data: bytes, jmeno: bytes) -> bytes:
    kon = start + len(data) - 1
    h = bytes([0, 0, typ, 0, kon >> 8, kon & 0xFF, start >> 8, start & 0xFF, 0])
    return h + jmeno + b"\0" + data


def pulzy_oric(obsah: bytes, rate: int = 44100) -> list[int]:
    us = [TICHO]
    for i, x in enumerate(bytes([0x16] * 40 + [0x24]) + obsah):
        par = 1 ^ (bin(x).count("1") & 1)
        for b in [0] + [(x >> q) & 1 for q in range(8)] + [par, 1, 1, 1, 1]:
            us += [208.33, 208.33] if b else [208.33, 416.67]
    us.append(TICHO)
    return pulzy_z_us(us, rate)


# ---------------------------------------------------------------- Atari (FSK 600 Bd)

def atari_zaznamy(data: bytes) -> list[bytes]:
    from sakra.platformy.atari import soucet_atari
    out = []
    for i in range(0, len(data) + 1, 128):
        kus = data[i:i + 128]
        if len(kus) == 128:
            z = b"\x55\x55\xfc" + kus
        else:
            z = b"\x55\x55\xfa" + kus.ljust(127, b"\0") + bytes([len(kus)])
        out.append(z + bytes([soucet_atari(z)]))
        if len(kus) < 128:
            break
    z = b"\x55\x55\xfe" + bytes(128)
    out.append(z + bytes([soucet_atari(z)]))
    return out


def signal_atari(zaznamy: list[bytes], rate: int = 44100, baud: float = 600.0) -> list[int]:
    """Spojitá FSK: značka 5327 Hz, mezera 3995 Hz; mezi záznamy značka (mezera mezi záznamy)."""
    us: list[float] = [TICHO]
    tb = 1e6 / baud
    bity = [1] * int(baud * 3)
    for z in zaznamy:
        for x in z:
            bity += [0] + [(x >> q) & 1 for q in range(8)] + [1]
        bity += [1] * int(baud * 0.25)
    # převod bitů na půlvlny se spojitou fází
    t = 0.0
    hrana = 0.0
    konec = len(bity) * tb
    while hrana < konec:
        b = bity[min(int(hrana / tb), len(bity) - 1)]
        pul = 1e6 / (5327 if b else 3995) / 2
        us.append(pul)
        hrana += pul
    us.append(TICHO)
    return pulzy_z_us(us, rate)


# ---------------------------------------------------------------- PWM (ZX turbo, Turbo 2000, CPC)

def pulzy_pwm(bloky: list[bytes], pilot: float, pilot_pocet: int, sync: list[float], nula: float, jedna: float,
              rate: int = 44100, trailer: int = 0) -> list[int]:
    us = [TICHO]
    for b in bloky:
        us += [pilot] * pilot_pocet + list(sync)
        for x in b:
            for q in range(7, -1, -1):
                t = jedna if (x >> q) & 1 else nula
                us += [t, t]
        us += [jedna, jedna] * trailer
        us += [nula, 500000.0]
    us.append(TICHO)
    return pulzy_z_us(us, rate)


def cpc_zaznam(sync: int, obsah: bytes) -> bytes:
    from sakra.platformy.pwm import crc_cpc
    out = bytes([sync])
    for i in range(0, max(len(obsah), 1), 256):
        seg = obsah[i:i + 256].ljust(256, b"\0")
        c = crc_cpc(seg)
        out += seg + bytes([c >> 8, c & 0xFF])
    return out


# ---------------------------------------------------------------- Sharp MZ (MAME mz_cas)

def pulzy_mz(hlavicka: bytes, data: bytes, rate: int = 44100) -> list[int]:
    K, D = [240.0, 278.0], [464.0, 494.0]

    def bajty(bb: bytes) -> list[float]:
        out = []
        for x in bb:
            out += D
            for q in range(7, -1, -1):
                out += D if (x >> q) & 1 else K
        return out

    def blok(bb: bytes, znacka: int, mezera: int) -> list[float]:
        sc = sum(bin(b).count("1") for b in bb) & 0xFFFF
        tel = bajty(bb + bytes([sc >> 8, sc & 0xFF]))
        return K * mezera + D * znacka + K * znacka + D + tel + D + K * 256 + tel + D

    us = [TICHO] + blok(hlavicka, 40, 3000) + [400000.0] + blok(data, 20, 1500) + [TICHO]
    return pulzy_z_us(us, rate)
