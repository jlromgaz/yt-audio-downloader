# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: onefile, windowed build of the YouTube Audio Downloader
GUI, with per-OS ffmpeg/deno vendored binaries and app icon embedded.

Build:
    pyinstaller app.spec

Vendored binaries must already exist (run scripts/fetch_vendor.py first).
Icons must already exist (run scripts/make_icons.py first).
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

REPO_ROOT = Path(SPECPATH).resolve()


def _platform_dir_name() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "win"
    return "linux"


PLATFORM_DIR = _platform_dir_name()
VENDOR_DIR = REPO_ROOT / "vendor" / PLATFORM_DIR

if sys.platform.startswith("win"):
    _ffmpeg_name, _deno_name = "ffmpeg.exe", "deno.exe"
    _icon_path = str(REPO_ROOT / "assets" / "icon.ico")
    # PyInstaller appends .exe on Windows automatically.
    _exe_name = "YouTubeAudioDownloader-windows"
elif sys.platform == "darwin":
    _ffmpeg_name, _deno_name = "ffmpeg", "deno"
    _icon_path = str(REPO_ROOT / "assets" / "icon.icns")
    _exe_name = "YouTubeAudioDownloader-macos"
else:
    _ffmpeg_name, _deno_name = "ffmpeg", "deno"
    _icon_path = str(REPO_ROOT / "assets" / "icon_256.png")
    # Distinct filenames per OS: macOS and Linux onefile binaries otherwise
    # share the identical name "YouTubeAudioDownloader", which collided as
    # GitHub Release assets (one silently overwrote the other) — confirmed
    # on the first real v0.1.0 release, which shipped only 2 of 3 binaries.
    _exe_name = "YouTubeAudioDownloader-linux"

# --add-binary entries: (source path on the build host, destination dir
# inside the onefile bundle, resolved at runtime via sys._MEIPASS by
# core/binaries.py).
binaries = [
    (str(VENDOR_DIR / _ffmpeg_name), "."),
    (str(VENDOR_DIR / _deno_name), "."),
]

datas = collect_data_files("customtkinter")

a = Analysis(
    ["gui/app.py"],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=_exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_path,
)

if sys.platform == "darwin":
    # A bare onefile Mach-O binary (no .app wrapper) is not reliably
    # double-clickable from Finder — confirmed via a real user report: it
    # opened in a generic text editor instead of launching. macOS GUI apps
    # need a proper .app bundle (Contents/MacOS + Info.plist) for Finder
    # and Gatekeeper to recognize and launch them correctly.
    app = BUNDLE(
        exe,
        name=f"{_exe_name}.app",
        icon=_icon_path,
        bundle_identifier="com.jlromgaz.ytaudiodownloader",
        info_plist={"NSHighResolutionCapable": True},
    )
