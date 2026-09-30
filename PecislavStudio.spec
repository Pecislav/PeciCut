# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
import os

datas = [('assets', 'assets'), ('models', 'models')]
datas += collect_data_files('customtkinter')
try:
    datas += collect_data_files('tkinterdnd2')
except Exception:
    pass

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PIL', 'PIL.ImageTk', 'cv2', 'numpy', 'tkinterdnd2',
        'customtkinter', 'darkdetect', 'pydub', 'segment_editor',
        'facecam_ai', 'ffmpeg_utils', 'audio_analyzer', 'video_cutter',
        'edl_generator'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PecislavStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt' if os.path.exists('version_info.txt') else None,
    icon=['assets/app_icon.ico'],
)
