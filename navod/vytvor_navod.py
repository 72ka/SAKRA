"""Návod SAKRA v PDF: text a snímky obrazovky (navod/obrazky, vytvoří navod/snimky.py) -> sakra/dokumenty.

Spuštění z kořene projektu:  python navod/vytvor_navod.py   (nejdřív případně python navod/snimky.py)
Sazba přes Qt (QTextDocument + QPdfWriter, A4); na každé stránce je patička s autorem a číslem stránky.
"""
from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
KOREN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOREN))

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSizeF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QPageLayout, QPageSize, QPainter, QPdfWriter,  # noqa: E402
                           QPen, QTextDocument)

from sakra import (AKRONYM, AUTOR, KONTAKT, LICENCE, LICENCE_NAVODU, LICENCE_NAVODU_URL, LICENCE_URL, LOGO,  # noqa: E402
                   NAVOD, PREZDIVKA, ROK, WEB, __version__)

OBRAZKY = Path(__file__).resolve().parent / "obrazky"
DPI = 96
STRANA = QSizeF(794, 1123)          # A4 při 96 dpi
OKRAJ_X, OKRAJ_NAHORE, OKRAJ_DOLE = 64, 56, 78
PATA = (f"SAKRA {__version__} – {AKRONYM}",
        f"© {ROK} {AUTOR}, alias {PREZDIVKA}  ·  vyrobeno pro potřeby Herního archivu, {WEB}")


def akronym(pt: float) -> str:
    """Akronym se zvýrazněnými písmeny S-A-K-R-A (velikost zadaná u každého písmene – Qt jinak u tučného
    písma vrátí výchozí velikost)."""
    p = f"<span style='font-size:{pt}pt;font-weight:bold;color:#E39A2B'>"
    return (f"<span style='font-size:{pt}pt'>a </span>{p}S</span><span style='font-size:{pt}pt'>wiss </span>"
            f"{p}A</span><span style='font-size:{pt}pt'>rmy </span>{p}K</span><span style='font-size:{pt}pt'>"
            f"nife for </span>{p}R</span><span style='font-size:{pt}pt'>etrogaming </span>{p}A</span>"
            f"<span style='font-size:{pt}pt'>rchaeologists</span>")

STYL = """
body { font-family: 'DejaVu Sans', 'Segoe UI', Arial, sans-serif; font-size: 10pt; color: #1F2430; }
h1 { font-size: 19pt; color: #1F2430; margin-top: 0; margin-bottom: 10px; }
h2 { font-size: 13pt; color: #B7741A; margin-top: 18px; margin-bottom: 6px; }
h3 { font-size: 11pt; margin-top: 12px; margin-bottom: 4px; }
p { margin-top: 0; margin-bottom: 7px; line-height: 130%; }
li { margin-bottom: 3px; }
.popis { color: #6B7280; font-size: 8.5pt; margin-bottom: 14px; }
.tip { background-color: #FFF3DD; }
.kod { font-family: 'DejaVu Sans Mono', Consolas, monospace; font-size: 8.5pt; background-color: #F2F3F5; }
table.t { border-collapse: collapse; margin-bottom: 10px; }
table.t th { background-color: #F6B26B; text-align: left; padding: 4px; }
table.t td { padding: 4px; border-bottom: 1px solid #E2E4E9; vertical-align: top; }
td.k { white-space: nowrap; font-weight: bold; }
"""


def obr(jmeno: str, popis: str, sirka: int = 666) -> str:
    # výška se musí zadat také – jinak Qt nechá pod zmenšeným obrázkem místo na původní výšku
    from PySide6.QtGui import QImage
    im = QImage(str(OBRAZKY / f"{jmeno}.png"))
    sirka = min(sirka, im.width())
    vyska = round(im.height() * sirka / max(1, im.width()))
    return (f"<p align=center style='line-height:100%'><img src='{jmeno}.png' width={sirka} height={vyska}></p>"
            f"<p class=popis align=center>{popis}</p>")


def tab(radky: list[tuple], hlavicka: tuple | None = None, sirky: tuple | None = None) -> str:
    h = "".join(f"<th>{x}</th>" for x in hlavicka) if hlavicka else ""
    s = ""
    for r in radky:
        s += "<tr>" + "".join(
            f"<td{' class=k' if i == 0 else ''}{f' width={round(100 * sirky[i] / sum(sirky))}%' if sirky else ''}>{x}</td>"
            for i, x in enumerate(r)) + "</tr>"
    return f"<table class=t width='100%' cellspacing=0>{('<tr>' + h + '</tr>') if h else ''}{s}</table>"


def tip(text: str) -> str:
    return f"<table width='100%' cellpadding=8 cellspacing=0><tr><td class=tip>{text}</td></tr></table><p></p>"


def kod(text: str) -> str:
    return f"<table width='100%' cellpadding=6 cellspacing=0><tr><td class=kod>{html.escape(text).replace(chr(10), '<br>')}</td></tr></table><p></p>"


NOVA = "<p style='page-break-before: always'></p>"

# ------------------------------------------------------------------------------------------- kapitoly
KAPITOLY: list[tuple[str, str, bool]] = []
# kapitoly, které začínají na nové stránce (krátké navazují za předchozí)
NA_NOVE_STRANE = {"Co je SAKRA", "Nahrávání z magnetofonu a ladění hlavy", "Průvodce", "Pracovní stůl",
                  "Ruční oprava poškozeného bloku",
                  "Archivní balíček", "Dávkové zpracování", "Podporované počítače"}


def vyska_loga(sirka: int) -> int:
    """Výška loga pro danou šířku (podle poměru stran souboru – v rich textu je nutné zadat obě)."""
    import struct
    w, h = struct.unpack(">II", LOGO.read_bytes()[16:24])          # IHDR v PNG
    return round(sirka * h / w)


def kapitola(nazev: str, obsah: str) -> None:
    KAPITOLY.append((nazev, obsah, nazev in NA_NOVE_STRANE))


