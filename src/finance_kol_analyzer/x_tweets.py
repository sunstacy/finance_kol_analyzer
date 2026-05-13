"""Collect posts from an X (Twitter) user timeline via the official API v2.

Uses `tweepy` (https://github.com/tweepy/tweepy) with **OAuth 2.0 only**:

* **App bearer** — set ``bearer_token`` in ``twitter_config.yaml`` or
  ``TWITTER_BEARER_TOKEN`` / ``X_BEARER_TOKEN``.
* **User bearer (PKCE)** — set ``client_id``, ``client_secret``, and ``access_token``
  (the user access token). Requests use ``Authorization: Bearer <access_token>``;
  ``client_id`` / ``client_secret`` are not sent on each HTTP call but must be
  present so your config matches the app that issued the token.

Timeline access and volume depend on your X developer project tier; see X
developer documentation for current limits.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import yaml
from tweepy import Client


@dataclass(frozen=True)
class TwitterConfig:
    """OAuth 2.0 credentials for X API v2 (loaded from YAML and/or the environment)."""

    bearer_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    access_token: str | None = None


@dataclass(frozen=True)
class XTweet:
    """One post from a user's timeline."""

    id: str
    text: str
    created_at: datetime | None = None
    public_metrics: dict[str, int] = field(default_factory=dict)


def utc_year_bounds(year: int) -> tuple[datetime, datetime]:
    """Return ``(start_time, end_time)`` for X user-timeline filters: inclusive start, **exclusive** end (UTC).

    The X API ``end_time`` parameter is exclusive; use ``year + 1`` Jan 1 as end.
    """

    start = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return start, end


def parse_utc_date(date_str: str) -> datetime:
    """Parse ``YYYY-MM-DD`` as midnight UTC."""

    raw = date_str.strip()
    dt = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt


def normalize_x_username(username: str) -> str:
    """Strip whitespace and a leading ``@`` from a handle."""

    handle = username.strip()
    if handle.startswith("@"):
        handle = handle[1:]
    return handle


