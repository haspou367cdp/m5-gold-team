"""Evaluator for PREREG_v2.md. Outcome logic copied from levels_bias/evaluate.py Q1."""
import sys, os
sys.dont_write_bytecode = True
import numpy as np, pandas as pd
from scipy.stats import norm
OUT = os.path.dirname(os.path.abspath(__file__))
OOS0 = pd.Timestamp('2025-07-01', tz='UTC'); Y26 = pd.Timestamp('2026-01-01', tz='UTC')

def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k/n; den = 1+z*z/n; c = (p+z*z/(2*n))/den; h = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (c-h, c+h)

def bars():
    d = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet', columns=['ts_utc','bid_h','bid_l','bid_c','bad_quote'])
    d = d[~d.bad_quote & (d.ts_utc >= pd.Timestamp('2024-12-20', tz='UTC'))]; d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]'); d = d.set_index('ts_utc')
    m5 = d.resample('5min', label='left', closed='left').agg({'bid_h':'max','bid_l':'min','bid_c':'last'}).dropna()
    m15 = d.bid_c.resample('15min', label='left', closed='left').last().dropna()
    return m5, m15

def main():
    L = pd.read_csv(f'{OUT}/levels_v2_hist.csv', parse_dates=['timestamp'])
    m5, m15 = bars()
    t5 = m5.index.values.astype(np.int64); H5 = m5.bid_h.values; L5 = m5.bid_l.values; end5 = t5 + 5*60*10**9
    m15c = pd.Series(m15.values, index=m15.index + pd.Timedelta('15min'))
    br = m15c.reindex(pd.DatetimeIndex(end5, tz='UTC')).values
    rows = []
    def test(T, p, side, atr, kind, meta):
        Tn = T.value; s = np.searchsorted(t5, Tn); e = np.searchsorted(t5, Tn + 4*3600*10**9)
        if s >= e: return
        hit = (H5[s:e] >= p) if side == 'resistance' else (L5[s:e] <= p)
        if not hit.any(): rows.append({**meta, 'kind': kind, 'touched': False}); return
        k = s + int(np.argmax(hit)); ke = min(np.searchsorted(t5, t5[k] + 2*3600*10**9), len(t5))
        if side == 'resistance': rev = L5[k:ke] <= p - atr; brk = br[k:ke] > p
        else: rev = H5[k:ke] >= p + atr; brk = br[k:ke] < p
        ir = int(np.argmax(rev)) if rev.any() else 10**9; ib = int(np.argmax(brk)) if brk.any() else 10**9
        out = 'neither' if ir == ib == 10**9 else ('break' if ib <= ir else 'reversal')
        rows.append({**meta, 'kind': kind, 'touched': True, 'outcome': out})
    for T, g in L.groupby('timestamp'):
        price, atr, tol = g.price_T.iloc[0], g.atr_m5.iloc[0], g.tol.iloc[0]; lp = g.price.values
        per = 'IS' if T < OOS0 else 'OOS'; sub = 'IS_2025H1' if T < OOS0 else ('2025H2' if T < Y26 else '2026')
        for i, l in enumerate(g.itertuples()):
            dist = l.price - price
            if abs(dist) < 0.3*atr: continue
            b = 'high' if l.score >= 4 else 'watch' if l.score == 3 else 'low'
            meta = dict(T=T, day=T.date(), period=per, sub=sub, score=l.score, bucket=b, side=l.side, pair=f'{T.value}_{i}')
            test(T, l.price, l.side, atr, 'level', meta)
            for kk in (1, -1, 2, -2, 3, -3):
                cd = dist*(1+0.15*kk); cp = price + cd
                if abs(cd) < 0.3*atr or np.min(np.abs(lp - cp)) <= tol: continue
                r5 = cp/5.0
                if abs(r5 - round(r5))*5 <= tol: continue
                test(T, cp, l.side, atr, 'control', meta); break
    Q = pd.DataFrame(rows); Q.to_csv(f'{OUT}/touches_v2.csv', index=False)
    return Q

