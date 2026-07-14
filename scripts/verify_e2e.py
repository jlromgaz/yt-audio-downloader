"""Real-network end-to-end verification of the download pipeline.

Downloads a known short public video to a temp directory using
core.downloader, then asserts the resulting file is a valid MP3 at 320
kbps via ffprobe. Prints PASS/FAIL and exits 0/1 accordingly.

Not run by ``pytest -m 'not integration'`` — invoke directly:
    python scripts/verify_e2e.py

``--binary <path>`` mode: the frozen PyInstaller app is a GUI-only binary
with no CLI interface, so a full download-through-GUI e2e cannot be
scripted headless. This mode instead launches the binary as a subprocess,
waits briefly to confirm it starts without an immediate crash, then sends
SIGTERM and confirms it exits within a timeout. This proves the frozen
binary is runnable (imports resolve, vendored ffmpeg/deno are found, the
Tk/CustomTkinter widget tree constructs) but does NOT prove a full
download completes through the GUI — that still requires a manual,
interactive click-test.
    python scripts/verify_e2e.py --binary dist/YouTubeAudioDownloader
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Allow running as `python scripts/verify_e2e.py` from the repo root without
# installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import binaries  # noqa: E402
from core.downloader import DownloadMode, DownloadResult, download  # noqa: E402

TEST_URL = "https://www.youtube.com/watch?v=LYdG2w8jbws"
EXPECTED_CODEC = "mp3"
EXPECTED_BITRATE_KBPS = 320
BITRATE_TOLERANCE_KBPS = 32  # yt-dlp/ffmpeg CBR/VBR encoding tolerance

BINARY_STARTUP_WAIT_S = 4
BINARY_SHUTDOWN_TIMEOUT_S = 10


def verify_binary_launches(binary_path: Path) -> int:
    """Smoke-check that the frozen GUI binary starts cleanly and can be
    terminated cleanly. Does not exercise the download flow (see module
    docstring for the documented limitation)."""
    print("=== verify_e2e: frozen binary launch smoke test ===")
    print(f"Binary: {binary_path}")

    if not binary_path.exists():
        print(f"FAIL: binary not found at {binary_path}")
        return 1

    process = subprocess.Popen([str(binary_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(BINARY_STARTUP_WAIT_S)

    early_exit_code = process.poll()
    if early_exit_code is not None:
        stdout, stderr = process.communicate()
        print(f"FAIL: process exited early with code {early_exit_code}")
        print(f"  stdout: {stdout.decode(errors='replace')[-2000:]}")
        print(f"  stderr: {stderr.decode(errors='replace')[-2000:]}")
        return 1

    print(f"[ok] process still running after {BINARY_STARTUP_WAIT_S}s (pid={process.pid})")

    process.terminate()
    try:
        process.wait(timeout=BINARY_SHUTDOWN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=BINARY_SHUTDOWN_TIMEOUT_S)
        print("FAIL: process did not respond to SIGTERM within timeout, had to SIGKILL")
        return 1

    print(f"[ok] process terminated cleanly (exit code {process.returncode})")
    print("PASS (launch smoke test only — full download-through-GUI flow requires manual testing)")
    return 0


def _ffprobe_json(file_path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe not found on PATH")

    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _find_mp3(dest: Path) -> Path | None:
    matches = list(dest.rglob("*.mp3"))
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary",
        type=Path,
        default=None,
        help="Path to a frozen PyInstaller binary; runs the launch smoke test instead of the network download check.",
    )
    args = parser.parse_args()

    if args.binary is not None:
        return verify_binary_launches(args.binary)

    print("=== verify_e2e: single video download ===")
    print(f"URL: {TEST_URL}")

    ffmpeg = binaries.ffmpeg_path()
    print(f"Resolved ffmpeg: {ffmpeg}")
    if ffmpeg is None:
        print("FAIL: ffmpeg could not be resolved")
        return 1

    with tempfile.TemporaryDirectory(prefix="yt-audio-e2e-") as tmp_dir:
        dest = Path(tmp_dir)
        logs: list[str] = []

        try:
            result: DownloadResult = download(
                url=TEST_URL,
                dest=dest,
                mode=DownloadMode.SINGLE,
                on_log=logs.append,
            )
        except Exception as exc:  # noqa: BLE001 - top-level e2e gate reports any failure
            print(f"FAIL: download() raised: {exc}")
            for line in logs[-20:]:
                print(f"  log: {line}")
            return 1

        print(f"DownloadResult: ok={result.ok} downloaded={result.downloaded} "
              f"skipped={result.skipped} errors={result.errors}")

        mp3_path = _find_mp3(dest)
        if mp3_path is None:
            print("FAIL: no .mp3 file found in destination directory")
            for line in logs[-20:]:
                print(f"  log: {line}")
            return 1

        print(f"Found file: {mp3_path} ({mp3_path.stat().st_size} bytes)")

        try:
            probe = _ffprobe_json(mp3_path)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            print(f"FAIL: ffprobe failed: {exc}")
            return 1

        streams = probe.get("streams", [])
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if not audio_streams:
            print("FAIL: no audio stream found via ffprobe")
            return 1

        stream = audio_streams[0]
        codec_name = stream.get("codec_name")
        duration = float(probe.get("format", {}).get("duration", 0))
        bit_rate_bps = int(probe.get("format", {}).get("bit_rate", 0))
        bit_rate_kbps = bit_rate_bps / 1000

        print(f"ffprobe: codec={codec_name} duration={duration:.2f}s bitrate={bit_rate_kbps:.0f}kbps")

        if codec_name != EXPECTED_CODEC:
            print(f"FAIL: expected codec '{EXPECTED_CODEC}', got '{codec_name}'")
            return 1

        if duration <= 0:
            print("FAIL: duration is not > 0")
            return 1

        if abs(bit_rate_kbps - EXPECTED_BITRATE_KBPS) > BITRATE_TOLERANCE_KBPS:
            print(
                f"FAIL: expected ~{EXPECTED_BITRATE_KBPS}kbps "
                f"(+/-{BITRATE_TOLERANCE_KBPS}), got {bit_rate_kbps:.0f}kbps"
            )
            return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
