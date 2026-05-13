from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from finance_kol_analyzer.x_tweets import collect_user_tweets_to_monthly_files, parse_utc_date


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download one user's tweets from 2025-01-01 through now (UTC), "
            "and save one file per calendar month under <handle>_tweets/ "
            "(each line: JSON with posted_at and text)."
        )
    )
    parser.add_argument("username", help="X handle, with or without leading @")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("."),
        help="Directory in which <username>_tweets/ will be created (default: current directory).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default="2025-01-01",
        metavar="YYYY-MM-DD",
        help="UTC start date inclusive (default: 2025-01-01).",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="UTC end date exclusive; default: now UTC. Use YYYY-MM-DD for end-of-day boundaries.",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=100_000,
        metavar="N",
        help="Safety cap on tweets to fetch (default: 100000).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to twitter_config.yaml (default: TWITTER_CONFIG_PATH or ./twitter_config.yaml).",
    )
    parser.add_argument(
        "--exclude-retweets",
        action="store_true",
        help="Omit retweets from the export.",
    )
    parser.add_argument(
        "--exclude-replies",
        action="store_true",
        help="Omit replies from the export.",
    )
    args = parser.parse_args()

    since_dt = parse_utc_date(args.since)
    if args.until is None:
        until_dt: datetime | None = None
    else:
        until_dt = parse_utc_date(args.until)

    try:
        out = collect_user_tweets_to_monthly_files(
            args.username,
            since=since_dt,
            until=until_dt,
            output_parent=args.base_dir,
            max_tweets=args.max,
            config_path=args.config,
            exclude_retweets=args.exclude_retweets,
            exclude_replies=args.exclude_replies,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Saved under {out}")


if __name__ == "__main__":
    main()
