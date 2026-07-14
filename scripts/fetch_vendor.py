"""Download ffmpeg + deno for the current platform into ``vendor/<platform>/``.

Sources (per design.md):
  - macOS ffmpeg:   evermeet.cx JSON API (static builds)
  - Windows ffmpeg: BtbN/FFmpeg-Builds GitHub releases, gyan.dev documented
                     as a manual fallback if the BtbN asset layout changes
  - Linux ffmpeg:   BtbN/FFmpeg-Builds GitHub releases
  - deno (all OS):  denoland/deno GitHub releases, per-OS/arch zip asset

Verification status (honest, not assumed): this script has been actually
run and verified end-to-end ONLY on macOS (arm64) on the development
machine used to build this feature. The Windows and Linux branches are
believed correct based on the current public asset naming of BtbN's
releases and deno's releases (checked against the live GitHub API while
writing this script), but they have NOT been executed on those platforms
in this session — CI (see .github/workflows/build-release.yml) is expected
to be the first real execution on Windows/Linux runners.

Accepted risk: downloaded binaries are fetched over HTTPS but are not
checksum/signature-verified against a pinned value before being bundled
into the distributed executable. For a personal portfolio project this is
an accepted tradeoff (all three sources are the standard/official
distribution channels for these tools); a hardened version would pin and
verify SHA-256 digests per release.

Usage:
    python scripts/fetch_vendor.py
"""

from __future__ import annotations

import json
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "vendor"

GITHUB_API_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "yt-audio-downloader-fetch-vendor"}
REQUEST_TIMEOUT_S = 60

DENO_RELEASES_URL = "https://api.github.com/repos/denoland/deno/releases/latest"
BTBN_RELEASES_URL = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
EVERMEET_FFMPEG_INFO_URL = "https://evermeet.cx/ffmpeg/info/ffmpeg/release"

# Documented fallback source for Windows ffmpeg if the BtbN asset layout
# ever changes shape; not used by default since BtbN currently works.
GYAN_DEV_FALLBACK_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def _platform_dir_name() -> str:
    """Mirror core.binaries._platform_dir_name() vendor sub-directory naming."""
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "win"
    return "linux"


def _http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=GITHUB_API_HEADERS)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url: str, dest_path: Path) -> None:
    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": GITHUB_API_HEADERS["User-Agent"]})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response, open(dest_path, "wb") as out_file:
        shutil.copyfileobj(response, out_file)


def _reject_path_traversal(member_name: str, target_dir: Path) -> None:
    """Guards against a malicious archive (from a compromised/spoofed
    upstream) writing outside target_dir via '../' or absolute paths in a
    member name (the classic zip/tar-slip path-traversal issue)."""
    resolved = (target_dir / member_name).resolve()
    if not resolved.is_relative_to(target_dir.resolve()):
        raise RuntimeError(f"Refusing to extract archive member outside target directory: {member_name!r}")


def _extract_archive(archive_path: Path, target_dir: Path) -> None:
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                _reject_path_traversal(member, target_dir)
            zf.extractall(target_dir)
    elif "".join(archive_path.suffixes[-2:]) in (".tar.xz", ".tar.gz") or archive_path.suffix in (".xz", ".gz"):
        with tarfile.open(archive_path) as tf:
            if hasattr(tarfile, "data_filter"):
                # Python 3.12+: the hardened 'data' filter also rejects
                # path traversal, device files, and other unsafe members.
                tf.extractall(target_dir, filter="data")
            else:
                for member in tf.getnames():
                    _reject_path_traversal(member, target_dir)
                tf.extractall(target_dir)
    elif archive_path.suffix == ".7z":
        raise RuntimeError(
            "7z extraction is not supported by the standard library; "
            "the macOS ffmpeg fetch path uses the .zip asset instead."
        )
    else:
        raise RuntimeError(f"Unsupported archive format: {archive_path}")


def _find_file(root: Path, name_predicate: Callable[[str], bool]) -> Path | None:
    for candidate in root.rglob("*"):
        if candidate.is_file() and name_predicate(candidate.name):
            return candidate
    return None


def _install_binary(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)
    mode = dest.stat().st_mode
    dest.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  [ok] installed {dest.relative_to(REPO_ROOT)}")


# --- ffmpeg fetchers ----------------------------------------------------------


