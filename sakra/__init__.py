"""SAKRA – a Swiss Army Knife for Retrogaming Archaeologists.

Digitalizace a archivace audiokazet s programy pro staré počítače.

Autor: Jan Heřman, alias 72ka, 2026. Vyrobeno pro potřeby Herního archivu (www.herniarchiv.cz)."""
from pathlib import Path

__version__ = "0.3.0a2"          # alpha

AKRONYM = "a Swiss Army Knife for Retrogaming Archaeologists"
_Z = "<b style='color:#E39A2B'>{}</b>"
AKRONYM_HTML = (f"a {_Z.format('S')}wiss {_Z.format('A')}rmy {_Z.format('K')}nife for {_Z.format('R')}etrogaming "
                f"{_Z.format('A')}rchaeologists")
AUTOR = "Jan Heřman"
PREZDIVKA = "72ka"
ROK = 2026
WEB = "www.herniarchiv.cz"
AUTORSTVI = f"© {ROK} {AUTOR}, alias {PREZDIVKA}"
URCENI = f"Vyrobeno pro potřeby Herního archivu ({WEB})"
PODPIS = f"SAKRA {__version__} – {AKRONYM} · {AUTORSTVI} · {URCENI}"

# licence: program PolyForm Noncommercial 1.0.0, návod a logo CC BY-NC 4.0; komerčně jen se souhlasem autora
LICENCE = "PolyForm Noncommercial 1.0.0"
LICENCE_URL = "https://polyformproject.org/licenses/noncommercial/1.0.0"
LICENCE_NAVODU = "CC BY-NC 4.0"
LICENCE_NAVODU_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
KONTAKT = "2hp@seznam.cz"

NAVOD = Path(__file__).resolve().parent / "dokumenty" / "SAKRA-navod.pdf"
LOGO = Path(__file__).resolve().parent / "data" / "logo.png"       # ústřední logo (kazeta + nožík)
IKONA = Path(__file__).resolve().parent / "data" / "ikona.png"     # ikona aplikace (široká, pixelová)
