#!/usr/bin/env python3
"""news_windows.py - machine-readable no-trade windows + M5-News bias + A/B/C tiers.

File: /workspace/m5-gold-team/data/news_windows.json   (all times Asia/Tehran, ISO 'YYYY-MM-DDTHH:MM')
{ "updated_at_tehran": ..., "source": ..., "news_bias": {...},
  "windows": [ {"start": "...", "end": "...", "label": "...", "tier": "A"|"B"|"C", "fomc": false, "added_by": "..."} ] }

Tiers (classified from the label; can be overridden with --tier):
  A  FOMC, CPI, NFP, Core PCE / PCE — hard block
  B  PPI, ISM, Retail Sales, GDP — caution + spread check (not an automatic block)
  C  everything else (speeches, claims, …) — monitor only, not an automatic block

Default buffers for the `event` command (minutes before / after the release):
  A        5 / 15
  A FOMC  15 / 45   (statement + press conference runs longer)
  B        5 / 15
  C        5 / 15   (stored for the calendar only; action is still monitor)

Existing windows keep the start/end that M5-News (or a human) already stored; only the tier/action is applied.

Commands
  seed  [--md /workspace/team/m5-news/latest.md]   import windows + htf_gold_bias from M5-News latest.md (merges, no dupes)
  add   --date 2026-11-13 --start 16:45 --end 17:15 --label "US PPI" [--by M5-News] [--tier A|B|C]
  event --date 2026-11-13 --time 17:00 --label "US PPI" [--before N --after N] [--tier A|B|C]
  bias  --bias bearish|bullish|neutral --why "..." [--invalidation "..."]
  list  [--date 2026-11-12]                         print windows (merged view, with tier)
  now   [--at "2026-11-12 17:05"] [--lookahead 30]  is a window active / starting soon? exit 1 only if a hard BLOCK is active
  prune [--days 3]                                  drop windows that ended more than N days ago

This module is stdlib-only (no pandas) so `bias` / `now` cannot stall on a heavy import.
Signal-only research tool. Not financial advice."""
import argparse, json, os, re, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TEH = ZoneInfo("Asia/Tehran")
NEWS_JSON = "/workspace/m5-gold-team/data/news_windows.json"
FMT = "%Y-%m-%dT%H:%M"
_TIER_RANK = {"A": 3, "B": 2, "C": 1}

def load_json(p, default=None):
    try:
        with open(p) as f: return json.load(f)
    except FileNotFoundError:
        return default

def save_json(p, obj):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, p)

def load():
    d = load_json(NEWS_JSON, None) or {}
    d.setdefault("windows", []); d.setdefault("news_bias", None); d.setdefault("source", None)
    return d

def save(d, source=None):
    d["windows"] = sorted(d["windows"], key=lambda w: w["start"])
    d["updated_at_tehran"] = datetime.now(TEH).strftime("%Y-%m-%d %H:%M")
    if source: d["source"] = source
    save_json(NEWS_JSON, d)

def mk(date, start, end):
    s = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M")
    e = datetime.strptime(f"{date} {end}", "%Y-%m-%d %H:%M")
    if e <= s: e += timedelta(days=1)
    return s, e

# ---------- tiers ----------
def classify_tier(label):
    """Return (tier, is_fomc) from a free-text event label. Never guesses beyond the keyword list."""
    s = (label or "").lower()
    # FOMC / rate decision first (longer buffer). A lone "Powell speaks" is C, not FOMC.
    if re.search(r"\bfomc\b", s) or re.search(r"\b(fed|fomc)\s+(rate|interest)\s+decision\b", s) \
            or "interest rate decision" in s or "fomc press" in s or "fomc statement" in s \
            or "fomc monetary" in s or "rate decision" in s:
        return "A", True
    if re.search(r"\bcpi\b", s) or "consumer price" in s:
        return "A", False
    if re.search(r"\bnfp\b", s) or re.search(r"non[-\s]?farm", s) or re.search(r"\bpayrolls\b", s):
        return "A", False
    if re.search(r"\bpce\b", s) or "personal consumption" in s:
        return "A", False
    if re.search(r"\bppi\b", s) or "producer price" in s:
        return "B", False
    if re.search(r"\bism\b", s):
        return "B", False
    if "retail sales" in s:
        return "B", False
    if re.search(r"\bgdp\b", s):
        return "B", False
    return "C", False

def action_for(tier, fomc=False):
    if tier == "A":
        return "block"
    if tier == "B":
        return "caution"
    if tier == "C":
        return "monitor"
    return None

def default_buffers(label, tier=None, fomc=None):
    """Minutes (before, after) for the `event` command, plus resolved tier/fomc."""
    t, is_fomc = classify_tier(label)
    if tier in ("A", "B", "C"):
        t = tier
        if fomc is None and t != "A":
            is_fomc = False
    if fomc is True:
        is_fomc = True
        t = "A"
    if is_fomc:
        return 15, 45, t, True
    return 5, 15, t, False

