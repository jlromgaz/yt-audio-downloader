"""Download YouTube audio as MP3 via yt-dlp, reporting progress/log through
callbacks.

Pure core logic: no tkinter imports. yt-dlp is injected via ``ydl_factory``
so unit tests never touch the network.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from core import binaries

AUDIO_CODEC_DEFAULT = "mp3"
AUDIO_QUALITY = "320"
# yt-dlp's built-in JS-challenge solver needs a remote EJS component to pass
# YouTube's signature/PO-token checks; without it extraction fails with
# "This video is not available" even for valid public videos. Requires a JS
# runtime (deno) reachable on PATH — see binaries.ensure_deno_on_path().
REMOTE_COMPONENTS = ["ejs:github"]
SINGLE_OUTTMPL = "%(title)s.%(ext)s"
PLAYLIST_OUTTMPL = "%(playlist_title)s/%(title)s.%(ext)s"


class DownloadMode(Enum):
    """Whether to download a single item or an entire playlist."""

    SINGLE = "SINGLE"
    PLAYLIST = "PLAYLIST"


@dataclass(frozen=True)
class ProgressEvent:
    """A single progress update translated from a yt-dlp hook payload."""

    status: str  # 'downloading' | 'finished' | 'error'
    filename: str | None
    percent: float | None
    index: int | None
    total: int | None


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of a download() run."""

    ok: bool
    downloaded: int
    skipped: int
    dest: Path
    errors: list[str]
    cancelled: bool = False


class _YdlClient(Protocol):
    """Structural type for the object returned by ``ydl_factory``."""

    def __enter__(self) -> "_YdlClient": ...

    def __exit__(self, *exc_info: object) -> bool | None: ...

    def download(self, urls: list[str]) -> int: ...


