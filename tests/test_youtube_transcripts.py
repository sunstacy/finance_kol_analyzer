from __future__ import annotations

from dataclasses import dataclass

import pytest

from finance_kol_analyzer.youtube_transcripts import (
    extract_youtube_video_id,
    get_youtube_transcript,
    get_youtube_transcript_text,
)


VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "youtube_link",
    [
        VIDEO_ID,
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&ab_channel=RickAstley",
        f"https://youtu.be/{VIDEO_ID}?si=share-token",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        f"www.youtube.com/watch?v={VIDEO_ID}",
        f"youtu.be/{VIDEO_ID}",
        (
            "https://www.youtube.com/attribution_link"
            f"?u=%2Fwatch%3Fv%3D{VIDEO_ID}%26feature%3Dshare"
        ),
    ],
)
def test_extract_youtube_video_id_from_supported_links(youtube_link: str) -> None:
    assert extract_youtube_video_id(youtube_link) == VIDEO_ID


@pytest.mark.parametrize(
    "youtube_link",
    [
        "",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=too-short",
        "https://www.youtube.com/playlist?list=PL123",
    ],
)
def test_extract_youtube_video_id_rejects_invalid_links(youtube_link: str) -> None:
    with pytest.raises(ValueError):
        extract_youtube_video_id(youtube_link)


def test_get_youtube_transcript_fetches_with_normalized_options() -> None:
    api = FakeTranscriptApi()

    transcript = get_youtube_transcript(
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        languages="en",
        preserve_formatting=True,
        api=api,
    )

    assert api.calls == [
        {
            "video_id": VIDEO_ID,
            "languages": ["en"],
            "preserve_formatting": True,
        }
    ]
    assert transcript == [
        {"text": "hello", "start": 0.0, "duration": 1.25},
        {"text": "world", "start": 1.25, "duration": 2.0},
    ]


def test_get_youtube_transcript_text_joins_snippet_text() -> None:
    text = get_youtube_transcript_text(
        VIDEO_ID,
        languages=["en"],
        separator=" ",
        api=FakeTranscriptApi(),
    )

    assert text == "hello world"


def test_get_youtube_transcript_requires_at_least_one_language() -> None:
    with pytest.raises(ValueError):
        get_youtube_transcript(VIDEO_ID, languages=[], api=FakeTranscriptApi())


class FakeTranscriptApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def fetch(
        self,
        video_id: str,
        *,
        languages: list[str],
        preserve_formatting: bool = False,
    ) -> FakeTranscript:
        self.calls.append(
            {
                "video_id": video_id,
                "languages": languages,
                "preserve_formatting": preserve_formatting,
            }
        )
        return FakeTranscript(
            [
                FakeSnippet(text="hello", start=0, duration=1.25),
                FakeSnippet(text="world", start=1.25, duration=2),
            ]
        )


@dataclass(frozen=True)
class FakeSnippet:
    text: str
    start: float
    duration: float


class FakeTranscript:
    def __init__(self, snippets: list[FakeSnippet]) -> None:
        self._snippets = snippets

    def to_raw_data(self) -> list[dict[str, float | str]]:
        return [
            {
                "text": snippet.text,
                "start": snippet.start,
                "duration": snippet.duration,
            }
            for snippet in self._snippets
        ]