def annotate_window(w):
    """Fill tier/fomc/action on a window dict (does not change start/end)."""
    if w.get("tier") in ("A", "B", "C"):
        tier = w["tier"]
        fomc = bool(w.get("fomc")) if "fomc" in w else (classify_tier(w.get("label") or "")[1] if tier == "A" else False)
    else:
        tier, fomc = classify_tier(w.get("label") or "")
    w = dict(w)
    w["tier"] = tier
    w["fomc"] = bool(fomc)
    w["action"] = action_for(tier, fomc)
    return w

def add(d, s, e, label, by, tier=None, fomc=None):
    t, is_fomc = classify_tier(label)
    if tier in ("A", "B", "C"):
        t = tier
        if fomc is None and t != "A":
            is_fomc = False
    if fomc is True:
        is_fomc = True
        t = "A"
    w = {"start": s.strftime(FMT), "end": e.strftime(FMT), "label": label.strip(),
         "tier": t, "fomc": bool(is_fomc), "added_by": by}
    if not any(x["start"] == w["start"] and x["end"] == w["end"] for x in d["windows"]):
        d["windows"].append(w); return True
    # already present: still backfill tier if the stored row is missing it
    for x in d["windows"]:
        if x["start"] == w["start"] and x["end"] == w["end"]:
            if x.get("tier") not in ("A", "B", "C"):
                x["tier"], x["fomc"] = t, bool(is_fomc)
            break
    return False

def windows(d):
    out = []
    for w in d["windows"]:
        ww = annotate_window(w)
        out.append((datetime.strptime(ww["start"], FMT).replace(tzinfo=TEH),
                    datetime.strptime(ww["end"], FMT).replace(tzinfo=TEH), ww))
    return out

def _merge_meta(a, b):
    labels = list(a["labels"])
    for lab in b["labels"]:
        if lab not in labels:
            labels.append(lab)
    tier = a["tier"] if _TIER_RANK.get(a["tier"], 0) >= _TIER_RANK.get(b["tier"], 0) else b["tier"]
    fomc = bool(a.get("fomc") or b.get("fomc"))
    if fomc:
        tier = "A"
    return {"labels": labels, "tier": tier, "fomc": fomc, "action": action_for(tier, fomc)}

def merged(d):
    """Overlapping/adjacent windows merged; labels joined; highest-severity tier kept."""
    out = []
    for s, e, w in sorted(windows(d), key=lambda x: x[0]):
        meta = {"labels": [w["label"]], "tier": w["tier"], "fomc": bool(w.get("fomc")),
                "action": w.get("action") or action_for(w["tier"], w.get("fomc"))}
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
            out[-1][2] = _merge_meta(out[-1][2], meta)
        else:
            out.append([s, e, meta])
    return out

def status(d, at=None, lookahead=30):
    """Current news-window status. `inside` is true if *any* stored window covers `at`.
    `action` is block/caution/monitor from the highest-severity overlapping window.
    `soon` / `soon_action` describe the next window; hard-block lookahead is 5 min (15 for FOMC),
    not the generic `lookahead` (kept for listing 'upcoming'). exit 1 from `now` only when action==block."""
    at = at or datetime.now(TEH)
    for s, e, meta in merged(d):
        if s <= at < e:
            return {"inside": True, "start": s.strftime("%H:%M"), "end": e.strftime("%H:%M"),
                    "labels": meta["labels"], "tier": meta["tier"], "fomc": meta["fomc"],
                    "action": meta["action"],
                    "minutes_left": round((e - at).total_seconds() / 60),
                    "soon": False, "soon_action": None}
    nxt = [(s, e, m) for s, e, m in merged(d) if s > at]
    if nxt:
        s, e, m = nxt[0]
        mins = round((s - at).total_seconds() / 60)
        pre = 15 if m.get("fomc") else (5 if m["tier"] == "A" else (5 if m["tier"] == "B" else None))
        soon_action = None
        if pre is not None and mins <= pre:
            soon_action = m["action"]
        return {"inside": False, "next_start": s.strftime("%Y-%m-%d %H:%M"), "next_end": e.strftime("%H:%M"),
                "next_labels": m["labels"], "minutes_to_next": mins,
                "tier": m["tier"], "fomc": m["fomc"], "action": None,
                "next_tier": m["tier"], "next_action": m["action"],
                "soon": bool(soon_action) or mins <= lookahead,
                "soon_block": soon_action == "block",
                "soon_action": soon_action}
    return {"inside": False, "next_start": None, "soon": False, "action": None, "tier": None,
            "soon_action": None, "soon_block": False, "fomc": False}

