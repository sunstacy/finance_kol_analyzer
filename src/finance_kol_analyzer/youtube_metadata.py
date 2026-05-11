"""Fetch metadata for a YouTube video using yt-dlp."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class YouTubeMetadata:
    """Metadata for a single YouTube video."""

    url: str
    title: str
    channel: str
    publish_date: date | None
    duration_seconds: int | None
    view_count: int | None
    description: str

    # Extra fields yt-dlp may provide
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_formatted(self) -> str:
        """Return duration as HH:MM:SS or MM:SS string."""
        if self.duration_seconds is None:
            return "unknown"
        total = int(self.duration_seconds)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def publish_date_formatted(self) -> str:
        if self.publish_date is None:
            return "unknown"
        return self.publish_date.strftime("%Y-%m-%d")

    def to_header(self) -> str:
        """Return a human-readable metadata header for the transcript file."""
        lines = [
            f"Title        : {self.title}",
            f"Channel      : {self.channel}",
            f"Published    : {self.publish_date_formatted}",
            f"Duration     : {self.duration_formatted}",
            f"Views        : {self.view_count:,}" if self.view_count is not None else "Views        : unknown",
            f"URL          : {self.url}",
        ]
        separator = "-" * 60
        return separator + "\n" + "\n".join(lines) + "\n" + separator


def fetch_youtube_metadata(youtube_url: str) -> YouTubeMetadata:
    """Fetch metadata for a YouTube video without downloading it.

    Uses ``yt-dlp`` to retrieve title, channel name, publish date,
    duration, view count, and description. No API key is required.

    Args:
        youtube_url: Any YouTube URL or video ID accepted by yt-dlp.

    Returns:
        A :class:`YouTubeMetadata` instance populated from yt-dlp info.

    Raises:
        ImportError: If yt-dlp is not installed.
        yt_dlp.utils.DownloadError: If the video is unavailable or private.
    """
    import yt_dlp  # type: ignore[import]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info: dict[str, Any] = ydl.extract_info(youtube_url, download=False) or {}

    return _info_to_metadata(youtube_url, info)


def _info_to_metadata(url: str, info: dict[str, Any]) -> YouTubeMetadata:
    publish_date = _parse_upload_date(info.get("upload_date"))

    return YouTubeMetadata(
        url=url,
        title=str(info.get("title") or ""),
        channel=str(info.get("uploader") or info.get("channel") or ""),
        publish_date=publish_date,
        duration_seconds=_safe_int(info.get("duration")),
        view_count=_safe_int(info.get("view_count")),
        description=str(info.get("description") or ""),
        extra={
            k: info[k]
            for k in ("like_count", "comment_count", "tags", "categories")
            if k in info
        },
    )


def _parse_upload_date(raw: Any) -> date | None:
    """Parse yt-dlp's YYYYMMDD upload_date string into a :class:`date`."""
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw), "%Y%m%d").date()
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
