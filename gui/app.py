"""Desktop GUI for the YouTube Audio Downloader (CustomTkinter).

Thin presentation layer: this module never imports yt_dlp directly — all
download/classification logic is delegated to ``core.url_classifier`` and
``core.downloader``. A background worker thread runs the download and
communicates with the Tk main thread exclusively through a ``queue.Queue``
drained by ``root.after(100, pump)``; the worker never touches widgets.
"""

from __future__ import annotations

import os
import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from core.downloader import DownloadMode, DownloadResult, ProgressEvent, download, probe_playlist_count
from core.url_classifier import Classification, UrlKind, classify
from gui import theme

APP_TITLE = "YouTube Audio Downloader"
WINDOW_SIZE = "720x560"
BANNER_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon_64.png"

SINGLE_VS_LIST_KINDS = {UrlKind.RADIO_MIX, UrlKind.VIDEO_IN_PLAYLIST}
QUEUE_POLL_INTERVAL_MS = 100


def default_download_folder() -> Path:
    """Return the default destination folder for downloaded audio."""
    return Path(os.path.expanduser("~")) / "Downloads" / "YoutubeAudioDownloader"


# --- Queue event types --------------------------------------------------------
# Plain tuples are used instead of a class hierarchy to keep the worker ->
# pump contract trivial to reason about: ("log", str) | ("progress",
# ProgressEvent) | ("done", DownloadResult) | ("error", str)


