"""Collect posts from an X (Twitter) user timeline via the official API v2.

Uses `tweepy` (https://github.com/tweepy/tweepy), the de facto Python client for
the X API. This requires a developer app and a **Bearer token** (OAuth 2.0 app-only
auth). Set ``TWITTER_BEARER_TOKEN`` or ``X_BEARER_TOKEN`` in the environment, or
pass ``bearer_token=`` / ``client=`` explicitly.

Timeline access and volume depend on your X developer project tier; see X
developer documentation for current limits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tweepy import Client


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


def create_x_client_from_env() -> Client:
    """Build a :class:`tweepy.Client` using env ``TWITTER_BEARER_TOKEN`` or ``X_BEARER_TOKEN``."""

    token = os.environ.get("TWITTER_BEARER_TOKEN") or os.environ.get("X_BEARER_TOKEN")
    if not token:
        msg = "Set TWITTER_BEARER_TOKEN or X_BEARER_TOKEN for X API v2 access."
        raise ValueError(msg)
    return Client(bearer_token=token)


def collect_x_user_tweets(
    username: str,
    *,
    max_tweets: int = 100,
    bearer_token: str | None = None,
    client: Client | None = None,
) -> list[XTweet]:
    """Return recent posts from the given X username (handle, with or without ``@``).

    Args:
        username: Screen name / handle.
        max_tweets: Maximum number of posts to return (paginates in batches up to 100).
        bearer_token: OAuth 2.0 Bearer token. If omitted, ``client`` or env vars are used.
        client: Optional pre-built :class:`tweepy.Client` (e.g. for tests).

    Returns:
        Newest-first list of :class:`XTweet` instances.

    Raises:
        ValueError: Missing credentials, invalid ``max_tweets``, or unknown user.
        tweepy.TweepyException: On API errors (rate limits, auth, etc.).
    """
    if max_tweets < 1:
        raise ValueError("max_tweets must be at least 1")

    resolved = client or (Client(bearer_token=bearer_token) if bearer_token else create_x_client_from_env())
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
