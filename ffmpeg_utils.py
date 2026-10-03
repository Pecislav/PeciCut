"""
ffmpeg_utils.py - Multiplatform utility module for locating, managing, and downloading FFmpeg and FFprobe binaries.

This module provides dynamic resolution of FFmpeg and FFprobe binaries across macOS,
Windows, and Linux. It searches:
1. Bundled binaries in PyInstaller temporary folder (sys._MEIPASS).
2. Binaries in the application root or a 'bin' subdirectory.
3. System PATH.
4. Standard operating system directories (e.g. /opt/homebrew/bin, /usr/local/bin).
5. Automatic 1-click download/installation into the local bin/ folder if missing.
"""

from __future__ import annotations

import gzip
import io
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple


def get_base_dir() -> Path:
    """
    Returns the base directory of the application, taking into account
    whether the app is running as a normal Python script or bundled via PyInstaller.
    """
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS"))
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def get_persistent_bin_dir() -> Path:
    """
    Returns a persistent directory for downloaded binaries (FFmpeg/FFprobe/FFplay)
    that persists across app updates, moves, and temporary folder cleanups.
    """
    if platform.system().lower() == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            p = Path(local_app_data) / "PecislavStudio" / "bin"
        else:
            p = Path.home() / ".pecislavstudio" / "bin"
    else:
        p = Path.home() / ".pecislavstudio" / "bin"
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_binary(binary_name: str) -> Optional[Path]:
    """
    Locates a binary (ffmpeg or ffprobe) following multiplatform resolution logic.
    """
    is_windows = platform.system().lower() == "windows"
    executable_name = f"{binary_name}.exe" if is_windows else binary_name

    base_dir = get_base_dir()
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    persistent_bin = get_persistent_bin_dir()

    search_dirs = [
        app_dir,
        app_dir / "bin",
        persistent_bin,
        base_dir,
        base_dir / "bin",
        Path.home() / ".pecislavstudio" / "bin",
        Path.cwd(),
        Path.cwd() / "bin",
    ]

    for directory in search_dirs:
        candidate = directory / executable_name
        if candidate.is_file() and (is_windows or os.access(candidate, os.X_OK)):
            return candidate.resolve()

    system_path = shutil.which(executable_name) or shutil.which(binary_name)
    if system_path:
        return Path(system_path).resolve()

    if not is_windows:
        unix_candidates = [
            Path("/opt/homebrew/bin") / binary_name,
            Path("/usr/local/bin") / binary_name,
            Path("/usr/bin") / binary_name,
            Path("/bin") / binary_name,
            Path.home() / ".local/bin" / binary_name,
        ]
        for candidate in unix_candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate.resolve()

    return None


def get_ffmpeg_paths() -> Tuple[Optional[Path], Optional[Path]]:
    """
    Returns a tuple of (ffmpeg_path, ffprobe_path).
    """
    ffmpeg_path = find_binary("ffmpeg")
    ffprobe_path = find_binary("ffprobe")
    return ffmpeg_path, ffprobe_path


