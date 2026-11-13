#!/usr/bin/env python3
"""shadow.py - silent log of setups that were valid but blocked ONLY by a gate (news A/B, volatility spike,
spread, Friday/session). Research only: nothing here changes a live gate, sends a message or places a trade.

gates_active(brief)            -> gate names that blocked this run (from latest_brief.json)
candidate(cfg, at=None)        -> (decision, plan, sizing) recomputed with the gates switched off
resolve(entries, bars, now)    -> fill / TP / SL / expiry from later 1-minute bid bars (DaryaGold limit, SL and TP
                                  fills carry no spread, so bid +offset is the broker price)
summary(entries)               -> counts and totals
Result per entry: R (move / stop distance) and toman for one full unit (80,000 toman per $1, 14,000 fee)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TEH = ZoneInfo("Asia/Tehran")
FILL_MIN = 30          # the signal card's limit order is valid 30 min
HOLD_MIN = 240         # an open shadow trade is closed at market after 4 h
FULL_RATE, FEE = 80000, 14000
KEEP = 300             # entries kept in bot_state

def gates_active(b):
    """Names of the gates that blocked entries in this brief (empty = blocked by missing setup, not a gate)."""
    g = []
    reg = (b.get("regime") or {}).get("code")
    nw = b.get("news_window") or {}
    sp = b.get("spread") or {}
    if (nw.get("inside") and (nw.get("action") == "block" or nw.get("tier") in ("A", "B"))) \
            or nw.get("soon_block") or nw.get("soon_action") == "block":
        g.append("news")
    if sp.get("abnormal"):
        g.append("spread")
    if reg == "volatility_expansion":
        g.append("volatility")
    se = b.get("session_entry") or {}
    if se.get("blocked"):
        g.append("friday" if se.get("friday_window") else "session")
    return g

def candidate(cfg, at=None):
    """Re-run bias/regime/engine with every gate switched off, on the data brief.py just wrote."""
    import brief as BR, bias as BI, regime as REG
    from m5lib import LEVELS_JSON, META_JSON, load_json
    lv = load_json(LEVELS_JSON)
    meta = load_json(META_JSON, {}) or {}
    q = BR.quality_gate(meta)
    if not lv or not q.get("ok"):
        return None, None, None
    b = BI.compute(at, ignore_gates=True)
    reg = REG.classify(lv, win={}, spread={}, h4=b.get("h4"), h1=b.get("h1"), ignore_gates=True)
    dec = REG.decide(lv, b, reg, quality=q)
    dec, plan, sizing, _ = BR._apply_broker_gates(dec, lv, b, cfg, {"blocked": False})
    return dec, plan, sizing

def new_entry(now, plan, sizing, gates, offset=0.3):
    side = plan["side"]
    r = lambda x: round(float(x), 2)
    return {"id": f"{now:%Y%m%d-%H%M}-{side}", "at": now.strftime("%Y-%m-%d %H:%M"), "side": side,
            "entry": r(plan["entry"]), "sl": r(plan["sl"]), "tp": r(plan["tp"]), "offset": offset,
            "unit": ((sizing or {}).get("size") or {}).get("key"), "gates": gates, "status": "pending"}

def has_open(entries):
    return any(e.get("status") in ("pending", "open") for e in entries)

def _ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TEH)

def _close(e, status, price, t):
    d = 1 if e["side"] == "BUY" else -1
    move = d * (price - e["entry"])
    e.update(status=status, exit=round(price, 2), exit_at=t.strftime("%Y-%m-%d %H:%M"),
             R=round(move / abs(e["entry"] - e["sl"]), 2), toman=round(move * FULL_RATE - FEE))

def resolve(entries, bars, now, close_at=None):
    """bars: iterable of (open_time aware datetime, high, low, close) 1-minute BID bars, ascending.
    Only bars that are complete at `now` are used. Same-bar SL and TP -> SL (conservative).
    close_at: forced flat time (Friday close), aware datetime or None."""
    bars = [(t, h, l, c) for t, h, l, c in bars if t + timedelta(minutes=1) <= now]
    for e in entries:
        if e.get("status") not in ("pending", "open"):
            continue
        at = _ts(e["at"])
        buy = e["side"] == "BUY"
        fill_dead = at + timedelta(minutes=FILL_MIN)
        last = None
        for t, h, l, c in bars:
            if t < at:
                continue
            if e["status"] == "pending":
                if t >= fill_dead or (close_at and t >= close_at):
                    e.update(status="unfilled", exit_at=fill_dead.strftime("%Y-%m-%d %H:%M"), R=0.0, toman=0)
                    break
                if (l <= e["entry"]) if buy else (h >= e["entry"]):
                    e.update(status="open", filled_at=t.strftime("%Y-%m-%d %H:%M"))
                    if (l <= e["sl"]) if buy else (h >= e["sl"]):
                        _close(e, "sl", e["sl"], t); break
                    last = c
                continue
            filled = _ts(e["filled_at"])
            if t >= filled + timedelta(minutes=HOLD_MIN) or (close_at and t >= close_at):
                _close(e, "expired", last if last is not None else c, t); break
            if (l <= e["sl"]) if buy else (h >= e["sl"]):
                _close(e, "sl", e["sl"], t); break
            if (h >= e["tp"]) if buy else (l <= e["tp"]):
                _close(e, "tp", e["tp"], t); break
            last = c
        else:
            if e["status"] == "pending" and now >= fill_dead and bars and bars[-1][0] >= fill_dead - timedelta(minutes=1):
                e.update(status="unfilled", exit_at=fill_dead.strftime("%Y-%m-%d %H:%M"), R=0.0, toman=0)
    return entries

def summary(entries):
    done = [e for e in entries if e.get("status") in ("tp", "sl", "expired")]
    out = {k: sum(1 for e in entries if e.get("status") == k) for k in ("tp", "sl", "expired", "unfilled", "pending", "open")}
    out["R"] = round(sum(float(e.get("R") or 0) for e in done), 2)
    out["toman"] = round(sum(float(e.get("toman") or 0) for e in done))
    out["closed"] = len(done)
    return out

def m1_bars(since):
    """1-minute bid bars from data/xauusd_1m.parquet since an aware datetime."""
    import pandas as pd
    from m5lib import DATA
    d = pd.read_parquet(f"{DATA}/xauusd_1m.parquet", columns=["h_b", "l_b", "c_b"])
    d = d[d.index >= pd.Timestamp(since).tz_convert("UTC")]
    return [(t.to_pydatetime().astimezone(TEH), float(r.h_b), float(r.l_b), float(r.c_b)) for t, r in d.iterrows()]
