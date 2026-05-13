from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from finance_kol_analyzer.x_tweets import (
    XTweet,
    _tweet_model_to_xtweet,
    collect_x_user_tweets,
    load_twitter_config,
    normalize_x_username,
    parse_utc_date,
    resolve_twitter_config,
    resolve_twitter_config_path,
    utc_year_bounds,
)


class TestUtcYearBounds:
    def test_2025_window(self) -> None:
        start, end = utc_year_bounds(2025)
        assert start.isoformat() == "2025-01-01T00:00:00+00:00"
        assert end.isoformat() == "2026-01-01T00:00:00+00:00"
        assert start < end


class TestParseUtcDate:
    def test_parses_midnight_utc(self) -> None:
        assert parse_utc_date("2025-06-15").isoformat() == "2025-06-15T00:00:00+00:00"


class TestNormalizeXUsername:
    def test_strips_at(self) -> None:
        assert normalize_x_username("@elonmusk") == "elonmusk"

    def test_preserves_plain_handle(self) -> None:
        assert normalize_x_username("elonmusk") == "elonmusk"

    def test_strips_whitespace(self) -> None:
        assert normalize_x_username("  foo  ") == "foo"


class TestTweetModelToXTweet:
    def test_dict_metrics(self) -> None:
        tweet = MagicMock()
        tweet.id = "1"
        tweet.text = "hello"
        tweet.created_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        tweet.public_metrics = {"like_count": 10, "reply_count": 2}
        out = _tweet_model_to_xtweet(tweet)
        assert out == XTweet(
            id="1",
            text="hello",
            created_at=tweet.created_at,
            public_metrics={"like_count": 10, "reply_count": 2},
        )

    def test_object_metrics(self) -> None:
        tweet = MagicMock()
        tweet.id = "2"
        tweet.text = "x"
        tweet.created_at = None
        tweet.public_metrics = SimpleNamespace(retweet_count=1, like_count=3, reply_count=0)
        out = _tweet_model_to_xtweet(tweet)
        assert out.public_metrics == {"retweet_count": 1, "like_count": 3, "reply_count": 0}


def test_collect_x_user_tweets_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    user = MagicMock()
    user.id = "99"
    client.get_user.return_value = MagicMock(data=user)

    first_tweet = MagicMock()
    first_tweet.id = "a"
    first_tweet.text = "one"
    first_tweet.created_at = None
    first_tweet.public_metrics = {}
    second_tweet = MagicMock()
    second_tweet.id = "b"
    second_tweet.text = "two"
    second_tweet.created_at = None
    second_tweet.public_metrics = {}

    def get_users_tweets(*_args: object, **kwargs: object) -> MagicMock:
        token = kwargs.get("pagination_token")
        resp = MagicMock()
        if token is None:
            resp.data = [first_tweet]
            resp.meta = {"next_token": "n1"}
        else:
            resp.data = [second_tweet]
            resp.meta = {}
        return resp

    client.get_users_tweets.side_effect = get_users_tweets

    tweets = collect_x_user_tweets("someuser", max_tweets=150, client=client)

    assert [t.id for t in tweets] == ["a", "b"]
    assert client.get_users_tweets.call_count == 2
    first_call = client.get_users_tweets.call_args_list[0]
    assert first_call.kwargs.get("pagination_token") is None
    assert first_call.kwargs.get("max_results") == 100
    second_call = client.get_users_tweets.call_args_list[1]
    assert second_call.kwargs.get("pagination_token") == "n1"
    # 149 posts still requested; X allows up to 100 per call.
    assert second_call.kwargs.get("max_results") == 100


def test_collect_x_user_not_found() -> None:
    client = MagicMock()
    client.get_user.return_value = MagicMock(data=None)
    with pytest.raises(ValueError, match="not found"):
        collect_x_user_tweets("nope", client=client)


def test_collect_x_max_tweets_invalid() -> None:
    with pytest.raises(ValueError, match="max_tweets"):
        collect_x_user_tweets("x", max_tweets=0, client=MagicMock())


def test_collect_x_invalid_time_window() -> None:
    from datetime import datetime, timezone

    t0 = datetime(2025, 6, 1, tzinfo=timezone.utc)
    t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="start_time"):
        collect_x_user_tweets("x", max_tweets=10, client=MagicMock(), start_time=t0, end_time=t1)


def test_collect_x_passes_timeline_filters_to_api() -> None:
    from datetime import datetime, timezone

    client = MagicMock()
    user = MagicMock()
    user.id = "42"
    client.get_user.return_value = MagicMock(data=user)
    client.get_users_tweets.return_value = MagicMock(data=[], meta={})

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, tzinfo=timezone.utc)
    collect_x_user_tweets(
        "acct",
        max_tweets=5,
        client=client,
        start_time=start,
        end_time=end,
        exclude_retweets=True,
        exclude_replies=True,
        include_public_metrics=False,
    )

    call_kw = client.get_users_tweets.call_args.kwargs
    assert call_kw["start_time"] is start
    assert call_kw["end_time"] is end
    assert call_kw["exclude"] == ["retweets", "replies"]
    assert call_kw["tweet_fields"] == ["created_at"]


def test_load_twitter_config_secret_key_alias(tmp_path) -> None:
    p = tmp_path / "twitter_config.yaml"
    p.write_text(
        "consumer_key: ck\nsecret_key: cs\nbearer_token: bt\n",
        encoding="utf-8",
    )
    cfg = load_twitter_config(p)
    assert cfg.consumer_key == "ck"
    assert cfg.consumer_secret == "cs"
    assert cfg.bearer_token == "bt"


def test_load_twitter_config_nested_twitter_key(tmp_path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(
        "other: 1\ntwitter:\n  bearer_token: nested\n  consumer_key: k\n",
        encoding="utf-8",
    )
    cfg = load_twitter_config(p)
    assert cfg.bearer_token == "nested"
    assert cfg.consumer_key == "k"


def test_resolve_twitter_config_env_overrides_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "twitter_config.yaml"
    p.write_text("bearer_token: fromfile\n", encoding="utf-8")
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "fromenv")
    cfg = resolve_twitter_config(p)
    assert cfg.bearer_token == "fromenv"


def test_resolve_twitter_config_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TWITTER_CONFIG_PATH", raising=False)
    assert resolve_twitter_config_path(None) == Path("twitter_config.yaml")


def test_resolve_twitter_config_path_from_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "x.yaml"
    monkeypatch.setenv("TWITTER_CONFIG_PATH", str(p))
    assert resolve_twitter_config_path(None) == p
