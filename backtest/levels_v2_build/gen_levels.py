"""Point-in-time historical levels_v2 at brief times 11:15/16:15 Tehran, weekdays 2025-01-01..2026-10-30.
Same snapshot rules as levels_bias/rebuild.py (market open, last 1m bar <= 15 min old). Output levels_v2_hist.csv."""
import sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/m5-gold-team/tools')
import numpy as np, pandas as pd
from datetime import datetime, time as dtime
from multiprocessing import Pool
import m5lib, levels_v2 as LV2
OUT = os.path.dirname(os.path.abspath(__file__)); H = None

def load():
    d = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet')
    d = d[~d.bad_quote & (d.ts_utc >= pd.Timestamp('2024-11-15', tz='UTC'))]
    d = d.rename(columns={'bid_o':'o_b','bid_h':'h_b','bid_l':'l_b','bid_c':'c_b','ask_o':'o_a','ask_h':'h_a','ask_l':'l_a','ask_c':'c_a','bid_vol':'v_b','ask_vol':'v_a'})
    d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]')
    return d.set_index('ts_utc')[['o_b','h_b','l_b','c_b','v_b','o_a','h_a','l_a','c_a','v_a']].sort_index()

def snap(T):
    try:
        a, b = H.index.searchsorted(T - pd.Timedelta(days=24)), H.index.searchsorted(T)
        m1 = H.iloc[a:b]
        if b - a < 5000 or not m5lib.market_open(T) or m1.index[-1] < T - pd.Timedelta(minutes=15): return []
        r = LV2.compute(m1, T)
        return [{'timestamp': T, 'price_T': r['price_bid'], 'atr_m5': r['atr_m5'], 'tol': r['tol'], **l} for l in r['levels']]
    except Exception as e:
        return [{'timestamp': T, 'error': repr(e)}]

def times():
    out = []
    for d in pd.date_range('2025-01-01', '2026-10-30', freq='D'):
        if d.weekday() >= 5: continue
        for hm in (dtime(11, 15), dtime(16, 15)):
            out.append(pd.Timestamp(datetime.combine(d.date(), hm), tz=m5lib.TEH).tz_convert('UTC'))
    return out

if __name__ == '__main__':
    H = load(); Ts = times()
    if len(sys.argv) > 1: Ts = Ts[:int(sys.argv[1])]
    with Pool(6) as p: res = p.map(snap, Ts, chunksize=10)
    df = pd.DataFrame([x for r in res for x in r])
    print('rows', len(df), 'snapshots', df.timestamp.nunique(), 'errors', int(df['error'].notna().sum()) if 'error' in df else 0)
    if 'error' in df: print(df[df.error.notna()].head()); df = df[df.error.isna()].drop(columns='error')
    df.to_csv(f'{OUT}/levels_v2_hist.csv' if len(sys.argv) == 1 else f'{OUT}/levels_v2_hist_sample.csv', index=False)
    print(df.score.value_counts().sort_index())
