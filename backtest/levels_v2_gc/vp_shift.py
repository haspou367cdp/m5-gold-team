"""Median $ distance between GC-volume and tick-volume POC/VAH/VAL on the same profile segments (descriptive)."""
import sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/m5-gold-team/backtest/levels_v2_gc'); sys.path.insert(0, '/workspace/m5-gold-team/tools')
import numpy as np, pandas as pd, m5lib
import gen_gc as GG, gen_levels as GL
GL.H = GL.load(); rows = []
for T in GG.eligible_times():
    d0 = m5lib.trading_day_start(T); dp = m5lib.previous_trading_day_start(d0)
    for tag, a, b in (('prev', dp, d0), ('dev', d0, T)):
        seg = GL.H[(GL.H.index >= a) & (GL.H.index < b) & (GL.H.index < T)]
        t, g = GG.ORIG_VP(seg), GG.vprofile_gc(seg)
        if t and g: rows.append({'T': T, 'seg': tag, **{f'd_{k}': abs(g[k]-t[k]) for k in ('POC', 'VAH', 'VAL')}})
D = pd.DataFrame(rows); D.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vp_shift.csv'), index=False)
print('profiles compared', len(D)); print(D.groupby('seg')[['d_POC', 'd_VAH', 'd_VAL']].median().round(2)); print('all', D[['d_POC', 'd_VAH', 'd_VAL']].median().round(2).to_dict())
b = pd.DataFrame(GG.LOG, columns=['a', 'b', 'n', 'j', 'basis']).dropna(); print('basis $: median', round(b.basis.median(), 2), 'IQR', b.basis.quantile([.25, .75]).round(2).tolist(), 'min/max', round(b.basis.min(), 2), round(b.basis.max(), 2))
