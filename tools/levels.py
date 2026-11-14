#!/usr/bin/env python3
"""levels.py - key XAUUSD levels for M5 scalping. Reads the cache written by fetch_xauusd.py.

Computes (all prices = Dukascopy BID unless the fallback source is in use; see meta.json):
  * previous trading-day high/low (gold day = 18:00 -> 17:00 New York = 02:30 -> 01:30 Tehran in US winter)
  * previous calendar-month H/L (New York month) and month-to-date H/L; incomplete if the cache starts late
  * today's Asia / London / New York session highs & lows + yesterday's NY high/low
      Asia 00:00 UTC-07:00 London (03:30-10:30 Tehran) | London 07:00 London-08:30 NY (10:30-17:00 Tehran)
      NY 08:30-17:00 NY (17:00-01:30 Tehran)   [zoneinfo => DST-correct automatically]
  * opening range = first 30 minutes of London and of New York
  * equal highs / equal lows on M15 (two or more swings inside the cluster tolerance)
  * round numbers ($5 / $10, extra weight for $50 / $100)
  * session VWAP (Asia / London / NY) and trading-day VWAP, mid typical price, tick volume (labelled as a tick-volume proxy), ±1σ on the day VWAP
  * EMA20 / EMA50 on M5, M15, H1, H4 ;  ATR(14) M5/H1/H4 (Wilder) ; fractal swing highs/lows on M5 / M15 / H1 / H4
Ranking: candidates within tol = max($0.5, 0.25*ATR_M5) are clustered; score = sum of source weights
+ 0.5 per distinct M15 reaction ("touch") in the last 3 days (max +2).
Ranks (strong/medium/weak) are stored in JSON only, are NOT backtested, and must not be printed as "قوی".
Output: /workspace/m5-gold-team/data/levels.json   usage: python3 levels.py [--range 60] [--print]"""
import argparse, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/workspace/m5-gold-team/tools")
from m5lib import (LEVELS_JSON, META_JSON, NY, UTC, load_bars, load_json, month_starts_utc, save_json, sessions_for, teh,
                   trading_day_start, previous_trading_day_start)

W = {"PDH": 3, "PDL": 3, "H4 swing high": 3, "H4 swing low": 3,
     "H1 swing high": 3, "H1 swing low": 3, "Asia high": 2, "Asia low": 2,
     "London high": 2.5, "London low": 2.5, "NY high": 2.5, "NY low": 2.5, "Prev NY high": 2, "Prev NY low": 2,
     "Today high": 1, "Today low": 1, "M15 swing high": 2, "M15 swing low": 2, "M5 swing high": 1, "M5 swing low": 1,
     "VWAP": 1.5, "VWAP +1σ": 0.5, "VWAP -1σ": 0.5,
     "Asia VWAP": 1.2, "London VWAP": 1.5, "NY VWAP": 1.5,
     "EMA20 H4": 2, "EMA50 H4": 2, "EMA20 H1": 1.5, "EMA50 H1": 1.5, "EMA20 M15": 1,
     "EMA50 M15": 1, "Round $100": 2.5, "Round $50": 2, "Round $10": 1, "Round $5": 0.5, "Daily high": 2.5, "Daily low": 2.5,
     "Prev month high": 3, "Prev month low": 3, "Month high": 2, "Month low": 2,
     "Equal high": 2.5, "Equal low": 2.5,
     "London OR high": 2, "London OR low": 2, "NY OR high": 2, "NY OR low": 2}
