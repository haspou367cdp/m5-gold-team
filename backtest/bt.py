"""M5 Gold Scalp backtest of SETUP_RULES.md v0.1. See PREREG.md for frozen interpretations."""
import re, sys, json
import numpy as np, pandas as pd

OUT = '/workspace/m5-gold-team/backtest'
DATA = '/workspace/data/gold_1m/xauusd_1m.parquet'
SPLIT = pd.Timestamp('2024-01-01', tz='UTC')

def load():
    d = pd.read_parquet(DATA)
    d = d[~d.bad_quote].sort_values('ts_utc').reset_index(drop=True)
    d['ts_utc'] = d.ts_utc.astype('datetime64[ns, UTC]')
    return d

def resample(d, rule):
    g = d.set_index('ts_utc')
    agg = {'bid_o':'first','bid_h':'max','bid_l':'min','bid_c':'last','ask_o':'first','ask_h':'max','ask_l':'min','ask_c':'last','spread_c':'last'}
    r = g.resample(rule, label='left', closed='left').agg(agg).dropna(subset=['bid_o'])
    return r.reset_index()

def ema(x, n): return pd.Series(x).ewm(span=n, adjust=False).mean().values

def atr_wilder(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h-l, np.maximum(abs(h-pc), abs(l-pc)))
    return pd.Series(tr).ewm(alpha=1/n, adjust=False).mean().values

def htf_trend(m5, htf, freq):
    """last CLOSED htf bar EMA20/50 state for each m5 bar decision time (m5 close)."""
    e20 = ema(htf.bid_c.values, 20); e50 = ema(htf.bid_c.values, 50)
    t = pd.DataFrame({'close_t': htf.ts_utc + pd.Timedelta(freq), 'e20': e20, 'e50': e50,
                      'e20p': np.r_[np.nan, e20[:-1]]})
    q = pd.DataFrame({'dt': m5.ts_utc + pd.Timedelta('5min')})
    m = pd.merge_asof(q, t, left_on='dt', right_on='close_t', direction='backward')
    bias = np.where(m.e20 > m.e50, 1, np.where(m.e20 < m.e50, -1, 0))
    slope = np.sign(m.e20 - m.e20p).fillna(0).values
    return bias, slope

def build_levels(m5):
    ts = m5.ts_utc
    ny = ts.dt.tz_convert('America/New_York')
    tday = (ny + pd.Timedelta('7h')).dt.date
    m5 = m5.assign(tday=tday, udate=ts.dt.date, hr=ts.dt.hour)
    recs = []
    # trading day H/L, end = last bar ts + 5min
    g = m5.groupby('tday').agg(h=('bid_h','max'), l=('bid_l','min'), end=('ts_utc','max'))
    recs.append(('PD', g))
    for name, a, b in [('AS',0,7),('LO',7,12),('NY',12,21)]:
        s = m5[(m5.hr>=a)&(m5.hr<b)]
        g2 = s.groupby('udate').agg(h=('bid_h','max'), l=('bid_l','min'), end=('ts_utc','max'))
        recs.append((name, g2))
    q = pd.DataFrame({'ts': ts})
    out = {}
    for name, g in recs:
        g = g.assign(end=g.end + pd.Timedelta('5min')).sort_values('end').reset_index(drop=True)
        # session must be complete: for trading day, the end is next day's start; use end of its last bar
        m = pd.merge_asof(q, g[['end','h','l']], left_on='ts', right_on='end', direction='backward', allow_exact_matches=True)
        out[name+'H'] = m.h.values; out[name+'L'] = m.l.values
    # guard: PD must not be the current trading day
    return pd.DataFrame(out)