def resolve_twitter_config_path(config_path: Path | str | None = None) -> Path:
    """Default config path: explicit ``config_path``, else ``TWITTER_CONFIG_PATH``, else ``twitter_config.yaml``."""

    if config_path is not None:
        return Path(config_path)
    env_path = os.environ.get("TWITTER_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return Path("twitter_config.yaml")


def load_twitter_config(path: Path | str) -> TwitterConfig:
    """Load OAuth 2.0 credentials from a YAML file.

    Top-level keys are read. If a ``twitter`` mapping exists, its keys are merged
    over the rest (nested wins on collision).

    Keys: ``bearer_token`` (optional), ``client_id``, ``client_secret``,
    ``access_token`` (OAuth 2.0 user token when not using app ``bearer_token`` alone).
    """

    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Twitter config not found: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if raw is None:
        return TwitterConfig()
    if not isinstance(raw, dict):
        raise ValueError("twitter_config.yaml must contain a YAML mapping at the top level")
    merged = dict(raw)
    nested = raw.get("twitter")
    if isinstance(nested, dict):
        merged = {k: v for k, v in merged.items() if k != "twitter"}
        merged.update(nested)
    return _twitter_config_from_mapping(merged)


def resolve_twitter_config(config_path: Path | str | None = None) -> TwitterConfig:
    """Load ``twitter_config.yaml`` when present, then apply environment overrides (env wins)."""

    path = resolve_twitter_config_path(config_path)
    base = load_twitter_config(path) if path.is_file() else TwitterConfig()
    return TwitterConfig(
        bearer_token=_first_str(
            os.environ.get("TWITTER_BEARER_TOKEN"),
            os.environ.get("X_BEARER_TOKEN"),
            base.bearer_token,
        ),
        client_id=_first_str(
            os.environ.get("TWITTER_CLIENT_ID"),
            os.environ.get("X_CLIENT_ID"),
            base.client_id,
        ),
        client_secret=_first_str(
            os.environ.get("TWITTER_CLIENT_SECRET"),
            os.environ.get("X_CLIENT_SECRET"),
            base.client_secret,
        ),
        access_token=_first_str(
            os.environ.get("TWITTER_ACCESS_TOKEN"),
            os.environ.get("TWITTER_OAUTH2_ACCESS_TOKEN"),
            base.access_token,
        ),
    )


def create_x_client_from_env(config_path: Path | str | None = None) -> Client:
    """Build a :class:`tweepy.Client` using OAuth 2.0 credentials from env and/or ``twitter_config.yaml``."""

    cfg = resolve_twitter_config(config_path)
    if cfg.bearer_token:
        return Client(bearer_token=cfg.bearer_token)
    if cfg.client_id and cfg.client_secret and cfg.access_token:
        return Client(bearer_token=cfg.access_token)
    raise ValueError(
        "Missing OAuth 2.0 credentials. Set bearer_token, or set client_id, "
        "client_secret, and access_token (user access token from the PKCE flow)."
    )


def collect_x_user_tweets(
    username: str,
    *,
    max_tweets: int = 100,
    bearer_token: str | None = None,
    client: Client | None = None,
    config_path: Path | str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    exclude_retweets: bool = False,
    exclude_replies: bool = False,
    include_public_metrics: bool = True,
) -> list[XTweet]:
    """Return recent posts from the given X username (handle, with or without ``@``).

    Args:
        username: Screen name / handle.
        max_tweets: Maximum number of posts to return (paginates in batches up to 100).
        bearer_token: OAuth 2.0 Bearer token. If omitted, ``client`` or env / YAML is used.
        client: Optional pre-built :class:`tweepy.Client` (e.g. for tests).
        config_path: Optional path to ``twitter_config.yaml`` (defaults per :func:`resolve_twitter_config_path`).
        start_time: If set, only tweets at or after this instant (UTC). Pass to the API to avoid
            paying for posts outside the window when usage is billed per returned post.
        end_time: If set, only tweets **before** this instant (UTC). The X ``end_time`` parameter is exclusive.
        exclude_retweets: When true, omit retweets from results (fewer rows if you do not need them).
        exclude_replies: When true, omit replies from results.
        include_public_metrics: When false, omit ``public_metrics`` from ``tweet_fields`` (slightly leaner payloads).

    Returns:
        Newest-first list of :class:`XTweet` instances.

    Raises:
        ValueError: Missing credentials, invalid ``max_tweets``, or unknown user.
        tweepy.TweepyException: On API errors (rate limits, auth, etc.).
    """
    if max_tweets < 1:
        raise ValueError("max_tweets must be at least 1")
    if start_time is not None and end_time is not None and start_time >= end_time:
        raise ValueError("start_time must be before end_time")

    if client is not None:
        resolved = client
    elif bearer_token:
        resolved = Client(bearer_token=bearer_token)
    else:
        resolved = create_x_client_from_env(config_path=config_path)
    handle = normalize_x_username(username)
    if not handle:
        raise ValueError("username is empty")

    user_resp = resolved.get_user(username=handle)
    if user_resp.data is None:
        raise ValueError(f"User not found: @{handle}")
    user_id = user_resp.data.id

    exclude: list[str] = []
    if exclude_retweets:
        exclude.append("retweets")
    if exclude_replies:
        exclude.append("replies")

    tweet_fields: list[str] = ["created_at"]
    if include_public_metrics:
        tweet_fields.append("public_metrics")

    tweets: list[XTweet] = []
    pagination_token: str | None = None

    while len(tweets) < max_tweets:
        page_size = min(100, max_tweets - len(tweets))
        kwargs: dict[str, Any] = {
            "max_results": page_size,
            "tweet_fields": tweet_fields,
        }
        if pagination_token is not None:
            kwargs["pagination_token"] = pagination_token
        if exclude:
            kwargs["exclude"] = exclude
        if start_time is not None:
            kwargs["start_time"] = start_time
        if end_time is not None:
            kwargs["end_time"] = end_time

        resp = resolved.get_users_tweets(user_id, **kwargs)
        if not resp.data:
            break
        for tweet in resp.data:
            tweets.append(_tweet_model_to_xtweet(tweet))
        next_token = (resp.meta or {}).get("next_token") if resp.meta else None
        if not next_token:
            break
        pagination_token = next_token

    return tweets[:max_tweets]


def user_tweets_archive_dirname(username: str) -> str:
    """Return ``<handle>_tweets`` with filesystem-safe characters (handle without ``@``)."""

    base = normalize_x_username(username)
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", base).strip("_")
    if not safe:
        safe = "user"
    return f"{safe}_tweets"


def tweet_to_archive_record(tweet: XTweet) -> dict[str, Any]:
    """Minimal dict for monthly export: posting time (ISO UTC) and text."""

    if tweet.created_at is not None:
        posted = tweet.created_at.astimezone(timezone.utc).isoformat()
    else:
        posted = None
    return {"posted_at": posted, "text": tweet.text}


def group_xtweets_by_month_utc(tweets: Sequence[XTweet]) -> dict[tuple[int, int], list[XTweet]]:
    """Bucket tweets by ``(year, month)`` in UTC. Tweets without ``created_at`` are omitted."""

    buckets: dict[tuple[int, int], list[XTweet]] = defaultdict(list)
    for t in tweets:
        if t.created_at is None:
            continue
        c = t.created_at.astimezone(timezone.utc)
        buckets[(c.year, c.month)].append(t)
    return dict(buckets)


def write_xtweets_monthly_files(tweets: Sequence[XTweet], output_dir: Path) -> list[Path]:
    """Write ``YYYY-MM.txt`` files (JSON lines: ``posted_at``, ``text``), oldest first within each month."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    buckets = group_xtweets_by_month_utc(tweets)
    written: list[Path] = []
    for year, month in sorted(buckets.keys()):
        rows = sorted(
            buckets[(year, month)],
            key=lambda tw: tw.created_at or datetime.min.replace(tzinfo=timezone.utc),
        )
        path = output_dir / f"{year}-{month:02d}.txt"
        lines = [json.dumps(tweet_to_archive_record(tw), ensure_ascii=False) for tw in rows]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        written.append(path)
    return written


def collect_user_tweets_to_monthly_files(
    username: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    output_parent: Path | str = Path("."),
    max_tweets: int = 100_000,
    bearer_token: str | None = None,
    client: Client | None = None,
    config_path: Path | str | None = None,
    exclude_retweets: bool = False,
    exclude_replies: bool = False,
    include_public_metrics: bool = False,
) -> Path:
    """Fetch tweets in ``[since, until)`` (UTC) and save one ``YYYY-MM.txt`` per month under ``<username>_tweets/``.

    Each line in a month file is a JSON object with ``posted_at`` (ISO-8601 UTC) and ``text``.

    Defaults: ``since`` = 2025-01-01 00:00 UTC, ``until`` = current time UTC (``end_time`` is exclusive on the API).

    Returns:
        Absolute path to the output directory (``.../<handle>_tweets``).
    """

    start = since if since is not None else parse_utc_date("2025-01-01")
    end = until if until is not None else datetime.now(timezone.utc)
    if start >= end:
        raise ValueError("until must be after since (API uses exclusive end_time)")

    tweets = collect_x_user_tweets(
        username,
        max_tweets=max_tweets,
        bearer_token=bearer_token,
        client=client,
        config_path=config_path,
        start_time=start,
        end_time=end,
        exclude_retweets=exclude_retweets,
        exclude_replies=exclude_replies,
        include_public_metrics=include_public_metrics,
    )
    folder = Path(output_parent) / user_tweets_archive_dirname(username)
    write_xtweets_monthly_files(tweets, folder)
    return folder.resolve()


def _tweet_model_to_xtweet(tweet: Any) -> XTweet:
    metrics: dict[str, int] = {}
    raw_metrics = getattr(tweet, "public_metrics", None)
    if isinstance(raw_metrics, dict):
        metrics = {k: int(v) for k, v in raw_metrics.items() if isinstance(v, (int, float))}
    elif raw_metrics is not None:
        for key in ("retweet_count", "reply_count", "like_count", "quote_count", "bookmark_count", "impression_count"):
            val = getattr(raw_metrics, key, None)
            if val is not None:
                metrics[key] = int(val)

    created = getattr(tweet, "created_at", None)
    if isinstance(created, datetime):
        created_at: datetime | None = created
    else:
        created_at = None

    return XTweet(
        id=str(tweet.id),
        text=str(tweet.text or ""),
        created_at=created_at,
        public_metrics=metrics,
    )


def _first_str(*candidates: str | None) -> str | None:
    for c in candidates:
        if c is not None and str(c).strip():
            return str(c).strip()
    return None


def _twitter_config_from_mapping(m: dict[str, Any]) -> TwitterConfig:
    return TwitterConfig(
        bearer_token=_mapping_str(m, "bearer_token", "bearerToken"),
        client_id=_mapping_str(m, "client_id", "clientId"),
        client_secret=_mapping_str(m, "client_secret", "clientSecret"),
        access_token=_mapping_str(m, "access_token", "accessToken"),
    )


def _mapping_str(m: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key not in m:
            continue
        val = m[key]
        if val is None:
            continue
        s = str(val).strip()
        if s:
            return s
    return None
