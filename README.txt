SAKRA – a Swiss Army Knife for Retrogaming Archaeologists
=========================================================
Digitalizace a archivace audiokazet s programy pro staré počítače.
Verze 0.3.0 alpha 2 (0.3.0a2, 2026)
Autor: Jan Heřman, alias 72ka, 2026.
Vyrobeno pro potřeby Herního archivu (www.herniarchiv.cz).

Podrobný návod s obrázky: sakra/dokumenty/SAKRA-navod.pdf (v aplikaci Nápověda → Návod, F1).

Licence: program PolyForm Noncommercial 1.0.0 (LICENSE) – zdarma pro jakékoli nekomerční použití, autora je
třeba uvádět; návod a logo CC BY-NC 4.0 (LICENSE-CC-BY-NC-4.0.txt). Komerční použití jen s písemným souhlasem
autora: 2hp@seznam.cz. Podrobně NOTICE.txt, knihovny třetích stran THIRD-PARTY-NOTICES.txt.

Co umí
------
- Načte nahrávku strany kazety (WAV/FLAC, mono i stereo, 16/24 bit i 32 bit float, 44,1–96 kHz).
- Zeptá se, pro jaký počítač kazeta je (nebo Automaticky): ruční volba zpracuje kazetu rychleji, zkusí se jen
  dekodéry zvoleného počítače. Volba je v průvodci (krok Nahrávka), na pracovním stole (záhlaví Přehledu kazety,
  dialog při otevření nahrávky) a v pravidlech dávky; ukládá se s projektem.
- Ikony platforem (kreslené programem, sakra/gui/ikony.py) v průvodci, stromu, tabulce, detailu i dávkách.
- Najde programy, pozná platformu a dekóduje je:
    Ondra SPO 186 – Tesla ROM (MIKOS)   -> CSW (ověřeno proti vzorovému CSW) + BIN
    Ondra SPO 186 – ViLi ROM            -> TAP (JOndra) + BIN
    SAPI-1 – MIKOS                      -> CSW + TXT (text, BASIC) / BIN         podle sapi2wav
    PMD 85, Didaktik Alfa, Consul 2717  -> PTP (vč. nestandardních bloků) + BIN  podle pmd2ptp
    Maťo                                -> PTP s hlavičkou PMD 85 + BIN          podle matowav2ptp
    IQ 151 (standard i Komenium)        -> Intel HEX (pro emulátor a SD-ROM)     podle iq151kom2hex
    ZX Spectrum (standard i turbo)      -> TZX celého programu: zavaděč v BASICu + všechny další bloky
                                           (obrazovka, kód, bloky bez hlavičky, turbo s naměřeným časováním);
                                           TAP, když jsou všechny bloky standardní;
                                           PNG „(nahrávací obrazovka)“ a „(po spuštění)“ – program se spustí
                                           v emulátoru Spectra 48K (balíček zx, bez okna): standardní bloky se
                                           nahrají rychle přes ROM, turbo se přehraje jako páska (pomalejší)
    ZX81 (ROM i FASTSAVER)              -> P                                     FASTSAVER podle zx81fastwav2p
    Commodore 64 / VIC-20               -> TAP v1 + PRG
    MSX                                 -> CAS
    BBC Micro / Acorn Electron          -> UEF + BIN
    Atari 8bit (standard 600 Bd)        -> CAS + XEX/BAS/BIN
    Atari 8bit Turbo 2000               -> CAS (bloky pwm*) + BIN
    Amstrad CPC                         -> CDT + BIN
    Sharp MZ-700/800                    -> MZF
    Oric (rychlý i pomalý záznam)       -> TAP
    POTAS (ČSLA, VAAZ Brno; synchronní) -> BIN + TXT (texty EDIS, BASIC); kopie většinovým hlasováním
    ŠMS VÚVT Žilina (Kansas City 300 Bd) -> BIN (adresa není na pásce – bývá namluvená; kopie ověří/opraví)
    nerozpoznané úseky                  -> CSW (přesné pulzy) + výřez WAV; platformu jde určit ručně
- Kontroluje součty bloků; poškozený blok zkusí přečíst znovu a opraví ho z jiné kopie na kazetě
  (Ondra, SAPI, PMD 85; C64 a Sharp mají každý blok na pásce dvakrát). Formáty bez součtu
  (MSX, ZX81, Oric) mají stav „bez součtu“ – úplnost je ověřená délkou a strukturou.
- Metadata přesně podle vzoru Herního archivu (HH08518.xlsx): načtení i uložení Excelu,
  ručně vyplněné údaje se při nové analýze zachovají. Technické údaje na listu „SAKRA“.
