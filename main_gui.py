"""
main_gui.py - PeciCut: Creator-focused video highlight cutter with modern CustomTkinter GUI.

Features:
- Target duration limitation (e.g. 5, 10, 15, 20, 30 min or unlimited), prioritizing loudest hype moments.
- Recommended initial values clearly stated under every single setting.
- Interactive question mark (?) help buttons explaining each feature in plain language.
- Pixel-perfect vertical centering of the "PRO CREATOR" badge.
- 1-click automatic FFmpeg downloader & status indicator with ❌ / ✓ feedback.
- Clean dropdown selectors for mode, duration, and output format.
- Sliders protected against accidental mousewheel/trackpad scrolling.
- Branded as PeciCut with custom Twitch/YouTube creator theme.
"""

from __future__ import annotations

import os
import platform
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

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

# -----------------------------------------------------------------------------
# Creator Branding Theme Colors (Orange / Matte Black)
# -----------------------------------------------------------------------------
BG_WINDOW = "#0D0E12"          # Hluboká matná černá
BG_HEADER = "#131419"          # Hlavička a patička
BG_CARD = "#17181F"            # Hlavní karty sekcí
BG_CARD_INNER = "#111216"      # Vnitřní rámečky (metadata / výsledky)
BORDER_CARD = "#232530"        # Decentní ohraničení karet

ORANGE_PRIMARY = "#FF6D00"     # Energická Twitch/YT oranžová
ORANGE_HOVER = "#FF851A"       # Světlejší hover oranžová
ORANGE_ACTIVE = "#E65A00"      # Kliknutí / aktivní stav
ORANGE_SUBTLE = "#28170B"      # Podbarvení badge / tagů
ORANGE_ACCENT_TEXT = "#FF8C26" # Oranžový text pro hodnoty a čísla