FA = {"PDH": "سقف دیروز", "PDL": "کف دیروز", "H4 swing high": "سقف چرخشی H4", "H4 swing low": "کف چرخشی H4",
      "H1 swing high": "سقف چرخشی H1", "H1 swing low": "کف چرخشی H1",
      "Asia high": "سقف آسیا", "Asia low": "کف آسیا", "London high": "سقف لندن", "London low": "کف لندن",
      "NY high": "سقف نیویورک", "NY low": "کف نیویورک", "Prev NY high": "سقف نیویورک دیروز",
      "Prev NY low": "کف نیویورک دیروز", "Today high": "سقف امروز", "Today low": "کف امروز",
      "M15 swing high": "سقف چرخشی M15", "M15 swing low": "کف چرخشی M15", "M5 swing high": "سقف چرخشی M5",
      "M5 swing low": "کف چرخشی M5", "VWAP": "VWAP روز (پروکسی حجم تیک)", "VWAP +1σ": "VWAP +1σ", "VWAP -1σ": "VWAP -1σ",
      "Asia VWAP": "VWAP آسیا (پروکسی حجم تیک)", "London VWAP": "VWAP لندن (پروکسی حجم تیک)",
      "NY VWAP": "VWAP نیویورک (پروکسی حجم تیک)",
      "EMA20 H4": "EMA20 H4", "EMA50 H4": "EMA50 H4", "EMA20 H1": "EMA20 H1", "EMA50 H1": "EMA50 H1",
      "EMA20 M15": "EMA20 M15", "EMA50 M15": "EMA50 M15",
      "Round $100": "عدد رُند", "Round $50": "عدد رُند", "Round $10": "عدد رُند", "Round $5": "عدد رُند ۵",
      "Daily high": "سقف روزانه", "Daily low": "کف روزانه",
      "Prev month high": "سقف ماه قبل", "Prev month low": "کف ماه قبل",
      "Month high": "سقف ماه جاری", "Month low": "کف ماه جاری",
      "Equal high": "سقف برابر M15", "Equal low": "کف برابر M15",
      "London OR high": "سقف رنج بازگشایی لندن", "London OR low": "کف رنج بازگشایی لندن",
      "NY OR high": "سقف رنج بازگشایی نیویورک", "NY OR low": "کف رنج بازگشایی نیویورک"}

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def atr(df, n=14):
    pc = df.c.shift(1)
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()

def fractals(df, n, since=None):
    x = df if since is None else df[df.index >= since]
    hi, lo = x.h.values, x.l.values; H, L = [], []
    for k in range(n, len(x) - n):
        if hi[k] == hi[k - n:k + n + 1].max(): H.append((x.index[k], float(hi[k])))
        if lo[k] == lo[k - n:k + n + 1].min(): L.append((x.index[k], float(lo[k])))
    return H, L

def hl(df, a, b):
    s = df[(df.index >= a) & (df.index < b)]
    if s.empty: return None
    return {"high": float(s.h.max()), "high_t": teh(s.h.idxmax()), "low": float(s.l.min()), "low_t": teh(s.l.idxmin()),
            "from": teh(a), "to": teh(min(b, s.index[-1] + pd.Timedelta(minutes=1))), "complete": bool(s.index[-1] + pd.Timedelta(minutes=1) >= b)}


def week_start_utc(t_utc):
    """Sunday 18:00 New York that opened the current gold week (Monday 02:30 Tehran in US winter)."""
    n = pd.Timestamp(t_utc).tz_convert(NY)
    days_since_sun = (n.weekday() + 1) % 7
    sunday = n.normalize() - pd.Timedelta(days=int(days_since_sun))
    start = sunday + pd.Timedelta(hours=18)
    if n < start:
        start -= pd.Timedelta(days=7)
    return pd.Timestamp(start).tz_convert(UTC)

def _vwap_block(bid1, start, end, last_t, label_anchor):
    """Mid typical price × tick volume (bid+ask ticks). Not exchange volume. Returns None if no bars."""
    b = bid1
    # 1m frame uses h_b/l_b/c_b; after rename, h/l/c. Support both.
    df = bid1
    end_eff = min(pd.Timestamp(end), pd.Timestamp(last_t) + pd.Timedelta(minutes=1))
    t = df[(df.index >= start) & (df.index < end_eff)]
    if t.empty:
        return None
    if {"h_b", "l_b", "c_b"}.issubset(t.columns):
        mid = ((t.h_b + t.l_b + t.c_b) / 3 + (t.h_a.fillna(t.h_b) + t.l_a.fillna(t.l_b) + t.c_a.fillna(t.c_b)) / 3) / 2
        v = (t.v_b.fillna(0) + t.v_a.fillna(0)).replace(0, np.nan).fillna(1e-9)
    else:
        typ = (t.h + t.l + t.c) / 3
        mid = typ
        v = (t["v"] if "v" in t.columns else pd.Series(1.0, index=t.index)).replace(0, np.nan).fillna(1e-9)
        if {"h_a", "l_a", "c_a"}.issubset(t.columns):
            mid = (typ + (t.h_a.fillna(t.h) + t.l_a.fillna(t.l) + t.c_a.fillna(t.c)) / 3) / 2
    vw = (mid * v).cumsum() / v.cumsum()
    sd = np.sqrt(((mid - vw) ** 2 * v).cumsum() / v.cumsum())
    return {"vwap": round(float(vw.iloc[-1]), 2), "sd": round(float(sd.iloc[-1]), 2),
            "anchor_tehran": teh(start), "as_of_tehran": teh(t.index[-1] + pd.Timedelta(minutes=1)),
            "volume_note": "tick-volume proxy (not exchange volume)", "bars": int(len(t)),
            "complete": bool(pd.Timestamp(last_t) + pd.Timedelta(minutes=1) >= pd.Timestamp(end))}

