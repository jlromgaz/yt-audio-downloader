"""Tests for core.url_classifier.classify.

Covers spec scenarios: Single video, Playlist link, Radio/mix link,
Video inside a playlist, Invalid or non-YouTube input.
"""

import pytest

from core.url_classifier import Classification, UrlKind, classify


def test_classify_single_video_returns_video_kind() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.kind == UrlKind.VIDEO


def test_classify_single_video_extracts_video_id() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.video_id == "dQw4w9WgXcQ"


def test_classify_single_video_has_no_confirmation_needed() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.needs_confirmation is False


def test_classify_playlist_returns_playlist_kind() -> None:
    result = classify("https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx")

    assert result.kind == UrlKind.PLAYLIST


def test_classify_playlist_extracts_playlist_id() -> None:
    result = classify("https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx")

    assert result.playlist_id == "PLxxxxxxxxxxxxxxxx"


def test_classify_playlist_needs_confirmation() -> None:
    result = classify("https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx")

    assert result.needs_confirmation is True


def test_classify_radio_mix_returns_radio_mix_kind() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ")

    assert result.kind == UrlKind.RADIO_MIX


def test_classify_radio_mix_needs_confirmation() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ")

    assert result.needs_confirmation is True


def test_classify_video_in_playlist_returns_video_in_playlist_kind() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxxxxxxxxxxxxxx")

    assert result.kind == UrlKind.VIDEO_IN_PLAYLIST


def test_classify_video_in_playlist_needs_confirmation() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxxxxxxxxxxxxxx")

    assert result.needs_confirmation is True


def test_classify_video_in_playlist_extracts_both_ids() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxxxxxxxxxxxxxx")

    assert result.video_id == "dQw4w9WgXcQ"
    assert result.playlist_id == "PLxxxxxxxxxxxxxxxx"


def test_classify_garbage_string_returns_invalid() -> None:
    result = classify("not a url")

    assert result.kind == UrlKind.INVALID


def test_classify_non_youtube_host_returns_invalid() -> None:
    result = classify("https://example.com/foo")

    assert result.kind == UrlKind.INVALID


def test_classify_empty_string_returns_invalid() -> None:
    result = classify("")

    assert result.kind == UrlKind.INVALID


def test_classify_invalid_raises_no_exception() -> None:
    # Should not raise for any of these malformed inputs.
    classify("not a url")
    classify("https://example.com/foo")
    classify("")


def test_classify_youtu_be_short_link_returns_video_kind() -> None:
    result = classify("https://youtu.be/dQw4w9WgXcQ")

    assert result.kind == UrlKind.VIDEO


def test_classify_youtu_be_short_link_extracts_video_id() -> None:
    result = classify("https://youtu.be/dQw4w9WgXcQ")

    assert result.video_id == "dQw4w9WgXcQ"


def test_classify_youtu_be_short_link_with_list_returns_video_in_playlist() -> None:
    result = classify("https://youtu.be/dQw4w9WgXcQ?list=PLxxxxxxxxxxxxxxxx")

    assert result.kind == UrlKind.VIDEO_IN_PLAYLIST
    assert result.video_id == "dQw4w9WgXcQ"
    assert result.playlist_id == "PLxxxxxxxxxxxxxxxx"


def test_classification_is_frozen_dataclass() -> None:
    result = classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert isinstance(result, Classification)
    with pytest.raises(AttributeError):
        result.kind = UrlKind.INVALID  # type: ignore[misc]


def test_classify_preserves_original_url() -> None:
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    result = classify(url)

    assert result.url == url
