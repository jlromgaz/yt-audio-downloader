"""Tests for core.downloader.download.

Uses a scripted fake yt-dlp client (no sockets) that records the ydl_opts
passed to it and replays a scripted sequence of progress-hook payloads and
logger calls. Covers spec scenarios: Single video downloaded, Full
playlist, Extraction uses configured remote component. Also satisfies the
threat-matrix row "Subprocess/process integration": the URL flows into the
fake as a data list-arg, and opts never contain a shell string.
"""

from __future__ import annotations

import threading
from pathlib import Path

import core.downloader as downloader
from core.downloader import DownloadMode, DownloadResult, ProgressEvent, download


class ScriptedYoutubeDL:
    """Stub yt-dlp client: records opts and the download() call, replays a
    scripted sequence of progress-hook payloads and logger calls. Mirrors
    real yt-dlp's contract of letting a hook's raised exception propagate
    out of download() uncaught, so cancellation tests exercise the same
    control flow as the real client."""

    def __init__(self, opts: dict, hook_events=None, log_calls=None, pp_events=None) -> None:
        self.opts = opts
        self.download_urls: list[str] | None = None
        self._hook_events = hook_events or []
        self._log_calls = log_calls or []
        # postprocessor_hooks payloads (e.g. FFmpegExtractAudio 'finished'),
        # scripted separately from progress_hooks: real yt-dlp fires these
        # only after a postprocessor actually completes, which is what
        # download() now uses to count a file as truly downloaded (see
        # test_download_only_counts_postprocessor_finished_as_downloaded).
        self._pp_events = pp_events or []

    def __enter__(self) -> "ScriptedYoutubeDL":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def download(self, urls: list[str]) -> int:
        self.download_urls = urls
        logger = self.opts.get("logger")
        for level, msg in self._log_calls:
            getattr(logger, level)(msg)
        for hook in self.opts.get("progress_hooks", []):
            for event in self._hook_events:
                hook(event)
        for pp_hook in self.opts.get("postprocessor_hooks", []):
            for event in self._pp_events:
                pp_hook(event)
        return 0


def make_factory(hook_events=None, log_calls=None, pp_events=None, captured=None):
    def factory(opts: dict) -> ScriptedYoutubeDL:
        instance = ScriptedYoutubeDL(
            opts, hook_events=hook_events, log_calls=log_calls, pp_events=pp_events
        )
        if captured is not None:
            captured.append(instance)
        return instance

    return factory


