"""
main_gui.py - Pecislav Studio: Creator Suite with modern CustomTkinter GUI.

Modules:
- PeciCut: Creator-focused video highlight cutter with Facecam AI and audio hype detection.
- Target duration limitation (e.g. 5, 10, 15, 20, 30 min or unlimited), prioritizing loudest hype moments.
- Recommended initial values clearly stated under every single setting.
- Interactive question mark (?) help buttons explaining each feature in plain language.
- Pixel-perfect vertical centering of the "PRO CREATOR" badge.
- 1-click automatic FFmpeg downloader & status indicator with X / feedback.
- Clean dropdown selectors for mode, duration, and output format.
- Sliders protected against accidental mousewheel/trackpad scrolling.
- Branded as Pecislav Studio by Pecislav with custom Twitch/YouTube creator theme.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw


from ffmpeg_utils import (
    download_ffmpeg_auto,
    find_binary,
    get_base_dir,
    get_ffmpeg_paths,
    open_folder_in_file_manager,
    verify_binaries,
)
from audio_analyzer import analyze_audio_stream, get_video_metadata
from edl_generator import generate_cmx3600_edl
from facecam_ai import (
    FacecamAnalyzer,
    analyze_candidate_facecam_segments,
    ensure_ai_models_present,
)
from video_cutter import (
    calculate_cut_statistics,
    cut_video_lossless,
    limit_segments_to_target_duration,
    merge_overlapping_segments,
)
from segment_editor import SegmentReviewDialog

APP_VERSION = "1.0.0-beta"

# -----------------------------------------------------------------------------
# Configuration Management & Defaults
# -----------------------------------------------------------------------------
def get_config_file_path() -> Path:
    """Returns path to config.json, preferring local app folder if writable, falling back to AppData / home."""
    base_dir = get_base_dir()
    local_cfg = base_dir / "config.json"
    if local_cfg.is_file():
        try:
            with open(local_cfg, "a"):
                pass
            return local_cfg
        except Exception:
            pass
    else:
        try:
            test_file = base_dir / ".test_write_cfg"
            test_file.touch()
            test_file.unlink()
            return local_cfg
        except Exception:
            pass

    if platform.system().lower() == "windows":
        app_data = os.getenv("APPDATA")
        if app_data:
            cfg_dir = Path(app_data) / "PecislavStudio"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            return cfg_dir / "config.json"

    cfg_dir = Path.home() / ".pecislavstudio"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.json"


CONFIG_FILE = get_config_file_path()
DEFAULT_CONFIG = {
    "language": "en",
    "theme": "system",
    "default_export_dir": "",
    "auto_open_folder": True,
    "history": []          # list of {"video": str, "output": str, "date": str, "stats": dict}
}


def load_app_config() -> dict:
    """Loads configuration from config.json, merged with default values."""
    cfg_file = get_config_file_path()
    if cfg_file.is_file():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cfg = DEFAULT_CONFIG.copy()
                    cfg.update(data)
                    return cfg
        except Exception as e:
            print(f"[Config] Error reading config.json: {e}")
    return DEFAULT_CONFIG.copy()


def save_app_config(config: dict):
    """Saves configuration dictionary to config.json."""
    cfg_file = get_config_file_path()
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Config] Error saving config.json: {e}")


# -----------------------------------------------------------------------------
# Cache & Maintenance Utilities
# -----------------------------------------------------------------------------
def get_app_cache_info() -> Tuple[int, List[Path]]:
    """
    Finds all temporary chunk directories, temp files, and caches created by Pecislav Studio.
    Returns (total_bytes, list_of_paths_to_clean).
    """
    paths_to_clean: List[Path] = []
    total_bytes = 0

    # 1. System temp files with autoclip_ or peci prefix
    tmp_dir = Path(tempfile.gettempdir())
    if tmp_dir.is_dir():
        try:
            for p in tmp_dir.iterdir():
                try:
                    if p.name.startswith(("autoclip_", "peci_", "pecicut_", "pecislav_")):
                        paths_to_clean.append(p)
                        if p.is_file():
                            total_bytes += p.stat().st_size
                        elif p.is_dir():
                            for f in p.rglob("*"):
                                if f.is_file():
                                    total_bytes += f.stat().st_size
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Local app cache directory if exists
    local_cache = get_base_dir() / "cache"
    if local_cache.is_dir():
        try:
            for f in local_cache.rglob("*"):
                try:
                    if f.is_file():
                        total_bytes += f.stat().st_size
                        paths_to_clean.append(f)
                except Exception:
                    pass
        except Exception:
            pass

    # 3. Local __pycache__ in base directory
    try:
        for pyc in get_base_dir().rglob("__pycache__"):
            paths_to_clean.append(pyc)
            for f in pyc.rglob("*"):
                if f.is_file():
                    total_bytes += f.stat().st_size
    except Exception:
        pass

    return total_bytes, paths_to_clean


def clear_app_cache() -> Tuple[int, int]:
    """
    Deletes temporary files and returns (freed_bytes, cleaned_count).
    """
    total_bytes, paths = get_app_cache_info()
    cleaned_count = 0
    freed_bytes = 0

    for p in paths:
        try:
            if p.is_file():
                sz = p.stat().st_size
                p.unlink(missing_ok=True)
                freed_bytes += sz
                cleaned_count += 1
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        freed_bytes += f.stat().st_size
                        cleaned_count += 1
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass

    return freed_bytes, cleaned_count


# -----------------------------------------------------------------------------
# Bilingual UI Translations (Čeština / English)
# -----------------------------------------------------------------------------
TRANSLATIONS = {
    "cs": {
        # App Shell & Navigation
        "app_title": "Pecislav Studio • Pro Creator",
        "brand_title": "Pecislav Studio",
        "nav_modules": "MODULY",
        "nav_pecicut": "  PeciCut",
        "nav_history": "  Historie projektů",
        "nav_system": "SYSTÉM",
        "nav_settings": "  Nastavení",
        "header_pecicut_title": "PeciCut",
        "header_pecicut_subtitle": "Automatický střih dlouhých záznamů (2-6h) z Twitch & YouTube dle mikrofonu",
        "header_settings_title": "Nastavení Studia",
        "header_settings_subtitle": "Barevný motiv, jazyk, export a aktualizace Pecislav Studio",
        "footer_text": f"Pecislav Studio v{APP_VERSION} • Creator Suite by Pecislav • Lossless FFmpeg Engine",

        # PeciCut Section 1: File selection
        "sec_file_title": "1. Výběr zdrojového video záznamu",
        "btn_select_file": "Procházet soubory...",
        "no_file_selected": "Zatím nebyl vybrán žádný soubor (.mp4, .mkv, .mov)",
        "meta_info_placeholder": "Po výběru souboru se zde zobrazí délka, FPS, rozlišení a nalezené audio stopy.",

        # PeciCut Section 2: Audio Track
        "sec_audio_title": "2. Výběr audio stopy pro analýzu (Mikrofon / Hlas)",
        "sec_audio_sub": "Vyberte stopu s vaším hlasem, aby se detekoval váš křik a reakce namísto zvuků ze hry.",

        # PeciCut Section 3: Detection Parameters
        "sec_params_title": "3. Režim detekce a parametry střihu",
        "mode_highlights": "Akcni highlighty (výkřiky, smích, hlasité momenty)",
        "mode_nosilence": "Celý stream bez hluchých míst (odstranění ticha)",
        "lbl_target_dur_title": "Cílová maximální délka sestřihu:",
        "lbl_threshold": "Práh hlasitosti / řevu (dBFS):",
        "lbl_pad_before": "Délka náběhu před momentem (Padding Before):",
        "lbl_pad_after": "Délka doznívání po momentu (Padding After):",
        "lbl_gap": "Minimální ticho pro rozdělení (Min Gap):",
        "chk_facecam": "Facecam AI (Analýza výrazu obličeje a smíchu z webkamery)",
        "sub_facecam": "Kombinuje audio analýzu s počítačovým viděním — prioritizuje nejlepší reakce obličeje, smích a leknutí.",

        # PeciCut Section 4: Export
        "sec_export_title": "4. Formát výstupu a cílová složka",
        "btn_change_out": "Změnit výstupní složku...",
        "out_dir_default": "Výstup: Automaticky ve složce se zdrojovým videem",
        "out_dir_custom": "Výstup: ",
        "chk_review_segments": "Před exportem otevřít editor momentů a náhledy",
        "sub_review_segments": "Umožní přehrát nalezené momenty a ručně upravit, co se má sestříhat.",

        # PeciCut Section 5: Progress & Results
        "btn_process": "Spustit zpracování záznamu",
        "btn_cancel": "Zrušit",
        "status_ready": "Video připraveno. Nastavte parametry a klikněte na 'Spustit zpracování'.",
        "status_waiting_editor": "Čekám na schválení momentů v editoru...",
        "btn_open_folder": "Otevřít složku s výsledkem",
        "lbl_done": "Hotovo!",

        # Settings Card 1: Themes
        "card_theme_title": " Barevný motiv aplikace",
        "card_theme_sub": "Vyberte vizuální styl studia (kliknutím na náhled):",
        "theme_system": "Systémová",
        "theme_light": "Bílá",
        "theme_dark": "Černá",

        # Settings Card 2: Language
        "card_lang_title": " Jazyk aplikace / Language",
        "card_lang_sub": "Zvolte preferovaný jazyk uživatelského rozhraní Pecislav Studio:",
        "lbl_select_language": "Aktivní jazyk rozhraní:",

        # Settings Card 3: Default Export & Folder Behavior
        "card_export_title": "Výchozí export a chování složek",
        "card_export_sub": "Nastavte kam se mají ukládat hotové sestřihy a chování po dokončení:",
        "lbl_default_folder": "Výchozí složka pro export:",
        "lbl_folder_beside": "(Automaticky ve složce se zdrojovým videem)",
        "btn_set_export_folder": "Změnit složku...",
        "btn_reset_export_folder": " Resetovat",
        "chk_auto_open_folder": "Automaticky otevřít cílovou složku po dokončení střihu",

        # Settings Card 4: Performance / CPU
        "card_perf_title": " Výkon a vytížení procesoru (CPU)",
        "card_perf_sub": "Přizpůsobte vytížení procesoru při renderování a AI analýze:",
        "perf_cores_detected": "Detekováno: {cores} jader CPU",
        "perf_max_opt": "Maximální výkon (všechna jádra)",
        "perf_balanced_opt": "Vyvážený / Herní režim (šetří CPU)",
        "perf_max_desc": "• Využívá 100% dostupných CPU jader pro nejrychlejší možný střih a detekci obličeje.",
        "perf_balanced_desc": "• Omezuje vytížení na polovinu jader ({half_cores}). Šetří procesor a grafiku pro plynulé hraní či streamování na Twitch/YouTube.",

        # Settings Card 5: Maintenance / Cache
        "card_cache_title": " Údržba a dočasná data (Cache)",
        "card_cache_sub": "Vyčistěte dočasné video segmenty, fragmenty a mezipaměť po předchozích střizích:",
        "lbl_cache_heading": "Stav dočasné mezipaměti:",
        "btn_clear_cache": "Promazat mezipaměť",
        "cache_clean": "Mezipaměť je čistá (0.0 MB)",
        "cache_found": "Nalezeno {size_mb} MB dočasných dat",
        "cache_cleared_msg": "Mezipaměť byla úspěšně promazána (uvolněno {freed_mb} MB).",

        # Settings Card 6: Components
        "card_comp_title": " Kontrola stažených součástí",
        "btn_recheck": " Zkontrolovat",
        "comp_ffmpeg_ok": "FFmpeg & FFprobe: Připraveno",
        "comp_ffmpeg_fail": "X FFmpeg & FFprobe: Chybí",
        "comp_ffmpeg_desc_ok": "Nalezeno v systému: {name}",
        "comp_ffmpeg_desc_fail": "Potřebné pro analýzu audia a střih videa",
        "comp_models_ok": "Facecam AI modely: Připraveno (3/3)",
        "comp_models_fail": "X Facecam AI modely: Nalezeno {cnt}/3",
        "comp_models_desc_ok": "YuNet ONNX & Haar Cascades v models/ pro detekci obličeje a reakcí",
        "comp_models_desc_fail": "Modely chybí pro analýzu webkamery",
        "comp_dirs_ok": "Pracovní adresáře aplikace: V pořádku",
        "comp_dirs_desc": "models/, assets/, bin/ jsou připraveny k použití",

        # Settings Card 7: Version & Updates
        "card_ver_title": "Verze aplikace a aktualizace",
        "btn_check_updates": "Zkontrolovat aktualizace",
        "btn_install_update": "Stáhnout a aktualizovat",
        "installed_ver": f"Nainstalovaná verze: Pecislav Studio v{APP_VERSION} (by Pecislav)",
        "update_status_latest": "Používáte nejnovější verzi aplikace.",
        "dnd_drop_hint": "Přetáhněte video sem (Drag & Drop) nebo vyberte soubor  •  MP4, MKV, MOV, WebM",
        "dnd_ready_hint": "Velikost: {size} MB  •  Připraveno k analýze  •  Přetažením nahradíte",
        "btn_change_file": "Změnit video",
    },
    "en": {
        # App Shell & Navigation
        "app_title": "Pecislav Studio • Pro Creator",
        "brand_title": "Pecislav Studio",
        "nav_modules": "MODULES",
        "nav_pecicut": "  PeciCut",
        "nav_history": "  Project History",
        "nav_system": "SYSTEM",
        "nav_settings": "  Settings",
        "header_pecicut_title": "PeciCut",
        "header_pecicut_subtitle": "Automated highlight cutter for long Twitch & YouTube recordings (2-6h) based on mic audio",
        "header_settings_title": "Studio Settings",
        "header_settings_subtitle": "Color theme, language, export and updates for Pecislav Studio",
        "footer_text": f"Pecislav Studio v{APP_VERSION} • Creator Suite by Pecislav • Lossless FFmpeg Engine",

        # PeciCut Section 1: File selection
        "sec_file_title": "1. Select Source Video Recording",
        "btn_select_file": "Browse files...",
        "no_file_selected": "No file selected yet (.mp4, .mkv, .mov)",
        "meta_info_placeholder": "File duration, FPS, resolution, and audio tracks will appear here after selection.",

        # PeciCut Section 2: Audio Track
        "sec_audio_title": "2. Select Audio Track for Analysis (Microphone / Voice)",
        "sec_audio_sub": "Select the track containing your voice so screams and reactions are analyzed instead of game audio.",

        # PeciCut Section 3: Detection Parameters
        "sec_params_title": "3. Detection Mode & Cutting Parameters",
        "mode_highlights": "Action Highlights (screams, laughter, hype moments)",
        "mode_nosilence": "Full Stream without Silence (remove quiet pauses)",
        "lbl_target_dur_title": "Target maximum video duration:",
        "lbl_threshold": "Loudness / Scream threshold (dBFS):",
        "lbl_pad_before": "Padding before highlight (Padding Before):",
        "lbl_pad_after": "Padding after highlight (Padding After):",
        "lbl_gap": "Minimum silence to split (Min Gap):",
        "chk_facecam": "Facecam AI (Facial expression & laughter analysis from webcam)",
        "sub_facecam": "Combines audio analysis with computer vision — prioritizes highest facial reactions, laughs and screams.",

        # PeciCut Section 4: Export
        "sec_export_title": "4. Output Format & Destination Directory",
        "btn_change_out": "Change output folder...",
        "out_dir_default": "Output: Automatically in source video directory",
        "out_dir_custom": "Output: ",
        "chk_review_segments": "Open interactive editor & video preview before export",
        "sub_review_segments": "Allows you to preview detected moments and customize which clips to export.",

        # PeciCut Section 5: Progress & Results
        "btn_process": "Start Processing Recording",
        "btn_cancel": "Cancel",
        "status_ready": "Video ready. Configure parameters and click 'Start Processing'.",
        "status_waiting_editor": "Waiting for moment selection in editor...",
        "btn_open_folder": "Open Destination Folder",
        "lbl_done": "Done!",

        # Settings Card 1: Themes
        "card_theme_title": " Application Color Theme",
        "card_theme_sub": "Select studio visual style (click on preview):",
        "theme_system": "System",
        "theme_light": "Light",
        "theme_dark": "Dark",

        # Settings Card 2: Language
        "card_lang_title": " Application Language / Jazyk",
        "card_lang_sub": "Select your preferred user interface language for Pecislav Studio:",
        "lbl_select_language": "Active UI Language:",

        # Settings Card 3: Default Export & Folder Behavior
        "card_export_title": "Default Export & Folder Behavior",
        "card_export_sub": "Set where exported highlights are saved and how the studio behaves upon completion:",
        "lbl_default_folder": "Default export folder:",
        "lbl_folder_beside": "(Automatically in source video folder)",
        "btn_set_export_folder": "Change folder...",
        "btn_reset_export_folder": " Reset",
        "chk_auto_open_folder": "Automatically open destination folder when export completes",

        # Settings Card 4: Performance / CPU
        "card_perf_title": " Performance & CPU Load",
        "card_perf_sub": "Adjust CPU utilization during video rendering and AI facecam analysis:",
        "perf_cores_detected": "Detected: {cores} CPU cores",
        "perf_max_opt": "Maximum Performance (all cores)",
        "perf_balanced_opt": "Balanced / Gaming Mode (saves CPU)",
        "perf_max_desc": "• Utilizes 100% of available CPU cores for fastest possible highlight cutting and facecam analysis.",
        "perf_balanced_desc": "• Limits processing to half the CPU cores ({half_cores}). Preserves CPU and GPU for smooth gaming or streaming on Twitch/YouTube.",

        # Settings Card 5: Maintenance / Cache
        "card_cache_title": " Maintenance & Temporary Cache",
        "card_cache_sub": "Clean up temporary video segments, chunks, and cache from previous cut sessions:",
        "lbl_cache_heading": "Temporary cache status:",
        "btn_clear_cache": "Clear Cache",
        "cache_clean": "Cache is clean (0.0 MB)",
        "cache_found": "Found {size_mb} MB of temporary data",
        "cache_cleared_msg": "Cache cleared successfully (freed {freed_mb} MB).",

        # Settings Card 6: Components
        "card_comp_title": " Component Health Check",
        "btn_recheck": " Recheck",
        "comp_ffmpeg_ok": "FFmpeg & FFprobe: Ready",
        "comp_ffmpeg_fail": "X FFmpeg & FFprobe: Missing",
        "comp_ffmpeg_desc_ok": "Found on system: {name}",
        "comp_ffmpeg_desc_fail": "Required for audio analysis and video cutting",
        "comp_models_ok": "Facecam AI models: Ready (3/3)",
        "comp_models_fail": "X Facecam AI models: Found {cnt}/3",
        "comp_models_desc_ok": "YuNet ONNX & Haar Cascades in models/ for face reaction detection",
        "comp_models_desc_fail": "Models missing for webcam reaction analysis",
        "comp_dirs_ok": "Application Working Directories: OK",
        "comp_dirs_desc": "models/, assets/, bin/ ready for use",

        # Settings Card 7: Version & Updates
        "card_ver_title": "Application Version & Updates",
        "btn_check_updates": "Check for Updates",
        "btn_install_update": "Download & Update",
        "installed_ver": f"Installed version: Pecislav Studio v{APP_VERSION} (by Pecislav)",
        "update_status_latest": "You are running the latest version.",
        "dnd_drop_hint": "Drag and drop video file here or click Browse  •  MP4, MKV, MOV, WebM",
        "dnd_ready_hint": "Size: {size} MB  •  Ready for analysis  •  Drag & drop to replace",
        "btn_change_file": "Change Video",
    }
}

# -----------------------------------------------------------------------------
# Creator Branding Theme Colors (Light / Dark Adaptive Tuples)
# -----------------------------------------------------------------------------
BG_WINDOW = ("#F0F2F5", "#0D0E12")          # Pozadí okna (světlá šedá / hluboká matná černá)
BG_HEADER = ("#E2E5E9", "#131419")          # Hlavička a patička
BG_CARD = ("#FFFFFF", "#17181F")            # Hlavní karty sekcí (čistá bílá / matná černá)
BG_CARD_INNER = ("#F7F8FA", "#111216")      # Vnitřní rámečky
BORDER_CARD = ("#D8DCE3", "#232530")        # Ohraničení karet

ORANGE_PRIMARY = "#FF6D00"                  # Energická Twitch/YT oranžová
ORANGE_HOVER = "#FF851A"                    # Světlejší hover oranžová
ORANGE_ACTIVE = "#E65A00"                   # Kliknutí / aktivní stav
ORANGE_SUBTLE = ("#FFE8D6", "#28170B")      # Podbarvení badge / tagů
ORANGE_ACCENT_TEXT = ("#D95A00", "#FF8C26") # Oranžový text pro hodnoty a čísla

TEXT_TITLE = ("#111827", "#FFFFFF")         # Text nadpisů (téměř černý / bílý)
TEXT_BODY = ("#4B5563", "#9FA6B3")          # Tlumený text popisků
TEXT_MUTED = ("#596172", "#8A92A2")         # Pomocné texty a tipy (vylepšený kontrast pro Light i Dark)
TEXT_REC = ("#C25E00", "#E08A3C")           # Teplá oranžovo-zlatá pro doporučení
TRACK_COLOR = ("#E5E7EB", "#242630")        # Pozadí dráhy sliderů a progress baru
BORDER_SUBTLE = ("#CBD5E1", "#363947")      # Ohraničení tlačítek a přepínačů

# -----------------------------------------------------------------------------
# Slanted Theme Preview Swatches Generator (Sharp Angle Cuts)
# -----------------------------------------------------------------------------

def create_slanted_theme_image(theme_type: str, w: int = 125, h: int = 42, r: int = 7) -> Image.Image:
    """
    Generates a crisp slanted color preview swatch without soft fade:
    - 'system': (černá / oranžová / bílá)
    - 'light': (oranžová / bílá)
    - 'dark': (oranžová / černá)
    """
    scale = 3  # 3x super-sampling for smooth anti-aliased diagonal edges
    sw, sh = w * scale, h * scale
    img = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    c_orange = (255, 109, 0, 255)
    c_white = (248, 249, 251, 255)
    c_black = (18, 19, 24, 255)

    # Sharp diagonal cut (slant dx across height)
    slant = sh * 0.45

    if theme_type == 'system':
        x1 = sw * 0.33
        x2 = sw * 0.67
        # 1. Černá (Left)
        draw.polygon([(0, 0), (x1 + slant/2, 0), (x1 - slant/2, sh), (0, sh)], fill=c_black)
        # 2. Oranžová (Middle)
        draw.polygon([(x1 + slant/2, 0), (x2 + slant/2, 0), (x2 - slant/2, sh), (x1 - slant/2, sh)], fill=c_orange)
        # 3. Bílá (Right)
        draw.polygon([(x2 + slant/2, 0), (sw, 0), (sw, sh), (x2 - slant/2, sh)], fill=c_white)
    elif theme_type == 'light':
        x = sw * 0.50
        # 1. Oranžová (Left)
        draw.polygon([(0, 0), (x + slant/2, 0), (x - slant/2, sh), (0, sh)], fill=c_orange)
        # 2. Bílá (Right)
        draw.polygon([(x + slant/2, 0), (sw, 0), (sw, sh), (x - slant/2, sh)], fill=c_white)
    elif theme_type == 'dark':
        x = sw * 0.50
        # 1. Oranžová (Left)
        draw.polygon([(0, 0), (x + slant/2, 0), (x - slant/2, sh), (0, sh)], fill=c_orange)
        # 2. Černá (Right)
        draw.polygon([(x + slant/2, 0), (sw, 0), (sw, sh), (x - slant/2, sh)], fill=c_black)

    # Rounded rectangle mask
    mask = Image.new('L', (sw, sh), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=r * scale, fill=255)

    out = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask=mask)

    # Subtle inner border
    draw_out = ImageDraw.Draw(out)
    draw_out.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=r * scale, outline=(100, 105, 120, 120), width=max(1, int(1.2 * scale)))

    return out.resize((w, h), Image.Resampling.LANCZOS)

# -----------------------------------------------------------------------------
# Floating Modern Tooltip (Hover Overlay - Zero Layout Shift)
# -----------------------------------------------------------------------------

class ModernTooltip:
    """
    Floating overlay tooltip that appears next to a widget on hover without shifting layout.
    Overlays gracefully above surrounding content with soft/semi-translucent typography
    and a distinct highlighted recommendation badge.
    """
    active_tooltip: Optional['ModernTooltip'] = None

    def __init__(self, widget, text: str, recommendation: Optional[str] = None, max_width: int = 400):
        self.widget = widget
        self.text = text.strip()
        self.recommendation = recommendation.strip() if recommendation else None
        self.max_width = max_width
        self.tip_window: Optional[tk.Toplevel] = None
        self.after_id = None
        self.hide_after_id = None

        targets = [self.widget]
        try:
            targets.extend(self.widget.winfo_children())
        except Exception:
            pass
        if hasattr(self.widget, "_canvas") and self.widget._canvas not in targets:
            targets.append(self.widget._canvas)
        if hasattr(self.widget, "_text_label") and self.widget._text_label not in targets:
            targets.append(self.widget._text_label)

        for w in targets:
            w.bind("<Enter>", self.on_enter, add=True)
            w.bind("<Leave>", self.on_leave, add=True)
            w.bind("<Button-1>", self.on_click, add=True)

    def set_recommendation(self, recommendation: Optional[str]):
        """Dynamically update recommendation text (e.g. when changing mode)."""
        self.recommendation = recommendation.strip() if recommendation else None

    def on_enter(self, event=None):
        if ModernTooltip.active_tooltip and ModernTooltip.active_tooltip != self:
            ModernTooltip.active_tooltip.hide()
        self.cancel_schedule()
        self.after_id = self.widget.after(80, self.show)

    def on_leave(self, event=None):
        self.cancel_schedule()
        self.hide_after_id = self.widget.after(150, self.hide)

    def on_click(self, event=None):
        self.cancel_schedule()
        self.hide()

    def cancel_schedule(self):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.hide_after_id:
            try:
                self.widget.after_cancel(self.hide_after_id)
            except Exception:
                pass
            self.hide_after_id = None

    def show(self):
        if self.tip_window or not self.widget.winfo_exists():
            return

        ModernTooltip.active_tooltip = self

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
            tw.attributes("-alpha", 0.95)
        except Exception:
            pass

        is_light = ctk.get_appearance_mode() == "Light"
        tip_bg = "#FFFFFF" if is_light else "#13141B"
        tip_fg = "#1F2937" if is_light else "#C2C7D0"
        rec_bg = "#FFF7ED" if is_light else "#231A13"
        rec_border = "#FFD1AD" if is_light else "#5C3414"
        rec_fg = "#C25E00" if is_light else "#FFA439"
        sep_bg = "#E5E7EB" if is_light else "#262936"

        # Subtle matte frame with creator orange accent border
        frame = tk.Frame(
            tw,
            bg=tip_bg,
            highlightthickness=1,
            highlightbackground="#FF6D00",
            padx=12,
            pady=10
        )
        frame.pack()

        font_family = "Segoe UI" if tk.TkVersion >= 8.6 and sys.platform.startswith("win") else "Helvetica"

        # Main explanation text (soft typography)
        lbl = tk.Label(
            frame,
            text=self.text,
            justify="left",
            font=(font_family, 11),
            fg=tip_fg,
            bg=tip_bg,
            wraplength=self.max_width
        )
        lbl.pack(anchor="w")

        hover_targets = [tw, frame, lbl]

        # Recommendation section (if present): Distinct warm amber shade + bold typography
        if self.recommendation:
            # Elegant thin separator
            sep = tk.Frame(frame, height=1, bg=sep_bg)
            sep.pack(fill="x", pady=(10, 8))

            # Recommendation container with subtle amber background
            rec_box = tk.Frame(
                frame,
                bg=rec_bg,
                highlightthickness=1,
                highlightbackground=rec_border,
                padx=10,
                pady=7
            )
            rec_box.pack(fill="x", anchor="w")

            rec_text = self.recommendation
            if not rec_text.startswith(""):
                rec_text = f"Doporuceni: {rec_text}"

            rec_lbl = tk.Label(
                rec_box,
                text=rec_text,
                justify="left",
                font=(font_family, 10, "bold"),
                fg=rec_fg,
                bg=rec_bg,
                wraplength=self.max_width - 24
            )
            rec_lbl.pack(anchor="w")

            hover_targets.extend([sep, rec_box, rec_lbl])

        # Keep tooltip open if mouse moves over tooltip window or recommendation box
        def keep_open(e):
            self.cancel_schedule()

        for widget_item in hover_targets:
            widget_item.bind("<Enter>", keep_open, add=True)
            widget_item.bind("<Leave>", self.on_leave, add=True)

        tw.update_idletasks()
        w_tip = tw.winfo_width()
        h_tip = tw.winfo_height()
        screen_w = tw.winfo_screenwidth()
        screen_h = tw.winfo_screenheight()

        root_x = self.widget.winfo_rootx()
        root_y = self.widget.winfo_rooty()
        btn_w = self.widget.winfo_width()

        # Position floating cleanly next to the ? button
        x = root_x + btn_w + 8
        y = root_y - 4

        # If it would overflow screen width on the right, place on left side
        if x + w_tip > screen_w - 12:
            x = max(8, root_x - w_tip - 8)

        # If it overflows screen height, clamp safely
        if y + h_tip > screen_h - 15:
            y = max(8, screen_h - h_tip - 15)

        tw.wm_geometry(f"+{x}+{y}")

    def hide(self):
        self.cancel_schedule()
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None
        if ModernTooltip.active_tooltip == self:
            ModernTooltip.active_tooltip = None

    @classmethod
    def hide_all(cls):
        if cls.active_tooltip:
            cls.active_tooltip.hide()

# -----------------------------------------------------------------------------
# Settings Dialog Compatibility Stub (Now integrated natively into Pecislav Studio)
# -----------------------------------------------------------------------------

class SettingsDialog:
    """Compatibility stub — switches to Pecislav Studio's integrated settings view."""
    def __init__(self, parent: 'AutoClipApp'):
        parent._switch_view("settings")


