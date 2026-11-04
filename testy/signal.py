"""Pomůcky pro testy: z délek pulzů udělá zvukový signál jako z magnetofonu."""
from __future__ import annotations

import numpy as np
import soundfile as sf


def signal_z_pulzu(pulzy, rate: int, sum_: float = 0.02, pauza_ms: float = 5.0, seed: int = 1) -> np.ndarray:
    """Obdélník ±0.6; pulzy delší než `pauza_ms` jsou ticho (páska nepřenáší stejnosměrnou složku)."""
    mez = pauza_ms * rate / 1000
    kusy = []
    for i, n in enumerate(pulzy):
        kusy.append(np.full(int(n), 0.0 if n > mez else (0.6 if i % 2 else -0.6), np.float32))
    x = np.concatenate(kusy) if kusy else np.zeros(0, np.float32)
    # trocha zaoblení hran (jednoduchý dolní propust) a šum
    x = np.convolve(x, np.ones(3, np.float32) / 3, mode="same").astype(np.float32)
    x += np.random.default_rng(seed).normal(0, sum_, len(x)).astype(np.float32)
    return x


def uloz_wav(cesta, x: np.ndarray, rate: int, subtype: str = "PCM_16") -> None:
    sf.write(str(cesta), x, rate, subtype=subtype)


# ---------------------------------------------------------------- Ondra

def blok_tesla(typ: int, data: bytes, jmeno: bytes, cislo: int, bajt271: int = 5) -> bytes:
    """Blok ROM Tesla (275 B) se správným součtem."""
    o = bytearray(b"\x10\x10\x10") + bytes([typ]) + data.ljust(255, b"\0")[:255] + jmeno.ljust(11)[:11]
    o += bytes([cislo, bajt271])
    o.append(sum(o[3:272]) & 0xFF)
    o += b"\x10\x10"
    return bytes(o)


def soubor_tesla(jmeno: bytes, data: bytes) -> list[bytes]:
    bloky = [blok_tesla(1, jmeno + b" ", jmeno[:11], 1)]
    kusy = [data[i:i + 255] for i in range(0, len(data), 255)] or [b""]
    for i, k in enumerate(kusy):
        bloky.append(blok_tesla(4 if i == len(kusy) - 1 else 0x42, k, jmeno[:11], i + 2))
    return bloky


def pulzy_tesla(bloky: list[bytes], rate: int = 44100, rychlost: float = 1.0) -> list[int]:
    from sakra.jadro.manchester import runy_z_pulbitu
    T = 204e-6 * rate / rychlost
    urovne: list = [("pauza", rate // 2)]
    for b in bloky:
        bity = [1] * 962
        for x in b:
            bity += [0] + [(x >> q) & 1 for q in range(8)] + [1, 1]
        for bit in bity:
            urovne += [bit, bit ^ 1]
        urovne.append(("pauza", int((0.2 if b[3] == 1 else 0.0435) * rate)))
    urovne.append(("pauza", rate))
    return runy_z_pulbitu(urovne, T)[0]


def zaznam_vili(jmeno: bytes, data: bytes) -> list[bytes]:
    """Soubor ROM ViLi: záznamy po 1024 B, každý 'H' + 23 B + součet a 'D' + data + součet."""
    kusy = [data[i:i + 1024] for i in range(0, len(data), 1024)] or [b""]
    out = []
    for i, k in enumerate(kusy, 1):
        hl = jmeno.ljust(12)[:12] + b"." + b"K\xefD" + f"{i:3d}".encode() + bytes([0xFF if i == len(kusy) else 0])
        hl += bytes([len(k) & 0xFF, len(k) >> 8, 0])
        out.append(b"H" + hl + bytes([sum(hl) & 0xFF]))
        out.append(b"D" + k + bytes([sum(k) & 0xFF]))
    return out


def pulzy_vili(zaznamy: list[bytes], rate: int = 44100) -> list[int]:
    from sakra.jadro.manchester import runy_z_pulbitu
    T = 218e-6 * rate
    urovne: list = [("pauza", rate // 2)]
    for z in zaznamy:
        bity = [1] * 768 + [0]
        for x in z + b"\x00":                       # + koncový bajt
            bity += [1 - (x & 1)] + [(x >> q) & 1 for q in range(8)]
        for bit in bity:
            urovne += [bit, bit ^ 1]
        urovne.append(("pauza", int(0.3 * rate)))
    urovne.append(("pauza", rate))
    return runy_z_pulbitu(urovne, T)[0]
