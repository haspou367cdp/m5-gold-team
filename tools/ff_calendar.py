#!/usr/bin/env python3
"""ff_calendar.py - build data/news_windows.json from the free ForexFactory weekly JSON feed (USD events).

Used by the GitHub Actions bot (bot/bot.py), where the M5-News bot is not available.
Tiers come from news_windows.classify_tier (label prefixed with "US "), buffers from
news_windows.default_buffers; DaryaGold floors are applied later by the usual effective_doc.
Conservative extras: any USD High-impact event the classifier calls C is raised to B (no-entry block);
"Federal Funds Rate" / FOMC statement / presser = A with fomc=true.
Existing windows added by a human/M5-News (added_by != 'ForexFactory') are kept.
usage: python3 ff_calendar.py [--out PATH] [--feed-json FILE]   exit 0 ok | 4 feed unavailable
Signal-only research tool. Not financial advice."""
import argparse, json, sys, urllib.request
from datetime import datetime, timedelta
sys.path.insert(0, "/workspace/m5-gold-team/tools")
import news_windows as nw

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def fetch(timeout=15):
    req = urllib.request.Request(FEED, headers={"User-Agent": "Mozilla/5.0 (m5-gold-team bot)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def classify(title, impact):
    t = title.lower()
    if "federal funds rate" in t or "fomc statement" in t or "fomc press" in t:
        return "A", True
    tier, fomc = nw.classify_tier("US " + title)
    if impact == "High" and tier == "C":
        tier = "B"
    return tier, fomc

def build(feed):
    wins = []
    for ev in feed:
        if ev.get("country") != "USD":
            continue
        try:
            t = datetime.fromisoformat(ev["date"]).astimezone(nw.TEH).replace(tzinfo=None)
        except Exception:
            continue
        title = ev.get("title") or "?"
        tier, fomc = classify(title, ev.get("impact"))
        if tier == "C" and ev.get("impact") != "Medium":
            continue  # low-impact non-Fed items are not windows
        before, after, tier, fomc = nw.default_buffers("US " + title, tier=tier, fomc=fomc)
        wins.append({"start": (t - timedelta(minutes=before)).strftime(nw.FMT),
                     "end": (t + timedelta(minutes=after)).strftime(nw.FMT),
                     "label": f"US {title} ({ev['impact']})", "tier": tier, "fomc": bool(fomc),
                     "added_by": "ForexFactory", "event_time_tehran": t.strftime(nw.FMT)})
    return wins

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=nw.NEWS_JSON)
    ap.add_argument("--feed-json")
    a = ap.parse_args()
    try:
        feed = json.load(open(a.feed_json)) if a.feed_json else fetch()
    except Exception as e:
        print(f"feed unavailable: {e}", file=sys.stderr); sys.exit(4)
    old = nw.load_json(a.out, None) or {}
    keep = [w for w in old.get("windows", []) if w.get("added_by") != "ForexFactory"]
    d = {"windows": keep + build(feed), "news_bias": old.get("news_bias"),
         "source": "ForexFactory weekly feed (USD: High, Medium, and any A/B such as Fed speakers)",
         "fetched_at_tehran": datetime.now(nw.TEH).strftime("%Y-%m-%d %H:%M")}
    nw.NEWS_JSON = a.out
    nw.save(d, source=d["source"])
    print(f"ok {len(d['windows'])} windows -> {a.out}")

if __name__ == "__main__":
    main()