# -----------------------------------------------------------------------------
# Dedicated Project History Dialog
# -----------------------------------------------------------------------------

class ProjectHistoryDialog(ctk.CTkToplevel):
    """Dedicated modal dialog for managing and reopening previously processed projects."""

    def __init__(
        self,
        parent: "AutoClipApp",
        config: Dict,
        on_open_project: Callable[[Dict], None],
        on_clear_history: Callable[[], None],
        on_close: Optional[Callable[[], None]] = None,
        current_lang: str = "cs"
    ):
        super().__init__(parent)
        self.parent_app = parent
        self.config = config
        self.on_open_project = on_open_project
        self.on_clear_history = on_clear_history
        self.on_close = on_close
        self.current_lang = current_lang if current_lang in ("cs", "en") else "cs"

        title = "Historie projektů • Pecislav Studio" if self.current_lang == "cs" else "Project History • Pecislav Studio"
        self.title(title)
        self.geometry("960x620")
        self.minsize(940, 500)
        self.configure(fg_color=BG_WINDOW)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._center()
        self._set_app_icon()
        self.after(50, self._apply_windows_titlebar_theme)
        self._build_ui()
        self._setup_dialog_scrolling()

    def _set_app_icon(self):
        """Loads and sets the window icon."""
        try:
            assets_dir = get_base_dir() / "assets"
            ico_file = assets_dir / "app_icon.ico"
            png_file = assets_dir / "app_icon.png"

            if sys.platform.startswith("win") and ico_file.is_file():
                try:
                    self.iconbitmap(str(ico_file))
                    return
                except Exception:
                    pass

            target_png = png_file if png_file.is_file() else None
            if target_png:
                try:
                    from PIL import Image, ImageTk
                    pil_icon = Image.open(target_png)
                    self._app_window_icon = ImageTk.PhotoImage(pil_icon)
                    self.wm_iconphoto(True, self._app_window_icon)  # type: ignore
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_windows_titlebar_theme(self):
        """Sets immersive dark mode or light mode for the Windows title bar via DwmSetWindowAttribute."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            from ctypes import c_int, byref, sizeof
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            mode = ctk.get_appearance_mode().lower()
            dark_flag = c_int(1 if mode == "dark" else 0)
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark_flag), sizeof(dark_flag)
            )
            if res != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, byref(dark_flag), sizeof(dark_flag)
                )
            if mode == "dark":
                caption_color = c_int(0x00181211)  # #111218
                text_color = c_int(0x00FFFFFF)
            else:
                caption_color = c_int(0x00FAFAF8)
                text_color = c_int(0x0010181A)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, byref(caption_color), sizeof(caption_color)
            )
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 36, byref(text_color), sizeof(text_color)
            )
        except Exception:
            pass

    def _center(self):
        self.update_idletasks()
        try:
            w, h = 920, 620
            px, py = self.parent_app.winfo_x(), self.parent_app.winfo_y()
            pw, ph = self.parent_app.winfo_width(), self.parent_app.winfo_height()
            self.geometry(f"{w}x{h}+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 2)}")
        except Exception:
            pass

    def _setup_dialog_scrolling(self):
        def _on_wheel(event):
            try:
                canvas = getattr(self.scroll_list, "_parent_canvas", None)
                if not canvas or not canvas.winfo_exists():
                    return
                if sys.platform.startswith("win"):
                    steps = -int(event.delta / 1.5)
                elif sys.platform == "darwin":
                    steps = -int(event.delta * 2)
                else:
                    num = getattr(event, "num", None)
                    steps = -60 if num == 4 else 60
                canvas.yview_scroll(steps, "units")
                return "break"
            except Exception:
                pass

        self.bind("<MouseWheel>", _on_wheel)
        self.bind("<Button-4>", _on_wheel)
        self.bind("<Button-5>", _on_wheel)

    def _on_close_window(self):
        cb = self.on_close
        self.on_close = None
        try:
            self.destroy()
        finally:
            if callable(cb):
                cb()

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 14))

        t_title = "Historie zpracovaných projektů" if self.current_lang == "cs" else "Processed Projects History"
        t_sub = ("Videa, která prošla analýzou a střihem. Kliknutím na projekt se okamžitě vrátíte do editoru momentů."
                 if self.current_lang == "cs"
                 else "Videos processed by PeciCut. Click any project to open the moment editor immediately.")

        lbl_t = ctk.CTkLabel(hdr, text=t_title, font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_TITLE)
        lbl_t.pack(anchor="w")
        lbl_s = ctk.CTkLabel(hdr, text=t_sub, font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        lbl_s.pack(anchor="w", pady=(3, 0))

        # Scrollable container for history items
        self.scroll_list = ctk.CTkScrollableFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER_CARD
        )
        self.scroll_list.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        history = self.config.get("history", [])
        valid_entries = [h for h in history if h.get("video")]

        if not valid_entries:
            empty_box = ctk.CTkFrame(self.scroll_list, fg_color="transparent")
            empty_box.pack(expand=True, fill="both", pady=80)

            msg1 = "Zatím žádná historie projektů" if self.current_lang == "cs" else "No project history yet"
            msg2 = ("Až dokončíte analýzu videa nebo střih, projekt se zde automaticky uloží.\n"
                    "Budete se k němu moci kdykoliv vrátit a znovu otevřít editor bez nutnosti re-analyzovat audio."
                    if self.current_lang == "cs"
                    else "Completed video analyses and cuts will be stored here.\nYou can return anytime to review moments without re-analyzing audio.")
            ctk.CTkLabel(
                empty_box,
                text=msg1,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=TEXT_TITLE
            ).pack(pady=(0, 8))
            ctk.CTkLabel(
                empty_box,
                text=msg2,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_MUTED,
                justify="center"
            ).pack()
        else:
            for item in reversed(valid_entries):
                self._render_item(item)

        # Footer
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(0, 18))

        if valid_entries:
            t_clr = "Vymazat celou historii" if self.current_lang == "cs" else "Clear All History"
            ctk.CTkButton(
                footer,
                text=t_clr,
                command=self._on_clear_clicked,
                height=34,
                font=ctk.CTkFont(size=12),
                fg_color=BG_CARD_INNER,
                hover_color=("#FEE2E2", "#341B1B"),
                text_color=("#DC2626", "#F87171"),
                border_width=1,
                border_color=BORDER_CARD,
                corner_radius=6
            ).pack(side="left")

        t_close = "Zavřít" if self.current_lang == "cs" else "Close"
        ctk.CTkButton(
            footer,
            text=t_close,
            command=self._on_close_window,
            height=34,
            width=110,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF",
            corner_radius=6
        ).pack(side="right")

    def _render_item(self, item: Dict):
        card = ctk.CTkFrame(
            self.scroll_list,
            fg_color=BG_CARD_INNER,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD
        )
        card.pack(fill="x", padx=8, pady=5)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        video_path_str = item.get("video", "")
        v_path = Path(video_path_str)
        date_str = item.get("date", "")
        stats = item.get("stats", {})
        output_path = item.get("output", "")

        segs = stats.get("total_segments", 0)
        dur_in = stats.get("original_duration_min", 0.0)
        dur_out = stats.get("output_duration_min", 0.0)

        # 1. Action buttons FIRST on the right to guarantee they never get squeezed or truncated
        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(side="right", padx=(14, 0))

        # Otevřít v editoru
        t_edit = "Otevřít v editoru" if self.current_lang == "cs" else "Open in Editor"
        btn_open = ctk.CTkButton(
            btns,
            text=t_edit,
            command=lambda it=item: self._select_project(it),
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF",
            corner_radius=6,
            width=130
        )
        btn_open.pack(side="left", padx=(0, 6))

        if output_path and Path(output_path).parent.is_dir():
            t_f = "Složka" if self.current_lang == "cs" else "Folder"
            btn_folder = ctk.CTkButton(
                btns,
                text=t_f,
                command=lambda p=Path(output_path).parent: self.parent_app._open_folder(p),
                height=34,
                width=66,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=BG_CARD,
                hover_color=("#E5E7EB", "#252834"),
                text_color=TEXT_TITLE,
                border_width=1,
                border_color=BORDER_CARD,
                corner_radius=6
            )
            btn_folder.pack(side="left", padx=(0, 6))

        t_del = "Smazat" if self.current_lang == "cs" else "Delete"
        btn_del = ctk.CTkButton(
            btns,
            text=t_del,
            command=lambda it=item: self._confirm_and_delete_item(it),
            height=34,
            width=66,
            font=ctk.CTkFont(size=11),
            fg_color=BG_CARD,
            hover_color=("#FEE2E2", "#3B1818"),
            text_color=("#DC2626", "#F87171"),
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=6
        )
        btn_del.pack(side="left")

        # 2. Left side info fills remaining space cleanly
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)

        # File name
        ctk.CTkLabel(
            left,
            text=v_path.name,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_TITLE,
            anchor="w"
        ).pack(anchor="w")

        # Details
        if dur_out > 0.05:
            cut_str = f"Sestřih: {dur_out:.1f} min" if self.current_lang == "cs" else f"Cut: {dur_out:.1f} min"
        else:
            cut_str = "Připraveno k sestřihu" if self.current_lang == "cs" else "Ready to cut"

        if self.current_lang == "cs":
            det = f"{date_str}  •  {segs} momentů  •  Původní: {dur_in:.1f} min  •  {cut_str}"
        else:
            det = f"{date_str}  •  {segs} clips  •  Original: {dur_in:.1f} min  •  {cut_str}"
        ctk.CTkLabel(
            left,
            text=det,
            font=ctk.CTkFont(size=11),
            text_color=ORANGE_PRIMARY if segs > 0 else TEXT_MUTED,
            anchor="w"
        ).pack(anchor="w", pady=(3, 2))

        # Path muted
        disp_path = str(v_path.parent)
        if len(disp_path) > 65:
            disp_path = disp_path[:30] + "..." + disp_path[-30:]
        ctk.CTkLabel(
            left,
            text=disp_path,
            font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED,
            anchor="w"
        ).pack(anchor="w")

    def _select_project(self, item: Dict):
        self.on_close = None
        self.destroy()
        self.on_open_project(item)

    def _confirm_and_delete_item(self, item: Dict):
        v_name = Path(item.get("video", "")).name or "projekt"
        title = "Potvrdit smazání" if self.current_lang == "cs" else "Confirm Delete"
        msg = (f"Opravdu si přejete smazat projekt z historie?\n\n{v_name}"
               if self.current_lang == "cs"
               else f"Are you sure you want to remove this project from history?\n\n{v_name}")
        if messagebox.askyesno(title, msg, parent=self):
            self._delete_item(item)

    def _delete_item(self, item: Dict):
        history = self.config.get("history", [])
        self.config["history"] = [h for h in history if h.get("video") != item.get("video")]
        save_app_config(self.config)
        self._build_ui()

    def _on_clear_clicked(self):
        title = "Vymazat historii" if self.current_lang == "cs" else "Clear History"
        msg = ("Opravdu si přejete vymazat celou historii projektů?"
               if self.current_lang == "cs"
               else "Are you sure you want to clear all project history?")
        if messagebox.askyesno(title, msg, parent=self):
            self.on_clear_history()
            self._build_ui()


try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    _DnDBase = TkinterDnD.DnDWrapper
    HAS_TKDND = True
except (ImportError, Exception):
    HAS_TKDND = False
    DND_FILES = None
    TkinterDnD = None
    _DnDBase = object  # type: ignore


class BaseApp(ctk.CTk, _DnDBase):  # type: ignore
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dnd_ready = False
        if HAS_TKDND and TkinterDnD is not None:
            try:
                self.TkdndVersion = getattr(TkinterDnD, "_require")(self)
                self._dnd_ready = True
            except Exception:
                self._dnd_ready = False


class AutoClipApp(BaseApp):
    _SPINNER = ("⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷")

    def __init__(self):
        super().__init__()

        # Configuration
        self.config = load_app_config()
        self.current_language = self.config.get("language", "en")
        self.auto_open_folder = bool(self.config.get("auto_open_folder", True))
        self.default_export_dir = self.config.get("default_export_dir", "")
        self.saved_theme = self.config.get("theme", "system")

        if self.saved_theme in ["light", "dark", "system"]:
            ctk.set_appearance_mode(self.saved_theme.capitalize())

        # Windows taskbar grouping & icon registration
        if sys.platform.startswith("win"):
            try:
                import ctypes
                myappid = "pecislav.studio.creator.1.0"
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        # Window settings
        self.title(self.tr("app_title"))
        self.geometry("1080x860")
        self.minsize(1060, 720)
        self.configure(fg_color=BG_WINDOW)
        self._set_app_icon()
        self.after(50, self._apply_windows_titlebar_theme)

        # Application state
        self.current_video_path: Optional[Path] = None
        if self.default_export_dir and Path(self.default_export_dir).is_dir():
            self.output_directory = Path(self.default_export_dir)
        else:
            self.output_directory = None
        self.video_metadata: Optional[Dict] = None
        self.processing_thread: Optional[threading.Thread] = None
        self.download_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.is_processing = False
        self.is_downloading_ffmpeg = False
        self.last_output_path: Optional[Path] = None
        self.settings_dialog = None
        self.current_view = "pecicut"
        self._dim_overlay: Optional[ctk.CTkFrame] = None

        # Build Studio Shell: Left Sidebar + Right Pages Container
        self._build_app_shell()
        self._setup_smooth_scrolling()

        # Check FFmpeg availability at launch
        self._check_ffmpeg_status()

    def _set_app_icon(self):
        """Loads and sets the window icon across Windows and macOS/Linux."""
        try:
            assets_dir = get_base_dir() / "assets"
            ico_file = assets_dir / "app_icon.ico"
            png_file = assets_dir / "app_icon.png"
            logo_file = assets_dir / "logo.png"

            # On Windows, try iconbitmap with .ico first
            if sys.platform.startswith("win") and ico_file.is_file():
                try:
                    self.iconbitmap(str(ico_file))
                    return
                except Exception:
                    pass

            # Cross-platform wm_iconphoto
            target_png = png_file if png_file.is_file() else (logo_file if logo_file.is_file() else None)
            if target_png:
                try:
                    from PIL import Image, ImageTk
                    pil_icon = Image.open(target_png)
                    self._app_window_icon = ImageTk.PhotoImage(pil_icon)
                    self.wm_iconphoto(True, self._app_window_icon)  # type: ignore
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_windows_titlebar_theme(self):
        """Sets immersive dark mode or light mode for the Windows title bar via DwmSetWindowAttribute."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            from ctypes import c_int, byref, sizeof
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            mode = ctk.get_appearance_mode().lower()
            dark_flag = c_int(1 if mode == "dark" else 0)
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark_flag), sizeof(dark_flag)
            )
            if res != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, byref(dark_flag), sizeof(dark_flag)
                )
            if mode == "dark":
                caption_color = c_int(0x00181211)  # #111218 (0x00BBGGRR)
                text_color = c_int(0x00FFFFFF)
            else:
                caption_color = c_int(0x00FAFAF8)  # #F8FAFA
                text_color = c_int(0x0010181A)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, byref(caption_color), sizeof(caption_color)
            )
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 36, byref(text_color), sizeof(text_color)
            )
        except Exception:
            pass

    def tr(self, key: str, **kwargs) -> str:
        """Retrieves localized text for the given translation key based on self.current_language."""
        lang = getattr(self, "current_language", "cs")
        text_dict = TRANSLATIONS.get(lang, TRANSLATIONS["cs"])
        val = text_dict.get(key, TRANSLATIONS["cs"].get(key, key))
        if kwargs:
            try:
                return val.format(**kwargs)
            except Exception:
                return val
        return val

    def _get_configured_threads(self) -> int:
        """Returns optimal thread count for FFmpeg and OpenCV (0 = all cores automatically)."""
        return 0


    # -------------------------------------------------------------------------
    # Helper: Interactive (?) Help Button Builder
    # -------------------------------------------------------------------------

    def _create_help_btn(self, parent_row, target_container=None, text: str = "", recommendation: Optional[str] = None) -> ctk.CTkButton:
        """
        Creates a clean (?) hover button with a floating tooltip overlay.
        The text floats cleanly next to the button on hover without shifting or jumping
        any widgets below, with a distinct bold warm-tinted recommendation badge.
        """
        btn = ctk.CTkButton(
            parent_row,
            text="?",
            width=22,
            height=22,
            corner_radius=11,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#E5E7EB", "#262833"),
            hover_color=ORANGE_PRIMARY,
            text_color=("#4B5563", "#B4B9C7")
        )
        tooltip = ModernTooltip(btn, text=text, recommendation=recommendation)
        setattr(btn, "_tooltip", tooltip)
        return btn

    def _setup_smooth_scrolling(self):
        """
        Configures smooth, fast web-like scrolling across the entire application interface.
        Allows scrolling everywhere across the page (over cards, buttons, labels, sliders, empty space)
        at a natural web-like speed (~80px per wheel notch).
        """
        def web_scroll(event):
            try:
                w = getattr(event, "widget", None)
                if not w or not hasattr(w, "winfo_toplevel"):
                    return

                top = w.winfo_toplevel()
                if not top or not top.winfo_exists():
                    return

                # Calculate scroll steps
                if sys.platform.startswith("win"):
                    steps = -int(event.delta / 1.5)
                elif sys.platform == "darwin":
                    steps = -int(event.delta * 2)
                else:
                    num = getattr(event, "num", None)
                    steps = -60 if num == 4 else 60

                # 1. If mouse is in a modal dialog (SegmentReviewDialog or ProjectHistoryDialog)
                if top != self:
                    # SegmentReviewDialog with list canvas
                    list_canvas = getattr(top, "_list_canvas", None)
                    if list_canvas and list_canvas.winfo_exists():
                        seg_units = -int(event.delta / 40) if sys.platform.startswith("win") else steps
                        list_canvas.yview_scroll(seg_units, "units")
                        return "break"

                    # Dialog with scroll_list (e.g. ProjectHistoryDialog)
                    scroll_list = getattr(top, "scroll_list", None)
                    if scroll_list and scroll_list.winfo_exists():
                        sc = getattr(scroll_list, "_parent_canvas", None)
                        if sc and sc.winfo_exists():
                            sc.yview_scroll(steps, "units")
                            return "break"
                    return

                if isinstance(w, ctk.CTkScrollbar):
                    return

                # 2. Determine currently active scrollable page in main window
                active_page = self.page_pecicut if self.current_view == "pecicut" else getattr(self, "page_settings", None)
                if not active_page or not active_page.winfo_exists():
                    return

                canvas = getattr(active_page, "_parent_canvas", None)
                if not canvas or not canvas.winfo_exists():
                    return

                # Hide floating tooltips on scroll
                ModernTooltip.hide_all()

                canvas.yview_scroll(steps, "units")
                return "break"
            except Exception:
                pass

        # Global bind to root window replacing default sluggish CTk scroll
        self.bind_all("<MouseWheel>", web_scroll, add=False)
        self.bind_all("<Button-4>", web_scroll, add=False)
        self.bind_all("<Button-5>", web_scroll, add=False)

    def _disable_slider_mousewheel(self, slider: ctk.CTkSlider):
        """
        Disables value modification on mouse wheel scroll for a slider.
        Sliders will ONLY change values when clicked and dragged with the mouse.
        Mouse wheel scroll over sliders will NEVER modify the slider value.
        """
        for seq in (
            "<MouseWheel>",
            "<Button-4>",
            "<Button-5>",
            "<Shift-MouseWheel>",
            "<Shift-Button-4>",
            "<Shift-Button-5>",
        ):
            try:
                slider._canvas.unbind(seq)
            except Exception:
                pass

        slider._scroll_step = 0.0
        slider._mouse_scroll_event = lambda event: None

    # -------------------------------------------------------------------------
    # UI Builder Methods
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Pecislav Studio Architecture & Layout (All-in-One Shell)
    # -------------------------------------------------------------------------

    def _build_app_shell(self):
        """Constructs the master layout: Sidebar on the left, Header & Pages on the right."""
        # Main outer container
        self.shell_container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.shell_container.pack(fill="both", expand=True)

        # 1. Left Navigation Sidebar
        self._build_sidebar(self.shell_container)

        # 2. Right Content Wrapper (Header + Active View + Footer)
        self.right_wrapper = ctk.CTkFrame(self.shell_container, fg_color="transparent", corner_radius=0)
        self.right_wrapper.pack(side="left", fill="both", expand=True)

        # Header bar inside right wrapper
        self._build_header(self.right_wrapper)

        # Container where page views are switched
        self.pages_container = ctk.CTkFrame(self.right_wrapper, fg_color="transparent", corner_radius=0)
        self.pages_container.pack(fill="both", expand=True, padx=0, pady=0)

        # Build View 1: PeciCut (Highlight Cutter)
        self._build_pecicut_view(self.pages_container)

        # Build View 2: Nastavení Studia
        self._build_settings_view(self.pages_container)

        # Build Bottom Status Footer
        self._build_footer(self.right_wrapper)

        # Default active module: PeciCut
        self._switch_view("pecicut")

    def _build_sidebar(self, parent):
        """Constructs the left modern navigation bar for Pecislav Studio."""
        self.sidebar_frame = ctk.CTkFrame(parent, width=230, corner_radius=0, fg_color=BG_HEADER)
        self.sidebar_frame.pack(side="left", fill="y", padx=0, pady=0)
        self.sidebar_frame.pack_propagate(False)

        # Brand header with perfectly aligned two-line typography and refined edition badge
        brand_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        brand_frame.pack(fill="x", padx=16, pady=(18, 12))

        brand_top_row = ctk.CTkFrame(brand_frame, fg_color="transparent")
        brand_top_row.pack(fill="x")

        # Studio logo if present
        assets_dir = get_base_dir() / "assets"
        logo_path = assets_dir / "logo.png"
        if not logo_path.is_file():
            logo_path = assets_dir / "app_icon.png"

        self.logo_image = None
        if logo_path.is_file():
            try:
                from PIL import Image
                pil_img = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(38, 38))
                lbl_logo = ctk.CTkLabel(brand_top_row, text="", image=self.logo_image, width=38, height=38)
                lbl_logo.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        # Two-line brand typography (Pecislav on top, Studio + sleek Pro Creator tag directly underneath)
        brand_text_box = ctk.CTkFrame(brand_top_row, fg_color="transparent")
        brand_text_box.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            brand_text_box,
            text="Pecislav",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_TITLE,
            height=19
        ).pack(anchor="w", pady=(0, 1))

        row_studio = ctk.CTkFrame(brand_text_box, fg_color="transparent", height=18)
        row_studio.pack(anchor="w", fill="x")

        ctk.CTkLabel(
            row_studio,
            text="Studio",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_TITLE,
            height=18
        ).pack(side="left", padx=(0, 6))

        badge_tag = ctk.CTkLabel(
            row_studio,
            text="PRO CREATOR",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color=("#C2410C", "#FF8C26"),
            fg_color=("#FFEDD5", "#26170E"),
            corner_radius=4,
            padx=5,
            pady=0,
            height=16
        )
        badge_tag.pack(side="left")

        # Divider
        ctk.CTkFrame(self.sidebar_frame, height=1, fg_color=BORDER_CARD).pack(fill="x", padx=14, pady=12)

        # Navigation Label
        self.lbl_sidebar_modules = ctk.CTkLabel(
            self.sidebar_frame,
            text=self.tr("nav_modules"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED
        )
        self.lbl_sidebar_modules.pack(anchor="w", padx=18, pady=(4, 6))

        # Nav 1: PeciCut Module
        self.btn_nav_pecicut = ctk.CTkButton(
            self.sidebar_frame,
            text=self.tr("nav_pecicut"),
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            corner_radius=8,
            fg_color=ORANGE_PRIMARY,
            text_color="#FFFFFF",
            hover_color=ORANGE_HOVER,
            command=lambda: self._switch_view("pecicut")
        )
        self.btn_nav_pecicut.pack(fill="x", padx=12, pady=4)

        # System Section Label
        self.lbl_sidebar_system = ctk.CTkLabel(
            self.sidebar_frame,
            text=self.tr("nav_system"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED
        )
        self.lbl_sidebar_system.pack(anchor="w", padx=18, pady=(16, 6))

        # Nav 2: Settings Module
        self.btn_nav_settings = ctk.CTkButton(
            self.sidebar_frame,
            text=self.tr("nav_settings"),
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            corner_radius=8,
            fg_color="transparent",
            text_color=TEXT_TITLE,
            hover_color=("#D1D5DB", "#20222B"),
            command=lambda: self._switch_view("settings")
        )
        self.btn_nav_settings.pack(fill="x", padx=12, pady=4)

        # Spacer pushes footer to the bottom
        ctk.CTkFrame(self.sidebar_frame, fg_color="transparent").pack(fill="both", expand=True)

        # Bottom Sidebar Box
        bottom_box = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        bottom_box.pack(fill="x", padx=14, pady=(0, 16))

        # Interactive FFmpeg health indicator pill
        self.sidebar_ffmpeg_pill = ctk.CTkButton(
            bottom_box,
            text="● FFmpeg: Ověřuji...",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            corner_radius=6,
            fg_color=("#E5E7EB", "#1C1E27"),
            text_color=TEXT_BODY,
            hover_color=("#D1D5DB", "#2B2E3B"),
            command=lambda: self._switch_view("settings")
        )
        self.sidebar_ffmpeg_pill.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            bottom_box,
            text=f"Pecislav Studio v{APP_VERSION}\nby Pecislav",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED,
            justify="center"
        ).pack(fill="x")

    def _build_header(self, parent):
        """Top banner inside right wrapper displaying active module info."""
        self.header_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color=BG_HEADER)
        self.header_frame.pack(fill="x", padx=0, pady=0)

        header_row = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=24, pady=14)

        left_box = ctk.CTkFrame(header_row, fg_color="transparent")
        left_box.pack(side="left", fill="x", expand=True)

        title_row = ctk.CTkFrame(left_box, fg_color="transparent")
        title_row.pack(anchor="w")

        self.lbl_header_title = ctk.CTkLabel(
            title_row,
            text=self.tr("header_pecicut_title"),
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_header_title.pack(side="left")

        self.lbl_header_subtitle = ctk.CTkLabel(
            left_box,
            text=self.tr("header_pecicut_subtitle"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        self.lbl_header_subtitle.pack(anchor="w", pady=(3, 0))

    def _build_pecicut_view(self, parent):
        """Builds the PeciCut Highlight Cutter view inside the main pages container."""
        self.page_pecicut = ctk.CTkScrollableFrame(parent, corner_radius=0, fg_color="transparent")
        self.scroll_frame = self.page_pecicut  # Preserve self.scroll_frame for existing callbacks

        # 1. Výběr souboru
        self._build_file_section(self.page_pecicut)
        # 2. Audio stopa
        self._build_audio_track_section(self.page_pecicut)
        # 3. Parametry detekce
        self._build_parameters_section(self.page_pecicut)
        # 4. Export
        self._build_export_section(self.page_pecicut)
        # 5. Průběh a výsledky
        self._build_progress_section(self.page_pecicut)

    def _build_settings_view(self, parent):
        """Builds the native Settings view for Pecislav Studio with all configuration cards."""
        self.page_settings = ctk.CTkScrollableFrame(parent, corner_radius=0, fg_color="transparent")

        # ---------------------------------------------------------------------
        # 1. Barevný režim aplikace (Obrázky se skosením: Systémová / Bílá / Černá)
        # ---------------------------------------------------------------------
        theme_card = ctk.CTkFrame(self.page_settings, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        theme_card.pack(fill="x", pady=(0, 12))

        self.lbl_theme_title = ctk.CTkLabel(
            theme_card,
            text=self.tr("card_theme_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_theme_title.pack(anchor="w", padx=16, pady=(14, 2))

        self.lbl_theme_sub = ctk.CTkLabel(
            theme_card,
            text=self.tr("card_theme_sub"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        self.lbl_theme_sub.pack(anchor="w", padx=16, pady=(0, 12))

        themes_row = ctk.CTkFrame(theme_card, fg_color="transparent")
        themes_row.pack(fill="x", padx=16, pady=(0, 16))

        # 3 theme previews with sharp slanted cuts
        self.theme_images = {}
        theme_modes = [
            ("system", self.tr("theme_system")),
            ("light", self.tr("theme_light")),
            ("dark", self.tr("theme_dark"))
        ]
        for mode_key, _ in theme_modes:
            pil_img = create_slanted_theme_image(mode_key, w=125, h=42, r=7)
            self.theme_images[mode_key] = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(125, 42))

        self.theme_buttons = {}
        for idx, (mode_key, label_text) in enumerate(theme_modes):
            btn = ctk.CTkButton(
                themes_row,
                image=self.theme_images[mode_key],
                text=label_text,
                compound="top",
                font=ctk.CTkFont(size=12, weight="bold"),
                height=84,
                corner_radius=10,
                fg_color=BG_CARD_INNER,
                text_color=TEXT_TITLE,
                border_width=1,
                border_color=BORDER_CARD,
                hover_color=("#E5E7EB", "#222530"),
                command=lambda m=mode_key: self._on_theme_select(m)
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else 10, 0))
            self.theme_buttons[mode_key] = btn

        current_mode = ctk.get_appearance_mode().lower()
        if current_mode not in ["light", "dark"]:
            current_mode = "system"
        self._highlight_selected_theme(current_mode)

        # ---------------------------------------------------------------------
        # 2. Jazyk aplikace / Language
        # ---------------------------------------------------------------------
        lang_card = ctk.CTkFrame(self.page_settings, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        lang_card.pack(fill="x", pady=(0, 12))

        self.lbl_lang_title = ctk.CTkLabel(
            lang_card,
            text=self.tr("card_lang_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_lang_title.pack(anchor="w", padx=16, pady=(14, 2))

        self.lbl_lang_sub = ctk.CTkLabel(
            lang_card,
            text=self.tr("card_lang_sub"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        self.lbl_lang_sub.pack(anchor="w", padx=16, pady=(0, 10))

        lang_box = ctk.CTkFrame(lang_card, fg_color=BG_CARD_INNER, corner_radius=8, border_width=1, border_color=BORDER_CARD)
        lang_box.pack(fill="x", padx=16, pady=(0, 16))

        l_inner = ctk.CTkFrame(lang_box, fg_color="transparent")
        l_inner.pack(fill="x", padx=14, pady=12)

        self.lbl_lang_select = ctk.CTkLabel(
            l_inner,
            text=self.tr("lbl_select_language"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_lang_select.pack(side="left")

        self.lang_menu = ctk.CTkOptionMenu(
            l_inner,
            values=["English", "Čeština"],
            command=self._on_language_select,
            width=200,
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(size=13),
            fg_color=ORANGE_PRIMARY,
            button_color=ORANGE_HOVER,
            button_hover_color="#CC5200",
            dropdown_fg_color=("#F3F4F6", "#1E2028"),
            dropdown_hover_color=ORANGE_PRIMARY,
            dropdown_text_color=TEXT_TITLE,
            text_color="#FFFFFF"
        )
        self.lang_menu.pack(side="right")
        self.lang_menu.set("English" if self.current_language == "en" else "Čeština")

        # ---------------------------------------------------------------------
        # 3. Výchozí export a chování složek
        # ---------------------------------------------------------------------
        export_card = ctk.CTkFrame(self.page_settings, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        export_card.pack(fill="x", pady=(0, 12))

        self.lbl_export_title = ctk.CTkLabel(
            export_card,
            text=self.tr("card_export_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_export_title.pack(anchor="w", padx=16, pady=(14, 2))

        self.lbl_export_sub = ctk.CTkLabel(
            export_card,
            text=self.tr("card_export_sub"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        self.lbl_export_sub.pack(anchor="w", padx=16, pady=(0, 10))

        # Folder location row
        folder_box = ctk.CTkFrame(export_card, fg_color=BG_CARD_INNER, corner_radius=8, border_width=1, border_color=BORDER_CARD)
        folder_box.pack(fill="x", padx=16, pady=(0, 10))

        f_inner = ctk.CTkFrame(folder_box, fg_color="transparent")
        f_inner.pack(fill="x", padx=12, pady=10)

        self.lbl_def_folder_title = ctk.CTkLabel(
            f_inner,
            text=self.tr("lbl_default_folder"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_def_folder_title.pack(anchor="w")

        curr_def_text = self.default_export_dir if (self.default_export_dir and Path(self.default_export_dir).is_dir()) else self.tr("lbl_folder_beside")
        curr_def_color = TEXT_TITLE if (self.default_export_dir and Path(self.default_export_dir).is_dir()) else TEXT_MUTED

        self.lbl_def_folder_path = ctk.CTkLabel(
            f_inner,
            text=curr_def_text,
            font=ctk.CTkFont(size=12),
            text_color=curr_def_color,
            anchor="w"
        )
        self.lbl_def_folder_path.pack(fill="x", pady=(2, 8))

        f_btn_row = ctk.CTkFrame(f_inner, fg_color="transparent")
        f_btn_row.pack(fill="x")

        self.btn_change_default_export = ctk.CTkButton(
            f_btn_row,
            text=self.tr("btn_set_export_folder"),
            command=self._on_change_default_export,
            width=160,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF"
        )
        self.btn_change_default_export.pack(side="left", padx=(0, 8))

        self.btn_reset_default_export = ctk.CTkButton(
            f_btn_row,
            text=self.tr("btn_reset_export_folder"),
            command=self._on_reset_default_export,
            width=110,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color=("#E5E7EB", "#20222B"),
            hover_color=("#D1D5DB", "#2B2E3B"),
            text_color=TEXT_TITLE
        )
        self.btn_reset_default_export.pack(side="left")

        # Auto open checkbox
        self.auto_open_folder_var = ctk.BooleanVar(value=self.auto_open_folder)
        self.chk_auto_open_folder = ctk.CTkCheckBox(
            export_card,
            text=self.tr("chk_auto_open_folder"),
            variable=self.auto_open_folder_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            border_color=("#9CA3AF", "#3A3D4D"),
            text_color=TEXT_TITLE,
            command=self._on_toggle_auto_open
        )
        self.chk_auto_open_folder.pack(anchor="w", padx=16, pady=(0, 16))

        # ---------------------------------------------------------------------
        # 4. Údržba a dočasná data (Cache)
        # ---------------------------------------------------------------------
        cache_card = ctk.CTkFrame(self.page_settings, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        cache_card.pack(fill="x", pady=(0, 12))

        self.lbl_cache_title = ctk.CTkLabel(
            cache_card,
            text=self.tr("card_cache_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_cache_title.pack(anchor="w", padx=16, pady=(14, 2))

        self.lbl_cache_sub = ctk.CTkLabel(
            cache_card,
            text=self.tr("card_cache_sub"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        self.lbl_cache_sub.pack(anchor="w", padx=16, pady=(0, 12))

        cache_box = ctk.CTkFrame(cache_card, fg_color=BG_CARD_INNER, corner_radius=8, border_width=1, border_color=BORDER_CARD)
        cache_box.pack(fill="x", padx=16, pady=(0, 16))

        c_inner = ctk.CTkFrame(cache_box, fg_color="transparent")
        c_inner.pack(fill="x", padx=14, pady=12)

        c_info = ctk.CTkFrame(c_inner, fg_color="transparent")
        c_info.pack(side="left", fill="x", expand=True)

        self.lbl_cache_heading = ctk.CTkLabel(
            c_info,
            text=self.tr("lbl_cache_heading"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_cache_heading.pack(anchor="w")

        self.lbl_cache_status = ctk.CTkLabel(
            c_info,
            text=self.tr("cache_clean"),
            font=ctk.CTkFont(size=11),
            text_color="#22C55E"
        )
        self.lbl_cache_status.pack(anchor="w", pady=(2, 0))

        self.btn_clean_cache = ctk.CTkButton(
            c_inner,
            text=self.tr("btn_clear_cache"),
            command=self._on_clear_cache_click,
            width=175,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#FEE2E2", "#2B1616"),
            hover_color=("#FECACA", "#3E1E1E"),
            text_color=("#DC2626", "#FF6B6B"),
            border_width=1,
            border_color=("#FCA5A5", "#5E2222")
        )
        self.btn_clean_cache.pack(side="right")

        # ---------------------------------------------------------------------
        # 6. Kontrola stažených součástí
        # ---------------------------------------------------------------------
        comp_card = ctk.CTkFrame(self.page_settings, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        comp_card.pack(fill="x", pady=(0, 12))

        comp_hdr = ctk.CTkFrame(comp_card, fg_color="transparent")
        comp_hdr.pack(fill="x", padx=16, pady=(14, 8))

        self.lbl_comp_title = ctk.CTkLabel(
            comp_hdr,
            text=self.tr("card_comp_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_comp_title.pack(side="left")

        self.btn_recheck = ctk.CTkButton(
            comp_hdr,
            text=self.tr("btn_recheck"),
            width=110,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#E5E7EB", "#20222B"),
            hover_color=("#D1D5DB", "#2B2E3B"),
            text_color=TEXT_TITLE,
            command=self._refresh_settings_components
        )
        self.btn_recheck.pack(side="right")

        self.comp_rows_frame = ctk.CTkFrame(comp_card, fg_color="transparent")
        self.comp_rows_frame.pack(fill="x", padx=16, pady=(0, 14))

        # ---------------------------------------------------------------------
        # 7. Verze aplikace a aktualizace
        # ---------------------------------------------------------------------
        ver_card = ctk.CTkFrame(self.page_settings, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        ver_card.pack(fill="x", pady=(0, 12))

        ver_hdr = ctk.CTkFrame(ver_card, fg_color="transparent")
        ver_hdr.pack(fill="x", padx=16, pady=(14, 8))

        self.lbl_ver_title = ctk.CTkLabel(
            ver_hdr,
            text=self.tr("card_ver_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_ver_title.pack(side="left")

        ver_btns = ctk.CTkFrame(ver_hdr, fg_color="transparent")
        ver_btns.pack(side="right")

        self.btn_update = ctk.CTkButton(
            ver_btns,
            text=self.tr("btn_check_updates"),
            width=165,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF",
            command=self._check_for_updates
        )
        self.btn_update.pack(side="left", padx=(0, 8))

        self.btn_install_update = ctk.CTkButton(
            ver_btns,
            text=self.tr("btn_install_update"),
            width=165,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=BG_CARD_INNER,
            hover_color=("#E5E7EB", "#252834"),
            text_color=ORANGE_PRIMARY,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=6,
            command=self._perform_auto_update
        )
        self.btn_install_update.pack(side="left")

        ver_body = ctk.CTkFrame(ver_card, fg_color="transparent")
        ver_body.pack(fill="x", padx=16, pady=(0, 16))

        self.lbl_installed_ver = ctk.CTkLabel(
            ver_body,
            text=self.tr("installed_ver"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_installed_ver.pack(anchor="w")

        self.lbl_update_status = ctk.CTkLabel(
            ver_body,
            text=self.tr("update_status_latest"),
            font=ctk.CTkFont(size=11),
            text_color="#22C55E"
        )
        self.lbl_update_status.pack(anchor="w", pady=(4, 0))

        # Initial quiet renders
        self._refresh_cache_display()
        self._render_components_static()

    def _on_language_select(self, choice: str):
        """Switches active studio language, updates config, and refreshes UI."""
        if "English" in choice:
            self.current_language = "en"
        else:
            self.current_language = "cs"
        self.config["language"] = self.current_language
        save_app_config(self.config)
        self._apply_translations()

    def _on_change_default_export(self):
        """Allows user to select a default export directory for all projects."""
        folder = filedialog.askdirectory(title=self.tr("card_export_title"))
        if folder:
            self.default_export_dir = folder
            self.config["default_export_dir"] = folder
            save_app_config(self.config)
            self.lbl_def_folder_path.configure(text=folder, text_color=TEXT_TITLE)
            if not self.current_video_path or not self.output_directory:
                self.output_directory = Path(folder)
                if hasattr(self, "lbl_output_dir"):
                    self.lbl_output_dir.configure(
                        text=f"{self.tr('out_dir_custom')}{folder}",
                        text_color=TEXT_TITLE
                    )

    def _on_reset_default_export(self):
        """Resets default export directory to save beside the original video."""
        self.default_export_dir = ""
        self.config["default_export_dir"] = ""
        save_app_config(self.config)
        self.lbl_def_folder_path.configure(
            text=self.tr("lbl_folder_beside"),
            text_color=TEXT_MUTED
        )
        if not self.current_video_path:
            self.output_directory = None
            if hasattr(self, "lbl_output_dir"):
                self.lbl_output_dir.configure(
                    text=self.tr("out_dir_default"),
                    text_color=TEXT_BODY
                )

    def _on_toggle_auto_open(self):
        """Toggles automatic destination folder opening upon export completion."""
        self.auto_open_folder = bool(self.auto_open_folder_var.get())
        self.config["auto_open_folder"] = self.auto_open_folder
        save_app_config(self.config)

    def _refresh_cache_display(self):
        """Updates temporary cache size indicator."""
        if not hasattr(self, "lbl_cache_status") or not self.lbl_cache_status.winfo_exists():
            return
        total_bytes, paths = get_app_cache_info()
        if total_bytes > 0:
            mb = total_bytes / (1024 * 1024)
            self.lbl_cache_status.configure(
                text=self.tr("cache_found", size_mb=f"{mb:.1f}"),
                text_color=ORANGE_ACCENT_TEXT
            )
        else:
            self.lbl_cache_status.configure(
                text=self.tr("cache_clean"),
                text_color="#22C55E"
            )

    def _on_clear_cache_click(self):
        """Cleans temporary files and reports freed space."""
        freed, cnt = clear_app_cache()
        freed_mb = freed / (1024 * 1024)
        if freed_mb < 0.1 and freed > 0:
            freed_str = f"{freed / 1024:.1f} KB"
        else:
            freed_str = f"{freed_mb:.1f} MB"
        self.lbl_cache_status.configure(
            text=self.tr("cache_cleared_msg", freed_mb=freed_str),
            text_color="#22C55E"
        )

    def _apply_translations(self):
        """Refreshes all texts across navigation, headers, and cards to match self.current_language."""
        # 1. Window & Sidebar
        self.title(self.tr("app_title"))
        if hasattr(self, "lbl_sidebar_modules"):
            self.lbl_sidebar_modules.configure(text=self.tr("nav_modules"))
        if hasattr(self, "btn_nav_pecicut"):
            self.btn_nav_pecicut.configure(text=self.tr("nav_pecicut"))
        if hasattr(self, "lbl_sidebar_system"):
            self.lbl_sidebar_system.configure(text=self.tr("nav_system"))
        if hasattr(self, "btn_nav_settings"):
            self.btn_nav_settings.configure(text=self.tr("nav_settings"))
        if hasattr(self, "btn_open_history"):
            self.btn_open_history.configure(text=self.tr("nav_history"))
        if hasattr(self, "lbl_footer"):
            self.lbl_footer.configure(text=self.tr("footer_text"))

        # 2. Header
        if self.current_view == "pecicut":
            self.lbl_header_title.configure(text=self.tr("header_pecicut_title"))
            self.lbl_header_subtitle.configure(text=self.tr("header_pecicut_subtitle"))
        else:
            self.lbl_header_title.configure(text=self.tr("header_settings_title"))
            self.lbl_header_subtitle.configure(text=self.tr("header_settings_subtitle"))

        # 3. Settings View
        if hasattr(self, "lbl_theme_title"):
            self.lbl_theme_title.configure(text=self.tr("card_theme_title"))
            self.lbl_theme_sub.configure(text=self.tr("card_theme_sub"))
            if "system" in self.theme_buttons:
                self.theme_buttons["system"].configure(text=self.tr("theme_system"))
            if "light" in self.theme_buttons:
                self.theme_buttons["light"].configure(text=self.tr("theme_light"))
            if "dark" in self.theme_buttons:
                self.theme_buttons["dark"].configure(text=self.tr("theme_dark"))

        if hasattr(self, "lbl_lang_title"):
            self.lbl_lang_title.configure(text=self.tr("card_lang_title"))
            self.lbl_lang_sub.configure(text=self.tr("card_lang_sub"))
            if hasattr(self, "lbl_lang_select"):
                self.lbl_lang_select.configure(text=self.tr("lbl_select_language"))
            if hasattr(self, "lang_menu"):
                self.lang_menu.set("English" if self.current_language == "en" else "Čeština")

        if hasattr(self, "lbl_export_title"):
            self.lbl_export_title.configure(text=self.tr("card_export_title"))
            self.lbl_export_sub.configure(text=self.tr("card_export_sub"))
            self.lbl_def_folder_title.configure(text=self.tr("lbl_default_folder"))
            if not self.default_export_dir or not Path(self.default_export_dir).is_dir():
                self.lbl_def_folder_path.configure(text=self.tr("lbl_folder_beside"))
            self.btn_change_default_export.configure(text=self.tr("btn_set_export_folder"))
            self.btn_reset_default_export.configure(text=self.tr("btn_reset_export_folder"))
            self.chk_auto_open_folder.configure(text=self.tr("chk_auto_open_folder"))

        if hasattr(self, "lbl_cache_title"):
            self.lbl_cache_title.configure(text=self.tr("card_cache_title"))
            self.lbl_cache_sub.configure(text=self.tr("card_cache_sub"))
            self.lbl_cache_heading.configure(text=self.tr("lbl_cache_heading"))
            self.btn_clean_cache.configure(text=self.tr("btn_clear_cache"))
            self._refresh_cache_display()

        if hasattr(self, "lbl_comp_title"):
            self.lbl_comp_title.configure(text=self.tr("card_comp_title"))
            self.btn_recheck.configure(text=self.tr("btn_recheck"))
            self._render_components_static()

        if hasattr(self, "lbl_ver_title"):
            self.lbl_ver_title.configure(text=self.tr("card_ver_title"))
            self.btn_update.configure(text=self.tr("btn_check_updates"))
            if hasattr(self, "btn_install_update"):
                self.btn_install_update.configure(text=self.tr("btn_install_update"))
            self.lbl_installed_ver.configure(text=self.tr("installed_ver"))

        # 4. PeciCut View
        if hasattr(self, "lbl_sec_file"):
            self.lbl_sec_file.configure(text=self.tr("sec_file_title"))
        if hasattr(self, "btn_select_file"):
            btn_txt = self.tr("btn_change_file") if self.current_video_path else self.tr("btn_select_file")
            self.btn_select_file.configure(text=btn_txt)
        if hasattr(self, "lbl_file_path") and not self.current_video_path:
            self.lbl_file_path.configure(text=self.tr("no_file_selected"))
        if hasattr(self, "lbl_dnd_hint"):
            if not self.current_video_path:
                self.lbl_dnd_hint.configure(text=self.tr("dnd_drop_hint"), text_color=TEXT_MUTED)
            else:
                self._update_drop_zone_labels()
        if hasattr(self, "lbl_meta_info") and not self.video_metadata:
            self.lbl_meta_info.configure(text=self.tr("meta_info_placeholder"))

        if hasattr(self, "lbl_sec_audio"):
            self.lbl_sec_audio.configure(text=self.tr("sec_audio_title"))
            self.lbl_sec_audio_sub.configure(text=self.tr("sec_audio_sub"))

        if hasattr(self, "lbl_sec_params"):
            self.lbl_sec_params.configure(text=self.tr("sec_params_title"))
        if hasattr(self, "lbl_dur_heading"):
            self.lbl_dur_heading.configure(text=self.tr("lbl_target_dur_title"))
        if hasattr(self, "lbl_thresh_heading"):
            self.lbl_thresh_heading.configure(text=self.tr("lbl_threshold"))
        if hasattr(self, "lbl_pad_before_heading"):
            self.lbl_pad_before_heading.configure(text=self.tr("lbl_pad_before"))
        if hasattr(self, "lbl_pad_after_heading"):
            self.lbl_pad_after_heading.configure(text=self.tr("lbl_pad_after"))
        if hasattr(self, "lbl_gap_heading"):
            self.lbl_gap_heading.configure(text=self.tr("lbl_gap"))
        if hasattr(self, "chk_facecam_ai"):
            self.chk_facecam_ai.configure(text=self.tr("chk_facecam"))
            self.sub_facecam.configure(text=self.tr("sub_facecam"))

        if hasattr(self, "lbl_sec_export"):
            self.lbl_sec_export.configure(text=self.tr("sec_export_title"))
            self.btn_change_out.configure(text=self.tr("btn_change_out"))
            if not self.output_directory or (self.current_video_path and self.output_directory == self.current_video_path.parent):
                self.lbl_output_dir.configure(text=self.tr("out_dir_default"))
            if hasattr(self, "chk_review_segments"):
                self.chk_review_segments.configure(text=self.tr("chk_review_segments"))
            if hasattr(self, "sub_review_segments"):
                self.sub_review_segments.configure(text=self.tr("sub_review_segments"))

        if hasattr(self, "btn_process"):
            self.btn_process.configure(text=self.tr("btn_process"))
            self.btn_cancel.configure(text=self.tr("btn_cancel"))
            self.btn_open_folder.configure(text=self.tr("btn_open_folder"))
            self.lbl_result_check.configure(text=self.tr("lbl_done"))
            if not self.is_processing and not self.current_video_path:
                self.lbl_status.configure(text=self.tr("status_ready"))

    def _render_components_static(self):
        """Renders component rows statically in their current state without running animation/spinner."""
        if not hasattr(self, "comp_rows_frame") or not self.comp_rows_frame.winfo_exists():
            return

        for child in self.comp_rows_frame.winfo_children():
            child.destroy()

        # --- Row 0: FFmpeg & FFprobe ---
        ffmpeg_path, ffprobe_path = get_ffmpeg_paths()
        ffmpeg_ok = bool(ffmpeg_path and ffprobe_path)
        row0 = ctk.CTkFrame(self.comp_rows_frame, fg_color=BG_CARD_INNER, corner_radius=6, border_width=1, border_color=BORDER_CARD)
        row0.pack(fill="x", pady=4)
        info0 = ctk.CTkFrame(row0, fg_color="transparent")
        info0.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        if ffmpeg_ok:
            ctk.CTkLabel(info0, text=self.tr("comp_ffmpeg_ok"), font=ctk.CTkFont(size=12, weight="bold"), text_color="#22C55E").pack(anchor="w")
            ctk.CTkLabel(info0, text=self.tr("comp_ffmpeg_desc_ok", name=ffmpeg_path.name if ffmpeg_path else ''), font=ctk.CTkFont(size=11), text_color=TEXT_BODY).pack(anchor="w")
        else:
            ctk.CTkLabel(info0, text=self.tr("comp_ffmpeg_fail"), font=ctk.CTkFont(size=12, weight="bold"), text_color="#EF4444").pack(anchor="w")
            ctk.CTkLabel(info0, text=self.tr("comp_ffmpeg_desc_fail"), font=ctk.CTkFont(size=11), text_color=TEXT_BODY).pack(anchor="w")
            ctk.CTkButton(
                row0, text="" + ("Stáhnout FFmpeg" if self.current_language == "cs" else "Download FFmpeg"),
                width=135, height=26,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=ORANGE_PRIMARY, hover_color=ORANGE_HOVER,
                text_color="#FFFFFF", command=self._settings_download_ffmpeg_action
            ).pack(side="right", padx=12)

        # --- Row 1: Facecam AI modely ---
        mdir = get_base_dir() / "models"
        yn = (mdir / "face_detection_yunet_2023mar.onnx").is_file()
        sm = (mdir / "haarcascade_smile.xml").is_file()
        fc = (mdir / "haarcascade_frontalface_default.xml").is_file()
        cnt = sum([yn, sm, fc])
        models_ok = (cnt == 3)
        row1 = ctk.CTkFrame(self.comp_rows_frame, fg_color=BG_CARD_INNER, corner_radius=6, border_width=1, border_color=BORDER_CARD)
        row1.pack(fill="x", pady=4)
        info1 = ctk.CTkFrame(row1, fg_color="transparent")
        info1.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        if models_ok:
            ctk.CTkLabel(info1, text=self.tr("comp_models_ok"), font=ctk.CTkFont(size=12, weight="bold"), text_color="#22C55E").pack(anchor="w")
            ctk.CTkLabel(info1, text=self.tr("comp_models_desc_ok"), font=ctk.CTkFont(size=11), text_color=TEXT_BODY).pack(anchor="w")
        else:
            ctk.CTkLabel(info1, text=self.tr("comp_models_fail", cnt=cnt), font=ctk.CTkFont(size=12, weight="bold"), text_color="#EF4444").pack(anchor="w")
            ctk.CTkLabel(info1, text=self.tr("comp_models_desc_fail"), font=ctk.CTkFont(size=11), text_color=TEXT_BODY).pack(anchor="w")
            ctk.CTkButton(
                row1, text="" + ("Stáhnout modely" if self.current_language == "cs" else "Download models"),
                width=135, height=26,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=ORANGE_PRIMARY, hover_color=ORANGE_HOVER,
                text_color="#FFFFFF", command=self._settings_download_models_action
            ).pack(side="right", padx=12)

        # --- Row 2: Pracovní adresáře ---
        row2 = ctk.CTkFrame(self.comp_rows_frame, fg_color=BG_CARD_INNER, corner_radius=6, border_width=1, border_color=BORDER_CARD)
        row2.pack(fill="x", pady=4)
        info2 = ctk.CTkFrame(row2, fg_color="transparent")
        info2.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        ctk.CTkLabel(info2, text=self.tr("comp_dirs_ok"), font=ctk.CTkFont(size=12, weight="bold"), text_color="#22C55E").pack(anchor="w")
        ctk.CTkLabel(info2, text=self.tr("comp_dirs_desc"), font=ctk.CTkFont(size=11), text_color=TEXT_BODY).pack(anchor="w")

    def _switch_view(self, view_name: str):
        """Switches the active view in Pecislav Studio between PeciCut and Nastavení."""
        self.current_view = view_name
        if view_name == "pecicut":
            self.page_settings.pack_forget()
            self.page_pecicut.pack(fill="both", expand=True, padx=20, pady=12)
            self.btn_nav_pecicut.configure(
                fg_color=ORANGE_PRIMARY,
                text_color="#FFFFFF",
                hover_color=ORANGE_HOVER
            )
            self.btn_nav_settings.configure(
                fg_color="transparent",
                text_color=TEXT_TITLE,
                hover_color=("#D1D5DB", "#20222B")
            )
            self.lbl_header_title.configure(text=self.tr("header_pecicut_title"))
            self.lbl_header_subtitle.configure(text=self.tr("header_pecicut_subtitle"))
        elif view_name == "settings":
            self.page_pecicut.pack_forget()
            self.page_settings.pack(fill="both", expand=True, padx=20, pady=12)
            self.btn_nav_settings.configure(
                fg_color=ORANGE_PRIMARY,
                text_color="#FFFFFF",
                hover_color=ORANGE_HOVER
            )
            self.btn_nav_pecicut.configure(
                fg_color="transparent",
                text_color=TEXT_TITLE,
                hover_color=("#D1D5DB", "#20222B")
            )
            self.lbl_header_title.configure(text=self.tr("header_settings_title"))
            self.lbl_header_subtitle.configure(text=self.tr("header_settings_subtitle"))
            self._refresh_cache_display()

    def _on_theme_select(self, mode_key: str):
        if mode_key == "light":
            ctk.set_appearance_mode("Light")
        elif mode_key == "dark":
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("System")
        self.config["theme"] = mode_key
        save_app_config(self.config)
        self._highlight_selected_theme(mode_key)
        self.after(50, self._apply_windows_titlebar_theme)

    def _highlight_selected_theme(self, active_mode: str):
        for mode_key, btn in getattr(self, "theme_buttons", {}).items():
            if mode_key == active_mode:
                btn.configure(
                    border_width=2,
                    border_color=ORANGE_PRIMARY,
                    fg_color=("#F3F4F6", "#20222B"),
                    text_color=ORANGE_PRIMARY
                )
            else:
                btn.configure(
                    border_width=1,
                    border_color=BORDER_CARD,
                    fg_color=BG_CARD_INNER,
                    text_color=TEXT_BODY
                )

    def _on_theme_change(self, choice: str):
        mode_map = {"Systémová": "system", "Bílá": "light", "Černá": "dark"}
        self._on_theme_select(mode_map.get(choice, "system"))

    def _refresh_settings_components(self):
        """Animated component check with spinner per row, then green/red results."""
        if not hasattr(self, "comp_rows_frame") or not self.comp_rows_frame.winfo_exists():
            return

        self._check_gen = getattr(self, "_check_gen", 0) + 1
        my_gen = self._check_gen

        # Clear existing rows
        for child in self.comp_rows_frame.winfo_children():
            child.destroy()

        loading_bg = ("#E5E7EB", "#1C1E27")
        comps = [
            "FFmpeg & FFprobe",
            "Facecam AI modely" if self.current_language == "cs" else "Facecam AI models",
            "Pracovní adresáře aplikace" if self.current_language == "cs" else "App working directories",
        ]
        row_refs = []
        for name in comps:
            row = ctk.CTkFrame(
                self.comp_rows_frame,
                fg_color=loading_bg, corner_radius=6,
                border_width=1, border_color=BORDER_CARD
            )
            row.pack(fill="x", pady=4)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=12, pady=8)
            t_lbl = ctk.CTkLabel(
                info,
                text=f"⣾  {name}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=TEXT_MUTED
            )
            t_lbl.pack(anchor="w")
            s_lbl = ctk.CTkLabel(
                info,
                text="Kontroluji..." if self.current_language == "cs" else "Checking...",
                font=ctk.CTkFont(size=11),
                text_color=TEXT_MUTED
            )
            s_lbl.pack(anchor="w")
            row_refs.append((row, t_lbl, s_lbl))

        spin_idx = [0]

        def tick():
            if not self.winfo_exists() or self._check_gen != my_gen:
                return
            spin_idx[0] = (spin_idx[0] + 1) % len(self._SPINNER)
            f = self._SPINNER[spin_idx[0]]
            for i, (_, t_lbl, _) in enumerate(row_refs):
                try:
                    cur = t_lbl.cget("text")
                    if any(sf in cur for sf in self._SPINNER):
                        t_lbl.configure(text=f"  {comps[i]}".replace("  ", f"{f}  "))
                except Exception:
                    pass
            self.after(80, tick)

        self.after(80, tick)

        results = {}

        def worker():
            import time
            ffp, ffpp = get_ffmpeg_paths()
            results["ffmpeg"] = (bool(ffp and ffpp), ffp, ffpp)
            time.sleep(0.25)

            mdir = get_base_dir() / "models"
            yn = (mdir / "face_detection_yunet_2023mar.onnx").is_file()
            sm = (mdir / "haarcascade_smile.xml").is_file()
            fc = (mdir / "haarcascade_frontalface_default.xml").is_file()
            cnt = sum([yn, sm, fc])
            results["models"] = (cnt == 3, cnt)
            time.sleep(0.15)

            results["dirs"] = True
            results["done"] = True

        threading.Thread(target=worker, daemon=True).start()

        def finalize():
            if not self.winfo_exists() or self._check_gen != my_gen:
                return
            if "done" not in results:
                self.after(80, finalize)
                return

            # --- Row 0: FFmpeg & FFprobe ---
            ffmpeg_ok, fp, fpp = results["ffmpeg"]
            row, t_lbl, s_lbl = row_refs[0]
            row.configure(fg_color=BG_CARD_INNER)
            if ffmpeg_ok:
                t_lbl.configure(text=self.tr("comp_ffmpeg_ok"), text_color="#22C55E")
                s_lbl.configure(text=self.tr("comp_ffmpeg_desc_ok", name=fp.name if fp else ''), text_color=TEXT_BODY)
            else:
                t_lbl.configure(text=self.tr("comp_ffmpeg_fail"), text_color="#EF4444")
                s_lbl.configure(text=self.tr("comp_ffmpeg_desc_fail"), text_color=TEXT_BODY)
                ctk.CTkButton(
                    row, text="" + ("Stáhnout FFmpeg" if self.current_language == "cs" else "Download FFmpeg"),
                    width=135, height=26,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    fg_color=ORANGE_PRIMARY, hover_color=ORANGE_HOVER,
                    text_color="#FFFFFF", command=self._settings_download_ffmpeg_action
                ).pack(side="right", padx=12)

            # --- Row 1: Facecam AI modely ---
            models_ok, models_cnt = results["models"]
            row, t_lbl, s_lbl = row_refs[1]
            row.configure(fg_color=BG_CARD_INNER)
            if models_ok:
                t_lbl.configure(text=self.tr("comp_models_ok"), text_color="#22C55E")
                s_lbl.configure(text=self.tr("comp_models_desc_ok"), text_color=TEXT_BODY)
            else:
                t_lbl.configure(text=self.tr("comp_models_fail", cnt=models_cnt), text_color="#EF4444")
                s_lbl.configure(text=self.tr("comp_models_desc_fail"), text_color=TEXT_BODY)
                ctk.CTkButton(
                    row, text="" + ("Stáhnout modely" if self.current_language == "cs" else "Download models"),
                    width=135, height=26,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    fg_color=ORANGE_PRIMARY, hover_color=ORANGE_HOVER,
                    text_color="#FFFFFF", command=self._settings_download_models_action
                ).pack(side="right", padx=12)

            # --- Row 2: Pracovní adresáře ---
            row, t_lbl, s_lbl = row_refs[2]
            row.configure(fg_color=BG_CARD_INNER)
            t_lbl.configure(text=self.tr("comp_dirs_ok"), text_color="#22C55E")
            s_lbl.configure(text=self.tr("comp_dirs_desc"), text_color=TEXT_BODY)

        self.after(80, finalize)

    def _settings_download_ffmpeg_action(self):
        self._prompt_ffmpeg_download()
        self.after(1500, self._refresh_settings_components)

    def _settings_download_models_action(self):
        finished = [False]
        def worker():
            ensure_ai_models_present()
            finished[0] = True

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if not self.winfo_exists():
                return
            if finished[0]:
                self._refresh_settings_components()
            else:
                self.after(200, poll)

        self.after(200, poll)

    def _check_for_updates(self):
        self.btn_update.configure(state="disabled")
        if hasattr(self, "btn_install_update"):
            self.btn_install_update.configure(state="disabled")
        self.lbl_update_status.configure(
            text="Ověřuji dostupnost nejnovější verze...",
            text_color=TEXT_BODY
        )
        result_holder = {}

        def worker():
            import time
            import urllib.request
            import json
            time.sleep(0.3)

            new_version_found = None
            release_data = None
            repos = ["Pecislav/PecislavStudio", "Pecislav/PeciCut"]
            for repo in repos:
                try:
                    # Query releases list (handles both final releases and prereleases/betas)
                    req = urllib.request.Request(
                        f"https://api.github.com/repos/{repo}/releases",
                        headers={"User-Agent": "PecislavStudio-App"}
                    )
                    with urllib.request.urlopen(req, timeout=4.0) as resp:
                        releases = json.loads(resp.read().decode("utf-8"))
                        if releases and isinstance(releases, list):
                            latest_rel = releases[0]
                            tag = latest_rel.get("tag_name", "").lstrip("v")
                            # If tag is strictly higher or different beta
                            if tag and tag != APP_VERSION.lstrip("v") and tag > APP_VERSION.lstrip("v"):
                                new_version_found = tag
                                release_data = latest_rel
                                break
                            elif tag and not new_version_found:
                                release_data = latest_rel
                except Exception:
                    continue

            self._latest_release_info = release_data
            if new_version_found:
                msg = f"K dispozici je nová verze: Pecislav Studio v{new_version_found}!" if self.current_language == "cs" else f"New version available: Pecislav Studio v{new_version_found}!"
                color = ORANGE_ACCENT_TEXT
                has_update = True
            else:
                msg = f"Používáte verzi Pecislav Studio v{APP_VERSION} (aktuální kód na GitHubu)." if self.current_language == "cs" else f"You are running Pecislav Studio v{APP_VERSION} (latest code on GitHub)."
                color = "#22C55E"
                has_update = False

            result_holder["done"] = (msg, color, has_update)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        def poll():
            if not self.winfo_exists():
                return
            if "done" in result_holder:
                msg, color, has_update = result_holder["done"]
                self.btn_update.configure(state="normal")
                if hasattr(self, "btn_install_update"):
                    self.btn_install_update.configure(state="normal")
                self.lbl_update_status.configure(text=msg, text_color=color)
            else:
                self.after(100, poll)

        self.after(100, poll)

    def _perform_auto_update(self):
        """Downloads updated code or binary from GitHub and updates the application safely."""
        title = "Aktualizace aplikace" if self.current_language == "cs" else "Application Update"
        msg = ("Opravdu si přejete stáhnout a nainstalovat nejnovější verzi z GitHubu?\n\n"
               "Vaše nastavení (config.json) i historie projektů zůstanou plně zachovány.") if self.current_language == "cs" else (
               "Do you want to download and install the latest update from GitHub?\n\n"
               "Your settings (config.json) and project history will be fully preserved.")
        if not messagebox.askyesno(title, msg, parent=self):
            return

        self.btn_update.configure(state="disabled")
        if hasattr(self, "btn_install_update"):
            self.btn_install_update.configure(state="disabled")

        self.lbl_update_status.configure(
            text="Stahuji aktualizaci z GitHubu...",
            text_color=ORANGE_PRIMARY
        )

        result_holder = {}

        def update_worker():
            import zipfile
            import urllib.request

            # 1. If running as compiled standalone .exe (PyInstaller frozen)
            if getattr(sys, "frozen", False):
                try:
                    exe_path = Path(sys.executable).resolve()
                    exe_dir = exe_path.parent

                    download_url = None
                    rel_info = getattr(self, "_latest_release_info", None)
                    if rel_info and "assets" in rel_info:
                        for asset in rel_info["assets"]:
                            name = asset.get("name", "").lower()
                            if name.endswith(".exe"):
                                download_url = asset.get("browser_download_url")
                                break

                    if not download_url:
                        download_url = "https://github.com/Pecislav/PecislavStudio/releases/download/v1.0.0-beta/PecislavStudio.exe"

                    req = urllib.request.Request(
                        download_url,
                        headers={"User-Agent": "PecislavStudio-Updater"}
                    )

                    new_exe = exe_dir / f"{exe_path.stem}_new.exe"
                    with urllib.request.urlopen(req, timeout=180) as resp, open(new_exe, "wb") as f_out:
                        shutil.copyfileobj(resp, f_out)

                    bat_path = exe_dir / "update_and_restart.bat"
                    bat_content = f"""@echo off
timeout /t 1 /nobreak > nul
move /y "{new_exe.name}" "{exe_path.name}"
start "" "{exe_path.name}"
del "%~f0"
"""
                    bat_path.write_text(bat_content, encoding="utf-8")

                    result_holder["done"] = (True, "Aplikace byla úspěšně aktualizována na novou verzi.")
                    self._restart_bat_script = str(bat_path)
                    return
                except Exception as e:
                    result_holder["done"] = (False, f"Aktualizace .exe selhala: {e}")
                    return

            # 2. If running from source (Python)
            app_dir = Path(__file__).parent.resolve()

            # Try Git pull if in a git repository
            if (app_dir / ".git").is_dir() and shutil.which("git"):
                try:
                    cflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
                    sinfo = None
                    if sys.platform.startswith("win"):
                        sinfo = subprocess.STARTUPINFO()
                        sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        sinfo.wShowWindow = 0
                    res = subprocess.run(
                        ["git", "pull", "--ff-only"],
                        cwd=str(app_dir),
                        capture_output=True,
                        text=True,
                        startupinfo=sinfo,
                        creationflags=cflags,
                        timeout=25
                    )
                    if res.returncode == 0:
                        result_holder["done"] = (True, "Aplikace byla úspěšně aktualizována přes Git repository.")
                        return
                except Exception:
                    pass

            # Direct ZIP download from GitHub repository
            try:
                zip_url = "https://github.com/Pecislav/PecislavStudio/archive/refs/heads/main.zip"
                req = urllib.request.Request(
                    zip_url,
                    headers={"User-Agent": "PecislavStudio-Updater"}
                )

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    zip_file = tmp_path / "update.zip"

                    with urllib.request.urlopen(req, timeout=40) as resp, open(zip_file, "wb") as f_out:
                        shutil.copyfileobj(resp, f_out)

                    with zipfile.ZipFile(zip_file, "r") as zf:
                        zf.extractall(tmp_path)

                    extracted = [d for d in tmp_path.iterdir() if d.is_dir() and d != zip_file]
                    if not extracted:
                        result_holder["done"] = (False, "Chyba při rozbalení archivu aktualizace.")
                        return

                    source_dir = extracted[0]

                    # Safe copy: copy files into app_dir, preserving configs & caches
                    protected = {"config.json", ".git", ".project_cache", "output", "videos", "__pycache__"}

                    for item in source_dir.iterdir():
                        if item.name in protected:
                            continue
                        dest = app_dir / item.name
                        if item.is_dir():
                            shutil.copytree(item, dest, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dest)

                result_holder["done"] = (True, "Soubory aplikace byly úspěšně aktualizovány na nejnovější verzi.")
            except Exception as e:
                result_holder["done"] = (False, f"Stažení selhalo: {e}")

        t = threading.Thread(target=update_worker, daemon=True)
        t.start()

        def poll_update():
            if not self.winfo_exists():
                return
            if "done" in result_holder:
                success, note = result_holder["done"]
                self.btn_update.configure(state="normal")
                if hasattr(self, "btn_install_update"):
                    self.btn_install_update.configure(state="normal")

                if success:
                    self.lbl_update_status.configure(
                        text="Aktualizace byla úspěšně nainstalována!",
                        text_color="#22C55E"
                    )
                    t_succ = "Aktualizace dokončena" if self.current_language == "cs" else "Update Completed"
                    m_succ = ("Pecislav Studio bylo úspěšně aktualizováno na nejnovější verzi.\n\n"
                              "Přejete si aplikaci restartovat nyní pro načtení změn?") if self.current_language == "cs" else (
                              "Pecislav Studio was successfully updated to the latest version.\n\n"
                              "Do you want to restart the application now?")
                    if messagebox.askyesno(t_succ, m_succ, parent=self):
                        self._restart_app()
                else:
                    self.lbl_update_status.configure(
                        text=f"Aktualizace selhala ({note})",
                        text_color="#EF4444"
                    )
                    messagebox.showerror(
                        "Chyba aktualizace" if self.current_language == "cs" else "Update Error",
                        f"Nepodařilo se dokončit automatickou aktualizaci:\n{note}"
                    )
            else:
                self.after(200, poll_update)

        self.after(200, poll_update)

    def _restart_app(self):
        """Cleanly restarts the application."""
        bat_script = getattr(self, "_restart_bat_script", None)
        if bat_script and Path(bat_script).is_file():
            try:
                cflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
                subprocess.Popen(["cmd.exe", "/c", str(bat_script)], cwd=str(Path(bat_script).parent), creationflags=cflags)
                self.destroy()
                sys.exit(0)
            except Exception:
                pass
        try:
            self.destroy()
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception:
            try:
                cflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
                subprocess.Popen([sys.executable] + sys.argv, creationflags=cflags)
                sys.exit(0)
            except Exception:
                pass

    def _build_file_section(self, parent):
        """1. File picker and metadata display."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        # Header row with title, ? button, and Project History button
        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        self.lbl_sec_file = ctk.CTkLabel(
            hdr,
            text=self.tr("sec_file_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_sec_file.pack(side="left")

        q_btn = self._create_help_btn(
            hdr,
            text=(
                "Vyberte video soubor z vašeho streamu nebo nahrávání (.mp4, .mkv nebo .mov).\n\n"
                "PeciCut podporuje i velmi dlouhé soubory (2 až 6+ hodin). Video se načítá bezztrátově "
                "a analyzuje přímo v paměti bez vytváření obřích souborů na disku."
            ),
            recommendation="Nahrajte MP4 nebo MKV soubor z OBS Studia o délce 2 až 6 hodin."
        )
        q_btn.pack(side="left", padx=(8, 0))

        t_hist = "Historie projektů" if self.current_language == "cs" else "Project History"
        self.btn_open_history = ctk.CTkButton(
            hdr,
            text=t_hist,
            command=self._open_history_dialog,
            height=28,
            width=140,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=BG_CARD_INNER,
            hover_color=("#E5E7EB", "#252834"),
            text_color=ORANGE_PRIMARY,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=6
        )
        self.btn_open_history.pack(side="right")

        # Interactive Drag & Drop Box
        self.drop_zone = ctk.CTkFrame(
            box,
            fg_color=BG_CARD_INNER,
            corner_radius=8,
            border_width=1,
            border_color=BORDER_CARD
        )
        self.drop_zone.pack(fill="x", padx=16, pady=(4, 10))

        drop_inner = ctk.CTkFrame(self.drop_zone, fg_color="transparent")
        drop_inner.pack(fill="x", padx=14, pady=10)

        btn_txt = self.tr("btn_change_file") if self.current_video_path else self.tr("btn_select_file")
        self.btn_select_file = ctk.CTkButton(
            drop_inner,
            text=btn_txt,
            command=self._on_select_file,
            width=180,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#F3F4F6", "#20222B"),
            hover_color=("#E5E7EB", "#2B2E3B"),
            border_width=1,
            border_color=ORANGE_PRIMARY,
            text_color=TEXT_TITLE
        )
        self.btn_select_file.pack(side="left")

        path_box = ctk.CTkFrame(drop_inner, fg_color="transparent")
        path_box.pack(side="left", fill="x", expand=True, padx=(14, 10))

        self.lbl_file_path = ctk.CTkLabel(
            path_box,
            text=self.tr("no_file_selected"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_BODY,
            anchor="w"
        )
        self.lbl_file_path.pack(anchor="w")

        self.lbl_dnd_hint = ctk.CTkLabel(
            path_box,
            text=self.tr("dnd_drop_hint"),
            font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED,
            anchor="w"
        )
        self.lbl_dnd_hint.pack(anchor="w", pady=(2, 0))

        # Register Drag & Drop targets across the drop zone and the window
        if getattr(self, "_dnd_ready", False) and DND_FILES is not None:
            try:
                targets = [self.drop_zone, drop_inner, path_box, self.lbl_file_path, self.lbl_dnd_hint, box, self]
                for target in targets:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind('<<Drop>>', self._on_file_drop)
                    target.dnd_bind('<<DropEnter>>', self._on_drop_enter)
                    target.dnd_bind('<<DropPosition>>', self._on_drop_position)
                    target.dnd_bind('<<DropLeave>>', self._on_drop_leave)
            except Exception:
                pass

        # Video metadata summary card
        self.meta_card = ctk.CTkFrame(box, fg_color=BG_CARD_INNER, corner_radius=8, border_width=1, border_color=BORDER_CARD)
        self.meta_card.pack(fill="x", padx=16, pady=(0, 14))

        self.lbl_meta_info = ctk.CTkLabel(
            self.meta_card,
            text=self.tr("meta_info_placeholder"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY,
            anchor="w"
        )
        self.lbl_meta_info.pack(padx=12, pady=8, anchor="w")

    def _on_drop_enter(self, event=None):
        self._dnd_active = True
        if hasattr(self, "drop_zone"):
            self.drop_zone.configure(
                border_color=ORANGE_PRIMARY,
                border_width=2,
                fg_color=("#FFE8D6", "#28170B")
            )
        if hasattr(self, "lbl_file_path"):
            t = "Pusťte video soubor zde pro načtení!" if self.current_language == "cs" else "Release video file here to load!"
            self.lbl_file_path.configure(text=t, text_color=ORANGE_PRIMARY)
        if hasattr(self, "lbl_dnd_hint"):
            t_sub = "Aplikace video okamžitě načte a připraví" if self.current_language == "cs" else "App will immediately load and prepare video"
            self.lbl_dnd_hint.configure(text=t_sub, text_color=TEXT_TITLE)
        self._animate_drop_pulse(0)
        return getattr(event, "action", "copy") if event else "copy"

    def _on_drop_position(self, event=None):
        return getattr(event, "action", "copy") if event else "copy"

    def _animate_drop_pulse(self, step: int):
        if not getattr(self, "_dnd_active", False) or not hasattr(self, "drop_zone"):
            return
        widths = [2, 3, 2, 1]
        w = widths[step % len(widths)]
        try:
            self.drop_zone.configure(border_width=w)
            self._pulse_job = self.after(160, lambda: self._animate_drop_pulse(step + 1))
        except Exception:
            pass

    def _on_drop_leave(self, event=None):
        self._dnd_active = False
        if hasattr(self, "_pulse_job") and self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None

        if hasattr(self, "drop_zone"):
            self.drop_zone.configure(
                border_color=BORDER_CARD,
                border_width=1,
                fg_color=BG_CARD_INNER
            )
        self._update_drop_zone_labels()
        return getattr(event, "action", "copy") if event else "copy"

    def _update_drop_zone_labels(self):
        if self.current_video_path and self.current_video_path.is_file():
            v_name = self.current_video_path.name
            disp_name = v_name if len(v_name) <= 34 else (v_name[:20] + "..." + v_name[-10:])
            if hasattr(self, "lbl_file_path"):
                self.lbl_file_path.configure(text=disp_name, text_color=TEXT_TITLE)
            if hasattr(self, "lbl_dnd_hint"):
                try:
                    size_mb = self.current_video_path.stat().st_size / (1024 * 1024)
                    self.lbl_dnd_hint.configure(
                        text=self.tr("dnd_ready_hint", size=f"{size_mb:.1f}"),
                        text_color=TEXT_MUTED
                    )
                except Exception:
                    pass
        else:
            if hasattr(self, "lbl_file_path"):
                self.lbl_file_path.configure(text=self.tr("no_file_selected"), text_color=TEXT_BODY)
            if hasattr(self, "lbl_dnd_hint"):
                self.lbl_dnd_hint.configure(text=self.tr("dnd_drop_hint"), text_color=TEXT_MUTED)

    def _on_file_drop(self, event):
        self._on_drop_leave()
        data = getattr(event, "data", "")
        if not data:
            return getattr(event, "action", "copy") if event else "copy"

        try:
            candidates = self.tk.splitlist(data)
        except Exception:
            candidates = [data.strip()]

        if not candidates:
            return getattr(event, "action", "copy") if event else "copy"

        candidate = candidates[0].strip()
        p = Path(candidate)
        if not p.is_file():
            messagebox.showwarning(
                "Neplatný soubor" if self.current_language == "cs" else "Invalid File",
                f"Přetažený soubor nebyl nalezen:\n{candidate}"
            )
            return getattr(event, "action", "copy") if event else "copy"

        ext = p.suffix.lower()
        valid_exts = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".ts", ".m4v"}
        if ext not in valid_exts:
            messagebox.showwarning(
                "Nepodporovaný formát" if self.current_language == "cs" else "Unsupported Format",
                f"Soubor '{p.name}' není podporované video.\nPodporované formáty: MP4, MKV, MOV, WebM, AVI."
            )
            return getattr(event, "action", "copy") if event else "copy"

        # Success animation flash (green border)
        if hasattr(self, "drop_zone"):
            self.drop_zone.configure(border_color="#22C55E", border_width=2)
            self.after(600, lambda: self.drop_zone.configure(border_color=BORDER_CARD, border_width=1) if hasattr(self, "drop_zone") else None)

        self._load_video_file(str(p))
        return getattr(event, "action", "copy") if event else "copy"

    def _show_dim_overlay(self, title: Optional[str] = None, subtitle: Optional[str] = None):
        """Zobrazí elegantní poloprůhledný závoj přes hlavní okno s kartou informující o otevřeném editoru či dialogu."""
        self._hide_dim_overlay()
        try:
            self.update_idletasks()
            # Ve světlém režimu jemný světlý závoj (#E5E8EB), v tmavém hluboká černá (#0B0C10)
            self._dim_overlay = ctk.CTkFrame(
                self,
                fg_color=("#E5E8EB", "#0B0C10"),
                corner_radius=0
            )
            self._dim_overlay.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
            self._dim_overlay.lift()

            card = ctk.CTkFrame(
                self._dim_overlay,
                fg_color=("#FFFFFF", "#181A22"),
                corner_radius=14,
                border_width=1,
                border_color=("#CBD5E1", "#2B2E3B")
            )
            card.place(relx=0.5, rely=0.5, anchor="center")

            title_txt = title or ("Editor momentů je otevřen" if self.current_language == "cs" else "Segment Editor is Open")
            sub_txt = subtitle or ("Upravte nebo potvrďte výběr v okně editoru.\nPo dokončení nebo zavření editoru se aplikace odemkne."
                                   if self.current_language == "cs"
                                   else "Review clips in the editor window.\nThe main window will unlock once closed.")

            ctk.CTkLabel(
                card,
                text="◈",
                font=ctk.CTkFont(size=20, weight="bold"),
                text_color=ORANGE_PRIMARY
            ).pack(padx=40, pady=(22, 2))

            ctk.CTkLabel(
                card,
                text=title_txt,
                font=ctk.CTkFont(size=17, weight="bold"),
                text_color=TEXT_TITLE
            ).pack(padx=40, pady=(0, 6))

            ctk.CTkLabel(
                card,
                text=sub_txt,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_BODY,
                justify="center"
            ).pack(padx=40, pady=(0, 24))
        except Exception:
            pass

    def _hide_dim_overlay(self):
        """Skryje ztmavovací vrstvu."""
        if hasattr(self, "_dim_overlay") and self._dim_overlay:
            try:
                self._dim_overlay.destroy()
            except Exception:
                pass
            self._dim_overlay = None

    def _open_history_dialog(self):
        """Otevře samostatné okno s historií projektů pro výběr videa."""
        t_hist_title = "Historie projektů je otevřena" if self.current_language == "cs" else "Project History is Open"
        t_hist_sub = ("Vyberte video pro úpravu v editoru nebo zavřete okno historie pro návrat."
                      if self.current_language == "cs"
                      else "Select a video to edit in the editor or close the history window to return.")
        self._show_dim_overlay(title=t_hist_title, subtitle=t_hist_sub)

        ProjectHistoryDialog(
            parent=self,
            config=self.config,
            on_open_project=self._open_project_from_history,
            on_clear_history=self._clear_history,
            on_close=self._hide_dim_overlay,
            current_lang=self.current_language
        )

    def _open_project_from_history(self, item: Dict):
        """Načte zpracovaný projekt z historie a okamžitě otevře Segment Editor."""
        video_str = item.get("video", "")
        if not video_str:
            self._hide_dim_overlay()
            return
        video_path = Path(video_str)
        if not video_path.is_file():
            self._hide_dim_overlay()
            messagebox.showwarning(
                "Soubor nenalezen" if self.current_language == "cs" else "File Not Found",
                f"Video soubor nebyl nalezen na původní cestě:\n{video_str}"
            )
            return

        cache_file_str = item.get("cache_file", "")
        data = None
        if cache_file_str and Path(cache_file_str).is_file():
            try:
                with open(cache_file_str, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None

        if not data:
            cache_dir = Path(__file__).parent / ".project_cache"
            v_hash = hashlib.md5(str(video_path.resolve()).encode("utf-8")).hexdigest()[:12]
            cand = cache_dir / f"{video_path.stem}_{v_hash}.json"
            if cand.is_file():
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = None

        if not data or not data.get("all_segments"):
            self._hide_dim_overlay()
            self._load_video_file(str(video_path))
            messagebox.showinfo(
                "Informace" if self.current_language == "cs" else "Info",
                "Video bylo načteno. Pro tento starší záznam nejsou uloženy náhledové segmenty v cache, spusťte prosím zpracování."
                if self.current_language == "cs"
                else "Video was loaded. Cached moments not found for this older item, please start processing."
            )
            return

        self.current_video_path = video_path
        disp_name = video_path.name if len(video_path.name) <= 34 else (video_path.name[:20] + "..." + video_path.name[-10:])
        self.lbl_file_path.configure(text=disp_name, text_color=TEXT_TITLE)
        if not self.video_metadata:
            self.video_metadata = get_video_metadata(video_path)

        all_segs = [tuple(s) for s in data.get("all_segments", [])]
        rec_segs = [tuple(s) for s in data.get("recommended_segments", all_segs)]
        target_dur = data.get("target_dur_sec")

        self._show_dim_overlay()

        def on_confirmed_from_editor(chosen_segments):
            self._hide_dim_overlay()
            self._start_export_for_segments(video_path, chosen_segments)

        def on_cancelled_from_editor():
            self._hide_dim_overlay()

        dlg = SegmentReviewDialog(
            parent=self,
            video_path=video_path,
            all_segments=all_segs,
            recommended_segments=rec_segs,
            target_duration_sec=target_dur,
            current_lang=self.current_language,
            on_confirm=on_confirmed_from_editor,
            on_cancel=on_cancelled_from_editor
        )
        dlg.lift()
        dlg.focus_force()

    def _start_export_for_segments(self, video_path: Path, segments: List[Tuple]):
        """Spustí export (EDL/MP4) přímo z editoru bez nutnosti re-analyzovat audio."""
        if not segments:
            return

        selected_format_label = self.format_var.get().lower()
        export_edl = "edl" in selected_format_label
        export_mp4 = "mp4" in selected_format_label
        selected_mode_label = self.mode_var.get().lower()
        mode = "highlights" if "highlight" in selected_mode_label else "remove_silence"
        output_dir = self.output_directory or video_path.parent

        self.is_processing = True
        self._proc_start_time = time.time()
        self._last_eta_calc_time = 0.0
        self._cached_eta_str = ""
        self._eta_smoothed = 25.0
        self.cancel_event.clear()
        self.btn_process.configure(state="disabled")
        self.btn_select_file.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.result_card.pack_forget()
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 10))
        self.progress_bar.set(0.0)

        def export_worker():
            try:
                meta = self.video_metadata or get_video_metadata(video_path)
                total_duration = meta.get("duration", 0.0)
                fps = meta.get("fps", 30.0)
                threads = self._get_configured_threads()

                stats = calculate_cut_statistics(total_duration, segments)
                base_name = video_path.stem
                suffix_mode = "highlights" if mode == "highlights" else "nosilence"
                generated_files = []

                if export_edl:
                    self._update_progress(0.20, "Generování CMX 3600 EDL souboru...")
                    edl_path = output_dir / f"{base_name}_PeciCut_{suffix_mode}.edl"
                    generate_cmx3600_edl(
                        segments=segments,
                        video_source_path=video_path,
                        output_edl_path=edl_path,
                        fps=fps,
                        title=f"PECICUT_{suffix_mode.upper()}"
                    )
                    generated_files.append(edl_path)
                    self.last_output_path = edl_path

                if export_mp4:
                    self._update_progress(0.40, "Příprava bezztrátového střihu videa (PeciCut FFmpeg concat)...")
                    def cut_cb(fraction: float, message: str):
                        p = 0.40 + (fraction * 0.58)
                        self._update_progress(p, message)

                    ext = video_path.suffix if video_path.suffix.lower() in [".mp4", ".mkv", ".mov"] else ".mp4"
                    out_video_path = output_dir / f"{base_name}_PeciCut_{suffix_mode}_cut{ext}"
                    cut_res = cut_video_lossless(
                        input_video_path=video_path,
                        segments=segments,
                        output_video_path=out_video_path,
                        threads=threads,
                        progress_callback=cut_cb,
                        cancel_event=self.cancel_event
                    )
                    if self.cancel_event.is_set():
                        self._on_finished_ui(cancelled=True)
                        return
                    if cut_res:
                        generated_files.append(cut_res)
                        self.last_output_path = cut_res

                self._update_progress(1.0, "Export úspěšně dokončen!")
                self._save_project_cache(
                    video_path=video_path,
                    all_segments=segments,
                    recommended_segments=segments,
                    target_dur_sec=None,
                    stats=stats,
                    output_files=generated_files
                )
                self._on_finished_ui(stats=stats, generated_files=generated_files)
            except Exception as e:
                self._on_finished_ui(error_msg=f"Chyba při exportu videa:\n{e}")

        threading.Thread(target=export_worker, daemon=True).start()

    def _save_project_cache(
        self,
        video_path: Path,
        all_segments: List[Tuple],
        recommended_segments: List[Tuple],
        target_dur_sec: Optional[float],
        stats: Optional[Dict] = None,
        output_files: Optional[List[Path]] = None
    ) -> Path:
        """Uloží segmenty a metadata projektu na disk pro okamžitý návrat z historie."""
        cache_dir = Path(__file__).parent / ".project_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        v_str = str(video_path.resolve())
        v_hash = hashlib.md5(v_str.encode("utf-8")).hexdigest()[:12]
        cache_file = cache_dir / f"{video_path.stem}_{v_hash}.json"

        def clean_segs(segs):
            return [[float(x) for x in s] for s in segs]

        date_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        data = {
            "video": v_str,
            "date": date_str,
            "target_dur_sec": target_dur_sec,
            "stats": stats or {},
            "output_files": [str(p) for p in (output_files or [])],
            "all_segments": clean_segs(all_segments),
            "recommended_segments": clean_segs(recommended_segments),
        }

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

        history = self.config.get("history", [])
        history = [h for h in history if h.get("video") != v_str]
        history.append({
            "video": v_str,
            "cache_file": str(cache_file),
            "date": date_str,
            "stats": {
                "original_duration_min": round((stats.get("original_duration_sec", 0) if stats else 0) / 60, 1),
                "output_duration_min": round((stats.get("output_duration_sec", 0) if stats else 0) / 60, 1),
                "total_segments": len(all_segments),
            },
            "output": str(output_files[0]) if output_files else "",
        })
        self.config["history"] = history[-15:]
        save_app_config(self.config)
        return cache_file

    def _open_folder(self, path: Path):
        """Otevře složku ve Finderu / Průzkumníku."""
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            elif platform.system() == "Windows":
                cflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
                subprocess.Popen(["explorer", str(path)], creationflags=cflags)
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    def _clear_history(self):
        self.config["history"] = []
        save_app_config(self.config)

    def _build_audio_track_section(self, parent):
        """2. Audio track dropdown menu."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        self.lbl_sec_audio = ctk.CTkLabel(
            hdr,
            text=self.tr("sec_audio_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_sec_audio.pack(side="left")

        q_btn = self._create_help_btn(
            hdr,
            text=(
                "Klíčové nastavení pro záznamy z OBS Studia!\n\n"
                "OBS typicky nahrává zvuk hry na Stopu 1 a váš mikrofon na Stopu 2 (nebo naopak).\n\n"
                "Vyberte stopu obsahující POUZE váš mikrofon. PeciCut tak bude analyzovat váš hlas, smích a křik, "
                "aniž by byl maten hlasitou střelbou nebo hudbou ze hry."
            ),
            recommendation="Vyberte samostatnou stopu mikrofonu z OBS (často Stopa 2), nikoliv smíchaný zvuk."
        )
        q_btn.pack(side="left", padx=(8, 0))

        self.lbl_sec_audio_sub = ctk.CTkLabel(
            box,
            text=self.tr("sec_audio_sub"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        self.lbl_sec_audio_sub.pack(anchor="w", padx=16, pady=(0, 8))

        self.audio_track_var = ctk.StringVar(value="Stopa 1 (výchozí)")
        self.audio_dropdown = ctk.CTkOptionMenu(
            box,
            values=["Stopa 1 (výchozí)"],
            variable=self.audio_track_var,
            width=540,
            height=36,
            dynamic_resizing=False,
            fg_color=("#F3F4F6", "#20222B"),
            text_color=TEXT_TITLE,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=("#E5E7EB", "#262833"),
            dropdown_text_color=TEXT_TITLE
        )
        self.audio_dropdown.pack(anchor="w", padx=16, pady=(0, 14))

    def _build_parameters_section(self, parent):
        """3. Mode Selection, Sliders, and Target Video Duration."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        # 3.1 Mode Header
        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        self.lbl_sec_params = ctk.CTkLabel(
            hdr,
            text=self.tr("sec_params_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_sec_params.pack(side="left")

        q_btn = self._create_help_btn(
            hdr,
            text=(
                "• Akční highlighty: Vybere pouze nejhlasitější a nejenergičtější momenty (křik, leknutí, smích, hype). "
                "Ideální pro tvorbu zábavného sestřihu z dlouhého streamu.\n\n"
                "• Vyřezat pouze ticho: Zachová celé video v původní chronologii, ale vyřízne mrtvé pasáže, "
                "kdy nikdo nemluví. Vhodné pro zrychlení celých gameplay záznamů."
            ),
            recommendation="Pro YouTube video zvolte 'Akční highlighty'."
        )
        q_btn.pack(side="left", padx=(8, 0))

        # Mode dropdown
        self.mode_var = ctk.StringVar(value="Pouze akcni highlighty (sestřih křiku a reakcí)")
        self.mode_dropdown = ctk.CTkOptionMenu(
            box,
            values=[
                "Pouze akcni highlighty (sestřih křiku a reakcí)",
                "Vyrézat pouze ticho (plná délka bez dlouhých pauz)"
            ],
            variable=self.mode_var,
            command=self._on_mode_dropdown_change,
            width=540,
            height=36,
            dynamic_resizing=False,
            fg_color=("#F3F4F6", "#20222B"),
            text_color=TEXT_TITLE,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=("#E5E7EB", "#262833"),
            dropdown_text_color=TEXT_TITLE
        )
        self.mode_dropdown.pack(anchor="w", padx=16, pady=(0, 10))

        # 3.2 Target Video Duration
        dur_hdr = ctk.CTkFrame(box, fg_color="transparent")
        dur_hdr.pack(fill="x", padx=16, pady=(6, 2))

        self.lbl_dur_heading = ctk.CTkLabel(
            dur_hdr,
            text=self.tr("lbl_target_dur_title"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_dur_heading.pack(side="left")

        q_dur = self._create_help_btn(
            dur_hdr,
            text=(
                "Chcete mít výsledné video o konkrétní délce (např. přesně 10 nebo 15 minut na YouTube)?\n\n"
                "Pokud nastavíte limit délky, PeciCut automaticky seřadí všechny zachycené momenty podle intenzity (hlasitosti) "
                "a vybere jen ty nejlepší hype reakce, které se vejdou do zadaného času!\n\n"
                "Možnost 'Bez limitu' zachová úplně všechny detekované momenty."
            ),
            recommendation="'10 minut' je ideální stopáž pro YouTube. Pro kompletní archiv zvolte 'Bez limitu'."
        )
        q_dur.pack(side="left", padx=(8, 0))

        self.target_dur_var = ctk.StringVar(value="Bez limitu (všechny zachycené momenty)")
        self.target_dur_dropdown = ctk.CTkOptionMenu(
            box,
            values=[
                "Bez limitu (všechny zachycené momenty)",
                "5 minut (rychlý sestřih / TikTok / Shorts kompilace)",
                "10 minut (optimální pro YouTube video)",
                "15 minut (delší YouTube video)",
                "20 minut (rozsáhlý highlight)",
                "30 minut (dlouhá stream kompilace)"
            ],
            variable=self.target_dur_var,
            width=540,
            height=34,
            dynamic_resizing=False,
            fg_color=("#F3F4F6", "#20222B"),
            text_color=TEXT_TITLE,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=("#E5E7EB", "#262833"),
            dropdown_text_color=TEXT_TITLE
        )
        self.target_dur_dropdown.pack(anchor="w", padx=16, pady=(2, 10))

        # 3.3 Slider 1: Loudness Threshold dBFS
        s1_frame = ctk.CTkFrame(box, fg_color="transparent")
        s1_frame.pack(fill="x", padx=16, pady=4)

        self.lbl_thresh_heading = ctk.CTkLabel(
            s1_frame,
            text=self.tr("lbl_threshold"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_thresh_heading.pack(side="left")

        self.q_thresh = self._create_help_btn(
            s1_frame,
            text=(
                "Určuje, jak hlasitý zvuk z mikrofonu musí být, aby se spustilo nahrávání klipu:\n\n"
                "• -10 dBFS: Pouze extrémní řev, panika a výkřiky leknutí.\n"
                "• -14 dBFS (výchozí): Standardní hlasitý křik, záchvat smíchu a hype reakce.\n"
                "• -18 dBFS: Zachytí i běžné mluvení a mírně zvýšený hlas.\n"
                "• -28 až -35 dBFS: Vhodné pro režim vyřezání ticha."
            ),
            recommendation="-14.0 dBFS je ideální střed. Pokud máš tichý mikrofon, zkus -16 dBFS."
        )
        self.q_thresh.pack(side="left", padx=(8, 0))

        self.lbl_threshold_val = ctk.CTkLabel(
            s1_frame,
            text="-14.0 dBFS",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ORANGE_ACCENT_TEXT
        )
        self.lbl_threshold_val.pack(side="right")

        self.slider_threshold = ctk.CTkSlider(
            box,
            from_=-35,
            to=-5,
            number_of_steps=60,
            command=self._on_threshold_slider_change,
            fg_color=TRACK_COLOR,
            progress_color=ORANGE_PRIMARY,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER
        )
        self.slider_threshold.set(-14.0)
        self.slider_threshold.pack(fill="x", padx=16, pady=(0, 8))
        self._disable_slider_mousewheel(self.slider_threshold)

        # 3.4 Padding frame (Before & After sliders side by side)
        pad_container = ctk.CTkFrame(box, fg_color="transparent")
        pad_container.pack(fill="x", padx=16, pady=2)

        # Context Before
        pad_left = ctk.CTkFrame(pad_container, fg_color="transparent")
        pad_left.pack(side="left", fill="x", expand=True, padx=(0, 10))

        p_before_hdr = ctk.CTkFrame(pad_left, fg_color="transparent")
        p_before_hdr.pack(fill="x")
        self.lbl_pad_before_heading = ctk.CTkLabel(p_before_hdr, text=self.tr("lbl_pad_before"), font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_TITLE)
        self.lbl_pad_before_heading.pack(side="left")
        q_p_bef = self._create_help_btn(
            p_before_hdr,
            text=(
                "Kolik sekund videa před začátkem výkřiku má klip obsahovat.\n\n"
                "Například 4 sekundy zajistí, že divák uvidí herní situaci nebo jump scare, který výkřik způsobil."
            ),
            recommendation="4.0 s (ukáže herní akci před výkřikem)"
        )
        q_p_bef.pack(side="left", padx=(6, 0))

        self.lbl_pad_before = ctk.CTkLabel(p_before_hdr, text="4.0 s", text_color=ORANGE_ACCENT_TEXT, font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_pad_before.pack(side="right")

        self.slider_pad_before = ctk.CTkSlider(
            pad_left,
            from_=0,
            to=10,
            number_of_steps=40,
            command=lambda v: self.lbl_pad_before.configure(text=f"{v:.1f} s"),
            fg_color=TRACK_COLOR,
            progress_color=ORANGE_PRIMARY,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER
        )
        self.slider_pad_before.set(4.0)
        self.slider_pad_before.pack(fill="x", pady=(2, 6))
        self._disable_slider_mousewheel(self.slider_pad_before)

        # Context After
        pad_right = ctk.CTkFrame(pad_container, fg_color="transparent")
        pad_right.pack(side="right", fill="x", expand=True, padx=(10, 0))

        p_after_hdr = ctk.CTkFrame(pad_right, fg_color="transparent")
        p_after_hdr.pack(fill="x")
        self.lbl_pad_after_heading = ctk.CTkLabel(p_after_hdr, text=self.tr("lbl_pad_after"), font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_TITLE)
        self.lbl_pad_after_heading.pack(side="left")
        q_p_aft = self._create_help_btn(
            p_after_hdr,
            text=(
                "Kolik sekund videa po skončení výkřiku má klip pokračovat.\n\n"
                "Například 2 sekundy zajistí, že video neusekne doznění smíchu nebo komentář těsně po reakci."
            ),
            recommendation="2.0 s (doznění smíchu a komentáře)"
        )
        q_p_aft.pack(side="left", padx=(6, 0))

        self.lbl_pad_after = ctk.CTkLabel(p_after_hdr, text="2.0 s", text_color=ORANGE_ACCENT_TEXT, font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_pad_after.pack(side="right")

        self.slider_pad_after = ctk.CTkSlider(
            pad_right,
            from_=0,
            to=10,
            number_of_steps=40,
            command=lambda v: self.lbl_pad_after.configure(text=f"{v:.1f} s"),
            fg_color=TRACK_COLOR,
            progress_color=ORANGE_PRIMARY,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER
        )
        self.slider_pad_after.set(2.0)
        self.slider_pad_after.pack(fill="x", pady=(2, 6))
        self._disable_slider_mousewheel(self.slider_pad_after)

        # 3.5 Smart merge gap slider
        gap_frame = ctk.CTkFrame(box, fg_color="transparent")
        gap_frame.pack(fill="x", padx=16, pady=(10, 2))

        gap_hdr = ctk.CTkFrame(gap_frame, fg_color="transparent")
        gap_hdr.pack(fill="x")
        self.lbl_gap_heading = ctk.CTkLabel(
            gap_hdr,
            text=self.tr("lbl_gap"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_gap_heading.pack(side="left")

        q_gap = self._create_help_btn(
            gap_frame,
            text=(
                "Pokud se dvě hlasité reakce odehrají těsně za sebou (např. se zasmějete, na 1 sekundu se nadechnete "
                "a znovu zařvete), PeciCut tyto momenty automaticky spojí do jednoho plynulého klipu.\n\n"
                "Díky tomu se video neseká po půlsekundách a střih působí profesionálně a přirozeně."
            ),
            recommendation="2.0 s zajistí plynulý sestřih bez trhání."
        )
        q_gap.pack(side="left", padx=(6, 0))

        self.lbl_gap_val = ctk.CTkLabel(gap_hdr, text="2.0 s", text_color=ORANGE_ACCENT_TEXT, font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_gap_val.pack(side="right")

        self.slider_gap = ctk.CTkSlider(
            box,
            from_=0,
            to=6,
            number_of_steps=60,
            command=lambda v: self.lbl_gap_val.configure(text=f"{v:.1f} s"),
            fg_color=TRACK_COLOR,
            progress_color=ORANGE_PRIMARY,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER
        )
        self.slider_gap.set(2.0)
        self.slider_gap.pack(fill="x", padx=16, pady=(0, 10))
        self._disable_slider_mousewheel(self.slider_gap)

        # 3.6 Facecam AI Feature Card
        facecam_box = ctk.CTkFrame(box, fg_color=BG_CARD_INNER, corner_radius=8, border_width=1, border_color=BORDER_CARD)
        facecam_box.pack(fill="x", padx=16, pady=(4, 12))

        f_hdr = ctk.CTkFrame(facecam_box, fg_color="transparent")
        f_hdr.pack(fill="x", padx=12, pady=(10, 4))

        self.facecam_ai_var = ctk.BooleanVar(value=True)
        self.chk_facecam_ai = ctk.CTkCheckBox(
            f_hdr,
            text=self.tr("chk_facecam"),
            variable=self.facecam_ai_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            border_color=("#9CA3AF", "#3A3D4D"),
            text_color=TEXT_TITLE
        )
        self.chk_facecam_ai.pack(side="left")

        q_ai = self._create_help_btn(
            f_hdr,
            text=(
                "Jak funguje Facecam AI:\n\n"
                "1. Analýza výrazu obličeje: Hledá v záběru obličej a měří otevření úst (křik, leknutí, údiv) "
                "a široký úsměv (záchvat smíchu).\n\n"
                "2. Detekce pohybu těla a hlavy: Měří kinetickou energii (když streamer nadskočí leknutím, hází hlavou či gestikuluje).\n\n"
                "3. Inteligentní hybridní skóre: Zkombinuje hlasitost audia s reakcí ve webkameře. Momenty s velkou reakcí v obličeji "
                "dostanou nejvyšší prioritu pro finální sestřih, zatímco náhodné zvuky ze hry bez reakce v obličeji jsou odfiltrovány.\n\n"
                " Běží bleskově dvoufázově — skenuje pouze kandidátské momenty (cca 5-10 sekund na 4h video)."
            ),
            recommendation="Ponechte zapnuté pro záznamy s webkamerou. Aplikace automaticky detekuje obličej."
        )
        q_ai.pack(side="left", padx=(8, 0))

        self.sub_facecam = ctk.CTkLabel(
            facecam_box,
            text=self.tr("sub_facecam"),
            font=ctk.CTkFont(size=11),
            text_color=TEXT_BODY
        )
        self.sub_facecam.pack(anchor="w", padx=12, pady=(0, 10))

    def _build_export_section(self, parent):
        """4. Single-choice output format (Dropdown) and destination directory."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        self.lbl_sec_export = ctk.CTkLabel(
            hdr,
            text=self.tr("sec_export_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_sec_export.pack(side="left")

        q_fmt = self._create_help_btn(
            hdr,
            text=(
                "• Hotové MP4 video: Okamžitý bezztrátový střih přes FFmpeg concat demuxer (-c copy). "
                "Zachovává 100% původní kvality obrazu i všechny zvukové stopy, hotovo za 1-2 minuty.\n\n"
                "• EDL Timeline: Vygeneruje soubor CMX 3600 EDL pro DaVinci Resolve a Adobe Premiere Pro. "
                "Umožní vám otevřít hotové střihy přímo v editoru a doladit hudbu, efekty či titulky."
            ),
            recommendation="'Hotové MP4 video' pro okamžité shlédnutí bez práce, 'EDL' pro úpravy v DaVinci/Premiere."
        )
        q_fmt.pack(side="left", padx=(8, 0))

        # Format selector (Dropdown menu)
        self.format_var = ctk.StringVar(value="Hotové MP4 video (rychlý bezztrátový FFmpeg střih)")
        self.format_dropdown = ctk.CTkOptionMenu(
            box,
            values=[
                "Hotové MP4 video (rychlý bezztrátový FFmpeg střih)",
                "EDL Timeline (.edl pro DaVinci Resolve a Premiere Pro)"
            ],
            variable=self.format_var,
            width=540,
            height=36,
            dynamic_resizing=False,
            fg_color=("#F3F4F6", "#20222B"),
            text_color=TEXT_TITLE,
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=("#E5E7EB", "#262833"),
            dropdown_text_color=TEXT_TITLE
        )
        self.format_dropdown.pack(anchor="w", padx=16, pady=(0, 12))

        # Output folder row
        out_row = ctk.CTkFrame(box, fg_color="transparent")
        out_row.pack(fill="x", padx=16, pady=(0, 14))

        self.btn_change_out = ctk.CTkButton(
            out_row,
            text=self.tr("btn_change_out"),
            command=self._on_select_output_dir,
            width=180,
            height=32,
            fg_color=("#F3F4F6", "#20222B"),
            hover_color=("#E5E7EB", "#2B2E3B"),
            border_width=1,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_TITLE
        )
        self.btn_change_out.pack(side="left")

        init_out_text = (
            f"{self.tr('out_dir_custom')}{self.default_export_dir}"
            if self.default_export_dir and Path(self.default_export_dir).is_dir()
            else self.tr("out_dir_default")
        )
        self.lbl_output_dir = ctk.CTkLabel(
            out_row,
            text=init_out_text,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_TITLE if (self.default_export_dir and Path(self.default_export_dir).is_dir()) else TEXT_BODY,
            anchor="w"
        )
        self.lbl_output_dir.pack(side="left", fill="x", expand=True, padx=12)

        # Option A: Interactive review editor & preview checkbox
        self.review_segments_var = ctk.BooleanVar(value=True)
        self.chk_review_segments = ctk.CTkCheckBox(
            box,
            text=self.tr("chk_review_segments"),
            variable=self.review_segments_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            border_color=("#9CA3AF", "#3A3D4D"),
            text_color=TEXT_TITLE
        )
        self.chk_review_segments.pack(anchor="w", padx=16, pady=(2, 2))

        self.sub_review_segments = ctk.CTkLabel(
            box,
            text=self.tr("sub_review_segments"),
            font=ctk.CTkFont(size=11),
            text_color=TEXT_BODY
        )
        self.sub_review_segments.pack(anchor="w", padx=16, pady=(0, 14))

    def _build_progress_section(self, parent):
        """Action button, progress bar, textual feedback, and results card."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        # Buttons row
        btn_row = ctk.CTkFrame(box, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(14, 10))

        self.btn_process = ctk.CTkButton(
            btn_row,
            text=self.tr("btn_process"),
            command=self._on_start_processing,
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF"
        )
        self.btn_process.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_cancel = ctk.CTkButton(
            btn_row,
            text=self.tr("btn_cancel"),
            command=self._on_cancel_processing,
            height=46,
            width=110,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#FEE2E2", "#301616"),
            hover_color=("#FECACA", "#451E1E"),
            text_color=("#DC2626", "#FF6B6B"),
            border_width=1,
            border_color=("#FCA5A5", "#5E2222"),
            state="disabled"
        )
        self.btn_cancel.pack(side="right")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(box, height=14, fg_color=TRACK_COLOR, progress_color=ORANGE_PRIMARY)
        self.progress_bar.pack(fill="x", padx=16, pady=(4, 6))
        self.progress_bar.set(0.0)

        # Status text
        self.lbl_status = ctk.CTkLabel(
            box,
            text=self.tr("status_ready"),
            font=ctk.CTkFont(size=13),
            text_color=TEXT_TITLE
        )
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 10))

        # Result row (Hidden initially - minimal checkmark + folder link)
        self.result_card = ctk.CTkFrame(box, fg_color="transparent")

        self.btn_open_folder = ctk.CTkButton(
            self.result_card,
            text=self.tr("btn_open_folder"),
            command=self._on_open_result_folder,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF",
            corner_radius=6
        )
        self.btn_open_folder.pack(side="left", padx=(0, 14))

        self.lbl_result_check = ctk.CTkLabel(
            self.result_card,
            text=self.tr("lbl_done"),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#22C55E"
        )
        self.lbl_result_check.pack(side="left")

    def _build_footer(self, parent):
        """Bottom status bar."""
        footer_frame = ctk.CTkFrame(parent, height=30, corner_radius=0, fg_color=BG_HEADER)
        footer_frame.pack(fill="x", side="bottom")

        self.lbl_footer = ctk.CTkLabel(
            footer_frame,
            text=f"Pecislav Studio v{APP_VERSION} • Creator Suite by Pecislav • Lossless FFmpeg Engine",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED
        )
        self.lbl_footer.pack(side="left", padx=16, pady=4)

    # -------------------------------------------------------------------------
    # Settings & FFmpeg Management
    # -------------------------------------------------------------------------

    def _open_settings_dialog(self):
        """Switches to the integrated Settings view in Pecislav Studio."""
        self._switch_view("settings")

    def _check_ffmpeg_status(self):
        """Verifies FFmpeg presence and updates the sidebar indicator badge."""
        ffmpeg_path, ffprobe_path = get_ffmpeg_paths()
        if hasattr(self, "sidebar_ffmpeg_pill"):
            if ffmpeg_path and ffprobe_path:
                self.sidebar_ffmpeg_pill.configure(
                    text="FFmpeg připraven",
                    text_color="#22C55E",
                    border_width=1,
                    border_color="#22C55E"
                )
            else:
                self.sidebar_ffmpeg_pill.configure(
                    text="FFmpeg chybí",
                    text_color="#EF4444",
                    border_width=1,
                    border_color="#EF4444"
                )
        if hasattr(self, "comp_rows_frame") and self.comp_rows_frame.winfo_exists():
            self._render_components_static()

    def _on_ffmpeg_status_clicked(self):
        """Opens settings when status clicked."""
        self._open_settings_dialog()

    def _prompt_ffmpeg_download(self):
        """Prompts the user to auto-download FFmpeg if missing."""
        if self.is_downloading_ffmpeg:
            return

        confirm = messagebox.askyesno(
            "Pecislav Studio • Automatické stažení FFmpeg",
            "FFmpeg a FFprobe nebyly v systému nalezeny.\n\n"
            "Chcete, aby Pecislav Studio automaticky stáhl a nastavil FFmpeg do složky aplikace?\n\n"
            "(Vše proběhne na pozadí z oficiálních zdrojů a FFmpeg bude ihned připraven k použití.)"
        )
        if not confirm:
            return

        self._start_ffmpeg_download()

    def _start_ffmpeg_download(self):
        """Launches the automatic download in a background thread."""
        self.is_downloading_ffmpeg = True
        if hasattr(self, "sidebar_ffmpeg_pill"):
            self.sidebar_ffmpeg_pill.configure(
                text="⏳ Stahuji...",
                border_color=ORANGE_PRIMARY,
                text_color=ORANGE_PRIMARY
            )
        self.lbl_status.configure(text="Zahajuji automatické stahování FFmpeg...")
        self.progress_bar.set(0.05)

        self.download_thread = threading.Thread(
            target=self._download_worker,
            daemon=True
        )
        self.download_thread.start()

    def _download_worker(self):
        def progress_cb(fraction: float, message: str):
            self.after(0, lambda: self._update_download_progress(fraction, message))

        success, msg = download_ffmpeg_auto(progress_callback=progress_cb)
        self.after(0, lambda: self._on_download_finished(success, msg))

    def _update_download_progress(self, fraction: float, message: str):
        self.progress_bar.set(min(max(fraction, 0.0), 1.0))
        self.lbl_status.configure(text=message)

    def _on_download_finished(self, success: bool, msg: str):
        self.is_downloading_ffmpeg = False
        self._check_ffmpeg_status()

        if success:
            self.progress_bar.set(1.0)
            self.lbl_status.configure(text="FFmpeg úspěšně nainstalován a připraven!")
            messagebox.showinfo("Hotovo", msg)
        else:
            self.progress_bar.set(0.0)
            self.lbl_status.configure(text="Stažení FFmpeg selhalo.")
            messagebox.showerror("Chyba instalace FFmpeg", f"{msg}\n\nTip: Nainstalujte FFmpeg ručně (brew install ffmpeg na macOS, winget install Gyan.FFmpeg na Windows).")

    # -------------------------------------------------------------------------
    # Helper & Event Handlers
    # -------------------------------------------------------------------------

    def _on_threshold_slider_change(self, value: float):
        self.lbl_threshold_val.configure(text=f"{value:.1f} dBFS")

    def _on_mode_dropdown_change(self, choice: str):
        if "highlighty" in choice.lower():
            self.slider_threshold.set(-14.0)
            self.lbl_threshold_val.configure(text="-14.0 dBFS")
            if hasattr(self, "q_thresh"):
                tt = getattr(self.q_thresh, "_tooltip", None)
                if tt is not None:
                    tt.set_recommendation("-14.0 dBFS je ideální střed. Pokud máš tichý mikrofon, zkus -16 dBFS.")
        else:
            self.slider_threshold.set(-28.0)
            self.lbl_threshold_val.configure(text="-28.0 dBFS")
            if hasattr(self, "q_thresh"):
                tt = getattr(self.q_thresh, "_tooltip", None)
                if tt is not None:
                    tt.set_recommendation("-28.0 dBFS pro ticho (odstraní mrtvé pauzy bez hlasu).")

    def _on_select_file(self):
        """Opens file dialog for video selection and parses metadata."""
        filetypes = [
            ("Video soubory (*.mp4, *.mkv, *.mov, *.webm)", "*.mp4 *.mkv *.mov *.webm *.avi *.MP4 *.MKV *.MOV *.WEBM"),
            ("Všechny soubory", "*.*")
        ]
        chosen = filedialog.askopenfilename(
            title="Vyberte video záznam",
            filetypes=filetypes
        )
        if chosen:
            self._load_video_file(chosen)

    def _load_video_file(self, path: str):
        """Načte vybraný nebo přetažený video soubor a spustí extrakci metadat."""
        video_path = Path(path)
        if not video_path.is_file():
            return

        self.current_video_path = video_path
        disp_name = video_path.name if len(video_path.name) <= 34 else (video_path.name[:20] + "..." + video_path.name[-10:])
        self.lbl_file_path.configure(text=disp_name, text_color=TEXT_TITLE)

        if hasattr(self, "btn_select_file"):
            self.btn_select_file.configure(text=self.tr("btn_change_file"))

        if hasattr(self, "lbl_dnd_hint"):
            try:
                size_mb = video_path.stat().st_size / (1024 * 1024)
                self.lbl_dnd_hint.configure(
                    text=self.tr("dnd_ready_hint", size=f"{size_mb:.1f}"),
                    text_color=TEXT_MUTED
                )
            except Exception:
                pass

        # Apply default export directory if set in config, otherwise default beside video
        if self.default_export_dir and Path(self.default_export_dir).is_dir():
            self.output_directory = Path(self.default_export_dir)
            self.lbl_output_dir.configure(
                text=f"{self.tr('out_dir_custom')}{self.default_export_dir}",
                text_color=TEXT_TITLE
            )
        else:
            self.output_directory = None
            self.lbl_output_dir.configure(
                text=self.tr("out_dir_default"),
                text_color=TEXT_BODY
            )

        # Reset results
        self.result_card.pack_forget()
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 10))
        self.lbl_status.configure(text=f"Načítám metadata souboru {video_path.name}...")

        # Load metadata in background thread
        threading.Thread(target=self._load_metadata_worker, args=(video_path,), daemon=True).start()

    def _load_metadata_worker(self, video_path: Path):
        try:
            meta = get_video_metadata(video_path)
            self.video_metadata = meta
            self.after(0, self._update_metadata_ui, meta)
        except Exception as e:
            self.after(0, lambda: self._show_error(f"Chyba při čtení metadat videa:\n{e}"))

    def _update_metadata_ui(self, meta: Dict):
        duration_sec = meta.get("duration", 0.0)
        h = int(duration_sec // 3600)
        m = int((duration_sec % 3600) // 60)
        s = int(duration_sec % 60)
        dur_str = f"{h}h {m:02d}m {s:02d}s"

        fps = meta.get("fps", 30.0)
        w = meta.get("width", 1920)
        h_res = meta.get("height", 1080)
        codec = meta.get("video_codec", "unknown")
        tracks = meta.get("audio_tracks", [])

        info_text = (
            f"Délka: {dur_str}  |  FPS: {fps:.2f}  |  Rozlišení: {w}x{h_res}  |  "
            f"Video Codec: {codec}  |  Audio stop: {len(tracks)}"
        )
        self.lbl_meta_info.configure(text=info_text, text_color=ORANGE_ACCENT_TEXT)

        # Update audio track dropdown
        if tracks:
            track_labels = [t["label"] for t in tracks]
            self.audio_dropdown.configure(values=track_labels)
            self.audio_track_var.set(track_labels[0])
        else:
            self.audio_dropdown.configure(values=["Žádné audio stopy nenalezeny"])
            self.audio_track_var.set("Žádné audio stopy")

        self.lbl_status.configure(text=self.tr("status_ready"))

    def _on_select_output_dir(self):
        """Allows user to select custom destination folder."""
        folder = filedialog.askdirectory(title=self.tr("sec_export_title"))
        if folder:
            self.output_directory = Path(folder)
            self.lbl_output_dir.configure(
                text=f"{self.tr('out_dir_custom')}{self.output_directory}",
                text_color=TEXT_TITLE
            )

    def _on_cancel_processing(self):
        """Requests cancellation of ongoing analysis/cutting."""
        if self.is_processing:
            self.cancel_event.set()
            self.lbl_status.configure(text="Rušení operace, čekejte prosím...")
            self.btn_cancel.configure(state="disabled")

    def _on_open_result_folder(self):
        """Reveals output files in the OS file explorer."""
        target = self.last_output_path
        if not target and self.output_directory:
            target = self.output_directory
        elif not target and self.current_video_path:
            target = self.current_video_path.parent

        if target:
            open_folder_in_file_manager(target)

    def _show_error(self, message: str):
        messagebox.showerror("Chyba", message)
        self.lbl_status.configure(text=f"Chyba: {message.splitlines()[0]}")

    # -------------------------------------------------------------------------
    # Core Processing Pipeline
    # -------------------------------------------------------------------------

    def _on_start_processing(self):
        """Validates inputs and spawns the background pipeline thread."""
        is_ok, msg = verify_binaries()
        if not is_ok:
            self._prompt_ffmpeg_download()
            return

        if not self.current_video_path or not self.current_video_path.exists():
            messagebox.showwarning("Upozornění", "Nejprve vyberte existující video soubor.")
            return

        selected_format_label = self.format_var.get().lower()
        export_edl = "edl" in selected_format_label
        export_mp4 = "mp4" in selected_format_label

        selected_mode_label = self.mode_var.get().lower()
        mode = "highlights" if "highlight" in selected_mode_label else "remove_silence"

        # Parse target duration
        target_str = self.target_dur_var.get()
        target_duration_sec: Optional[float] = None
        import re
        dur_match = re.search(r"(\d+)\s*min", target_str, re.IGNORECASE)
        if dur_match:
            target_duration_sec = float(dur_match.group(1)) * 60.0

        # Prepare UI for processing state
        self.is_processing = True
        self._proc_start_time = time.time()
        self._last_eta_calc_time = 0.0
        self._cached_eta_str = ""
        dur_sec = self.video_metadata.get("duration", 7200.0) if self.video_metadata else 7200.0
        self._eta_smoothed = max(35.0, (dur_sec / 150.0) + (25.0 if export_mp4 else 5.0))
        self.cancel_event.clear()
        self.btn_process.configure(state="disabled")
        self.btn_select_file.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.result_card.pack_forget()
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 10))
        self.progress_bar.set(0.0)

        # Collect parameters
        track_str = self.audio_track_var.get()
        track_idx = 0
        if self.video_metadata and "audio_tracks" in self.video_metadata:
            for t in self.video_metadata["audio_tracks"]:
                if t["label"] == track_str:
                    track_idx = t["track_index"]
                    break

        params = {
            "video_path": self.current_video_path,
            "track_index": track_idx,
            "threshold_db": float(self.slider_threshold.get()),
            "mode": mode,
            "target_duration_sec": target_duration_sec,
            "padding_before": float(self.slider_pad_before.get()),
            "padding_after": float(self.slider_pad_after.get()),
            "min_gap": float(self.slider_gap.get()),
            "use_facecam_ai": self.facecam_ai_var.get(),
            "open_editor": bool(self.review_segments_var.get()) if hasattr(self, "review_segments_var") else True,
            "export_edl": export_edl,
            "export_mp4": export_mp4,
            "output_dir": self.output_directory or self.current_video_path.parent,
        }

        # Spawn worker thread
        self.processing_thread = threading.Thread(
            target=self._processing_worker,
            args=(params,),
            daemon=True
        )
        self.processing_thread.start()

    def _processing_worker(self, params: Dict):
        """Background thread executing analysis, merging, EDL, and video cutting."""
        video_path: Path = params["video_path"]
        output_dir: Path = params["output_dir"]
        track_idx: int = params["track_index"]
        threshold_db: float = params["threshold_db"]
        mode: str = params["mode"]
        target_dur_sec: Optional[float] = params["target_duration_sec"]
        pad_before: float = params["padding_before"]
        pad_after: float = params["padding_after"]
        min_gap: float = params["min_gap"]
        use_facecam_ai: bool = params.get("use_facecam_ai", False)
        open_editor: bool = params.get("open_editor", True)
        export_edl: bool = params["export_edl"]
        export_mp4: bool = params["export_mp4"]

        try:
            # 1. Inspect metadata if not already available
            if not self.video_metadata:
                self._update_progress(0.05, "Načítání metadat videa...")
                meta = get_video_metadata(video_path)
            else:
                meta = self.video_metadata

            total_duration = meta.get("duration", 0.0)
            fps = meta.get("fps", 30.0)
            threads = self._get_configured_threads()

            # 2. Audio Analysis (FFmpeg streaming + NumPy RMS)
            self._update_progress(0.08, "Zahajuji analýzu hlasitosti audia...")

            def analysis_cb(fraction: float, message: str):
                p = 0.10 + (fraction * 0.52)
                self._update_progress(p, message)

            # Pro cílovou délku (např. 10, 15, 20, 30 min) nasbíráme dostatečně
            # široký pool kandidátních momentů (včetně živého mluvení, smíchu a reakcí),
            # ze kterých následně AI vybere ty nejlepší a nejhlasitější pro naplnění stopáže.
            effective_thresh = threshold_db
            if mode == "highlights" and target_dur_sec and target_dur_sec > 0:
                effective_thresh = min(threshold_db, -17.5)

            raw_segments = analyze_audio_stream(
                video_path=video_path,
                track_index=track_idx,
                total_duration=total_duration,
                threshold_db=effective_thresh,
                mode=mode,
                padding_before=pad_before,
                padding_after=pad_after,
                threads=threads,
                progress_callback=analysis_cb,
                cancel_event=self.cancel_event
            )

            if self.cancel_event.is_set():
                self._on_finished_ui(cancelled=True)
                return

            if not raw_segments:
                self._on_finished_ui(error_msg="Nebyly detekovány žádné momenty odpovídající zadanému prahu hlasitosti.")
                return

            # 3. Intelligent segment merging
            self._update_progress(0.64, f"Inteligentní slučování segmentů (detekováno {len(raw_segments)} kandidátů)...")
            merged_segments = merge_overlapping_segments(
                raw_segments,
                min_gap=min_gap,
                min_duration=0.5
            )

            facecam_active = False
            # 3.5 Facecam AI Vision Pass (if enabled and in highlights mode)
            if use_facecam_ai and mode == "highlights" and merged_segments:
                self._update_progress(0.66, "Příprava Facecam AI (kontrola modelů YuNet a detektoru reakcí)...")
                models_ok = ensure_ai_models_present(
                    progress_callback=lambda msg: self._update_progress(0.66, msg)
                )
                if models_ok:
                    facecam_active = True
                    def ai_progress(pct: float, msg: str):
                        p = 0.67 + (pct / 100.0) * 0.08
                        self._update_progress(p, f"{msg}")

                    merged_segments = analyze_candidate_facecam_segments(
                        video_path=video_path,
                        candidate_segments=merged_segments,
                        sample_fps=2.0,
                        threads=threads,
                        progress_callback=ai_progress,
                        cancel_event=self.cancel_event
                    )

                    if self.cancel_event.is_set():
                        self._on_finished_ui(cancelled=True)
                        return

            all_candidate_segments = list(merged_segments)

            # 4. Limit to target duration if requested (prioritizes highest hype/loudness peaks)
            if target_dur_sec and target_dur_sec > 0:
                self._update_progress(0.70, f"Výběr doporučených momentů pro cílovou délku {int(target_dur_sec//60)} min...")
                recommended_segments = limit_segments_to_target_duration(
                    all_candidate_segments,
                    max_duration_sec=target_dur_sec
                )
            else:
                recommended_segments = list(all_candidate_segments)

            # Uložit do cache a historie po úspěšné audio analýze (proces je hotový)
            self._save_project_cache(
                video_path=video_path,
                all_segments=all_candidate_segments,
                recommended_segments=recommended_segments,
                target_dur_sec=target_dur_sec,
                stats={"original_duration_sec": total_duration, "total_segments": len(all_candidate_segments)},
                output_files=None
            )

            # 4.5 Interactive Segment Review & Video Preview Editor (Option A)
            if open_editor and all_candidate_segments:
                self._update_progress(0.70, self.tr("status_waiting_editor"))
                editor_event = threading.Event()
                editor_result = {"confirmed": False, "segments": []}

                def show_editor():
                    self._show_dim_overlay()
                    dlg = SegmentReviewDialog(
                        parent=self,
                        video_path=video_path,
                        all_segments=all_candidate_segments,
                        recommended_segments=recommended_segments,
                        target_duration_sec=target_dur_sec,
                        current_lang=self.current_language,
                        on_confirm=lambda chosen: on_editor_done(True, chosen),
                        on_cancel=lambda: on_editor_done(False, [])
                    )
                    dlg.lift()
                    dlg.focus_force()

                def on_editor_done(confirmed: bool, chosen: List[Tuple]):
                    self._hide_dim_overlay()
                    editor_result["confirmed"] = confirmed
                    editor_result["segments"] = chosen
                    editor_event.set()

                self.after(0, show_editor)
                editor_event.wait()

                if self.cancel_event.is_set() or not editor_result["confirmed"]:
                    self._on_finished_ui(cancelled=True)
                    return

                merged_segments = editor_result["segments"]
            else:
                merged_segments = recommended_segments

            if not merged_segments:
                self._on_finished_ui(error_msg="Po výběru nezůstal žádný segment k sestříhání.")
                return

            stats = calculate_cut_statistics(total_duration, merged_segments)
            stats["facecam_active"] = facecam_active
            base_name = video_path.stem
            suffix_mode = "highlights" if mode == "highlights" else "nosilence"

            generated_files = []

            # 5. EDL Export
            if export_edl:
                self._update_progress(0.70, "Generování CMX 3600 EDL souboru...")
                edl_filename = f"{base_name}_PeciCut_{suffix_mode}.edl"
                edl_path = output_dir / edl_filename
                generate_cmx3600_edl(
                    segments=merged_segments,
                    video_source_path=video_path,
                    output_edl_path=edl_path,
                    fps=fps,
                    title=f"PECICUT_{suffix_mode.upper()}"
                )
                generated_files.append(edl_path)
                self.last_output_path = edl_path

            # 6. MP4 Lossless Video Cut
            if export_mp4:
                self._update_progress(0.75, "Příprava bezztrátového střihu videa (PeciCut FFmpeg concat)...")

                def cut_cb(fraction: float, message: str):
                    p = 0.75 + (fraction * 0.23)
                    self._update_progress(p, message)

                ext = video_path.suffix if video_path.suffix.lower() in [".mp4", ".mkv", ".mov"] else ".mp4"
                out_video_name = f"{base_name}_PeciCut_{suffix_mode}_cut{ext}"
                out_video_path = output_dir / out_video_name

                cut_res = cut_video_lossless(
                    input_video_path=video_path,
                    segments=merged_segments,
                    output_video_path=out_video_path,
                    threads=threads,
                    progress_callback=cut_cb,
                    cancel_event=self.cancel_event
                )

                if self.cancel_event.is_set():
                    self._on_finished_ui(cancelled=True)
                    return

                if cut_res:
                    generated_files.append(cut_res)
                    self.last_output_path = cut_res

            # 7. Completed successfully
            self._update_progress(1.0, "Zpracování úspěšně dokončeno!")
            self._save_project_cache(
                video_path=video_path,
                all_segments=all_candidate_segments,
                recommended_segments=merged_segments,
                target_dur_sec=target_dur_sec,
                stats=stats,
                output_files=generated_files
            )
            self._on_finished_ui(stats=stats, generated_files=generated_files)

        except Exception as e:
            self._on_finished_ui(error_msg=f"Neočekávaná chyba při zpracování:\n{e}")

    def _update_progress(self, fraction: float, message: str):
        """Thread-safe UI update for progress bar and status label with percentage and conservative ETA."""
        def update():
            clamped = min(max(fraction, 0.0), 1.0)
            self.progress_bar.set(clamped)
            pct = int(round(clamped * 100))

            eta_str = ""
            start_t = getattr(self, "_proc_start_time", None)
            now = time.time()

            if start_t and 0.02 <= clamped < 0.99:
                last_calc = getattr(self, "_last_eta_calc_time", 0.0)
                cached = getattr(self, "_cached_eta_str", "")
                if (now - last_calc) >= 1.2 or not cached:
                    self._last_eta_calc_time = now
                    elapsed = max(0.5, now - start_t)

                    rate = clamped / elapsed
                    raw_remaining = (1.0 - clamped) / max(0.00005, rate)

                    curr_eta = getattr(self, "_eta_smoothed", raw_remaining)
                    # Plynulý odhad bez okamžitého propadu na 1s
                    self._eta_smoothed = 0.85 * curr_eta + 0.15 * raw_remaining

                    rem = int(round(self._eta_smoothed))
                    if rem >= 3600:
                        h, r = divmod(rem, 3600)
                        m = r // 60
                        eta_val = f"~{h}h {m:02d}m"
                    elif rem >= 60:
                        m, s = divmod(rem, 60)
                        eta_val = f"~{m}m {s:02d}s"
                    else:
                        eta_val = f"~{max(2, rem)}s"

                    if self.current_language == "cs":
                        self._cached_eta_str = f" (Zbývá {eta_val})"
                    else:
                        self._cached_eta_str = f" ({eta_val} left)"

                eta_str = getattr(self, "_cached_eta_str", "")

            full_text = f"{pct}%{eta_str} • {message}"
            self.lbl_status.configure(text=full_text)
        self.after(0, update)

    def _on_finished_ui(
        self,
        stats: Optional[Dict] = None,
        generated_files: Optional[List[Path]] = None,
        error_msg: Optional[str] = None,
        cancelled: bool = False
    ):
        """Thread-safe UI restoration after job completion, cancellation, or error."""
        def restore():
            self.is_processing = False
            self.btn_process.configure(state="normal")
            self.btn_select_file.configure(state="normal")
            self.btn_cancel.configure(state="disabled")

            if cancelled:
                self.progress_bar.set(0.0)
                self.result_card.pack_forget()
                self.lbl_status.pack(anchor="w", padx=16, pady=(0, 10))
                self.lbl_status.configure(text="Zpracování bylo zrušeno uživatelem.")
                messagebox.showinfo("Zrušeno", "Operace byla zrušena.")
            elif error_msg:
                self.result_card.pack_forget()
                self.lbl_status.pack(anchor="w", padx=16, pady=(0, 10))
                self.lbl_status.configure(text="Zpracování selhalo.")
                messagebox.showerror("Chyba zpracování", error_msg)
            else:
                self.progress_bar.set(1.0)
                self.lbl_status.pack_forget()
                self.result_card.pack(anchor="w", padx=16, pady=(2, 12))
                if getattr(self, "auto_open_folder", True):
                    self.after(600, self._on_open_result_folder)
                self._refresh_cache_display()

        self.after(0, restore)


def main():
    app = AutoClipApp()
    app.mainloop()


if __name__ == "__main__":
    main()
