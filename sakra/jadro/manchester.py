"""Společné nástroje pro Manchesterské kódování (Ondra: ROM Tesla i ViLi)."""
from __future__ import annotations

import numpy as np

from .pulzy import Pulzy


def odhad_pulbitu(behy: np.ndarray, nominal: float) -> float | None:
    """Délka půlbitu (ve vzorcích) z běhů; hledá se kolem `nominal` (±40 %)."""
    kr = behy[(behy > 0.6 * nominal) & (behy < 1.4 * nominal)]
    dl = behy[(behy > 1.2 * nominal) & (behy < 2.8 * nominal)]
    if len(kr) < 50:
        return None
    t = float(np.median(kr))
    if len(dl) > 20:
        t = (t * len(kr) + float(np.median(dl)) / 2 * len(dl)) / (len(kr) + len(dl))
    return t


def pulbity(p: Pulzy, i0: int, i1: int, T: float):
    """Rozloží běhy na půlbity. Vrací seznam souvislých kusů (úrovně 0/1, pozice ve vzorcích)."""
    hr = p.hrany[i0:i1 + 1]
    r = np.diff(hr).astype(np.float64)
    lv = (p.urovne[i0:i1] > 0).astype(np.int8)
    # 1 nebo 2 půlbity; delší běh (do ~20 ms) je výpadek signálu, ne pauza – vyřeší ho resynchronizace
    k = np.where(r < 1.5 * T, 1, np.where(r < 2.6 * T, 2, np.where(r < 100 * T, np.rint(r / T), 0))).astype(np.int64)
    kusy = []
    hranice = np.flatnonzero(k == 0)
    zac = 0
    for h in list(hranice) + [len(k)]:
        if h - zac > 40:
            kk = k[zac:h]
            beh = np.repeat(np.arange(h - zac), kk)      # ke kterému běhu půlbit patří
            hb = lv[zac:h][beh]
            # první půlbit leží na hraně, druhý půlbit dlouhého běhu v jeho polovině
            prvni = np.concatenate([[True], beh[1:] != beh[:-1]])
            hp = hr[zac:h][beh] + np.where(prvni, 0, (r[zac:h][beh] / 2).astype(np.int64))
            kusy.append((hb, hp))
        zac = h + 1
    return kusy


def manchester(hb: np.ndarray, hp: np.ndarray):
    """Půlbity -> bity (hodnota = úroveň první poloviny), s průběžnou resynchronizací fáze.

    Vrací (bity, pozice, obraceno): bity jsou normované tak, aby synchronizační úvod byl 1.
    """
    n = len(hb)
    if n < 4:
        return np.zeros(0, np.int8), np.zeros(0, np.int64), False
    # Dva stejné půlbity za sebou leží vždy na hranici bitů -> určují fázi. V jednolitém úvodu
    # (samé stejné bity) se fáze poznat nedá, proto se vezme z prvních takových míst za ním.
    stejne = np.flatnonzero(hb[:-1] == hb[1:])[:200]
    if len(stejne):
        i = int(np.bincount((stejne + 1) % 2, minlength=2).argmax())
    else:
        i = 0
    h = hb.tolist()
    bity, pos = [], []
    stejnych = 0          # kolik posledních bitů má stejnou hodnotu (úvod)
    while i + 1 < n:
        if h[i] != h[i + 1]:
            v = h[i]
            stejnych = stejnych + 1 if bity and bity[-1] == v else 1
            bity.append(v)
            pos.append(i)
            i += 2
        else:
            # posun fáze; byl-li před ním dlouhý jednolitý úvod, četl se v opačné fázi -> obrátit
            if stejnych >= 64:
                for j in range(len(bity) - stejnych, len(bity)):
                    bity[j] ^= 1
            stejnych = 0
            i += 1
    if not bity:
        return np.zeros(0, np.int8), np.zeros(0, np.int64), False
    b = np.array(bity, np.int8)
    zac = b[: min(len(b), 200)]
    obraceno = int(zac.sum()) * 2 < len(zac)
    if obraceno:
        b ^= 1
    return b, hp[np.array(pos)], obraceno


