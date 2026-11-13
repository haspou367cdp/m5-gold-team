"""Evaluator for PREREG_v2_confirm.md (levels_v2 2020-2024 confirmation, primary = paired net R of a fixed fade rule).
Touch/reversal/break logic copied from levels_v2_build/evaluate_v2.py test(). Controls: same as evaluate_v2.py minus the $5 exclusion."""
import sys, os
sys.dont_write_bytecode = True
import numpy as np, pandas as pd
OUT = os.path.dirname(os.path.abspath(__file__))
SEED, REPS = 20261113, 5000
SLIP_RT, FLAT_RT = 0.20, 0.50
NS = 10**9; M5NS = 5*60*NS

def bars():
    d = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet', columns=['ts_utc','bid_h','bid_l','bid_c','spread_c','bad_quote'])
    d = d[~d.bad_quote & (d.ts_utc >= pd.Timestamp('2019-12-01', tz='UTC')) & (d.ts_utc < pd.Timestamp('2025-01-03', tz='UTC'))]
    d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]'); d = d.set_index('ts_utc').sort_index()
    m5 = d.resample('5min', label='left', closed='left').agg({'bid_h':'max','bid_l':'min','bid_c':'last'}).dropna()
    m15 = d.bid_c.resample('15min', label='left', closed='left').last().dropna()
    h1 = d.bid_c.resample('1h', label='left', closed='left').last().dropna()
    return d, m5, m15, h1

def trade(j0, je, p, side, atr, H1, L1, C1):
    """Fade at level p from 1m index j0 through je (inclusive). Returns gross PnL ($), exit idx, exit type, MAE, MFE ($)."""
    h, l = H1[j0:je+1], L1[j0:je+1]
    if side == 'resistance':  # short
        stop, tgt = p + atr, p - 1.5*atr; hs = h >= stop; ht = l <= tgt
    else:                      # long
        stop, tgt = p - atr, p + 1.5*atr; hs = l <= stop; ht = h >= tgt
    ht = ht.copy(); ht[0] = False          # entry bar: only stop checked
    i_s = int(np.argmax(hs)) if hs.any() else 10**9; i_t = int(np.argmax(ht)) if ht.any() else 10**9
    if i_s == i_t == 10**9: ie, typ, ex = je - j0, 'time', C1[je]
    elif i_s <= i_t: ie, typ, ex = i_s, 'stop', stop   # same bar -> stop
    else: ie, typ, ex = i_t, 'target', tgt
    hh, ll = h[:ie+1], l[:ie+1]
    if side == 'resistance': g = p - ex; mae = hh.max() - p; mfe = p - ll.min()
    else: g = ex - p; mae = p - ll.min(); mfe = hh.max() - p
    return g, j0 + ie, typ, max(mae, 0.0), max(mfe, 0.0)