def equal_swings(swings, tol, side):
    """Cluster M15 swing highs or lows that sit within `tol` of each other. Need >= 2 swings."""
    pts = sorted(swings, key=lambda x: x[1])  # (t, price)
    if len(pts) < 2:
        return []
    clusters, cur = [], [pts[0]]
    for p in pts[1:]:
        if p[1] - cur[0][1] <= tol and p[1] - cur[-1][1] <= tol:
            cur.append(p)
        else:
            clusters.append(cur); cur = [p]
    clusters.append(cur)
    out = []
    for cl in clusters:
        if len(cl) < 2:
            continue
        prices = [p for _, p in cl]
        out.append({"price": round(float(np.mean(prices)), 2),
                    "zone": [round(min(prices), 2), round(max(prices), 2)],
                    "n": len(cl), "side": side,
                    "times": [teh(t) for t, _ in cl]})
    return out

def add_structure(out, bid, last_t, n_adr=20):
    """PDH/PDL already in sessions; add week H/L, previous week, month H/L, ADR of N full days (default 20), % used, D1 structure."""
    d0 = trading_day_start(last_t)
    ws = week_start_utc(last_t)
    pws = ws - pd.Timedelta(days=7)
    week = hl(bid, ws, last_t + pd.Timedelta(minutes=1))
    prev_week = hl(bid, pws, ws)
    if prev_week is not None:
        prev_week["incomplete"] = bool(len(bid) and bid.index[0] > pws + pd.Timedelta(hours=6))
    if week is not None:
        week["incomplete"] = False
    this_m, prev_m = month_starts_utc(last_t)
    # next month start = this_m + ~32d rolled to day 1, but we only need prev month [prev_m, this_m) and MTD [this_m, now]
    prev_month = hl(bid, prev_m, this_m)
    month = hl(bid, this_m, last_t + pd.Timedelta(minutes=1))
    cache_start = bid.index[0] if len(bid) else None
    if prev_month is not None:
        prev_month["incomplete"] = bool(cache_start is not None and cache_start > prev_m + pd.Timedelta(hours=12))
        prev_month["cache_start_tehran"] = teh(cache_start) if cache_start is not None else None
    if month is not None:
        month["incomplete"] = bool(cache_start is not None and cache_start > this_m + pd.Timedelta(hours=12))
        month["complete"] = False  # month still running
    days, ds = [], d0
    for _ in range(40):
        if len(days) >= n_adr:
            break
        ds = previous_trading_day_start(ds)
        end = ds + pd.Timedelta(hours=23)          # 18:00 NY -> 17:00 NY next calendar day
        sl = bid[(bid.index >= ds) & (bid.index < end)]
        if sl.empty:
            continue
        span_h = (sl.index[-1] - sl.index[0]).total_seconds() / 3600.0
        if len(sl) < 800 or span_h < 16:           # drop weekend stubs / half days
            continue
        r = hl(bid, ds, end)
        if not r:
            continue
        days.append({"day_start_tehran": teh(ds), "high": r["high"], "low": r["low"],
                     "range": round(r["high"] - r["low"], 3), "bars": int(len(sl))})
    adr = (sum(d["range"] for d in days) / len(days)) if days else None
    today = (out.get("sessions") or {}).get("today")
    today_range = (today["high"] - today["low"]) if today else None
    used = (100.0 * today_range / adr) if (adr and today_range is not None and adr > 0) else None
    d1 = "n/a"
    if len(days) >= 2:
        h1, h2 = days[0]["high"], days[1]["high"]
        l1, l2 = days[0]["low"], days[1]["low"]
        if h1 < h2 and l1 < l2: d1 = "LH/LL"
        elif h1 > h2 and l1 > l2: d1 = "HH/HL"
        else: d1 = "mixed"
    out["structure"] = {
        "week": week, "prev_week": prev_week,
        "prev_month": prev_month, "month": month,
        "adr_n": len(days), "adr": None if adr is None else round(adr, 2),
        "today_range": None if today_range is None else round(today_range, 2),
        "adr_used_pct": None if used is None else round(used, 1),
        "d1_structure": d1,
        "adr_days": days,
    }
    return out

