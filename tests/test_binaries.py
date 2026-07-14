"""Tests for core.binaries binary resolution.

Covers spec scenarios: Dev mode with vendor present, Frozen build,
Dev mode fallback to system PATH. Also covers the threat-matrix row
"Subprocess/process integration" — asserting the deno PATH prepend adds
only the resolved deno_dir(), no unrelated entries.
"""

import sys
from pathlib import Path

import pytest

import core.binaries as binaries


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_ffmpeg_path_resolves_from_frozen_meipass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe_name = binaries._executable_name(binaries.FFMPEG_BINARY_NAME)
    _make_executable(tmp_path / exe_name)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    result = binaries.ffmpeg_path()

    assert result == tmp_path / exe_name


def test_ffmpeg_path_resolves_from_vendor_dir_in_dev_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(binaries, "PROJECT_ROOT", tmp_path)
    platform_dir = binaries._platform_dir_name()
    exe_name = binaries._executable_name(binaries.FFMPEG_BINARY_NAME)
    vendor_ffmpeg = _make_executable(tmp_path / "vendor" / platform_dir / exe_name)

    result = binaries.ffmpeg_path()

    assert result == vendor_ffmpeg


def test_ffmpeg_path_falls_back_to_system_path_when_vendor_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(binaries, "PROJECT_ROOT", tmp_path)
    fake_system_ffmpeg = "/usr/bin/ffmpeg"
    monkeypatch.setattr(binaries.shutil, "which", lambda name: fake_system_ffmpeg if name == "ffmpeg" else None)

    result = binaries.ffmpeg_path()

    assert result == Path(fake_system_ffmpeg)


def test_ffmpeg_path_returns_none_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(binaries, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)

    assert binaries.ffmpeg_path() is None


def test_deno_dir_returns_parent_directory_of_resolved_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(binaries, "PROJECT_ROOT", tmp_path)
    platform_dir = binaries._platform_dir_name()
    exe_name = binaries._executable_name(binaries.DENO_BINARY_NAME)
    vendor_deno = _make_executable(tmp_path / "vendor" / platform_dir / exe_name)

    result = binaries.deno_dir()

    assert result == vendor_deno.parent


def test_deno_dir_returns_none_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(binaries, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)

    assert binaries.deno_dir() is None


def test_ensure_deno_on_path_prepends_only_resolved_deno_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    resolved_dir = tmp_path / "deno-bin"
    resolved_dir.mkdir()
    monkeypatch.setattr(binaries, "deno_dir", lambda: resolved_dir)
    # os.pathsep is ':' on POSIX and ';' on Windows — hardcoding ':' made
    # this test fail on the Windows CI runner (found via a real CI run).
    existing_entries = [str(tmp_path / "usr-bin"), str(tmp_path / "bin")]
    monkeypatch.setenv("PATH", binaries.os.pathsep.join(existing_entries))

    binaries.ensure_deno_on_path()

    entries = binaries.os.environ["PATH"].split(binaries.os.pathsep)
    assert entries[0] == str(resolved_dir)
    assert entries[1:] == existing_entries


def test_ensure_deno_on_path_does_not_duplicate_entry_when_called_twice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    resolved_dir = tmp_path / "deno-bin"
    resolved_dir.mkdir()
    monkeypatch.setattr(binaries, "deno_dir", lambda: resolved_dir)
    monkeypatch.setenv("PATH", binaries.os.pathsep.join([str(tmp_path / "usr-bin"), str(tmp_path / "bin")]))

    binaries.ensure_deno_on_path()
    binaries.ensure_deno_on_path()

    entries = binaries.os.environ["PATH"].split(binaries.os.pathsep)
    assert entries.count(str(resolved_dir)) == 1


def test_ensure_deno_on_path_is_noop_when_deno_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binaries, "deno_dir", lambda: None)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    binaries.ensure_deno_on_path()

    assert binaries.os.environ["PATH"] == "/usr/bin:/bin"
