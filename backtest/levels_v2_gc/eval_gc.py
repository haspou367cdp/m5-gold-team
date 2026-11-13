"""Eval for PREREG_v2gc.md: reuses levels_v2_build/evaluate_v2.py outcome/control code unchanged (OUT redirected)."""
import sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/m5-gold-team/backtest/levels_v2_build')
import numpy as np, pandas as pd
import evaluate_v2 as EV
OUT = os.path.dirname(os.path.abspath(__file__))

def paired(Q, bucket='high'):
    q = Q[Q.bucket == bucket]
    l = q[(q.kind == 'level') & q.touched].set_index('pair'); c = q[(q.kind == 'control') & q.touched].set_index('pair')
    k = l.index.intersection(c.index); l, c = l.loc[k].reset_index(), c.loc[k].reset_index()
    return l, c

def boot(l, c, reps=5000, seed=20261113):
    d = (l.outcome == 'reversal').astype(int).values - (c.outcome == 'reversal').astype(int).values
    if len(d) == 0: return np.nan, np.nan, (np.nan, np.nan), 0
    u, inv = np.unique(l.day.astype(str).values, return_inverse=True); s = np.bincount(inv, weights=d); n = np.bincount(inv)
    rng = np.random.default_rng(seed); bs = []
    for _ in range(reps):
        w = np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u)); bs.append((w*s).sum()/max((w*n).sum(), 1))
    bs = np.array(bs); return 100*d.mean(), float((bs <= 0).mean()), tuple(np.percentile(bs, [2.5, 97.5])*100), len(d)

if __name__ == '__main__':
    R = {}
    for v in ('tick', 'gc'):
        EV.OUT = f'{OUT}/{v}'; Q = EV.main(); R[v] = Q
        T = EV.tab(Q, ['bucket']); T.to_csv(f'{OUT}/{v}/tab_bucket.csv', index=False); print(f'\n## {v} unpaired by bucket\n', T.to_markdown(index=False))
        for b in ('high', 'watch', 'low'):
            l, c = paired(Q, b); r = boot(l, c)
            print(f'{v} PAIRED {b}: n={r[3]} level {100*(l.outcome=="reversal").mean():.1f}% ctrl {100*(c.outcome=="reversal").mean():.1f}% diff {r[0]:.2f}pp p1 {r[1]:.4f} CI {r[2][0]:.1f}..{r[2][1]:.1f}')
        l, c = paired(Q, 'high'); mid = pd.Timestamp('2025-12-01')
        for nm, m in (('before Dec', pd.to_datetime(l['T']).dt.tz_localize(None) < mid), ('Dec', pd.to_datetime(l['T']).dt.tz_localize(None) >= mid)):
            r = boot(l[m.values], c[m.values]); print(f'{v} PAIRED high {nm}: n={r[3]} diff {r[0]:.2f}pp')
    p_gc = boot(*paired(R['gc'], 'high'))[1]; p_prev = 0.0878
    ps = sorted([('v2gc', p_gc), ('v2_quick', p_prev)], key=lambda x: x[1])
    holm = {ps[0][0]: min(1, 2*ps[0][1])}; holm[ps[1][0]] = max(holm[ps[0][0]], min(1, ps[1][1]))
    print('\nHolm-adjusted one-sided p:', holm)
    # GC minus tick paired-diff (diff-in-diff), descriptive
    lg, cg = paired(R['gc']); lt, ct = paired(R['tick'])
    print(f"diff-in-diff (gc paired diff - tick paired diff): {boot(lg, cg)[0]-boot(lt, ct)[0]:.2f} pp")
