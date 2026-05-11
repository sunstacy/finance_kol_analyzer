from __future__ import annotations

import argparse
import json
import re
import ssl
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

from finance_kol_analyzer import get_youtube_transcript_text

# Use certifi's CA bundle so macOS Python can verify HTTPS certificates.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


DEFAULT_INPUT_FILE = Path("youtube_links.txt")
DEFAULT_OUTPUT_DIR = Path("transcripts")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch YouTube transcripts from a links file and save them as text files."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_FILE,
        type=Path,
        help="Text file containing one YouTube link per line.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        type=Path,
        help="Folder where transcript text files will be saved.",
    )
    parser.add_argument(
        "--languages",
        default="en",
        help="Comma-separated language codes ordered by preference, for example: en,zh-Hans",
    )
    args = parser.parse_args()

    links = read_youtube_links(args.input)
    if not links:
        print(f"No YouTube links found in {args.input}.")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    languages = [language.strip() for language in args.languages.split(",") if language.strip()]

    for link in links:
        try:
            title = fetch_youtube_title(link)
            transcript = get_youtube_transcript_text(link, languages=languages)
            output_path = next_available_path(
                args.output_dir / f"{sanitize_filename(title)}.txt"
            )
            output_path.write_text(transcript, encoding="utf-8")
            print(f"Saved: {output_path}")
        except Exception as exc:
            print(f"Failed: {link}\n  Reason: {exc}")


def read_youtube_links(input_file: Path) -> list[str]:
    """Read links from a text file, skipping blank lines and comments."""

    return [
        line.strip()
        for line in input_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def fetch_youtube_title(youtube_link: str) -> str:
    """Fetch a YouTube title using the public oEmbed endpoint."""

    query = urlencode({"url": youtube_link, "format": "json"})
    with urlopen(
        f"https://www.youtube.com/oembed?{query}", timeout=15, context=_SSL_CONTEXT
    ) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data["title"])


def sanitize_filename(title: str) -> str:
    """Convert a YouTube title into a safe cross-platform filename."""

    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
    if not sanitized:
        sanitized = "youtube_transcript"
    return sanitized[:150]


def next_available_path(path: Path) -> Path:
    """Avoid overwriting an existing transcript with the same title."""

    if not path.exists():
        return path

    for counter in range(2, 10_000):
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate

    return path.with_name(f"{path.stem} ({uuid4().hex[:8]}){path.suffix}")


if __name__ == "__main__":
    main()