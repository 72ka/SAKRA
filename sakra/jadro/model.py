"""Datový model: kazeta → strany → záznamy (řádky tabulky podle vzoru) a dekódované soubory s bloky."""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---- technická vrstva (co SAKRA přečetla z pásky) ----


@dataclass
class Blok:
    zacatek: float                 # s od začátku strany
    konec: float
    typ: str                       # např. "hlavička", "data", "konec", "H", "D"
    cislo: int | None              # číslo bloku / záznamu, je-li v datech
    data: bytes                    # celý blok, jak byl přečten (poškozené bajty = 0)
    ok: bool                       # kontrolní součet v pořádku
    oprava: str = ""               # jak byl blok opraven (prázdné = nebylo třeba)
    chybne_bajty: list[int] = field(default_factory=list)
    hrany: tuple[int, int] = (0, 0)  # rozsah v Pulzy.hrany (pro přesnou kopii signálu)


@dataclass
class Soubor:
    """Jeden program/soubor na pásce (hlavička + data)."""
    platforma: str                 # id modulu, např. "ondra-tesla"
    nazev: str                     # jméno z hlavičky (plné)
    nazev_bloku: str               # jméno, jak je v bloku (může být zkrácené)
    typ_bloku: str                 # např. "BASIC", "Kód", "Program", "Bytes"
    bloky: list[Blok] = field(default_factory=list)
    chybi: list[int] = field(default_factory=list)   # čísla chybějících bloků
    kompletni: bool = False
    info: dict[str, Any] = field(default_factory=dict)  # adresy, délky, texty…
    vystup: dict[str, str] = field(default_factory=dict)  # přípona -> sha1 po exportu
    overeno: bool = True           # False = formát nemá kontrolní součet, úplnost je ověřená jen strukturou

    @property
    def zacatek(self) -> float:
        return self.bloky[0].zacatek if self.bloky else 0.0

    @property
    def konec(self) -> float:
        return self.bloky[-1].konec if self.bloky else 0.0

    @property
    def ok(self) -> bool:
        return self.kompletni and all(b.ok for b in self.bloky)

    @property
    def opraveno(self) -> bool:
        return any(b.oprava for b in self.bloky)

    @property
    def stav(self) -> str:
        if self.ok:
            if self.opraveno:
                return "opraveno"
            return "ok" if self.overeno else "neověřeno"
        return "chyba"


@dataclass
class Signal:
    """Údaje o kvalitě signálu jednoho úseku."""
    rychlost: float = 1.0          # 1.0 = jmenovitá rychlost
    uroven: float = 0.0            # relativní špička 0..1
    obracena_polarita: bool = False


# ---- archivní vrstva (struktura podle vzoru Herního archivu, HH08518.xlsx) ----

TYPY = ["Audio", "Data"]
OBSAHY = ["Hra", "Program", "Data", "WIP"]
FUNKCNI_ORIG = ["Ano", "Audio", "Code", "Audio+Code"]
FUNKCNI_EDIT = ["Ano", "Ne", "Ne (DUMP)"]
TURBA = ["Není v Turbo", "T2K - Kb bloky", "T2K - Nestandardní"]


@dataclass
class Zaznam:
    """Jeden řádek tabulky „Obsah (n)“ – sloupce přesně podle vzoru."""
    cas_od: float | None = None
    cas_do: float | None = None
    typ: str = "Data"
    platforma: str = ""
    nazev: str = ""
    obsah: str = ""
    funkcni_orig: str = ""
    funkcni_edit: str = ""
    turbo: str = ""
    nazev_bloku: str = ""
    typ_bloku: str = ""
    poznamky: str = ""
    zvyrazneni: str = ""           # sloupce (písmena) s tmavší barvou buňky – převzato ze vzoru
    soubor: Soubor | None = None   # technická data (není ve vzoru)
    nerozpoznano: bool = False

    @property
    def stav(self) -> str:
        if self.soubor is not None:
            return self.soubor.stav
        if self.nerozpoznano:
            return "žádná data" if self.typ == "Audio" else "nerozpoznáno"
        return ""


ZADNA_DATA = "žádná data (šum, řeč, hudba…)"     # ruční určení nerozpoznaného úseku: není to program
NAZVY_BEZ_DAT = ("(žádná data)", "(zvukový záznam)")


def urci_platformu(z: Zaznam, text: str) -> None:
    """Ruční určení nerozpoznaného úseku: platforma ze seznamu, „(neznámá)“, nebo žádná data (typ Audio –
    do balíčku jen výřez WAV, ne CSW)."""
    if text == ZADNA_DATA:
        z.typ, z.platforma = "Audio", ""
        if z.nazev in ("", "(nerozpoznáno)"):
            z.nazev = "(žádná data)"
        return
    if z.typ == "Audio":
        z.typ = "Data"
    if z.nazev in NAZVY_BEZ_DAT:
        z.nazev = "(nerozpoznáno)"
    z.platforma = "?" if text in ("", "?", "(neznámá)") else text