def main():
    L = pd.read_csv(f'{OUT}/levels_v2_confirm_hist.csv', parse_dates=['timestamp'])
    d, m5, m15, h1 = bars()
    t1 = d.index.values.astype(np.int64); H1 = d.bid_h.values; L1 = d.bid_l.values; C1 = d.bid_c.values; SP = d.spread_c.values
    t5 = m5.index.values.astype(np.int64); H5 = m5.bid_h.values; L5 = m5.bid_l.values; end5 = t5 + M5NS
    m15c = pd.Series(m15.values, index=m15.index + pd.Timedelta('15min'))
    br = m15c.reindex(pd.DatetimeIndex(end5, tz='UTC')).values
    h1c = pd.Series(h1.values, index=h1.index + pd.Timedelta('1h'))  # indexed by completion time
    # snapshot state: ATR tercile within year, H1 EMA20 vs EMA50 trend (completed H1 bars, last 12 days before T)
    S = L.groupby('timestamp').atr_m5.first().reset_index(); S['year'] = S.timestamp.dt.year
    S['atr_tercile'] = S.groupby('year').atr_m5.transform(lambda x: pd.qcut(x.rank(method='first'), 3, labels=[1, 2, 3]).astype(int))
    tr = []
    for T in S.timestamp:
        x = h1c[(h1c.index <= T) & (h1c.index > T - pd.Timedelta(days=12))]
        tr.append('up' if x.ewm(span=20, adjust=False).mean().iloc[-1] > x.ewm(span=50, adjust=False).mean().iloc[-1] else 'down')
    S['trend'] = tr; state = S.set_index('timestamp')[['atr_tercile', 'trend']].to_dict('index')
    rows = []
    def test(T, p, side, atr, kind, meta):
        Tn = T.value; s = np.searchsorted(t5, Tn); e = np.searchsorted(t5, Tn + 4*3600*NS)
        if s >= e: return
        hit = (H5[s:e] >= p) if side == 'resistance' else (L5[s:e] <= p)
        if not hit.any(): rows.append({**meta, 'kind': kind, 'lvl': p, 'touched': False}); return
        k = s + int(np.argmax(hit)); ke = min(np.searchsorted(t5, t5[k] + 2*3600*NS), len(t5))
        if side == 'resistance': rev = L5[k:ke] <= p - atr; brk = br[k:ke] > p
        else: rev = H5[k:ke] >= p + atr; brk = br[k:ke] < p
        ir = int(np.argmax(rev)) if rev.any() else 10**9; ib = int(np.argmax(brk)) if brk.any() else 10**9
        out = 'neither' if ir == ib == 10**9 else ('break' if ib <= ir else 'reversal')
        bfail = np.nan
        if ib < 10**9:
            after = (L5[k+ib+1:ke] <= p - atr) if side == 'resistance' else (H5[k+ib+1:ke] >= p + atr)
            bfail = bool(after.any())
        # trade on 1m
        a1, b1 = np.searchsorted(t1, t5[k]), np.searchsorted(t1, t5[k] + M5NS)
        w = (H1[a1:b1] >= p) if side == 'resistance' else (L1[a1:b1] <= p)
        j0 = a1 + int(np.argmax(w)) if w.any() else a1   # w.any() must hold (M5 high = max of 1m highs)
        kt = min(k + 24, len(t5) - 1); je = np.searchsorted(t1, t5[kt] + M5NS) - 1
        g, jx, typ, mae, mfe = trade(j0, je, p, side, atr, H1, L1, C1)
        sp = float(SP[j0]); net = g - sp - SLIP_RT; netf = g - FLAT_RT
        rows.append({**meta, 'kind': kind, 'lvl': p, 'touched': True, 'outcome': out, 'bars_to_rev': ir if ir < 10**9 else np.nan,
                     'had_break': ib < 10**9, 'break_fail': bfail, 'entry_ts': pd.Timestamp(t1[j0], tz='UTC'),
                     'exit_ts': pd.Timestamp(t1[jx], tz='UTC'), 'exit_type': typ, 'spread_entry': sp, 'gross_usd': g,
                     'net_usd': net, 'R_gross': g/atr, 'R_net': net/atr, 'R_net_flat': netf/atr, 'MAE_atr': mae/atr, 'MFE_atr': mfe/atr,
                     'entry_1m_found': bool(w.any())})
    nocontrol = 0
    for T, g in L.groupby('timestamp'):
        price, atr, tol = g.price_T.iloc[0], g.atr_m5.iloc[0], g.tol.iloc[0]; lp = g.price.values; st = state[T]
        for i, l in enumerate(g.itertuples()):
            dist = l.price - price
            if abs(dist) < 0.3*atr: continue
            b = 'high' if l.score >= 4 else 'watch' if l.score == 3 else 'low'
            meta = dict(T=T, day=T.date(), week=f'{T.isocalendar()[0]}-{T.isocalendar()[1]:02d}', year=T.year, score=l.score,
                        bucket=b, side=l.side, atr=atr, atr_tercile=st['atr_tercile'], trend=st['trend'], pair=f'{T.value}_{i}')
            test(T, l.price, l.side, atr, 'level', meta)
            found = False
            for kk in (1, -1, 2, -2, 3, -3):
                cd = dist*(1+0.15*kk); cp = price + cd
                if abs(cd) < 0.3*atr or np.min(np.abs(lp - cp)) <= tol: continue
                test(T, cp, l.side, atr, 'control', meta); found = True; break
            if not found: nocontrol += 1
    Q = pd.DataFrame(rows); Q.to_csv(f'{OUT}/touches_confirm.csv', index=False)
    return Q, nocontrol

