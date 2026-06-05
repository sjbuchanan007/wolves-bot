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
import re

# A Bluesky handle always contains a dot (e.g. wolvesfc.bsky.social). This lets
# us turn those into real mentions while leaving legacy X-style @names (no dot,
# e.g. @officialwolves) as plain text.
_BLUESKY_HANDLE_RE = re.compile(r"@([a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")


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


def _bluesky_richtext(client, text):
    """Turn @handle.tld mentions into real Bluesky mentions (facets).

    Never raises: if a handle can't be resolved we fall back to plain text for
    that token, and we print why, so a failure is visible in the logs rather
    than silently posting plain text.
    """
    try:
        from atproto import client_utils

        builder = client_utils.TextBuilder()
        pos = 0
        mentioned = False
        for match in _BLUESKY_HANDLE_RE.finditer(text):
            if match.start() > pos:
                builder.text(text[pos:match.start()])
            try:
                did = client.resolve_handle(match.group(1)).did
                builder.mention(match.group(0), did)
                mentioned = True
            except Exception as err:
                print(f"  (bluesky: couldn't resolve {match.group(0)}: {err})")
                builder.text(match.group(0))
            pos = match.end()
        if pos < len(text):
            builder.text(text[pos:])
        return builder if mentioned else text
    except Exception as err:
        print(f"  (bluesky: rich-text build failed, posting plain text: {err})")
        return text


def post_to_bluesky(text, dry_run=False):
    if not _have("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"):
        return ("Bluesky", "skipped", "no credentials set")
    if dry_run:
        return ("Bluesky", "dry-run", text)
    from atproto import Client

    client = Client()
    try:
        client.login(os.environ["BLUESKY_HANDLE"], os.environ["BLUESKY_APP_PASSWORD"])
        client.send_post(_bluesky_richtext(client, text))
        return ("Bluesky", "posted", text)
    except Exception as err:
        return ("Bluesky", "error", str(err))
