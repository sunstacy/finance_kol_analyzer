from __future__ import annotations

import argparse
import re
from uuid import uuid4
from pathlib import Path

from finance_kol_analyzer import fetch_youtube_metadata, get_youtube_transcript_text


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
    parser.add_argument(
        "--fallback-language",
        action="store_true",
        default=True,
        help=(
            "If the requested language is unavailable, automatically use the first "
            "available language instead of failing (default: on). "
            "Pass --no-fallback-language to disable."
        ),
    )
    parser.add_argument(
        "--no-fallback-language",
        dest="fallback_language",
        action="store_false",
        help="Fail instead of falling back to another language.",
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
            metadata = fetch_youtube_metadata(link)
            transcript = get_youtube_transcript_text(
                link,
                languages=languages,
                fallback_to_any_language=args.fallback_language,
            )
            output_path = next_available_path(
                args.output_dir / f"{sanitize_filename(metadata.title)}.txt"
            )
            content = metadata.to_header() + "\n\n" + transcript
            output_path.write_text(content, encoding="utf-8")
            print(f"Saved: {output_path}  [{metadata.channel} · {metadata.publish_date_formatted}]")
        except Exception as exc:
            print(f"Failed: {link}\n  Reason: {exc}")


def read_youtube_links(input_file: Path) -> list[str]:
    """Read links from a text file, skipping blank lines and comments."""

    return [
        line.strip()
        for line in input_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


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