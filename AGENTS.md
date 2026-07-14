# Coding Standards — YouTube Audio Downloader

## Architecture

- Strict separation between `core/` (business logic, no UI imports) and `gui/` (presentation only).
- `core/` modules must never import tkinter/customtkinter. GUI must never call yt-dlp directly — always through `core.downloader`.
- All user-facing behavior decisions (URL classification, download mode) live in `core/`, not in the GUI.

## Python

- Python 3.10+ syntax. Type hints on all public functions.
- No bare `except:`. Catch specific exceptions; unexpected errors propagate to the caller with context.
- Standard library first; every new third-party dependency must be justified.
- Constants (bitrate, output templates, URLs) at module level, never inline magic values.

## Testing

- TDD: new core behavior requires a failing test first.
- Unit tests must not hit the network. yt-dlp is faked/mocked in unit tests.
- Integration tests are marked `@pytest.mark.integration` and excluded from the default run.

## UI text and code language

- All code, comments, docstrings, log messages, and UI copy in English.

## Commits

- Conventional commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`, `ci:`).
- No AI attribution or Co-Authored-By lines.
