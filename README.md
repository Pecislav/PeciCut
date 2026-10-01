<div align="center">

# Pecislav Studio 🎬
### *The Ultimate Desktop Creator Suite by Pecislav*

[![Version](https://img.shields.io/badge/Verze-1.0.0-FF6D00?style=for-the-badge&logo=rocket)](https://github.com/Pecislav/PecislavStudio)
[![Platform](https://img.shields.io/badge/Platforma-macOS%20%7C%20Windows-22C55E?style=for-the-badge&logo=apple)](https://github.com/Pecislav/PecislavStudio)
[![Edition](https://img.shields.io/badge/Edice-PRO%20CREATOR-FF6D00?style=for-the-badge)](https://github.com/Pecislav/PecislavStudio)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

<p align="center">
  <b>Komplexní All-in-One ekosystém pro streamery, YouTubery a tvůrce obsahu.</b><br>
  Automatický střih dlouhých streamů (2–6 hodin), hybridní Facecam AI pro zachycení nejlepších reakcí a bleskový bezztrátový export bez ztráty kvality.
</p>

---

</div>

## 🧭 O aplikaci Pecislav Studio

**Pecislav Studio** je modulární desktopový software navržený speciálně pro potřeby moderních tvůrců na Twitchi a YouTube. Namísto instalace desítek samostatných jednoúčelových skriptů sjednocuje klíčové nástroje pro střih, video analýzu a správu obsahu do jednoho vyladěného centra s tmavým a světlým Twitch/YouTube Creator motivem.

---

## 🧩 Moduly Studia

### 🎬 1. PeciCut — Highlight Cutter & Reaction Engine
Hlavní modul pro automatický střih záznamů streamů a videí:
- **🤖 Facecam Computer Vision AI**: V reálném čase analyzuje webkameru pomocí neuronových sítí OpenCV YuNet. Detekuje otevřená ústa při výkřiku, leknutí či údivu, široký úsměv při záchvatu smíchu a kinetický pohyb těla.
- **⚡ Dvoufázová hybridní analýza**: 
  - *Fáze 1*: Proudová analýza audio křivky z OBS mikrofonu (vytyčí kandidáty za pár sekund s minimální spotřebou RAM).
  - *Fáze 2*: Počítačové vidění vzorkuje pouze tyto momenty a vybere skutečné reakce tvůrce (odfiltruje náhodné rány ze hry, kde streamer nereaguje).
- **⏱️ Cílová maximální stopáž**: Možnost omezit délku sestřihu na **5, 10, 15, 20, 30 minut** nebo **bez limitu**. PeciCut inteligentně seřadí zachycené momenty a vybere ty nejzábavnější, které se přesně vejdou do zadaného času.
- **🎞️ Bezztrátový FFmpeg Stream Copy**: Střih probíhá bezztrátově přes concat demuxer (`-c copy`) bez zdlouhavého překódování — 4hodinový stream je sestříhán během 1 až 2 minut v plné původní kvalitě.
- **📋 CMX 3600 EDL Export**: Možnost exportovat timeline přímo do DaVinci Resolve a Adobe Premiere Pro pro finální úpravy.

### ⚙️ 2. Nastavení Studia — Centrální správa & Diagnostika
- **🎨 Zkosené vizuální motivy**: 3 stylizované grafické karty s ostrým šikmým přelivem barev:
  - *Systémová*: Tříbarevný přeliv (černá / oranžová / bílá)
  - *Bílá*: Dvoubarevný přeliv (oranžová / bílá)
  - *Černá*: Dvoubarevný přeliv (oranžová / černá)
- **📦 Kontrola stažených součástí**: 1-click ověření dostupnosti FFmpeg enginu, AI modelů (YuNet ONNX, Haar Cascades) a pracovních adresářů.
- **⬇️ Automatický 1-Click downloader**: Pokud FFmpeg nebo modely chybí, Studio je samo stáhne na pozadí z oficiálních repozitářů.
- **🚀 Verze a aktualizace**: Přímé napojení na GitHub Releases pro automatickou kontrolu nových verzí.

---

## 🛠️ Požadavky a instalace

### Požadavky:
- **macOS** (Apple Silicon i Intel) nebo **Windows 10/11**
- **Python 3.10** nebo novější
- FFmpeg (aplikace umí stáhnout automaticky jedním kliknutím)

### Rychlé spuštění:
```bash
# 1. Klonování repozitáře
git clone https://github.com/Pecislav/PecislavStudio.git
cd PecislavStudio

# 2. Instalace závislostí
python3 -m pip install -r requirements.txt

# 3. Spuštění Pecislav Studio
python3 main_gui.py
```

---

## 📦 Sestavení samostatné aplikace (.app / .exe)

Aplikaci lze snadno zabalit do jednoho spustitelného balíčku bez nutnosti mít nainstalovaný Python:

### macOS (.app):
```bash
pyinstaller --noconfirm --onedir --windowed \
  --name "Pecislav Studio" \
  --add-data "models:models" \
  --add-data "assets:assets" \
  main_gui.py
```

### Windows (.exe):
```bash
pyinstaller --noconfirm --onedir --windowed ^
  --name "Pecislav Studio" ^
  --add-data "models;models" ^
  --add-data "assets;assets" ^
  main_gui.py
```

Výsledná aplikace se vytvoří ve složce `dist/Pecislav Studio`.

---

## 👤 Autor

Vytvořil **Pecislav** pro tvůrčí komunitu.
- GitHub: [@Pecislav](https://github.com/Pecislav)
- Projekt: **Pecislav Studio (Pro Creator Edition)**
