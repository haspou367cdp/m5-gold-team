"""Phase 4 replay driver (historical simulation). See PREREG.md for the frozen rules.

usage: python3 backtest/phase4/sim.py [--start 2020-01-02] [--end 2026-10-29] [--workers 7] [--out backtest/phase4/out]
"""
import argparse, json, os, sys, time
from datetime import date, datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/workspace/m5-gold-team/tools")
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

TEH = ZoneInfo("Asia/Tehran")
EQUITY = 2954400
RATE = {"full_unit": 80000, "half_unit": 40000}
UNIT = {"full_unit": "1U", "half_unit": "0.5U"}
FEE, SPREAD = 14000, 0.25
STOPOUT_LOSS = {"full_unit": 800000, "half_unit": 400000}
SLOTS = [(h, m) for h in range(7, 24) for m in (0, 15, 30, 45)] + [(0, 0), (0, 15)]

_M = None
_CFG = None


def _init(start, end, path=None):
    global _M, _CFG
    from data import load_hist, Market, HIST
    import broker_daryagold as DG
    s = (pd.Timestamp(start) - pd.Timedelta(days=70)).strftime("%Y-%m-%d")
    e = (pd.Timestamp(end) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    _M = Market(load_hist(path or HIST, start=s, end=e))
    _CFG = DG.load_config(equity=EQUITY)


def slot_times(d):
    """UTC instants (slot + 2 min) for the DaryaGold session that opens on Tehran date d."""
    out = []
    for h, m in SLOTS:
        day = d if h >= 7 else d + timedelta(days=1)
        lt = datetime(day.year, day.month, day.day, h, m, tzinfo=TEH) + timedelta(minutes=2)
        out.append(pd.Timestamp(lt).tz_convert("UTC"))
    return out


def session_close_utc(d):
    nd = d + timedelta(days=1)
    return pd.Timestamp(datetime(nd.year, nd.month, nd.day, 0, 30, tzinfo=TEH)).tz_convert("UTC")


def simulate_order(m1, sig, t, close_utc):
    """Limit order → fill → SL/TP (60 s rule) → exit. Forward walk over 1-minute bars from t (outcome only)."""
    side, E, SL, TP, key = sig["side"], sig["entry"], sig["sl"], sig["tp"], sig["unit"]
    d = 1 if side == "BUY" else -1
    rate = RATE[key]
    valid = min(t + pd.Timedelta(minutes=30), close_utc)
    idx = m1.index
    i0 = idx.searchsorted(t, "left")
    i_end = idx.searchsorted(close_utc, "left")
    i_val = idx.searchsorted(valid, "left")
    O, H, L, C = (m1[c].to_numpy()[i0:i_end] for c in ("o_b", "h_b", "l_b", "c_b"))
    res = {"filled": False, "tp_deferred": 0, "exit_type": None}
    nv = i_val - i0
    hit = np.nonzero(L[:nv] <= E)[0] if d > 0 else np.nonzero(H[:nv] >= E)[0]
    if not len(hit):
        res["end"] = valid
        return res
    f = int(hit[0])
    res.update(filled=True, fill_at=idx[i0 + f])
    so_move = (STOPOUT_LOSS[key] - FEE - SPREAD * rate) / rate     # adverse $ move that reaches the stop-out loss
    mfe = mae = 0.0
    exit_px, j = None, f
    for j in range(f, len(O)):
        hi, lo, op = H[j], L[j], O[j]
        fav = (hi - E) if d > 0 else (E - lo)
        adv = (E - lo) if d > 0 else (hi - E)
        sl_hit = (lo <= SL) if d > 0 else (hi >= SL)
        so_hit = adv >= so_move
        tp_touch = (hi >= TP) if d > 0 else (lo <= TP)
        tp_ok = tp_touch and j >= f + 2
        if tp_touch and not tp_ok and not sl_hit:
            res["tp_deferred"] += 1
        if sl_hit or so_hit:
            so_px = E - d * so_move
            sl_px = (min(op, SL) if d > 0 else max(op, SL)) if j > f else SL
            if so_hit and ((d > 0 and so_px >= sl_px) or (d < 0 and so_px <= sl_px)):
                exit_px, res["exit_type"] = so_px, "stop_out"
            else:
                exit_px, res["exit_type"] = sl_px, "sl"
            mae = max(mae, abs(exit_px - E))
            break
        mfe, mae = max(mfe, fav), max(mae, adv)
        if tp_ok:
            exit_px, res["exit_type"] = TP, "tp"
            break
    if exit_px is None:          # daily close (or end of data): the owner closes at the last bar's close
        if not len(C):
            return dict(res, filled=False, end=valid)
        j = len(C) - 1
        exit_px, res["exit_type"] = float(C[j]), "close"
    res["exit_at"] = idx[i0 + j]
    gross = (exit_px - E) * d * rate
    risk = abs(E - SL) * rate + SPREAD * rate + FEE
    net = gross - SPREAD * rate - FEE
    risk50 = abs(E - SL) * rate + 0.50 * rate + FEE
    res.update(exit=round(float(exit_px), 3), gross=round(gross), net=round(net), risk=round(risk), R=net / risk,
               net_s50=round(gross - 0.50 * rate - FEE), R_s50=(gross - 0.50 * rate - FEE) / risk50,
               mfe_R=mfe * rate / risk, mae_R=mae * rate / risk, end=res["exit_at"] + pd.Timedelta(minutes=1),
               hold_min=float((res["exit_at"] - res["fill_at"]).total_seconds() / 60 + 1))
    return res


def run_day(d):
    """One DaryaGold session. Days are independent: positions end at the 00:30 close, equity is fixed."""
    import engine as E
    M, cfg = _M, _CFG
    close = session_close_utc(d)
    busy_until = None
    losses, net_day, stopped, stop_hit = 0, 0, False, False
    sent = set()
    rows, evals = [], 0
    for t in slot_times(d):
        if t >= close or stopped or (busy_until is not None and t < busy_until):
            continue
        m1 = M.m1_at(t)
        if not len(m1) or (t - m1.index[-1]) > pd.Timedelta(minutes=11):
            continue                          # stale / closed market
        evals += 1
        try:
            ev = E.evaluate(M, t, cfg)
        except Exception as e:                # a crash in the live code = no signal at that run
            rows.append({"day": str(d), "t": str(t), "error": f"{type(e).__name__}: {str(e)[:80]}"})
            continue
        if ev["status"] not in ("APPROVED", "APPROVED_WITH_WARNING"):
            continue
        key = (ev["side"], round(ev["entry"] * 2) / 2, round(ev["sl"] * 2) / 2)
        if key in sent:
            continue
        sent.add(key)
        r = simulate_order(M.m1, ev, t, close)
        busy_until = r["end"]
        row = {"day": str(d), "t_teh": ev["t"], "engine": ev["engine"], "regime": ev["regime"], "side": ev["side"],
               "unit": UNIT[ev["unit"]], "entry": ev["entry"], "sl": ev["sl"], "tp": ev["tp"], "net_rr": ev["net_rr"],
               "status": ev["status"], **{k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in r.items()}}
        rows.append(row)
        if r["filled"]:
            net_day += r["net"]
            if r["net"] < 0:
                losses += 1
            if losses >= 3 or -net_day >= 0.2 * EQUITY:
                stopped = stop_hit = True
    return {"day": str(d), "evals": evals, "stop_hit": stop_hit, "rows": rows}


def days_between(start, end):
    d, e = date.fromisoformat(start), date.fromisoformat(end)
    while d <= e:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def run_month(m, ds, path=None):
    _init(ds[0].isoformat(), ds[-1].isoformat(), path)
    return [run_day(d) for d in ds]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-02")
    ap.add_argument("--end", default="2026-10-29")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    months = {}
    for d in days_between(a.start, a.end):
        months.setdefault(d.strftime("%Y-%m"), []).append(d)
    todo = {m: ds for m, ds in months.items() if not os.path.exists(os.path.join(a.out, f"{m}.json"))}   # resumable
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_month, m, ds): m for m, ds in todo.items()}
        for n, f in enumerate(as_completed(futs), 1):
            m = futs[f]
            with open(os.path.join(a.out, f"{m}.json"), "w") as fh:
                json.dump(f.result(), fh)
            print(f"{m} done ({n}/{len(todo)}) {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