- Archivní balíček: složka s inventárním číslem, Excel, JSON, protokol (HTML a PDF), fotky kazety,
  kopie nahrávky (FLAC, u 32 bit float původní WAV), soubory programů + WAV, SHA1SUMS.
  U opravených programů je WAV čistý signál a výřez nahrávky leží vedle jako „(původní)“.
  V průvodci se balíček standardně zabalí do jednoho souboru <inventární číslo>.7z (LZMA2, knihovna py7zr);
  volba „Zabalit balíček do jednoho souboru 7z“ v posledním kroku.

Tři režimy (přepínač nahoře)
---------------------------
Průvodce      šest kroků pro dobrovolníky: nahrávka, kazeta, platforma, programy, kontrola, uložení.
Pracovní stůl časová osa s vlnou, strom, tabulka podle vzoru, karta kazety, detail programu.
Dávky         fronta nahrávek (kazety se seskupí podle inventárního čísla), zpracování na pozadí,
              bezchybné rovnou do archivu, sporné ke kontrole; sledovaná složka; Excel se stejným
              inventárním číslem vedle nahrávek se načte jako metadata.

Vzhled a jazyk (Soubor → Nastavení…, Ctrl+,)
--------------------------------------------
Barvy:  podle systému / světlé / tmavé.
Styl:   moderní (zaoblené panely, jantarová tlačítka, přepínač režimů jako segmenty) nebo klasický (Fusion).
        V moderním stylu jde zapnout vlastní záhlaví okna (tři barevné tečky místo rámu systému;
        velikost okna se pak mění úchytem vpravo dole nebo dvojklikem na záhlaví).
Jazyk:  čeština / angličtina (English); projeví se po restartu (aplikace ho nabídne). Výchozí podle jazyka
        systému. Výstupy pro archiv (Excel podle vzoru, protokol, názvy souborů) zůstávají česky.

Spuštění
--------
Windows: dvojklik na run.bat (potřebuje Python 3.11+, nejlépe s nástrojem uv).
Pozn.: PySide6 6.12.0 na Pythonu 3.11 při kreslení ubírá reference na None a aplikace spadne; pro
Python 3.11 se proto instaluje PySide6 < 6.12 (v pyproject.toml), od Pythonu 3.12 to nevadí.
Linux (Debian, Ubuntu): nejdřív systémové balíčky pro Python a Qt:
    sudo apt install python3 python3-venv libgl1 libegl1 libxkbcommon-x11-0 \
        libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libfontconfig1 alsa-utils
