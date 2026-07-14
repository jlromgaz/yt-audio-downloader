"""Generate raster icon assets (PNG/ICO/ICNS) from ``assets/icon.svg``.

Rasterization strategy (documented honestly, no silent fake success):
  1. Prefer ``cairosvg`` if installed (cross-platform, works on any OS).
  2. Fall back to macOS's built-in ``sips`` CLI (verified working on this
     dev machine, macOS-only).
  3. If neither is available, raise a clear error instead of producing a
     blank/placeholder image.

``.icns`` (macOS) generation additionally requires the ``iconutil`` CLI
(bundled with macOS Xcode command line tools). If it is not present on the
host, the script logs a clear message and skips ``.icns`` generation instead
of crashing — this keeps the script runnable on Windows/Linux CI runners
that only need the ``.ico``/``.png`` outputs.

Usage:
    python scripts/make_icons.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SVG_SOURCE = REPO_ROOT / "assets" / "icon.svg"
ASSETS_DIR = REPO_ROOT / "assets"

# Sizes used for the individual PNG exports and embedded in the .ico/.icns.
PNG_SIZES = (16, 32, 64, 128, 256, 512)

# macOS .iconset requires this exact filename -> pixel size mapping.
ICONSET_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
}


def _rasterize_with_cairosvg(svg_path: Path, size: int, out_path: Path) -> bool:
    """Try rendering with cairosvg. Returns False if the library is absent."""
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        return False

    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(out_path),
        output_width=size,
        output_height=size,
    )
    return True


def _rasterize_with_sips(svg_path: Path, size: int, out_path: Path) -> bool:
    """Render with macOS's built-in ``sips`` CLI. macOS-only, verified on
    this dev machine (Darwin). Returns False on any other platform or if
    ``sips`` is unavailable."""
    if sys.platform != "darwin" or shutil.which("sips") is None:
        return False

    # sips rasterizes SVG at its intrinsic size; resample to the target
    # size in a second pass via Pillow for exact dimensions.
    with tempfile.TemporaryDirectory(prefix="make_icons_") as tmp_dir:
        raw_png = Path(tmp_dir) / "raw.png"
        subprocess.run(
            ["sips", "-s", "format", "png", str(svg_path), "--out", str(raw_png)],
            check=True,
            capture_output=True,
        )
        with Image.open(raw_png) as img:
            resized = img.resize((size, size), Image.LANCZOS)
            resized.save(out_path, format="PNG")
    return True


def rasterize_png(svg_path: Path, size: int, out_path: Path) -> None:
    """Rasterize the SVG to a square PNG of ``size`` pixels.

    Raises RuntimeError if no rasterization backend is available — this
    script never writes a fake/placeholder image on failure.
    """
    if _rasterize_with_cairosvg(svg_path, size, out_path):
        return
    if _rasterize_with_sips(svg_path, size, out_path):
        return
    raise RuntimeError(
        "No SVG rasterization backend available. Install 'cairosvg' "
        "(pip install cairosvg) for cross-platform support, or run this "
        "script on macOS where 'sips' is used as a fallback."
    )


def generate_pngs() -> dict[int, Path]:
    """Generate assets/icon_<size>.png for every size in PNG_SIZES."""
    pngs: dict[int, Path] = {}
    for size in PNG_SIZES:
        out_path = ASSETS_DIR / f"icon_{size}.png"
        rasterize_png(SVG_SOURCE, size, out_path)
        pngs[size] = out_path
        print(f"[ok] wrote {out_path.relative_to(REPO_ROOT)} ({size}x{size})")
    return pngs


def generate_ico(pngs: dict[int, Path]) -> None:
    """Build assets/icon.ico (Windows) from the generated PNGs via Pillow."""
    ico_sizes = [s for s in PNG_SIZES if s <= 256]  # ICO format caps at 256
    base_size = max(ico_sizes)
    out_path = ASSETS_DIR / "icon.ico"
    with Image.open(pngs[base_size]) as base_img:
        base_img.save(
            out_path,
            format="ICO",
            sizes=[(s, s) for s in ico_sizes],
        )
    print(f"[ok] wrote {out_path.relative_to(REPO_ROOT)} (sizes: {ico_sizes})")


def generate_icns(pngs: dict[int, Path]) -> None:
    """Build assets/icon.icns (macOS) via ``iconutil``.

    Requires the ``iconutil`` CLI (ships with macOS / Xcode command line
    tools). If unavailable, logs a clear message and returns without
    raising — this is a documented, graceful skip, not a fake success.
    """
    if shutil.which("iconutil") is None:
        print(
            "[skip] 'iconutil' not found on this machine. .icns generation "
            "requires macOS with Xcode command line tools installed "
            "(xcode-select --install). Skipping .icns output."
        )
        return

    with tempfile.TemporaryDirectory(prefix="make_icons_iconset_") as tmp_dir:
        iconset_dir = Path(tmp_dir) / "icon.iconset"
        iconset_dir.mkdir()

        for filename, size in ICONSET_FILES.items():
            if size not in pngs:
                # Regenerate any @2x size not already produced by PNG_SIZES.
                out_path = iconset_dir / filename
                rasterize_png(SVG_SOURCE, size, out_path)
            else:
                shutil.copy(pngs[size], iconset_dir / filename)

        out_path = ASSETS_DIR / "icon.icns"
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(out_path)],
            check=True,
            capture_output=True,
        )
    print(f"[ok] wrote {out_path.relative_to(REPO_ROOT)}")


def main() -> int:
    if not SVG_SOURCE.exists():
        print(f"[error] source SVG not found: {SVG_SOURCE}")
        return 1

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    pngs = generate_pngs()
    generate_ico(pngs)
    generate_icns(pngs)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