@dataclass
class Strana:
    cislo: int                       # 1, 2 (Obsah (1), Obsah (2))
    nahravka: str = ""               # cesta k WAV
    delka: float = 0.0
    vzorkovani: str = ""
    format: str = ""
    kanal: int = 0                   # skutečně použitý kanál (0 = levý)
    volba_kanalu: str = "auto"       # auto (silnější) / levy / pravy
    polarita: str = "auto"           # auto / normalni / obracena
    zaznamy: list[Zaznam] = field(default_factory=list)
    signal: dict[str, Any] = field(default_factory=dict)


@dataclass
class Digitalizace:
    tape_deck: str = ""          # značka (B2 ve vzoru)
    tape_deck_model: str = ""    # model (B3)
    sound_card: str = ""
    di_box: str = ""
    vzorkovani: str = ""
    format: str = ""
    datum: dt.date | None = None
    autor: str = ""


@dataclass
class Inventar:
    cislo: str = ""              # inventární číslo, např. HH08518 (název souboru ve vzoru)
    puv_transakce: str = ""
    verze_dumpu: int = 1
    verze_metadat: dt.date | None = dt.date(2024, 4, 1)
    vyrobce: str = ""
    delka_strany: str = ""
    material: str = ""


@dataclass
class Kazeta:
    inventar: Inventar = field(default_factory=Inventar)
    digitalizace: Digitalizace = field(default_factory=Digitalizace)
    strany: list[Strana] = field(default_factory=list)
    poznamka: str = ""
    fotky: list[str] = field(default_factory=list)     # cesty k fotkám kazety a obalu
    platforma: str = ""          # pro jaký počítač kazeta je (zkusí se jen jeho dekodéry); "" = rozpoznat automaticky

    def strana(self, cislo: int) -> Strana:
        for s in self.strany:
            if s.cislo == cislo:
                return s
        s = Strana(cislo)
        self.strany.append(s)
        self.strany.sort(key=lambda x: x.cislo)
        return s


# ---- serializace do JSON (projekt .sakra a metadata balíčku) ----

def _do_json(o):
    if isinstance(o, np.generic):          # čísla z numpy (např. indexy hran) – JSON je neumí
        return o.item()
    if isinstance(o, bytes):
        return {"__bytes__": o.hex()}
    if isinstance(o, (dt.date, dt.datetime)):
        return {"__date__": o.isoformat()}
    if dataclasses.is_dataclass(o):
        return {f.name: _do_json(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, (list, tuple)):
        return [_do_json(x) for x in o]
    if isinstance(o, dict):
        return {str(k): _do_json(v) for k, v in o.items()}
    return o


def _z_json(typ, d):
    if d is None:
        return None
    if isinstance(d, dict) and "__bytes__" in d:
        return bytes.fromhex(d["__bytes__"])
    if isinstance(d, dict) and "__date__" in d:
        return dt.date.fromisoformat(d["__date__"][:10])
    if isinstance(d, list):
        return [_z_json(typ, x) for x in d]
    if dataclasses.is_dataclass(typ):
        hodnoty = {}
        for f in dataclasses.fields(typ):
            if f.name not in d:
                continue
            hodnoty[f.name] = _z_json(_TYPY_POLI.get((typ.__name__, f.name)), d[f.name])
        return typ(**hodnoty)
    if isinstance(d, dict):
        return {k: _z_json(None, v) for k, v in d.items()}
    return d


_TYPY_POLI = {
    ("Kazeta", "inventar"): Inventar, ("Kazeta", "digitalizace"): Digitalizace,
    ("Kazeta", "strany"): Strana, ("Strana", "zaznamy"): Zaznam,
    ("Zaznam", "soubor"): Soubor, ("Soubor", "bloky"): Blok,
}


def kazeta_do_json(k: Kazeta) -> dict:
    return {"format": "sakra-kazeta", "verze": 1, "kazeta": _do_json(k)}


def kazeta_z_json(d: dict) -> Kazeta:
    k = _z_json(Kazeta, d["kazeta"])
    for s in k.strany:
        for z in s.zaznamy:
            if z.soubor is not None:
                for b in z.soubor.bloky:
                    b.hrany = tuple(b.hrany)
    return k


def cas_text(t: float | None) -> str:
    """Čas ve formátu vzoru mm:ss.cc."""
    if t is None:
        return "-"
    t = max(0.0, t)
    m = int(t // 60)
    return f"{m:02d}:{t - 60 * m:05.2f}"


def cas_z_textu(s) -> float | None:
    if s is None:
        return None
    s = str(s).strip()
    if not s or s == "-":
        return None
    try:
        if ":" in s:
            m, r = s.split(":", 1)
            return int(m) * 60 + float(r.replace(",", "."))
        return float(s.replace(",", "."))
    except ValueError:
        return None