TEXT_TITLE = "#FFFFFF"         # Bílý text nadpisů
TEXT_BODY = "#9FA6B3"          # Tlumený text popisků
TEXT_MUTED = "#606675"         # Pomocné texty a tipy
TEXT_REC = "#E08A3C"           # Teplá oranžovo-zlatá pro doporučení
TRACK_COLOR = "#242630"        # Pozadí dráhy sliderů a progress baru
BORDER_SUBTLE = "#363947"      # Ohraničení tlačítek a přepínačů

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

        # Subtle dark matte frame with creator orange accent border
        frame = tk.Frame(
            tw,
            bg="#13141B",
            highlightthickness=1,
            highlightbackground="#FF6D00",
            padx=12,
            pady=10
        )
        frame.pack()

        font_family = "Segoe UI" if tk.TkVersion >= 8.6 and sys.platform.startswith("win") else "Helvetica"

        # Main explanation text (soft, slightly translucent/muted typography)
        lbl = tk.Label(
            frame,
            text=self.text,
            justify="left",
            font=(font_family, 11),
            fg="#C2C7D0",
            bg="#13141B",
            wraplength=self.max_width
        )
        lbl.pack(anchor="w")

        hover_targets = [tw, frame, lbl]

        # Recommendation section (if present): Distinct warm amber shade + bold typography
        if self.recommendation:
            # Elegant thin separator
            sep = tk.Frame(frame, height=1, bg="#262936")
            sep.pack(fill="x", pady=(10, 8))

            # Recommendation container with subtle dark-amber background
            rec_box = tk.Frame(
                frame,
                bg="#231A13",
                highlightthickness=1,
                highlightbackground="#5C3414",
                padx=10,
                pady=7
            )
            rec_box.pack(fill="x", anchor="w")

            rec_text = self.recommendation
            if not rec_text.startswith("💡"):
                rec_text = f"💡 Doporučení: {rec_text}"

            rec_lbl = tk.Label(
                rec_box,
                text=rec_text,
                justify="left",
                font=(font_family, 10, "bold"),
                fg="#FFA439",  # Teplá zářivá oranžovo-zlatá pro doporučení
                bg="#231A13",
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


class AutoClipApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window settings
        self.title("PeciCut 🎬 Highlight Cutter")
        self.geometry("940x860")
        self.minsize(860, 720)
        self.configure(fg_color=BG_WINDOW)

        # Application state
        self.current_video_path: Optional[Path] = None
        self.output_directory: Optional[Path] = None
        self.video_metadata: Optional[Dict] = None
        self.processing_thread: Optional[threading.Thread] = None
        self.download_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.is_processing = False
        self.is_downloading_ffmpeg = False
        self.last_output_path: Optional[Path] = None

        # Build UI
        self._build_header()
        self._build_footer()
        self._build_main_scrollable_container()
        self._setup_smooth_scrolling()

        # Check FFmpeg availability at launch
        self._check_ffmpeg_status()


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
            fg_color="#262833",
            hover_color=ORANGE_PRIMARY,
            text_color="#B4B9C7"
        )
        tooltip = ModernTooltip(btn, text=text, recommendation=recommendation)
        btn._tooltip = tooltip
        return btn

    def _setup_smooth_scrolling(self):
        """
        Configures high-performance, smooth 1:1 hardware scrolling for the scrollable frame
        with collision guards on boundaries to completely prevent stuttering at the end.
        """
        canvas = self.scroll_frame._parent_canvas
        orig_yview = canvas.yview

        def safe_yview(*args):
            if not args:
                return orig_yview()
            ModernTooltip.hide_all()
            if args[0] == "scroll" and len(args) >= 2:
                try:
                    count = int(args[1])
                    top, bottom = orig_yview()
                    # If at bottom and scrolling down: drop event to avoid stutter/flooding
                    if count > 0 and bottom >= 0.999:
                        return "break"
                    # If at top and scrolling up: drop event
                    if count < 0 and top <= 0.001:
                        return "break"
                except Exception:
                    pass
            return orig_yview(*args)

        canvas.yview = safe_yview

        # Allow smooth scrolling over all widgets (buttons, labels, cards, sliders)
        # except when user is explicitly dragging the scrollbar thumb itself
        def custom_check_valid_scroll(widget):
            try:
                if isinstance(widget, ctk.windows.widgets.ctk_scrollbar.CTkScrollbar):
                    return False
            except Exception:
                pass
            return True

        self.scroll_frame._check_if_valid_scroll = custom_check_valid_scroll

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

    def _build_header(self):
        """Top banner with PeciCut branding and FFmpeg status/download badge."""
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=BG_HEADER)
        header_frame.pack(fill="x", padx=0, pady=0)

        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side="left", padx=24, pady=16)

        # Title row using grid for pixel-perfect vertical centering of PRO CREATOR
        title_row = ctk.CTkFrame(title_container, fg_color="transparent")
        title_row.pack(anchor="w")

        # Check for custom logo in assets/logo.png
        assets_dir = get_base_dir() / "assets"
        logo_path = assets_dir / "logo.png"
        self.logo_image = None

        col = 0
        if logo_path.is_file():
            try:
                from PIL import Image
                pil_img = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(
                    light_image=pil_img,
                    dark_image=pil_img,
                    size=(36, 36)
                )
                img_lbl = ctk.CTkLabel(title_row, text="", image=self.logo_image)
                img_lbl.grid(row=0, column=col, padx=(0, 10), sticky="w")
                col += 1
                title_text = "PeciCut"
            except Exception as e:
                print(f"Chyba při načítání loga: {e}", file=sys.stderr)
                title_text = "✂️ PeciCut"
        else:
            title_text = "✂️ PeciCut"

        title_lbl = ctk.CTkLabel(
            title_row,
            text=title_text,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=TEXT_TITLE
        )
        title_lbl.grid(row=0, column=col, sticky="w")
        col += 1

        # Perfectly vertically centered "PRO CREATOR" badge
        tag_lbl = ctk.CTkLabel(
            title_row,
            text="PRO CREATOR",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#0D0E12",
            fg_color=ORANGE_PRIMARY,
            corner_radius=6,
            padx=8,
            pady=3
        )
        tag_lbl.grid(row=0, column=col, padx=(12, 0), sticky="")
        title_row.grid_rowconfigure(0, weight=1)

        subtitle_lbl = ctk.CTkLabel(
            title_container,
            text="Automatický střih dlouhých záznamů (2-6h) z Twitch & YouTube dle mikrofonu",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        subtitle_lbl.pack(anchor="w", pady=(3, 0))

        # FFmpeg status / 1-click download button
        self.btn_ffmpeg_status = ctk.CTkButton(
            header_frame,
            text="FFmpeg: Ověřování...",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ORANGE_SUBTLE,
            text_color=ORANGE_ACCENT_TEXT,
            hover_color="#3A1C0B",
            corner_radius=8,
            height=32,
            command=self._on_ffmpeg_status_clicked
        )
        self.btn_ffmpeg_status.pack(side="right", padx=24, pady=16)

    def _build_main_scrollable_container(self):
        """Scrollable area containing configuration sections."""
        self.scroll_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=12)

        self._build_file_section(self.scroll_frame)
        self._build_audio_track_section(self.scroll_frame)
        self._build_parameters_section(self.scroll_frame)
        self._build_export_section(self.scroll_frame)
        self._build_progress_section(self.scroll_frame)

    def _build_file_section(self, parent):
        """1. File picker and metadata display."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        # Header row with title and ? button
        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        lbl = ctk.CTkLabel(
            hdr,
            text="1. Výběr zdrojového video záznamu",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        lbl.pack(side="left")

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

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 6))

        self.btn_select_file = ctk.CTkButton(
            row,
            text="📁 Procházet soubory...",
            command=self._on_select_file,
            width=180,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#20222B",
            hover_color="#2B2E3B",
            border_width=1,
            border_color=ORANGE_PRIMARY,
            text_color="#FFFFFF"
        )
        self.btn_select_file.pack(side="left")

        self.lbl_file_path = ctk.CTkLabel(
            row,
            text="Zatím nebyl vybrán žádný soubor (.mp4, .mkv, .mov)",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY,
            anchor="w"
        )
        self.lbl_file_path.pack(side="left", fill="x", expand=True, padx=14)

        # Video metadata summary card
        self.meta_card = ctk.CTkFrame(box, fg_color=BG_CARD_INNER, corner_radius=8, border_width=1, border_color=BORDER_CARD)
        self.meta_card.pack(fill="x", padx=16, pady=(0, 14))

        self.lbl_meta_info = ctk.CTkLabel(
            self.meta_card,
            text="ℹ️ Po výběru souboru se zde zobrazí délka, FPS, rozlišení a nalezené audio stopy.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY,
            anchor="w"
        )
        self.lbl_meta_info.pack(padx=12, pady=8, anchor="w")

    def _build_audio_track_section(self, parent):
        """2. Audio track dropdown menu."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        lbl = ctk.CTkLabel(
            hdr,
            text="2. Výběr audio stopy pro analýzu (Mikrofon / Hlas)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        lbl.pack(side="left")

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

        sub = ctk.CTkLabel(
            box,
            text="Vyberte stopu s vaším hlasem, aby se detekoval váš křik a reakce namísto zvuků ze hry.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        sub.pack(anchor="w", padx=16, pady=(0, 8))

        self.audio_track_var = ctk.StringVar(value="Stopa 1 (výchozí)")
        self.audio_dropdown = ctk.CTkOptionMenu(
            box,
            values=["Stopa 1 (výchozí)"],
            variable=self.audio_track_var,
            width=540,
            height=36,
            dynamic_resizing=False,
            fg_color="#20222B",
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color="#262833",
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

        lbl = ctk.CTkLabel(
            hdr,
            text="3. Režim detekce a parametry střihu",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        lbl.pack(side="left")

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
        self.mode_var = ctk.StringVar(value="🔥 Pouze akční highlighty (sestřih křiku a reakcí)")
        self.mode_dropdown = ctk.CTkOptionMenu(
            box,
            values=[
                "🔥 Pouze akční highlighty (sestřih křiku a reakcí)",
                "✂️ Vyřezat pouze ticho (plná délka bez dlouhých pauz)"
            ],
            variable=self.mode_var,
            command=self._on_mode_dropdown_change,
            width=540,
            height=36,
            dynamic_resizing=False,
            fg_color="#20222B",
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color="#262833",
            dropdown_text_color=TEXT_TITLE
        )
        self.mode_dropdown.pack(anchor="w", padx=16, pady=(0, 10))

        # 3.2 Target Video Duration
        dur_hdr = ctk.CTkFrame(box, fg_color="transparent")
        dur_hdr.pack(fill="x", padx=16, pady=(6, 2))

        ctk.CTkLabel(
            dur_hdr,
            text="Cílová maximální délka sestřihu:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_TITLE
        ).pack(side="left")

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

        self.target_dur_var = ctk.StringVar(value="♾️ Bez limitu (všechny zachycené momenty)")
        self.target_dur_dropdown = ctk.CTkOptionMenu(
            box,
            values=[
                "♾️ Bez limitu (všechny zachycené momenty)",
                "⏱️ 5 minut (rychlý sestřih / TikTok / Shorts kompilace)",
                "⏱️ 10 minut (optimální pro YouTube video)",
                "⏱️ 15 minut (delší YouTube video)",
                "⏱️ 20 minut (rozsáhlý highlight)",
                "⏱️ 30 minut (dlouhá stream kompilace)"
            ],
            variable=self.target_dur_var,
            width=540,
            height=34,
            dynamic_resizing=False,
            fg_color="#20222B",
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color="#262833",
            dropdown_text_color=TEXT_TITLE
        )
        self.target_dur_dropdown.pack(anchor="w", padx=16, pady=(2, 10))

        # 3.3 Slider 1: Loudness Threshold dBFS
        s1_frame = ctk.CTkFrame(box, fg_color="transparent")
        s1_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(
            s1_frame,
            text="Práh hlasitosti / řevu (dBFS):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_TITLE
        ).pack(side="left")

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
            from_=-35.0,
            to=-5.0,
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
        ctk.CTkLabel(p_before_hdr, text="Kontext před peakem:", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_TITLE).pack(side="left")
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
            from_=0.0,
            to=10.0,
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
        ctk.CTkLabel(p_after_hdr, text="Kontext po peaku:", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_TITLE).pack(side="left")
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
            from_=0.0,
            to=10.0,
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
        ctk.CTkLabel(
            gap_hdr,
            text="Inteligentní sloučení (spojit momenty s mezerou menší než):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_TITLE
        ).pack(side="left")

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
            from_=0.5,
            to=6.0,
            number_of_steps=55,
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
            text="🤖 Facecam AI (Analýza výrazu obličeje a smíchu z webkamery)",
            variable=self.facecam_ai_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            border_color="#3A3D4D",
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
                "⚡ Běží bleskově dvoufázově — skenuje pouze kandidátské momenty (cca 5-10 sekund na 4h video)."
            ),
            recommendation="Ponechte zapnuté pro záznamy s webkamerou. Aplikace automaticky detekuje obličej."
        )
        q_ai.pack(side="left", padx=(8, 0))

        sub_ai = ctk.CTkLabel(
            facecam_box,
            text="Kombinuje audio analýzu s počítačovým viděním — prioritizuje nejlepší reakce obličeje, smích a leknutí.",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_BODY
        )
        sub_ai.pack(anchor="w", padx=12, pady=(0, 10))

    def _build_export_section(self, parent):
        """4. Single-choice output format (Dropdown) and destination directory."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        lbl = ctk.CTkLabel(
            hdr,
            text="4. Formát výstupu a cílová složka",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        lbl.pack(side="left")

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
        self.format_var = ctk.StringVar(value="🎥 Hotové MP4 video (rychlý bezztrátový FFmpeg střih)")
        self.format_dropdown = ctk.CTkOptionMenu(
            box,
            values=[
                "🎥 Hotové MP4 video (rychlý bezztrátový FFmpeg střih)",
                "📋 EDL Timeline (.edl pro DaVinci Resolve a Premiere Pro)"
            ],
            variable=self.format_var,
            width=540,
            height=36,
            dynamic_resizing=False,
            fg_color="#20222B",
            button_color=ORANGE_PRIMARY,
            button_hover_color=ORANGE_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color="#262833",
            dropdown_text_color=TEXT_TITLE
        )
        self.format_dropdown.pack(anchor="w", padx=16, pady=(0, 12))

        # Output folder row
        out_row = ctk.CTkFrame(box, fg_color="transparent")
        out_row.pack(fill="x", padx=16, pady=(0, 14))

        self.btn_change_out = ctk.CTkButton(
            out_row,
            text="Změnit výstupní složku...",
            command=self._on_select_output_dir,
            width=180,
            height=32,
            fg_color="#20222B",
            hover_color="#2B2E3B",
            border_width=1,
            border_color=BORDER_SUBTLE,
            text_color="#FFFFFF"
        )
        self.btn_change_out.pack(side="left")

        self.lbl_output_dir = ctk.CTkLabel(
            out_row,
            text="Výstup: Automaticky ve složce se zdrojovým videem",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY,
            anchor="w"
        )
        self.lbl_output_dir.pack(side="left", fill="x", expand=True, padx=12)

    def _build_progress_section(self, parent):
        """Action button, progress bar, textual feedback, and results card."""
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BORDER_CARD)
        box.pack(fill="x", pady=8)

        # Buttons row
        btn_row = ctk.CTkFrame(box, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(14, 10))

        self.btn_process = ctk.CTkButton(
            btn_row,
            text="🚀 Spustit zpracování záznamu",
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
            text="Zrušit",
            command=self._on_cancel_processing,
            height=46,
            width=110,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#301616",
            hover_color="#451E1E",
            text_color="#FF6B6B",
            border_width=1,
            border_color="#5E2222",
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
            text="Připraven k výběru videa.",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_TITLE
        )
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 10))

        # Result row (Hidden initially - minimal checkmark + folder link)
        self.result_card = ctk.CTkFrame(box, fg_color="transparent")

        self.lbl_result_check = ctk.CTkLabel(
            self.result_card,
            text="✓ Hotovo!",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#22C55E"
        )
        self.lbl_result_check.pack(side="left", padx=(0, 14))

        self.btn_open_folder = ctk.CTkButton(
            self.result_card,
            text="📂 Otevřít složku s výsledkem",
            command=self._on_open_result_folder,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF",
            corner_radius=6
        )
        self.btn_open_folder.pack(side="left")

    def _build_footer(self):
        """Bottom status bar."""
        footer_frame = ctk.CTkFrame(self, height=30, corner_radius=0, fg_color=BG_HEADER)
        footer_frame.pack(fill="x", side="bottom")

        self.lbl_footer = ctk.CTkLabel(
            footer_frame,
            text="PeciCut v1.0 • Creator Edition by Peci • Lossless FFmpeg Engine",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED
        )
        self.lbl_footer.pack(side="left", padx=16, pady=4)

    # -------------------------------------------------------------------------
    # FFmpeg Status & 1-Click Auto Downloader
    # -------------------------------------------------------------------------

    def _check_ffmpeg_status(self):
        """Verifies FFmpeg presence and updates the header badge."""
        ffmpeg_path, ffprobe_path = get_ffmpeg_paths()
        if ffmpeg_path and ffprobe_path:
            self.btn_ffmpeg_status.configure(
                text="✓ FFmpeg & FFprobe: Připraveno",
                text_color="#4ADE80",
                fg_color="#132418",
                hover_color="#1A3322"
            )
        else:
            self.btn_ffmpeg_status.configure(
                text="❌ FFmpeg chybí (Klikni pro stažení)",
                text_color="#FFA3A3",
                fg_color="#381414",
                hover_color="#4A1A1A"
            )

    def _on_ffmpeg_status_clicked(self):
        """Called when clicking the FFmpeg status badge."""
        ffmpeg_path, ffprobe_path = get_ffmpeg_paths()
        if ffmpeg_path and ffprobe_path:
            messagebox.showinfo(
                "FFmpeg je připraven",
                f"FFmpeg a FFprobe jsou v pořádku detekovány.\n\n"
                f"FFmpeg: {ffmpeg_path}\n"
                f"FFprobe: {ffprobe_path}"
            )
        else:
            self._prompt_ffmpeg_download()

    def _prompt_ffmpeg_download(self):
        """Prompts the user to auto-download FFmpeg if missing."""
        if self.is_downloading_ffmpeg:
            return

        confirm = messagebox.askyesno(
            "PeciCut • Automatické stažení FFmpeg",
            "FFmpeg a FFprobe nebyly v systému nalezeny.\n\n"
            "Chcete, aby PeciCut automaticky stáhl a nastavil FFmpeg do složky aplikace?\n\n"
            "(Vše proběhne na pozadí z oficiálních zdrojů a FFmpeg bude ihned připraven k použití.)"
        )
        if not confirm:
            return

        self._start_ffmpeg_download()

    def _start_ffmpeg_download(self):
        """Launches the automatic download in a background thread."""
        self.is_downloading_ffmpeg = True
        self.btn_ffmpeg_status.configure(
            text="⏳ Stahuji FFmpeg...",
            fg_color=ORANGE_SUBTLE,
            text_color=ORANGE_ACCENT_TEXT
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
            messagebox.showinfo("Hotovo", f"🎉 {msg}")
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
            if hasattr(self, "q_thresh") and hasattr(self.q_thresh, "_tooltip"):
                self.q_thresh._tooltip.set_recommendation("-14.0 dBFS je ideální střed. Pokud máš tichý mikrofon, zkus -16 dBFS.")
        else:
            self.slider_threshold.set(-28.0)
            self.lbl_threshold_val.configure(text="-28.0 dBFS")
            if hasattr(self, "q_thresh") and hasattr(self.q_thresh, "_tooltip"):
                self.q_thresh._tooltip.set_recommendation("-28.0 dBFS pro ticho (odstraní mrtvé pauzy bez hlasu).")

    def _on_select_file(self):
        """Opens file dialog for video selection and parses metadata."""
        filetypes = [
            ("Video soubory (*.mp4, *.mkv, *.mov)", "*.mp4 *.mkv *.mov *.MP4 *.MKV *.MOV"),
            ("Všechny soubory", "*.*")
        ]
        chosen = filedialog.askopenfilename(
            title="Vyberte video záznam",
            filetypes=filetypes
        )
        if not chosen:
            return

        video_path = Path(chosen)
        self.current_video_path = video_path
        self.lbl_file_path.configure(text=video_path.name, text_color=TEXT_TITLE)
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
            f"📹 Délka: {dur_str}  |  FPS: {fps:.2f}  |  Rozlišení: {w}x{h_res}  |  "
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

        self.lbl_status.configure(text="Video připraveno. Nastavte parametry a klikněte na 'Spustit zpracování'.")

    def _on_select_output_dir(self):
        """Allows user to select custom destination folder."""
        folder = filedialog.askdirectory(title="Vyberte cílovou složku")
        if folder:
            self.output_directory = Path(folder)
            self.lbl_output_dir.configure(
                text=f"Výstup: {self.output_directory}",
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
        if "5 minut" in target_str:
            target_duration_sec = 5.0 * 60.0
        elif "10 minut" in target_str:
            target_duration_sec = 10.0 * 60.0
        elif "15 minut" in target_str:
            target_duration_sec = 15.0 * 60.0
        elif "20 minut" in target_str:
            target_duration_sec = 20.0 * 60.0
        elif "30 minut" in target_str:
            target_duration_sec = 30.0 * 60.0

        # Prepare UI for processing state
        self.is_processing = True
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

            # 2. Audio Analysis (FFmpeg streaming + NumPy RMS)
            self._update_progress(0.08, "Zahajuji analýzu hlasitosti audia...")

            def analysis_cb(fraction: float, message: str):
                p = 0.10 + (fraction * 0.52)
                self._update_progress(p, message)

            raw_segments = analyze_audio_stream(
                video_path=video_path,
                track_index=track_idx,
                total_duration=total_duration,
                threshold_db=threshold_db,
                mode=mode,
                padding_before=pad_before,
                padding_after=pad_after,
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
                self._update_progress(0.66, "🤖 Příprava Facecam AI (kontrola modelů YuNet a detektoru reakcí)...")
                models_ok = ensure_ai_models_present(
                    progress_callback=lambda msg: self._update_progress(0.66, msg)
                )
                if models_ok:
                    facecam_active = True
                    def ai_progress(pct: float, msg: str):
                        p = 0.67 + (pct / 100.0) * 0.08
                        self._update_progress(p, f"🤖 {msg}")

                    merged_segments = analyze_candidate_facecam_segments(
                        video_path=video_path,
                        candidate_segments=merged_segments,
                        sample_fps=2.0,
                        progress_callback=ai_progress,
                        cancel_event=self.cancel_event
                    )

                    if self.cancel_event.is_set():
                        self._on_finished_ui(cancelled=True)
                        return

            # 4. Limit to target duration if requested (prioritizes highest hype/loudness peaks)
            if target_dur_sec and target_dur_sec > 0:
                self._update_progress(0.75, f"Výběr nejlepších momentů pro cílovou délku {int(target_dur_sec//60)} min...")
                merged_segments = limit_segments_to_target_duration(
                    merged_segments,
                    max_duration_sec=target_dur_sec
                )

            if not merged_segments:
                self._on_finished_ui(error_msg="Po sloučení nezůstal žádný segment s dostatečnou délkou.")
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
            self._on_finished_ui(stats=stats, generated_files=generated_files)

        except Exception as e:
            self._on_finished_ui(error_msg=f"Neočekávaná chyba při zpracování:\n{e}")

    def _update_progress(self, fraction: float, message: str):
        """Thread-safe UI update for progress bar and status label."""
        def update():
            self.progress_bar.set(min(max(fraction, 0.0), 1.0))
            self.lbl_status.configure(text=message)
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

        self.after(0, restore)


def main():
    app = AutoClipApp()
    app.mainloop()


if __name__ == "__main__":
    main()
