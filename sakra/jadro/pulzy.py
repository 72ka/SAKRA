"""Hledání pulzů (přechodů signálu) s hysterezí a rozdělení nahrávky na úseky."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

KUS = 1 << 22   # zpracování po kusech kvůli paměti


@dataclass
class Pulzy:
    """Přechody signálu: `hrany[i]` = vzorek, kde se úroveň změnila na `urovne[i]` (+1/-1)."""
    rate: int
    hrany: np.ndarray     # int64
    urovne: np.ndarray    # int8
    posun: int = 0        # vzorek, od kterého se počítalo (u opakovaného čtení části nahrávky)

    def behy(self, od: int = 0, do: int | None = None) -> np.ndarray:
        """Délky úrovní (ve vzorcích) mezi hranami od..do."""
        return np.diff(self.hrany[od:(len(self.hrany) if do is None else do + 1)])

    def cas(self, i: int) -> float:
        return float(self.hrany[min(i, len(self.hrany) - 1)]) / self.rate


def najdi_pulzy(x: np.ndarray, rate: int, rel: float = 0.15, posun: int = 0,
                podlaha_rel: float | None = None) -> Pulzy:
    """Přechody s hysterezí: práh = `rel` × místní špička (±2 ms), nejméně 2 % celkové špičky.
    `podlaha_rel` = pevná spodní mez prahu vůči špičce (pro čtení úseku bez ticha, kde odhad šumu selže)."""
    blk = max(16, rate // 2000)
    n = len(x) // blk
    if n == 0:
        return Pulzy(rate, np.zeros(0, np.int64), np.zeros(0, np.int8), posun)
    pk = np.abs(x[: n * blk].astype(np.int32)).reshape(n, blk).max(axis=1)
    okoli = pk.copy()
    for d in (1, 2, 3, 4):
        okoli[d:] = np.maximum(okoli[d:], pk[:-d])
        okoli[:-d] = np.maximum(okoli[:-d], pk[d:])
    # spodní mez prahu: nad šumem v tichých místech, ale nejvýš čtvrtina špičky signálu
    vrchol = float(np.percentile(pk, 99))
    podlaha = min(max(0.02 * vrchol, 1.5 * float(np.percentile(pk, 5))), 0.25 * vrchol)
    if podlaha_rel is not None:
        podlaha = podlaha_rel * vrchol
    prah_bl = np.maximum(okoli * rel, podlaha).astype(np.int32)

    hrany, urovne = [], []
    posledni = 0
    for zac in range(0, len(x), KUS):
        kus = x[zac:zac + KUS].astype(np.int32)
        bl = np.minimum((np.arange(zac, zac + len(kus)) // blk), n - 1)
        h = prah_bl[bl]
        s = np.zeros(len(kus), np.int8)
        s[kus > h] = 1
        s[kus < -h] = -1
        idx = np.flatnonzero(s)
        if not len(idx):
            continue
        v = s[idx]
        zmena = np.empty(len(v), bool)
        zmena[0] = v[0] != posledni
        zmena[1:] = v[1:] != v[:-1]
        hrany.append(idx[zmena] + zac)
        urovne.append(v[zmena])
        posledni = int(v[-1])
    if not hrany:
        return Pulzy(rate, np.zeros(0, np.int64), np.zeros(0, np.int8), posun)
    return Pulzy(rate, np.concatenate(hrany).astype(np.int64) + posun, np.concatenate(urovne), posun)


def odecti_stred(x: np.ndarray, rate: int, okno_us: float) -> np.ndarray:
    """Odečte klouzavý průměr přes `okno_us` (plovoucí nula: u střídavě vázaného záznamu se střed signálu
    posouvá podle dat a průchody nulou se ztrácejí). Okno = perioda nejdelšího bitu ho odstraní celé."""
    n = max(2, int(round(okno_us * rate / 1e6)))
    c = np.concatenate(([0.0], np.cumsum(x, dtype=np.float64)))
    a = np.clip(np.arange(len(x)) - n // 2, 0, len(x))
    b = np.clip(np.arange(len(x)) - n // 2 + n, 0, len(x))
    y = x - (c[b] - c[a]) / np.maximum(b - a, 1)
    return np.clip(y, -32767, 32767).astype(np.int16)


@dataclass
class Usek:
    """Souvislý úsek signálu bez delší pauzy; i0..i1 jsou indexy do Pulzy.hrany."""
    i0: int
    i1: int
    zacatek: float
    konec: float
    histogram: np.ndarray = field(repr=False, default=None)  # počty běhů po 10 µs (0..3 ms)

    @property
    def delka(self) -> float:
        return self.konec - self.zacatek


HIST_KROK_US = 10
HIST_MAX_US = 3000


def histogram_us(behy: np.ndarray, rate: int) -> np.ndarray:
    us = behy * (1e6 / rate)
    return np.bincount(np.minimum((us / HIST_KROK_US).astype(np.int64), HIST_MAX_US // HIST_KROK_US),
                       minlength=HIST_MAX_US // HIST_KROK_US + 1)


def rozdel_na_useky(p: Pulzy, mezera_s: float = 0.02, min_hran: int = 64) -> list[Usek]:
    """Úseky oddělené během delším než `mezera_s` (ticho nebo stejnosměrný signál)."""
    if len(p.hrany) < 2:
        return []
    behy = np.diff(p.hrany)
    dlouhe = np.flatnonzero(behy > mezera_s * p.rate)
    zacatky = np.concatenate(([0], dlouhe + 1))
    konce = np.concatenate((dlouhe, [len(p.hrany) - 1]))
    out = []
    for a, b in zip(zacatky, konce):
        if b - a < min_hran:
            continue
        u = Usek(int(a), int(b), p.cas(a), p.cas(b))
        u.histogram = histogram_us(behy[a:b], p.rate)
        out.append(u)
    return out


# ---- ruční úpravy přechodů (oprava poškozeného bloku) ----

def vloz_hranu(p: Pulzy, vzorek: int) -> Pulzy:
    """Přidá přechod na vzorku; úrovně za ním se obrátí (přechody se vždy střídají)."""
    i = int(np.searchsorted(p.hrany, vzorek))
    if i < len(p.hrany) and p.hrany[i] == vzorek:
        return p
    nova = -(p.urovne[i - 1] if i > 0 else -p.urovne[0] if len(p.urovne) else 1)
    hr = np.insert(p.hrany, i, vzorek)
    ur = np.concatenate((p.urovne[:i], [nova], -p.urovne[i:])).astype(np.int8)
    return Pulzy(p.rate, hr, ur, p.posun)


def odeber_hranu(p: Pulzy, i: int) -> Pulzy:
    """Odebere přechod s indexem i (např. zákmit); úrovně za ním se obrátí."""
    hr = np.delete(p.hrany, i)
    ur = np.concatenate((p.urovne[:i], -p.urovne[i + 1:])).astype(np.int8)
    return Pulzy(p.rate, hr, ur, p.posun)
