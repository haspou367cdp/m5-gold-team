"""Outcome evaluation for PREREG_levels_bias.md. Reads snapshots.pkl (rebuild.py) + full 1m history."""
import sys, re, pickle, json, os
import numpy as np, pandas as pd
from scipy.stats import binomtest, norm
sys.dont_write_bytecode = True
sys.path.insert(0, "/workspace/m5-gold-team/tools")
import m5lib
OUT = os.path.dirname(os.path.abspath(__file__))
SPLIT = pd.Timestamp('2024-01-01', tz='UTC')

def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k/n; den = 1+z*z/n; c = (p+z*z/(2*n))/den; h = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (c-h, c+h)

def bars():
    d = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet', columns=['ts_utc','bid_h','bid_l','bid_c','bad_quote'])
    d = d[~d.bad_quote]; d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]'); d = d.set_index('ts_utc')
    m5 = d.resample('5min', label='left', closed='left').agg({'bid_h':'max','bid_l':'min','bid_c':'last'}).dropna()
    m15 = d.bid_c.resample('15min', label='left', closed='left').last().dropna()
    h1 = d.bid_c.resample('1h', label='left', closed='left').last().dropna()
    return d, m5, m15, h1

def news_windows():
    html = open(f'{OUT}/../fomc_calendar_source.html').read()
    days = set(re.findall(r'fomcpresconf(20\d{6})', html)) | set(re.findall(r'monetary(20\d{6})a', html)); days.discard('20250822')
    special = {'20200303': '10:00', '20200315': '17:00'}
    ev = [pd.Timestamp(f'{x[:4]}-{x[4:6]}-{x[6:]} {special.get(x,"14:00")}', tz='America/New_York').tz_convert('UTC') for x in sorted(days) if x >= '20200101']
    for d in pd.date_range('2020-01-01', '2026-10-31', freq='D'):
        if d.weekday() < 5: ev.append(pd.Timestamp(f'{d.date()} 08:30', tz='America/New_York').tz_convert('UTC'))
    ev = np.array(sorted(x.value for x in ev))
    return ev, 15*60*10**9

def session_of(t, cache={}):
    key = t.normalize()
    if key not in cache: cache[key] = m5lib.sessions_for(t)
    for k, (a, b) in cache[key].items():
        if a <= t < b: return k
    return 'off'

