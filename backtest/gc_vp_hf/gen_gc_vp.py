"""Generator for PREREG_gc_vp.md: point-in-time GC volume-profile levels (PD + PS POC/VAH/VAL) mapped to XAUUSD via rolling basis.
No outcomes computed here."""
import sys, os; sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/m5-gold-team/tools')
import numpy as np, pandas as pd
from datetime import datetime, time as dtime
import m5lib
OUT = os.path.dirname(os.path.abspath(__file__))
SRC = '/workspace/m5-gold-team/data/gc_free_sources/hf_commodity_futures_sample/data/minute/part-00000.parquet'
D0, D1 = '2025-11-21', '2026-03-27'

def load_gc():
    d = pd.read_parquet(SRC); g = d[d.contract_name == 'COMEX Gold Futures'].copy()
    g['ts'] = pd.to_datetime(g.timestamp, unit='ms').dt.tz_localize('America/Chicago').dt.tz_convert('UTC')
    g['date'] = g.ts.dt.tz_convert('Asia/Tehran').dt.date
    return g[['ts', 'date', 'high', 'low', 'close', 'volume', 'contract_code']].sort_values('ts')

def load_xau():
    x = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet', columns=['ts_utc', 'bid_o', 'bid_h', 'bid_l', 'bid_c', 'ask_c', 'bad_quote'])
    x = x[~x.bad_quote & (x.ts_utc >= pd.Timestamp('2025-10-01', tz='UTC')) & (x.ts_utc < pd.Timestamp('2026-05-01', tz='UTC'))]
    x['ts_utc'] = x.ts_utc.astype('datetime64[ns, UTC]'); return x.set_index('ts_utc').sort_index()

def profile(b):
    """b: GC 1m bars (high, low, volume). Returns POC, VAH, VAL (bin low + 0.05) or None."""
    lo = np.floor(b.low.values/0.1 + 1e-9).astype(np.int64); hi = np.floor(b.high.values/0.1 + 1e-9).astype(np.int64)
    v = b.volume.values.astype(float); base = lo.min(); n = hi.max() - base + 1; prof = np.zeros(n)
    for l, h, vv in zip(lo - base, hi - base, v):
        prof[l:h+1] += vv/(h - l + 1)
    tot = prof.sum()
    if tot <= 0: return None
    px = (np.arange(n) + base)*0.1 + 0.05; vwm = (prof*px).sum()/tot
    mx = np.flatnonzero(prof == prof.max()); poc = mx[np.lexsort((px[mx], np.abs(px[mx] - vwm)))[0]]
    a = z = poc; acc = prof[poc]
    while acc < 0.7*tot:
        up = prof[z+1] if z + 1 < n else -1; dn = prof[a-1] if a - 1 >= 0 else -1
        if up < 0 and dn < 0: break
        if up >= dn: z += 1; acc += prof[z]
        else: a -= 1; acc += prof[a]
    return px[poc], px[z], px[a]