def spread_normal(d, m5):
    x = pd.DataFrame({'date': d.ts_utc.dt.date, 'hr': d.ts_utc.dt.hour, 's': d.spread_c})
    hm = x.groupby(['hr','date']).s.median().reset_index().sort_values(['hr','date'])
    hm['norm'] = hm.groupby('hr').s.transform(lambda v: v.rolling(20, min_periods=20).median().shift(1))
    k = pd.DataFrame({'hr': m5.ts_utc.dt.hour, 'date': m5.ts_utc.dt.date})
    return k.merge(hm[['hr','date','norm']], on=['hr','date'], how='left').norm.values

# ---------------- signals: list of (bar_idx, dir, sl, inval_type, inval_value, setup)
def sig_sweep(M, LV, bias):
    o,h,l,c = M['o'],M['h'],M['l'],M['c']; n=len(c); S=[]
    lv = LV.values
    for i in range(1,n):
        b = bias[i]
        if b == 0: continue
        for L in lv[i]:
            if not np.isfinite(L): continue
            if b == 1 and c[i-1] > L and l[i] <= L-0.5 and c[i] > L:
                S.append((i,1,l[i]-0.5,'px',l[i],1)); break
            if b == -1 and c[i-1] < L and h[i] >= L+0.5 and c[i] < L:
                S.append((i,-1,h[i]+0.5,'px',h[i],1)); break
    return S

def sig_break_retest(M, LV, bias, atr):
    o,h,l,c = M['o'],M['h'],M['l'],M['c']; n=len(c); S=[]
    lv = LV.values; pend=[]  # (L, dir, break_idx)
    for i in range(1,n):
        # process pending
        newp=[]; fired=False
        for (L,dr,j) in pend:
            if i-j > 6: continue
            if dr==1 and c[i] < L: continue
            if dr==-1 and c[i] > L: continue
            tol = 0.1*atr[i-1]
            if not fired:
                if dr==1:
                    touched = l[i] <= L+tol or (i-1>j and l[i-1] <= L+tol)
                    body = abs(c[i]-o[i]); lw = min(o[i],c[i])-l[i]
                    pin = lw >= 2*body and c[i] >= (h[i]+l[i])/2 and lw>0
                    eng = c[i]>o[i] and c[i-1]<o[i-1] and c[i]>=o[i-1] and o[i]<=c[i-1]
                    if touched and c[i] > L and (pin or eng) and bias[i]==1:
                        lo = min(l[j+1:i+1]); S.append((i,1,lo-0.5,'lvl',L,2)); fired=True; continue
                else:
                    touched = h[i] >= L-tol or (i-1>j and h[i-1] >= L-tol)
                    body = abs(c[i]-o[i]); uw = h[i]-max(o[i],c[i])
                    pin = uw >= 2*body and c[i] <= (h[i]+l[i])/2 and uw>0
                    eng = c[i]<o[i] and c[i-1]>o[i-1] and c[i]<=o[i-1] and o[i]>=c[i-1]
                    if touched and c[i] < L and (pin or eng) and bias[i]==-1:
                        hi = max(h[j+1:i+1]); S.append((i,-1,hi+0.5,'lvl',L,2)); fired=True; continue
            newp.append((L,dr,j))
        pend=newp
        # new breaks at bar i
        a = atr[i-1]; body = c[i]-o[i]
        for L in set(lv[i][np.isfinite(lv[i])]):
            if c[i-1] <= L < c[i] and body >= 0.6*a and bias[i]==1: pend.append((L,1,i))
            if c[i-1] >= L > c[i] and -body >= 0.6*a and bias[i]==-1: pend.append((L,-1,i))
    return S

def sig_ema(M, bias, h1slope):
    o,h,l,c = M['o'],M['h'],M['l'],M['c']; n=len(c); S=[]
    e20 = ema(c,20); e50 = ema(c,50)
    for i in range(52,n):
        if bias[i]==1 and h1slope[i]>0 and e20[i]>e50[i] and e20[i]>e20[i-1]:
            w=slice(i-2,i+1)
            if (l[w]<=e20[w]).any() and (c[w]>=e50[w]).all() and c[i]>o[i] and c[i]>e20[i]:
                S.append((i,1,l[w].min()-0.5,'ema50',0,3))
        elif bias[i]==-1 and h1slope[i]<0 and e20[i]<e50[i] and e20[i]<e20[i-1]:
            w=slice(i-2,i+1)
            if (h[w]>=e20[w]).any() and (c[w]<=e50[w]).all() and c[i]<o[i] and c[i]<e20[i]:
                S.append((i,-1,h[w].max()+0.5,'ema50',0,3))
    return S, e50

