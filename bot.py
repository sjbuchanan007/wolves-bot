#!/usr/bin/env python3
"""Wolves Ay We — a wee social bot for X, Mastodon and Bluesky.

Posts a random line from tweets.txt a handful of times a day, at random-ish
hours, so it reads like a person rather than a clockwork machine. Posts to
every platform that has credentials configured (see platforms.py).

Scheduling (no server, tolerant of GitHub's flaky cron):
the whole day's plan is derived deterministically from today's date -- which
hours to post at, and which tweet goes out at each. The workflow runs often;
each run posts the earliest slot that's due (its hour has passed) but not yet
done, recording it in state.json. So if GitHub drops a run, a later one catches
the slot up, and nothing is ever posted twice.

No repeats: each day's tweets are drawn from a shuffled copy of the list, so a
line never goes out twice in the same day, and today's first post is never a
repeat of yesterday's last.
"""

import json
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
# Records which of today's slots have already been posted, so the bot can run
# often, catch up slots that GitHub's flaky cron missed, and never repeat one.
STATE_FILE = Path(__file__).with_name("state.json")


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


def load_state(today):
    """Today's posting state: {"date": "...", "posted": [hours]}.

    Resets automatically when the stored date isn't today.
    """
    try:
        data = json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    if data.get("date") != today.isoformat():
        return {"date": today.isoformat(), "posted": []}
    return data


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def broadcast(text, dry_run):
    """Send to every backend; return (posted_count, errored_count)."""
    posted = errored = 0
    for backend in platforms.ALL:
        platform, status, detail = backend(text, dry_run=dry_run)
        print(f"  {platform:<9} {status:<8} {detail}")
        posted += status == "posted"
        errored += status == "error"
    return posted, errored


def main():
    now = datetime.now(timezone.utc).astimezone(TIMEZONE)
    dry_run = os.environ.get("DRY_RUN") == "1"
    force = os.environ.get("FORCE_POST") == "1"
    tweets = load_tweets()
    plan = plan_for_day(now.date(), tweets)

    summary = ", ".join(f"{h:02d}:00" for h in sorted(plan))
    print(f"{now:%Y-%m-%d %H:%M %Z} | today's plan: {len(plan)} posts at [{summary}]")

    # FORCE_POST: one-off test post, ignores schedule and state entirely.
    if force:
        text = random.SystemRandom().choice(tweets)
        print(f"FORCE_POST set -- one-off test, ignoring schedule. Selected: {text!r}")
        _, errored = broadcast(text, dry_run)
        if errored:
            sys.exit(f"{errored} platform(s) failed to post.")
        return

    # Catch-up: post the earliest slot that's due (its hour has passed) but not
    # yet done. One per run, so several missed slots clear gradually, not in a
    # burst. This tolerates GitHub dropping runs -- any later run catches up.
    state = load_state(now.date())
    posted_slots = set(state["posted"])
    due = [h for h in sorted(plan) if h <= now.hour and h not in posted_slots]

    if not due:
        done = sorted(posted_slots)
        print(f"Nothing due (hour {now.hour}; already posted today: {done}).")
        return

    slot = due[0]
    text = plan[slot]
    if len(due) > 1:
        print(f"{len(due)} slots due {due}; catching up the earliest first.")
    print(f"Posting slot {slot:02d}:00 -> {text!r}")

    posted, errored = broadcast(text, dry_run)

    if posted and not dry_run:
        posted_slots.add(slot)
        state["posted"] = sorted(posted_slots)
        save_state(state)
        print(f"Recorded slot {slot:02d}:00 as posted.")
    if errored:
        # Don't record the slot -- a later run retries it.
        sys.exit(f"{errored} platform(s) failed to post.")
    if posted == 0 and not dry_run:
        print("No platforms configured -- set credentials as secrets to go live.")


if __name__ == "__main__":
    main()
