from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from finance_kol_analyzer.x_tweets import (
    XTweet,
    _tweet_model_to_xtweet,
    collect_x_user_tweets,
    normalize_x_username,
)


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