def sig_arb(m5, M, bias):
    ts = m5.ts_utc; hr = ts.dt.hour.values; mi = ts.dt.minute.values; dt = ts.dt.date.values
    o,h,l,c = M['o'],M['h'],M['l'],M['c']; S=[]
    df = pd.DataFrame({'d':dt,'hr':hr,'h':h,'l':l})
    rng = df[df.hr<7].groupby('d').agg(H=('h','max'),L=('l','min'))
    done=set()
    for i in np.where((hr>=7)&(hr<9))[0]:
        d=dt[i]
        if d in done or d not in rng.index: continue
        H,L = rng.loc[d,'H'], rng.loc[d,'L']; w=H-L
        if not (5<=w<=25): done.add(d); continue
        b=bias[i]
        if b==1 and c[i]>H:
            S.append((i,1,[(H+L)/2, l[i]],'rng',H,4)); done.add(d)
        elif b==-1 and c[i]<L:
            S.append((i,-1,[(H+L)/2, h[i]],'rng',L,4)); done.add(d)
    return S

# ---------------- simulation on 1m
class Sim:
    def __init__(self, d):
        self.ts = d.ts_utc.values.astype('datetime64[m]').astype(np.int64)  # minutes
        self.bo,self.bh,self.bl,self.bc = [d[k].values for k in ('bid_o','bid_h','bid_l','bid_c')]
        self.sp_o = (d.ask_o-d.bid_o).values; self.sp_h=(d.ask_h-d.bid_h).values
        self.sp_l=(d.ask_l-d.bid_l).values; self.sp_c=(d.ask_c-d.bid_c).values
        self.b5 = self.ts//5
    def run(self, sigs, m5ts_min, e50=None, smult=1.0, delay=0, maxR=8.0, minR=3.0, split=True, blocked=None):
        res=[]; busy_until=-1
        N=len(self.ts)
        for (i,dr,sl,itype,ival,setup) in sigs:
            ebar = i+1+delay
            if ebar >= len(m5ts_min): continue
            if blocked is not None and blocked[i]: continue
            f = np.searchsorted(self.ts, m5ts_min[ebar])
            if f>=N: continue
            if self.ts[f] <= busy_until: continue
            if dr==1: entry = self.bo[f] + smult*self.sp_o[f]
            else: entry = self.bo[f]
            # SL choice
            cands = sl if isinstance(sl,list) else [sl]
            SL=None
            for s in cands:
                R = (entry-s) if dr==1 else (s+ (0 if True else 0) - entry)
                if minR <= R <= maxR: SL=s; break
            if SL is None: continue
            R = entry-SL if dr==1 else SL-entry
            tp1 = entry+dr*1.5*R; tp2 = entry+dr*2.5*R
            out = self._walk(f, dr, entry, SL, tp1, tp2, itype, ival, e50, smult, split, m5ts_min)
            if out is None: continue
            pnl, xi, reason = out
            busy_until = self.ts[xi]
            res.append(dict(setup=setup, dir=dr, sig_bar_ts=int(m5ts_min[i]), entry_ts=int(self.ts[f]), exit_ts=int(self.ts[xi]),
                            entry=entry, sl=SL, tp1=tp1, tp2=tp2, risk=R, pnl_px=pnl, R=pnl/R, exit=reason))
        return pd.DataFrame(res)
    def _walk(self, f, dr, entry, SL, tp1, tp2, itype, ival, e50, smult, split, m5ts_min):
        N=len(self.ts); half1_open = True; rem = 1.0; pnl=0.0
        w1 = 0.5 if split else 1.0
        for m in range(f, min(N, f+60*24*10)):
            if dr==1:
                o,hh,ll = self.bo[m], self.bh[m], self.bl[m]   # exits at bid
                if o <= SL: return pnl + rem*(o-entry), m, 'gapSL'
                if ll <= SL: return pnl + rem*(SL-entry), m, 'SL'
                if half1_open and hh >= tp1:
                    pnl += w1*(tp1-entry); rem -= w1; half1_open=False
                    if rem<=1e-9: return pnl, m, 'TP1'
                if not half1_open and hh >= tp2: return pnl + rem*(tp2-entry), m, 'TP2'
            else:
                a_o = self.bo[m]+smult*self.sp_o[m]; a_h=self.bh[m]+smult*self.sp_h[m]; a_l=self.bl[m]+smult*self.sp_l[m]
                if a_o >= SL: return pnl + rem*(entry-a_o), m, 'gapSL'
                if a_h >= SL: return pnl + rem*(entry-SL), m, 'SL'
                if half1_open and a_l <= tp1:
                    pnl += w1*(entry-tp1); rem -= w1; half1_open=False
                    if rem<=1e-9: return pnl, m, 'TP1'
                if not half1_open and a_l <= tp2: return pnl + rem*(entry-tp2), m, 'TP2'
            # M5 close check
            if m+1 < N and self.b5[m+1] != self.b5[m]:
                c = self.bc[m]
                if itype=='ema50':
                    k = np.searchsorted(m5ts_min, self.b5[m]*5); lvl = e50[k]
                else: lvl = ival
                bad = (c < lvl) if dr==1 else (c > lvl)
                if bad:
                    x = m+1
                    px = self.bo[x] if dr==1 else self.bo[x]+smult*self.sp_o[x]
                    return pnl + rem*dr*(px-entry), x, 'inval'
        m = min(N-1, f+60*24*10-1)
        px = self.bc[m] if dr==1 else self.bc[m]+smult*self.sp_c[m]
        return pnl + rem*dr*(px-entry), m, 'timeout'