kapitola("Co je SAKRA", f"""
<p><span style='font-size:12pt'><b>SAKRA</b> = </span>{akronym(12)}</p>
<p>Švýcarský nožík pro archeology retro her: <b>SAKRA</b> převádí nahrávky audiokazet s programy pro staré počítače do archivní podoby. Z nahrávky strany
kazety najde jednotlivé programy, pozná, pro jaký počítač jsou, přečte je, zkontroluje kontrolní součty a uloží
je ve formátech, které se dají otevřít v emulátorech. K tomu vyplní tabulku metadat v podobě, jakou používá
Herní archiv, a vytvoří protokol digitalizace.</p>
<p>Program vytvořil <b>{AUTOR}</b>, alias <b>{PREZDIVKA}</b>, v roce {ROK} pro potřeby
<b>Herního archivu</b> (<a href='https://{WEB}'>{WEB}</a>).</p>
<h2>Co SAKRA umí</h2>
<ul>
<li>načte nahrávku strany kazety (WAV nebo FLAC, mono i stereo, 16 a 24 bitů i 32 bitů float, 44,1–96 kHz);</li>
<li>rozpozná 19 způsobů záznamu – od Ondry a PMD 85 po ZX Spectrum, Commodore 64 nebo Atari (přehled je
v kapitole „Podporované počítače“);</li>
<li>poškozený blok zkusí přečíst znovu jinak a opraví ho z další kopie téhož programu na kazetě;
když to nejde, umožní opravu ručně přímo na průběhu signálu;</li>
<li>vyplní tabulku metadat (Excel), kterou lze načíst i uložit a doplnit ručně;</li>
<li>vytvoří archivní balíček: programy pro emulátory, výřezy WAV, kopii nahrávky, fotky kazety,
protokol v HTML a PDF a kontrolní součty souborů;</li>
<li>u ZX Spectra spustí program ve vestavěném emulátoru a uloží nahrávací obrazovku i obrazovku po spuštění;</li>
<li>zpracuje i celé dávky kazet najednou a k ruční kontrole nechá jen ty sporné.</li>
</ul>
<h2>Tři režimy</h2>
{tab([("Průvodce", "Šest kroků od nahrávky po archivní balíček. Vhodné pro dobrovolníky a běžnou práci."),
      ("Pracovní stůl", "Podrobné zobrazení: průběh signálu, seznam programů, tabulka metadat, detail programu, "
                        "přehrávání a ruční opravy."),
      ("Dávky", "Fronta mnoha nahrávek, zpracování na pozadí, bezchybné kazety rovnou do archivu.")],
     sirky=(110, 556))}
<p>Mezi režimy se přepíná přepínačem vpravo nahoře nebo v nabídce <b>Zobrazit</b>. Všechny režimy pracují
se stejnou kazetou – co se začne v Průvodci, jde dokončit na Pracovním stole.</p>
""")

kapitola("Instalace a spuštění", """
<h2>Windows</h2>
<p><b>Přenosná verze:</b> rozbalte <b>SAKRA-""" + __version__ + """-windows-x64.zip</b> kamkoli (i na flash disk)
a spusťte <b>SAKRA.bat</b>. Nic se neinstaluje a Python není potřeba (je přibalený). Pro dávky z příkazové řádky
slouží <b>sakra-cli.bat</b>.</p>
<p><b>Instalátor</b> <b>SAKRA-""" + __version__ + """-instalace.exe</b> (sestavuje se ve Windows) volitelně vytvoří
zástupce na ploše a přiřadí projekty <b>.sakra</b>, které se pak otevírají dvojklikem. SAKRA se pak spouští
z nabídky Start, kde je i tento návod.</p>
<h2>Linux (Debian, Ubuntu)</h2>
<p><b>Sestavená aplikace:</b> rozbalte <b>SAKRA-""" + __version__ + """-linux-x86_64.tar.gz</b> a spusťte soubor
<b>SAKRA</b> ve složce SAKRA (příkazová řádka: <b>sakra-cli</b>).</p>
<p><b>Ze zdrojových souborů:</b> nejdřív nainstalujte systémové balíčky pro Python a Qt:</p>
""" + kod("sudo apt install python3 python3-venv libgl1 libegl1 libxkbcommon-x11-0 \\\n"
          "    libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libfontconfig1 alsa-utils") + """
<p>a pak ve složce programu spusťte:</p>
""" + kod("./run.sh") + """
<p>První spuštění si založí vlastní prostředí Pythonu a stáhne potřebné knihovny (asi 100 MB), další spuštění
jsou rychlá. Když přibude nová verze s novými knihovnami, skript je doinstaluje sám.</p>
<p>Ve Windows lze program ze zdrojových souborů spustit souborem <b>run.bat</b> (potřebuje Python 3.11
nebo novější).</p>
""" + tip("<b>Přehrávání zvuku</b> nepotřebuje další knihovny: ve Windows je vestavěné, v Linuxu se použije "
          "pw-play, paplay nebo aplay (balík alsa-utils)."))

kapitola("Než začnete: nahrávka kazety", """
<ul>
<li>Každou stranu kazety nahrajte do <b>samostatného souboru</b> WAV nebo FLAC.</li>
<li>Nahrávejte <b>bez úprav</b> – bez filtrů, normalizace, odšumění a komprese. SAKRA si signál upraví sama
a každá úprava navíc může data poškodit.</li>
<li>Vzorkování 44,1, 48 nebo 96 kHz, 16 nebo 24 bitů, případně 32 bitů float. Stereo nevadí – SAKRA použije
kanál se silnějším signálem.</li>
<li>Soubor pojmenujte <b>inventárním číslem a stranou</b>, např. <b>HH08518 (1).wav</b>,
<b>RH07860 (A).wav</b>, <b>HH08518 strana B.wav</b> nebo <b>HH08518-A.wav</b>. Z názvu se pozná číslo kazety
i strana; jinak je jde nastavit ručně.</li>
<li>Leží-li vedle nahrávek tabulka Excel se stejným inventárním číslem (např. <b>HH08518.xlsx</b>),
v Dávkách se z ní načtou metadata.</li>
</ul>
""" + tip("Nahrajte vždy <b>obě strany</b>. Programy bývají na kazetě vícekrát a poškozený blok často "
          "opraví kopie z druhé strany.") + """
<p>Nahrávat lze i přímo v SAKRA – viz další kapitola.</p>
""")

kapitola("Nahrávání z magnetofonu a ladění hlavy", """
<p>Stranu kazety lze nahrát přímo ze zvukového vstupu počítače (line-in): <b>Soubor → Nahrát z magnetofonu…</b>
(Ctrl+R), nebo v Průvodci v kroku Nahrávka tlačítko <b>Nahrát z magnetofonu…</b>. Nahrávka se uloží jako WAV
s názvem <b>&lt;inventární číslo&gt; (&lt;strana&gt;).wav</b> a pak se s ní pracuje jako s každou jinou.</p>
<h2>Postup</h2>
<ol>
<li>Zvolte vstup, vzorkování (44,1 / 48 / 96 kHz), bitovou hloubku (16 / 24 bitů) a stereo nebo mono.
Vyplňte inventární číslo, stranu a složku. Volby si SAKRA pamatuje.</li>
<li>Pusťte kazetu a stiskněte <b>Sledovat úroveň</b> – nic se neukládá, jen se ukazuje úroveň a ladění hlavy.
Hlasitost nastavte tak, aby špičky sahaly do žluté, nikdy do červené (přebuzení).</li>
<li>Seřiďte hlavu (viz níže).</li>
<li>Přetočte kazetu na začátek, stiskněte <b>● Nahrávat</b> a pusťte magnetofon. Na konci strany
<b>■ Zastavit</b>. Hlásí-li SAKRA přebuzení, snižte úroveň a stranu nahrajte znovu.</li>
<li>Strana se sama přepne na další – otočte kazetu a nahrajte ji stejně. Nakonec <b>Otevřít v SAKRA</b>.</li>
</ol>
<h2>Ladění hlavy (azimut)</h2>
<p>Hlava magnetofonu musí stát přesně kolmo na pásek, jinak se rozmazávají krátké pulzy a čtení je
nespolehlivé. Kazety bývají nahrané na jiném magnetofonu, proto se vyplatí hlavu seřídit podle kazety, kterou
se chystáte nahrát. Při sledování i nahrávání ukazuje SAKRA z posledního půl sekundy zvuku:</p>
""" + tab([("Histogram délek pulzů", "Jak dlouhé jsou půlvlny signálu (0–1500 µs). Hlavní špička je oranžová. "
                                     "Čím užší a vyšší špičky, tím lépe."),
           ("Rozptyl ±%", "Šířka hlavní špičky; v závorce nejlepší dosažená hodnota, aby bylo vidět, zda se "
                          "otáčením šroubku zlepšuje. Dobré čtení mívá do ±3 %."),
           ("Posun kanálů L/R", "U sterea: data jsou na obou stopách stejná, šikmá hlava je časově posune. "
                                "Ideál 0 µs – ukazatel je v zelené zóně (±20 µs), dál žlutý a červený. "
                                "Nesouhlasí-li kanály vůbec (mono magnetofon, prázdná stopa), SAKRA to napíše.")],
          sirky=(150, 516)) + """
<p>Pusťte zaváděcí tón nebo data a jemně otáčejte šroubkem azimutu (bývá vedle hlavy, přístupný otvorem
v krytu kazetového prostoru), až je oranžová špička nejužší a posun kanálů nejblíž 0 µs. Obě měřítka se
obvykle zlepšují současně.</p>
""" + obr("ladeni_spatne", "Šikmá hlava: kanály posunuté o víc než 100 µs (ukazatel červeně vlevo), širší špička.", 520)
    + obr("ladeni_serizeno", "Po seřízení: posun kanálů do 10 µs (ukazatel v zelené zóně), užší špička a menší rozptyl.", 520)
    + obr("ladeni_mono", "Jedna stopa prázdná (mono magnetofon): posun kanálů nejde změřit, ladí se jen "
                         "podle histogramu.", 520) + tip(
    "Na Linuxu potřebuje nahrávání knihovnu <b>libportaudio2</b>, nebo programy <b>parecord</b> "
    "(pulseaudio-utils) či <b>arecord</b> (alsa-utils). Ve Windows a macOS stačí zvuková karta."))