def compute(rng=None):
    m1, m5, m15, h1, h4 = (load_bars(t) for t in ("1m", "m5", "m15", "h1", "h4"))
    meta = load_json(META_JSON, {})
    last_t = m1.index[-1]; price = float(m1.c_b.iloc[-1])
    out = {"as_of_tehran": meta.get("as_of_tehran"), "source": meta.get("source"), "price_bid": price,
           "price_ask": meta.get("last_ask")}
    # --- ATR / EMAs ---
    a5 = float(atr(m5).iloc[-1]); out["atr_m5_14"] = round(a5, 2)
    out["atr_h1_14"] = round(float(atr(h1).iloc[-1]), 2)
    out["atr_h4_14"] = round(float(atr(h4).iloc[-1]), 2) if len(h4) >= 16 else None
    emas = {}
    for name, df in (("M5", m5), ("M15", m15), ("H1", h1), ("H4", h4)):
        if len(df) < 56:
            continue
        e20, e50 = ema(df.c, 20), ema(df.c, 50)
        emas[name] = {"ema20": round(float(e20.iloc[-1]), 2), "ema50": round(float(e50.iloc[-1]), 2),
                      "ema20_slope5": round(float(e20.iloc[-1] - e20.iloc[-6]), 2),
                      "ema50_slope5": round(float(e50.iloc[-1] - e50.iloc[-6]), 2), "close": float(df.c.iloc[-1])}
    out["ema"] = emas
    # --- sessions ---
    d0 = trading_day_start(last_t); dp = previous_trading_day_start(d0)
    out["trading_day_start_tehran"] = teh(d0)
    pd_ = hl(m1.rename(columns={"h_b": "h", "l_b": "l"}), dp, d0 - pd.Timedelta(hours=1))   # 18:00 -> 17:00 NY
    bid = m1.rename(columns={"o_b": "o", "h_b": "h", "l_b": "l", "c_b": "c"})
    ses = sessions_for(last_t); y = sessions_for(last_t - pd.Timedelta(days=1))
    # yesterday's NY: use the last weekday's NY session
    yd = last_t - pd.Timedelta(days=1)
    while yd.weekday() >= 5: yd -= pd.Timedelta(days=1)
    yny = sessions_for(yd)["ny"]
    out["sessions"] = {"prev_day": pd_, "today": hl(bid, d0, last_t + pd.Timedelta(minutes=1)),
                       "asia": hl(bid, *ses["asia"]), "london": hl(bid, *ses["london"]), "ny": hl(bid, *ses["ny"]),
                       "prev_ny": hl(bid, *yny)}
    # --- opening range: first 30 minutes of London and NY ---
    or_td = pd.Timedelta(minutes=30)
    out["opening_ranges"] = {
        "london": hl(bid, ses["london"][0], ses["london"][0] + or_td),
        "ny": hl(bid, ses["ny"][0], ses["ny"][0] + or_td),
    }
    # --- VWAP: trading-day + each session, tick-volume proxy ---
    day_vwap = _vwap_block(m1, d0, last_t + pd.Timedelta(days=1), last_t, "day")
    if day_vwap:
        day_vwap["complete"] = False
        out["vwap"] = day_vwap
    sess_vwap = {}
    for key, (a, b) in (("asia", ses["asia"]), ("london", ses["london"]), ("ny", ses["ny"])):
        block = _vwap_block(m1, a, b, last_t, key)
        if block:
            sess_vwap[key] = block
    out["session_vwap"] = sess_vwap
    out["vwap_note"] = "All VWAPs use tick volume (bid+ask ticks), not exchange volume — a tick-volume proxy."
    # --- candidates ---
    C = []
    def add(price_, kind, t_=None):
        if price_ is not None and np.isfinite(price_): C.append({"price": float(price_), "kind": kind, "t": t_})
    s = out["sessions"]
    if s["prev_day"]: add(s["prev_day"]["high"], "PDH", s["prev_day"]["high_t"]); add(s["prev_day"]["low"], "PDL", s["prev_day"]["low_t"])
    for key, nm in (("asia", "Asia"), ("london", "London"), ("ny", "NY"), ("prev_ny", "Prev NY"), ("today", "Today")):
        if s.get(key): add(s[key]["high"], f"{nm} high", s[key]["high_t"]); add(s[key]["low"], f"{nm} low", s[key]["low_t"])
    for key, nm in (("london", "London OR"), ("ny", "NY OR")):
        r = (out["opening_ranges"] or {}).get(key)
        if r:
            add(r["high"], f"{nm} high", r["high_t"]); add(r["low"], f"{nm} low", r["low_t"])
    # daily highs/lows of the 5 trading days before yesterday (gold day 18:00->17:00 NY)
    ds = dp; daily = []
    for _ in range(5):
        ds = previous_trading_day_start(ds); r = hl(bid, ds, ds + pd.Timedelta(hours=23))
        if r:
            daily.append({"day_start_tehran": teh(ds), **r}); add(r["high"], "Daily high", r["high_t"]); add(r["low"], "Daily low", r["low_t"])
    out["daily"] = daily
    for name, df, n, look in (("H4", h4, 3, pd.Timedelta(days=20)), ("H1", h1, 3, pd.Timedelta(days=8)),
                               ("M15", m15, 3, pd.Timedelta(days=2)), ("M5", m5, 3, pd.Timedelta(hours=12))):
        if df is None or len(df) < 2 * n + 3:
            continue
        H, L = fractals(df, n, last_t - look)
        for tt, p in H: add(p, f"{name} swing high", teh(tt))
        for tt, p in L: add(p, f"{name} swing low", teh(tt))
    # M5 is included here only so the display snapshot can read structure+EMA like the other
    # frames. Candidates and scores above are unchanged (M5 fractals were already in C).
    out["swings"] = {nm: {"highs": [(teh(a), b) for a, b in fractals(df, 3, last_t - lk)[0][-5:]],
                          "lows": [(teh(a), b) for a, b in fractals(df, 3, last_t - lk)[1][-5:]]}
                     for nm, df, lk in (("H4", h4, pd.Timedelta(days=20)), ("H1", h1, pd.Timedelta(days=8)),
                                        ("M15", m15, pd.Timedelta(days=2)),
                                        ("M5", m5, pd.Timedelta(days=1))) if df is not None and len(df) >= 10}
    if "vwap" in out:
        add(out["vwap"]["vwap"], "VWAP"); add(out["vwap"]["vwap"] + out["vwap"]["sd"], "VWAP +1σ"); add(out["vwap"]["vwap"] - out["vwap"]["sd"], "VWAP -1σ")
    for key, kind in (("asia", "Asia VWAP"), ("london", "London VWAP"), ("ny", "NY VWAP")):
        if sess_vwap.get(key) and sess_vwap[key].get("vwap") is not None:
            add(sess_vwap[key]["vwap"], kind)
    for tf in ("H4", "H1", "M15"):
        if tf in emas:
            add(emas[tf]["ema20"], f"EMA20 {tf}"); add(emas[tf]["ema50"], f"EMA50 {tf}")
    # month H/L added after structure is filled — compute month now so we can add candidates
    this_m, prev_m = month_starts_utc(last_t)
    prev_month_hl = hl(bid, prev_m, this_m)
    month_hl = hl(bid, this_m, last_t + pd.Timedelta(minutes=1))
    if prev_month_hl:
        add(prev_month_hl["high"], "Prev month high", prev_month_hl["high_t"])
        add(prev_month_hl["low"], "Prev month low", prev_month_hl["low_t"])
    if month_hl:
        add(month_hl["high"], "Month high", month_hl["high_t"])
        add(month_hl["low"], "Month low", month_hl["low_t"])
    # equal highs / lows on M15
    tol_eq = max(0.5, 0.25 * a5)
    H15, L15 = fractals(m15, 3, last_t - pd.Timedelta(days=3))
    eq_h = equal_swings(H15, tol_eq, "high")
    eq_l = equal_swings(L15, tol_eq, "low")
    out["equal"] = {"highs": eq_h, "lows": eq_l, "tolerance": round(tol_eq, 2)}
    for e in eq_h:
        add(e["price"], "Equal high", e["times"][-1] if e["times"] else None)
    for e in eq_l:
        add(e["price"], "Equal low", e["times"][-1] if e["times"] else None)
    rng = rng or max(60.0, 8 * (out.get("atr_h1_14") or 8))
    C = [c for c in C if abs(c["price"] - price) <= rng]
    for r in np.arange(np.floor((price - rng) / 5) * 5, price + rng, 5):
        kind = "Round $100" if r % 100 == 0 else "Round $50" if r % 50 == 0 else "Round $10" if r % 10 == 0 else "Round $5"
        add(float(r), kind)
    # --- cluster ---
    tol = max(0.5, 0.25 * a5); out["cluster_tol"] = round(tol, 2)
    C.sort(key=lambda c: c["price"]); clusters = []
    for c in C:
        if clusters and c["price"] - clusters[-1][-1]["price"] <= tol: clusters[-1].append(c)
        else: clusters.append([c])
    recent = m15[m15.index >= last_t - pd.Timedelta(days=3)]
    levels = []
    for cl in clusters:
        kinds = sorted({c["kind"] for c in cl}, key=lambda k: -W[k])
        structural = [c for c in cl if not c["kind"].startswith(("Round", "EMA", "VWAP", "Asia VWAP", "London VWAP", "NY VWAP"))]
        ref = structural or cl
        p = float(np.mean([c["price"] for c in ref])); lo_, hi_ = min(c["price"] for c in cl), max(c["price"] for c in cl)
        near = ((recent.h - p).abs() <= tol) | ((recent.l - p).abs() <= tol)
        touches = int((near & ~near.shift(1, fill_value=False)).sum())       # distinct M15 reactions
        score = sum(W[k] for k in kinds) + min(2.0, 0.5 * touches)
        if score < 1: continue
        strength = "strong" if score >= 6 else "medium" if score >= 3.5 else "weak"
        levels.append({"price": round(p, 2), "zone": [round(lo_, 2), round(hi_, 2)], "side": "resistance" if p > price else "support",
                       "distance": round(p - price, 2), "distance_atr": round((p - price) / a5, 2), "score": round(score, 1),
                       "strength": strength, "touches_m15_3d": touches, "kinds": kinds,
                       "label_fa": "، ".join(dict.fromkeys(FA[k] for k in kinds)), "times": [c["t"] for c in cl if c["t"]]})
    out["levels"] = levels
    out["round_numbers"] = [float(r) for r in np.arange(np.floor((price - 30) / 5) * 5, price + 30, 5)]
    add_structure(out, bid, last_t)
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--range", type=float, default=None, help="$ distance from price to keep (default max(60, 8*ATR_H1))")
    ap.add_argument("--print", action="store_true", help="print ranked table (score only; no قوی/متوسط/ضعیف)")
    a = ap.parse_args()
    out = compute(a.range); save_json(LEVELS_JSON, out)
    print(f"levels: {len(out['levels'])} -> {LEVELS_JSON} | price {out['price_bid']} | ATR M5 {out['atr_m5_14']} | as-of {out['as_of_tehran']} Tehran")
    if a.print:
        for L in sorted(out["levels"], key=lambda l: -l["price"]):
            print(f"{L['price']:>9.2f}  {L['side'][:3]}  score {L['score']:>4}  touches {L['touches_m15_3d']}  {', '.join(L['kinds'])}")

if __name__ == "__main__":
    main()