def paired(Q, bucket='high', col='R_net'):
    t = Q[Q.touched & (Q.bucket == bucket)]
    lv = t[t.kind == 'level'].set_index('pair'); ct = t[t.kind == 'control'].set_index('pair')
    ix = lv.index.intersection(ct.index)
    P = lv.loc[ix, ['day', 'week', 'year', 'side', 'atr_tercile', 'trend', col]].rename(columns={col: 'lv'}); P['ct'] = ct.loc[ix, col]
    return P

def boot_paired(P, key, reps=REPS, seed=SEED):
    rng = np.random.default_rng(seed); g = P.groupby(key).agg(sl=('lv', 'sum'), sc=('ct', 'sum'), n=('lv', 'size'))
    sl, sc, n = g.sl.values, g.sc.values, g.n.values; m = len(g); obs = (sl.sum() - sc.sum())/n.sum(); ds = np.empty(reps)
    for r in range(reps):
        w = np.bincount(rng.integers(0, m, m), minlength=m); ds[r] = ((w*sl).sum() - (w*sc).sum())/(w*n).sum()
    return obs, float((ds <= 0).mean()), np.percentile(ds, [2.5, 97.5])

def boot_two(a, b, key='day', col='R_net', reps=REPS, seed=SEED):
    rng = np.random.default_rng(seed); keys = np.array(sorted(set(a[key]) | set(b[key])), dtype=object); di = {x: i for i, x in enumerate(keys)}
    def agg(x):
        s = np.zeros(len(keys)); n = np.zeros(len(keys)); ii = [di[v] for v in x[key]]
        np.add.at(s, ii, x[col].values); np.add.at(n, ii, 1); return s, n
    sa, na = agg(a); sb, nb = agg(b); obs = sa.sum()/na.sum() - sb.sum()/nb.sum(); ds = np.empty(reps); m = len(keys)
    for r in range(reps):
        w = np.bincount(rng.integers(0, m, m), minlength=m); ds[r] = (w*sa).sum()/(w*na).sum() - (w*sb).sum()/(w*nb).sum()
    return obs, float((ds <= 0).mean()), np.percentile(ds, [2.5, 97.5])

def pf(x):
    w, l = x[x > 0].sum(), -x[x < 0].sum(); return w/l if l > 0 else np.nan

def desc(x):
    return dict(n=len(x), mean_R_net=x.R_net.mean(), mean_R_flat=x.R_net_flat.mean(), mean_R_gross=x.R_gross.mean(),
                win_rate=(x.R_net > 0).mean(), PF=pf(x.R_net), rev_pct=(x.outcome == 'reversal').mean(),
                MAE_atr=x.MAE_atr.mean(), MFE_atr=x.MFE_atr.mean(), bars_to_rev=x.bars_to_rev.mean(),
                break_fail=x.break_fail.dropna().astype(float).mean(), n_break=int(x.had_break.sum()),
                stop=(x.exit_type == 'stop').mean(), target=(x.exit_type == 'target').mean(), time=(x.exit_type == 'time').mean(),
                spread_med=x.spread_entry.median())

