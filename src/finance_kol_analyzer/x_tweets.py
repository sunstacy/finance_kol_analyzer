"""Collect posts from an X (Twitter) user timeline via the official API v2.

Uses `tweepy` (https://github.com/tweepy/tweepy), the de facto Python client for
the X API. Provide a **Bearer token** (OAuth 2.0 app-only auth) via
``TWITTER_BEARER_TOKEN`` / ``X_BEARER_TOKEN``, a ``twitter_config.yaml`` file
(see :func:`load_twitter_config`), or ``bearer_token=`` / ``client=`` on the call.

``consumer_key`` / ``consumer_secret`` (or ``secret_key`` in YAML) are read and
kept on :class:`TwitterConfig` for your own use; timeline helpers here use the
bearer token.

Timeline access and volume depend on your X developer project tier; see X
developer documentation for current limits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from tweepy import Client


@dataclass(frozen=True)
class TwitterConfig:
    """Credentials loaded from YAML and/or the environment."""

    bearer_token: str | None = None
    consumer_key: str | None = None
    consumer_secret: str | None = None


@dataclass(frozen=True)
class XTweet:
    """One post from a user's timeline."""

    id: str
    text: str
    created_at: datetime | None = None
    public_metrics: dict[str, int] = field(default_factory=dict)


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
    """Load ``consumer_key``, ``consumer_secret`` / ``secret_key``, and ``bearer_token`` from a YAML file.

    Top-level keys are read. If a ``twitter`` mapping exists, its keys are merged
    over the rest (nested wins on collision).

    Recognized field names:

    * Bearer: ``bearer_token``
    * API key: ``consumer_key``, ``api_key``
    * API secret: ``consumer_secret``, ``secret_key``, ``api_secret``
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
        consumer_key=_first_str(
            os.environ.get("TWITTER_CONSUMER_KEY"),
            os.environ.get("TWITTER_API_KEY"),
            base.consumer_key,
        ),
        consumer_secret=_first_str(
            os.environ.get("TWITTER_CONSUMER_SECRET"),
            os.environ.get("TWITTER_API_SECRET"),
            base.consumer_secret,
        ),
    )


def create_x_client_from_env(config_path: Path | str | None = None) -> Client:
    """Build a :class:`tweepy.Client` from env vars and/or ``twitter_config.yaml``."""

    cfg = resolve_twitter_config(config_path)
    if not cfg.bearer_token:
        msg = (
            "No bearer token: set TWITTER_BEARER_TOKEN or X_BEARER_TOKEN, or add "
            "bearer_token to twitter_config.yaml (see TWITTER_CONFIG_PATH to relocate the file)."
        )
        raise ValueError(msg)
    return Client(bearer_token=cfg.bearer_token)


def collect_x_user_tweets(
    username: str,
    *,
    max_tweets: int = 100,
    bearer_token: str | None = None,
    client: Client | None = None,
    config_path: Path | str | None = None,
) -> list[XTweet]:
    """Return recent posts from the given X username (handle, with or without ``@``).

    Args:
        username: Screen name / handle.
        max_tweets: Maximum number of posts to return (paginates in batches up to 100).
        bearer_token: OAuth 2.0 Bearer token. If omitted, ``client`` or env / YAML is used.
        client: Optional pre-built :class:`tweepy.Client` (e.g. for tests).
        config_path: Optional path to ``twitter_config.yaml`` (defaults per :func:`resolve_twitter_config_path`).

    Returns:
        Newest-first list of :class:`XTweet` instances.

    Raises:
        ValueError: Missing credentials, invalid ``max_tweets``, or unknown user.
        tweepy.TweepyException: On API errors (rate limits, auth, etc.).
    """
    if max_tweets < 1:
        raise ValueError("max_tweets must be at least 1")

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

    tweets: list[XTweet] = []
    pagination_token: str | None = None

    while len(tweets) < max_tweets:
        page_size = min(100, max_tweets - len(tweets))
        resp = resolved.get_users_tweets(
            user_id,
            max_results=page_size,
            pagination_token=pagination_token,
            tweet_fields=["created_at", "public_metrics"],
        )
        if not resp.data:
            break
        for tweet in resp.data:
            tweets.append(_tweet_model_to_xtweet(tweet))
        next_token = (resp.meta or {}).get("next_token") if resp.meta else None
        if not next_token:
            break
        pagination_token = next_token

    return tweets[:max_tweets]


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
        consumer_key=_mapping_str(m, "consumer_key", "consumerKey", "api_key", "apiKey"),
        consumer_secret=_mapping_str(
            m,
            "consumer_secret",
            "consumerSecret",
            "secret_key",
            "api_secret",
            "apiSecret",
        ),
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
