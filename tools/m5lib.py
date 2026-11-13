"""Shared helpers for the M5 Gold Scalp toolkit (paths, time zones, sessions, market hours).
Signal-only research. Not financial advice. Never places trades."""
import json, os
from datetime import datetime, timedelta, timezone, time as dtime
from zoneinfo import ZoneInfo
import pandas as pd

ROOT = "/workspace/m5-gold-team"
DATA = f"{ROOT}/data"
TOOLS = f"{ROOT}/tools"
NEWS_JSON = f"{DATA}/news_windows.json"
META_JSON = f"{DATA}/meta.json"
LEVELS_JSON = f"{DATA}/levels.json"
BIAS_JSON = f"{DATA}/bias.json"
MACRO_JSON = f"{DATA}/macro.json"
TEH = ZoneInfo("Asia/Tehran"); NY = ZoneInfo("America/New_York"); LDN = ZoneInfo("Europe/London"); UTC = timezone.utc

def now_utc():
    return datetime.now(UTC)

def teh(t, fmt="%Y-%m-%d %H:%M"):
    """Format any tz-aware datetime / pandas Timestamp in Tehran time."""
    if t is None: return None
    t = pd.Timestamp(t)
    if t.tzinfo is None: t = t.tz_localize("UTC")
    return t.tz_convert(TEH).strftime(fmt)

def load_json(p, default=None):
    try:
        with open(p) as f: return json.load(f)
    except FileNotFoundError:
        return default

def save_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, p)

# ---------- market hours (spot gold, DST-correct via New York local time) ----------
# Open Sun 18:00 NY -> Fri 17:00 NY, daily maintenance break 17:00-18:00 NY.
def market_open(t_utc):
    n = pd.Timestamp(t_utc).tz_convert(NY)
    wd, hm = n.weekday(), n.hour * 60 + n.minute
    if wd == 5: return False                       # Saturday
    if wd == 6: return hm >= 18 * 60               # Sunday after 18:00
    if wd == 4 and hm >= 17 * 60: return False     # Friday after 17:00
    return not (17 * 60 <= hm < 18 * 60)           # daily break

def minutes_since_open(t_utc):
    """Minutes since the market last (re)opened; 0 if closed."""
    t = pd.Timestamp(t_utc)
    if not market_open(t): return 0
    m = 0
    while m < 60 * 24 * 3 and market_open(t - pd.Timedelta(minutes=m + 1)): m += 1
    return m

# ---------- sessions ----------
def trading_day_start(t_utc):
    """Start (UTC) of the gold trading day containing t: 18:00 New York (= 02:30 Tehran in US winter)."""
    n = pd.Timestamp(t_utc).tz_convert(NY)
    d = n.normalize() + pd.Timedelta(hours=18)
    if n < d: d -= pd.Timedelta(days=1)
    while d.weekday() in (4, 5):        # weekend: roll back to Thursday 18:00 NY
        d -= pd.Timedelta(days=1)
    return d.tz_convert(UTC)

def previous_trading_day_start(day_start_utc):
    d = pd.Timestamp(day_start_utc).tz_convert(NY) - pd.Timedelta(days=1)
    while d.weekday() in (4, 5): d -= pd.Timedelta(days=1)   # no trading day starts Fri/Sat 18:00
    return pd.Timestamp(datetime.combine(d.date(), dtime(18, 0)), tz=NY).tz_convert(UTC)

def sessions_for(t_utc):
    """Session windows (UTC) of the calendar day (UTC date) of t.
    Asia   = 00:00 UTC -> 07:00 London   (03:30-10:30 Tehran in winter)
    London = 07:00 London -> 08:30 NY    (10:30-17:00 Tehran in winter)
    NY     = 08:30 NY -> 17:00 NY        (17:00-01:30 Tehran in winter)"""
    t = pd.Timestamp(t_utc).tz_convert(UTC)
    d = t.normalize()
    date = d.date()
    lo = pd.Timestamp(datetime.combine(date, dtime(7, 0)), tz=LDN).tz_convert(UTC)
    ny0 = pd.Timestamp(datetime.combine(date, dtime(8, 30)), tz=NY).tz_convert(UTC)
    ny1 = pd.Timestamp(datetime.combine(date, dtime(17, 0)), tz=NY).tz_convert(UTC)
    return {"asia": (d, lo), "london": (lo, ny0), "ny": (ny0, ny1)}

def month_starts_utc(t_utc):
    """UTC instants of this and previous New York calendar-month opens."""
    n = pd.Timestamp(t_utc).tz_convert(NY)
    this = pd.Timestamp(year=n.year, month=n.month, day=1, tz=NY).tz_convert(UTC)
    prev_anchor = this - pd.Timedelta(days=1)
    prev = pd.Timestamp(year=prev_anchor.year, month=prev_anchor.month, day=1, tz=NY).tz_convert(UTC)
    return this, prev

def resample_m1(m1, rule):
    """Clock-resample the 1m bid/ask cache (same rules as fetch_xauusd.resample)."""
    g = m1.resample(rule, label="left", closed="left")
    out = g.agg({"o_b": "first", "h_b": "max", "l_b": "min", "c_b": "last", "o_a": "first", "h_a": "max",
                 "l_a": "min", "c_a": "last", "v_b": "sum", "v_a": "sum"})
    out = out.dropna(subset=["c_b"])
    out = out.rename(columns={"o_b": "o", "h_b": "h", "l_b": "l", "c_b": "c"})
    out["v"] = out.pop("v_b").fillna(0) + out.pop("v_a").fillna(0)
    out["spread"] = out.c_a - out.c
    out["spread_avg"] = (m1.c_a - m1.c_b).resample(rule, label="left", closed="left").mean().reindex(out.index)
    return out

def load_bars(tf):
    """tf in {'1m','m5','m15','h1','h4'} -> DataFrame indexed by UTC bar-open time.
    H4 is written by fetch_xauusd.py; if the file is missing it is rebuilt from the 1m cache."""
    p = f"{DATA}/xauusd_{tf}.parquet"
    if os.path.exists(p):
        return pd.read_parquet(p)
    if tf == "h4" and os.path.exists(f"{DATA}/xauusd_1m.parquet"):
        m1 = pd.read_parquet(f"{DATA}/xauusd_1m.parquet")
        out = resample_m1(m1, "4h")
        try:
            out.to_parquet(p)
        except Exception:
            pass
        return out
    raise SystemExit(f"ERROR: {p} missing. Run fetch_xauusd.py first.")