def verify_binaries() -> Tuple[bool, str]:
    """
    Checks whether both ffmpeg and ffprobe are available and functional.
    Returns (is_valid, status_message).
    """
    ffmpeg_path, ffprobe_path = get_ffmpeg_paths()
    missing = []
    if not ffmpeg_path:
        missing.append("ffmpeg")
    if not ffprobe_path:
        missing.append("ffprobe")

    if missing:
        msg = f"Chybí komponenty: {', '.join(missing)}."
        return False, msg

    try:
        startupinfo = None
        cflags = 0
        if platform.system().lower() == "windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            cflags = subprocess.CREATE_NO_WINDOW

        res = subprocess.run(
            [str(ffmpeg_path), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            creationflags=cflags,
            timeout=5,
        )
        if res.returncode != 0:
            return False, f"FFmpeg byl nalezen v {ffmpeg_path}, ale selhalo spuštění."
    except Exception as e:
        return False, f"Chyba při ověřování FFmpeg: {e}"

    return True, f"FFmpeg: {ffmpeg_path}\nFFprobe: {ffprobe_path}"


def open_folder_in_file_manager(folder_path: Path | str) -> bool:
    """
    Cross-platform utility to open a directory in the default OS file explorer
    (Finder on macOS, Explorer on Windows, xdg-open on Linux).
    Ensures the target directory exists before opening.
    """
    try:
        target = Path(folder_path).resolve()
        if target.is_file():
            folder = target.parent
        elif not target.exists() and target.suffix:
            folder = target.parent
        else:
            folder = target

        folder.mkdir(parents=True, exist_ok=True)
        system = platform.system().lower()

        if system == "windows":
            win_target = str(target)
            win_folder = str(folder)
            if target.is_file():
                try:
                    subprocess.Popen(["explorer", f"/select,{win_target}"])
                    return True
                except Exception:
                    pass
            try:
                subprocess.Popen(["explorer", win_folder])
                return True
            except Exception:
                try:
                    os.startfile(win_folder)
                    return True
                except Exception:
                    return False
        elif system == "darwin":
            if target.is_file():
                subprocess.run(["open", "-R", str(target)], check=False)
            else:
                subprocess.run(["open", str(folder)], check=False)
            return True
        else:
            subprocess.run(["xdg-open", str(folder)], check=False)
            return True
    except Exception as e:
        print(f"Error opening folder: {e}", file=sys.stderr)
        return False


def download_ffmpeg_auto(
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[bool, str]:
    """
    Downloads and configures FFmpeg and FFprobe automatically into the application's
    local 'bin/' directory. Works across macOS and Windows.
    """
    system = platform.system().lower()
    bin_dir = get_persistent_bin_dir()

    if progress_callback:
        progress_callback(0.05, "Zjišťuji konfiguraci systému...")

    # Case 1: macOS with Homebrew installed
    if system == "darwin" and shutil.which("brew"):
        if progress_callback:
            progress_callback(0.15, "Instaluji FFmpeg pomocí Homebrew (brew install ffmpeg)...")
        try:
            res = subprocess.run(
                ["brew", "install", "ffmpeg"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if res.returncode == 0:
                is_ok, msg = verify_binaries()
                if is_ok:
                    if progress_callback:
                        progress_callback(1.0, "FFmpeg úspěšně nainstalován přes Homebrew!")
                    return True, "FFmpeg úspěšně nainstalován přes Homebrew."
        except Exception as e:
            print(f"Brew install error: {e}", file=sys.stderr)

    # Case 2: Windows - Download Gyan.dev FFmpeg essentials zip
    if system == "windows":
        zip_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        if progress_callback:
            progress_callback(0.10, "Stahuji balíček FFmpeg pro Windows (gyan.dev)...")

        try:
            req = urllib.request.Request(
                zip_url,
                headers={"User-Agent": "Mozilla/5.0 SnapCutDownloader/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                buffer = io.BytesIO()

                chunk_size = 1024 * 512
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    buffer.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        fraction = 0.10 + 0.70 * (downloaded / total_size)
                        mb_down = downloaded / (1024 * 1024)
                        mb_tot = total_size / (1024 * 1024)
                        progress_callback(fraction, f"Stahuji FFmpeg: {mb_down:.1f} MB / {mb_tot:.1f} MB ({int(fraction*100)}%)")

            if progress_callback:
                progress_callback(0.85, "Rozbaluji binárky ffmpeg.exe a ffprobe.exe...")

            buffer.seek(0)
            with zipfile.ZipFile(buffer) as zf:
                for member in zf.namelist():
                    filename = Path(member).name.lower()
                    if filename in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                        target_file = bin_dir / filename
                        with zf.open(member) as source, open(target_file, "wb") as target:
                            shutil.copyfileobj(source, target)
                        try:
                            local_bin = get_base_dir() / "bin"
                            local_bin.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(target_file, local_bin / filename)
                        except Exception:
                            pass

            is_ok, msg = verify_binaries()
            if is_ok:
                if progress_callback:
                    progress_callback(1.0, "FFmpeg úspěšně stažen a připraven!")
                return True, "FFmpeg úspěšně stažen a připraven."
            return False, f"FFmpeg stažen, ale ověření selhalo: {msg}"

        except Exception as e:
            return False, f"Chyba při stahování pro Windows: {e}"

    # Case 3: macOS direct download from Evermeet.cx
    if system == "darwin":
        try:
            targets = [
                ("ffmpeg", "https://evermeet.cx/ffmpeg/getrelease/zip"),
                ("ffprobe", "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"),
            ]

            for idx, (b_name, url) in enumerate(targets):
                if progress_callback:
                    base_p = 0.20 + (idx * 0.40)
                    progress_callback(base_p, f"Stahuji {b_name} z evermeet.cx...")

                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 SnapCutDownloader/1.0"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    zip_data = resp.read()

                with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                    for member in zf.namelist():
                        if Path(member).name == b_name:
                            dest = bin_dir / b_name
                            with zf.open(member) as src, open(dest, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            # Make executable
                            dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                            # Remove macOS quarantine if applicable
                            subprocess.run(["xattr", "-d", "com.apple.quarantine", str(dest)], check=False)

            is_ok, msg = verify_binaries()
            if is_ok:
                if progress_callback:
                    progress_callback(1.0, "FFmpeg úspěšně stažen a připraven!")
                return True, "FFmpeg úspěšně stažen."
            return False, f"Ověření selhalo: {msg}"

        except Exception as e:
            return False, f"Chyba při stahování pro macOS: {e}\nDoporučujeme v Terminálu spustit: brew install ffmpeg"

    return False, "Automatické stažení není pro tento systém podporováno. Nainstalujte FFmpeg ručně."