def tab(Q, keys):
    t = Q[Q.touched]; out = []
    for k, g in t.groupby(keys):
        lv, ct = g[g.kind == 'level'], g[g.kind == 'control']
        n1, k1 = len(lv), int((lv.outcome == 'reversal').sum()); n2, k2 = len(ct), int((ct.outcome == 'reversal').sum())
        if n1 == 0 or n2 == 0: continue
        p1, p2 = k1/n1, k2/n2; pp = (k1+k2)/(n1+n2); se = np.sqrt(pp*(1-pp)*(1/n1+1/n2))
        z = (p1-p2)/se if se > 0 else 0; c1, c2 = wilson(k1, n1), wilson(k2, n2)
        out.append({**dict(zip(keys if isinstance(keys, list) else [keys], k if isinstance(k, tuple) else (k,))),
                    'n_touch': n1, 'reversal%': round(100*p1, 1), 'rev_CI95': f'{100*c1[0]:.1f}-{100*c1[1]:.1f}',
                    'ctrl_n': n2, 'ctrl_rev%': round(100*p2, 1), 'ctrl_CI95': f'{100*c2[0]:.1f}-{100*c2[1]:.1f}',
                    'diff_pp': round(100*(p1-p2), 1), 'p_two_sided_z': round(2*norm.sf(abs(z)), 4)})
    return pd.DataFrame(out)

def boot(a, b, reps=5000, seed=20261113):
    """Day-clustered bootstrap of rev%(a) - rev%(b); a, b touched rows. Returns diff, one-sided p (diff<=0)."""
    rng = np.random.default_rng(seed)
    days = np.array(sorted(set(a.day) | set(b.day)), dtype=object); di = {d: i for i, d in enumerate(days)}
    def agg(x):
        r = np.zeros(len(days)); n = np.zeros(len(days))
        np.add.at(n, [di[d] for d in x.day], 1); np.add.at(r, [di[d] for d in x.day], (x.outcome == 'reversal').values)
        return r, n
    ra, na = agg(a); rb, nb = agg(b); obs = ra.sum()/na.sum() - rb.sum()/nb.sum(); ds = []
    for _ in range(reps):
        w = np.bincount(rng.integers(0, len(days), len(days)), minlength=len(days))
        ds.append((w*ra).sum()/(w*na).sum() - (w*rb).sum()/(w*nb).sum())
    ds = np.array(ds); return 100*obs, float((ds <= 0).mean()), (100*np.percentile(ds, 2.5), 100*np.percentile(ds, 97.5))

if __name__ == '__main__':
    Q = main(); t = Q[Q.touched]
    T1 = tab(Q, ['period', 'bucket']); T2 = tab(Q, ['sub', 'bucket']); T3 = tab(Q, ['period', 'score']); T4 = tab(Q, ['period', 'bucket', 'side'])
    for nm, x in (('period_bucket', T1), ('sub_bucket', T2), ('period_score', T3), ('period_bucket_side', T4)):
        x.to_csv(f'{OUT}/tab_{nm}.csv', index=False); print(f'\n## {nm}\n', x.to_markdown(index=False))
    oos = t[t.period == 'OOS']; hi = oos[oos.bucket == 'high']
    h1 = boot(hi[hi.kind == 'level'], hi[hi.kind == 'control'])
    h2 = boot(hi[hi.kind == 'level'], oos[(oos.bucket == 'low') & (oos.kind == 'level')])
    print('\nH1 OOS high vs control: diff %.2f pp, p_one_sided %.4f, CI %s' % (h1[0], h1[1], h1[2]))
    print('H2 OOS high vs low levels: diff %.2f pp, p_one_sided %.4f, CI %s' % (h2[0], h2[1], h2[2]))
    print('n OOS high touched levels', int((hi.kind == 'level').sum()))
    print('eligible levels', int((Q.kind == 'level').sum()), 'touched', int(((Q.kind == 'level') & Q.touched).sum()),
          'controls', int((Q.kind == 'control').sum()), 'touched', int(((Q.kind == 'control') & Q.touched).sum()))
