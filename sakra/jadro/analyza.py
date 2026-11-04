"""Celý postup zpracování: nahrávka → pulzy → úseky → platforma → dekódování → záznamy."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..platformy import VSECHNY, Kontext, dekodery, podle_id
from ..platformy.zx import sluc_programy
from . import audio
from .model import Kazeta, Soubor, Strana, Zaznam
from .pulzy import Pulzy, Usek, najdi_pulzy, rozdel_na_useky

PRAH_SKORE = 0.55          # od jakého skóre histogramu se zkusí dekodér platformy
MIN_NEROZPOZNANO_S = 0.5   # kratší nerozpoznané úseky (lupnutí) se ignorují
SLOUCIT_MEZERU_S = 2.0     # nerozpoznané úseky blíž než tohle se spojí
DELKY_KAZET = [5, 6, 10, 12, 15, 20, 23, 30, 45, 60]   # minut na stranu


@dataclass
class Oblast:
    """Barevný úsek časové osy."""
    zacatek: float
    konec: float
    platforma: str | None       # id platformy nebo None = nerozpoznáno
    nazev: str = ""


@dataclass
class VysledekStrany:
    strana: Strana
    nahravka: audio.Nahravka
    pulzy: Pulzy
    useky: list[Usek]
    soubory: list[Soubor] = field(default_factory=list)
    oblasti: list[Oblast] = field(default_factory=list)


def _je_audio(h: np.ndarray) -> bool:
    """Data mají délky pulzů soustředěné do několika hodnot; řeč a hudba ne."""
    celkem = h.sum()
    if not celkem:
        return True
    return float(np.sort(h)[-8:].sum() / celkem) < 0.55


KANALY = {"auto": None, "levy": 0, "pravy": 1}
CHYBY_DEKODERU: list[str] = []      # výjimky dekodérů (strana se přesto zpracuje bez nich) – pro protokol
POLARITY = ("auto", "normalni", "obracena")


def _hodnoceni(v: "VysledekStrany") -> tuple[int, int]:
    """Čím víc dobrých bloků a míň vadných, tím líp (pro výběr polarity)."""
    bloky = [b for s in v.soubory for b in s.bloky]
    return sum(b.ok for b in bloky), -sum(not b.ok for b in bloky)


def analyzuj_stranu(cesta: str | Path, cislo: int, prubeh=None, kanal: int | None = None,
                    volba_kanalu: str = "auto", polarita: str = "auto", platforma: str = "") -> VysledekStrany:
    """`volba_kanalu` auto/levy/pravy (nebo přímo `kanal`), `polarita` auto/normalni/obracena.
    `platforma`: počítač, pro který je kazeta (POCITACE) – zkusí se jen jeho dekodéry;
    prázdná = automaticky všechny.
    Auto polarita: čte se normálně; zůstane-li vadný blok (nebo se nenajde nic), zkusí se i obrácený signál
    a ponechá se lepší výsledek."""
    pr = prubeh or (lambda x, t="": None)
    pr(0.0, "Načítám nahrávku")
    if kanal is None:
        kanal = KANALY.get(volba_kanalu)
    nahr = audio.nacti(cesta, kanal=kanal, prubeh=lambda x: pr(0.25 * x, "Načítám nahrávku"))
    if nahr.kanaly == 1:
        volba_kanalu = "auto"
    obracena = polarita == "obracena"
    if obracena:
        nahr.vzorky = -nahr.vzorky
        nahr.obracena = True
    v = _analyzuj_nahravku(nahr, cesta, cislo, lambda x, t="": pr(x if polarita != "auto" else 0.8 * x, t), platforma)
    if polarita == "auto" and (any(not b.ok for s in v.soubory for b in s.bloky)
                               or (not v.soubory and any(z.nerozpoznano and z.typ != "Audio"
                                                         for z in v.strana.zaznamy))):
        obr = dataclasses.replace(nahr, vzorky=-nahr.vzorky, obracena=True)
        v2 = _analyzuj_nahravku(obr, cesta, cislo, lambda x, t="": pr(0.8 + 0.2 * x, "Obrácená polarita: " + t),
                                platforma)
        if _hodnoceni(v2) > _hodnoceni(v):
            v = v2
            obracena = True
    v.strana.volba_kanalu = volba_kanalu
    v.strana.polarita = polarita
    v.strana.signal["polarita_obracena"] = obracena
    return v


def _analyzuj_nahravku(nahr, cesta, cislo: int, pr, platforma: str = "") -> "VysledekStrany":
    pr(0.25, "Hledám pulzy")
    p = najdi_pulzy(nahr.vzorky, nahr.rate)
    useky = rozdel_na_useky(p)
    ktx = Kontext(nahr, p, cislo)
    soubory: list[Soubor] = []
    vybrane = dekodery(platforma)
    for i, pl in enumerate(vybrane):
        pr(0.3 + 0.6 * i / len(vybrane), f"Dekóduji: {pl.nazev}")
        kand = [u for u in useky if pl.skore(u, p.rate) >= PRAH_SKORE]
        if kand:
            try:
                soubory += [s for s in pl.dekoduj(ktx, kand) if any(b.ok for b in s.bloky)]
            except Exception as e:  # noqa: BLE001 – chyba jednoho dekodéru nesmí shodit celou stranu
                import traceback
                CHYBY_DEKODERU.append(f"{pl.nazev}: {type(e).__name__}: {e}")
                traceback.print_exc()
    soubory = _vyres_prekryvy(soubory)
    soubory = sluc_programy(soubory)        # Spectrum: zavaděč + další bloky = jeden program
    soubory.sort(key=lambda s: s.zacatek)
    pr(0.92, "Sestavuji obsah")

    strana = Strana(cislo, str(Path(cesta)), nahr.delka, nahr.vzorkovani_popis, nahr.format_popis, nahr.kanal)
    oblasti = [Oblast(s.zacatek, s.konec, s.platforma, s.nazev) for s in soubory]
    nerozpoznane = _nerozpoznane(useky, soubory)
    oblasti += [Oblast(a, b, None, "audio" if audio_ else "") for a, b, audio_ in nerozpoznane]
    oblasti.sort(key=lambda o: o.zacatek)

    zaznamy = [_zaznam_ze_souboru(s) for s in soubory]
    zaznamy += [Zaznam(cas_od=round(a, 2), cas_do=round(b, 2), typ="Audio" if aud else "Data", platforma="" if aud else "?",
                       nazev="(zvukový záznam)" if aud else "(nerozpoznáno)", nerozpoznano=True)
                for a, b, aud in nerozpoznane]
    zaznamy.sort(key=lambda z: z.cas_od or 0)
    strana.zaznamy = zaznamy
    konec_signalu = max((u.konec for u in useky), default=0.0)
    strana.signal = {"useku": len(useky), "konec_signalu": round(konec_signalu, 2),
                     "rychlost": _median([s.info.get("rychlost") for s in soubory]),
                     "kanalu": nahr.kanaly, "polarita_obracena": False}
    pr(1.0, "Hotovo")
    return VysledekStrany(strana, nahr, p, useky, soubory, oblasti)


def _median(h):
    h = [x for x in h if x]
    return round(float(np.median(h)), 3) if h else None


def _vyres_prekryvy(soubory: list[Soubor]) -> list[Soubor]:
    """Když dvě platformy přečtou totéž místo, vyhraje ta s více správnými bloky."""
    out: list[Soubor] = []
    for s in sorted(soubory, key=lambda s: -sum(b.ok for b in s.bloky)):
        if any(s.zacatek < o.konec and o.zacatek < s.konec and o.platforma != s.platforma for o in out):
            continue
        out.append(s)
    return out


def _nerozpoznane(useky: list[Usek], soubory: list[Soubor]) -> list[tuple[float, float, bool]]:
    kryto = [(s.zacatek - 1.0, s.konec + 0.5) for s in soubory]
    volne = [u for u in useky if not any(a <= u.zacatek and u.konec <= b for a, b in kryto)
             and not any(u.zacatek < b and a < u.konec and (min(b, u.konec) - max(a, u.zacatek)) > 0.8 * u.delka
                         for a, b in kryto)]
    out: list[list] = []
    for u in volne:
        if out and u.zacatek - out[-1][1] < SLOUCIT_MEZERU_S and not any(
                out[-1][1] <= s.zacatek <= u.zacatek for s in soubory):
            out[-1][1] = u.konec
            out[-1][2] = out[-1][2] + u.histogram
        else:
            out.append([u.zacatek, u.konec, u.histogram.copy()])
    return [(a, b, _je_audio(h)) for a, b, h in out if b - a >= MIN_NEROZPOZNANO_S]


def _zaznam_ze_souboru(s: Soubor) -> Zaznam:
    pl = podle_id(s.platforma)
    z = Zaznam(cas_od=round(s.zacatek, 2), cas_do=round(s.konec, 2), typ="Data",
               platforma=pl.nazev if pl else s.platforma, nazev=s.nazev, turbo=pl.turbo(s) if pl else "",
               nazev_bloku=s.nazev_bloku, typ_bloku=s.typ_bloku, soubor=s)
    obnov_navrhy(z)
    return z


def popis_stavu(s: Soubor) -> str:
    """Krátký technický popis pro poznámku a protokol."""
    casti = []
    vadne = [b for b in s.bloky if not b.ok]
    if s.chybi:
        casti.append("chybí blok " + ", ".join(map(str, s.chybi)))
    if vadne:
        casti.append("poškozený blok " + ", ".join(str(b.cislo) if b.cislo is not None else f"v {b.zacatek:.1f} s"
                                                   for b in vadne))
    opr = [f"blok {b.cislo if b.cislo is not None else f'v {b.zacatek:.1f} s'}: {b.oprava}"
           for b in s.bloky if b.oprava]
    if opr:
        casti.append("; ".join(opr))
    if not s.kompletni and not s.chybi and not vadne:
        casti.append("neúplný soubor (chybí hlavička nebo konec)")
    return "; ".join(casti)


def obnov_navrhy(z: Zaznam) -> None:
    """Návrhy hodnot podle dekódování; co už člověk vyplnil, se nepřepisuje."""
    s = z.soubor
    if s is None:
        return
    if not z.funkcni_orig and (not s.ok or s.opraveno):
        z.funkcni_orig = "Audio"
    stav = popis_stavu(s)
    puvodni = [p for p in z.poznamky.split(" | ") if p and not p.startswith("SAKRA:")]
    z.poznamky = " | ".join(puvodni + ([f"SAKRA: {stav}"] if stav else []))


def oprav_kopiemi(vysledky: list[VysledekStrany]) -> None:
    """Oprava poškozených souborů z jiných kopií na téže kazetě (i z druhé strany)."""
    vse = [(v.strana.cislo, s) for v in vysledky for s in v.soubory]
    for pl in VSECHNY:
        pl.sluc_kopie(vse)
    for v in vysledky:
        for z in v.strana.zaznamy:
            if z.soubor is not None:
                obnov_navrhy(z)


# ---- ruční úprava signálu: opakované dekódování jednoho bloku ----

# platforma souboru -> moduly, které ho dekódují (některé platformy jen přeřazují soubory jiného modulu)
DEKODERY = {"sapi1-mikos": ["ondra-tesla"], "acorn": ["msx"], "atari-t2k": ["zx-turbo"], "cpc": ["zx-turbo"],
            "zx-rom": ["zx-rom", "zx-turbo"], "zx-turbo": ["zx-rom", "zx-turbo"]}


class _KontextBezCteni(Kontext):
    """Při ruční úpravě se blok nesmí „opravit“ opakovaným čtením původní nahrávky."""

    def precti_znovu(self, zacatek, konec, rel, stred_us=None):
        return Pulzy(self.pulzy.rate, np.zeros(0, np.int64), np.zeros(0, np.int8))


def znovu_dekoduj_blok(v: VysledekStrany, s: Soubor, b) -> object | None:
    """Dekóduje okolí bloku z (upravených) pulzů strany a vrátí blok na stejném místě, nebo None."""
    p = v.pulzy
    # konec poškozeného bloku bývá zapsaný jen po místo chyby – vezme se celý úsek nahrávky (mezi pauzami)
    od, do = b.zacatek - 1.0, b.konec + 0.5
    for u in v.useky:
        if u.zacatek < b.konec and b.zacatek < u.konec:
            od, do = min(od, u.zacatek - 0.05), max(do, u.konec + 0.05)
    a, c = np.searchsorted(p.hrany, [od * p.rate, do * p.rate])
    kus = Pulzy(p.rate, p.hrany[a:c], p.urovne[a:c], p.posun)
    useky = rozdel_na_useky(kus)
    if not useky:
        return None
    ktx = _KontextBezCteni(v.nahravka, kus, v.strana.cislo)
    kandidati = []
    for pid in DEKODERY.get(s.platforma, [s.platforma]):
        pl = podle_id(pid)
        if pl is None:
            continue
        for f in pl.dekoduj(ktx, useky):
            for nb in f.bloky:
                prekryv = min(nb.konec, b.konec) - max(nb.zacatek, b.zacatek)
                if prekryv > 0.5 * (b.konec - b.zacatek) and (b.cislo is None or nb.cislo in (None, b.cislo)):
                    kandidati.append(nb)
    if not kandidati:
        return None
    return max(kandidati, key=lambda x: (x.ok, -len(x.chybne_bajty), -abs(x.zacatek - b.zacatek)))


def delka_strany_text(vysledky: list[VysledekStrany]) -> str:
    konec = max((v.strana.signal.get("konec_signalu", 0) for v in vysledky), default=0) / 60
    for m in DELKY_KAZET:
        if konec <= m:
            return f"{m} minut"
    return f"{int(np.ceil(konec))} minut"


def doplnit_kazetu(kazeta: Kazeta, vysledky: list[VysledekStrany]) -> None:
    """Vloží výsledky stran do kazety a doplní automatická pole hlavičky."""
    for v in vysledky:
        stara = next((s for s in kazeta.strany if s.cislo == v.strana.cislo), None)
        if stara is not None:
            prenes_rucni(stara, v.strana)
            kazeta.strany.remove(stara)
        kazeta.strany.append(v.strana)
    kazeta.strany.sort(key=lambda s: s.cislo)
    if vysledky:
        n = vysledky[0].nahravka
        kazeta.digitalizace.vzorkovani = kazeta.digitalizace.vzorkovani or n.vzorkovani_popis
        kazeta.digitalizace.format = kazeta.digitalizace.format or n.format_popis
        if not kazeta.inventar.delka_strany:
            kazeta.inventar.delka_strany = delka_strany_text(vysledky)


def _klic_nazvu(s: str) -> str:
    """Název pro porovnání: bez rozsahu adres „<1000-3FFF>“, jen písmena a číslice."""
    s = s.split("<")[0]
    return "".join(c for c in s.upper() if c.isalnum())


def prenes_rucni(stara: Strana, nova: Strana) -> None:
    """Při opakované analýze (nebo po načtení Excelu) zachová ručně vyplněná pole.

    Řádky se párují podle názvu; z více stejných se vezme časově nejbližší (do 60 s).
    """
    volne = list(stara.zaznamy)
    for z in nova.zaznamy:
        if z.nerozpoznano:
            # nerozpoznaný úsek: ruční platforma nebo „žádná data“ podle polohy na pásce
            s = next((s for s in volne if s.nerozpoznano and s.cas_od is not None and z.cas_od is not None
                      and abs(s.cas_od - z.cas_od) < 2.0 and abs((s.cas_do or 0) - (z.cas_do or 0)) < 4.0), None)
            if s is not None:
                volne.remove(s)
                z.typ, z.platforma, z.nazev = s.typ, s.platforma, s.nazev
                for pole in ("obsah", "poznamky", "zvyrazneni"):
                    if getattr(s, pole):
                        setattr(z, pole, getattr(s, pole))
            continue
        k = _klic_nazvu(z.nazev)
        kandidati = [s for s in volne if k and (_klic_nazvu(s.nazev) == k or _klic_nazvu(s.nazev_bloku) == k
                                                 or (_klic_nazvu(s.nazev).startswith(k) and len(k) >= 6))]
        if z.cas_od is not None:
            kandidati = [s for s in kandidati if s.cas_od is None or abs(s.cas_od - z.cas_od) < 60]
            kandidati.sort(key=lambda s: abs((s.cas_od if s.cas_od is not None else 1e9) - z.cas_od))
        if not kandidati:
            continue
        s = kandidati[0]
        volne.remove(s)
        for pole in ("obsah", "funkcni_orig", "funkcni_edit", "turbo", "zvyrazneni"):
            if getattr(s, pole):
                setattr(z, pole, getattr(s, pole))
        rucni = [p for p in s.poznamky.split(" | ") if p and not p.startswith("SAKRA:")]
        if rucni:
            z.poznamky = " | ".join(rucni + [p for p in z.poznamky.split(" | ") if p.startswith("SAKRA:")])
        if s.nazev:
            z.nazev = s.nazev
