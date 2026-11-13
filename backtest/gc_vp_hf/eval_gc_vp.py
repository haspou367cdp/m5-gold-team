"""Evaluator for PREREG_gc_vp.md. Confirmation entries (H_rev, H_cont), matched controls, paired net R, day-block bootstrap, Holm.
Bootstrap/pairing conventions copied from levels_v2_confirm/evaluate_confirm.py."""
import sys, os, pickle; sys.dont_write_bytecode = True
import numpy as np, pandas as pd
OUT = os.path.dirname(os.path.abspath(__file__))
SEED, REPS, COST = 20261113, 5000, 0.56
NS = 10**9; M5NS = 5*60*NS; HALF = pd.Timestamp('2026-01-24').date()

def bars():
    d = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet', columns=['ts_utc', 'bid_o', 'bid_h', 'bid_l', 'bid_c', 'bad_quote'])
    d = d[~d.bad_quote & (d.ts_utc >= pd.Timestamp('2025-11-01', tz='UTC')) & (d.ts_utc < pd.Timestamp('2026-04-15', tz='UTC'))]
    d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]'); d = d.set_index('ts_utc').sort_index()
    m5 = d.resample('5min', label='left', closed='left').agg({'bid_o': 'first', 'bid_h': 'max', 'bid_l': 'min', 'bid_c': 'last'}).dropna()
    return d, m5

def news():
    n = pd.read_csv('/workspace/m5-gold-team/data/news_calendar_hist.csv')
    # DEVIATION 1 (bug fix, before any output): tz_localize('Asia/Tehran') of the naive window columns fails on 2022 DST-ambiguous rows;
    # use the explicit datetime_utc column with the same +-15 min windows (window_start/end_tehran = event -15/+15 min).
    u = pd.to_datetime(n.datetime_utc, utc=True); s = u - pd.Timedelta(minutes=15); e = u + pd.Timedelta(minutes=15)
    return s.values.astype('datetime64[ns]').astype(np.int64), e.values.astype('datetime64[ns]').astype(np.int64)

