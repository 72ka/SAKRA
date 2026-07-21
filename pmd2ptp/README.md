# Převodník PMD 85 kazetových záznamů (SAKRA Project)

Nástroj pro digitalizaci, dekódování, restauraci a analýzu magnetofonových nahrávek z ČSSR osmibitového počítače **PMD 85**.

Skript zpracovává surové soubory `.wav`, provádí emulaci fázové detekce hran signálu, ověřuje integritu bloků pomocí CRC, generuje čisté rekonstruované WAV záznamy pro reálný hardware a exportuje kompletní data do kontejneru **PTP** (PMD 85 formát pro emulátor od RM-Team).

---

## Klíčové vlastnosti

* **Chytrý výběr kanálu**: Při stereo nahrávce automaticky analyzuje obě stopy a vybere silnější/hlasitější kanál (bez degradace způsobené downmixem).
* **Butterworthův pásmový filtr (`-f`)**: Volitelná filtrace (300 Hz – 5 kHz) pro odstranění nízkofrekvenčního síťového brumu a VF šumu.
* **Biphase / Manchester dekódování**: Analyzuje frekvenci a periodu signálu ($T$), detekuje start/stop bity i fázovou polaritu synchronizační posloupnosti.
* **Podpora standardních i nestandardních bloků**: Korektně parsuje hlavičky, datové bloky i dohledané nestandardní bloky (bez kontroly ovšem).
* **Automatické generování výstupů**:
  * **`.ptp`**: Finální kontejner s kompletní strukturou pásky pro emulátor od RM Team.
  * **Vyčištěný `.wav`**: Rekonstruovaný obdélníkový signál vhodný pro zpětné nahrávání na reálném HW.
  * **Report `.txt`**: Strukturovaný analytický přehled kompatibilní s databází historických nahrávek Rudolfa Jana Suchého.
  * **Visual `.png` (`-v`)**: Přehledný časový graf nahrávky s vyznačením jednotlivých bloků.
  * **Log soubory `.log`**: Kompletní výpis průběhu dekódování pro každý soubor.

---

## Požadavky a Instalace

Pro spuštění je vyžadován **Python 3.8+** a následující knihovny:

```bash
pip install numpy scipy matplotlib tqdm