kapitola("Okno aplikace", """
<p>V horní části okna je nabídka a přepínač režimů:</p>
""" + tab([("Soubor", "Nová kazeta, Otevřít nahrávku…, Otevřít projekt…, Uložit projekt, Archivní balíček…, "
                      "Nastavení…, Konec"),
           ("Metadata", "Načíst z Excelu…, Uložit Excel…"),
           ("Zobrazit", "Průvodce, Pracovní stůl, Dávky, Přehrát výběr"),
           ("Nápověda", "Návod (PDF), O aplikaci")], sirky=(110, 556)) + """
<p><b>Projekt</b> (soubor <b>.sakra</b>) uloží celou rozpracovanou kazetu – odkazy na nahrávky, výsledky
dekódování, ručně vyplněné údaje i ruční opravy. Po otevření projektu se pokračuje tam, kde se skončilo,
a archivní balíček z něj jde kdykoli vytvořit znovu.</p>
<p><b>Nápověda → O aplikaci</b> ukáže logo, verzi, autora a odkaz na Herní archiv.</p>
""" + obr("o_aplikaci", "Nápověda → O aplikaci", 400) + """
<p>Okno si pamatuje velikost, polohu i naposledy použitý režim. Všechny části mají posuvníky, takže se okno
vejde i na menší obrazovku.</p>
""")

kapitola("Průvodce", obr("pruvodce1", "Krok 1 – výběr nahrávek. Vlevo kroky, vpravo nápověda ke kroku.") + """
<p>Průvodce vede prací v šesti krocích. Vlevo je seznam kroků (hotové mají zelenou fajfku), uprostřed
obsah kroku a vpravo nápověda s tipy. Tlačítka <b>← Zpět</b> a <b>Pokračovat</b> jsou dole;
na hotový krok se lze vrátit i kliknutím v seznamu.</p>
<h2>1. Nahrávka</h2>
<p>Tlačítkem <b>Vybrat nahrávky…</b> nebo přetažením souborů do okna vyberte nahrávky stran. V tabulce je vidět
strana (lze ji změnit), délka a formát. Inventární číslo se vyplní z názvu souboru.</p>
<p><b>Pro jaký počítač je kazeta?</b> Pod tabulkou vyberte dlaždici počítače, víte-li to, nebo nechte
<b>Automaticky</b>. Ruční volba zpracuje kazetu rychleji – zkusí se jen dekodéry zvoleného počítače (všechny jeho
varianty, např. u ZX Spectra standardní záznam i turbo). Automaticky se hodí, když na kazetě může být víc počítačů
nebo když platformu neznáte. Úsek, který zvolený počítač nepřečte, se uloží jako nerozpoznaný (CSW) – nic se
neztratí a lze ho zpracovat znovu s jinou volbou.</p>
<h2>2. Kazeta</h2>
<p>Údaje o digitalizaci a kazetě pro hlavičku tabulky metadat: magnetofon, zvuková karta, DI-box, autor
digitalizace, výrobce a materiál kazety a další. <b>Profil pracoviště</b> si údaje o vybavení zapamatuje
a příště je vyplní jedním výběrem. Vzorkování a formát se doplní z nahrávky. Sem patří i fotky kazety
a obalu: <b>Přidat fotky…</b> ze souborů, nebo <b>Z kamery…</b> rovnou z připojené kamery (USB webkamera) –
živý náhled, <b>Vyfotit</b> uloží snímek jako „HH08518 foto 1.jpg“ a po zavření se snímky přidají ke kazetě.
Kamera potřebuje doplněk OpenCV (spouštěcí skripty ho instalují samy, jinak
<b>pip install opencv-python-headless</b>).</p>
""" + obr("pruvodce3", "Krok 3 – co SAKRA na pásce našla.") + """
<h2>3. Platforma</h2>
<p>Při přechodu na tento krok proběhne analýza nahrávek. SAKRA ukáže, které počítače na pásce našla
a kolik programů přečetla. Úseky, které nepoznala, si můžete pustit (<b>▶ Poslechnout</b>, nejvýš
20 sekund; tlačítko se během poslechu změní na <b>■ Zastavit</b>) a platformu určit ručně, pokud ji znáte.
Když na pásce žádný program není (šum, řeč, hudba), zvolte <b>žádná data (šum, řeč, hudba…)</b> – úsek se pak
uloží jen jako výřez WAV a nebude se hlásit jako problém.</p>
<h2>4. Programy</h2>
<p>Seznam programů jako tabulka metadat. Doplňte nebo opravte název a vyberte, co program obsahuje
(Hra, Program, Data…). Sloupce s rozbalovacím seznamem nabízejí hodnoty podle vzoru Herního archivu.
Název přečtený z hlavičky zůstává ve sloupci „Název bloku“.</p>
""" + obr("pruvodce5", "Krok 5 – kontrola: barevný okraj ukazuje stav každé položky.") + """
<h2>5. Kontrola</h2>
<p>Všechno, co potřebuje lidské oko: poškozené programy, opravy a nerozpoznané úseky. Každou položku si lze
poslechnout nebo otevřít na Pracovním stole, kde jde poškozený blok opravit ručně.</p>
<h2>6. Uložit do archivu</h2>
<p>Vyberte složku archivu a volby balíčku (viz kapitola „Archivní balíček“) a stiskněte
<b>Vytvořit archivní balíček</b>. Inventární číslo jde doplnit i přímo tady. Volba <b>Zabalit balíček do jednoho
souboru 7z</b> (zapnutá) vytvoří místo složky jediný soubor <i>inventární číslo</i>.7z se stejným obsahem
(komprese LZMA2, otevře ho 7-Zip i jiné archivátory); u dlouhé nahrávky balení chvíli trvá, průběh je vidět
dole. Potom můžete otevřít složku balíčku, pokračovat na Pracovní stůl nebo začít <b>Další kazetu</b>.</p>
""" + obr("pruvodce6", "Krok 6 – vytvoření archivního balíčku."))