class _YdlLogger:
    """Routes yt-dlp log levels to the on_log callback and records error
    messages so download() can count skipped items."""

    def __init__(self, on_log: Callable[[str], None]) -> None:
        self._on_log = on_log
        self.errors: list[str] = []

    def debug(self, msg: str) -> None:
        self._on_log(msg)

    def info(self, msg: str) -> None:
        self._on_log(msg)

    def warning(self, msg: str) -> None:
        self._on_log(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self._on_log(msg)


def _percent_from_bytes(payload: dict) -> float | None:
    downloaded = payload.get("downloaded_bytes")
    total = payload.get("total_bytes") or payload.get("total_bytes_estimate")
    if downloaded is None or not total:
        return None
    return (downloaded / total) * 100


def _progress_event_from_hook_payload(payload: dict) -> ProgressEvent:
    info = payload.get("info_dict") or {}
    return ProgressEvent(
        status=payload.get("status", "downloading"),
        filename=payload.get("filename"),
        percent=_percent_from_bytes(payload),
        index=info.get("playlist_index"),
        total=info.get("n_entries"),
    )


def _make_hook(
    on_progress: Callable[[ProgressEvent], None],
    finished_count: list[int],
    cancel_event: threading.Event | None = None,
) -> Callable[[dict], None]:
    def hook(payload: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            # DownloadCancelled is yt-dlp's documented mechanism for a
            # progress hook to abort the in-flight download cleanly (as
            # opposed to a generic exception, which yt-dlp may treat as a
            # fatal extraction error rather than a graceful stop).
            from yt_dlp.utils import DownloadCancelled

            raise DownloadCancelled("Cancelled by user")

        event = _progress_event_from_hook_payload(payload)
        on_progress(event)
        if event.status == "finished":
            finished_count[0] += 1

    return hook


def _make_postprocessor_hook(
    cancel_event: threading.Event | None = None,
) -> Callable[[dict], None]:
    """Checks cancel_event during postprocessing (ffmpeg MP3 conversion) so
    a cancel request takes effect between postprocessing steps, not only
    between raw-download progress ticks — though it cannot interrupt an
    ffmpeg subprocess already in flight for the current item.

    Deliberately does not count completions here: yt-dlp runs several
    postprocessors per item (audio extraction, metadata embedding, file
    move, ...) and fires 'finished' for each one under a version-dependent
    name (observed as "ExtractAudio", not the "FFmpegExtractAudio" key used
    to *configure* it) — counting here proved unreliable in a live-download
    check. Completion is counted from progress_hooks' raw-stream 'finished'
    event instead; the ffmpeg-missing failure mode this could otherwise
    mask is caught upfront in ``download()`` (see ``_resolve_ffmpeg_or_raise``).
    """

    def hook(payload: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            from yt_dlp.utils import DownloadCancelled

            raise DownloadCancelled("Cancelled by user")

    return hook


def _resolve_ffmpeg_or_raise() -> str:
    resolved = binaries.ffmpeg_path()
    if resolved is None:
        raise RuntimeError(
            "ffmpeg could not be found (checked bundled binaries and system PATH). "
            "MP3 conversion requires ffmpeg to be installed."
        )
    return str(resolved)


def _build_ydl_opts(
    dest: Path,
    mode: DownloadMode,
    codec: str,
    on_log: Callable[[str], None],
    on_progress: Callable[[ProgressEvent], None],
    finished_count: list[int],
    cancel_event: threading.Event | None = None,
) -> tuple[dict, _YdlLogger]:
    noplaylist = mode is DownloadMode.SINGLE
    outtmpl = SINGLE_OUTTMPL if mode is DownloadMode.SINGLE else PLAYLIST_OUTTMPL

    logger = _YdlLogger(on_log)
    hook = _make_hook(on_progress, finished_count, cancel_event)
    pp_hook = _make_postprocessor_hook(cancel_event)

    # Fails fast with a clear error when ffmpeg cannot be resolved at all,
    # instead of silently passing ffmpeg_location=None to yt-dlp — which
    # previously let MP3 conversion fail under ignoreerrors while still
    # being reported as a successful download (see the regression test).
    ffmpeg_location = _resolve_ffmpeg_or_raise()

    opts = {
        "format": "bestaudio/best",
        "paths": {"home": str(dest)},
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": AUDIO_QUALITY,
            }
        ],
        "outtmpl": outtmpl,
        "noplaylist": noplaylist,
        "remote_components": list(REMOTE_COMPONENTS),
        "ffmpeg_location": ffmpeg_location,
        "ignoreerrors": True,
        "quiet": True,
        "logger": logger,
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
    }
    return opts, logger


def _default_ydl_factory(opts: dict) -> _YdlClient:
    import yt_dlp

    return yt_dlp.YoutubeDL(opts)


def download(
    url: str,
    dest: Path,
    mode: DownloadMode,
    codec: str = AUDIO_CODEC_DEFAULT,
    on_log: Callable[[str], None] = lambda msg: None,
    on_progress: Callable[[ProgressEvent], None] = lambda event: None,
    ydl_factory: Callable[[dict], _YdlClient] | None = None,
    cancel_event: threading.Event | None = None,
) -> DownloadResult:
    """Download ``url`` into ``dest`` per ``mode``, reporting progress/log
    via callbacks.

    Per-item failures are handled by yt-dlp's ``ignoreerrors`` and counted
    as skipped in the result; fatal setup errors (bad opts, missing ffmpeg)
    propagate as exceptions. Core never calls ``sys.exit``.

    If ``cancel_event`` is set (from any thread) while a download is in
    flight, the progress hook raises ``yt_dlp.utils.DownloadCancelled`` on
    its next call, which this function catches and reports as a cancelled
    (not failed) result — the caller distinguishes "user cancelled" from
    "download failed" via ``DownloadResult.cancelled``.
    """
    from yt_dlp.utils import DownloadCancelled

    binaries.ensure_deno_on_path()

    finished_count = [0]
    ydl_opts, logger = _build_ydl_opts(
        dest, mode, codec, on_log, on_progress, finished_count, cancel_event
    )
    factory = ydl_factory or _default_ydl_factory

    try:
        with factory(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadCancelled:
        return DownloadResult(
            ok=False,
            downloaded=finished_count[0],
            skipped=len(logger.errors),
            dest=Path(dest),
            errors=list(logger.errors),
            cancelled=True,
        )

    downloaded = finished_count[0]
    skipped = len(logger.errors)
    ok = downloaded > 0 or skipped == 0

    return DownloadResult(
        ok=ok,
        downloaded=downloaded,
        skipped=skipped,
        dest=Path(dest),
        errors=list(logger.errors),
    )


def probe_playlist_count(
    url: str,
    ydl_factory: Callable[[dict], _YdlClient] | None = None,
) -> int | None:
    """Lightweight playlist-size probe using yt-dlp's ``extract_flat`` mode
    (no media download, no ffmpeg). Returns the entry count, or ``None`` if
    it cannot be determined (network error, non-playlist URL, etc.).

    Additive helper for GUI confirmation dialogs; keeps yt-dlp usage
    confined to ``core`` per the core/gui boundary. Never raises — callers
    should treat ``None`` as "unknown count".
    """
    factory = ydl_factory or _default_ydl_factory
    opts = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
        "remote_components": list(REMOTE_COMPONENTS),
    }
    from yt_dlp.utils import YoutubeDLError

    try:
        with factory(opts) as ydl:
            info = ydl.extract_info(url, download=False)  # type: ignore[attr-defined]
    except YoutubeDLError:
        # Base class for every error yt-dlp itself raises (extraction
        # failure, network error, unsupported URL, ...). The probe is
        # best-effort for a confirmation dialog, so these are swallowed
        # into "unknown count" rather than propagated; a genuine bug
        # (e.g. AttributeError from unexpected data) still propagates.
        return None

    if not info:
        return None

    entries = info.get("entries")
    if entries is None:
        return None
    return len(list(entries))
