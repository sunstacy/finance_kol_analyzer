#!/usr/bin/env python3
"""Smoke-test X credentials from twitter_config.yaml (or env).

Makes one small API call (default: ``GET /2/users/by/username`` for ``X``).
Use this to separate **invalid tokens** (often 401) from **billing** (402).

Usage::

    python3 src/verify_twitter_credentials.py --config twitter_config.yaml
    python3 src/verify_twitter_credentials.py --config twitter_config.yaml --username SomeHandle
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tweepy

from finance_kol_analyzer.x_tweets import (
    create_tweepy_client_from_config,
    resolve_twitter_config,
)


def _mask(value: str | None, *, head: int = 4, tail: int = 4) -> str:
    if value is None or not str(value).strip():
        return "(missing)"
    s = str(value).strip()
    if len(s) <= head + tail + 1:
        return "***"
    return f"{s[:head]}…{s[-tail:]}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify X API credentials and print a minimal authenticated request result.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to twitter_config.yaml (default: TWITTER_CONFIG_PATH or ./twitter_config.yaml).",
    )
    parser.add_argument(
        "--username",
        default="X",
        help="Public handle to resolve with get_user (default: X).",
    )
    args = parser.parse_args()

    try:
        cfg = resolve_twitter_config(args.config)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    print("Resolved credentials (masked):")
    print(f"  consumer_key:          {_mask(cfg.consumer_key)}")
    print(f"  consumer_key_secret:   {_mask(cfg.consumer_secret)}  (stored as consumer_secret for tweepy)")
    print(f"  access_token:          {_mask(cfg.access_token)}")
    print(f"  access_token_secret:   {_mask(cfg.access_token_secret)}")
    print(f"  bearer_token:          {_mask(cfg.bearer_token)}")
    if cfg.bearer_token:
        print("\nAuth mode: **bearer_token** (used for Client).")
    elif (
        cfg.consumer_key
        and cfg.consumer_secret
        and cfg.access_token
        and cfg.access_token_secret
    ):
        print("\nAuth mode: **OAuth 1.0a user** (consumer + access tokens).")
    else:
        print(
            "\nERROR: Incomplete configuration. Add bearer_token, or all OAuth1 fields.",
            file=sys.stderr,
        )
        return 2

    try:
        client = create_tweepy_client_from_config(cfg)
    except ValueError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2

    handle = args.username.lstrip("@")
    print(f"\nCalling get_user(username={handle!r}) …")
    try:
        resp = client.get_user(username=handle)
    except tweepy.TweepyException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        body = getattr(getattr(exc, "response", None), "text", "") or ""
        snippet = body.replace("\n", " ")[:400]
        print(f"\nTweepyException: {exc}")
        if status is not None:
            print(f"HTTP status: {status}")
            if status == 401:
                print(
                    "\nHint: 401 usually means wrong or revoked keys/tokens, or wrong app/project."
                )
            elif status == 402:
                print(
                    "\nHint: 402 means the request reached X but this enrolled account has no "
                    "billable credits for this product. Keys can still be valid—check Billing on the "
                    "same developer project that owns these keys."
                )
            elif status == 403:
                print(
                    "\nHint: 403 often means the app lacks access to this endpoint or the user is protected."
                )
        if snippet:
            print(f"Response body (truncated): {snippet}")
        return 1

    if resp.data is None:
        print("OK (HTTP success) but no user returned (unknown handle or no permission).")
        return 0

    u = resp.data
    print("OK — credentials accepted for this call.")
    print(f"  user id:   {u.id}")
    print(f"  username:  {u.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