kapitola("Pracovní stůl", obr("stul", "Pracovní stůl: vlevo obsah kazety, uprostřed přehled kazety, detail strany, "
                                      "pulzy a histogram délek, vpravo vybraný soubor s bloky dat.") + """
<p>Pracovní stůl ukazuje všechno, co SAKRA o kazetě ví. Nahrávku otevřete v nabídce <b>Soubor → Otevřít
nahrávku…</b> (Ctrl+O); vybrat lze obě strany najednou.</p>
<h2>Části okna</h2>
""" + tab([("Obsah kazety (vlevo)", "Strom stran, programů a jejich bloků se stavem. Kliknutí vybere program "
                                "nebo blok. Pod stromem <b>Platformy na pásce</b>: kolik programů pro který počítač "
                                "SAKRA našla a kolik z nich je v pořádku."),
           ("Lišta", "Nová kazeta, otevření a uložení, Archivní balíček, načtení a uložení Excelu; vpravo "
                     "Kanál a Polarita zobrazené strany."),
           ("Přehled kazety", "Všechny strany pod sebou, barevně podle počítače, šedě nerozpoznané úseky. U stereo "
                              "nahrávky jsou vidět obě stopy (L a P), nezpracovaná stopa je celá šedá. Rámeček "
                              "ukazuje úsek, který je zobrazený níže v detailu strany. Kliknutí do přehledu přejde "
                              "na dané místo (a vybere program, který tam je)."),
           ("Strana", "Detailní průběh signálu zobrazené strany; v nadpisu časy zobrazeného úseku a vybraný "
                      "program, vpravo rychlost pásky a formát nahrávky. Nad průběhem volba strany, "
                      "Celá strana, Přehrát, Zastavit a Ruční úprava."),
           ("Pulzy", "Průběh signálu po jednotlivých pulzech kolem místa pod myší (na průběhu strany); bez myši "
                     "kolem místa chyby vybraného programu. Červený rámeček = místo, kde se čtení bloku zastavilo. "
                     "V nadpisu čas a nejčastější délky půlvln."),
           ("Histogram délek", "Jak často se ve zobrazeném úseku vyskytují jednotlivé délky půlvln (µs). Vrcholy "
                               "jsou popsané – každý počítač má svůj podpis, např. ZX Spectrum 244 a 489 µs."),
           ("Obsah pásky", "Tabulka metadat se sloupci jako ve vzoru Herního archivu."),
           ("Kazeta (záložka)", "Hlavička tabulky: digitalizace, inventář, popis kazety, fotky."),
           ("Protokol", "Záznam o tom, co SAKRA dělala (analýza, opravy, uložení)."),
           ("Vybraný soubor (vpravo)", "Údaje o vybraném programu, jeho části, náhled a seznam bloků; dole "
                                       "<b>Bloky dat</b> a tlačítko Uložit tento program…")], sirky=(150, 516)) + """
""" + obr("pulzy", "Pulzy a histogram délek: výpadek signálu v bloku 48 (červený rámeček) a dvě délky půlvln "
                   "záznamu Ondry.") + """
<h2>Platforma kazety</h2>
<p>Při otevření nahrávky nové kazety se SAKRA zeptá, pro jaký počítač kazeta je (dlaždice s ikonami, nebo
<b>Automaticky</b>). Volba je pak v záhlaví <b>Přehledu kazety</b>; její změna zpracuje znovu všechny strany.
Ukládá se s projektem. V <b>Dávkách</b> je stejná volba v pravidlech (Platforma kazet). Každý počítač má v celé
aplikaci svou ikonu – v průvodci, ve stromu, v tabulce, v detailu programu i v dávkách.</p>
<h2>Kanál a polarita</h2>
<p>V liště nahoře se pro zobrazenou stranu dá zvolit, jak se má nahrávka číst. Po změně se strana analyzuje znovu
(ruční údaje v tabulce zůstanou, ruční úpravy signálu se zahodí – SAKRA se předem zeptá). Volba se uloží
s projektem.</p>
""" + tab([("Kanál", "<b>Auto</b> – kanál se silnějším signálem (který se použil, je vidět v řádku nad průběhem strany), "
                     "<b>Levý</b>, <b>Pravý</b>, <b>L+P (součet)</b> – obě stopy srovnané o posun a sečtené "
                     "(u sešikmené hlavy nebo slabé nahrávky lepší odstup od šumu). U mono nahrávky je výběr vypnutý."),
           ("Posun P", "Jen u součtu: o kolik je pravá stopa posunutá proti levé (µs, kladně = zpožďuje se). "
                       "<b>auto</b> = změří se z nahrávky. Při ladění šipkami se hned ukazuje zobrazení „Součet L+P“, "
                       "nová analýza proběhne po Enteru."),
           ("Polarita", "<b>Normální</b> – signál, jak je nahraný. <b>Obrácená</b> – signál se před čtením "
                        "převrátí (např. při obráceně zapojeném kabelu nebo magnetofonu, který obrací fázi). "
                        "<b>Auto</b> – čte se normálně; zůstane-li vadný blok, zkusí se i obrácený signál "
                        "a ponechá se lepší výsledek; vyhraje-li obrácená, je to vidět v řádku nad průběhem strany.")],
          sirky=(110, 556)) + """
<p><b>Zobrazit</b> nad časovou osou určuje, co se u stereo nahrávky kreslí (analýzu to nemění): <b>Vstup
analýzy</b> (to, co čtou dekodéry), <b>Levá stopa</b>, <b>Pravá stopa</b>, <b>Součet L+P</b> nebo <b>Obě stopy</b>
pod sebou – po přiblížení na pár milisekund je vidět, jak je pravá stopa posunutá. Bublina u výběru ukazuje
změřený posun a shodu stop; nesouhlasí-li stopy (jiný obsah, jedna prázdná), součet čtení spíš zhorší.</p>
""" + obr("stereo_obe", "Zobrazení Obě stopy: pravá stopa je proti levé zpožděná (sešikmená hlava).", 560) + """
<h2>Bloky dat</h2>
<p>Každý blok vybraného programu je v pravém panelu jedno políčko: <font color='#2EA866'><b>zelené</b></font>
= bez chyby, <font color='#E3A72F'><b>oranžové</b></font> = opravené (z kopie, opakovaným čtením nebo ručně),
<font color='#E04848'><b>červené</b></font> = chyba. Najetí myší ukáže číslo, typ, délku a čas bloku,
kliknutí blok vybere a přiblíží na průběhu strany – odtud se dá rovnou spustit ruční úprava.</p>
<h2>Ovládání časové osy</h2>
""" + tab([("kolečko myši", "přiblížení a oddálení v místě kurzoru"),
           ("tažení myší", "posun"),
           ("kliknutí", "výběr programu v daném místě"),
           ("dvojklik / Celá strana", "zobrazení celé strany"),
           ("Shift + tažení", "výběr úseku"),
           ("pravé tlačítko", "označit výběr jako šum, hudbu nebo řeč; zrušit označení"),
           ("mezerník / ▶ Přehrát", "přehrání vybraného úseku"),
           ("■", "zastavení přehrávání")], sirky=(170, 496)) + """
<p>Při velkém přiblížení jsou vidět jednotlivé vzorky a přechody signálu přes nulu; poškozené bloky jsou
označené červeně.</p>
<h2>Slabá místa signálu</h2>
<p>Nad průběhem strany jsou čárky tam, kde úroveň signálu v bloku klesne proti okolí:
<font color='#F08A24'><b>oranžová</b></font> = slabé čtení (pod 50 %), <font color='#E03A3A'><b>červená</b></font>
= výpadek (pod 25 %, navíc podbarvený). Najetí myší na čárku ukáže úroveň a délku. Čárky pomáhají najít
místo pro ruční úpravu; ne každé slabé místo musí způsobit chybu.</p>
<h2>Šum, hudba a řeč</h2>
<p>Úsek, který není program (šum, hudba, mluvené slovo, znělka), lze označit ručně: vyberte ho na časové ose
<b>Shift + tažením</b> (nebo klikněte na program či úsek) a pravým tlačítkem zvolte <b>Označit jako: šum /
hudba / řeč</b>. Totéž nabízí pravé tlačítko na záznamu v <b>Obsahu kazety</b>. Úsek dostane vlastní řádek
(do balíčku jako výřez WAV) a analýza ho vynechá i při dalším zpracování. Rozpoznané programy se z výběru
odečtou, takže se přeznačí jen dosud nerozpoznaná část. Pravé tlačítko nad označeným úsekem nabídne
<b>Zrušit označení</b>.</p>
""" + obr("osa_vzorky", "Silně přiblížená časová osa: jednotlivé vzorky a přechody přes nulu.") + """
<h2>Tabulka Obsah pásky</h2>
<p>Sloupce odpovídají vzoru Herního archivu. <b>Žlutě podbarvené</b> buňky vyplnila SAKRA, ostatní doplní
člověk. Sloupce s rozbalovacím seznamem nabízejí hodnoty podle komentářů vzoru; ve sloupci Platforma lze
nerozpoznanému úseku určit počítač ručně, nebo zvolit <b>žádná data</b> (případně upřesnit
<b>žádná data – šum / hudba / řeč</b>). Ručně vyplněné údaje
(i určení nerozpoznaných úseků) se při nové analýze zachovají.</p>
""" + obr("karta", "Záložka Kazeta: údaje o digitalizaci, inventář, popis kazety a fotky.", 560) + """
<h2>Detail programu</h2>
<p>Údaje z hlaviček (název, typ, délka, adresa, autostart…), části programu, stav a provedené opravy,
seznam bloků a <b>náhled</b>: u ZX Spectra výpis BASICu a obrazovky, u SAPI-1 text, u ostatních začátek dat
v šestnáctkovém zápisu. V seznamu bloků je u každého bloku <b>kontrolní součet</b> uložený na pásce
a spočtený z přečtených dat (zeleně shoda, červeně rozdíl), u formátů s hlavičkou zvlášť hlavička a data. Tlačítko <b>Uložit tento program…</b> uloží jen vybraný program do zvolené složky.</p>
""")

