"""Thin CLI wrapper over core.url_classifier and core.downloader.

Interactive prompt, ASCII banner. All business logic (URL classification,
download options, progress/log routing) lives in core/; this script only
handles user I/O and exit codes.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from core.downloader import DownloadMode, DownloadResult, download
from core.url_classifier import UrlKind, classify

SINGLE_VS_LIST_KINDS = {UrlKind.RADIO_MIX, UrlKind.VIDEO_IN_PLAYLIST}


def check_dependencies() -> None:
    """Check that yt-dlp and ffmpeg are importable/reachable before running."""
    missing = []
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("yt-dlp (install it with: pip install yt-dlp)")

    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg (required to convert audio to MP3; install it and add it to PATH)")

    if missing:
        print("The following dependencies are missing to run the script:")
        for item in missing:
            print(f" - {item}")
        sys.exit(1)


def get_default_download_folder() -> Path:
    """Return the default destination folder for downloaded audio."""
    return Path(os.path.expanduser("~")) / "Downloads" / "YoutubeAudioDownloader"


def prompt_single_vs_list() -> DownloadMode:
    """Ask the user whether to download only this item or the whole list."""
    while True:
        choice = input("> Download only this video, or the whole list? [single/list]: ").strip().lower()
        if choice in ("single", "s"):
            return DownloadMode.SINGLE
        if choice in ("list", "l"):
            return DownloadMode.PLAYLIST
        print("Please answer 'single' or 'list'.")


def resolve_mode(kind: UrlKind) -> DownloadMode | None:
    """Resolve the DownloadMode for a classified URL, prompting when the
    URL kind is ambiguous (RADIO_MIX / VIDEO_IN_PLAYLIST)."""
    if kind == UrlKind.VIDEO:
        return DownloadMode.SINGLE
    if kind == UrlKind.PLAYLIST:
        return DownloadMode.PLAYLIST
    if kind in SINGLE_VS_LIST_KINDS:
        return prompt_single_vs_list()
    return None


def print_progress(text: str) -> None:
    """Print a log line prefixed for readability in the console."""
    print(text)


def result_to_exit_code(result: DownloadResult) -> int:
    """Map a DownloadResult to a process exit code."""
    return 0 if result.ok else 1


def main() -> int:
    print("========================================")
    print("      YouTube Audio Downloader")
    print("========================================\n")

    check_dependencies()

    url = input("> Enter the YouTube link (individual video or playlist): ").strip()
    if not url:
        print("\nError: You must enter a valid link.")
        return 1

    classification = classify(url)
    if classification.kind == UrlKind.INVALID:
        print("\nError: This does not look like a valid YouTube link.")
        return 1

    mode = resolve_mode(classification.kind)
    if mode is None:
        print("\nError: Could not determine a download mode for this link.")
        return 1

    dest = get_default_download_folder()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"\n[+] Audio files will be automatically saved in: {dest}")
    print("\n[~] Starting download and conversion to high-quality MP3...")

    try:
        result = download(
            url=url,
            dest=dest,
            mode=mode,
            on_log=print_progress,
        )
    except Exception as exc:  # noqa: BLE001 - CLI top-level boundary reports any failure
        print(f"\n[ERROR] An error occurred during download or conversion: {exc}")
        return 1

    if result.ok:
        print(f"\n[OK] Process completed successfully! Audio files have been saved in: {dest}")
        if result.skipped:
            print(f"[i] {result.skipped} item(s) were skipped (private/deleted/unavailable).")
    else:
        print(f"\n[ERROR] Download finished with errors: {result.errors}")

    return result_to_exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
