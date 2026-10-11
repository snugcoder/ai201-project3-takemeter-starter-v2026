"""
Timeboxed scraper: collect public r/AmItheAsshole posts into labels.csv.

- Columns: text, label, note  (label and note hold a single-space placeholder " ")
- text = title: "full post body"  (one cell, nothing is trimmed)
- Update posts (e.g. "UPDATE: ...") are skipped
- One file, unsplit. The notebook does the 70/15/15 split, so don't split here.
- Hard time limit so this stays a small side task, not a scraping project.

Usage:
    pip install requests pandas
    python scrape_aita.py

If Reddit returns 403/429 (common for unauthenticated scripts), stop and
collect by copy and paste instead. Don't fight it. Check Reddit's terms
and API rules if you use this for anything beyond coursework.
"""

import random
import re
import time

import pandas as pd
import requests

# ---- settings ---------------------------------------------------------------
SUBREDDIT = "AmItheAsshole"
TARGET_POSTS = 250          # collect a buffer above 200 for dedupe/cleanup
TIME_LIMIT_SECONDS = 15 * 60  # hard timebox
PAUSE_SECONDS = 2.5         # be polite to Reddit
MIN_BODY_CHARS = 200        # skip near-empty posts
OUTPUT_FILE = "labels.csv"
SEED = 42

# Mix of listings so you don't get 250 near-identical "top of all time" posts.
LISTINGS = [
    ("top", {"t": "year"}),
    ("hot", {}),
    ("top", {"t": "month"}),
    ("new", {}),
    ("top", {"t": "week"}),
]

HEADERS = {
    # Reddit blocks generic user agents. Put something descriptive here.
    "User-Agent": "class-project-aita-collector/0.1 (educational; contact: OverAssociate7324)"
}

# Mod/meta threads aren't real AITA posts.
SKIP_TITLE = re.compile(r"(open forum|monthly|meta|announcement|rules|megathread)", re.I)
REMOVED_BODIES = {"[removed]", "[deleted]", ""}

# Update posts: "update" as a word in the title, or a body that opens with it
# (e.g. "UPDATE:", "Update -", "[Update]", "Update to my last post").
UPDATE_TITLE = re.compile(r"\bupdate[sd]?\b", re.I)
UPDATE_BODY_START = re.compile(r"^\W*(update|edit\s*:?\s*update)\b", re.I)


def is_update(title: str, body: str) -> bool:
    return bool(UPDATE_TITLE.search(title) or UPDATE_BODY_START.match(body))


def keep(post: dict) -> bool:
    body = (post.get("selftext") or "").strip()
    title = (post.get("title") or "").strip()
    if is_update(title, body):
        return False
    if post.get("stickied") or post.get("is_self") is False:
        return False
    if body in REMOVED_BODIES or len(body) < MIN_BODY_CHARS:
        return False
    if post.get("removed_by_category"):
        return False
    if SKIP_TITLE.search(title):
        return False
    return True


def to_text(post: dict) -> str:
    # Title and whole post body (untrimmed) in one cell: title: "body"
    return f'{post["title"].strip()}: "{post["selftext"].strip()}"'


def fetch_page(sort: str, params: dict, after: str | None):
    url = f"https://www.reddit.com/r/{SUBREDDIT}/{sort}.json"
    q = {"limit": 100, "raw_json": 1, **params}
    if after:
        q["after"] = after
    resp = requests.get(url, headers=HEADERS, params=q, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} from Reddit for {sort} {params}")
    data = resp.json()["data"]
    return [c["data"] for c in data["children"]], data.get("after")


def main():
    start = time.time()
    seen_ids, seen_text, rows = set(), set(), []

    def out_of_time():
        return time.time() - start > TIME_LIMIT_SECONDS

    for sort, params in LISTINGS:
        after = None
        while len(rows) < TARGET_POSTS and not out_of_time():
            try:
                posts, after = fetch_page(sort, params, after)
            except Exception as e:
                print(f"Stopping this listing ({sort} {params}): {e}")
                break

            for p in posts:
                if p["id"] in seen_ids or not keep(p):
                    continue
                text = to_text(p)
                if text in seen_text:
                    continue
                seen_ids.add(p["id"])
                seen_text.add(text)
                rows.append(text)

            print(f"{sort} {params}: {len(rows)} posts so far "
                  f"({int(time.time() - start)}s elapsed)")
            if not after:
                break
            time.sleep(PAUSE_SECONDS)

        if len(rows) >= TARGET_POSTS or out_of_time():
            break

    if not rows:
        print("Collected nothing. Fall back to copy and paste.")
        return

    # Shuffle so sort orders are mixed. This is NOT a train/test split.
    random.Random(SEED).shuffle(rows)

    df = pd.DataFrame({"text": rows, "label": " ", "note": " "})
    df.to_csv(OUTPUT_FILE, index=False)  # pandas handles quotes/commas/newlines

    print(f"\nWrote {len(df)} posts to {OUTPUT_FILE}")
    if len(df) < 200:
        print("Under 200 rows. Add more by copy and paste before moving on.")
    print('Reminder: label and note are " " placeholders, and do not split this file.')


if __name__ == "__main__":
    main()