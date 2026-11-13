#!/usr/bin/env python3
"""fetch_xauusd.py - pull fresh XAUUSD 1-minute candles (bid + ask) and build M5/M15/H1.

Primary source : Dukascopy public chart datafeed (freeserv.dukascopy.com, XAU/USD spot, 1MIN, BID and ASK).
Fallback source: Yahoo Finance via yfinance (GC=F COMEX futures; XAUUSD=X is delisted). Fallback has NO bid/ask
                 split (spread unknown) and GC=F is futures, not spot (price differs from broker spot by the basis).
Cache          : /workspace/m5-gold-team/data/xauusd_{1m,m5,m15,h1,h4}.parquet + meta.json (source, as-of).
Exit codes     : 0 ok | 2 data STALE while market open (>--max-age min) | 3 all sources failed.

usage: python3 fetch_xauusd.py [--days 10] [--max-age 15] [--source auto|dukascopy|yahoo] [--quiet]
Signal-only research tool. Not financial advice."""
import argparse, os, sys, time
import pandas as pd, requests
sys.path.insert(0, "/workspace/m5-gold-team/tools")
from m5lib import DATA, META_JSON, UTC, teh, now_utc, market_open, minutes_since_open, save_json, load_json, month_starts_utc

DUKA = ("https://freeserv.dukascopy.com/2.0/index.php?path=chart%2Fjson3&instrument=XAU%2FUSD"
        "&offer_side={side}&interval=1MIN&splits=true&stocks=true&limit=2000&time_direction=N&timestamp={ts}&jsonp=_cb")
HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://freeserv.dukascopy.com/"}
COLS = ["o", "h", "l", "c", "v"]

def _duka_page(side, ts):
    last = ""
    for att in range(4):
        try:
            r = requests.get(DUKA.format(side=side, ts=ts), headers=HDR, timeout=20)
            last = r.text
            return __import__("json").loads(last[last.index("(") + 1:last.rindex(")")])
        except Exception as e:
            last = f"{e} {last[:150]}"
            time.sleep(2 * (att + 1))
    raise RuntimeError(f"Dukascopy {side} page at {ts} failed: {last}")

def _duka_side(side, start_ms, now_ms):
    rows, ts = [], start_ms
    while ts < now_ms:
        d = [x for x in _duka_page(side, ts) if x[0] >= ts]
        if not d: break
        rows += d; ts = d[-1][0] + 60000
        if len(d) < 2000: break
        time.sleep(0.3)
    df = pd.DataFrame(rows, columns=["ts_ms"] + COLS).drop_duplicates("ts_ms", keep="last")
    df = df[df.ts_ms + 60000 + 5000 <= now_ms]                     # completed bars only
    flat = (df.v == 0) & (df.o == df.h) & (df.h == df.l) & (df.l == df.c)
    return df[~flat]                                               # drop filler bars when market closed

def fetch_dukascopy(days):
    now_ms = int(time.time() * 1000); start = now_ms - int(days * 86400000); start -= start % 60000
    b = _duka_side("B", start, now_ms); a = _duka_side("A", start, now_ms)
    if b.empty: raise RuntimeError("Dukascopy returned no bid bars")
    m = b.merge(a, on="ts_ms", how="left", suffixes=("_b", "_a"))
    m.index = pd.to_datetime(m.pop("ts_ms"), unit="ms", utc=True); m.index.name = "ts_utc"
    return m.sort_index(), "Dukascopy freeserv XAU/USD spot 1m (bid + ask)"

def fetch_yahoo(days):
    import yfinance as yf
    errs = []
    # XAUUSD=X is delisted on Yahoo (404 as of 2026-11-12); GC=F is the only working Yahoo gold 1m series.
    for sym, label in [("GC=F", "Yahoo Finance GC=F (COMEX gold FUTURES, not spot - differs from broker by basis; NO bid/ask; may be delayed)")]:
        try:
            df = yf.download(sym, period=f"{min(int(days)+1, 7)}d", interval="1m", progress=False, auto_adjust=False)
            if df is None or df.empty: errs.append(f"{sym}: empty"); continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.rename(columns=str.lower)
            out = pd.DataFrame({"o_b": df.open, "h_b": df.high, "l_b": df.low, "c_b": df.close,
                                "v_b": df.get("volume", 0).astype(float)})
            for c in COLS: out[f"{c}_a"] = float("nan")
            out.index = pd.to_datetime(out.index, utc=True); out.index.name = "ts_utc"
            out = out[out.index + pd.Timedelta(minutes=1) <= pd.Timestamp.now(tz="UTC")]
            return out.dropna(subset=["c_b"]).sort_index(), label
        except Exception as e:
            errs.append(f"{sym}: {e}")
    raise RuntimeError("Yahoo fallback failed: " + "; ".join(errs))

