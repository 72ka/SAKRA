"""Popis vzorové tabulky Herního archivu (HH08518.xlsx): rozložení, barvy, nápovědy, povolené hodnoty."""

FONT = "Arial"
VELIKOST = 11
VYSKA_RADKU = 15.75
LIST = "List 1"

SIRKY = {"A": 11.38, "B": 11.38, "C": 5.75, "D": 31.86, "E": 34.36, "F": 20.31, "G": 16.83,
         "H": 17.24, "I": 13.88, "J": 47.44, "K": 14.33, "L": 68.13}

BARVA_DIGITALIZACE = "6D9EEB"     # popisky A2:A9
BARVA_DIGI_HODNOTA = "C9DAF8"     # B8:B9
BARVA_INVENTAR = "8E7CC3"         # popisky D2:D4
BARVA_INV_HODNOTA = "B4A7D6"      # E2:E4
BARVA_POPIS = "B6D7A8"            # popisky D6:D8
BARVA_HLAVICKA = "F6B26B"         # záhlaví tabulky obsahu
BARVA_RADEK = "FCE5CD"            # řádek obsahu
BARVA_ZVYRAZNENI = "F9CB9C"       # zvýrazněný řádek (např. další kopie)

# (řádek, popisek) – hlavička Digitalizace ve sloupci A, hodnota ve B
DIGITALIZACE = [(2, "Tape-deck"), (4, "Sound-card"), (5, "DI-Box"), (6, "Vzorkování"),
                (7, "Formát"), (8, "Datum"), (9, "Autor")]
# Inventář ve sloupci D, hodnota v E
INVENTAR = [(2, "Pův. transakce"), (3, "Verze dumpu"), (4, "Verze metadat")]
POPIS_KAZETY = [(6, "Výrobce"), (7, "Délka strany"), (8, "Materiál")]

PRVNI_OBSAH = 11      # řádek „Obsah (1)“

SLOUPCE = [  # (písmeno, záhlaví, pole modelu)
    ("A", "Čas Od", "cas_od"), ("B", "Čas Do", "cas_do"), ("C", "Typ", "typ"),
    ("D", "Platforma", "platforma"), ("E", "Název", "nazev"), ("F", "Obsah", "obsah"),
    ("G", "Funkční (Orig.)", "funkcni_orig"), ("H", "Funkční (Edit)", "funkcni_edit"),
    ("I", "Turbo", "turbo"), ("J", "Název bloku", "nazev_bloku"), ("K", "Typ Bloku", "typ_bloku"),
    ("L", "Poznámky", "poznamky"),
]

# nápovědy ke sloupcům – texty převzaté ze vzoru (komentáře buněk)
NAPOVEDY = {
    "C": "Sloupeček popisující typ audia nahraného na pásku:\n\nAudio - Jde o běžný zvukový záznam (hudba, "
         "jazyková lekce, záznam z diktafonu atd.).\n\nData - Jedná se o data na nějaký z mikropočítačů.",
    "F": "Sloupeček popisující o jaký typ obsahu (v případě pokud je daný zvuk program) se jedná.\n\nHra - Jedná "
         "se zábavní software.\n\nProgram - Jedná se o žitkový software nebo o nějaký nástroj. Do této skupiny z "
         "pravdlda spadají i výukové programy.\n\nData - Data, která k přečtení či pužití potřebují nějaký jiný "
         "program (např. text do D-TEXTu).\n\nWIP - Jedná se o nějaká rozpracovaná data (např. rozdělaná hra apod.)",
    "G": "Sloupeček popisující, jestli program funguje bez jakékoliv opravy zvukového záznamu nebo zásahu do kódu. "
         "Chyba je většinou blíže popsána v sloupečku \"Poznámky\".\n\nAno - Program je v pořádku\n\nAudio - Je "
         "poškazený samotný zvukový záznam (data jsou nahraná nekonzistetně rychle, v datech jsou výpadky zvuku, "
         "data jsou přehraná jiným zvukem atd.) \n\nCode - Audio se zdá být v pořádku a chyba spočívá v samotném "
         "kódu programu (bug v basicovým programu, chybný převod do turba, chybějící blok programu atd.)\n\n"
         "Audio+Code - Není zcela jasné, co je příčinou poškození",
    "H": "Sloupeček popisující, jestli se data povedlo po opravě zvukového záznamu dostat do funkční podoby.\n\n"
         "Ano - Program se úspěšně spustí a má v Dumpu svůj vlastní .tzx a .wav soubor.\n\nNe - Program z "
         "nějakého důvodu nefunguje a v Dumpu tedy nemá svůj vlastní .tzx a .wav soubor.\n\nNe (DUMP) - Program "
         "z nějakého důvodu nefunguje ale v Dumpu má svůj vlastní .tzx a .wav soubor, pravděpodobně z důvodu, že "
         "jiná verze tohoto programu neexistuje.",
    "I": "Sloupeček popisující jestli je program nahraný v Turbu a pokud ano, tak v jakém.",
}
