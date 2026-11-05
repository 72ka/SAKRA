"""Nastavení aplikace: kde leží, profily pracoviště, složky, import a export.

Kde je nastavení (první platné):
1. proměnná prostředí SAKRA_NASTAVENI = cesta k souboru INI,
2. přenosná instalace: soubor sakra.ini vedle programu (SAKRA.exe, u zdrojáků v kořeni projektu),
3. soubor INI zvolený v Nastavení (v systémovém úložišti je pak jen odkaz na něj),
4. systémové úložiště (Windows registr, macOS plist, Linux ~/.config/HerniArchiv/SAKRA.conf).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings

ORGANIZACE, APLIKACE = "HerniArchiv", "SAKRA"
PROMENNA = "SAKRA_NASTAVENI"
PRENOSNY = "sakra.ini"
ODKAZ = "soubor_nastaveni"           # v systémovém úložišti: cesta k vlastnímu souboru INI
PAMATOVAT = "slozky/pamatovat"       # dialogy si pamatují naposledy použitou složku
VYCHOZI_PROFIL = "profil/vychozi"
POLE_PROFILU = ["tape_deck", "tape_deck_model", "sound_card", "di_box", "autor"]
NEEXPORTOVAT = {ODKAZ, "okno/geometrie"}      # vázané na tento počítač / binární
# složky: klíč nastavení, popis (překládá GUI)
SLOZKY = [
    ("slozka", "Nahrávky a projekty (kde hledat)"),
    ("archiv", "Archivní balíčky (kam ukládat)"),
    ("nahravani/slozka", "Nahrávky z magnetofonu"),
    ("kamera/slozka", "Fotky z kamery"),
    ("davky/vystup", "Výstup dávek"),
    ("davky/sledovana", "Sledovaná složka dávek"),
    ("mezipamet/slozka", "Uložené analýzy"),
]


def _koren() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def prenosny_soubor() -> Path:
    """sakra.ini vedle programu; u přenosné verze pro Windows (zdroje v app\\) i vedle SAKRA.bat."""
    kandidati = [_koren() / PRENOSNY]
    if not getattr(sys, "frozen", False) and (_koren().parent / "SAKRA.bat").exists():
        kandidati.insert(0, _koren().parent / PRENOSNY)
    return next((k for k in kandidati if k.exists()), kandidati[0])


def _systemove() -> QSettings:
    return QSettings(ORGANIZACE, APLIKACE)


def umisteni() -> tuple[str, str]:
    """(druh, cesta): druh env / prenosne / soubor / system."""
    env = os.environ.get(PROMENNA, "")
    if env:
        return "env", env
    if prenosny_soubor().exists():
        return "prenosne", str(prenosny_soubor())
    odkaz = _systemove().value(ODKAZ, "") or ""
    if odkaz:
        return "soubor", str(odkaz)
    return "system", _systemove().fileName()


def nastaveni() -> QSettings:
    druh, cesta = umisteni()
    if druh == "system":
        return _systemove()
    return QSettings(cesta, QSettings.Format.IniFormat)


def _hodnoty(s: QSettings) -> dict:
    return {k: s.value(k) for k in s.allKeys() if k not in NEEXPORTOVAT}


def presun(cil: str | Path | None) -> None:
    """Přesune nastavení do souboru INI `cil` (None = zpět do systémového úložiště); hodnoty se zkopírují."""
    hodnoty = {k: nastaveni().value(k) for k in nastaveni().allKeys() if k != ODKAZ}
    sysn = _systemove()
    if cil is None:
        sysn.remove(ODKAZ)
        for k, v in hodnoty.items():
            sysn.setValue(k, v)
    else:
        cil = Path(cil)
        cil.parent.mkdir(parents=True, exist_ok=True)
        n = QSettings(str(cil), QSettings.Format.IniFormat)
        for k, v in hodnoty.items():
            n.setValue(k, v)
        n.sync()
        sysn.setValue(ODKAZ, str(cil))
    sysn.sync()


# ---------------------------------------------------------------- export / import
def _json_hodnota(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_json_hodnota(x) for x in v]
    return None                                   # QByteArray apod. se nepřenáší


def exportuj(cesta: str | Path) -> int:
    """Celé nastavení (bez vazby na počítač) do JSON; vrací počet položek."""
    h = {k: _json_hodnota(v) for k, v in _hodnoty(nastaveni()).items()}
    h = {k: v for k, v in h.items() if v is not None}
    Path(cesta).write_text(json.dumps({"sakra_nastaveni": 1, "hodnoty": h}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return len(h)


def importuj(cesta: str | Path) -> int:
    """Nastavení z JSON (export nastavení nebo profilů); vrací počet převzatých položek."""
    d = json.loads(Path(cesta).read_text(encoding="utf-8"))
    if "sakra_profily" in d:
        return importuj_profily(cesta)
    if "sakra_nastaveni" not in d or not isinstance(d.get("hodnoty"), dict):
        raise ValueError("Soubor není export nastavení SAKRA")
    n = nastaveni()
    pocet = 0
    for k, v in d["hodnoty"].items():
        if k not in NEEXPORTOVAT:
            n.setValue(k, v)
            pocet += 1
    n.sync()
    return pocet


# ---------------------------------------------------------------- profily pracoviště
def profily() -> dict[str, dict[str, str]]:
    try:
        p = json.loads(nastaveni().value("profily", "{}") or "{}")
        return p if isinstance(p, dict) else {}
    except (TypeError, ValueError):
        return {}


def uloz_profily(p: dict, vychozi: str | None = "") -> None:
    """Uloží profily; `vychozi` "" = beze změny, None = žádný."""
    n = nastaveni()
    n.setValue("profily", json.dumps(p, ensure_ascii=False))
    if vychozi is None or (vychozi and vychozi in p):
        n.setValue(VYCHOZI_PROFIL, vychozi or "")
    if (n.value(VYCHOZI_PROFIL, "") or "") not in p:
        n.setValue(VYCHOZI_PROFIL, "")
    n.sync()


def vychozi_profil() -> str:
    jm = nastaveni().value(VYCHOZI_PROFIL, "") or ""
    return jm if jm in profily() else ""


def pouzij_vychozi_profil(kazeta) -> bool:
    """Doplní prázdné údaje o pracovišti z výchozího profilu; True, když něco doplnil."""
    p = profily().get(vychozi_profil())
    if not p:
        return False
    zmena = False
    for jm in POLE_PROFILU:
        if not getattr(kazeta.digitalizace, jm) and p.get(jm):
            setattr(kazeta.digitalizace, jm, p[jm])
            zmena = True
    return zmena


def zapis_profily(cesta: str | Path, p: dict | None = None, vychozi: str | None = None) -> int:
    """Profily (výchozí: uložené) do JSON pro jiné pracoviště; vrací počet."""
    p = profily() if p is None else p
    vychozi = vychozi_profil() if vychozi is None else vychozi
    Path(cesta).write_text(json.dumps({"sakra_profily": 1, "vychozi": vychozi, "profily": p},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    return len(p)


def precti_profily(cesta: str | Path) -> tuple[dict, str]:
    """(profily, výchozí) ze souboru exportu profilů – nebo z exportu celého nastavení."""
    d = json.loads(Path(cesta).read_text(encoding="utf-8"))
    if isinstance(d, dict) and "sakra_nastaveni" in d:
        h = d.get("hodnoty") or {}
        try:
            d = {"profily": json.loads(h.get("profily") or "{}"), "vychozi": h.get(VYCHOZI_PROFIL, "")}
        except ValueError:
            d = {}
    nove = d.get("profily") if isinstance(d, dict) else None
    if not isinstance(nove, dict):
        raise ValueError("Soubor není export profilů SAKRA")
    out = {str(jm): {k: str(h.get(k, "") or "") for k in POLE_PROFILU} for jm, h in nove.items() if isinstance(h, dict)}
    return out, str(d.get("vychozi") or "")


def importuj_profily(cesta: str | Path) -> int:
    """Přidá profily ze souboru (stejný název se přepíše); výchozí se převezme, jen když žádný není."""
    nove, vychozi = precti_profily(cesta)
    p = profily()
    p.update(nove)
    uloz_profily(p, vychozi if not vychozi_profil() and vychozi in p else "")
    return len(nove)


# ---------------------------------------------------------------- složky
def pamatovat() -> bool:
    return str(nastaveni().value(PAMATOVAT, True)).lower() not in ("false", "0")


def zapamatuj_slozku(klic: str, cesta: str | Path) -> None:
    """Uloží složku použitou v dialogu – jen když si ji aplikace má pamatovat (nebo ještě žádná není)."""
    n = nastaveni()
    if pamatovat() or not n.value(klic, ""):
        n.setValue(klic, str(cesta))
