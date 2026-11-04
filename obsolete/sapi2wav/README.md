# SAPI-1 MIKOS Cassette Decoder & Signal Reconstructor

Nástroj pro digitalizaci, dekódování a restaurování magnetofonových nahrávek pro historický mikropočítač **SAPI-1** (systém MIKOS).

Tento skript emuluje chování hardwarového dekodéru, provádí pokročilou analýzu signálu, kontroluje integritu dat pomocí CRC a dokáže extrahovat uložené programy (textové nahrávky v BASICu, obecné textové soubory). Umí vygenerovat stoprocentně čistou, matematicky zrekonstruovanou obdélníkovou WAV nahrávku, kterou lze bez chyb nahrát přímo do reálného hardwaru.

---

## Klíčové vlastnosti (Features)

- **Analýza hran:**
  - Klasická detekce průchodů nulou. Automatické zjištění polarity.
- **Robustní filtrace:** Integrovaný Butterworthův pásmový filtr (300 Hz – 5 kHz) pro eliminaci síťového brumu (50 Hz) a vysokofrekvenčního šumu.
- **Extrakce dat:** Automatické poslepování MIKOS bloků do výsledných souborů:
  - `.txt` pro ASCII texty a zdrojové kódy (např. BASIC) s automatickým čištěním historického balastu (Form Feed, Ctrl+Z).
- **Hardware-Ready rekonstrukce:** Generování vyčištěného obdélníkového WAV signálu s přesnou fází a pilotním tónem pro spolehlivé načtení v SAPI-1.
- **Grafická vizualizace:** Možnost vygenerovat PNG diagram s waveformou kazety a přesným kaskádovým mapováním bloků.
- **Kompatibilní reporty:** Generování přehledného textového logu/reportu s časovými značkami (MM:SS) vhodného pro archivaci.

---

## Požadavky a instalace (Prerequisites)

Skript vyžaduje funkční prostředí **Python 3** a několik knihoven pro zpracování signálů a vykreslování.

Instalaci potřebných balíčků provedete příkazem:
```bash
pip install numpy scipy matplotlib tqdm