kapitola("Stavy programů", """
<p>Každý program a úsek má stav, který se ukazuje barevně ve všech režimech i v protokolu:</p>
""" + tab([("<font color='#2EA866'>✓ v pořádku</font>", "Všechny bloky jsou přečtené a kontrolní součty sedí."),
           ("<font color='#D08A10'>✓ opraveno</font>", "Program je v pořádku, ale některý blok bylo potřeba opravit: "
            "opakovaným čtením signálu, z jiné kopie na kazetě nebo ruční úpravou. Co se stalo, je v poznámce."),
           ("<font color='#4A86C8'>~ bez součtu</font>", "Formát nemá kontrolní součet (MSX, ZX81, Oric); úplnost "
            "je ověřená jen délkou a strukturou."),
           ("<font color='#E04848'>✗ chyba</font>", "Některý blok se nepodařilo přečíst, nebo program není celý "
            "(například nahrávka končí uprostřed dat)."),
           ("<font color='#8A93A3'>? nerozpoznáno</font>", "Úsek signálu, který SAKRA nepřiřadila žádnému počítači. "
            "Uloží se jako přesný záznam pulzů (CSW) a výřez WAV, takže se nic neztratí."),
           ("<font color='#8A93A3'>♪ žádná data</font>", "Šum, řeč nebo hudba – SAKRA to poznala sama (zvukový "
            "záznam), nebo jste úsek tak označili ve sloupci Platforma. Uloží se jen jako výřez WAV.")],
          sirky=(130, 536)) + tip(
    "Poškozený program často opraví <b>druhá kopie</b> na kazetě – proto nahrávejte obě strany. "
    "Když kopie není, zkuste ruční úpravu (další kapitola)."))

kapitola("Ruční oprava poškozeného bloku", """
<p>Když je blok poškozený výpadkem nebo zákmitem signálu, dá se opravit přímo na průběhu signálu: přidáním
chybějícího přechodu přes nulu nebo odebráním přebývajícího. Po každém kliknutí SAKRA blok znovu přečte
a ukáže, zda už sedí kontrolní součet.</p>
<h2>Postup</h2>
<ol>
<li>Na Pracovním stole vyberte program se stavem <b>✗ chyba</b>.</li>
<li>Stiskněte <b>✎ Ruční úprava</b> nad časovou osou. Objeví se lišta úprav s informací o bloku.</li>
<li>Kolečkem myši přibližte místo chyby tak, aby byly vidět jednotlivé vzorky.</li>
<li><b>Levé tlačítko</b> přidá přechod přes nulu přesně na místo kliknutí, <b>pravé tlačítko</b> odebere
nejbližší přechod (zákmit).</li>
<li>Po každém kliknutí lišta úprav ukáže, zda kontrolní součet bloku sedí. Jakmile sedí, je program
<b>✓ opraveno</b> (ruční úprava signálu, +N/−M přechodů).</li>
<li><b>Hotovo</b> úpravy ukončí. <b>Vrátit úpravy</b> vrátí blok do původního stavu; neúspěšná úprava
se při ukončení vrátí sama.</li>
</ol>
""" + obr("uprava_pred", "Ruční úprava: přiblížené místo chyby, oranžově přechody přes nulu.")
    + obr("uprava_po", "Po přidání chybějícího přechodu: „Kontrolní součet bloku sedí“.") + tip(
    "Ruční úpravou se mění jen data v projektu, nahrávka zůstává beze změny. U opraveného programu se do "
    "balíčku uloží čistý signál a výřez původní nahrávky vedle něj jako „(původní)“."))