def seed(d, md):
    txt = open(md, encoding="utf-8").read()
    n, date = 0, None
    for line in txt.splitlines():
        m = re.match(r"\s*(?:today|tomorrow)_(\d{4}-\d{2}-\d{2}):", line)
        if m: date = m.group(1); continue
        m = re.match(r"\s*-\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*(\((\w+)\))?\s*\|\s*(.+)", line)
        if m and date:
            s, e = mk(date, m.group(1), m.group(2))
            if m.group(4):   # e.g. "(Fri)" -> event is after midnight, i.e. next calendar day
                s += timedelta(days=1); e += timedelta(days=1)
            n += add(d, s, e, m.group(5), "M5-News latest.md")
    b = re.search(r"^htf_gold_bias:\s*(\w+)", txt, re.M); why = re.search(r"^htf_why:\s*(.+)$", txt, re.M)
    dt = re.search(r"^date:\s*(\S+)", txt, re.M)
    if b:
        d["news_bias"] = {"bias": b.group(1).lower(), "why": why.group(1) if why else "", "date": dt.group(1) if dt else None,
                          "invalidation": d.get("news_bias", {}).get("invalidation") if d.get("news_bias") else None,
                          "source": md}
    return n

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("seed"); p.add_argument("--md", default="/workspace/team/m5-news/latest.md")
    p = sp.add_parser("add"); p.add_argument("--date", required=True); p.add_argument("--start", required=True)
    p.add_argument("--end", required=True); p.add_argument("--label", required=True); p.add_argument("--by", default="M5-News")
    p.add_argument("--tier", choices=["A", "B", "C"], default=None)
    p = sp.add_parser("event"); p.add_argument("--date", required=True); p.add_argument("--time", required=True)
    p.add_argument("--label", required=True); p.add_argument("--before", type=int, default=None)
    p.add_argument("--after", type=int, default=None); p.add_argument("--by", default="M5-News")
    p.add_argument("--tier", choices=["A", "B", "C"], default=None)
    p = sp.add_parser("bias"); p.add_argument("--bias", required=True, choices=["bullish", "bearish", "neutral"])
    p.add_argument("--why", default=""); p.add_argument("--invalidation", default=None)
    p = sp.add_parser("list"); p.add_argument("--date")
    p = sp.add_parser("now"); p.add_argument("--at"); p.add_argument("--lookahead", type=int, default=30)
    p = sp.add_parser("prune"); p.add_argument("--days", type=int, default=3)
    a = ap.parse_args(); d = load()
    if a.cmd == "seed":
        n = seed(d, a.md); save(d, a.md); print(f"seeded {n} new windows from {a.md}; bias={d['news_bias'] and d['news_bias']['bias']}", flush=True)
    elif a.cmd == "add":
        s, e = mk(a.date, a.start, a.end)
        print("added" if add(d, s, e, a.label, a.by, tier=a.tier) else "already present", flush=True); save(d)
    elif a.cmd == "event":
        before, after, tier, fomc = default_buffers(a.label, tier=a.tier)
        if a.before is not None: before = a.before
        if a.after is not None: after = a.after
        t = datetime.strptime(f"{a.date} {a.time}", "%Y-%m-%d %H:%M")
        print("added" if add(d, t - timedelta(minutes=before), t + timedelta(minutes=after),
                             a.label, a.by, tier=a.tier or tier, fomc=fomc) else "already present", flush=True)
        save(d)
    elif a.cmd == "bias":
        d["news_bias"] = {"bias": a.bias, "why": a.why, "invalidation": a.invalidation,
                          "date": datetime.now(TEH).strftime("%Y-%m-%d"), "source": "news_windows.py bias"}
        save(d); print("bias set:", a.bias, flush=True)
    elif a.cmd == "list":
        for s, e, meta in merged(d):
            if a.date and s.strftime("%Y-%m-%d") != a.date and e.strftime("%Y-%m-%d") != a.date: continue
            tag = f"tier {meta['tier']}" + (" FOMC" if meta.get("fomc") else "") + f" / {meta['action']}"
            print(f"{s:%Y-%m-%d %H:%M} -> {e:%H:%M} Tehran | {tag} | {' + '.join(meta['labels'])}", flush=True)
        print("news_bias:", d.get("news_bias"), flush=True)
    elif a.cmd == "now":
        at = datetime.strptime(a.at, "%Y-%m-%d %H:%M").replace(tzinfo=TEH) if a.at else None
        st = status(d, at, a.lookahead); print(st, flush=True)
        sys.exit(1 if (st.get("action") == "block" or st.get("soon_block")) else 0)
    elif a.cmd == "prune":
        cut = datetime.now(TEH) - timedelta(days=a.days)
        before = len(d["windows"]); d["windows"] = [w for s, e, w in windows(d) if e >= cut]
        save(d); print(f"pruned {before - len(d['windows'])}", flush=True)

if __name__ == "__main__":
    main()
