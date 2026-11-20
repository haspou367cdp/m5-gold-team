"""Point-in-time market data for the Phase 4 replay (historical simulation, no look-ahead).

bars_at(tf, t) returns exactly what the live bot could have seen at Tehran/UTC instant t:
1-minute bars whose minute has fully closed (open <= t - 1 min), and higher time frames resampled
from those bars only (the last M5/M15/H1/H4 bar is the partial bar built from the closed minutes).
"""
import os
import pandas as pd

HIST = os.environ.get("P4_HIST", "/workspace/data/gold_1m/xauusd_1m.parquet")
TFS = {"m5": "5min", "m15": "15min", "h1": "1h", "h4": "4h"}
AGG = {"o_b": "first", "h_b": "max", "l_b": "min", "c_b": "last", "o_a": "first", "h_a": "max",
       "l_a": "min", "c_a": "last", "v_b": "sum", "v_a": "sum"}


def load_hist(path=HIST, start=None, end=None):
    d = pd.read_parquet(path)
    if "ts_utc" in d.columns:
        d = d.set_index("ts_utc")
        d = d.rename(columns={"bid_o": "o_b", "bid_h": "h_b", "bid_l": "l_b", "bid_c": "c_b", "ask_o": "o_a",
                              "ask_h": "h_a", "ask_l": "l_a", "ask_c": "c_a", "bid_vol": "v_b", "ask_vol": "v_a"})
        if "bad_quote" in d.columns:
            d = d[~d.bad_quote]
    d = d[["o_b", "h_b", "l_b", "c_b", "v_b", "o_a", "h_a", "l_a", "c_a", "v_a"]].astype("float64")
    d.index = pd.DatetimeIndex(d.index).tz_convert("UTC").as_unit("ns")
    d = d[~d.index.duplicated()].sort_index()
    if start is not None:
        d = d[d.index >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        d = d[d.index < pd.Timestamp(end, tz="UTC")]
    return d


def resample(m1, rule):
    """Same rules as tools/m5lib.resample_m1."""
    g = m1.resample(rule, label="left", closed="left")
    out = g.agg(AGG).dropna(subset=["c_b"])
    out = out.rename(columns={"o_b": "o", "h_b": "h", "l_b": "l", "c_b": "c"})
    out["v"] = out.pop("v_b").fillna(0) + out.pop("v_a").fillna(0)
    out["spread"] = out.c_a - out.c
    out["spread_avg"] = (m1.c_a - m1.c_b).resample(rule, label="left", closed="left").mean().reindex(out.index)
    return out


class Market:
    """Full history + pre-resampled frames; slices are cut at t and the partial last bar is rebuilt."""

    def __init__(self, m1, depth_days=62):
        self.m1 = m1
        self.depth = pd.Timedelta(days=depth_days)
        self.full = {tf: resample(m1, r) for tf, r in TFS.items()}
        self._i = m1.index

    def cut(self, t):
        return pd.Timestamp(t).tz_convert("UTC") - pd.Timedelta(minutes=1)   # last usable minute (closed)

    def m1_at(self, t):
        c = self.cut(t)
        lo = self._i.searchsorted(c - self.depth, "left")
        hi = self._i.searchsorted(c, "right")
        return self.m1.iloc[lo:hi]

    def bars_at(self, tf, t):
        if tf == "1m":
            return self.m1_at(t)
        c = self.cut(t)
        f = self.full[tf]
        rule = TFS[tf]
        b0 = c.floor(rule) if tf != "h4" else c.floor("4h")
        lo = f.index.searchsorted(c - self.depth, "left")
        hi = f.index.searchsorted(b0, "left")          # complete bars only
        done = f.iloc[lo:hi]
        part_src = self.m1.iloc[self._i.searchsorted(b0, "left"):self._i.searchsorted(c, "right")]
        if len(part_src):
            part = resample(part_src, rule)
            part = part[part.index == b0]
            if len(part):
                return pd.concat([done, part])
        return done
