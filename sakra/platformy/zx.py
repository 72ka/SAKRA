"""ZX Spectrum (a kompatibilní: Didaktik, Delta…): standardní zavaděč ROM.

Časování v taktech Z80 (3,5 MHz): úvodní tón 2168, synchronizace 667 + 735, bit 0 = 2× 855, bit 1 = 2× 1710.
Blok: příznak (00 hlavička / FF data), data, XOR součet. Hlavička 17 B: typ, jméno 10, délka, param 1, param 2.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from ..formaty import png, tzx
from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import HIST_KROK_US, Pulzy, Usek
from ..jadro.texty import hex_vypis, jmeno, texty
from .zaklad import Kontext, Platforma, pripona

US = 1 / 3.5          # µs na takt
PILOT = 2168 * US     # 619 µs
BIT0 = 855 * US       # 244 µs
BIT1 = 1710 * US      # 489 µs
MIN_PILOT = 300       # nejméně tolik půlvln úvodního tónu
MAX_VYPADEK_PILOTU = 4  # tolik zkreslených půlvln uprostřed úvodního tónu se přemostí
TYPY_HLAVICKY = {0: "Program", 1: "Number array", 2: "Character array", 3: "Bytes"}


def bloky_zx(p: Pulzy, i0: int, i1: int) -> list[Blok]:
    r = np.diff(p.hrany[i0:i1 + 1]) * (1e6 / p.rate)
    je_pilot = (r > 0.75 * PILOT) & (r < 1.3 * PILOT)
    # souvislé řady úvodního tónu
    zmeny = np.flatnonzero(np.diff(np.concatenate(([0], je_pilot.astype(np.int8), [0]))))
    rady: list[list[int]] = []
    for a, b in zip(zmeny[::2], zmeny[1::2]):
        # ojedinělá zkreslená půlvlna tón nepřeruší (jinak by se rozpadl na kousky bez synchronizace);
        # krátké půlvlny (synchronizace, bit 0) ale ano – tam tón opravdu končí
        if rady and a - rady[-1][1] <= MAX_VYPADEK_PILOTU \
                and ((r[rady[-1][1]:a] > 0.6 * PILOT) & (r[rady[-1][1]:a] < 1.6 * PILOT)).all():
            rady[-1][1] = int(b)
        else:
            rady.append([int(a), int(b)])
    out = []
    for a, b in rady:
        if b - a < MIN_PILOT:
            continue
        f = float(np.median(r[a:b])) / PILOT              # rychlost pásky (1.0 = jmenovitá)
        j = b
        if j + 1 >= len(r) or not (150 * f < r[j] + r[j + 1] < 600 * f):
            continue
        j += 2
        bity = []
        b0, b1 = 2 * BIT0 * f, 2 * BIT1 * f              # součet dvou půlvln: 489 vs 977 µs
        while j + 1 < len(r):
            s = r[j] + r[j + 1]
            # jen bity blízko jmenovité délky – rychlejší (turbo) záznam by se jinak četl jako samé nuly
            if 0.65 * b0 < s < 1.35 * b0:
                bity.append(0)
            elif 0.7 * b1 < s < 1.35 * b1:
                bity.append(1)
            else:
                break
            j += 2
        n = len(bity) // 8
        if n < 2:
            continue
        data = np.packbits(np.array(bity[: n * 8], np.uint8)).tobytes()
        x = 0
        for v in data:
            x ^= v
        ok = x == 0
        typ = "hlavička" if data[0] == 0 and n == 19 else "data"
        blok = Blok(p.cas(i0 + a), p.cas(i0 + j), typ, None, data, ok, hrany=(i0 + a, i0 + j),
                    chybne_bajty=[] if ok else list(range(n)))
        blok.info_rychlost = f  # type: ignore[attr-defined]
        out.append(blok)
    return out


# (odečíst plovoucí střed?, práh hystereze) – pořadí zkoušení při opakovaném čtení vadného bloku
CTENI_ZNOVU = ((True, 0.15), (True, 0.1), (True, 0.25), (False, 0.08), (False, 0.25), (True, 0.05), (True, 0.35))


def precti_znovu_zx(ktx: Kontext, b: Blok, konec: float) -> Blok:
    """Vadný blok se přečte znovu z nahrávky (od úvodního tónu po další blok).

    Záznam ze Spectra nemá stejnosměrnou složku: na dlouhých řadách stejných bitů se střed signálu posouvá
    a průchody nulou s hysterezí se ztrácejí (blok se „utrhne“ uprostřed). Pomůže odečíst klouzavý průměr
    přes periodu bitu 1 – ten bitové kmitočty odstraní celé a zbude jen plovoucí nula."""
    f = getattr(b, "info_rychlost", 1.0)
    for stred, rel in CTENI_ZNOVU:
        p2 = ktx.precti_znovu(b.zacatek - 0.05, konec, rel, 2 * BIT1 * f if stred else None)
        if len(p2.hrany) < 2 * MIN_PILOT:
            continue
        for nb in bloky_zx(p2, 0, len(p2.hrany) - 1):
            if nb.ok and abs(nb.zacatek - b.zacatek) < 1.0 and nb.data[0] == b.data[0]:
                nb.oprava = (f"opakované čtení (práh {rel:.0%}" + (", plovoucí střed)" if stred else ")"))
                # indexy hran do pulzů celé strany (časová osa, ruční úpravy)
                a, c = np.searchsorted(ktx.pulzy.hrany, p2.hrany[list(nb.hrany)])
                nb.hrany = (int(a), int(c))
                nb.info_rychlost = getattr(nb, "info_rychlost", f)  # type: ignore[attr-defined]
                return nb
    return b


class ZXSpectrum(Platforma):
    id = "zx-rom"
    pocitac = "ZX Spectrum"
    varianta = ""
    barva = "#E8574A"
    pripona = "tzx"
    poradi = 20

    def skore(self, usek: Usek, rate: int) -> float:
        # každý blok začíná úvodním tónem (≥ 3223 půlvln ~619 µs) – bez něj to ZX ROM není
        h = usek.histogram
        pilot = h[int(0.75 * PILOT / HIST_KROK_US):int(1.3 * PILOT / HIST_KROK_US) + 1].sum()
        return 1.0 if pilot >= MIN_PILOT else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        bloky: list[Blok] = []
        for u in useky:
            bloky += bloky_zx(ktx.pulzy, u.i0, u.i1)
        bloky.sort(key=lambda b: b.zacatek)
        konec_signalu = max((u.konec for u in useky), default=0.0)
        for i, b in enumerate(bloky):
            if not b.ok:
                dalsi = bloky[i + 1].zacatek if i + 1 < len(bloky) else konec_signalu + 0.05
                bloky[i] = precti_znovu_zx(ktx, b, dalsi)
        soubory: list[Soubor] = []
        akt: Soubor | None = None
        for b in bloky:
            if b.typ == "hlavička" and b.ok:
                akt = Soubor(self.id, "", jmeno(b.data[2:12]), TYPY_HLAVICKY.get(b.data[1], "?"))
                akt.bloky.append(b)
                soubory.append(akt)
            elif akt is not None and len(akt.bloky) == 1 and akt.bloky[0].typ == "hlavička" \
                    and b.zacatek - akt.konec < 10:
                akt.bloky.append(b)
                akt = None
            else:
                s = Soubor(self.id, "", "", "Bez hlavičky")
                s.bloky.append(b)
                soubory.append(s)
                akt = None
        rychlosti = [getattr(b, "info_rychlost", 1.0) for b in bloky]
        for s in soubory:
            self.dokonci(s)
            s.info["rychlost"] = round(float(np.median(rychlosti)), 3) if rychlosti else 1.0
        return soubory

    def dokonci(self, s: Soubor) -> None:
        dokonci_program(s)

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        return zapis_program(s, cil)

    def nahled(self, s: Soubor) -> dict:
        return nahled_programu(s)

    def snimky(self, s: Soubor) -> dict:
        return snimky_programu(s)


def snimky_programu(s: Soubor, sekund_po: float = 4.0) -> dict:
    """Spustí program v emulátoru Spectra (výsledek se pamatuje). Viz zx_emulace."""
    if getattr(s, "_emulace", None) is None:
        from . import zx_emulace
        cas = s.info.get("casovani") or [None] * len(s.bloky)
        bloky = [(b.data, c) for b, c in zip(s.bloky, list(cas) + [None] * len(s.bloky)) if b.ok]
        r = zx_emulace.spust([b for b, _ in bloky], [c for _, c in bloky], sekund_po)
        r["sekund_po"] = sekund_po
        s._emulace = r  # type: ignore[attr-defined]
    return s._emulace  # type: ignore[attr-defined]


# =====================================================================  celý program (zavaděč + další bloky)

TAKT = 3.5            # taktů Z80 na µs
MEZERA_PROGRAMU_S = 5.0


def casti_programu(s: Soubor) -> list[dict]:
    """Rozdělí bloky programu na části: hlavička + data, nebo data bez hlavičky."""
    casti: list[dict] = []
    i = 0
    bl = s.bloky
    while i < len(bl):
        b = bl[i]
        if b.typ == "hlavička" and b.ok and len(b.data) == 19:
            typ, delka, p1, p2 = b.data[1], *struct.unpack_from("<HHH", b.data, 12)
            dat = bl[i + 1] if i + 1 < len(bl) and bl[i + 1].typ == "data" else None
            casti.append({"hlavicka": b, "data": dat, "typ": typ, "jmeno": jmeno(b.data[2:12]), "delka": delka,
                          "p1": p1, "p2": p2,
                          "uplna": dat is not None and dat.ok and len(dat.data) - 2 == delka})
            i += 2 if dat is not None else 1
        else:
            casti.append({"hlavicka": None, "data": b, "typ": None, "jmeno": "", "delka": len(b.data) - 2,
                          "uplna": b.ok})
            i += 1
    return casti


def _popis_casti(c: dict) -> str:
    if c["hlavicka"] is None:
        return f"bez hlavičky, {c['delka']} B" + ("" if c["uplna"] else " – chyba")
    t = TYPY_HLAVICKY.get(c["typ"], str(c["typ"]))
    if c["typ"] == 3 and c["delka"] == 6912 and c["p1"] == 16384:
        t = "SCREEN$"
    pop = f"{t} „{c['jmeno']}“, {c['delka']} B"
    if c["typ"] == 3 and t != "SCREEN$":
        pop += f" @ {c['p1']}"
    if c["typ"] == 0 and c["p1"] < 32768:
        pop += f", autostart {c['p1']}"
    if c["data"] is None:
        pop += " – chybí data"
    elif not c["uplna"]:
        pop += " – chyba"
    return pop


def dokonci_program(s: Soubor) -> None:
    casti = casti_programu(s)
    prvni = casti[0] if casti else None
    hl = [c for c in casti if c["hlavicka"] is not None]
    if hl:
        h = hl[0]
        s.nazev_bloku = h["jmeno"]
        s.nazev = h["jmeno"] or "(bez jména)"
        s.typ_bloku = TYPY_HLAVICKY.get(h["typ"], str(h["typ"]))
        s.info.update({"typ": s.typ_bloku, "delka": h["delka"]})
        if h["typ"] == 0:
            s.info.update({"autostart": h["p1"] if h["p1"] < 32768 else None, "delka_programu": h["p2"]})
        elif h["typ"] == 3:
            s.info["adresa"] = h["p1"]
            if h["delka"] == 6912 and h["p1"] == 16384 and len(casti) == 1:
                s.typ_bloku = "Bytes (SCREEN$)"
    else:
        s.nazev = s.nazev or f"(bez hlavičky, {prvni['delka'] if prvni else 0} B)"
        s.typ_bloku = s.typ_bloku or "Bez hlavičky"
    s.kompletni = bool(casti) and all(c["uplna"] for c in casti)
    s.chybi = [i + 2 for i, c in enumerate(casti) if c["hlavicka"] is not None and c["data"] is None]
    if len(casti) > 1:
        s.info["casti"] = [_popis_casti(c) for c in casti]
    data = b"".join(c["data"].data[1:-1] for c in casti if c["data"] is not None and c["data"].ok)
    s.info["delka_dat"] = len(data)
    s.info["texty"] = texty(data)
    s._data = data  # type: ignore[attr-defined]


def sluc_programy(soubory: list[Soubor]) -> list[Soubor]:
    """Na Spectru je program řada bloků: zavaděč v BASICu (hlavička Program + data), pak další bloky
    (obrazovka, kód, bloky bez hlavičky, často už turbo). Nový program začíná hlavičkou typu Program
    nebo po pauze delší než 5 s; jiná platforma mezi bloky program také ukončí."""
    out: list[Soubor] = []
    akt: Soubor | None = None
    for s in sorted(soubory, key=lambda x: x.zacatek):
        if s.platforma not in ("zx-rom", "zx-turbo"):
            out.append(s)
            akt = None
            continue
        if s.platforma == "zx-rom":
            s.info["casovani"] = [None] * len(s.bloky)
        zavadec = s.bloky[0].typ == "hlavička" and s.bloky[0].ok and s.bloky[0].data[1] == 0
        if akt is None or zavadec or s.zacatek - akt.konec > MEZERA_PROGRAMU_S:
            akt = s
            out.append(s)
        else:
            akt.bloky += s.bloky
            akt.info["casovani"] = akt.info.get("casovani", []) + s.info.get("casovani", [None] * len(s.bloky))
            if s.platforma == "zx-turbo":
                akt.platforma = "zx-turbo"
            if "rychlost" in s.info and "rychlost" not in akt.info:
                akt.info["rychlost"] = s.info["rychlost"]
    for s in out:
        if s.platforma in ("zx-rom", "zx-turbo"):
            dokonci_program(s)
    return out


def _casovani_tzx(c: dict | None) -> dict | None:
    if c is None:
        return None
    sync = c.get("sync") or [c.get("nula", 244)] * 2
    return {"pilot": c.get("pilot", 619) * TAKT, "pilot_pocet": c.get("pilot_pocet", 3223),
            "sync1": sync[0] * TAKT, "sync2": (sync[1] if len(sync) > 1 else sync[0]) * TAKT,
            "nula": c.get("nula", 244) * TAKT, "jedna": c.get("jedna", 489) * TAKT, "pauza_ms": 1000}


def zapis_program(s: Soubor, cil: Path) -> list[Path]:
    """Celý program do jednoho TZX (standardní bloky 10h, turbo 11h s naměřeným časováním);
    TAP jen když jsou všechny bloky standardní; PNG náhled každé obrazovky SCREEN$."""
    cas = s.info.get("casovani") or [None] * len(s.bloky)
    cas = list(cas) + [None] * (len(s.bloky) - len(cas))
    out = [pripona(cil, ".tzx")]
    tzx.zapis_tzx_turbo(out[0], [(b.data, _casovani_tzx(c)) for b, c in zip(s.bloky, cas)],
                        popis=f"SAKRA: {s.nazev}")
    if all(c is None for c in cas):
        out.append(pripona(cil, ".tap"))
        tzx.zapis_tap(out[-1], [b.data for b in s.bloky])
    obrazovky = [d for d in _obrazovky(s)]
    for i, d in enumerate(obrazovky):
        out.append(pripona(cil, " (nahrávací obrazovka).png" if len(obrazovky) == 1
                           else f" (nahrávací obrazovka {i + 1}).png"))
        png.zapis(out[-1], obrazovka_zx(d))
    return out


def zapis_snimky(s: Soubor, cil: Path) -> list[Path]:
    """PNG z emulátoru: obrazovka po spuštění a nahrávací obrazovka (není-li už z bloku SCREEN$)."""
    r = snimky_programu(s)
    out = []
    if r.get("nahravaci") and not _obrazovky(s):
        out.append(pripona(cil, " (nahrávací obrazovka).png"))
        png.zapis(out[-1], obrazovka_zx(r["nahravaci"]))
    out.append(pripona(cil, " (po spuštění).png"))
    png.zapis(out[-1], obrazovka_zx(r["po_spusteni"]))
    return out


def _obrazovky(s: Soubor) -> list[bytes]:
    """Data obrazovek SCREEN$: hlavička Bytes 6912 B @ 16384, nebo blok bez hlavičky s 6912 B."""
    out = []
    for c in casti_programu(s):
        d = c["data"]
        if d is None or not d.ok or len(d.data) != 6914:
            continue
        if c["hlavicka"] is None or (c["typ"] == 3 and c["p1"] == 16384):
            out.append(d.data[1:6913])
    return out


# =====================================================================  náhled: výpis BASICu

TOKENY = {0xA3: "SPECTRUM", 0xA4: "PLAY"}
TOKENY.update(zip(range(0xA5, 0x100), (
    "RND|INKEY$|PI|FN|POINT|SCREEN$|ATTR|AT|TAB|VAL$|CODE|VAL|LEN|SIN|COS|TAN|ASN|ACS|ATN|LN|EXP|INT|SQR|SGN|ABS|"
    "PEEK|IN|USR|STR$|CHR$|NOT|BIN|OR|AND|<=|>=|<>|LINE|THEN|TO|STEP|DEF FN|CAT|FORMAT|MOVE|ERASE|OPEN #|CLOSE #|"
    "MERGE|VERIFY|BEEP|CIRCLE|INK|PAPER|FLASH|BRIGHT|INVERSE|OVER|OUT|LPRINT|LLIST|STOP|READ|DATA|RESTORE|NEW|"
    "BORDER|CONTINUE|DIM|REM|FOR|GO TO|GO SUB|INPUT|LOAD|LIST|LET|PAUSE|NEXT|POKE|PRINT|PLOT|RUN|SAVE|RANDOMIZE|"
    "IF|CLS|DRAW|CLEAR|RETURN|COPY").split("|")))


def basic_vypis(data: bytes, delka: int | None = None, nejvic_radku: int = 400) -> str:
    """Tokenizovaný BASIC Spectra -> text (číslo řádku, příkazy). Čísla v pětibajtovém tvaru se vynechají."""
    d = data[:delka] if delka else data
    radky = []
    i = 0
    while i + 4 <= len(d) and len(radky) < nejvic_radku:
        cislo = d[i] << 8 | d[i + 1]
        n = d[i + 2] | d[i + 3] << 8
        if cislo > 9999:
            break
        telo = d[i + 4:i + 4 + n]
        i += 4 + n
        text = []
        rem = False
        j = 0
        while j < len(telo):
            c = telo[j]
            j += 1
            if c == 0x0D:
                break
            if c == 0x0E and not rem:
                j += 5
            elif c in (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x17, 0x16):
                j += 2 if c in (0x16, 0x17) else 1
            elif c in TOKENY:
                slovo = TOKENY[c]
                if text and not text[-1].endswith(" ") and slovo[0].isalpha():
                    text.append(" ")
                text.append(slovo + (" " if slovo[-1].isalpha() or slovo[-1] == "$" else ""))
                rem = rem or c == 0xEA
            elif c == 0x60:
                text.append("£")
            elif c == 0x7F:
                text.append("©")
            elif 32 <= c < 127:
                text.append(chr(c))
            elif 0x80 <= c <= 0x8F:
                text.append("▒")
            elif 0x90 <= c <= 0xA2:
                text.append(f"[{chr(c - 0x90 + 65)}]")
        radky.append(f"{cislo:4d} " + "".join(text).rstrip())
    return "\n".join(radky)


def nahled_programu(s: Soubor) -> dict:
    """Náhled pro detail programu: obrázky obrazovek, výpis BASICu a začátek kódu každé části."""
    obrazky, texty_ = [], []
    for c in casti_programu(s):
        d = c["data"]
        if d is None or not d.ok:
            continue
        obsah = d.data[1:-1]
        if c["typ"] == 0:
            texty_.append((f"BASIC „{c['jmeno']}“", basic_vypis(obsah, c["p2"] or None)))
        elif len(obsah) == 6912 and (c["hlavicka"] is None or c["p1"] == 16384):
            obrazky.append((f"Nahrávací obrazovka „{c['jmeno'] or 'bez hlavičky'}“", obrazovka_zx(obsah)))
        else:
            adr = c["p1"] if c["typ"] == 3 else 0
            texty_.append((_popis_casti(c), hex_vypis(obsah, adr)))
    r = getattr(s, "_emulace", None)
    if r is not None:
        if r.get("nahravaci") and not _obrazovky(s):
            obrazky.insert(0, ("Nahrávací obrazovka (z emulátoru)", obrazovka_zx(r["nahravaci"])))
        obrazky.append((f"Po spuštění (emulátor, {r['zpusob']}, {r['sekund_po']:g} s po nahrání)",
                        obrazovka_zx(r["po_spusteni"])))
        emulace = "hotovo"
    else:
        from .zx_emulace import k_dispozici
        emulace = k_dispozici() or "lze"
    return {"obrazky": obrazky, "texty": texty_, "emulace": emulace}


PALETA = np.array([[0, 0, 0], [0, 0, 192], [192, 0, 0], [192, 0, 192], [0, 192, 0], [0, 192, 192], [192, 192, 0],
                   [192, 192, 192]], np.uint8)


def obrazovka_zx(d: bytes) -> np.ndarray:
    """SCREEN$ (6144 B bitmapy + 768 B atributů) -> RGB 256×192 (bez blikání)."""
    bit = np.unpackbits(np.frombuffer(d[:6144], np.uint8)).reshape(6144, 8)
    y = np.arange(192)
    adr = ((y & 0xC0) << 5) | ((y & 0x07) << 8) | ((y & 0x38) << 2)      # začátek řádku v bitmapě
    pix = bit[(adr[:, None] + np.arange(32)[None, :])].reshape(192, 256)
    atr = np.frombuffer(d[6144:6912], np.uint8).reshape(24, 32).repeat(8, 0).repeat(8, 1)
    jas = np.where(atr & 0x40, 255 / 192, 1.0)[..., None]
    ink = PALETA[atr & 7] * jas
    paper = PALETA[(atr >> 3) & 7] * jas
    return np.where(pix[..., None] == 1, ink, paper).clip(0, 255).astype(np.uint8)


def pulzy_z_bloku(bloky: list[bytes], rate: int = 44100, rychlost: float = 1.0) -> list[int]:
    """Standardní signál ZX z bloků (pro testy a pro přehrání)."""
    k = rate / 3.5e6 / rychlost
    out: list[float] = [rate * 0.5]
    for b in bloky:
        out += [2168 * k] * (8063 if b[0] < 128 else 3223)
        out += [667 * k, 735 * k]
        for v in b:
            for q in range(7, -1, -1):
                t = (1710 if (v >> q) & 1 else 855) * k
                out += [t, t]
        out.append(945 * k)
        out.append(rate * 1.0)
    return [max(1, int(round(x))) for x in out]
