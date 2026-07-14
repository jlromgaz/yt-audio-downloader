"""Classify a YouTube URL into a download intent before any download starts.

Pure, network-free parsing. No tkinter, no yt-dlp imports here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import parse_qs, urlparse

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
YOUTU_BE_HOST = "youtu.be"
RADIO_MIX_PLAYLIST_PREFIX = "RD"


class UrlKind(Enum):
    """The intent classes a YouTube URL can be classified into."""

    VIDEO = "VIDEO"
    PLAYLIST = "PLAYLIST"
    RADIO_MIX = "RADIO_MIX"
    VIDEO_IN_PLAYLIST = "VIDEO_IN_PLAYLIST"
    INVALID = "INVALID"


@dataclass(frozen=True)
class Classification:
    """Result of classifying a URL."""

    kind: UrlKind
    url: str
    video_id: str | None = None
    playlist_id: str | None = None
    needs_confirmation: bool = False


def _extract_youtu_be_video_id(path: str) -> str | None:
    video_id = path.lstrip("/")
    return video_id or None


def classify(url: str) -> Classification:
    """Classify a YouTube URL into VIDEO, PLAYLIST, RADIO_MIX,
    VIDEO_IN_PLAYLIST, or INVALID.

    Never raises for malformed or non-YouTube input; returns INVALID instead.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return Classification(kind=UrlKind.INVALID, url=url)

    host = parsed.netloc.lower()
    query = parse_qs(parsed.query)

    video_id: str | None = None
    playlist_id: str | None = None

    if host in YOUTUBE_HOSTS:
        video_id = query.get("v", [None])[0]
        playlist_id = query.get("list", [None])[0]
    elif host == YOUTU_BE_HOST:
        video_id = _extract_youtu_be_video_id(parsed.path)
        playlist_id = query.get("list", [None])[0]
    else:
        return Classification(kind=UrlKind.INVALID, url=url)

    if video_id and playlist_id:
        if playlist_id.startswith(RADIO_MIX_PLAYLIST_PREFIX):
            return Classification(
                kind=UrlKind.RADIO_MIX,
                url=url,
                video_id=video_id,
                playlist_id=playlist_id,
                needs_confirmation=True,
            )
        return Classification(
            kind=UrlKind.VIDEO_IN_PLAYLIST,
            url=url,
            video_id=video_id,
            playlist_id=playlist_id,
            needs_confirmation=True,
        )

    if playlist_id:
        return Classification(
            kind=UrlKind.PLAYLIST,
            url=url,
            playlist_id=playlist_id,
            needs_confirmation=True,
        )

    if video_id:
        return Classification(
            kind=UrlKind.VIDEO,
            url=url,
            video_id=video_id,
            needs_confirmation=False,
        )

    return Classification(kind=UrlKind.INVALID, url=url)
