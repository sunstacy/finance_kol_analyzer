"""Helpers for fetching YouTube transcripts from user-facing links."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol, TypedDict, cast
from urllib.parse import parse_qs, unquote, urlparse


class TranscriptSnippet(TypedDict):
    """A single timestamped transcript snippet."""

    text: str
    start: float
    duration: float


class TranscriptApi(Protocol):
    """Subset of youtube-transcript-api used by this module."""

    def fetch(
        self,
        video_id: str,
        *,
        languages: Sequence[str],
        preserve_formatting: bool = False,
    ) -> Any:
        """Fetch a transcript for a YouTube video."""

    def list(self, video_id: str) -> Any:
        """List available transcripts for a YouTube video."""


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_PATH_VIDEO_ID_PREFIXES = {"embed", "shorts", "live", "v"}


def extract_youtube_video_id(youtube_link: str) -> str:
    """Extract a YouTube video ID from common YouTube URL formats.

    Args:
        youtube_link: A YouTube URL such as ``https://youtu.be/dQw4w9WgXcQ``
            or ``https://www.youtube.com/watch?v=dQw4w9WgXcQ``. A bare
            11-character video ID is also accepted.

    Returns:
        The 11-character YouTube video ID.

    Raises:
        ValueError: If the input is empty, not a supported YouTube URL, or does
            not contain a valid video ID.
    """

    link = youtube_link.strip()
    if not link:
        raise ValueError("A YouTube link or video ID is required.")

    if _is_valid_video_id(link):
        return link

    parsed = urlparse(_with_scheme_if_needed(link))
    hostname = (parsed.hostname or "").lower()
    if hostname not in _YOUTUBE_HOSTS:
        raise ValueError(f"Unsupported YouTube host: {hostname or 'missing host'}.")

    query = parse_qs(parsed.query)

    if hostname == "youtu.be":
        return _validate_video_id(_first_path_segment(parsed.path))

    if "v" in query:
        return _validate_video_id(query["v"][0])

    if "u" in query:
        return extract_youtube_video_id(_absolutize_youtube_path(unquote(query["u"][0])))

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if path_segments and path_segments[0] == "attribution_link" and "u" in query:
        return extract_youtube_video_id(_absolutize_youtube_path(unquote(query["u"][0])))

    if len(path_segments) >= 2 and path_segments[0] in _PATH_VIDEO_ID_PREFIXES:
        return _validate_video_id(path_segments[1])

    raise ValueError(f"Could not find a YouTube video ID in: {youtube_link!r}.")


def get_youtube_transcript(
    youtube_link: str,
    languages: Sequence[str] | str = ("en",),
    *,
    preserve_formatting: bool = False,
    fallback_to_any_language: bool = False,
    api: TranscriptApi | None = None,
) -> list[TranscriptSnippet]:
    """Fetch timestamped transcript snippets for a YouTube link.

    The implementation uses the maintained ``youtube-transcript-api`` package.
    It supports manually created and auto-generated captions without requiring a
    YouTube API key or a headless browser.

    Args:
        youtube_link: A YouTube link or bare video ID.
        languages: Preferred caption language codes, ordered by priority.
            Defaults to English. A single language string is accepted.
        preserve_formatting: Keep YouTube formatting tags when supported by the
            upstream transcript API.
        fallback_to_any_language: If True and the requested languages are not
            available, automatically fetch the first available transcript in
            any language instead of raising an error.
        api: Optional injected ``YouTubeTranscriptApi``-compatible instance.
            This is useful for tests or for supplying a preconfigured proxy.

    Returns:
        A list of dictionaries with ``text``, ``start``, and ``duration`` keys.

    Raises:
        ValueError: If the link or languages are invalid.
        youtube_transcript_api exceptions: Propagated when captions are disabled,
            unavailable in the requested language, or YouTube blocks the request.
    """

    video_id = extract_youtube_video_id(youtube_link)
    normalized_languages = _normalize_languages(languages)
    transcript_api = api or _default_transcript_api()

    try:
        transcript = transcript_api.fetch(
            video_id,
            languages=normalized_languages,
            preserve_formatting=preserve_formatting,
        )
    except Exception as exc:
        if not fallback_to_any_language:
            raise
        transcript = _fetch_any_available_transcript(
            transcript_api, video_id, preserve_formatting, original_error=exc
        )

    raw_snippets = (
        transcript.to_raw_data()
        if hasattr(transcript, "to_raw_data")
        else cast(Iterable[Any], transcript)
    )

    return [_normalize_snippet(snippet) for snippet in raw_snippets]


def _fetch_any_available_transcript(
    transcript_api: TranscriptApi,
    video_id: str,
    preserve_formatting: bool,
    original_error: Exception,
) -> Any:
    """Return the first available transcript regardless of language."""
    try:
        transcript_list = transcript_api.list(video_id)
        transcript = next(iter(transcript_list))
        return transcript.fetch()
    except Exception:
        raise original_error


def get_youtube_transcript_text(
    youtube_link: str,
    languages: Sequence[str] | str = ("en",),
    *,
    preserve_formatting: bool = False,
    fallback_to_any_language: bool = False,
    separator: str = "\n",
    api: TranscriptApi | None = None,
) -> str:
    """Fetch a transcript and join all snippets into plain text."""

    snippets = get_youtube_transcript(
        youtube_link,
        languages=languages,
        preserve_formatting=preserve_formatting,
        fallback_to_any_language=fallback_to_any_language,
        api=api,
    )
    return separator.join(snippet["text"] for snippet in snippets)


def create_youtube_transcript_api_from_env() -> TranscriptApi:
    """Create a transcript API client configured from proxy environment vars.

    Supported variables:
        YOUTUBE_TRANSCRIPT_PROXY: Generic proxy URL used for both HTTP and HTTPS.
        YOUTUBE_TRANSCRIPT_HTTP_PROXY: Generic HTTP proxy URL.
        YOUTUBE_TRANSCRIPT_HTTPS_PROXY: Generic HTTPS proxy URL.
        YOUTUBE_TRANSCRIPT_WEBSHARE_USERNAME: Webshare proxy username.
        YOUTUBE_TRANSCRIPT_WEBSHARE_PASSWORD: Webshare proxy password.
        YOUTUBE_TRANSCRIPT_WEBSHARE_LOCATIONS: Optional comma-separated
            Webshare country codes, such as ``us,de``.
    """

    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

    generic_proxy = os.getenv("YOUTUBE_TRANSCRIPT_PROXY")
    http_proxy = os.getenv("YOUTUBE_TRANSCRIPT_HTTP_PROXY") or generic_proxy
    https_proxy = os.getenv("YOUTUBE_TRANSCRIPT_HTTPS_PROXY") or generic_proxy
    webshare_username = os.getenv("YOUTUBE_TRANSCRIPT_WEBSHARE_USERNAME")
    webshare_password = os.getenv("YOUTUBE_TRANSCRIPT_WEBSHARE_PASSWORD")
    webshare_locations = _parse_comma_separated_env(
        os.getenv("YOUTUBE_TRANSCRIPT_WEBSHARE_LOCATIONS")
    )

    has_generic_proxy = bool(http_proxy or https_proxy)
    has_webshare_proxy = bool(webshare_username or webshare_password)

    if has_generic_proxy and has_webshare_proxy:
        raise ValueError(
            "Configure either generic YouTube transcript proxy variables or "
            "Webshare proxy variables, not both."
        )

    http_client = _make_certifi_session()

    if has_webshare_proxy:
        if not webshare_username or not webshare_password:
            raise ValueError(
                "Both YOUTUBE_TRANSCRIPT_WEBSHARE_USERNAME and "
                "YOUTUBE_TRANSCRIPT_WEBSHARE_PASSWORD are required."
            )
        return YouTubeTranscriptApi(
            http_client=http_client,
            proxy_config=WebshareProxyConfig(
                proxy_username=webshare_username,
                proxy_password=webshare_password,
                filter_ip_locations=webshare_locations,
            ),
        )

    if has_generic_proxy:
        return YouTubeTranscriptApi(
            http_client=http_client,
            proxy_config=GenericProxyConfig(
                http_url=http_proxy,
                https_url=https_proxy,
            ),
        )

    return YouTubeTranscriptApi(http_client=http_client)


def _default_transcript_api() -> TranscriptApi:
    return create_youtube_transcript_api_from_env()


def _make_certifi_session() -> Any:
    import certifi
    import requests

    session = requests.Session()
    session.verify = certifi.where()
    return session


def _with_scheme_if_needed(link: str) -> str:
    known_prefixes = (
        "youtube.com/",
        "www.youtube.com/",
        "m.youtube.com/",
        "music.youtube.com/",
        "youtu.be/",
        "youtube-nocookie.com/",
        "www.youtube-nocookie.com/",
    )
    if "://" not in link and link.lower().startswith(known_prefixes):
        return f"https://{link}"
    return link


def _first_path_segment(path: str) -> str:
    return next((segment for segment in path.split("/") if segment), "")


def _absolutize_youtube_path(path_or_url: str) -> str:
    parsed = urlparse(path_or_url)
    if parsed.hostname:
        return path_or_url
    if path_or_url.startswith("/"):
        return f"https://www.youtube.com{path_or_url}"
    return f"https://www.youtube.com/{path_or_url}"


def _normalize_languages(languages: Sequence[str] | str) -> list[str]:
    if isinstance(languages, str):
        languages = [languages]

    normalized = [language.strip() for language in languages if language.strip()]
    if not normalized:
        raise ValueError("At least one transcript language code is required.")
    return normalized


def _parse_comma_separated_env(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_snippet(snippet: Any) -> TranscriptSnippet:
    if isinstance(snippet, Mapping):
        text = snippet["text"]
        start = snippet["start"]
        duration = snippet["duration"]
    else:
        text = snippet.text
        start = snippet.start
        duration = snippet.duration

    return {
        "text": str(text),
        "start": float(start),
        "duration": float(duration),
    }


def _validate_video_id(video_id: str) -> str:
    cleaned = video_id.strip()
    if not _is_valid_video_id(cleaned):
        raise ValueError(f"Invalid YouTube video ID: {video_id!r}.")
    return cleaned


def _is_valid_video_id(video_id: str) -> bool:
    return bool(_VIDEO_ID_RE.fullmatch(video_id))
