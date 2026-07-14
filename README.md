# YouTube Audio Downloader

A desktop app (with a CLI fallback) to download audio from YouTube videos or
entire playlists as high-quality **320 kbps MP3**. Built with `yt-dlp` for
extraction, `ffmpeg` for audio conversion, and a CustomTkinter GUI on top of
a tkinter-free core library.

## For End Users

No Python install needed — just download the app for your OS:

1. Go to the [Releases](../../releases) page and download the asset for
   your platform: `YouTubeAudioDownloader-windows.exe`,
   `YouTubeAudioDownloader-macos.app.zip`, or `YouTubeAudioDownloader-linux`.
2. **macOS**: unzip `YouTubeAudioDownloader-macos.app.zip` first — you get a
   `YouTubeAudioDownloader-macos.app` you can double-click. **Windows/Linux**:
   the downloaded file is already runnable, no unzip needed.
3. Double-click it to launch. No install step required.
   - **macOS**: the app isn't signed with an Apple Developer certificate, so
     Gatekeeper will block it the first time ("Apple could not verify..." /
     cannot check for malicious software). Either right-click the `.app` →
     **Open** → **Open** in the dialog, or run
     `xattr -dr com.apple.quarantine YouTubeAudioDownloader-macos.app` in
     Terminal (note the `-r`, needed since a `.app` is a folder), then open
     it normally.
3. Paste a YouTube link (video, playlist, or radio/mix), pick a destination
   folder (defaults to `Downloads/YoutubeAudioDownloader`), and click
   **Download**.
4. Playlists and radio/mix links prompt a confirmation before anything
   downloads; invalid links are reported in the log without crashing the app.

### Platform verification status (honest, as of this writing)

- **macOS (arm64)**: build + run + real-network download verified locally
  on the development machine this session.
- **Windows / Linux**: built and smoke-tested by CI (GitHub Actions matrix)
  on tagged releases, but not yet manually verified on physical Windows or
  Linux hardware. If you hit a platform-specific issue, please open one.

## For Developers

### Setup

```bash
git clone <this-repo>
cd yt-audio-downloader
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

macOS also needs Tk (CustomTkinter depends on it):

```bash
brew install python-tk@3.14
```

Linux (Debian/Ubuntu) needs the system Tk package:

```bash
sudo apt-get install python3-tk
```

### Running

```bash
# Unit tests (no network, no GUI)
pytest -m "not integration"

# Launch the GUI
python -m gui.app

# Run the CLI wrapper instead
python download_audio.py

# Real-network end-to-end check (downloads an actual short video)
python scripts/verify_e2e.py
```

### Building a standalone binary locally

```bash
python scripts/fetch_vendor.py   # downloads ffmpeg + deno into vendor/<platform>/
python scripts/make_icons.py     # generates assets/icon.{ico,icns,png}
pyinstaller app.spec             # onefile build
```

Output layout differs by OS: Windows -> `dist/YouTubeAudioDownloader-windows.exe`;
Linux -> `dist/YouTubeAudioDownloader-linux`; macOS -> a proper app bundle at
`dist/YouTubeAudioDownloader-macos.app` (the actual binary lives inside, at
`Contents/MacOS/YouTubeAudioDownloader-macos`) — a bare Mach-O binary without
this wrapper isn't reliably launchable by double-clicking in Finder.

Then smoke-test the frozen binary launches cleanly:

```bash
# macOS
python scripts/verify_e2e.py --binary "dist/YouTubeAudioDownloader-macos.app/Contents/MacOS/YouTubeAudioDownloader-macos"
# Linux / Windows
python scripts/verify_e2e.py --binary dist/YouTubeAudioDownloader-linux
```

### Architecture

- `core/` — pure business logic (URL classification, download orchestration,
  binary resolution). No tkinter imports, no direct UI dependency.
- `gui/` — CustomTkinter presentation layer. Never imports `yt_dlp` directly;
  talks to `core` only through `core.downloader` and `core.url_classifier`.
  The download runs on a background thread and communicates with the Tk
  main thread via a `queue.Queue` drained by `root.after(100, ...)`.
- `download_audio.py` — thin CLI wrapper over the same `core` API.
- `scripts/fetch_vendor.py` — downloads platform-specific `ffmpeg`/`deno`
  binaries into `vendor/<platform>/` for local packaging.
- `scripts/make_icons.py` — rasterizes `assets/icon.svg` into the PNG/ICO/ICNS
  formats needed by the packaged app.
- `scripts/verify_e2e.py` — real-network integration check (excluded from
  the default `pytest -m "not integration"` run); also supports
  `--binary <path>` to smoke-test that a frozen build launches cleanly.
- `app.spec` — PyInstaller onefile spec bundling the vendored binaries and
  app icon.
- `.github/workflows/build-release.yml` — CI: unit tests on every push/PR;
  on a `v*` tag, builds a Windows/macOS/Linux matrix, runs the e2e smoke
  gate, and publishes a GitHub Release with all three artifacts.

### Coding standards

See [`AGENTS.md`](AGENTS.md) for the full conventions (core/gui boundary,
type hints, no bare `except`, TDD for `core/`, English-only code/comments).