def run(L, D, M5, NW, src):
    t1 = D.index.values.astype(np.int64); H1, L1, C1 = D.bid_h.values, D.bid_l.values, D.bid_c.values
    t5 = M5.index.values.astype(np.int64); O5, H5, L5, C5 = M5.bid_o.values, M5.bid_h.values, M5.bid_l.values, M5.bid_c.values
    ns, ne = NW; rows = []
    def trade(kb, direction, atr):
        """Enter at open of M5 bar kb; direction +1 long, -1 short. Returns dict."""
        e = O5[kb]; stop = e - direction*atr; tgt = e + direction*1.5*atr
        ke = min(kb + 23, len(t5) - 1); j0 = np.searchsorted(t1, t5[kb]); je = np.searchsorted(t1, t5[ke] + M5NS) - 1
        h, l = H1[j0:je+1], L1[j0:je+1]
        hs = (l <= stop) if direction > 0 else (h >= stop); ht = (h >= tgt) if direction > 0 else (l <= tgt)
        i_s = int(np.argmax(hs)) if hs.any() else 10**9; i_t = int(np.argmax(ht)) if ht.any() else 10**9
        if i_s == i_t == 10**9: ie, typ, ex = je - j0, 'time', C1[je]
        elif i_s <= i_t: ie, typ, ex = i_s, 'stop', stop
        else: ie, typ, ex = i_t, 'target', tgt
        hh, ll = h[:ie+1], l[:ie+1]; g = direction*(ex - e)
        mae = (e - ll.min()) if direction > 0 else (hh.max() - e); mfe = (hh.max() - e) if direction > 0 else (e - ll.min())
        ent, exi = t1[j0], t1[j0 + ie]
        innews = bool(((ns <= exi) & (ne >= ent)).any())
        return dict(entry_ts=pd.Timestamp(ent, tz='UTC'), exit_type=typ, gross=g, R_net=(g - COST)/atr, R_gross=g/atr,
                    MAE_atr=max(mae, 0)/atr, MFE_atr=max(mfe, 0)/atr, news=innews)
    def test(T, p, side, atr, kind, meta):
        Tn = T.value; s = np.searchsorted(t5, Tn); e = np.searchsorted(t5, Tn + 4*3600*NS)
        if s >= e: return
        hit = (H5[s:e] >= p) if side == 'resistance' else (L5[s:e] <= p)
        base = {**meta, 'kind': kind, 'lvl': p}
        if not hit.any(): rows.append({**base, 'hyp': 'touch', 'touched': False}); return
        k = s + int(np.argmax(hit)); rows.append({**base, 'hyp': 'touch', 'touched': True})
        cs = C5[k+1:k+7]; ts_ = t5[k+1:k+7]
        if side == 'resistance': rev = cs < p; cont = cs >= p + 0.25*atr; drev, dcont = -1, +1
        else: rev = cs > p; cont = cs <= p - 0.25*atr; drev, dcont = +1, -1
        for hyp, cond, dr in (('rev', rev, drev), ('cont', cont, dcont)):
            if not cond.any(): continue
            i = int(np.argmax(cond)); kc = k + 1 + i; kb = kc + 1
            if kb >= len(t5) or t5[kb] > t5[kc] + M5NS + 15*60*NS: continue   # entry bar must open within 15 min of confirm close
            # also confirm bar must be within 6 bars in time-index sense (consecutive bars present) -> use index as declared
            rows.append({**base, 'hyp': hyp, 'touched': True, 'bars_to_conf': i + 1, **trade(kb, dr, atr)})
    nocontrol = 0
    for T, g in L.groupby('T'):
        price, atr, tol = g.price_T.iloc[0], g.atr_m5.iloc[0], g.tol.iloc[0]; lp = g.price.values
        for i, l in enumerate(g.itertuples()):
            dist = l.price - price
            if abs(dist) < 0.3*atr: continue
            Tt = T.tz_convert('Asia/Tehran')
            meta = dict(src=src, T=T, day=Tt.date(), sess='London' if Tt.hour == 11 else 'NY', half='A' if Tt.date() < HALF else 'B',
                        side=l.side, atr=atr, atr_tercile=l.atr_tercile, trend=l.trend, ltype=l.kinds, strong=getattr(l, 'strong', np.nan), pair=f'{src}_{T.value}_{i}')
            test(T, l.price, l.side, atr, 'level', meta)
            found = False
            for kk in (1, -1, 2, -2, 3, -3):
                cd = dist*(1 + 0.15*kk); cp = price + cd
                if abs(cd) < 0.3*atr or np.min(np.abs(lp - cp)) <= tol: continue
                test(T, cp, l.side, atr, 'control', meta); found = True; break
            if not found: nocontrol += 1
    return pd.DataFrame(rows), nocontrol

def paired(Q, hyp, mask=None):
    t = Q[Q.hyp == hyp] if mask is None else Q[(Q.hyp == hyp) & mask]
    lv = t[t.kind == 'level'].set_index('pair'); ct = t[t.kind == 'control'].set_index('pair'); ix = lv.index.intersection(ct.index)
    P = lv.loc[ix, ['day', 'half', 'sess', 'side', 'atr_tercile', 'trend', 'ltype', 'news', 'R_net']].rename(columns={'R_net': 'lv'})
    P['ct'] = ct.loc[ix, 'R_net']; P['ct_news'] = ct.loc[ix, 'news']; return P

def boot_paired(P, key='day', reps=REPS, seed=SEED):
    if len(P) == 0: return np.nan, np.nan, [np.nan, np.nan]
    rng = np.random.default_rng(seed); g = P.groupby(key).agg(sl=('lv', 'sum'), sc=('ct', 'sum'), n=('lv', 'size'))
    sl, sc, n = g.sl.values, g.sc.values, g.n.values; m = len(g); obs = (sl.sum() - sc.sum())/n.sum(); ds = np.empty(reps)
    for r in range(reps):
        w = np.bincount(rng.integers(0, m, m), minlength=m); ds[r] = ((w*sl).sum() - (w*sc).sum())/(w*n).sum()
    return obs, float((ds <= 0).mean()), np.percentile(ds, [2.5, 97.5])