def atr_wilder(m5, n=14):
    pc = m5.c.shift(1); tr = pd.concat([m5.h - m5.l, (m5.h - pc).abs(), (m5.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def main():
    G = load_gc(); X = load_xau()
    cov = pd.read_csv(f'{OUT}/gc_front_daily_coverage.csv', index_col=0); front = {pd.Timestamp(k).date(): v for k, v in cov.contract.items()}
    mid = (X.bid_c + X.ask_c)/2
    rows, basis_log, skipped = [], [], {}
    def skip(r): skipped[r] = skipped.get(r, 0) + 1
    for day in pd.date_range(D0, D1, freq='D'):
        if day.weekday() >= 5: continue
        for hm in (dtime(11, 15), dtime(16, 15)):
            T = pd.Timestamp(datetime.combine(day.date(), hm), tz=m5lib.TEH).tz_convert('UTC')
            if not m5lib.market_open(T): skip('market_closed'); continue
            x = X[(X.index >= T - pd.Timedelta(days=10)) & (X.index < T)]
            if len(x) == 0 or x.index[-1] < T - pd.Timedelta(minutes=15): skip('xau_stale'); continue
            fc = front.get(day.date())
            if fc is None:
                prev = [d for d in front if d < day.date()]
                if not prev: skip('no_front'); continue
                fc = front[max(prev)]
            gc = G[G.contract_code == fc]
            # basis
            gw = gc[(gc.ts >= T - pd.Timedelta(minutes=60)) & (gc.ts < T)].set_index('ts').close
            mm = mid.reindex(gw.index); ok = mm.notna()
            if ok.sum() < 30: skip('basis_lt30'); continue
            basis = float(np.median(gw[ok].values - mm[ok].values))
            # ATR / price / trend
            m5 = x.resample('5min', label='left', closed='left').agg({'bid_h': 'max', 'bid_l': 'min', 'bid_c': 'last'}).dropna().rename(columns={'bid_h': 'h', 'bid_l': 'l', 'bid_c': 'c'})
            atr = float(atr_wilder(m5).iloc[-1]); price = float(x.bid_c.iloc[-1]); tol = max(0.5, 0.25*atr)
            h1 = x.bid_c.resample('1h', label='left', closed='left').last().dropna()
            h1 = h1[h1.index + pd.Timedelta('1h') <= T]
            trend = 'up' if h1.ewm(span=20, adjust=False).mean().iloc[-1] > h1.ewm(span=50, adjust=False).mean().iloc[-1] else 'down'
            # profiles
            L = []
            pds = m5lib.previous_trading_day_start(m5lib.trading_day_start(T)); pde = pds + pd.Timedelta(hours=23)
            b = gc[(gc.ts >= pds) & (gc.ts < pde)]
            npd = len(b)
            if npd >= 300:
                r = profile(b); L += [('PD_POC', r[0]), ('PD_VAH', r[1]), ('PD_VAL', r[2])]
            ses = []
            for k in range(0, 6):
                tt = T - pd.Timedelta(days=k)
                if tt.weekday() >= 5: continue
                for nm, (a_, e_) in m5lib.sessions_for(tt).items():
                    if e_ <= T: ses.append((e_, nm, a_))
            e_, snm, a_ = max(ses)
            b = gc[(gc.ts >= a_) & (gc.ts < e_)]; nps = len(b)
            if nps >= 60:
                r = profile(b); L += [('PS_POC', r[0]), ('PS_VAH', r[1]), ('PS_VAL', r[2])]
            if not L: skip('no_profile'); continue
            basis_log.append(dict(T=T, T_teh=m5lib.teh(T), contract=fc, basis=basis, basis_n=int(ok.sum()), price_T=price, atr_m5=atr,
                                  n_pd=npd, ps_session=snm, ps_start=m5lib.teh(a_), n_ps=nps, trend=trend))
            M = sorted([(gp - basis, nm, gp) for nm, gp in L])
            cl = [[M[0]]]
            for m in M[1:]:
                if m[0] - cl[-1][-1][0] <= tol: cl[-1].append(m)
                else: cl.append([m])
            for c in cl:
                p = float(np.mean([m[0] for m in c]))
                rows.append(dict(T=T, price=p, side='resistance' if p > price else 'support', kinds='|'.join(m[1] for m in c),
                                 gc_prices='|'.join(f'{m[2]:.2f}' for m in c), basis=basis, price_T=price, atr_m5=atr, tol=tol, trend=trend, contract=fc))
    pd.DataFrame(rows).to_csv(f'{OUT}/gc_levels.csv', index=False); B = pd.DataFrame(basis_log); B.to_csv(f'{OUT}/basis_log.csv', index=False)
    print('snapshots', len(B), 'levels', len(rows), 'skipped', skipped)
    print('basis stats', B.basis.describe().round(3).to_dict()); print(B.groupby('contract').basis.describe().round(2))
    print('ps_session counts', B.ps_session.value_counts().to_dict(), 'PD present', int((B.n_pd >= 300).sum()), 'PS present', int((B.n_ps >= 60).sum()))

if __name__ == '__main__':
    main()