kapitola("Náhledy a emulátor ZX Spectra", obr("detail", "Detail programu ZX Spectrum s náhledem.", 420) + """
<p>U programů pro ZX Spectrum ukazuje detail výpis programu v BASICu, obrazovky SCREEN$ a začátek strojového
kódu. Odkazem <b>▶ Spustit v emulátoru</b> se program spustí ve vestavěném emulátoru Spectra 48K (bez okna,
na pozadí) a do náhledu přibude obrazovka po spuštění.</p>
<ul>
<li><b>Nahrávací obrazovka</b> – obrázek, který program ukazuje během nahrávání. Je-li na pásce blok SCREEN$,
použije se přímo on; jinak se vezme snímek z emulátoru, který během nahrávání vydržel nejdéle a vypadá
jako obrázek.</li>
<li><b>Po spuštění</b> – obrazovka 4 sekundy po dokončení nahrávání (bez stisku kláves).</li>
</ul>
<p>Program s běžnými bloky se nahraje rychle (do sekundy). Program s turbozavaděčem se do emulátoru přehraje
jako páska, asi čtyřikrát rychleji než ve skutečnosti – u delší hry to trvá kolem minuty.</p>
<p>Do archivního balíčku se obě obrazovky uloží jako PNG, je-li zapnutá volba <b>Snímky z emulátoru</b>.</p>
""")

kapitola("Archivní balíček", """
<p>Archivní balíček je složka pojmenovaná inventárním číslem se vším, co se z kazety podařilo získat.
Vytvoří se v Průvodci (krok 6), na Pracovním stole přes <b>Soubor → Archivní balíček…</b> (Ctrl+E)
nebo automaticky v Dávkách.</p>
<h2>Volby</h2>
""" + tab([("Složka archivu", "Kam se balíček vytvoří (uvnitř vznikne složka s inventárním číslem)."),
           ("Přiložit bezztrátovou kopii celé nahrávky (FLAC)", "Do podsložky zdroj se uloží celá nahrávka. "
            "Nahrávky ve 32 bitech float se kopírují jako původní WAV."),
           ("WAV programů jako čistý signál", "Výřez WAV každého programu se vytvoří znovu z přečtených dat "
            "jako čistý signál. U opravených programů se to dělá vždy."),
           ("Snímky z emulátoru", "U ZX Spectra uloží nahrávací obrazovku a obrazovku po spuštění.")],
          sirky=(230, 436)) + """
<h2>Obsah balíčku</h2>
""" + kod("HH08518/\n"
          "  HH08518.xlsx               tabulka metadat podle vzoru Herního archivu\n"
          "  HH08518.json               všechna data v strojově čitelné podobě\n"
          "  protokol.html, protokol.pdf\n"
          "  SHA1SUMS                   kontrolní součty všech souborů\n"
          "  1-01 KORAB.csw             program ve formátu pro emulátor (strana-pořadí název)\n"
          "  1-01 KORAB.wav             výřez nahrávky s programem\n"
          "  1-01 KORAB.bin             data programu\n"
          "  2-03 HRA (nahrávací obrazovka).png, 2-03 HRA (po spuštění).png\n"
          "  nerozpoznane/              nerozpoznané úseky (CSW + WAV)\n"
          "  nahledy/                   fotky kazety a obalu\n"
          "  zdroj/HH08518-1.flac       kopie nahrávky strany") + """
<p><b>Protokol</b> shrnuje údaje o kazetě a digitalizaci, fotky a obsah každé strany se stavem programů
a poznámkami; PDF je připravené k tisku.</p>
""")

kapitola("Dávkové zpracování", obr("davky", "Dávky: fronta kazet, filtry podle stavu, vpravo detail a pravidla.")
         + """
<p>Dávky slouží ke zpracování mnoha kazet bez obsluhy. Nahrávky přidejte tlačítkem <b>+ Přidat nahrávky…</b>
nebo <b>+ Přidat složku…</b>; soubory se samy seskupí do kazet podle inventárního čísla v názvu
(<b>HH08518 (1).wav</b> a <b>HH08518 (2).wav</b> jsou jedna kazeta). Leží-li vedle nahrávek Excel se stejným
inventárním číslem, načtou se z něj metadata.</p>
<p><b>▶ Spustit</b> zpracuje frontu na pozadí, <b>Pozastavit</b> ji zastaví po dokončení rozpracované kazety.
Tlačítka filtrů nad tabulkou ukazují počty kazet podle stavu: ve frontě, zpracovává se, ke kontrole, chyba,
hotovo.</p>
<h2>Pravidla dávky</h2>
""" + tab([("Výstup (archiv)", "Složka archivu. Každá zpracovaná kazeta se v ní uloží i jako projekt .sakra "
            "(podsložka projekty)."),
           ("Kazety bez chyb rovnou exportovat", "Bezchybné kazety se hned uloží jako archivní balíček; ostatní "
            "čekají ke kontrole."),
           ("Přiložit kopii nahrávky, čistý signál, snímky", "Stejné volby jako u archivního balíčku."),
           ("Sledovat složku", "Nové nahrávky v zadané složce se zařadí do fronty samy, jakmile se dopíšou.")],
          sirky=(200, 466)) + """
<h2>Kontrola sporných kazet</h2>
<p>Vybraná kazeta ukáže vpravo souhrn. <b>Otevřít na pracovním stole</b> (nebo dvojklik) ji otevře
k opravám; <b>Schválit</b> ji označí jako hotovou a <b>Exportovat schválené</b> pak vytvoří balíčky
všech schválených kazet. <b>Zpracovat znovu</b> kazetu znovu analyzuje.</p>
""")

kapitola("Metadata a Excel", """
<p>Tabulka metadat má přesně rozložení vzoru Herního archivu: hlavička s údaji o digitalizaci a kazetě
a pro každou stranu tabulka obsahu. Technické údaje SAKRA (bloky, chyby, opravy, rychlost pásky) jsou
na zvláštním listu <b>SAKRA</b>.</p>
<ul>
<li><b>Metadata → Uložit Excel…</b> uloží tabulku kdykoli během práce; v balíčku je vždy.</li>
<li><b>Metadata → Načíst z Excelu…</b> převezme ručně vyplněné údaje z existující tabulky. Programy se párují
podle názvu, takže to funguje i po nové analýze.</li>
<li>Údaje vyplněné ručně SAKRA při opakované analýze nepřepíše.</li>
</ul>
""")