def test_download_single_mode_sets_noplaylist_true_and_outtmpl(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    opts = captured[0].opts
    assert opts["noplaylist"] is True
    assert opts["outtmpl"] == "%(title)s.%(ext)s"


def test_download_playlist_mode_sets_noplaylist_false_and_outtmpl(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/playlist?list=PLxxx",
        dest=tmp_path,
        mode=DownloadMode.PLAYLIST,
        ydl_factory=make_factory(captured=captured),
    )

    opts = captured[0].opts
    assert opts["noplaylist"] is False
    assert opts["outtmpl"] == "%(playlist_title)s/%(title)s.%(ext)s"


def test_download_configures_remote_components_for_extraction(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    assert captured[0].opts["remote_components"] == ["ejs:github"]


def test_download_sets_format_bestaudio(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    assert captured[0].opts["format"] == "bestaudio/best"


def test_download_sets_paths_home_to_dest(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    assert captured[0].opts["paths"] == {"home": str(tmp_path)}


def test_download_sets_postprocessor_codec_and_quality(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        codec="mp3",
        ydl_factory=make_factory(captured=captured),
    )

    assert captured[0].opts["postprocessors"] == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}
    ]


def test_download_sets_ignoreerrors_true(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    assert captured[0].opts["ignoreerrors"] is True


def test_download_sets_ffmpeg_location_from_binaries(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(downloader.binaries, "ffmpeg_path", lambda: Path("/fake/ffmpeg"))
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    assert captured[0].opts["ffmpeg_location"] == "/fake/ffmpeg"


def test_download_ensures_deno_on_path_before_instantiation(monkeypatch, tmp_path: Path) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(downloader.binaries, "ensure_deno_on_path", lambda: calls.append(True))

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(),
    )

    assert calls == [True]


def test_download_passes_url_as_list_arg_not_shell_string(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    assert captured[0].download_urls == ["https://www.youtube.com/watch?v=abc"]


def test_download_opts_contain_no_shell_string(tmp_path: Path) -> None:
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(captured=captured),
    )

    opts = captured[0].opts
    assert "shell" not in opts
    for value in opts.values():
        if isinstance(value, str):
            assert "&&" not in value
            assert ";" not in value


def test_logger_routes_debug_info_warning_error_to_on_log(tmp_path: Path) -> None:
    logs: list[str] = []
    log_calls = [("debug", "d-msg"), ("info", "i-msg"), ("warning", "w-msg"), ("error", "e-msg")]

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        on_log=logs.append,
        ydl_factory=make_factory(log_calls=log_calls),
    )

    assert logs == ["d-msg", "i-msg", "w-msg", "e-msg"]


def test_hook_maps_downloading_status_to_progress_event_with_percent(tmp_path: Path) -> None:
    events: list[ProgressEvent] = []
    hook_events = [
        {
            "status": "downloading",
            "filename": "video.mp3",
            "downloaded_bytes": 50,
            "total_bytes": 100,
            "info_dict": {"playlist_index": 1, "n_entries": 3},
        }
    ]

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        on_progress=events.append,
        ydl_factory=make_factory(hook_events=hook_events),
    )

    assert events == [
        ProgressEvent(status="downloading", filename="video.mp3", percent=50.0, index=1, total=3)
    ]


def test_hook_maps_finished_status_to_progress_event(tmp_path: Path) -> None:
    events: list[ProgressEvent] = []
    hook_events = [
        {
            "status": "finished",
            "filename": "video.mp3",
            "downloaded_bytes": 100,
            "total_bytes": 100,
            "info_dict": {"playlist_index": 2, "n_entries": 3},
        }
    ]

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        on_progress=events.append,
        ydl_factory=make_factory(hook_events=hook_events),
    )

    assert events == [
        ProgressEvent(status="finished", filename="video.mp3", percent=100.0, index=2, total=3)
    ]


def test_download_counts_finished_hooks_into_downloaded_result(tmp_path: Path) -> None:
    hook_events = [
        {"status": "finished", "filename": "a.mp3", "downloaded_bytes": 1, "total_bytes": 1, "info_dict": {}},
        {"status": "finished", "filename": "b.mp3", "downloaded_bytes": 1, "total_bytes": 1, "info_dict": {}},
    ]

    result = download(
        url="https://www.youtube.com/playlist?list=PLxxx",
        dest=tmp_path,
        mode=DownloadMode.PLAYLIST,
        ydl_factory=make_factory(hook_events=hook_events),
    )

    assert isinstance(result, DownloadResult)
    assert result.downloaded == 2


def test_download_counts_logger_errors_as_skipped_and_continues(tmp_path: Path) -> None:
    hook_events = [
        {"status": "finished", "filename": "a.mp3", "downloaded_bytes": 1, "total_bytes": 1, "info_dict": {}},
    ]
    log_calls = [("error", "ERROR: Video unavailable (private)")]

    result = download(
        url="https://www.youtube.com/playlist?list=PLxxx",
        dest=tmp_path,
        mode=DownloadMode.PLAYLIST,
        ydl_factory=make_factory(hook_events=hook_events, log_calls=log_calls),
    )

    assert result.downloaded == 1
    assert result.skipped == 1
    assert result.errors == ["ERROR: Video unavailable (private)"]
    assert result.ok is True


