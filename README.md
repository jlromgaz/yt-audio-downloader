# 🎧 YouTube Audio Downloader

<p>
  <img src="https://img.shields.io/badge/status-personal%20project-blue" alt="status badge" />
  <img src="https://img.shields.io/badge/purpose-educational-brightgreen" alt="educational purpose badge" />
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" alt="python version badge" />
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="platform badge" />
</p>

A desktop app (with a CLI fallback) that downloads audio from YouTube videos or
playlists and converts it to high-quality **320 kbps MP3**. It started as a way
to get comfortable steering an AI coding assistant through a stack outside my
day-to-day expertise (Java) — packaging a Python desktop GUI, wiring a CI/CD
pipeline, and orchestrating a real download/conversion workflow end to end.

> ⚠️ **This is a personal, educational project.** It exists to practice
> building and shipping a cross-platform desktop app with AI-assisted
> development — not to encourage or facilitate copyright infringement. See
> [Purpose & Disclaimer](#-purpose--disclaimer) below before using it.

---

## 📚 Table of Contents

- [Purpose & Disclaimer](#-purpose--disclaimer)
- [Tech Stack](#-tech-stack)
- [For End Users](#for-end-users)
- [For Developers](#for-developers)
- [Architecture](#architecture)
- [Coding Standards](#coding-standards)

---

## 🎓 Purpose & Disclaimer

This repository is part of my personal AI-assisted development portfolio. My
day-to-day expertise is **Java**; this project is a hands-on exercise in using
AI tools to design, build, and ship software in a language and stack I don't
use professionally (Python, a native GUI, PyInstaller packaging, GitHub
Actions CI/CD).

**The goal is learning, not distribution.** Specifically:

- This tool is intended for **personal, educational, and experimentation
  use only** — for example, downloading audio you own the rights to, that is
  explicitly licensed for reuse (e.g. Creative Commons), or that is in the
  public domain.
- It is **not affiliated with, endorsed by, or sponsored by YouTube or
  Google**, and "YouTube" is used here only to describe compatibility.
- Downloading copyrighted content without the rights holder's permission may
  violate YouTube's Terms of Service and copyright law in your jurisdiction.
  **You are responsible for how you use this tool** — please respect content
  creators' rights and the platform's terms.
- No YouTube account credentials, API keys, or any other third-party secrets
  are used, stored, or required anywhere in this project — it only relies on
  `yt-dlp`'s public extraction logic against publicly accessible URLs.

If you represent a rights holder with a concern about this repository, please
open an issue and I'll address it promptly.

---

## 🧱 Tech Stack

This project is the main showcase for applying AI-assisted development to a
non-Java stack. Here's everything under the hood:

| Layer | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.12+ | Core application language |
| **Media extraction** | [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) | Resolves and downloads audio streams |
| **Audio conversion** | [`ffmpeg`](https://ffmpeg.org/) (vendored per OS) | Converts extracted audio to 320 kbps MP3 |
| **JS runtime** | [`deno`](https://deno.com/) (vendored per OS) | Runs `yt-dlp`'s remote JS-challenge component |
| **Desktop GUI** | [`CustomTkinter`](https://github.com/TomSchimansky/CustomTkinter) on top of Tkinter | Cross-platform native-looking UI |
| **Imaging** | [`Pillow`](https://python-pillow.org/) | Icon rasterization and image handling |
| **Packaging** | [`PyInstaller`](https://pyinstaller.org/) | Builds onefile binaries / macOS `.app` bundle |
| **Testing** | [`pytest`](https://pytest.org/) | Unit tests (network-free, `yt-dlp` mocked) + marked integration tests |
| **CI/CD** | [GitHub Actions](https://github.com/features/actions) | Test matrix (Win/macOS/Linux), tag-triggered release pipeline |

Architecturally, the app keeps a **strict separation** between a
UI-agnostic `core/` (business logic) and a `gui/` presentation layer — the
GUI never talks to `yt-dlp` directly, and `core/` never imports Tkinter. See
[Architecture](#architecture) for details.

---

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
4. Paste a YouTube link (video, playlist, or radio/mix), pick a destination
   folder (defaults to `Downloads/YoutubeAudioDownloader`), and click
   **Download**.
5. Playlists and radio/mix links prompt a confirmation before anything
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

## Architecture

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

## Coding Standards

See [`AGENTS.md`](AGENTS.md) for the full conventions (core/gui boundary,
type hints, no bare `except`, TDD for `core/`, English-only code/comments).
