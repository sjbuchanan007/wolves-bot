"""Posting backends for X, Mastodon and Bluesky.

Each ``post_to_*`` function is a no-op that returns ("<name>", "skipped", ...)
unless its credentials are present in the environment. That means you can turn
platforms on one at a time -- just add that platform's secrets and it starts
posting; no code changes needed. Heavy libraries are imported lazily inside
each function so a platform you're not using never has to be installed or
configured.

Every function returns a (platform, status, detail) tuple where status is one
of: "posted", "skipped", "dry-run", "error".
"""

import os


def _have(*names):
    """True only if every named environment variable is set and non-empty."""
    return all(os.environ.get(name) for name in names)


def post_to_x(text, dry_run=False):
    keys = ("CONSUMER_KEY", "CONSUMER_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET")
    if not _have(*keys):
        return ("X", "skipped", "no credentials set")
    if dry_run:
        return ("X", "dry-run", text)
    import tweepy

    client = tweepy.Client(
        consumer_key=os.environ["CONSUMER_KEY"],
        consumer_secret=os.environ["CONSUMER_SECRET"],
        access_token=os.environ["ACCESS_TOKEN"],
        access_token_secret=os.environ["ACCESS_TOKEN_SECRET"],
    )
    try:
        client.create_tweet(text=text)
        return ("X", "posted", text)
    except tweepy.TweepyException as err:
        return ("X", "error", str(err))


def post_to_mastodon(text, dry_run=False):
    if not _have("MASTODON_API_BASE_URL", "MASTODON_ACCESS_TOKEN"):
        return ("Mastodon", "skipped", "no credentials set")
    if dry_run:
        return ("Mastodon", "dry-run", text)
    from mastodon import Mastodon

    client = Mastodon(
        access_token=os.environ["MASTODON_ACCESS_TOKEN"],
        api_base_url=os.environ["MASTODON_API_BASE_URL"],
    )
    try:
        client.status_post(text)
        return ("Mastodon", "posted", text)
    except Exception as err:  # Mastodon.py raises a family of MastodonError types
        return ("Mastodon", "error", str(err))


def post_to_bluesky(text, dry_run=False):
    if not _have("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"):
        return ("Bluesky", "skipped", "no credentials set")
    if dry_run:
        return ("Bluesky", "dry-run", text)
    from atproto import Client

    client = Client()
    try:
        client.login(os.environ["BLUESKY_HANDLE"], os.environ["BLUESKY_APP_PASSWORD"])
        client.send_post(text)
        return ("Bluesky", "posted", text)
    except Exception as err:
        return ("Bluesky", "error", str(err))


# All backends, tried in order. Add a new platform by appending its function.
ALL = (post_to_x, post_to_mastodon, post_to_bluesky)