def test_download_raises_immediately_when_ffmpeg_is_not_resolvable(monkeypatch, tmp_path: Path) -> None:
    # Regression test for a real bug found via a live download: passing
    # ffmpeg_location=None to yt-dlp let postprocessing fail silently under
    # ignoreerrors, and the old counting logic (raw-stream progress
    # 'finished') still reported the item as downloaded with no MP3 ever
    # produced. Failing fast when ffmpeg cannot be resolved at all matches
    # this function's own documented contract ("fatal setup errors ...
    # missing ffmpeg ... propagate as exceptions").
    monkeypatch.setattr(downloader.binaries, "ffmpeg_path", lambda: None)

    import pytest

    with pytest.raises(RuntimeError, match="ffmpeg"):
        download(
            url="https://www.youtube.com/watch?v=abc",
            dest=tmp_path,
            mode=DownloadMode.SINGLE,
            ydl_factory=make_factory(),
        )


def test_download_result_dest_is_the_requested_path(tmp_path: Path) -> None:
    result = download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(),
    )

    assert result.dest == tmp_path


def test_download_result_is_frozen_dataclass(tmp_path: Path) -> None:
    result = download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(),
    )

    import pytest

    with pytest.raises(AttributeError):
        result.ok = False  # type: ignore[misc]


def test_download_result_cancelled_defaults_to_false(tmp_path: Path) -> None:
    result = download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        ydl_factory=make_factory(),
    )

    assert result.cancelled is False


def test_download_hook_raises_download_cancelled_when_event_is_set(tmp_path: Path) -> None:
    # Pre-set cancel_event: the hook must raise before touching on_progress,
    # matching yt-dlp's documented cancellation contract (a progress hook
    # raising DownloadCancelled stops the current download cleanly).
    from yt_dlp.utils import DownloadCancelled

    cancel_event = threading.Event()
    cancel_event.set()
    events: list[ProgressEvent] = []
    hook_events = [
        {"status": "downloading", "filename": "a.mp3", "downloaded_bytes": 1, "total_bytes": 100, "info_dict": {}},
    ]

    class RaisingYoutubeDL(ScriptedYoutubeDL):
        def download(self, urls: list[str]) -> int:
            self.download_urls = urls
            for hook in self.opts.get("progress_hooks", []):
                for event in self._hook_events:
                    hook(event)  # expected to raise DownloadCancelled
            return 0

    def factory(opts: dict) -> RaisingYoutubeDL:
        return RaisingYoutubeDL(opts, hook_events=hook_events)

    with __import__("pytest").raises(DownloadCancelled):
        # Exercise the hook directly through a factory that does not catch
        # the exception, proving the hook itself raises rather than swallows.
        instance = factory({})
        instance.opts = {"progress_hooks": [downloader._make_hook(events.append, [0], cancel_event)]}
        instance.download(["https://www.youtube.com/watch?v=abc"])

    assert events == []  # cancelled before on_progress was ever invoked


def test_download_returns_cancelled_result_when_ydl_raises_download_cancelled(tmp_path: Path) -> None:
    from yt_dlp.utils import DownloadCancelled

    class CancellingYoutubeDL(ScriptedYoutubeDL):
        def download(self, urls: list[str]) -> int:
            raise DownloadCancelled("Cancelled by user")

    def factory(opts: dict) -> CancellingYoutubeDL:
        return CancellingYoutubeDL(opts)

    cancel_event = threading.Event()
    cancel_event.set()

    result = download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        cancel_event=cancel_event,
        ydl_factory=factory,
    )

    assert result.cancelled is True
    assert result.ok is False


def test_download_passes_cancel_event_into_ydl_opts_hook(tmp_path: Path) -> None:
    # The cancel_event must reach the hook wired into progress_hooks so a
    # click on Cancel (setting the event from the GUI thread) takes effect
    # on the very next progress callback.
    cancel_event = threading.Event()
    captured: list[ScriptedYoutubeDL] = []

    download(
        url="https://www.youtube.com/watch?v=abc",
        dest=tmp_path,
        mode=DownloadMode.SINGLE,
        cancel_event=cancel_event,
        ydl_factory=make_factory(captured=captured),
    )

    cancel_event.set()
    from yt_dlp.utils import DownloadCancelled
    import pytest

    hook = captured[0].opts["progress_hooks"][0]
    with pytest.raises(DownloadCancelled):
        hook({"status": "downloading", "filename": "x.mp3", "downloaded_bytes": 1, "total_bytes": 10, "info_dict": {}})


