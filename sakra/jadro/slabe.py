"""Místa se slabým čtením: pokles úrovně signálu proti okolí (slabá magnetizace, výpadek, zmačkaná páska).

Hledá se jen uvnitř bloků s daty (mezery mezi bloky jsou ticho záměrně). Obálka = špička |x| po
OKNO_S; typická úroveň okolí = 75. percentil obálky po úsecích REF_S (lineárně proložený), takže
pomalé kolísání hlasitosti nevadí a krátký výpadek ji nesníží. Místo, kde obálka klesne pod SLABE
(výpadek pod VYPADEK) typické úrovně, se hlásí včetně sestupu k němu. Krátké mělké poklesy (jedno
okno těsně pod SLABE) jsou běžné kolísání a hlásí se jen, když trvají aspoň MIN_OKEN oken nebo
klesnou pod HLUBOKE. (Ověřeno na nahrávkách HH08518, HH09529, HH09534, HH09582, HH09613: hlášení
pokrývají 7 z 10 vadných bloků; kazeta HH09613 bez šroubků má víc míst než se šroubky.)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

OKNO_S = 0.002          # obálka: špička po 2 ms
REF_S = 1.0             # typická úroveň okolí: úseky po 1 s
OKRAJ_S = 0.02          # kraje bloku (náběh a doznění) se nehodnotí
SLABE = 0.5             # pod polovinu okolí = slabé čtení
VYPADEK = 0.25          # pod čtvrtinu = výpadek
SPOJIT_OKEN = 2         # mezera do 2 oken mezi slabými místy se spojí
MIN_OKEN = 3            # mělký pokles se hlásí, když trvá aspoň 3 okna (6 ms)
HLUBOKE = 0.4           # ... nebo když klesne pod 40 % okolí


@dataclass
class SlabeMisto:
    zacatek: float      # s
    konec: float
    uroven: float       # nejnižší úroveň proti okolí (0..1)

    @property
    def vypadek(self) -> bool:
        return self.uroven < VYPADEK


def _spoj_useky(useky: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(useky):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def slaba_mista(vzorky: np.ndarray, rate: int, useky: list[tuple[float, float]]) -> list[SlabeMisto]:
    """Slabá místa v úsecích s daty (začátek, konec v s), seřazená podle času."""
    n = max(1, int(round(rate * OKNO_S)))
    m = max(1, int(round(REF_S / OKNO_S)))
    out: list[SlabeMisto] = []
    for a, b in _spoj_useky(useky):
        i0 = max(0, int((a + OKRAJ_S) * rate))
        i1 = min(len(vzorky), int((b - OKRAJ_S) * rate))
        oken = (i1 - i0) // n
        if oken < 10:
            continue
        x = vzorky[i0:i0 + oken * n].reshape(oken, n)
        obalka = np.maximum(x.max(axis=1).astype(np.int32), -x.min(axis=1).astype(np.int32)).astype(np.float64)
        useku = -(-oken // m)
        typicka = np.array([np.percentile(obalka[j * m:(j + 1) * m], 75) for j in range(useku)])
        if useku > 1:
            stredy = np.arange(useku) * m + m / 2
            typicka = np.interp(np.arange(oken), stredy, typicka)
        else:
            typicka = np.full(oken, typicka[0])
        if not typicka.max():
            continue
        pomer = obalka / np.maximum(typicka, 1.0)
        slabe = np.flatnonzero(pomer < SLABE)
        if not len(slabe):
            continue
        # souvislé běhy (mezery do SPOJIT_OKEN oken se spojí)
        zlomy = np.flatnonzero(np.diff(slabe) > SPOJIT_OKEN + 1)
        zacatky = np.concatenate(([slabe[0]], slabe[zlomy + 1]))
        konce = np.concatenate((slabe[zlomy], [slabe[-1]]))
        for z, k in zip(zacatky, konce):
            nejnizsi = float(pomer[z:k + 1].min())
            if k + 1 - z >= MIN_OKEN or nejnizsi < HLUBOKE:
                out.append(SlabeMisto((i0 + z * n) / rate, (i0 + (k + 1) * n) / rate, nejnizsi))
    return out


def slaba_mista_strany(v) -> list[SlabeMisto]:
    """Slabá místa ve všech blocích strany (VysledekStrany)."""
    useky = [(b.zacatek, b.konec) for s in v.soubory for b in s.bloky if b.konec > b.zacatek]
    return slaba_mista(v.nahravka.vzorky, v.nahravka.rate, useky)