if __name__ == '__main__':
    Q, nocontrol = main(); t = Q[Q.touched]; R = {}
    print('rows', len(Q), 'levels eligible', int((Q.kind == 'level').sum()), 'controls', int((Q.kind == 'control').sum()),
          'levels without control', nocontrol, 'entry_1m_found false', int((~t.entry_1m_found).sum()))
    print('eligible high levels', int(((Q.kind == 'level') & (Q.bucket == 'high')).sum()),
          'high without control', int(((Q.kind == 'level') & (Q.bucket == 'high')).sum() - ((Q.kind == 'control') & (Q.bucket == 'high')).sum()))
    P = paired(Q); Pf = paired(Q, col='R_net_flat')
    d_day = boot_paired(P, 'day'); d_wk = boot_paired(P, 'week'); d_flat = boot_paired(Pf, 'day')
    print(f'PRIMARY paired high: n={len(P)} lv={P.lv.mean():.4f} ct={P.ct.mean():.4f} diff={d_day[0]:.4f} p_day={d_day[1]:.4f} CI={d_day[2]} p_week={d_wk[1]:.4f} CI_w={d_wk[2]}')
    print(f'FLAT 0.50 paired: lv={Pf.lv.mean():.4f} ct={Pf.ct.mean():.4f} diff={d_flat[0]:.4f} p_day={d_flat[1]:.4f}')
    yr = P.groupby('year').agg(n=('lv', 'size'), lv=('lv', 'mean'), ct=('ct', 'mean')); yr['diff'] = yr.lv - yr.ct
    yrf = Pf.groupby('year').agg(lv_flat=('lv', 'mean'), ct_flat=('ct', 'mean')); yr = yr.join(yrf); yr['diff_flat'] = yr.lv_flat - yr.ct_flat
    print(yr.round(4).to_markdown())
    hi = t[t.bucket == 'high']; ulv, uct = hi[hi.kind == 'level'], hi[hi.kind == 'control']
    u = boot_two(ulv, uct); print(f'UNPAIRED high: n_lv={len(ulv)} n_ct={len(uct)} lv={ulv.R_net.mean():.4f} ct={uct.R_net.mean():.4f} diff={u[0]:.4f} p_day={u[1]:.4f}')
    lo = t[(t.bucket == 'low') & (t.kind == 'level')]
    h2 = boot_two(ulv, lo); print(f'H2 high vs low levels: n_hi={len(ulv)} n_lo={len(lo)} diff={h2[0]:.4f} p_day={h2[1]:.4f} CI={h2[2]}')
    # secondary descriptive tables
    pk = set(P.index)
    D = []
    for (b, kd), g in t.groupby(['bucket', 'kind']): D.append({'sample': 'all touched', 'bucket': b, 'kind': kd, **desc(g)})
    for kd in ('level', 'control'):
        g = t[(t.bucket == 'high') & (t.kind == kd) & t.pair.isin(pk)]; D.append({'sample': 'paired high', 'bucket': 'high', 'kind': kd, **desc(g)})
    D = pd.DataFrame(D); D.to_csv(f'{OUT}/tab_secondary.csv', index=False); print(D.round(4).to_markdown(index=False))
    Y = []
    for (y, kd), g in t[(t.bucket == 'high') & t.pair.isin(pk)].groupby(['year', 'kind']): Y.append({'year': y, 'kind': kd, **desc(g)})
    Y = pd.DataFrame(Y); Y.to_csv(f'{OUT}/tab_year_paired_high.csv', index=False); print(Y.round(4).to_markdown(index=False))
    yr.to_csv(f'{OUT}/tab_year_primary.csv')
    sc = []
    for s, g in t[t.kind == 'level'].groupby('score'): sc.append({'score': s, **desc(g)})
    sc = pd.DataFrame(sc); sc.to_csv(f'{OUT}/tab_score.csv', index=False); print(sc.round(4).to_markdown(index=False))
    bal = pd.concat([P.groupby('atr_tercile').size().rename('pairs'), ], axis=1); print('balance by ATR tercile (pairs; level and control share T):\n', bal.to_markdown())
    print('balance by trend:\n', P.groupby('trend').size().to_markdown())
    for nm, by in (('atr_tercile', 'atr_tercile'), ('trend', 'trend'), ('side', 'side')):
        x = P.groupby(by).agg(n=('lv', 'size'), lv=('lv', 'mean'), ct=('ct', 'mean')); x['diff'] = x.lv - x.ct; print(f'paired by {nm}\n', x.round(4).to_markdown())
    crit = {'a_p_day<0.025': d_day[1] < 0.025, 'b_diff>=0.05': d_day[0] >= 0.05, 'c_level_R>0': P.lv.mean() > 0,
            'd_years_pos>=4': int((yr['diff'] > 0).sum()) >= 4, 'e_pairs>=300': len(P) >= 300, 'f_p_week<0.05': d_wk[1] < 0.05}
    print('CRITERIA', crit, 'years_pos', int((yr['diff'] > 0).sum()))
    print('VERDICT', 'PASS' if all(crit.values()) else 'FAIL')
    P.to_csv(f'{OUT}/pairs_high_confirm.csv')
