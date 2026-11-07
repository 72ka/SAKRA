"""Zásuvné moduly platforem. Nová platforma = třída odvozená od Platforma přidaná do VSECHNY."""
from .atari import Atari
from .commodore import Commodore64
from .fsk import MSX, Acorn
from .iq151 import IQ151
from .ondra import OndraTesla, OndraViLi, Sapi1
from .oric import Oric
from .pmd import PMD85, Mato
from .potas import POTAS
from .pwm import CPC, AtariT2K, Turbo
from .sharp import SharpMZ
from .sms import SMS
from .sord import SordM5
from .zaklad import Kontext, Platforma
from .zx import ZXSpectrum
from .zx81 import ZX81

VSECHNY: list[Platforma] = sorted([
    OndraTesla(), OndraViLi(), Sapi1(), ZXSpectrum(), Turbo(), ZX81(), PMD85(), Mato(), IQ151(),
    Commodore64(), MSX(), Acorn(), Oric(), Atari(), AtariT2K(), CPC(), SharpMZ(), SMS(), POTAS(), SordM5(),
], key=lambda p: p.poradi)

# platformy, které lze ručně přiřadit nerozpoznanému úseku (uloží se jako přesný záznam pulzů CSW)
RUCNI = ["IQ 151", "PMD 85", "Maťo", "SAPI-1", "PMI-80", "ŠMS VÚVT", "POTAS", "Ondra SPO 186", "ZX Spectrum", "ZX81", "Commodore 64",
         "Commodore C16/Plus4", "Atari 8bit", "MSX", "Amstrad CPC", "BBC Micro / Acorn Electron", "Sharp MZ-700/800",
         "Oric", "Sord m5", "jiná"]


# počítače, pro které jde kazetu zpracovat jen jejich dekodéry (volba „pro jakou platformu je kazeta“)
POCITACE: list[str] = list(dict.fromkeys(p.pocitac for p in VSECHNY))


def dekodery(pocitac: str = "") -> list[Platforma]:
    """Dekodéry pro daný počítač (všechny jeho varianty, např. ZX standard i turbo); prázdný = všechny."""
    return [p for p in VSECHNY if not pocitac or p.pocitac == pocitac] or VSECHNY


def podle_id(id_: str) -> Platforma | None:
    return next((p for p in VSECHNY if p.id == id_), None)


def bloky_pro_zobrazeni(s):
    """Pohled na signál bez změny datových bloků a exportu."""
    pl = podle_id(s.platforma)
    return pl.bloky_pro_zobrazeni(s) if pl else s.bloky


__all__ = ["VSECHNY", "RUCNI", "POCITACE", "Kontext", "Platforma", "dekodery", "podle_id", "bloky_pro_zobrazeni"]