def news_block(m5):
    html = open(f'{OUT}/fomc_calendar_source.html').read()
    days = set(re.findall(r'fomcpresconf(20\d{6})', html)) | set(re.findall(r'monetary(20\d{6})a', html))
    days.discard('20250822')
    special = {'20200303':'10:00','20200315':'17:00'}
    ev=[]
    for dd in sorted(days):
        if dd < '20200101': continue
        t = special.get(dd,'14:00')
        ev.append(pd.Timestamp(f'{dd[:4]}-{dd[4:6]}-{dd[6:]} {t}', tz='America/New_York').tz_convert('UTC'))
    ny = m5.ts_utc.dt.tz_convert('America/New_York')
    dec = m5.ts_utc + pd.Timedelta('5min')  # decision/entry time
    decny = dec.dt.tz_convert('America/New_York')
    mins = decny.dt.hour*60+decny.dt.minute
    blk = np.array(((mins>=8*60+15)&(mins<=8*60+45)&(decny.dt.weekday<5)).values, dtype=bool, copy=True)
    e = np.array([x.value for x in ev]); dv = dec.values.astype('datetime64[ns]').astype(np.int64)
    idx = np.searchsorted(e, dv)
    for k in (idx-1, idx):
        k2 = np.clip(k,0,len(e)-1)
        blk |= np.abs(dv - e[k2]) <= 15*60*1e9
    return blk, len(ev)

