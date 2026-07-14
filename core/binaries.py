"""Resolve ffmpeg/deno binaries across dev and frozen (PyInstaller) execution.

Resolution order: frozen ``sys._MEIPASS`` -> ``vendor/<platform>/`` -> system
PATH via ``shutil.which``. Pure filesystem/env lookups, no tkinter, no
network.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FFMPEG_BINARY_NAME = "ffmpeg"
DENO_BINARY_NAME = "deno"


def _platform_dir_name() -> str:
    """Map the running platform to its vendor sub-directory name."""
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "win"
    return "linux"


def _executable_name(base_name: str) -> str:
    """Append the platform-specific executable suffix."""
    if sys.platform.startswith("win"):
        return f"{base_name}.exe"
    return base_name


def _frozen_dir() -> Path | None:
    """Return the PyInstaller onefile extraction dir, if running frozen."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return None


def _vendor_dir() -> Path:
    """Return the dev-mode vendored binaries directory for this platform."""
    return PROJECT_ROOT / "vendor" / _platform_dir_name()


def _resolve_binary(base_name: str) -> Path | None:
    """Resolve a binary by name using the frozen -> vendor -> PATH order."""
    exe_name = _executable_name(base_name)

    frozen_dir = _frozen_dir()
    if frozen_dir is not None:
        candidate = frozen_dir / exe_name
        if candidate.exists():
            return candidate

    vendor_candidate = _vendor_dir() / exe_name
    if vendor_candidate.exists():
        return vendor_candidate

    found = shutil.which(base_name)
    if found:
        return Path(found)

    return None


def ffmpeg_path() -> Path | None:
    """Resolve the ffmpeg binary path, or None if unresolvable."""
    return _resolve_binary(FFMPEG_BINARY_NAME)


def deno_dir() -> Path | None:
    """Resolve the directory containing the deno binary, or None."""
    deno_path = _resolve_binary(DENO_BINARY_NAME)
    if deno_path is None:
        return None
    return deno_path.parent


def ensure_deno_on_path() -> None:
    """Prepend the resolved deno directory to PATH, if not already present."""
    directory = deno_dir()
    if directory is None:
        return

    dir_str = str(directory)
    current_path = os.environ.get("PATH", "")
    parts = current_path.split(os.pathsep) if current_path else []
    if dir_str in parts:
        return

    os.environ["PATH"] = os.pathsep.join([dir_str, *parts]) if parts else dir_str