kapitola("Nastavení", "<p>Soubor → Nastavení… (Ctrl+,) má čtyři záložky.</p><h2>Vzhled</h2>"
         + obr("nastaveni", "Záložka Vzhled", 480) + tab(
    [("Barvy", "Podle systému, Světlé nebo Tmavé."),
     ("Styl", "Moderní (zaoblené panely, jantarová tlačítka, přepínač režimů jako segmenty) nebo "
              "Klasický (Fusion)."),
     ("Vlastní záhlaví okna", "Jen v moderním stylu: tři barevné tečky místo rámu systému. Velikost okna se pak "
                              "mění úchytem vpravo dole, dvojklik na záhlaví okno zvětší nebo vrátí."),
     ("Jazyk / Language", "Čeština nebo angličtina (English). Výchozí je podle jazyka systému. Výstupy pro archiv "
                          "(Excel podle vzoru, protokol, názvy souborů) zůstávají česky.")],
    sirky=(150, 516)) + "<p>Barvy a styl se změní hned, jazyk po restartu aplikace (SAKRA ho nabídne).</p>"
    """<h2>Profily pracoviště</h2>
<p>Uložené sestavy magnetofonu, převodníku, DI-boxu a autora digitalizace (na kartě kazety je uloží
<b>Uložit jako profil…</b>, sem vede i tlačítko <b>Spravovat…</b>). Profil jde založit, přejmenovat, smazat
a upravit jeho údaje. <b>Výchozí profil</b> (★) se předvyplní do každé nové kazety – v průvodci, na pracovním
stole i v dávkách; doplní jen prázdné údaje, takže to, co přinese Excel, nepřepíše. Na kartě kazety je
u něj „(výchozí)“. <b>Exportovat…</b> a <b>Importovat…</b> přenesou profily mezi pracovišti (soubor JSON;
stejně pojmenovaný profil se přepíše).</p>
""" + obr("nastaveni_profily", "Záložka Profily pracoviště", 480) + """
<h2>Složky</h2>
<p>Kde aplikace hledá nahrávky a projekty a kam ukládá archivní balíčky, nahrávky z magnetofonu, fotky z kamery,
výstup dávek a uložené analýzy. Prázdné pole = výchozí. Je-li zapnuté <b>Pamatovat si naposledy použitou
složku</b>, dialogy si složku po použití zapamatují (jako dosud); vypnuté – dialogy vždy začnou v nastavených
složkách a nemění je.</p>
""" + obr("nastaveni_slozky", "Záložka Složky", 480) + """
<h2>Nastavení a data</h2>
<p><b>Soubor s nastavením</b> ukazuje, kde je nastavení uložené. Výchozí je úložiště systému (Windows registr,
macOS ~/Library/Preferences, Linux ~/.config/HerniArchiv/SAKRA.conf). <b>Uložit do souboru…</b> ho přesune
do zvoleného souboru INI (sdílený nebo zálohovaný disk), <b>Zpět do systému</b> ho vrátí. <b>Přenosná instalace</b>:
leží-li vedle programu (SAKRA.exe, u zdrojáků v kořeni projektu) soubor <b>sakra.ini</b>, nastavení je v něm –
např. SAKRA na USB disku. Cestu jde určit i proměnnou prostředí <b>SAKRA_NASTAVENI</b>.
<b>Exportovat nastavení…</b> uloží vzhled, jazyk, profily, složky a volby dialogů do souboru JSON (záloha,
přenos na jiný počítač), <b>Importovat nastavení…</b> je načte (projeví se po restartu, SAKRA ho nabídne).
<b>Uložené analýzy</b>: hotová analýza strany se ukládá, takže návrat ke kazetě (z dávky, otevření projektu)
je okamžitý; tlačítko je smaže (uvádí počet a velikost).</p>
""" + obr("nastaveni_data", "Záložka Nastavení a data", 480))

kapitola("Klávesové zkratky", tab(
    [("Ctrl+N", "Nová kazeta"), ("Ctrl+O", "Otevřít nahrávku"), ("Ctrl+R", "Nahrát z magnetofonu"),
     ("Ctrl+Shift+O", "Otevřít projekt"),
     ("Ctrl+S", "Uložit projekt"), ("Ctrl+E", "Archivní balíček"), ("Ctrl+,", "Nastavení"),
     ("mezerník", "Přehrát vybraný úsek (na časové ose)"), ("F1", "Tento návod"), ("Ctrl+Q", "Konec")],
    sirky=(150, 516)))

kapitola("Příkazová řádka", """
<p>Kazetu lze zpracovat i bez okna, například ve skriptu. V sestavené aplikaci slouží k tomu program
<b>sakra-cli</b>, ve zdrojových souborech příkaz <b>sakra</b>:</p>
""" + kod('sakra-cli analyzuj "HH08518 (1).wav" "HH08518 (2).wav" --excel HH08518.xlsx --vystup D:\\Archiv') + tab(
    [("--vystup SLOŽKA", "vytvořit archivní balíček"), ("--excel SOUBOR", "načíst metadata z tabulky"),
     ("--inv ČÍSLO", "inventární číslo (jinak z názvu souboru)"),
     ("--bez-zdroje", "do balíčku nekopírovat celou nahrávku"), ("--projekt SOUBOR", "uložit projekt .sakra"),
     ("--version", "verze a autor programu")], sirky=(170, 496)) + """
<p>Výpis ukáže obsah každé strany: časy, platformu, název, typ a stav každého programu.</p>
""")

kapitola("Podporované počítače", tab(
    [("Ondra SPO 186 – Tesla ROM", "CSW + BIN"), ("Ondra SPO 186 – ViLi ROM", "TAP + BIN"),
     ("SAPI-1 – MIKOS", "CSW + TXT (text, BASIC) nebo BIN"),
     ("PMD 85, Didaktik Alfa, Consul 2717", "PTP + BIN"), ("Maťo", "PTP + BIN"),
     ("IQ 151 (standard i Komenium)", "Intel HEX"),
     ("ZX Spectrum (standard i turbo)", "TZX celého programu, TAP (jen standardní bloky), PNG obrazovek"),
     ("ZX81 (ROM i FASTSAVER)", "P"), ("Commodore 64 / VIC-20", "TAP + PRG"), ("MSX", "CAS"),
     ("BBC Micro / Acorn Electron", "UEF + BIN"), ("Atari 8bit (600 Bd)", "CAS + XEX/BAS/BIN"),
     ("Atari 8bit Turbo 2000", "CAS + BIN"), ("Amstrad CPC", "CDT + BIN"), ("Sharp MZ-700/800", "MZF"),
     ("Oric", "TAP"), ("ŠMS VÚVT Žilina", "BIN (Kansas City 300 Bd; kopie na pásce se porovnají)"),
     ("POTAS (ČSLA, VAAZ Brno)", "BIN + TXT (texty EDIS a BASIC v češtině; kopie většinovým hlasováním)"), ("nerozpoznaný úsek", "CSW (přesné pulzy) + WAV")],
    ("Počítač / způsob záznamu", "Formáty v balíčku"), (270, 396)) + """
<p>U ZX Spectra tvoří zavaděč v BASICu a všechny bloky za ním (obrazovka, kód, bloky bez hlavičky, turbo)
jeden program – jeden řádek tabulky a jeden soubor TZX. Nový program začíná hlavičkou typu Program nebo
po pauze delší než 5 sekund.</p>
""")

kapitola("Když něco nejde", tab(
    [("Úsek je „nerozpoznáno“", "Poslechněte si ho. Je-li to šum, řeč nebo hudba, zvolte ve sloupci Platforma "
      "„žádná data“. Znáte-li počítač, určete ho tamtéž. Neurčený úsek je v balíčku uložen jako CSW a WAV."),
     ("Program má chybu", "Nahrajte i druhou stranu (kopie programu blok opraví), zkuste kazetu nahrát znovu "
      "na jiném magnetofonu, případně použijte ruční úpravu."),
     ("Program není celý", "Detail ukáže chybějící části. Nahrávka mohla skončit dřív než data na pásce."),
     ("Nehraje zvuk (Linux)", "Nainstalujte balík alsa-utils nebo pipewire-pulse (pw-play/paplay)."),
     ("Emulátor ZX je pomalý", "Programy s turbozavaděčem se přehrávají jako páska; snímky lze v balíčku vypnout."),
     ("Okno se nevejde na obrazovku", "Okno lze zmenšit, jednotlivé části mají posuvníky; velikost se pamatuje.")],
    sirky=(170, 496)))

