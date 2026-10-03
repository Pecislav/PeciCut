<div align="center">

# Pecislav Studio 🎬
### *The Ultimate Desktop Creator Suite by Pecislav*

[![Version](https://img.shields.io/badge/Verze-1.0.0--beta-FF6D00?style=for-the-badge&logo=rocket)](https://github.com/Pecislav/PecislavStudio)
[![Platform](https://img.shields.io/badge/Platforma-Windows%20%7C%20macOS-22C55E?style=for-the-badge&logo=windows)](https://github.com/Pecislav/PecislavStudio)
[![UI](https://img.shields.io/badge/Design-Logi%20Options%2B%20Style-FF6D00?style=for-the-badge)](https://github.com/Pecislav/PecislavStudio)
[![Typography](https://img.shields.io/badge/Font-Poppins-0284C7?style=for-the-badge)](https://fonts.google.com/specimen/Poppins)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

<p align="center">
  <b>Komplexní All-in-One ekosystém pro streamery, YouTubery a tvůrce obsahu.</b><br>
  Automatický střih dlouhých streamů (2–6 hodin), hybridní Facecam AI pro zachycení nejlepších reakcí a bleskový bezztrátový export bez ztráty kvality.
</p>

---

</div>

## 🧭 O aplikaci Pecislav Studio

**Pecislav Studio** je moderní desktopový software navržený speciálně pro potřeby tvůrců na Twitchi a YouTube. Nabízí elegantní design inspirovaný **Logi Options+**, čistou typografii **Google Fonts Poppins**, zaoblené plovoucí prvky a signaturní oranžový akcent `#FF6D00`. Namísto desítek jednoúčelových skriptů přináší ucelené profesionální řešení s tmavým i světlým režimem.

---

## 🧩 Hlavní funkce a moduly

### 🎬 1. PeciCut — Highlight Cutter & Reaction Engine
- **🤖 Facecam Computer Vision AI**: V reálném čase analyzuje webkameru pomocí neuronových sítí OpenCV YuNet ONNX. Detekuje otevřená ústa při výkřiku, údivu, široký úsměv při záchvatu smíchu a kinetický pohyb těla.
- **⚡ Dvoufázová hybridní analýza**:
  - *Fáze 1*: Blesková proudová analýza audio křivky z OBS mikrofonu (vytyčí kandidáty během několika sekund s minimální zátěží RAM).
  - *Fáze 2*: Počítačové vidění prozkoumá pouze tyto momenty a vybere skutečné reakce tvůrce (odfiltruje náhodné zvuky ze hry).
- **⏱️ Cílová stopáž videa**: Omezení délky sestřihu na **5, 10, 15, 20, 30 minut** nebo **bez limitu**. PeciCut seřadí zachycené momenty podle intenzity a vybere nejlepší hype reakce.
- **✂️ Interaktivní Segment Review Editor**: Vizuální kontrola všech zachycených momentů před exportem s podporou celoobrazovkového náhledu, waveform křivky a okamžitého doladění klipů.
- **🎞️ Bezztrátový FFmpeg Stream Copy**: Střih probíhá bezztrátově přes concat demuxer (`-c copy`) bez rekomprese — 4hodinový stream je sestříhán za 1 až 2 minuty v plné původní kvalitě.
- **📋 CMX 3600 EDL Export**: Export timeline přímo do DaVinci Resolve a Adobe Premiere Pro pro finální postprodukci.

### ⚙️ 2. Nastavení Studia & Diagnostika
- **🎨 Přepínání motivů**: Podpora tmavého (Dark), světlého (Light) a systémového (System) režimu s živými náhledy a laděnými kontrastními barvami.
- **🌐 Vícejazyčné rozhraní**: Kompletní lokalizace do češtiny (CS) i angličtiny (EN).
- **💾 Spolehlivé ukládání nastavení**: Veškerá konfigurace (parametry střihu, posuvníky, složky, vzhled) se ukládá do trvalého `%APPDATA%/PecislavStudio/config.json`.
- **⬇️ 1-Click stahování s procenty**: Automatické stažení FFmpeg a Facecam AI modelů přímo v rozhraní s živým ukazatelem stažených dat (MB / KB) a procentuálním průběhem (`XX %`).
- **🧹 Správa mezipaměti**: Bezpečné promazání dočasných audio renderů jedním kliknutím bez ztráty nastavení.
- **🚀 Automatické aktualizace**: Integrovaná kontrola nových verzí přímo z GitHub Releases.

---

## 🛠️ Požadavky a instalace

### Požadavky:
- **Windows 10 / 11** nebo **macOS** (Apple Silicon i Intel)
- **Python 3.10** nebo novější
- FFmpeg (aplikace umí stáhnout automaticky přímo v nastavení)

### Rychlé spuštění z repozitáře:
```bash
# 1. Klonování repozitáře
git clone https://github.com/Pecislav/PecislavStudio.git
cd PecislavStudio

# 2. Instalace závislostí
python -m pip install -r requirements.txt

# 3. Spuštění Pecislav Studio
python main_gui.py
```

---

## 📦 Sestavení samostatné aplikace (.exe / .app)

Aplikaci lze snadno zabalit do jednoho spustitelného balíčku:

### Windows (.exe):
Spusťte přiložený skript:
```cmd
build_exe.bat
```
Nebo přes PyInstaller:
```cmd
py -m PyInstaller --noconfirm PecislavStudio.spec
```

Výsledná aplikace se vytvoří ve složce `dist/Pecislav Studio/`.

---

## 👤 Autor

Vytvořil **Pecislav** pro tvůrčí komunitu.
- GitHub: [@Pecislav](https://github.com/Pecislav)
- Projekt: **Pecislav Studio (Pro Creator Edition)**
