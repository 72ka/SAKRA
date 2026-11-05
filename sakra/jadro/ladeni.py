"""Ladění hlavy magnetofonu (azimut) podle přehrávaného záznamu: ukazatele z posledního kusu zvuku.

- Délky pulzů (půlperiody mezi průchody nulou s hysterezí): při správném azimutu ostré špičky
  histogramu; rozmazaná hlava je rozšíří. Rozptyl hlavní špičky = směrodatná odchylka / průměr.
- Posun kanálů L/R (stereo): data jsou na obou stopách stejná, šikmá hlava je posune v čase.
  Vzájemná korelace v okně ±MAX_POSUN_US, zpřesněná parabolou; ideál 0 µs.
- Úroveň výšek: RMS rozdílu sousedních vzorků (vyšší = víc vysokých kmitočtů, lepší azimut).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HYSTEREZE = 0.08          # podíl špičky: průchod nulou se počítá až po překročení ±hystereze
MAX_US = 2000             # histogram 0..MAX_US µs
KROK_US = 10
MAX_POSUN_US = 300


@dataclass
class Ladeni:
    histogram: np.ndarray        # počty pulzů po KROK_US
    spicka_us: float | None      # střed hlavní špičky
    rozptyl: float | None        # směrodatná odchylka / průměr hlavní špičky (0.03 = ±3 %)
    posun_us: float | None       # L proti R (kladné: R se zpožďuje), None u mono
    korelace: float | None       # 0..1 v místě posunu
    vysky: float                 # úroveň výšek (0..1 plné škály)
    pulzu: int


def delky_pulzu_us(x: np.ndarray, rate: int) -> np.ndarray:
    """Půlperiody (µs) mezi průchody nulou s hysterezí."""
    x = np.asarray(x, np.float64)
    if len(x) < 4:
        return np.zeros(0)
    prah = HYSTEREZE * np.abs(x).max()
    if prah <= 0:
        return np.zeros(0)
    stav = np.where(x > prah, 1, np.where(x < -prah, -1, 0))
    i = np.flatnonzero(stav)
    if len(i) < 2:
        return np.zeros(0)
    s = stav[i]
    zmeny = i[1:][s[1:] != s[:-1]]            # první vzorek za překročením opačného prahu
    if len(zmeny) < 2:
        return np.zeros(0)
    return np.diff(zmeny) * 1e6 / rate


def hlavni_spicka(delky: np.ndarray) -> tuple[float | None, float | None]:
    """Střed a relativní rozptyl nejčetnější skupiny délek (okolí módu ±25 %)."""
    d = delky[(delky > 0) & (delky < MAX_US)]
    if len(d) < 20:
        return None, None
    h, _ = np.histogram(d, bins=np.arange(0, MAX_US + KROK_US, KROK_US))
    mod = (np.argmax(h) + 0.5) * KROK_US
    sk = d[np.abs(d - mod) <= 0.25 * mod]
    if len(sk) < 10:
        return None, None
    stred = float(sk.mean())
    return stred, float(sk.std() / stred)


def posun_kanalu(l: np.ndarray, r: np.ndarray, rate: int) -> tuple[float | None, float | None]:
    """Posun R proti L (µs) a korelace v jeho místě."""
    l = np.asarray(l, np.float64) - np.mean(l)
    r = np.asarray(r, np.float64) - np.mean(r)
    if len(l) < 64 or not l.any() or not r.any():
        return None, None
    n = 1 << int(np.ceil(np.log2(2 * len(l))))
    k = np.fft.irfft(np.fft.rfft(r, n) * np.conj(np.fft.rfft(l, n)), n)
    m = max(1, int(MAX_POSUN_US * 1e-6 * rate))
    okno = np.concatenate((k[-m:], k[:m + 1]))          # zpoždění -m..+m
    j = int(np.argmax(okno))
    zpozdeni = j - m
    if 0 < j < len(okno) - 1:                             # parabola přes tři body
        a, b, c = okno[j - 1], okno[j], okno[j + 1]
        jm = a - 2 * b + c
        if jm:
            zpozdeni += 0.5 * (a - c) / jm
    kor = float(okno[j] / np.sqrt((l ** 2).sum() * (r ** 2).sum()))
    return zpozdeni * 1e6 / rate, max(0.0, min(1.0, kor))


def vyhodnot(x: np.ndarray, rate: int, plna: float = 2 ** 31) -> Ladeni:
    """x: vzorky (n,) nebo (n, kanály) – poslední kus přehrávaného záznamu."""
    x = np.asarray(x)
    if x.ndim == 1:
        x = x[:, None]
    mono = x.astype(np.float64).mean(axis=1)
    delky = delky_pulzu_us(mono, rate)
    h, _ = np.histogram(delky, bins=np.arange(0, MAX_US + KROK_US, KROK_US))
    spicka, rozptyl = hlavni_spicka(delky)
    posun = kor = None
    if x.shape[1] >= 2:
        posun, kor = posun_kanalu(x[:, 0], x[:, 1], rate)
    vysky = float(np.sqrt(np.mean(np.diff(mono) ** 2)) / plna) if len(mono) > 1 else 0.0
    return Ladeni(h, spicka, rozptyl, posun, kor, vysky, len(delky))