def resample(m1, rule):
    g = m1.resample(rule, label="left", closed="left")
    out = g.agg({"o_b": "first", "h_b": "max", "l_b": "min", "c_b": "last", "o_a": "first", "h_a": "max",
                 "l_a": "min", "c_a": "last", "v_b": "sum", "v_a": "sum"})
    out = out.dropna(subset=["c_b"])
    out = out.rename(columns={"o_b": "o", "h_b": "h", "l_b": "l", "c_b": "c"})
    out["v"] = out.pop("v_b").fillna(0) + out.pop("v_a").fillna(0)
    out["spread"] = out.c_a - out.c                                    # ask - bid at bar close
    out["spread_avg"] = (m1.c_a - m1.c_b).resample(rule, label="left", closed="left").mean().reindex(out.index)
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=float, default=10, help="look-back in calendar days (default 10)")
    ap.add_argument("--max-age", type=float, default=15, help="max minutes since last bar close during market hours")
    ap.add_argument("--source", default="auto", choices=["auto", "dukascopy", "yahoo"])
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    errors, m1, src = [], None, None
    order = {"auto": [fetch_dukascopy, fetch_yahoo], "dukascopy": [fetch_dukascopy], "yahoo": [fetch_yahoo]}[a.source]
    for fn in order:
        try:
            m1, src = fn(a.days)
            if fn is fetch_yahoo: src = "FALLBACK - " + src
            break
        except Exception as e:
            errors.append(str(e)); print(f"WARN: {fn.__name__} failed: {e}", file=sys.stderr)
    if m1 is None or m1.empty:
        print("ERROR: ALL DATA SOURCES FAILED - no prices available. Do NOT publish levels.", file=sys.stderr)
        save_json(META_JSON, {"ok": False, "errors": errors, "checked_at_utc": str(now_utc())}); sys.exit(3)

    # Merge with any older cached bars so prev-month H/L, ADR(20) and weekly levels keep a stable history.
    # A short incremental fetch must not wipe a longer cache. Keep at least the previous NY month
    # (plus a 2-day pad) and never less than 80 calendar days.
    cache_1m = f"{DATA}/xauusd_1m.parquet"
    try:
        if os.path.exists(cache_1m):
            old = pd.read_parquet(cache_1m)
            if old is not None and len(old) and old.index.tz is not None:
                m1 = pd.concat([old, m1]).sort_index()
                m1 = m1[~m1.index.duplicated(keep="last")]
                _, prev_m = month_starts_utc(m1.index[-1])
                floor = pd.Timestamp(prev_m) - pd.Timedelta(days=2)
                if floor.tzinfo is None:
                    floor = floor.tz_localize("UTC")
                cut = min(floor, m1.index[-1] - pd.Timedelta(days=80))
                m1 = m1[m1.index >= cut]
    except Exception as e:
        errors.append(f"cache merge skipped: {e}")

    m1.to_parquet(cache_1m)
    for tf, rule in [("m5", "5min"), ("m15", "15min"), ("h1", "1h"), ("h4", "4h")]:
        resample(m1, rule).to_parquet(f"{DATA}/xauusd_{tf}.parquet")

    now = pd.Timestamp(now_utc())
    last_open = m1.index[-1]; last_close = last_open + pd.Timedelta(minutes=1)
    age = (now - last_close).total_seconds() / 60
    is_open = market_open(now); since_open = minutes_since_open(now)
    stale = bool(is_open and since_open > a.max_age and age > a.max_age)
    meta = {"ok": not stale, "source": src, "fallback": src.startswith("FALLBACK"), "bars_1m": len(m1),
            "first_bar_utc": str(m1.index[0]), "last_bar_open_utc": str(last_open),
            "as_of_tehran": teh(last_close, "%Y-%m-%d %H:%M"), "fetched_at_tehran": teh(now, "%Y-%m-%d %H:%M:%S"),
            "age_minutes": round(age, 1), "market_open": is_open, "stale": stale,
            "last_bid": round(float(m1.c_b.iloc[-1]), 3),
            "last_ask": None if pd.isna(m1.c_a.iloc[-1]) else float(m1.c_a.iloc[-1]),
            "price_side": ("single last-trade price of COMEX futures (NOT spot; basis vs broker can be several $)" if src.startswith("FALLBACK")
                           else "bid (broker quotes may differ by ~$1)"), "errors": errors}
    save_json(META_JSON, meta)
    if not a.quiet:
        print(f"source : {src}\nbars   : {len(m1)} x 1m  ({teh(m1.index[0])} -> {teh(last_open)} Tehran, bar open)")
        print(f"as-of  : {meta['as_of_tehran']} Tehran (last bar close), age {age:.1f} min, market {'OPEN' if is_open else 'CLOSED'}")
        print(f"last   : bid {meta['last_bid']}  ask {meta['last_ask']}")
        print(f"cache  : {DATA}/xauusd_{{1m,m5,m15,h1,h4}}.parquet, {META_JSON}")
    if stale:
        print(f"!!! STALE DATA: last bar closed {age:.0f} min ago while market is open (limit {a.max_age:.0f}). "
              f"Do NOT use these prices.", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
