from __future__ import annotations

from datetime import date

import pytest

from finance_kol_analyzer.youtube_metadata import (
    YouTubeMetadata,
    _info_to_metadata,
    _parse_upload_date,
)


def _make_metadata(**kwargs) -> YouTubeMetadata:
    defaults = dict(
        url="https://www.youtube.com/watch?v=abc",
        title="Test Video",
        channel="Test Channel",
        publish_date=date(2024, 3, 15),
        duration_seconds=3725,
        view_count=1_234_567,
        description="A test video.",
    )
    defaults.update(kwargs)
    return YouTubeMetadata(**defaults)


class TestParseUploadDate:
    def test_valid_date(self) -> None:
        assert _parse_upload_date("20240315") == date(2024, 3, 15)

    def test_none_returns_none(self) -> None:
        assert _parse_upload_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_upload_date("") is None

    def test_invalid_format_returns_none(self) -> None:
        assert _parse_upload_date("not-a-date") is None


class TestYouTubeMetadataDurationFormatted:
    def test_hours_minutes_seconds(self) -> None:
        meta = _make_metadata(duration_seconds=3725)
        assert meta.duration_formatted == "1:02:05"

    def test_minutes_seconds_only(self) -> None:
        meta = _make_metadata(duration_seconds=185)
        assert meta.duration_formatted == "3:05"

    def test_none_duration(self) -> None:
        meta = _make_metadata(duration_seconds=None)
        assert meta.duration_formatted == "unknown"


class TestYouTubeMetadataPublishDateFormatted:
    def test_known_date(self) -> None:
        meta = _make_metadata(publish_date=date(2024, 3, 15))
        assert meta.publish_date_formatted == "2024-03-15"

    def test_none_date(self) -> None:
        meta = _make_metadata(publish_date=None)
        assert meta.publish_date_formatted == "unknown"


class TestYouTubeMetadataToHeader:
    def test_header_contains_key_fields(self) -> None:
        meta = _make_metadata()
        header = meta.to_header()
        assert "Test Video" in header
        assert "Test Channel" in header
        assert "2024-03-15" in header
        assert "1:02:05" in header
        assert "1,234,567" in header
        assert meta.url in header

    def test_header_has_separator_lines(self) -> None:
        meta = _make_metadata()
        header = meta.to_header()
        assert "---" in header


class TestInfoToMetadata:
    def test_full_info(self) -> None:
        info = {
            "title": "My Video",
            "uploader": "My Channel",
            "upload_date": "20240315",
            "duration": 300,
            "view_count": 500,
            "description": "Hello",
            "like_count": 42,
        }
        meta = _info_to_metadata("https://example.com", info)
        assert meta.title == "My Video"
        assert meta.channel == "My Channel"
        assert meta.publish_date == date(2024, 3, 15)
        assert meta.duration_seconds == 300
        assert meta.view_count == 500
        assert meta.extra == {"like_count": 42}

    def test_missing_fields_use_defaults(self) -> None:
        meta = _info_to_metadata("https://example.com", {})
        assert meta.title == ""
        assert meta.channel == ""
        assert meta.publish_date is None
        assert meta.duration_seconds is None
        assert meta.view_count is None
