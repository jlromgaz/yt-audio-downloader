"""Design tokens (colors, fonts, spacing) for the desktop GUI.

Font families are resolved at runtime against the fonts actually installed
on the host, via ``tkinter.font.families()``. This requires an existing Tk
root window, so ``resolve_fonts()`` must be called after a ``CTk``/``Tk``
root has been created (never at import time).
"""

from __future__ import annotations

import tkinter.font as tkfont
from dataclasses import dataclass

# --- Colors -----------------------------------------------------------------

BG = "#1a1b26"
SURFACE = "#24283b"
PRIMARY = "#7aa2f7"
TEXT = "#c0caf5"
MUTED = "#565f89"
ERROR = "#f7768e"
SUCCESS = "#9ece6a"

# --- Spacing ------------------------------------------------------------------

PAD_S = 6
PAD_M = 12
PAD_L = 20
RADIUS = 8

# --- Font fallback stacks ----------------------------------------------------
# Inter / JetBrains Mono are not guaranteed present on a clean target
# machine, so each token is a fallback stack; the first installed family
# wins, with a Tk built-in default as the last resort.

_TITLE_STACK = ("Inter", "SF Pro Display", "Segoe UI")
_BODY_STACK = ("Inter", "SF Pro Text", "Segoe UI")
_MONO_STACK = ("JetBrains Mono", "Menlo", "Consolas", "Courier New")

_TITLE_SIZE = 22
_BODY_SIZE = 13
_MONO_SIZE = 12


@dataclass(frozen=True)
class FontToken:
    """A resolved (family, size, weight) tuple ready for CTk widgets."""

    family: str
    size: int
    weight: str = "normal"

    def as_tuple(self) -> tuple[str, int, str]:
        return (self.family, self.size, self.weight)


def _first_available_family(stack: tuple[str, ...], available: set[str]) -> str | None:
    for family in stack:
        if family in available:
            return family
    return None


def resolve_fonts() -> dict[str, FontToken]:
    """Resolve FONT_TITLE/FONT_BODY/FONT_MONO against installed fonts.

    Must be called after a Tk root window exists. Falls back to Tk's
    system default font family when no stack entry is installed.
    """
    available = set(tkfont.families())
    default_family = tkfont.nametofont("TkDefaultFont").actual("family")

    title_family = _first_available_family(_TITLE_STACK, available) or default_family
    body_family = _first_available_family(_BODY_STACK, available) or default_family
    mono_family = _first_available_family(_MONO_STACK, available) or "TkFixedFont"

    return {
        "FONT_TITLE": FontToken(title_family, _TITLE_SIZE, "bold"),
        "FONT_BODY": FontToken(body_family, _BODY_SIZE, "normal"),
        "FONT_MONO": FontToken(mono_family, _MONO_SIZE, "normal"),
    }
