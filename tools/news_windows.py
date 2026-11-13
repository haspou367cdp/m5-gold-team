#!/usr/bin/env python3
"""news_windows.py - machine-readable no-trade windows + M5-News bias + A/B/C tiers.

File: /workspace/m5-gold-team/data/news_windows.json   (all times Asia/Tehran, ISO 'YYYY-MM-DDTHH:MM')
{ "updated_at_tehran": ..., "source": ..., "news_bias": {...},
  "windows": [ {"start": "...", "end": "...", "label": "...", "tier": "A"|"B"|"C", "fomc": false, "added_by": "..."} ] }

Tiers (auto-classified from the label for *new* `event`/`add` rows only).
Stored `tier` and `fomc` on an existing window are authoritative and are never overwritten.

  A  US CPI, US NFP, US Core PCE / PCE; FOMC *decision/statement/presser* (fomc=true);
     Fed Chair speeches (fomc=false). Hard block.
  B  FOMC *minutes* (fomc=false — not a hard block); PPI, ISM, Retail Sales, GDP;
     named non-US CPI; other Fed speeches (governors, vice chairs, presidents). Caution + spread check.
  C  monitor only (claims and other items that are not in the lists above)

Default buffers for the `event` command (minutes before / after `--time`).
These match data/news_windows.json `window_policy` and do not rewrite stored start/end:
  A data (US CPI / NFP / PCE)     15 / 15
  A FOMC (`--time` = statement)   30 / 90  (30 before the statement, 60 after a presser that starts ~30 min later)
  A FOMC (`--time` = presser)     30 / 60  (if the label is a press conference only)
  A Fed Chair speech              15 / 30
  B data / FOMC minutes           15 / 15
  B Fed speech / Q&A              15 / 30
  C                               5 / 15   (calendar only; action is still monitor)

Existing windows keep the start, end, tier and fomc that M5-News (or a human) already stored.

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
_US = r"(?:us|u\.s\.|u\.s|usa|united states)"
_NON_US = (r"(?:uk|u\.k\.|britain|british|ons|eurozone|euro[- ]area|euro area|"
           r"germany|france|china|japan|canada|australia|india|ecb)")
_SPEECH = (r"(?:speaks?|speech|remarks|discussion|conversation|fireside|"
           r"testimony|testifies|luncheon|moderated|q\s*&\s*a)")
_FED_BANK = (r"(?:fed|federal reserve|fomc|"
             r"(?:new york|ny|chicago|cleveland|san francisco|sf|atlanta|"
             r"richmond|st\.?\s*louis|minneapolis|dallas|boston|"
             r"philadelphia|kansas city|philly)\s+fed)")

def _has_us(s):
    return bool(re.search(rf"\b{_US}\b", s))

def _has_non_us(s):
    return bool(re.search(rf"\b{_NON_US}\b", s))

def classify_tier(label):
    """Return (tier, is_fomc) from a free-text event label. Used only when a window has no stored tier/fomc.
    Stored fields always win. is_fomc is True only for the FOMC decision/statement/presser, never minutes."""
    s = (label or "").lower()
    # 1) Minutes first: any "FOMC minutes" label is B, fomc=false — not a hard block.
    if re.search(r"\bfomc\s+minutes\b", s) or (re.search(r"\bfomc\b", s) and "minutes" in s):
        return "B", False
    # 2) FOMC decision / statement / press conference (not a lone "Fed official speaks").
    if re.search(r"\bfomc\b", s) and re.search(
            r"(rate decision|interest rate|statement|press(?:er| conference)|monetary policy decision|fomc meeting)", s):
        return "A", True
    if re.search(r"\b(fed|fomc)\s+(rate|interest)\s+decision\b", s) or "interest rate decision" in s             or "fomc press" in s or "fomc statement" in s or "fomc monetary" in s:
        return "A", True
    # Bare "FOMC" without minutes/decision: do not auto-upgrade. (Minutes already handled.)
    # 3) CPI: require a US country marker. Named non-US CPI is B, not A. Bare "CPI" is not auto-A.
    if re.search(r"\bcpi\b", s) or "consumer price" in s:
        if _has_us(s) and not _has_non_us(s):
            return "A", False
        if _has_non_us(s):
            return "B", False
        return "C", False
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
    # 4) Fed Chair speech → A, but fomc=false (not the FOMC meeting block).
    if re.search(rf"\b{_FED_BANK}\s+chair(?:man|woman)?\b", s) or re.search(
            r"\bchair(?:man|woman)?\s+(powell|warsh|jerome|kevin)\b", s):
        return "A", False
    # 5) Other Fed speeches default to B (governors, vice chairs, presidents).
    if re.search(rf"\b{_FED_BANK}\b", s) and re.search(rf"\b{_SPEECH}\b", s):
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
    """Minutes (before, after) for a *new* `event` row, plus resolved tier/fomc.
    Does not change windows already stored in news_windows.json."""
    t, is_fomc = classify_tier(label)
    if tier in ("A", "B", "C"):
        t = tier
        if fomc is None and t != "A":
            is_fomc = False
    if fomc is True:
        is_fomc = True
        t = "A"
    s = (label or "").lower()
    if is_fomc:
        # --time is the statement by default: 30 before statement, 60 after presser start (~statement+30).
        if re.search(r"press(?:er| conference)", s) and not re.search(r"statement|rate decision|interest rate", s):
            return 30, 60, t, True
        return 30, 90, t, True
    if t == "A" and re.search(r"\bchair", s):
        return 15, 30, t, False
    if t == "A":
        return 15, 15, t, False
    if t == "B" and re.search(rf"\b{_SPEECH}\b", s):
        return 15, 30, t, False
    if t == "B":
        return 15, 15, t, False
    return 5, 15, t, False

def annotate_window(w):
    """Return a copy with action filled in. Never mutates the stored row.
    If `tier` and/or `fomc` are already set on the window, those values win — the classifier is not applied."""
    w = dict(w)
    has_tier = w.get("tier") in ("A", "B", "C")
    has_fomc = "fomc" in w
    guessed_tier, guessed_fomc = classify_tier(w.get("label") or "")
    tier = w["tier"] if has_tier else guessed_tier
    # Explicit fomc (including False, e.g. FOMC minutes) is never replaced by a label guess.
    fomc = bool(w.get("fomc")) if has_fomc else (False if has_tier else guessed_fomc)
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
    # already present: do not touch start/end/label/tier/fomc (M5-News hand-set values are authoritative)
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
    `soon` / `soon_action` describe the next window. Stored start/end already include the official
    lead-in, so a hard-block 'soon' flag is only raised in the last 5 minutes before a tier-A
    window starts. exit 1 from `now` only when action==block (or soon_block)."""
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
        # Stored windows already include policy lead-ins; only flag the last 5 min before a block.
        pre = 5 if m["action"] == "block" else None
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