def ramce(bity: np.ndarray, delka: int, kontrola) -> tuple[np.ndarray, np.ndarray]:
    """Pro každou pozici bitu: zda tam začíná platný rámec a jakou má hodnotu.

    `kontrola(W)` dostane okna (n, delka) a vrátí (platny, hodnota).
    """
    if len(bity) < delka:
        return np.zeros(0, bool), np.zeros(0, np.int32)
    W = np.lib.stride_tricks.sliding_window_view(bity, delka)
    return kontrola(W)


def runy_z_pulbitu(urovne: list, T: float) -> tuple[list[int], int]:
    """Úrovně půlbitů (0/1) a pauzy ("pauza", vzorků) -> (délky pulzů, počáteční úroveň).

    Pauza prodlouží aktuální úroveň (na začátku se počítá jako úroveň 0).
    """
    out: list[int] = []
    akt = None
    prvni = 0
    delka = 0.0
    for u in urovne:
        if isinstance(u, tuple):
            if akt is None:
                akt = 0
            delka += u[1]
            continue
        if u == akt:
            delka += T
            continue
        if akt is not None:
            out.append(int(round(delka)))
        else:
            prvni = u
        akt = u
        delka = T
    if akt is not None:
        out.append(int(round(delka)))
    return out, prvni


def hrany_z_jedne_polarity(p: Pulzy, i0: int, i1: int, T: float, uroven: int, zisk: float = 0.3) -> Pulzy:
    """Bifáze s nespolehlivými hranami jedné polarity (pomalý náběh po pásce, posunutý průchod nulou):
    hrany `uroven` se srovnají fázovým závěsem na mřížku půlbitů a hrany opačné polarity se dopočítají.
    Mezi dvěma hranami stejné polarity leží 2–4 půlbity a opačná hrana je vždy uprostřed bitu
    (Manchester má přechod v každém středu bitu): mezera 2 -> +1, 4 -> +2, 3 -> ta z +1/+2, která je středem."""
    sel = np.flatnonzero(p.urovne[i0:i1 + 1] == uroven) + i0
    t = p.hrany[sel].astype(np.float64)
    if len(t) < 50:
        return Pulzy(p.rate, np.zeros(0, np.int64), np.zeros(0, np.int8), p.posun)
    # půlbit podle hran této polarity (odhad z běhů obou polarit zkreslí právě posunuté hrany)
    d = np.diff(t)
    d = d[d < 6 * T]
    if len(d) > 50:
        kandidati = T * np.linspace(0.85, 1.15, 121)
        T = float(min(kandidati, key=lambda h: float(np.abs(d / h - np.round(d / h)).mean())))
    # mřížka: index půlbitu každé hrany (fázový závěs, dlouhá mezera = pauza, závěs začíná znovu)
    g = np.zeros(len(t), np.int64)
    faze = t[0]
    for i in range(1, len(t)):
        d = (t[i] - faze) / T
        k = max(1, int(round(d)))
        if k > 100:
            faze = t[i]
        else:
            faze += k * T + zisk * (d - k) * T
        g[i] = g[i - 1] + k
    mezera = np.diff(g)
    # střed bitu: hrany před mezerou 4 leží ve středu bitu -> jejich parita
    ctyri = g[:-1][mezera == 4]
    stred = int(np.bincount(ctyri % 2, minlength=2).argmax()) if len(ctyri) else 0
    j = np.where(mezera == 3, np.where(g[:-1] % 2 == stred, 2, 1), np.where(mezera >= 4, 2, 1))
    j = np.where(mezera > 100, 1, j)
    druhe = t[:-1] + j * T
    hrany = np.empty(2 * len(t) - 1, np.float64)
    hrany[0::2] = t
    hrany[1::2] = druhe
    urovne = np.empty(len(hrany), np.int8)
    urovne[0::2] = uroven
    urovne[1::2] = -uroven
    return Pulzy(p.rate, np.rint(hrany).astype(np.int64), urovne, p.posun)