def test_download_reports_partial_progress_on_mid_playlist_cancellation(tmp_path: Path) -> None:
    # A realistic cancellation happens after some items already finished
    # downloading; the reported downloaded/skipped counts must reflect that
    # partial progress, not always report zero.
    from yt_dlp.utils import DownloadCancelled

    class PartiallyCancellingYoutubeDL(ScriptedYoutubeDL):
        def download(self, urls: list[str]) -> int:
            for hook in self.opts.get("progress_hooks", []):
                hook(
                    {
                        "status": "finished",
                        "filename": "a.mp3",
                        "downloaded_bytes": 1,
                        "total_bytes": 1,
                        "info_dict": {},
                    }
                )
            raise DownloadCancelled("Cancelled by user")

    def factory(opts: dict) -> PartiallyCancellingYoutubeDL:
        return PartiallyCancellingYoutubeDL(opts)

    cancel_event = threading.Event()

    result = download(
        url="https://www.youtube.com/playlist?list=PLxxx",
        dest=tmp_path,
        mode=DownloadMode.PLAYLIST,
        cancel_event=cancel_event,
        ydl_factory=factory,
    )

    assert result.cancelled is True
    assert result.downloaded == 1


def test_postprocessor_hook_also_raises_download_cancelled_when_event_is_set() -> None:
    # Cancellation must also take effect between postprocessing steps, not
    # only between raw-download progress ticks — otherwise clicking Cancel
    # while ffmpeg is converting the last queued item has no effect at all.
    from yt_dlp.utils import DownloadCancelled

    cancel_event = threading.Event()
    cancel_event.set()
    hook = downloader._make_postprocessor_hook(cancel_event)

    with __import__("pytest").raises(DownloadCancelled):
        hook({"status": "finished", "postprocessor": "ExtractAudio"})


def test_postprocessor_hook_does_not_raise_when_event_not_set() -> None:
    hook = downloader._make_postprocessor_hook(cancel_event=None)

    # Must not raise for a normal, uncancelled postprocessor event.
    hook({"status": "finished", "postprocessor": "ExtractAudio"})


def test_probe_playlist_count_returns_entry_count(tmp_path: Path) -> None:
    class FlatYoutubeDL:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def extract_info(self, url, download=False):
            return {"entries": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}

    from core.downloader import probe_playlist_count

    count = probe_playlist_count(
        "https://www.youtube.com/playlist?list=PLxxx",
        ydl_factory=lambda opts: FlatYoutubeDL(),
    )

    assert count == 3


def test_probe_playlist_count_returns_none_on_missing_entries(tmp_path: Path) -> None:
    class NoEntriesYoutubeDL:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def extract_info(self, url, download=False):
            return {"title": "not a playlist"}

    from core.downloader import probe_playlist_count

    count = probe_playlist_count(
        "https://www.youtube.com/watch?v=abc",
        ydl_factory=lambda opts: NoEntriesYoutubeDL(),
    )

    assert count is None


def test_probe_playlist_count_returns_none_on_youtube_dl_error(tmp_path: Path) -> None:
    from yt_dlp.utils import YoutubeDLError

    class ExplodingYoutubeDL:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def extract_info(self, url, download=False):
            raise YoutubeDLError("network error")

    from core.downloader import probe_playlist_count

    count = probe_playlist_count(
        "https://www.youtube.com/playlist?list=PLxxx",
        ydl_factory=lambda opts: ExplodingYoutubeDL(),
    )

    assert count is None


def test_probe_playlist_count_propagates_unexpected_exceptions(tmp_path: Path) -> None:
    # Only yt-dlp's own error hierarchy is swallowed; a genuine bug (e.g. an
    # AttributeError from unexpected data shape) must still surface instead
    # of being silently treated as "unknown count".
    class BuggyYoutubeDL:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def extract_info(self, url, download=False):
            raise AttributeError("unexpected data shape")

    import pytest

    from core.downloader import probe_playlist_count

    with pytest.raises(AttributeError):
        probe_playlist_count(
            "https://www.youtube.com/playlist?list=PLxxx",
            ydl_factory=lambda opts: BuggyYoutubeDL(),
        )
