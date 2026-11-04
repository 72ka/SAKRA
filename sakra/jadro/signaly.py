"""Společné nástroje pro dekodéry: běhy a periody v µs, souvislé řady, sériové rámce (UART), skládání bajtů."""
from __future__ import annotations

import numpy as np

from .pulzy import Pulzy


def behy_us(p: Pulzy, i0: int, i1: int) -> np.ndarray:
    """Délky půlvln (mezi sousedními hranami) v µs; prvek k odpovídá hraně i0 + k."""
    return np.diff(p.hrany[i0:i1 + 1]) * (1e6 / p.rate)


def periody(p: Pulzy, i0: int, i1: int, smer: int = -1) -> tuple[np.ndarray, np.ndarray]:
    """Celé periody měřené mezi hranami stejného směru (-1 = sestupná, jako průchod nulou dolů).

    Vrací (délky v µs, vzorek začátku periody)."""
    idx = np.flatnonzero(p.urovne[i0:i1 + 1] == smer) + i0
    h = p.hrany[idx]
    return np.diff(h) * (1e6 / p.rate), h[:-1]


def rady(maska: np.ndarray, nejmene: int = 1) -> list[tuple[int, int]]:
    """Souvislé řady hodnot True: [(od, do)) s délkou aspoň `nejmene`."""
    m = np.concatenate(([0], maska.astype(np.int8), [0]))
    z = np.flatnonzero(np.diff(m))
    return [(int(a), int(b)) for a, b in zip(z[::2], z[1::2]) if b - a >= nejmene]


def bajt_lsb(bity) -> int:
    return sum((int(b) & 1) << i for i, b in enumerate(bity))


def bajt_msb(bity) -> int:
    v = 0
    for b in bity:
        v = (v << 1) | (int(b) & 1)
    return v


def bajty_msb(bity: np.ndarray) -> bytes:
    n = len(bity) // 8
    return np.packbits(np.asarray(bity[:n * 8], np.uint8)).tobytes() if n else b""


def uart(bity, data: int = 8, stop: int = 1, parita=None, od: int = 0, do: int | None = None):
    """Asynchronní rámce: start 0, `data` bitů od LSB, (parita), `stop` bitů 1. Mezi rámci libovolně 1.

    `parita(hodnota) -> očekávaný bit` (nebo None = bez parity).
    Vrací seznam (index startbitu, hodnota, rámec v pořádku). Po chybném rámci se hledá další start bit.
    """
    b = bity
    n = len(b) if do is None else min(do, len(b))
    delka = 1 + data + (1 if parita else 0) + stop
    out = []
    i = od
    while i + delka <= n:
        if b[i] != 0:
            i += 1
            continue
        hod = bajt_lsb(b[i + 1:i + 1 + data])
        k = i + 1 + data
        ok = True
        if parita:
            ok = int(b[k]) == parita(hod)
            k += 1
        if not all(int(x) == 1 for x in b[k:k + stop]):
            ok = False
        out.append((i, hod, ok))
        i = i + delka if ok else i + 1
    return out


def souvisle_bajty(ramce_, delka_ramce: int) -> list[list[tuple[int, int, bool]]]:
    """Rámce z `uart` rozdělí na skupiny jdoucí těsně za sebou (mezera nejvýš 4 rámce klidu)."""
    skupiny: list[list] = []
    for r in ramce_:
        if skupiny and r[0] - skupiny[-1][-1][0] <= delka_ramce * 5:
            skupiny[-1].append(r)
        else:
            skupiny.append([r])
    return skupiny


def dve_shluky(x: np.ndarray, iteraci: int = 12) -> tuple[float, float]:
    """Dvě hodnoty (krátká, dlouhá) metodou k-průměrů v 1D."""
    x = np.asarray(x, np.float64)
    if len(x) == 0:
        return 0.0, 0.0
    # krajní percentily: jedna skupina může výrazně převažovat (dlouhý úvodní tón)
    a, b = np.percentile(x, 1), np.percentile(x, 99)
    for _ in range(iteraci):
        if a == b:
            break
        prah = (a + b) / 2
        m = x < prah
        if m.all() or not m.any():
            break
        a, b = float(x[m].mean()), float(x[~m].mean())
    return float(a), float(b)


def xor(data: bytes) -> int:
    v = 0
    for x in data:
        v ^= x
    return v
