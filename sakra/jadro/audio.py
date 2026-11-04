"""Načtení nahrávky kazety (WAV, FLAC…) do jednoho kanálu int16 připraveného pro hledání pulzů."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

POPIS_FORMATU = {
    "PCM_U8": "8 bit", "PCM_S8": "8 bit", "PCM_16": "16 bit", "PCM_24": "24 bit",
    "PCM_32": "32 bit", "FLOAT": "32 bit float", "DOUBLE": "64 bit float",
}
BLOK = 1 << 20          # po kolika vzorcích se soubor čte
MAX_RATE = 50_000       # vyšší vzorkování se pro analýzu zmenší na polovinu (96 kHz -> 48 kHz)
KROK_OBALKY_S = 0.01    # obálka všech kanálů (přehled kazety): maximum po 10 ms


@dataclass
class Nahravka:
    cesta: Path
    rate: int               # vzorkování analyzovaného signálu (po případném zmenšení)
    rate_puvodni: int       # vzorkování souboru
    kanaly: int
    kanal: int              # použitý kanál (0 = levý)
    subtype: str            # podtyp soundfile (PCM_16, FLOAT…)
    vzorky: np.ndarray      # int16, odstraněná stejnosměrná složka, normalizováno
    obracena: bool = False  # nastaví se, když dekodér zjistí obrácenou polaritu
    obalky: np.ndarray | None = None   # (kanály, n) špička |x| po krok_obalky s, 0..1 společně pro všechny kanály
    krok_obalky: float = KROK_OBALKY_S

    @property
    def delka(self) -> float:
        return len(self.vzorky) / self.rate

    @property
    def format_popis(self) -> str:
        return POPIS_FORMATU.get(self.subtype, self.subtype)

    @property
    def vzorkovani_popis(self) -> str:
        k = self.rate_puvodni / 1000
        return (f"{k:.0f} kHz" if k == int(k) else f"{k:.1f} kHz".replace(".", ","))


def _vyber_kanal(cesta: Path, info) -> int:
    """U sterea vezme kanál s větším rozkmitem (druhý bývá prázdný nebo slabší)."""
    if info.channels == 1:
        return 0
    with sf.SoundFile(str(cesta)) as f:
        rozkmit = np.zeros(info.channels)
        krok = max(1, info.frames // 20)
        for zac in range(0, info.frames, krok):
            f.seek(zac)
            d = f.read(min(BLOK // 4, info.frames - zac), dtype="float32", always_2d=True)
            if len(d):
                rozkmit = np.maximum(rozkmit, np.percentile(np.abs(d), 99.5, axis=0))
    return int(np.argmax(rozkmit))


def nacti(cesta: str | Path, kanal: int | None = None, prubeh=None) -> Nahravka:
    """Načte nahrávku. `prubeh(podil)` se volá s hodnotou 0..1."""
    cesta = Path(cesta)
    info = sf.info(str(cesta))
    if kanal is None:
        kanal = _vyber_kanal(cesta, info)
    deleni = 2 if info.samplerate > MAX_RATE else 1
    rate = info.samplerate // deleni
    n = info.frames // deleni
    x = np.empty(n, np.float32)
    pos = 0
    krok_ob = max(1, int(info.samplerate * KROK_OBALKY_S))
    obalky: list[np.ndarray] = []
    zbytek: np.ndarray | None = None
    with sf.SoundFile(str(cesta)) as f:
        while True:
            d = f.read(BLOK * deleni, dtype="float32", always_2d=True)
            if not len(d):
                break
            a = np.abs(d) if zbytek is None else np.concatenate([zbytek, np.abs(d)])
            m = len(a) // krok_ob * krok_ob                       # zbytek do dalšího bloku (obálka nesmí ujet)
            if m:
                obalky.append(a[:m].reshape(m // krok_ob, krok_ob, a.shape[1]).max(axis=1))
            zbytek = a[m:]
            c = d[:, kanal]
            if deleni == 2:
                c = c[: len(c) // 2 * 2].reshape(-1, 2).mean(axis=1)
            c = c[: n - pos]
            x[pos:pos + len(c)] = c
            pos += len(c)
            if prubeh:
                prubeh(0.8 * pos / max(1, n))
    x = x[:pos]
    _odstran_ss(x, rate)
    vrchol = float(np.percentile(np.abs(x[:: max(1, len(x) // 2_000_000)]), 99.9)) if len(x) else 0.0
    meritko = 30000.0 / vrchol if vrchol > 0 else 1.0
    out = np.empty(len(x), np.int16)
    for zac in range(0, len(x), BLOK):
        out[zac:zac + BLOK] = np.clip(x[zac:zac + BLOK] * meritko, -32767, 32767)
    if prubeh:
        prubeh(1.0)
    ob = np.concatenate(obalky).T if obalky else np.zeros((info.channels, 0), np.float32)
    if ob.size and ob.max() > 0:
        ob = ob / float(np.percentile(ob, 99.9) or ob.max())
    return Nahravka(cesta, rate, info.samplerate, info.channels, kanal, info.subtype, out,
                    obalky=np.clip(ob, 0, 1).astype(np.float32), krok_obalky=krok_ob / info.samplerate)


def _odstran_ss(x: np.ndarray, rate: int) -> None:
    """Odečte pomalu se měnící stejnosměrnou složku (střed po 50 ms, lineárně proložený)."""
    krok = max(1, rate // 20)
    m = len(x) // krok
    if m < 2:
        x -= x.mean() if len(x) else 0
        return
    stredy = x[: m * krok].reshape(m, krok).mean(axis=1)
    osa = np.arange(m) * krok + krok / 2
    for zac in range(0, len(x), BLOK):
        idx = np.arange(zac, min(len(x), zac + BLOK))
        x[zac:zac + len(idx)] -= np.interp(idx, osa, stredy).astype(np.float32)


def obalka(vzorky: np.ndarray, sloupcu: int) -> tuple[np.ndarray, np.ndarray]:
    """Minimum a maximum pro `sloupcu` stejných dílů (náhled vlny na časové ose)."""
    n = len(vzorky)
    if n == 0 or sloupcu <= 0:
        return np.zeros(0, np.int16), np.zeros(0, np.int16)
    krok = max(1, n // sloupcu)
    m = n // krok
    v = vzorky[: m * krok].reshape(m, krok)
    return v.min(axis=1), v.max(axis=1)
