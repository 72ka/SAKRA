"""CSW v2 (Compressed Square Wave) – přesný záznam délek pulzů, bez komprese (RLE)."""
from __future__ import annotations

import struct
from pathlib import Path

from .. import __version__

PODPIS = b"Compressed Square Wave\x1a"


def zapis(cesta: Path, rate: int, pulzy, pocatecni_uroven: int = 0) -> None:
    """`pulzy` = délky pulzů ve vzorcích; `pocatecni_uroven` 1 = začíná se vysokou úrovní."""
    data = bytearray()
    for n in pulzy:
        n = int(n)
        if n <= 0:
            continue
        if n < 256:
            data.append(n)
        else:
            data.append(0)
            data += struct.pack("<I", n)
    hlav = PODPIS + bytes([2, 0]) + struct.pack("<II", rate, len(pulzy)) + bytes([1, pocatecni_uroven & 1, 0])
    hlav += f"SAKRA {__version__}".encode("ascii")[:16].ljust(16, b"\0")
    Path(cesta).write_bytes(hlav + bytes(data))


def nacti(cesta: Path) -> tuple[int, list[int], int]:
    """Vrací (vzorkování, délky pulzů, počáteční úroveň). Umí v1 i v2 bez Z-RLE."""
    d = Path(cesta).read_bytes()
    if not d.startswith(PODPIS):
        raise ValueError("není CSW")
    major = d[0x17]
    if major == 1:
        rate = struct.unpack_from("<H", d, 0x19)[0]
        uroven = d[0x1C] & 1
        p = 0x20
    else:
        rate = struct.unpack_from("<I", d, 0x19)[0]
        if d[0x21] != 1:
            raise ValueError("komprimované CSW (Z-RLE) zatím není podporováno")
        uroven = d[0x22] & 1
        p = 0x34 + d[0x23]
    out = []
    while p < len(d):
        n = d[p]
        p += 1
        if n == 0:
            n = struct.unpack_from("<I", d, p)[0]
            p += 4
        out.append(n)
    return rate, out, uroven
