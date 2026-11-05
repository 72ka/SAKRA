"""Načtení nahrávky kazety (WAV, FLAC…) do jednoho kanálu int16 připraveného pro hledání pulzů.

Vstup analýzy: jeden kanál (Auto = silnější, levý, pravý), nebo SOUCET = (L + P posunutý o posun_us) / 2 –
u sešikmené hlavy srovná obě stopy a sečte je (lepší poměr signálu k šumu). U sterea se vždy ponechají
obě stopy (`stopy`, každá normalizovaná zvlášť) pro zobrazení a změří se posun P proti L.
"""
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
SOUCET = -1             # kanál: součet L + P s korekcí posunu
MERENI_USEKU = 12       # posun kanálů: medián z tolika nejsilnějších půlsekund


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
    stopy: np.ndarray | None = None    # stereo: (n, 2) int16 L a P, každá normalizovaná zvlášť (zobrazení, součet)
    posun_us: float | None = None      # změřený posun P proti L (kladný: P se zpožďuje); None = nejde změřit
    korelace: float | None = None      # shoda stop v místě posunu (0..1)
    posun_souctu_us: float = 0.0       # o kolik se P posunula při součtu (kanal == SOUCET)

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
    return int(np.argmax(_rozkmity(cesta, info)))


def _rozkmity(cesta: Path, info) -> np.ndarray:
    """99,5. percentil |x| po kanálech z 20 vzorků souboru."""
    with sf.SoundFile(str(cesta)) as f:
        rozkmit = np.zeros(info.channels)
        krok = max(1, info.frames // 20)
        for zac in range(0, info.frames, krok):
            f.seek(zac)
            d = f.read(min(BLOK // 4, info.frames - zac), dtype="float32", always_2d=True)
            if len(d):
                rozkmit = np.maximum(rozkmit, np.percentile(np.abs(d), 99.5, axis=0))
    return rozkmit


def posun_stop(stopy: np.ndarray, rate: int) -> tuple[float | None, float | None]:
    """Posun P proti L (µs) jako medián z nejsilnějších půlsekund; (None, korelace) když stopy nesouhlasí."""
    from .ladeni import posun_kanalu
    n = rate // 2
    kusu = len(stopy) // n
    if kusu < 1:
        return None, None
    sila = np.abs(stopy[: kusu * n, 0].reshape(kusu, n).astype(np.float32)).mean(axis=1)
    nejsilnejsi = np.argsort(sila)[::-1][:MERENI_USEKU]
    mereni = [posun_kanalu(stopy[i * n:(i + 1) * n, 0], stopy[i * n:(i + 1) * n, 1], rate) for i in nejsilnejsi]
    mereni = [(p, k) for p, k in mereni if p is not None]
    if not mereni:
        return None, None
    kor = float(np.median([k for _, k in mereni]))
    dobre = [p for p, k in mereni if k >= 0.5]
    return (float(np.median(dobre)) if dobre else None), kor


def soucet(l: np.ndarray, r: np.ndarray, posun_vzorku: float) -> np.ndarray:
    """(L + P posunutý zpět o posun_vzorku) / 2 jako float32; zlomek vzorku lineární interpolací."""
    n = len(l)
    k = int(np.floor(posun_vzorku))
    f = np.float32(posun_vzorku - k)
    rr = r.astype(np.float32)
    idx = np.clip(np.arange(n) + k, 0, n - 1)
    zarovnana = rr[idx]
    if f:
        zarovnana = (1 - f) * zarovnana + f * rr[np.clip(idx + 1, 0, n - 1)]
    return 0.5 * (l.astype(np.float32) + zarovnana)


def nacti(cesta: str | Path, kanal: int | None = None, prubeh=None, posun_us: float | None = None) -> Nahravka:
    """Načte nahrávku. `kanal`: None = silnější, 0/1/… = ten kanál, SOUCET = L + P s korekcí posunu
    (`posun_us` P proti L; None = změřit). `prubeh(podil)` se volá s hodnotou 0..1."""
    cesta = Path(cesta)
    info = sf.info(str(cesta))
    stereo = info.channels > 1
    rozkmit = _rozkmity(cesta, info) if stereo else None
    if kanal is None:
        kanal = int(np.argmax(rozkmit)) if stereo else 0
    if kanal == SOUCET and not stereo:
        kanal = 0
    deleni = 2 if info.samplerate > MAX_RATE else 1
    rate = info.samplerate // deleni
    n = info.frames // deleni
    x = np.empty(n if kanal != SOUCET else 0, np.float32)
    st = np.empty((n, 2), np.int16) if stereo else None
    meritka = (30000.0 / np.maximum(rozkmit[:2], 1e-6)).astype(np.float32) if stereo else None
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
            dd = d[:, :2] if stereo else d[:, :1]
            if deleni == 2:
                dd = dd[: len(dd) // 2 * 2].reshape(-1, 2, dd.shape[1]).mean(axis=1)
            dd = dd[: n - pos]
            if stereo:
                st[pos:pos + len(dd)] = np.clip(dd * meritka, -32767, 32767)
            if kanal != SOUCET:                       # jeden kanál: přesně jako dřív
                c = d[:, kanal]
                if deleni == 2:
                    c = c[: len(c) // 2 * 2].reshape(-1, 2).mean(axis=1)
                c = c[: n - pos]
                x[pos:pos + len(c)] = c
            pos += len(dd)
            if prubeh:
                prubeh(0.8 * pos / max(1, n))
    if stereo:
        st = st[:pos]
        posun_zmereny, korelace = posun_stop(st, rate)
    else:
        posun_zmereny = korelace = None
    posun_souctu = 0.0
    if kanal == SOUCET:
        posun_souctu = posun_us if posun_us is not None else (posun_zmereny or 0.0)
        x = soucet(st[:, 0], st[:, 1], posun_souctu * 1e-6 * rate)
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
                    obalky=np.clip(ob, 0, 1).astype(np.float32), krok_obalky=krok_ob / info.samplerate,
                    stopy=st, posun_us=posun_zmereny, korelace=korelace, posun_souctu_us=posun_souctu)


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