class App(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.configure(fg_color=theme.BG)

        self._fonts = theme.resolve_fonts()
        self._event_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._download_total = 0

        self._build_layout()
        self._start_pump()

    # --- Layout ---------------------------------------------------------------

    def _build_layout(self) -> None:
        container = ctk.CTkFrame(self, fg_color=theme.BG)
        container.pack(fill="both", expand=True, padx=theme.PAD_L, pady=theme.PAD_L)

        self._build_header(container)
        self._build_url_entry(container)
        self._build_folder_row(container)
        self._build_download_button(container)
        self._build_progress_row(container)
        self._build_log(container)

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, theme.PAD_M))

        if BANNER_ICON_PATH.exists():
            try:
                from PIL import Image

                banner_image = ctk.CTkImage(
                    light_image=Image.open(BANNER_ICON_PATH),
                    dark_image=Image.open(BANNER_ICON_PATH),
                    size=(48, 48),
                )
                icon_label = ctk.CTkLabel(header, image=banner_image, text="")
                icon_label.pack(side="left", padx=(0, theme.PAD_M))
            except (OSError, ImportError) as exc:
                # Banner icon is decorative, never fatal to the app — but a
                # broken/missing icon file (e.g. a bad release build) must
                # still be visible somewhere, not fail completely silently.
                print(f"Warning: could not load banner icon: {exc}")

        title_font = ctk.CTkFont(*self._fonts["FONT_TITLE"].as_tuple())
        title_label = ctk.CTkLabel(header, text=APP_TITLE, text_color=theme.TEXT, font=title_font)
        title_label.pack(side="left")

    def _build_url_entry(self, parent: ctk.CTkFrame) -> None:
        body_font = ctk.CTkFont(*self._fonts["FONT_BODY"].as_tuple())
        self.url_entry = ctk.CTkEntry(
            parent,
            placeholder_text="Paste a YouTube URL (video, playlist, or mix)",
            font=body_font,
            fg_color=theme.SURFACE,
            text_color=theme.TEXT,
            border_color=theme.MUTED,
        )
        self.url_entry.pack(fill="x", pady=(0, theme.PAD_M))

    def _build_folder_row(self, parent: ctk.CTkFrame) -> None:
        body_font = ctk.CTkFont(*self._fonts["FONT_BODY"].as_tuple())
        folder_row = ctk.CTkFrame(parent, fg_color="transparent")
        folder_row.pack(fill="x", pady=(0, theme.PAD_M))

        self.folder_entry = ctk.CTkEntry(
            folder_row,
            font=body_font,
            fg_color=theme.SURFACE,
            text_color=theme.TEXT,
            border_color=theme.MUTED,
        )
        self.folder_entry.insert(0, str(default_download_folder()))
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, theme.PAD_S))

        self.browse_button = ctk.CTkButton(
            folder_row,
            text="Browse...",
            font=body_font,
            fg_color=theme.SURFACE,
            hover_color=theme.MUTED,
            text_color=theme.TEXT,
            command=self._on_browse_clicked,
        )
        self.browse_button.pack(side="left")

    def _build_download_button(self, parent: ctk.CTkFrame) -> None:
        body_font = ctk.CTkFont(*self._fonts["FONT_BODY"].as_tuple())
        button_row = ctk.CTkFrame(parent, fg_color="transparent")
        button_row.pack(fill="x", pady=(0, theme.PAD_M))

        self.download_button = ctk.CTkButton(
            button_row,
            text="Download",
            font=body_font,
            fg_color=theme.PRIMARY,
            hover_color=theme.MUTED,
            text_color=theme.BG,
            command=self._on_download_clicked,
        )
        self.download_button.pack(side="left", fill="x", expand=True, padx=(0, theme.PAD_S))

        self.cancel_button = ctk.CTkButton(
            button_row,
            text="Cancel",
            font=body_font,
            fg_color=theme.SURFACE,
            hover_color=theme.ERROR,
            text_color=theme.TEXT,
            state="disabled",
            command=self._on_cancel_clicked,
        )
        self.cancel_button.pack(side="left")

    def _build_progress_row(self, parent: ctk.CTkFrame) -> None:
        body_font = ctk.CTkFont(*self._fonts["FONT_BODY"].as_tuple())
        progress_row = ctk.CTkFrame(parent, fg_color="transparent")
        progress_row.pack(fill="x", pady=(0, theme.PAD_M))

        self.progress_bar = ctk.CTkProgressBar(progress_row, progress_color=theme.PRIMARY)
        self.progress_bar.set(0)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, theme.PAD_S))

        self.counter_label = ctk.CTkLabel(progress_row, text="", font=body_font, text_color=theme.MUTED)
        self.counter_label.pack(side="left")

    def _build_log(self, parent: ctk.CTkFrame) -> None:
        mono_font = ctk.CTkFont(*self._fonts["FONT_MONO"].as_tuple())
        self.log_box = ctk.CTkTextbox(
            parent,
            font=mono_font,
            fg_color=theme.SURFACE,
            text_color=theme.TEXT,
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")

    # --- Log helpers ------------------------------------------------------------

    def _append_log(self, message: str, color: str | None = None) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # --- Button FSM ---------------------------------------------------------------

    def _set_running(self, running: bool) -> None:
        idle_state = "disabled" if running else "normal"
        running_state = "normal" if running else "disabled"
        self.download_button.configure(state=idle_state)
        self.browse_button.configure(state=idle_state)
        self.url_entry.configure(state=idle_state)
        self.folder_entry.configure(state=idle_state)
        self.cancel_button.configure(state=running_state)

    # --- Event handlers -----------------------------------------------------------

    def _on_browse_clicked(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder_entry.get() or str(Path.home()))
        if chosen:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, chosen)

    def _on_download_clicked(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self._append_log("Error: enter a URL first.")
            return

        classification = classify(url)

        if classification.kind == UrlKind.INVALID:
            self._append_log(f"Error: '{url}' is not a valid YouTube link.")
            return

        if classification.kind == UrlKind.VIDEO:
            self._start_download(url, DownloadMode.SINGLE)
            return

        if classification.kind == UrlKind.PLAYLIST:
            self._confirm_playlist_then_download(classification)
            return

        if classification.kind in SINGLE_VS_LIST_KINDS:
            self._confirm_single_vs_list_then_download(classification)
            return

    def _on_cancel_clicked(self) -> None:
        if self._cancel_event is None:
            return
        self._cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self._append_log("Cancelling...")

    def _confirm_playlist_then_download(self, classification: Classification) -> None:
        # probe_playlist_count() is a real network call; running it on the
        # main thread would freeze the whole window for its duration (see
        # _start_download for the same worker-thread + queue pattern used
        # for the actual download).
        self._append_log("Checking playlist size...")
        self.download_button.configure(state="disabled")
        threading.Thread(
            target=self._probe_playlist_worker,
            args=(classification,),
            daemon=True,
        ).start()

    def _probe_playlist_worker(self, classification: Classification) -> None:
        """Runs on a background thread. MUST NOT touch any Tk widget."""
        count = probe_playlist_count(classification.url)
        self._event_queue.put(("playlist_count_ready", (classification, count)))

    def _handle_playlist_count_ready(self, classification: Classification, count: int | None) -> None:
        self.download_button.configure(state="normal")
        count_text = str(count) if count is not None else "an unknown number of"
        confirmed = messagebox.askyesno(
            "Confirm playlist download",
            f"This playlist contains {count_text} item(s). Download the whole playlist?",
        )
        if confirmed:
            self._start_download(classification.url, DownloadMode.PLAYLIST)
        else:
            self._append_log("Playlist download cancelled.")

    def _confirm_single_vs_list_then_download(self, classification: Classification) -> None:
        answer = messagebox.askyesnocancel(
            "Single video or full list?",
            "This link points to a single video inside a list (or radio/mix).\n\n"
            "Yes = download only this video\nNo = download the whole list\nCancel = abort",
        )
        if answer is None:
            self._append_log("Download cancelled.")
            return
        mode = DownloadMode.SINGLE if answer else DownloadMode.PLAYLIST
        self._start_download(classification.url, mode)

    # --- Worker thread + queue pump ------------------------------------------------

    def _start_download(self, url: str, mode: DownloadMode) -> None:
        dest_text = self.folder_entry.get().strip() or str(default_download_folder())
        dest = Path(dest_text)
        dest.mkdir(parents=True, exist_ok=True)

        self._download_total = 0
        self._cancel_event = threading.Event()
        self.progress_bar.set(0)
        self.counter_label.configure(text="")
        self._set_running(True)
        self._append_log(f"Starting download ({mode.value}): {url}")

        self._worker_thread = threading.Thread(
            target=self._run_worker,
            args=(url, dest, mode, self._cancel_event),
            daemon=True,
        )
        self._worker_thread.start()

    def _run_worker(
        self, url: str, dest: Path, mode: DownloadMode, cancel_event: threading.Event
    ) -> None:
        """Runs on a background thread. MUST NOT touch any Tk widget —
        only pushes events onto the thread-safe queue for the pump to
        consume on the main thread."""

        def on_log(message: str) -> None:
            self._event_queue.put(("log", message))

        def on_progress(event: ProgressEvent) -> None:
            self._event_queue.put(("progress", event))

        try:
            result = download(
                url=url,
                dest=dest,
                mode=mode,
                on_log=on_log,
                on_progress=on_progress,
                cancel_event=cancel_event,
            )
        except Exception as exc:  # noqa: BLE001 - worker boundary reports any failure to the pump
            self._event_queue.put(("error", str(exc)))
            return

        self._event_queue.put(("done", result))

    def _start_pump(self) -> None:
        self.after(QUEUE_POLL_INTERVAL_MS, self._pump)

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self._event_queue.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        finally:
            self.after(QUEUE_POLL_INTERVAL_MS, self._pump)

    def _handle_event(self, kind: str, payload: object) -> None:
        if kind == "log":
            self._append_log(str(payload))
        elif kind == "progress":
            self._handle_progress(payload)  # type: ignore[arg-type]
        elif kind == "done":
            self._handle_done(payload)  # type: ignore[arg-type]
        elif kind == "error":
            self._handle_error(str(payload))
        elif kind == "playlist_count_ready":
            classification, count = payload  # type: ignore[misc]
            self._handle_playlist_count_ready(classification, count)

    def _handle_progress(self, event: ProgressEvent) -> None:
        if event.percent is not None:
            self.progress_bar.set(min(event.percent / 100, 1.0))
        if event.index is not None and event.total is not None:
            self._download_total = event.total
            self.counter_label.configure(text=f"{event.index}/{event.total}")

    def _handle_done(self, result: DownloadResult) -> None:
        self._cancel_event = None
        if result.cancelled:
            self._append_log(f"Cancelled. {result.downloaded} file(s) saved to {result.dest}")
        elif result.ok:
            self.progress_bar.set(1.0)
            self._append_log(f"Done. {result.downloaded} file(s) saved to {result.dest}")
            if result.skipped:
                self._append_log(f"{result.skipped} item(s) skipped (private/unavailable).")
        else:
            self._append_log("Finished with errors:")
            for error in result.errors:
                self._append_log(f"  {error}")
        self._set_running(False)

    def _handle_error(self, message: str) -> None:
        self._cancel_event = None
        self._append_log(f"Error: {message}")
        self._set_running(False)


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
