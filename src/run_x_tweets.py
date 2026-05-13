from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from finance_kol_analyzer.x_tweets import (
    collect_x_user_tweets,
    parse_utc_date,
    utc_year_bounds,
)


def _tweet_to_jsonable(tweet: object) -> dict:
    from finance_kol_analyzer.x_tweets import XTweet

    assert isinstance(tweet, XTweet)
    return {
        "id": tweet.id,
        "text": tweet.text,
        "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
        "public_metrics": tweet.public_metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Collect posts from an X (Twitter) user via API v2 (tweepy). "
            "Use --year or --since/--until so the API only returns posts in that window "
            "(cheapest when you pay per returned post)."
        )
    )
    parser.add_argument("username", help="X handle, with or without leading @")
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Maximum posts to fetch (default: 100, or 50000 if --year is set). "
            "Raise this if one user posted more than the default in that window."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to twitter_config.yaml (default: TWITTER_CONFIG_PATH or ./twitter_config.yaml).",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        metavar="YYYY",
        help="Only tweets in this UTC calendar year (sets API start_time / end_time).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Only tweets at or after this UTC date (inclusive). Overrides --year for the start bound.",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Only tweets before this UTC date (exclusive, API end_time). Overrides --year for the end bound.",
    )
    parser.add_argument(
        "--exclude-retweets",
        action="store_true",
        help="Omit retweets (fewer posts if you do not need them).",
    )
    parser.add_argument(
        "--exclude-replies",
        action="store_true",
        help="Omit replies (fewer posts if you do not need them).",
    )
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        help="Do not request public_metrics (slightly leaner payloads).",
    )
    args = parser.parse_args()

    start_time: datetime | None = None
    end_time: datetime | None = None

    if args.year is not None:
        start_time, end_time = utc_year_bounds(args.year)
    if args.since is not None:
        start_time = parse_utc_date(args.since)
    if args.until is not None:
        end_time = parse_utc_date(args.until)

    max_tweets = args.max
    if max_tweets is None:
        max_tweets = 50_000 if (args.year is not None or args.since is not None or args.until is not None) else 100

    try:
        tweets = collect_x_user_tweets(
            args.username,
            max_tweets=max_tweets,
            config_path=args.config,
            start_time=start_time,
            end_time=end_time,
            exclude_retweets=args.exclude_retweets,
            exclude_replies=args.exclude_replies,
            include_public_metrics=not args.no_metrics,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for row in tweets:
        print(json.dumps(_tweet_to_jsonable(row), ensure_ascii=False))


if __name__ == "__main__":
    main()
