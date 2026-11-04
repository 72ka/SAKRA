"""Hledání čitelných textů v datech (pomáhá s identifikací programu)."""
from __future__ import annotations

import re

_TEXT = re.compile(rb"[\x20-\x7e]{6,}")


def texty(data: bytes, nejvic: int = 30) -> list[str]:
    out: list[str] = []
    for m in _TEXT.finditer(data):
        s = m.group().decode("ascii").strip()
        # aspoň tři písmena za sebou, ať to není jen řada čísel nebo instrukcí
        if len(s) >= 6 and re.search(r"[A-Za-z]{3}", s) and s not in out:
            out.append(s)
            if len(out) >= nejvic:
                break
    return out


def jmeno(b: bytes, mapa: dict[int, str] | None = None) -> str:
    """Bajty jména -> text; nepísmenné znaky jako '?', mezery a nuly na konci pryč."""
    s = "".join((mapa or {}).get(c, chr(c) if 32 <= c < 127 else "?") for c in b.rstrip(b"\0"))
    return s.rstrip()


def pocet(n: int, jeden: str, dva: str, pet: str) -> str:
    """„1 program“, „3 programy“, „5 programů“; v angličtině tvary podle překladu
    (1 = jednotné číslo, jinak množné)."""
    from ..i18n import tr
    return f"{n} {tr(jeden if n == 1 else dva if 2 <= n <= 4 else pet)}"


def hex_vypis(data: bytes, adresa: int = 0, nejvic: int = 256) -> str:
    """Hexadecimální výpis s ASCII sloupcem (náhled dat)."""
    out = []
    for i in range(0, min(len(data), nejvic), 16):
        kus = data[i:i + 16]
        out.append(f"{(adresa + i) & 0xFFFF:04X}  " + " ".join(f"{b:02X}" for b in kus).ljust(48) + "  "
                   + "".join(chr(b) if 32 <= b < 127 else "." for b in kus))
    if len(data) > nejvic:
        from ..i18n import tr
        out.append(tr("… celkem {0} B").format(len(data)))
    return "\n".join(out)