def main():
    S = pickle.load(open(f'{OUT}/snapshots.pkl', 'rb'))
    S = [s for s in S if 'error' not in s]
    d1, m5, m15, h1 = bars()
    t5 = m5.index.values.astype(np.int64); H5 = m5.bid_h.values; L5 = m5.bid_l.values
    end5 = t5 + 5*60*10**9
    m15c = pd.Series(m15.values, index=m15.index + pd.Timedelta('15min'))
    br = m15c.reindex(pd.DatetimeIndex(end5, tz='UTC')).values   # M15 close at bars that end an M15 bar (else NaN)
    ev, half = news_windows()
    def in_news(tns):
        k = np.searchsorted(ev, tns); 
        return any(0 <= j < len(ev) and abs(ev[j]-tns) <= half for j in (k-1, k))
    def overlaps_news(a, b):
        k = np.searchsorted(ev, a - half); return k < len(ev) and ev[k] - half <= b
    # ---------- Q1
    rows = []
    def test(T, p, side, atr, kind, meta):
        Tn = T.value; s = np.searchsorted(t5, Tn); e = np.searchsorted(t5, Tn + 4*3600*10**9)
        if s >= e: return
        hit = (H5[s:e] >= p) if side == 'resistance' else (L5[s:e] <= p)
        if not hit.any(): rows.append({**meta, 'kind': kind, 'touched': False}); return
        k = s + int(np.argmax(hit)); ke = min(np.searchsorted(t5, t5[k] + 2*3600*10**9), len(t5))
        if side == 'resistance':
            rev = L5[k:ke] <= p - atr; brk = br[k:ke] > p
        else:
            rev = H5[k:ke] >= p + atr; brk = br[k:ke] < p
        ir = int(np.argmax(rev)) if rev.any() else 10**9; ib = int(np.argmax(brk)) if brk.any() else 10**9
        out = 'neither' if ir == ib == 10**9 else ('break' if ib <= ir else 'reversal')
        tt = pd.Timestamp(t5[k], tz='UTC')
        rows.append({**meta, 'kind': kind, 'touched': True, 'outcome': out, 'touch_ts': tt, 'session': session_of(tt), 'news': in_news(t5[k])})
    for sn in S:
        T, price, atr, tol = sn['T'], sn['price'], sn['atr'], sn['tol']
        lv = sn['levels']; lp = np.array([l[0] for l in lv])
        for (p, side, strength, score, kinds) in lv:
            dist = p - price
            if abs(dist) < 0.3*atr: continue
            meta = dict(T=T, period='IS' if T < SPLIT else 'OOS', brief='London' if T.tz_convert(m5lib.TEH).hour == 11 else 'NY',
                        strength=strength, side=side, level=p, score=score, kinds=kinds, atr=atr, dist_atr=abs(dist)/atr)
            test(T, p, side, atr, 'level', meta)
            for kk in (1, -1, 2, -2, 3, -3):
                cd = dist*(1+0.15*kk); cp = price + cd
                if abs(cd) < 0.3*atr: continue
                if np.min(np.abs(lp - cp)) <= tol: continue
                r5 = cp/5.0
                if abs(r5 - round(r5))*5 <= tol: continue
                test(T, cp, side, atr, 'control', {**meta, 'level': cp}); break
    Q1 = pd.DataFrame(rows); Q1.to_csv(f'{OUT}/q1_touches.csv', index=False)
    # ---------- Q2
    rows = []
    d1c = d1.bid_c; d1t = d1.index.values.astype(np.int64)
    for sn in S:
        T = sn['T']; T2 = T + pd.Timedelta('2h'); j = np.searchsorted(d1t, T2.value) - 1
        if j < 0 or T2.value - d1t[j] > 10*60*10**9: continue
        mv = d1c.values[j] - sn['price']; b = sn['bias']; dr = 1 if b == 'bullish' else -1 if b == 'bearish' else 0
        rec = dict(T=T, period='IS' if T < SPLIT else 'OOS', brief='London' if T.tz_convert(m5lib.TEH).hour == 11 else 'NY', bias=b,
                   conf=sn['conf'], h1=sn['h1'], m15=sn['m15'], move=mv, atr=sn['atr'], verdict=sn['verdict'],
                   news=overlaps_news(T.value, T2.value), inv_neutral=sn['inv_neutral'], inv_off=sn['inv_off'])
        if dr:
            rec['hit'] = np.sign(mv) == dr if mv != 0 else np.nan
            rec['big'] = abs(mv) >= 0.5*sn['atr']
            # invalidation within (T, T+2h]
            c15 = m15c[(m15c.index > T) & (m15c.index <= T2)]
            if sn['inv_neutral'] is not None:
                rec['inv15'] = bool(((c15 > sn['inv_neutral']) if dr == -1 else (c15 < sn['inv_neutral'])).any())
            if sn['inv_off'] is not None:
                c1 = h1[(h1.index + pd.Timedelta('1h') > T) & (h1.index + pd.Timedelta('1h') <= T2)]
                rec['invH1'] = bool(((c1 > sn['inv_off']) if dr == -1 else (c1 < sn['inv_off'])).any())
        rows.append(rec)
    Q2 = pd.DataFrame(rows); Q2.to_csv(f'{OUT}/q2_briefs.csv', index=False)
    report(Q1, Q2, len(S))

def q1tab(df, by):
    rows = []
    for k, g in df.groupby(by, observed=True):
        k = k if isinstance(k, tuple) else (k,)
        r = {}
        for kind in ('level', 'control'):
            x = g[(g.kind == kind) & g.touched]; n = len(x); kr = int((x.outcome == 'reversal').sum())
            lo, hi = wilson(kr, n)
            r[kind] = (n, kr, (x.outcome == 'break').sum(), (x.outcome == 'neither').sum(), lo, hi)
        (n1, k1, b1, ne1, lo1, hi1), (n0, k0, b0, ne0, lo0, hi0) = r['level'], r['control']
        p1 = k1/n1 if n1 else np.nan; p0 = k0/n0 if n0 else np.nan
        pp = (k1+k0)/(n1+n0) if n1+n0 else np.nan
        z = (p1-p0)/np.sqrt(pp*(1-pp)*(1/n1+1/n0)) if n1 and n0 and 0 < pp < 1 else np.nan
        rows.append({**dict(zip(by, k)), 'n_touch': n1, 'reversal%': round(100*p1, 1), 'rev_CI95': f'{100*lo1:.1f}-{100*hi1:.1f}',
                     'break%': round(100*b1/n1, 1) if n1 else np.nan, 'neither%': round(100*ne1/n1, 1) if n1 else np.nan,
                     'ctrl_n': n0, 'ctrl_rev%': round(100*p0, 1), 'ctrl_CI95': f'{100*lo0:.1f}-{100*hi0:.1f}',
                     'ctrl_break%': round(100*b0/n0, 1) if n0 else np.nan, 'diff_pp': round(100*(p1-p0), 1),
                     'p_two_sided': round(2*(1-norm.cdf(abs(z))), 4) if np.isfinite(z) else np.nan})
    return pd.DataFrame(rows)

