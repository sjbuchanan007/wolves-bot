#!/usr/bin/env python3
"""Wolves Ay We — a wee social bot for X, Mastodon and Bluesky.

Posts a random line from tweets.txt a handful of times a day, at random-ish
hours, so it reads like a person rather than a clockwork machine. Posts to
every platform that has credentials configured (see platforms.py).

Scheduling (no database / no server keeping state):
the whole day's plan is derived deterministically from today's date. Every run
that day computes the SAME plan -- which hours to post at, and which tweet goes
out at each hour -- and only acts when the current hour is one of the slots.
Run this once an hour (see the GitHub Actions workflow) and you get a fresh,
random pattern of 6-12 posts every day with nothing to store between runs.

No repeats: each day's tweets are drawn from a shuffled copy of the list, so a
line never goes out twice in the same day, and we also make sure today's first
post isn't a repeat of yesterday's last.
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import platforms

# --- Tunables ---------------------------------------------------------------
# Local timezone the "waking hours" are measured in (Wolverhampton).
TIMEZONE = ZoneInfo("Europe/London")
# Don't post outside these hours (24h clock, inclusive start, exclusive end).
ACTIVE_START_HOUR = 8    # 08:00
ACTIVE_END_HOUR = 23     # up to 22:59
# Random number of posts per day, picked fresh each day.
MIN_POSTS_PER_DAY = 6
MAX_POSTS_PER_DAY = 12

TWEETS_FILE = Path(__file__).with_name("tweets.txt")


def load_tweets():
    """Read tweets.txt: one tweet per line, skipping blanks and # comments."""
    lines = []
    for raw in TWEETS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    if not lines:
        sys.exit(f"No tweets found in {TWEETS_FILE} -- add some lines first.")
    return lines


def _slots_for(day):
    """The hours we've decided to post at on a given date (deterministic)."""
    planner = random.Random(day.isoformat())
    active = list(range(ACTIVE_START_HOUR, ACTIVE_END_HOUR))
    count = min(planner.randint(MIN_POSTS_PER_DAY, MAX_POSTS_PER_DAY), len(active))
    return sorted(planner.sample(active, count))


def _raw_plan(day, tweets):
    """{hour: tweet} for a date, no repeats within the day. Deterministic.

    Uses a separate seed from the slot picker so the two concerns stay
    independent. If there are fewer tweets than slots we cycle (only possible
    with a very short list), which is the one case a same-day repeat can occur.
    """
    slots = _slots_for(day)
    shuffler = random.Random(day.isoformat() + "|tweets")
    pool = tweets[:]
    shuffler.shuffle(pool)
    chosen = [pool[i % len(pool)] for i in range(len(slots))]
    return dict(zip(slots, chosen))


def plan_for_day(day, tweets):
    """Today's {hour: tweet}, also avoiding a repeat across the day boundary."""
    plan = _raw_plan(day, tweets)
    if not plan:
        return plan
    yesterday = _raw_plan(day - timedelta(days=1), tweets)
    if yesterday:
        first_hour = min(plan)
        last_tweet_yesterday = yesterday[max(yesterday)]
        if plan[first_hour] == last_tweet_yesterday and len(plan) > 1:
            # Swap the first two slots' tweets so we don't echo yesterday.
            hours = sorted(plan)
            plan[hours[0]], plan[hours[1]] = plan[hours[1]], plan[hours[0]]
    return plan


def main():
    now = datetime.now(timezone.utc).astimezone(TIMEZONE)
    dry_run = os.environ.get("DRY_RUN") == "1"
    plan = plan_for_day(now.date(), load_tweets())

    summary = ", ".join(f"{h:02d}:00" for h in sorted(plan))
    print(f"{now:%Y-%m-%d %H:%M %Z} | today's plan: {len(plan)} posts at [{summary}]")

    text = plan.get(now.hour)
    if text is None:
        print(f"Hour {now.hour} isn't a posting slot today -- nothing to do.")
        return

    print(f"This is a posting slot. Selected: {text!r}")
    results = [backend(text, dry_run=dry_run) for backend in platforms.ALL]

    posted = errored = 0
    for platform, status, detail in results:
        print(f"  {platform:<9} {status:<8} {detail}")
        posted += status == "posted"
        errored += status == "error"

    if errored:
        sys.exit(f"{errored} platform(s) failed to post.")
    if posted == 0 and not dry_run:
        print("No platforms configured -- set credentials as secrets to go live.")


if __name__ == "__main__":
    main()
