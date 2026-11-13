"""Point-in-time rebuild of tools/levels.py + tools/bias.py at each brief time (11:15 / 16:15 Tehran). See PREREG_levels_bias.md.
Reuses the team's code unchanged; only data loaders and news input are monkeypatched."""
import sys, json, os, pickle
import numpy as np, pandas as pd
from datetime import datetime, time as dtime
from multiprocessing import Pool
sys.dont_write_bytecode = True
sys.path.insert(0, "/workspace/m5-gold-team/tools")
import m5lib, levels as LV, bias as BI, fetch_xauusd as FX
OUT = os.path.dirname(os.path.abspath(__file__))
H = None

def load_hist():
    d = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet')
    d = d[~d.bad_quote]
    d = d.rename(columns={'bid_o':'o_b','bid_h':'h_b','bid_l':'l_b','bid_c':'c_b','ask_o':'o_a','ask_h':'h_a','ask_l':'l_a','ask_c':'c_a','bid_vol':'v_b','ask_vol':'v_a'})
    d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]')
    return d.set_index('ts_utc')[['o_b','h_b','l_b','c_b','v_b','o_a','h_a','l_a','c_a','v_a']].sort_index()

def snap(T):
    idx = H.index
    a, b = idx.searchsorted(T - pd.Timedelta(days=10)), idx.searchsorted(T)
    if b - a < 1000: return None
    m1 = H.iloc[a:b]
    if not m5lib.market_open(T) or m1.index[-1] < T - pd.Timedelta(minutes=15): return None
    bars = {'1m': m1, 'm5': FX.resample(m1, '5min'), 'm15': FX.resample(m1, '15min'), 'h1': FX.resample(m1, '1h')}
    meta = {'ok': True, 'stale': False, 'market_open': True}
    LV.load_bars = lambda tf: bars[tf]
    LV.load_json = lambda p, default=None: meta
    lv = LV.compute()
    BI.load_bars = lambda tf: bars[tf]
    BI.load_json = lambda p, default=None: lv if p == m5lib.LEVELS_JSON else meta
    BI.nw.load = lambda: {'windows': [], 'news_bias': None, 'source': None}
    b_ = BI.compute(T.tz_convert(m5lib.TEH).to_pydatetime())
    inv = b_.get('invalidation') or {}
    return dict(T=T, price=lv['price_bid'], atr=lv['atr_m5_14'], tol=lv['cluster_tol'],
                levels=[(l['price'], l['side'], l['strength'], l['score'], '|'.join(l['kinds'])) for l in lv['levels']],
                bias=b_['bias'], tech=b_['technical_bias'], conf=b_['technical_confidence'],
                h1=b_['h1']['trend'], h1s=b_['h1']['score'], m15=b_['m15']['trend'], m15s=b_['m15']['score'],
                inv_neutral=inv.get('neutral_level'), inv_off=inv.get('off_level'), verdict=b_['verdict']['code'])

def safe(T):
    try: return snap(T)
    except Exception as e: return {'T': T, 'error': repr(e)}

def times():
    out = []
    for d in pd.date_range('2020-01-02', '2026-10-30', freq='D'):
        if d.weekday() >= 5: continue
        for hm in (dtime(11, 15), dtime(16, 15)):
            out.append(pd.Timestamp(datetime.combine(d.date(), hm), tz=m5lib.TEH).tz_convert('UTC'))
    return out

if __name__ == '__main__':
    H = load_hist()
    Ts = times()
    if len(sys.argv) > 1: Ts = Ts[:int(sys.argv[1])]
    with Pool(6) as p: res = p.map(safe, Ts, chunksize=20)
    res = [r for r in res if r is not None]
    errs = [r for r in res if 'error' in r]
    print('snapshots', len(res), 'errors', len(errs), errs[:3])
    pickle.dump(res, open(f'{OUT}/snapshots.pkl', 'wb'))