TIRAZ = f"""
<p style='page-break-before: always'>&nbsp;</p><p>&nbsp;</p><p>&nbsp;</p><p>&nbsp;</p>
<p align=center style='line-height:100%'><img src='{LOGO.as_uri()}' width=376 height={vyska_loga(376)}></p>
<p><b>SAKRA {__version__}</b> – {akronym(10)}</p>
<p>Digitalizace a archivace audiokazet s programy pro staré počítače.</p>
<p>Autor: <b>{AUTOR}</b>, alias <b>{PREZDIVKA}</b>, {ROK}.</p>
<p>Vyrobeno pro potřeby <b>Herního archivu</b> – <a href='https://{WEB}'>{WEB}</a>.</p>
<p><b>Licence.</b> Program: <a href='{LICENCE_URL}'>{LICENCE}</a> – zdarma pro jakékoli nekomerční použití
(osobní, koníčky, výzkum, studium, archivy, muzea, školy a další neziskové a veřejné instituce); kdo program šíří
nebo upravuje, musí uvádět autora. Tento návod a logo: <a href='{LICENCE_NAVODU_URL}'>{LICENCE_NAVODU}</a>
(uvádějte „Jan Heřman (72ka), SAKRA“). <b>Komerční použití jen s písemným souhlasem autora:</b>
<a href='mailto:{KONTAKT}'>{KONTAKT}</a>. Podrobně v souborech LICENSE a NOTICE.txt.</p>
<p style='color:#6B7280;font-size:8.5pt'>Emulátor ZX Spectra: knihovna zx (Ivan Kosarev, licence MIT); ROM ZX Spectra
© Amstrad, šíření s emulátory povoleno. Rozhraní: Qt for Python (PySide6, LGPL). Archiv 7z: py7zr (LGPL).
Licence všech knihoven: THIRD-PARTY-NOTICES.txt.</p>
"""


# ------------------------------------------------------------------------------------------- sazba
def titulni() -> str:
    return f"""
<p>&nbsp;</p>
<p align=center style='line-height:100%'><img src='{LOGO.as_uri()}' width=560 height={vyska_loga(560)}></p>
<p align=center style='font-size:40pt;font-weight:bold;color:#E39A2B;margin-bottom:0'>SAKRA</p>
<p align=center style='margin-bottom:12px'>{akronym(14)}</p>
<p align=center style='font-size:11pt;color:#6B7280'>Digitalizace a archivace audiokazet s programy pro staré
počítače</p>
<p align=center style='font-size:20pt;font-weight:bold'>Návod k použití</p>
<p align=center style='color:#6B7280'>verze {__version__}</p>
<p>&nbsp;</p><p>&nbsp;</p><p>&nbsp;</p>
<p align=center style='font-size:11pt'>Autor: <b>{AUTOR}</b>, alias <b>{PREZDIVKA}</b>, {ROK}</p>
<p align=center style='font-size:11pt'>Vyrobeno pro potřeby <b>Herního archivu</b><br>
<a href='https://{WEB}'>{WEB}</a></p>
"""


def html_navodu(strany: dict[str, int]) -> str:
    obsah = "".join(
        f"<tr><td width=40 style='color:#B7741A'><b>{i}</b></td><td>{html.escape(n)}</td>"
        f"<td align=right width=50>{strany.get(n, '00')}</td></tr>"
        for i, (n, _, _) in enumerate(KAPITOLY, 1))
    telo = titulni() + NOVA + f"<h1>Obsah</h1><table width='100%' cellpadding=4 cellspacing=0>{obsah}</table>"
    for i, (nazev, text, nova) in enumerate(KAPITOLY, 1):
        telo += (NOVA if nova else "<p>&nbsp;</p>") + f"<h1>{i}. {html.escape(nazev)}</h1>" + text
    telo += TIRAZ
    return f"<html><head><style>{STYL}</style></head><body>{telo}</body></html>"


def sestav(strany: dict[str, int]) -> QTextDocument:
    doc = QTextDocument()
    doc.setDefaultFont(QFont("DejaVu Sans", 10))
    doc.setBaseUrl(QUrl.fromLocalFile(str(OBRAZKY) + "/"))
    doc.setPageSize(QSizeF(STRANA.width() - 2 * OKRAJ_X, STRANA.height() - OKRAJ_NAHORE - OKRAJ_DOLE))
    doc.setDocumentMargin(0)
    doc.setHtml(html_navodu(strany))
    return doc


def strany_kapitol(doc: QTextDocument) -> dict[str, int]:
    vyska = doc.pageSize().height()
    out = {}
    b = doc.begin()
    while b.isValid():
        if b.blockFormat().headingLevel() == 1:
            m = re.match(r"\d+\. (.*)", b.text())
            if m:
                out[m.group(1)] = int(doc.documentLayout().blockBoundingRect(b).top() // vyska) + 1
        b = b.next()
    return out


def main() -> Path:
    app = QGuiApplication.instance() or QGuiApplication(["sakra"])  # noqa: F841
    doc = sestav({})
    doc = sestav(strany_kapitol(doc))                # druhý průchod: čísla stránek v obsahu
    NAVOD.parent.mkdir(parents=True, exist_ok=True)
    w = QPdfWriter(str(NAVOD))
    w.setResolution(DPI)
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter))
    w.setTitle(f"SAKRA – {AKRONYM} – návod k použití")
    w.setAuthor(f"{AUTOR} ({PREZDIVKA})")
    w.setCreator(f"SAKRA {__version__} – pro potřeby Herního archivu ({WEB})")
    p = QPainter(w)
    stran = doc.pageCount()
    vyska = doc.pageSize().height()
    sirka = doc.pageSize().width()
    pismo = QFont("DejaVu Sans")
    pismo.setPointSizeF(7)
    for i in range(stran):
        if i:
            w.newPage()
        p.save()
        p.translate(OKRAJ_X, OKRAJ_NAHORE - i * vyska)
        doc.drawContents(p, QRectF(0, i * vyska, sirka, vyska))
        p.restore()
        y = STRANA.height() - OKRAJ_DOLE + 34
        p.setPen(QPen(QColor("#E39A2B"), 1))
        p.drawLine(QPointF(OKRAJ_X, y - 14), QPointF(STRANA.width() - OKRAJ_X, y - 14))
        p.setPen(QColor("#6B7280"))
        p.setFont(pismo)
        p.drawText(QRectF(OKRAJ_X, y - 10, sirka, 12), Qt.AlignmentFlag.AlignLeft, PATA[0])
        p.drawText(QRectF(OKRAJ_X, y + 1, sirka, 12), Qt.AlignmentFlag.AlignLeft, PATA[1])
        p.drawText(QRectF(OKRAJ_X, y - 10, sirka, 16), Qt.AlignmentFlag.AlignRight, f"{i + 1} / {stran}")
    p.end()
    print(f"{NAVOD} ({stran} stran)")
    return NAVOD


if __name__ == "__main__":
    main()
    os._exit(0)