def fetch_ffmpeg_macos(vendor_dir: Path) -> None:
    """Verified end-to-end on this dev machine (macOS arm64)."""
    print("Fetching ffmpeg (macOS, evermeet.cx)...")
    info = _http_get_json(EVERMEET_FFMPEG_INFO_URL)
    zip_url = info["download"]["zip"]["url"]

    with tempfile.TemporaryDirectory(prefix="fetch_vendor_ffmpeg_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        archive_path = tmp_path / "ffmpeg.zip"
        _download_file(zip_url, archive_path)
        _extract_archive(archive_path, tmp_path)

        ffmpeg_bin = _find_file(tmp_path, lambda name: name == "ffmpeg")
        if ffmpeg_bin is None:
            raise RuntimeError("ffmpeg binary not found inside downloaded archive")

        _install_binary(ffmpeg_bin, vendor_dir / "ffmpeg")


def _btbn_asset_url(name_predicate: Callable[[str], bool]) -> str:
    release = _http_get_json(BTBN_RELEASES_URL)
    for asset in release.get("assets", []):
        if name_predicate(asset["name"]):
            return asset["browser_download_url"]
    raise RuntimeError("No matching BtbN/FFmpeg-Builds asset found for this platform")


def fetch_ffmpeg_windows(vendor_dir: Path) -> None:
    """NOT executed/verified in this session (no Windows host available
    here). Code path is complete and targets BtbN's current stable asset
    naming (ffmpeg-master-latest-win64-gpl.zip); see GYAN_DEV_FALLBACK_URL
    for a manual fallback if BtbN changes shape."""
    print("Fetching ffmpeg (Windows, BtbN/FFmpeg-Builds)... [unverified on this session's host]")
    url = _btbn_asset_url(lambda n: n == "ffmpeg-master-latest-win64-gpl.zip")

    with tempfile.TemporaryDirectory(prefix="fetch_vendor_ffmpeg_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        archive_path = tmp_path / "ffmpeg.zip"
        _download_file(url, archive_path)
        _extract_archive(archive_path, tmp_path)

        ffmpeg_bin = _find_file(tmp_path, lambda name: name == "ffmpeg.exe")
        if ffmpeg_bin is None:
            raise RuntimeError("ffmpeg.exe not found inside downloaded archive")

        _install_binary(ffmpeg_bin, vendor_dir / "ffmpeg.exe")


def fetch_ffmpeg_linux(vendor_dir: Path) -> None:
    """NOT executed/verified in this session (no Linux host available
    here). Code path is complete and targets BtbN's current stable asset
    naming (ffmpeg-master-latest-linux64-gpl.tar.xz)."""
    print("Fetching ffmpeg (Linux, BtbN/FFmpeg-Builds)... [unverified on this session's host]")
    url = _btbn_asset_url(lambda n: n == "ffmpeg-master-latest-linux64-gpl.tar.xz")

    with tempfile.TemporaryDirectory(prefix="fetch_vendor_ffmpeg_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        archive_path = tmp_path / "ffmpeg.tar.xz"
        _download_file(url, archive_path)
        _extract_archive(archive_path, tmp_path)

        ffmpeg_bin = _find_file(tmp_path, lambda name: name == "ffmpeg")
        if ffmpeg_bin is None:
            raise RuntimeError("ffmpeg binary not found inside downloaded archive")

        _install_binary(ffmpeg_bin, vendor_dir / "ffmpeg")


# --- deno fetcher (all platforms) ---------------------------------------------


def _deno_asset_suffix() -> str:
    """Map (platform, machine arch) to deno's release asset target triple."""
    machine = platform.machine().lower()
    is_arm = machine in ("arm64", "aarch64")

    if sys.platform == "darwin":
        return "aarch64-apple-darwin" if is_arm else "x86_64-apple-darwin"
    if sys.platform.startswith("win"):
        return "aarch64-pc-windows-msvc" if is_arm else "x86_64-pc-windows-msvc"
    return "aarch64-unknown-linux-gnu" if is_arm else "x86_64-unknown-linux-gnu"


def fetch_deno(vendor_dir: Path) -> None:
    """Verified end-to-end on this dev machine (macOS arm64). The
    Windows/Linux branches use the same GitHub Releases API and asset
    naming scheme, verified against the live API response while writing
    this script, but not executed on those OSes in this session."""
    print("Fetching deno (GitHub releases)...")
    release = _http_get_json(DENO_RELEASES_URL)
    target_triple = _deno_asset_suffix()
    asset_name = f"deno-{target_triple}.zip"

    asset_url = None
    for asset in release.get("assets", []):
        if asset["name"] == asset_name:
            asset_url = asset["browser_download_url"]
            break
    if asset_url is None:
        raise RuntimeError(f"No deno release asset found matching '{asset_name}'")

    with tempfile.TemporaryDirectory(prefix="fetch_vendor_deno_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        archive_path = tmp_path / asset_name
        _download_file(asset_url, archive_path)
        _extract_archive(archive_path, tmp_path)

        exe_name = "deno.exe" if sys.platform.startswith("win") else "deno"
        deno_bin = _find_file(tmp_path, lambda name, exe_name=exe_name: name == exe_name)
        if deno_bin is None:
            raise RuntimeError(f"{exe_name} not found inside downloaded archive")

        _install_binary(deno_bin, vendor_dir / exe_name)


def main() -> int:
    platform_name = _platform_dir_name()
    vendor_dir = VENDOR_DIR / platform_name
    vendor_dir.mkdir(parents=True, exist_ok=True)

    print(f"Target platform: {platform_name} ({sys.platform}, {platform.machine()})")
    print(f"Vendor directory: {vendor_dir.relative_to(REPO_ROOT)}")

    try:
        if platform_name == "darwin":
            fetch_ffmpeg_macos(vendor_dir)
        elif platform_name == "win":
            fetch_ffmpeg_windows(vendor_dir)
        else:
            fetch_ffmpeg_linux(vendor_dir)

        fetch_deno(vendor_dir)
    except (RuntimeError, OSError) as exc:
        print(f"[error] {exc}")
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