a pak ./run.sh (první spuštění založí .venv a stáhne závislosti, asi 100 MB).
Pro vývoj s uv (https://docs.astral.sh/uv/):
    uv sync
    uv run sakra                         grafická aplikace
    uv run sakra analyzuj "HH08518 (2)_44kHz.wav" --excel HH08518.xlsx --vystup D:\Archiv
    uv run sakra analyzuj "HH08518 (2)_44kHz.wav" --platforma "Ondra SPO 186"   jen dekodéry Ondry (rychlejší)
Testy:
    python -m unittest discover -s testy -t .

Přehrávání úseku (mezerník nebo ▶ Přehrát) nepotřebuje další knihovny: ve Windows vestavěný winsound,
v Linuxu pw-play, paplay nebo aplay (balík alsa-utils), na macOS afplay.

Sestavení pro pracovníky archivu (bez Pythonu)
----------------------------------------------
Windows: instalator\sestav_windows.bat -> dist\SAKRA\ (SAKRA.exe, sakra-cli.exe pro dávky)
         a s nainstalovaným Inno Setup 6 i dist\SAKRA-0.3.0a2-instalace.exe
         (nabídka Start, ikona na ploše, otevírání projektů .sakra dvojklikem).
Linux:   instalator/sestav_linux.sh -> dist/SAKRA/ (asi 190 MB)

Automatické sestavení na GitHubu (.github/workflows/sestaveni.yml, GitHub Actions):
  - každý push: testy na Linuxu a Windows,
  - značka verze: git tag v0.3.0a2 && git push origin v0.3.0a2
    -> testy, sestavení (Windows: instalátor + přenosný zip, Linux: tar.gz) a Release na GitHubu
       se soubory ke stažení; alpha/beta/rc verze se označí jako „pre-release“,
  - ručně: záložka Actions -> Sestavení -> Run workflow (soubory jsou u běhu jako „artifacts“).
  Verzi je třeba předem nastavit v sakra/__init__.py a pyproject.toml (stejně jako ve značce).

Ovládání (Pracovní stůl)
------------------------
- Otevřít nahrávku… – strana se pozná z názvu („(1)“, „(2)“, „strana B“, „-A“); lze vybrat obě najednou.
- Nastavení (Ctrl+,): Vzhled; Profily pracoviště (výchozí, přejmenovat, smazat, upravit, import/export JSON);
  Složky (kde hledat, kam ukládat, uložené analýzy; pamatovat si poslední složku ano/ne); Nastavení a data
  (kde je konfigurace: systém / vlastní soubor INI / přenosný sakra.ini vedle programu / proměnná
  SAKRA_NASTAVENI; export a import celého nastavení do JSON; mazání uložených analýz).
- Kanál (Auto / Levý / Pravý / L+P součet) a Polarita (Auto / Normální / Obrácená) v liště nahoře (pro zobrazenou stranu): po změně se strana
  analyzuje znovu, volba se uloží s projektem. Auto polarita při vadném bloku zkusí i obrácený signál.
  L+P sečte obě stopy srovnané o posun pravé proti levé (Posun P v µs, „auto“ = změřit); pomáhá u sešikmené
  hlavy a slabých nahrávek. „Zobrazit“ nad časovou osou kreslí vstup analýzy, levou, pravou stopu, součet
  nebo obě stopy pod sebou (jen zobrazení); bublina ukazuje změřený posun a shodu stop.
- Časová osa: kolečko = přiblížení, tažení = posun, klik = výběr programu, dvojklik = celá strana,
  mezerník = přehrát vybraný úsek. Při velkém přiblížení jsou vidět jednotlivé vzorky a přechody,
  poškozené bloky červeně.
- Ruční označení úseku (šum, hudba, řeč): Shift + tažení na časové ose vybere úsek (nebo klikněte na
  program), pravé tlačítko → „Označit jako: šum / hudba / řeč“. Úsek se hned objeví v obsahu jako vlastní
  řádek (typ Audio, do balíčku jako výřez WAV). Rozpoznané programy se z výběru odečtou (i s rezervou
  1 s na zaváděcí tón), přeznačí se jen nerozpoznaná část; program se označí, jen když na něm leží celý
  výběr (klik na program). Nerozpoznané kusy v označeném úseku zmizí a analýza ho
  vynechá i při „Analyzovat znovu“ a po otevření projektu (uloží se s projektem). Na ose je šrafovaný
  s ✎. Pravé tlačítko nad ním → „Zrušit označení“ (úsek se vrátí jako nerozpoznaný, program v něm najde
  nová analýza). Totéž nabízí pravé tlačítko na záznamu v panelu Obsah kazety (Označit jako… /
  Zrušit označení). Druh lze určit i u nerozpoznaného úseku v Průvodci (krok Platforma) a ve sloupci
  Platforma: „žádná data – šum / hudba / řeč“.
- Slabá místa signálu: nad vlnou čárky tam, kde úroveň v bloku klesne proti okolí (oranžová = slabé čtení
  pod 50 %, červená = výpadek pod 25 %, výpadek je i podbarvený); bublina nad čárkou ukáže úroveň a délku.
  Hodí se k nalezení místa pro ruční úpravu; ne každé slabé místo musí způsobit chybu.
- ✎ Ruční úprava (u programu s vadným blokem): přiblížení zůstane, pokud je pohled uvnitř vadného bloku;
  přibližte kolečkem na jednotlivé vzorky; levé tlačítko
  přidá přechod přes nulu přesně na místo kliknutí, pravé odebere nejbližší
  přechod (zákmit). Po každém kliknutí se blok znovu dekóduje a nad osou se ukáže, zda už sedí kontrolní
  součet; pak je blok „opraven“ (ruční úprava signálu +N/−M přechodů). „Vrátit úpravy“ vrátí původní stav,
  neúspěšná úprava se při ukončení vrátí sama.
- Nahrát z magnetofonu (Soubor → Nahrát z magnetofonu…, Ctrl+R, nebo v Průvodci v kroku Nahrávka):
  strana kazety ze zvukového vstupu rovnou do WAV „<inventární číslo> (<strana>).wav“ (44,1/48/96 kHz,
  16/24 bitů, stereo/mono). Nejdřív „Sledovat úroveň“ (špičky do žluté; červená = přebuzeno, nahrát
  znovu), pak Nahrávat a pustit magnetofon. Po zastavení lze nahrát další stranu; „Otevřít v SAKRA“
  nahrávky zpracuje jako obvykle. Ladění hlavy (azimut) při sledování i nahrávání: histogram délek
  pulzů (oranžová hlavní špička; čím užší, tím lépe), rozptyl ±% s nejlepší dosaženou hodnotou a u sterea
  posun kanálů L/R v µs (zelená zóna kolem 0). Pusťte zaváděcí tón nebo data a šroubkem azimutu hledejte
  nejmenší rozptyl a posun nejblíž 0 µs. Zvukový vstup: knihovna sounddevice (PortAudio, ve Windows a macOS
  přibalené); na Linuxu bez libportaudio2 se použije parecord (pulseaudio-utils) nebo arecord (alsa-utils).
- Uložené analýzy: hotová analýza strany se ukládá (Linux ~/.cache/sakra/analyzy, Windows
  %LOCALAPPDATA%\SAKRA\cache\analyzy, nejvýš 4 GB, nejstarší se mažou), takže návrat ke kazetě z dávky
  nebo otevření projektu je okamžité. Po změně nahrávky, voleb (kanál, polarita, platforma, ručně
  označené úseky) nebo verze SAKRA se analyzuje znovu. Vymazání: Soubor → Nastavení → Uložené analýzy;
  proměnná SAKRA_CACHE = jiná složka, nebo 0 = neukládat.
- Karta kazety: datum digitalizace se navrhne podle času změny souboru nahrávky (u dvou stran starší);
  dnešní datum se ukazuje jen do analýzy a neuloží se, dokud ho nezměníte.
- Tabulka bloků v detailu: sloupec „Součet (pásek / spočteno)“ – kontrolní součet uložený na pásce
  a spočtený z přečtených dat (zeleně shoda, červeně rozdíl), u formátů s hlavičkou zvlášť hlavička a
  data (PMD 85, Maťo, Ondra ViLi, BBC/Acorn CRC-16, Amstrad CPC po segmentech). ZX81, Oric, ŠMS, POTAS
  a MSX kontrolní součet nemají („bez součtu“).
- Detail programu: údaje z hlaviček, části programu, náhled (ZX: výpis BASICu, nahrávací obrazovka,
  odkazem „Spustit v emulátoru“ i obrazovka po spuštění, začátek kódu; SAPI-1: text; ostatní: začátek dat hexadecimálně), bloky a opravy.
- Obsah pásky: sloupce jako ve vzoru; žlutě podbarvené vyplnila SAKRA, ostatní doplní člověk
  (rozbalovací seznamy podle komentářů vzoru, u Platformy i ruční určení nerozpoznaného úseku – včetně
  „žádná data (šum, řeč, hudba…)“: typ Audio, do balíčku jen výřez WAV).
- Přehled kazety: všechny strany, u sterea obě stopy (L/P), nezpracovaná stopa šedě.
- Kazeta: hlavička vzoru; „Profil pracoviště“ si pamatuje magnetofon, převodník, DI-box a autora
  (výchozí profil se předvyplní do každé nové kazety, i v dávkách; správa profilů: tlačítko Spravovat…);
  fotky kazety a obalu – ze souborů (Přidat fotky…) nebo z připojené kamery (Z kamery…: živý náhled,
  Vyfotit uloží „<inventární číslo> foto <n>.jpg“). Kamera potřebuje volitelný doplněk OpenCV
  (run.sh / run.bat ho instalují, jinak pip install opencv-python-headless nebo pip install -e ".[kamera]").
- Načíst z Excelu – převezme ručně vyplněné údaje (páruje se podle názvu programu).

Struktura
---------
sakra/jadro/        načtení zvuku, pulzy, Manchester, sériové rámce, datový model, celý postup analýzy
sakra/platformy/    zásuvné moduly platforem (nová platforma = nová třída v VSECHNY)
sakra/formaty/      CSW, TZX/CDT, TAP, PTP, PNG
sakra/metadata/     Excel podle vzoru (sablona.py = rozložení a nápovědy vzoru)
sakra/balicek.py    archivní balíček a protokol (HTML, PDF)
sakra/gui/          okno aplikace (PySide6): průvodce, pracovní stůl, dávky, přehrávač
sakra/data/         logo (logo.png)
sakra/dokumenty/    návod v PDF (vytvoří ho navod/vytvor_navod.py, včetně snímků obrazovky)
instalator/         PyInstaller (sakra.spec), Inno Setup (sakra.iss), ikona, skripty sestavení
testy/              testy (syntetické nahrávky všech platforem + skutečné nahrávky HH08518 a RH07860)
obsolete/           původní samostatné převodníky J. Heřmana (PMD 85, Maťo, IQ 151, SAPI-1, ZX81) – vzor dekodérů,
                    licence MIT (obsolete/LICENSE)