def pf(x):
    w, l = x[x > 0].sum(), -x[x < 0].sum(); return w/l if l > 0 else np.nan

def desc(x):
    return dict(n=len(x), mean_R_net=x.R_net.mean(), mean_R_gross=x.R_gross.mean(), win=(x.R_net > 0).mean(), PF=pf(x.R_net),
                MAE=x.MAE_atr.mean(), MFE=x.MFE_atr.mean(), bars_to_conf=x.bars_to_conf.mean(),
                stop=(x.exit_type == 'stop').mean(), target=(x.exit_type == 'target').mean(), time=(x.exit_type == 'time').mean())

def holm(ps):
    o = np.argsort(ps); m = len(ps); adj = np.empty(m); run_ = 0
    for r, i in enumerate(o): run_ = max(run_, min(1, (m - r)*ps[i])); adj[i] = run_
    return adj

if __name__ == '__main__':
    G = pd.read_csv(f'{OUT}/gc_levels.csv', parse_dates=['T'])
    S = G.groupby('T').atr_m5.first().reset_index(); S['atr_tercile'] = pd.qcut(S.atr_m5.rank(method='first'), 3, labels=[1, 2, 3]).astype(int)
    G = G.merge(S[['T', 'atr_tercile']], on='T')
    snaps = pickle.load(open('/workspace/m5-gold-team/backtest/levels_bias/snapshots.pkl', 'rb'))
    sm = {pd.Timestamp(s['T']): s for s in snaps if 'error' not in s}
    st = G.groupby('T').agg(price_T=('price_T', 'first'), atr_m5=('atr_m5', 'first'), trend=('trend', 'first'), atr_tercile=('atr_tercile', 'first'))
    LV, miss = [], 0
    for T, r in st.iterrows():
        s = sm.get(T)
        if s is None: miss += 1; continue
        tol = s['tol']
        for (p, side, strength, score, kinds) in s['levels']:
            LV.append(dict(T=T, price=p, side='resistance' if p > r.price_T else 'support', kinds=kinds, strong=score >= 6,
                           price_T=r.price_T, atr_m5=r.atr_m5, tol=tol, trend=r.trend, atr_tercile=r.atr_tercile))
    LV = pd.DataFrame(LV)
    print('GC snapshots', len(st), 'GC levels', len(G), '| levels.py snapshots matched', len(st) - miss, 'missing', miss, 'levels.py levels', len(LV))
    D, M5 = bars(); NW = news()
    Qg, ncg = run(G, D, M5, NW, 'gc'); Ql, ncl = run(LV, D, M5, NW, 'lvpy')
    Q = pd.concat([Qg, Ql]); Q.to_csv(f'{OUT}/trades_gc_vp.csv', index=False)
    for src, q, nc in (('gc', Qg, ncg), ('lvpy', Ql, ncl)):
        tch = q[q.hyp == 'touch']
        print(f'[{src}] eligible levels {int((tch.kind=="level").sum())} controls {int((tch.kind=="control").sum())} no-control {nc} | '
              f'touched levels {int(((tch.kind=="level")&tch.touched).sum())} touched controls {int(((tch.kind=="control")&tch.touched).sum())}')
    res = {}
    for src, q in (('gc', Qg), ('lvpy', Ql)):
        for hyp in ('rev', 'cont'):
            P = paired(q, hyp); b = boot_paired(P)
            hA = P[P.half == 'A']; hB = P[P.half == 'B']
            res[(src, hyp)] = dict(n_pairs=len(P), lv=P.lv.mean(), ct=P.ct.mean(), diff=b[0], p_day=b[1], ci_lo=b[2][0], ci_hi=b[2][1],
                                   diffA=hA.lv.mean() - hA.ct.mean(), nA=len(hA), diffB=hB.lv.mean() - hB.ct.mean(), nB=len(hB))
            P.to_csv(f'{OUT}/pairs_{src}_{hyp}.csv')
    for src in ('gc', 'lvpy'):
        adj = holm(np.array([res[(src, 'rev')]['p_day'], res[(src, 'cont')]['p_day']]))
        res[(src, 'rev')]['p_holm'], res[(src, 'cont')]['p_holm'] = adj
    for k, v in res.items():
        v['reading'] = 'positive hint' if (v['diff'] > 0 and v['p_holm'] < 0.10 and v['diffA'] > 0 and v['diffB'] > 0) else 'no evidence'
    R = pd.DataFrame(res).T; R.to_csv(f'{OUT}/tab_primary.csv'); print('PRIMARY (paired, net R):'); print(R.round(4).to_markdown())
    # levels.py strong-only (secondary)
    for hyp in ('rev', 'cont'):
        P = paired(Ql, hyp, Ql.strong == True); b = boot_paired(P)
        print(f'[lvpy strong>=6] {hyp}: n={len(P)} lv={P.lv.mean():.4f} ct={P.ct.mean():.4f} diff={b[0]:.4f} p_day={b[1]:.4f}')
    # secondary descriptive
    Dd = []
    tr = Q[Q.hyp.isin(['rev', 'cont'])]
    for (src, hyp, kind), g in tr.groupby(['src', 'hyp', 'kind']): Dd.append(dict(sample='all trades (unpaired)', src=src, hyp=hyp, kind=kind, **desc(g)))
    for src, q in (('gc', Qg), ('lvpy', Ql)):
        for hyp in ('rev', 'cont'):
            P = paired(q, hyp); pk = set(P.index); t = q[(q.hyp == hyp) & q.pair.isin(pk)]
            for kind, g in t.groupby('kind'): Dd.append(dict(sample='paired', src=src, hyp=hyp, kind=kind, **desc(g)))
    Dd = pd.DataFrame(Dd); Dd.to_csv(f'{OUT}/tab_secondary.csv', index=False); print(Dd.round(3).to_markdown(index=False))
    Sp = []
    for src, q in (('gc', Qg), ('lvpy', Ql)):
        for hyp in ('rev', 'cont'):
            P = paired(q, hyp)
            for nm, col in (('session', 'sess'), ('half', 'half'), ('news(level trade)', 'news'), ('atr_tercile', 'atr_tercile'), ('trend', 'trend'), ('side', 'side')):
                for v, g in P.groupby(col): Sp.append(dict(src=src, hyp=hyp, split=nm, value=v, n=len(g), lv=g.lv.mean(), ct=g.ct.mean(), diff=g.lv.mean() - g.ct.mean()))
    Sp = pd.DataFrame(Sp); Sp.to_csv(f'{OUT}/tab_splits.csv', index=False); print(Sp.round(3).to_markdown(index=False))
    # GC per level type (level side only, unpaired; first kind of a merged level)
    tg = Qg[Qg.hyp.isin(['rev', 'cont']) & (Qg.kind == 'level')].copy(); tg['type'] = tg.ltype.str.split('|').str[0]
    Ty = tg.groupby(['hyp', 'type']).agg(n=('R_net', 'size'), mean_R=('R_net', 'mean'), win=('R_net', lambda x: (x > 0).mean())); Ty.to_csv(f'{OUT}/tab_ltype.csv'); print(Ty.round(3).to_markdown())
    # GC minus levels.py paired diff (descriptive)
    for hyp in ('rev', 'cont'): print(f'GC minus levels.py paired diff [{hyp}]: {res[("gc", hyp)]["diff"] - res[("lvpy", hyp)]["diff"]:.4f}')
