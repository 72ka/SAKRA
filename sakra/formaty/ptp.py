"""PTP (PMD 85 Tape Package, emulátor RM-TEAM): posloupnost bloků, každý uvozený délkou (2 B, LE)."""
from __future__ import annotations

import struct
from pathlib import Path


def zapis(cesta: Path, bloky: list[bytes]) -> None:
    Path(cesta).write_bytes(b"".join(struct.pack("<H", len(b)) + bytes(b) for b in bloky))


def nacti(cesta: Path) -> list[bytes]:
    d = Path(cesta).read_bytes()
    out, p = [], 0
    while p + 2 <= len(d):
        n = struct.unpack_from("<H", d, p)[0]
        out.append(d[p + 2:p + 2 + n])
        p += 2 + n
    return out