def q2tab(df, by, col='hit'):
    rows = []
    for k, g in df.groupby(by, observed=True):
        k = k if isinstance(k, tuple) else (k,)
        x = g[g[col].notna()][col].astype(bool) if col == 'hit' else g
        n, h = len(x), int(x.sum())
        lo, hi = wilson(h, n); p = binomtest(h, n, 0.5).pvalue if n else np.nan
        rows.append({**dict(zip(by, k)), 'n': n, 'hit%': round(100*h/n, 1) if n else np.nan, 'CI95': f'{100*lo:.1f}-{100*hi:.1f}', 'binom_p': round(p, 4)})
    return pd.DataFrame(rows)

def report(Q1, Q2, nsnap):
    md = ['# Level reaction + brief bias study — results (M5-Journal)', '',
          'Prereg: PREREG_levels_bias.md (sha in HASHES.txt, written before results). Data: DataHunter\'s Dukascopy-derived 1m BID+ASK, 2020-01-02..2026-10-30.',
          f'Snapshots rebuilt (brief times 11:15/16:15 Tehran, market open, fresh data): {nsnap}.', '']
    lv = Q1[Q1.kind == 'level']
    md.append(f"Q1 eligible levels: {len(lv)}, touched within 4h: {int(lv.touched.sum())} ({100*lv.touched.mean():.1f}%). Controls: {int((Q1.kind=='control').sum())}, touched {int(Q1[Q1.kind=='control'].touched.sum())}.\n")
    T = Q1[Q1.touched == True].copy()
    T['strength'] = pd.Categorical(T.strength, ['strong', 'medium', 'weak'])
    md.append('## Q1 level reaction (reversal = ≥1×ATR_M5 away before an M15 close beyond; 2h after touch). Control = matched non-level price\n')
    md.append('### by period × strength\n'); md.append(q1tab(T, ['period', 'strength']).to_markdown(index=False))
    md.append('\n### strong+medium by period × side\n'); sm = T[T.strength.isin(['strong', 'medium'])]
    md.append(q1tab(sm, ['period', 'side']).to_markdown(index=False))
    md.append('\n### strong+medium by period × session (of touch; m5lib sessions)\n'); md.append(q1tab(sm, ['period', 'session']).to_markdown(index=False))
    md.append('\n### by period × strength × side\n'); md.append(q1tab(T, ['period', 'strength', 'side']).to_markdown(index=False))
    md.append('\n### news-proxy variant: touches outside ±15 min of 08:30 ET (every weekday) and FOMC 14:00 ET\n')
    md.append(q1tab(T[~T.news.astype(bool)], ['period', 'strength']).to_markdown(index=False))
    md.append('\n## Q2 brief bias vs BID move 2h later\n')
    D = Q2[Q2.bias != 'neutral']
    md.append(f"Briefs with outcome: {len(Q2)}; bias split: {Q2.bias.value_counts().to_dict()}\n")
    md.append('### all directional briefs\n'); md.append(q2tab(D, ['period']).to_markdown(index=False))
    md.append(q2tab(D, ['period', 'brief']).to_markdown(index=False))
    md.append(q2tab(D, ['period', 'conf']).to_markdown(index=False))
    md.append(q2tab(D, ['period', 'brief', 'bias']).to_markdown(index=False))
    md.append('\n### threshold: only moves ≥ 0.5×ATR_M5\n')
    B = D[D.big == True]
    md.append(f"share of directional briefs with |move| ≥ 0.5 ATR: {100*D.big.astype(bool).mean():.1f}% (n={len(D)}); hit% below = among those only\n")
    md.append(q2tab(B, ['period']).to_markdown(index=False)); md.append(q2tab(B, ['period', 'brief']).to_markdown(index=False))
    md.append('\n### invalidation (M15 close beyond neutral_level / H1 close beyond off_level within 2h)\n')
    rows = []
    for (per,), g in D.groupby(['period']):
        g15 = g[g.inv15.notna()]; gH = g[g.invH1.notna()]
        rows.append(dict(period=per, n_with_neutral_level=len(g15), inv15_pct=round(100*g15.inv15.astype(bool).mean(), 1),
                         hit_if_inv15=round(100*g15[g15.inv15.astype(bool)].hit.dropna().astype(bool).mean(), 1),
                         hit_if_not=round(100*g15[~g15.inv15.astype(bool)].hit.dropna().astype(bool).mean(), 1),
                         n_with_off_level=len(gH), invH1_pct=round(100*gH.invH1.astype(bool).mean(), 1)))
    md.append(pd.DataFrame(rows).to_markdown(index=False))
    md.append('\n### news-proxy variant: drop briefs whose 2h window overlaps a proxy window\n')
    Dn = D[~D.news.astype(bool)]
    md.append(f"kept {len(Dn)} of {len(D)} directional briefs; by brief: {Dn.brief.value_counts().to_dict()}\n")
    md.append(q2tab(Dn, ['period', 'brief']).to_markdown(index=False))
    open(f'{OUT}/summary.md', 'w').write('\n'.join(md))
    print('\n'.join(md))

if __name__ == '__main__': main()
