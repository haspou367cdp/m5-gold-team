"""Cost-aware report from a freqtrade backtest export: net $ per 1U = gross - 0.425; toman = x80,000."""
import sys, json, numpy as np, pandas as pd
from freqtrade.data.btanalysis import load_backtest_data, get_latest_backtest_filename
COST, TOM = 0.425, 80000
TEH = 'Asia/Tehran'

def stats(t):
    if len(t) == 0:
        return dict(trades=0)
    sgn = np.where(t.is_short, -1, 1)
    net = (t.close_rate - t.open_rate) * sgn - COST
    gp, gl = net[net > 0].sum(), -net[net <= 0].sum()
    eq = (net * TOM).cumsum(); dd = (eq.cummax().clip(lower=0) - eq).max()
    dur = (pd.to_datetime(t.close_date) - pd.to_datetime(t.open_date)).dt.total_seconds() / 60
    return dict(trades=len(t), win=round((net > 0).mean() * 100, 1), pf=round(gp / gl, 2) if gl > 0 else np.inf,
                net_toman=int(net.sum() * TOM), avg_toman=int(net.mean() * TOM), maxdd_toman=int(dd),
                avg_hold_min=round(dur.mean(), 1), sl_exits=int((t.exit_reason.str.contains('stop')) .sum()),
                roi=int((t.exit_reason == 'roi').sum()), time=int((t.exit_reason == 'time_stop').sum()))

def load(path, strat):
    from pathlib import Path
    p = Path(path)
    if p.is_dir():
        for f in sorted(p.glob('backtest-result-*.zip'), reverse=True):
            try:
                t = load_backtest_data(f, strat); break
            except Exception:
                continue
        else:
            raise ValueError(f'{strat} not found in {path}')
    else:
        t = load_backtest_data(p, strat)
    t = t.sort_values('open_date').reset_index(drop=True)
    t['month'] = pd.to_datetime(t.open_date).dt.tz_convert(TEH).dt.strftime('%Y-%m')
    return t

if __name__ == '__main__':
    path = sys.argv[1]
    strats = sys.argv[2:]
    rows = []
    for s in strats:
        t = load(path, s)
        r = stats(t); r['strategy'] = s; rows.append(r)
    print(pd.DataFrame(rows).set_index('strategy').to_string())
