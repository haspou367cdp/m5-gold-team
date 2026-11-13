"""Generate levels_v2 with (a) Dukascopy tick volume (frozen, unchanged) and (b) COMEX GC_F26 1m volume, on the same snapshots.
levels_v2.py is NOT modified: variant (b) only swaps levels_v2.vprofile for a wrapper that builds the identical profile
(typical-price $0.5 bins, 70% value area, >=30 bars) from GC bars in the same time segment, shifted to spot by a basis.
See PREREG_v2gc.md."""
import sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/m5-gold-team/tools'); sys.path.insert(0, '/workspace/m5-gold-team/backtest/levels_v2_build')
import numpy as np, pandas as pd
import m5lib, levels_v2 as LV2, gen_levels as GL
OUT = os.path.dirname(os.path.abspath(__file__))
GCF = '/workspace/m5-gold-team/data/gc_volume_sample/firstratedata_sample/GC_F26_1min.csv'
END = pd.Timestamp('2025-12-27', tz='UTC')      # before Jan-26 delivery period (first notice ~2025-12-30)
ORIG_VP = LV2.vprofile

def load_gc():
    d = pd.read_csv(GCF, header=None, names=['t', 'o', 'h', 'l', 'c', 'v'])
    d['t'] = pd.to_datetime(d.t).dt.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC')
    return d.dropna(subset=['t']).set_index('t').sort_index()

G = load_gc(); LOG = []

def vprofile_gc(seg):
    """seg = spot 1m slice used by levels_v2 for this profile. Use GC bars inside [seg start, seg end]."""
    if len(seg) < 30: return None
    a, b = seg.index[0], seg.index[-1]
    g = G[(G.index >= a) & (G.index <= b)]
    j = g.index.intersection(seg.index)
    if len(g) < 30 or len(j) < 20: LOG.append((a, b, len(g), len(j), None)); return None
    basis = float(np.median(g.loc[j, 'c'].values - seg.loc[j, 'c_b'].values))   # GC - spot bid, same minutes, same segment
    LOG.append((a, b, len(g), len(j), basis))
    x = pd.DataFrame({'h_b': g.h - basis, 'l_b': g.l - basis, 'c_b': g.c - basis, 'v_b': g.v.astype(float), 'v_a': 0.0}, index=g.index)
    return ORIG_VP(x)

def eligible_times():
    ny = G.index.tz_convert('America/New_York'); td = pd.Series((ny + pd.Timedelta(hours=6)).date, index=G.index)
    n = td.value_counts()
    out = []
    for T in GL.times():
        if T >= END: continue
        d0 = m5lib.trading_day_start(T); dp = m5lib.previous_trading_day_start(d0)
        key = (dp.tz_convert('America/New_York') + pd.Timedelta(hours=6)).date()
        if n.get(key, 0) >= 200: out.append(T)
    return out

def run(T, variant):
    LV2.vprofile = vprofile_gc if variant == 'gc' else ORIG_VP
    return GL.snap(T)

if __name__ == '__main__':
    GL.H = GL.load(); Ts = eligible_times(); print('eligible snapshots', len(Ts), Ts[0], Ts[-1])
    for variant in ('tick', 'gc'):
        rows = [x for T in Ts for x in run(T, variant)]
        df = pd.DataFrame(rows)
        if 'error' in df: print(variant, 'errors', df.error.notna().sum()); df = df[df.error.isna()].drop(columns='error')
        df.to_csv(f'{OUT}/{variant}/levels_v2_hist.csv', index=False)
        print(variant, 'rows', len(df), 'snapshots', df.timestamp.nunique(), df.score.value_counts().sort_index().to_dict())
    pd.DataFrame(LOG, columns=['seg_start', 'seg_end', 'gc_bars', 'matched_min', 'basis']).to_csv(f'{OUT}/basis_log.csv', index=False)
