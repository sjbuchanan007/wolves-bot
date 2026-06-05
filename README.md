# Wolves Ay We — social bot

A revival of the original Raspberry Pi cron bot. Posts a random bit of Wolves
banter a handful of times a day, at random-ish hours, running free on GitHub
Actions — no Pi, no server, no cron to babysit. Posts to **X (Twitter)**,
**Mastodon** and **Bluesky** — to whichever you've set up credentials for.

## How it works

- **`tweets.txt`** — the banter list, one tweet per line. Edit this freely;
  blank lines and `#` comments are ignored. No code knowledge needed.
- **`bot.py`** — picks a tweet and posts it; handles the scheduling.
- **`platforms.py`** — the X / Mastodon / Bluesky posting backends.
- **`.github/workflows/wolves-bot.yml`** — runs `bot.py` every hour.

### The scheduling trick

We want 6–12 posts a day at random times, but GitHub Actions only offers a
*fixed* hourly schedule and keeps no memory between runs. So instead of storing
a schedule, `bot.py` derives the whole day's plan from the date: it seeds the
random generator with today's date, picks a random count (6–12), random hours,
and which tweet goes out at each. Every hourly run that day computes the *same*
plan, so the result is a guaranteed 6–12 posts, randomly spaced, a fresh
pattern each day — with nothing to store.

### No repeats

Each day's tweets are drawn from a shuffled copy of the list, so the same line
never goes out twice in a day, and today's first post is never a repeat of
yesterday's last. (The only way to get a same-day repeat is to have fewer
active tweets than posts in a day — keep more than ~12 lines uncommented.)

### Posts to all configured platforms

Each platform posts only if its credentials are present (as GitHub secrets), so
you can switch them on one at a time. Add no secrets and nothing posts; add just
the X ones and only X posts; add all three and it posts everywhere. No code
changes needed either way.

## Setup

For **each** platform you want, get its credentials and add them as GitHub
secrets: **repo Settings → Secrets and variables → Actions → New repository
secret**.

### X (Twitter)

1. [X Developer Portal](https://developer.x.com/) → create a **Project** + **App**
   (the **Free** tier allows ~500 posts/month; 6–12/day stays well under).
2. App → **User authentication settings** → enable **OAuth 1.0a** with
   **Read and Write** permissions.
3. **Keys and tokens** → grab the four values and add them as secrets:
   `CONSUMER_KEY`, `CONSUMER_SECRET`, `ACCESS_TOKEN`, `ACCESS_TOKEN_SECRET`.
   (If you set Read/Write *after* creating the access token, regenerate it so it
   picks up write permission.)

### Mastodon

1. Sign in on your instance (e.g. `mastodon.social`) →
   **Preferences → Development → New application**.
2. Give it the **`write:statuses`** scope, create it, and copy **Your access
   token**.
3. Add secrets:
   - `MASTODON_API_BASE_URL` — your instance URL, e.g. `https://mastodon.social`
   - `MASTODON_ACCESS_TOKEN` — the access token

### Bluesky

1. In the Bluesky app: **Settings → Privacy and security → App passwords →
   Add App Password**. Copy it (looks like `xxxx-xxxx-xxxx-xxxx`).
2. Add secrets:
   - `BLUESKY_HANDLE` — your handle, e.g. `wolvesaywe.bsky.social`
   - `BLUESKY_APP_PASSWORD` — the app password (use this, **not** your login
     password)

### Test it

**Actions → wolves-bot → Run workflow**, tick **dry run** → it prints the day's
plan and what it *would* post to each configured platform, without posting.

## Running locally

```bash
pip install -r requirements.txt

# See today's plan + what it would post, no credentials needed, nothing sent:
DRY_RUN=1 python bot.py

# Actually post: export the secrets for whichever platforms you want, then:
python bot.py