def main():
    d = load()
    m5 = resample(d,'5min'); h1 = resample(d,'1h'); m15 = resample(d,'15min')
    M = {k: m5['bid_'+k].values for k in 'ohlc'}
    bias, h1slope = htf_trend(m5, h1, '1h')
    bias15, _ = htf_trend(m5, m15, '15min')
    LV = build_levels(m5)
    atr = atr_wilder(M['h'],M['l'],M['c'])
    norm = spread_normal(d, m5)
    spread_ok = m5.spread_c.values <= 1.5*norm
    print('levels/bias built', flush=True)
    S1 = sig_sweep(M, LV, bias); S2 = sig_break_retest(M, LV, bias, atr)
    S3, e50 = sig_ema(M, bias, h1slope); S4 = sig_arb(m5, M, bias)
    allS = {1:S1,2:S2,3:S3,4:S4}
    for k,v in allS.items(): print('setup',k,'raw signals',len(v), flush=True)
    allS = {k:[s for s in v if spread_ok[s[0]]] for k,v in allS.items()}
    m5ts_min = m5.ts_utc.values.astype('datetime64[m]').astype(np.int64)
    sim = Sim(d)
    blk, nfomc = news_block(m5)
    variants = {'base':dict(), 'spread+50%':dict(smult=1.5), 'delay+1bar':dict(delay=1),
                'news-proxy':dict(blocked=blk), 'acct500_R<=5_TP1':dict(maxR=5.0, split=False)}
    frames=[]
    for vn, kw in variants.items():
        for k,S in allS.items():
            t = sim.run(S, m5ts_min, e50=e50, **kw); t['variant']=vn; frames.append(t)
            print(vn, k, len(t), round(t.R.mean(),3) if len(t) else None, flush=True)
    T = pd.concat(frames, ignore_index=True)
    for c in ('sig_bar_ts','entry_ts','exit_ts'):
        T[c] = pd.to_datetime(T[c]*60, unit='s', utc=True)
    T.to_csv(f'{OUT}/trades_all_variants.csv', index=False)
    json.dump({'n_fomc_events': nfomc}, open(f'{OUT}/meta.json','w'))
    # bias check
    bias_check(m5, h1, m15).to_csv(f'{OUT}/bias_check.csv', index=False)

def bias_check(m5, h1, m15):
    # at each H1 close time T
    T = h1.ts_utc + pd.Timedelta('1h')
    e20=ema(h1.bid_c.values,20); e50=ema(h1.bid_c.values,50)
    hb = np.sign(e20-e50)
    q = pd.DataFrame({'T':T,'hb':hb,'c0':h1.bid_c.values})
    e20m=ema(m15.bid_c.values,20); e50m=ema(m15.bid_c.values,50)
    mt = pd.DataFrame({'ct': m15.ts_utc+pd.Timedelta('15min'), 'mb': np.sign(e20m-e50m)})
    q = pd.merge_asof(q.sort_values('T'), mt, left_on='T', right_on='ct', direction='backward')
    # price 2h later: last m5 close at or before T+2h
    p = pd.DataFrame({'t': m5.ts_utc+pd.Timedelta('5min'), 'c': m5.bid_c.values})
    q['T2'] = q['T']+pd.Timedelta('2h')
    q = pd.merge_asof(q.sort_values('T2'), p.rename(columns={'t':'t2','c':'c2'}), left_on='T2', right_on='t2', direction='backward')
    q = q[(q.T2 - q.t2) <= pd.Timedelta('10min')]  # require data near T+2h (skip weekend gaps)
    q['move'] = np.sign(q.c2 - q.c0)
    hr = q['T'].dt.hour
    q['session'] = np.select([hr<7, hr<12, hr<21],['Asia','London','NewYork'],'Late')
    q['period'] = np.where(q['T']<SPLIT,'IS','OOS')
    rows=[]
    for (per,ses),g in q.groupby(['period','session']):
        a = g[(g.hb==g.mb)&(g.hb!=0)&(g.move!=0)]
        h_ = g[(g.hb!=0)&(g.move!=0)]
        rows.append(dict(period=per, session=ses, n_agree=len(a), hit_H1M15_agree=(a.hb==a.move).mean(),
                         n_h1=len(h_), hit_H1_only=(h_.hb==h_.move).mean(), up_share=(h_.move>0).mean()))
    return pd.DataFrame(rows)

if __name__=='__main__': main()
