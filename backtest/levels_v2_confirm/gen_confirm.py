"""Wrapper: run the UNCHANGED levels_v2_build/gen_levels.snap() (-> tools/levels_v2.compute) for 2020-01-01..2024-12-31.
Only the data-load start/end and the snapshot date list differ from gen_levels.py (see PREREG_v2_confirm.md)."""
import sys, os, hashlib
sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/m5-gold-team/backtest/levels_v2_build'); sys.path.insert(0, '/workspace/m5-gold-team/tools')
import pandas as pd
from datetime import datetime, time as dtime
from multiprocessing import Pool
import gen_levels as G, m5lib
OUT = os.path.dirname(os.path.abspath(__file__))
for f, h in (('/workspace/m5-gold-team/tools/levels_v2.py', '9aaeb469c0baf4955529ab90af6fee4db27f365f3bdace93b811e85068e0f284'),
             ('/workspace/m5-gold-team/backtest/levels_v2_build/gen_levels.py', '9def4b23828e51b14a0b91c4c4bfcad6ed7c6b00293c4667030b53987cb23554')):
    assert hashlib.sha256(open(f, 'rb').read()).hexdigest() == h, f'hash mismatch {f}'

def load():  # same as gen_levels.load() except the date filter
    d = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet')
    d = d[~d.bad_quote & (d.ts_utc < pd.Timestamp('2025-01-02', tz='UTC'))]
    d = d.rename(columns={'bid_o':'o_b','bid_h':'h_b','bid_l':'l_b','bid_c':'c_b','ask_o':'o_a','ask_h':'h_a','ask_l':'l_a','ask_c':'c_a','bid_vol':'v_b','ask_vol':'v_a'})
    d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]')
    return d.set_index('ts_utc')[['o_b','h_b','l_b','c_b','v_b','o_a','h_a','l_a','c_a','v_a']].sort_index()

def times():  # same as gen_levels.times() except the range
    out = []
    for d in pd.date_range('2020-01-01', '2024-12-31', freq='D'):
        if d.weekday() >= 5: continue
        for hm in (dtime(11, 15), dtime(16, 15)):
            out.append(pd.Timestamp(datetime.combine(d.date(), hm), tz=m5lib.TEH).tz_convert('UTC'))
    return out

if __name__ == '__main__':
    G.H = load(); Ts = times(); print('candidate snapshots', len(Ts), flush=True)
    with Pool(5) as p: res = p.map(G.snap, Ts, chunksize=10)
    df = pd.DataFrame([x for r in res for x in r])
    ne = int(df['error'].notna().sum()) if 'error' in df else 0
    print('rows', len(df), 'snapshots', df.timestamp.nunique(), 'errors', ne)
    if ne: print(df[df.error.notna()].head()); df = df[df.error.isna()].drop(columns='error')
    df.to_csv(f'{OUT}/levels_v2_confirm_hist.csv', index=False)
    df['year'] = pd.to_datetime(df.timestamp, utc=True).dt.year
    print(df.score.value_counts().sort_index()); print(df.groupby('year').timestamp.nunique())
