from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finance_kol_analyzer.x_tweets import collect_x_user_tweets


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
        description="Collect recent posts from an X (Twitter) user via API v2 (tweepy)."
    )
    parser.add_argument("username", help="X handle, with or without leading @")
    parser.add_argument(
        "--max",
        type=int,
        default=100,
        metavar="N",
        help="Maximum number of posts to fetch (default: 100).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to twitter_config.yaml (default: TWITTER_CONFIG_PATH or ./twitter_config.yaml).",
    )
    args = parser.parse_args()

    try:
        tweets = collect_x_user_tweets(args.username, max_tweets=args.max, config_path=args.config)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for row in tweets:
        print(json.dumps(_tweet_to_jsonable(row), ensure_ascii=False))


if __name__ == "__main__":
    main()
