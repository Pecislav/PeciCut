# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path
import os

block_cipher = None

datas = [
    ('assets', 'assets'),
    ('models', 'models'),
]
datas += collect_data_files('customtkinter')
try:
    datas += collect_data_files('tkinterdnd2')
except Exception:
    pass

hiddenimports = [
    'PIL',
    'PIL.ImageTk',
    'cv2',
    'numpy',
    'tkinterdnd2',
    'customtkinter',
    'darkdetect',
    'pydub',
    'segment_editor',
    'facecam_ai',
    'ffmpeg_utils',
    'audio_analyzer',
    'video_cutter',
    'edl_generator',
]
try:
    hiddenimports += collect_submodules('customtkinter')
except Exception:
    pass
try:
    hiddenimports += collect_submodules('tkinterdnd2')
except Exception:
    pass

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Pecislav Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico' if os.path.exists('assets/app_icon.ico') else None,
    version='version_info.txt' if os.path.exists('version_info.txt') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Pecislav Studio',
)
