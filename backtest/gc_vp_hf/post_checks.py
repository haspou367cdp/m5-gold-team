"""Post-hoc descriptive checks (NOT pre-registered decisions; reported as context only)."""
import sys; sys.dont_write_bytecode = True
import numpy as np, pandas as pd
Q = pd.read_csv('trades_gc_vp.csv', parse_dates=['T', 'entry_ts']); SEED, REPS = 20261113, 5000
def boot_two(a, b, key='day'):
    rng = np.random.default_rng(SEED); keys = sorted(set(a[key]) | set(b[key])); di = {x: i for i, x in enumerate(keys)}
    def agg(x):
        s = np.zeros(len(keys)); n = np.zeros(len(keys)); ii = [di[v] for v in x[key]]; np.add.at(s, ii, x.R_net.values); np.add.at(n, ii, 1); return s, n
    sa, na = agg(a); sb, nb = agg(b); m = len(keys); ds = np.empty(REPS)
    for r in range(REPS):
        w = np.bincount(rng.integers(0, m, m), minlength=m); ds[r] = (w*sa).sum()/(w*na).sum() - (w*sb).sum()/(w*nb).sum()
    return sa.sum()/na.sum() - sb.sum()/nb.sum(), float((ds <= 0).mean())
for src in ('gc', 'lvpy'):
    for hyp in ('rev', 'cont'):
        t = Q[(Q.src == src) & (Q.hyp == hyp)]; lv, ct = t[t.kind == 'level'], t[t.kind == 'control']
        d, p = boot_two(lv, ct)
        P = pd.read_csv(f'pairs_{src}_{hyp}.csv', index_col=0); unp = lv[~lv.pair.isin(P.index)]; unc = ct[~ct.pair.isin(P.index)]
        # dedupe identical level entries (same entry time + direction sign of gross path) within source
        dd = lv.drop_duplicates(['entry_ts', 'side'])
        print(f'{src} {hyp}: UNPAIRED lv n={len(lv)} {lv.R_net.mean():.3f} ct n={len(ct)} {ct.R_net.mean():.3f} diff={d:.3f} p_day={p:.4f} | '
              f'level trades without traded control n={len(unp)} mean={unp.R_net.mean():.3f}; control trades without traded level n={len(unc)} mean={unc.R_net.mean():.3f} | '
              f'distinct days in pairs {P.day.nunique()} | level trades dedup by entry {len(dd)} mean {dd.R_net.mean():.3f}')
