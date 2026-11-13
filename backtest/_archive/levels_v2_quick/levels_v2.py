"""levels_v2 — XAUUSD level-detection system v2 (UNVALIDATED until backtest/levels_v2 passes).
Framework (owner, 2026-11-13): Daily+4H context, 1H levels, 15M refinement, 5M trigger.
Candidates: PDH/PDL, PWH/PWL, H4 & H1 swings, equal highs/lows, Asia/London session H/L,
volume-profile POC/VAH/VAL (Dukascopy TICK-VOLUME PROXY, not COMEX volume), anchored VWAP.
Skipped for the quick test: supply/demand zones, order blocks, FVG, fib.
Score 0-5 (one point each):
  s1 structure  : cluster contains an H1 or H4 swing (confirmed fractal)
  s2 liquidity  : cluster contains EQH/EQL, PDH/PDL or PWH/PWL
  s3 volume     : cluster contains a VP POC/VAH/VAL (prev day or developing day)
  s4 session    : a completed M15 bar in London/NY in the last 72h traded through the level (±tol)
  s5 displacement: a completed M15 bar touched the level in the last 5 days and within the next 4 M15 bars
                   a close was >= 2 x ATR_M15 away from it
Pure library: no I/O on import. compute(m1, T) uses only bars with open < T (completed bars for structure).
CLI: python3 levels_v2.py --print  (reads the live cache data/xauusd_1m.parquet; writes nothing)."""
import sys
import numpy as np, pandas as pd
sys.dont_write_bytecode = True

def _m5lib():
    sys.path.insert(0, "/workspace/m5-gold-team/tools"); import m5lib; return m5lib

def atr(df, n=14):
    pc = df.c.shift(1)
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()

def resample(m1, rule, offset=None):
    kw = dict(label='left', closed='left')
    if offset is not None: kw['offset'] = offset
    r = m1.resample(rule, **kw).agg({'o_b': 'first', 'h_b': 'max', 'l_b': 'min', 'c_b': 'last'}).dropna()
    return r.rename(columns={'o_b': 'o', 'h_b': 'h', 'l_b': 'l', 'c_b': 'c'})

def completed(df, T, period):
    return df[df.index + period <= T]

def fractals(df, n, since):
    x = df[df.index >= since]; hi, lo = x.h.values, x.l.values; H, L = [], []
    for k in range(n, len(x) - n):
        if hi[k] == hi[k - n:k + n + 1].max(): H.append(float(hi[k]))
        if lo[k] == lo[k - n:k + n + 1].min(): L.append(float(lo[k]))
    return H, L

def vprofile(m1):
    """POC/VAH/VAL from 1m bars, typical-price binning ($0.5), volume = bid_vol+ask_vol (Dukascopy tick-volume proxy)."""
    if len(m1) < 30: return None
    tp = (m1.h_b + m1.l_b + m1.c_b) / 3
    v = (m1.v_b.fillna(0) + m1.v_a.fillna(0)).values
    if v.sum() <= 0: v = np.ones(len(m1))
    b = np.floor(tp.values / 0.5).astype(int); u, inv = np.unique(b, return_inverse=True)
    vol = np.bincount(inv, weights=v); i = int(np.argmax(vol)); lo = hi = i; tot = vol.sum(); acc = vol[i]
    while acc < 0.7 * tot and (lo > 0 or hi < len(u) - 1):
        a = vol[lo - 1] if lo > 0 else -1; c = vol[hi + 1] if hi < len(u) - 1 else -1
        if c >= a: hi += 1; acc += vol[hi]
        else: lo -= 1; acc += vol[lo]
    f = lambda j: (u[j] + 0.5) * 0.5
    return {'POC': f(i), 'VAH': f(hi), 'VAL': f(lo)}

def compute(m1, T=None, rng=None):
    """m1: 1m BID/ASK frame (toolkit column names, UTC index) with >= ~21 days of history before T."""
    L5 = _m5lib()
    if T is None: T = m1.index[-1] + pd.Timedelta(minutes=1)
    m1 = m1[m1.index < T]
    price = float(m1.c_b.iloc[-1])
    m5 = resample(m1.iloc[-3000:], '5min'); m15 = resample(m1[m1.index >= T - pd.Timedelta(days=8)], '15min')
    h1 = resample(m1[m1.index >= T - pd.Timedelta(days=12)], '1h'); h4 = resample(m1, '4h')
    m15c = completed(m15, T, pd.Timedelta('15min')); h1c = completed(h1, T, pd.Timedelta('1h')); h4c = completed(h4, T, pd.Timedelta('4h'))
    a5 = float(atr(m5).iloc[-1]); a15 = float(atr(m15c).iloc[-1]); ah1 = float(atr(h1c).iloc[-1])
    tol = max(0.5, 0.25 * a5)
    C = []
    def add(p, kind):
        if p is not None and np.isfinite(p): C.append((float(p), kind))
    # daily / weekly
    d0 = L5.trading_day_start(T); dp = L5.previous_trading_day_start(d0)
    pdm = m1[(m1.index >= dp) & (m1.index < d0)]
    if len(pdm): add(pdm.h_b.max(), 'PDH'); add(pdm.l_b.min(), 'PDL')
    tny = T.tz_convert(L5.NY); ws = (tny.normalize() - pd.Timedelta(days=(tny.weekday() + 1) % 7) + pd.Timedelta(hours=18))
    if ws > tny: ws -= pd.Timedelta(days=7)
    ws = ws.tz_convert('UTC'); pw = m1[(m1.index >= ws - pd.Timedelta(days=7)) & (m1.index < ws)]
    if len(pw): add(pw.h_b.max(), 'PWH'); add(pw.l_b.min(), 'PWL')
    # swings
    H4h, H4l = fractals(h4c, 2, T - pd.Timedelta(days=15))
    H1h, H1l = fractals(h1c, 3, T - pd.Timedelta(days=8))
    for p in H4h: add(p, 'H4 swing high')
    for p in H4l: add(p, 'H4 swing low')
    for p in H1h: add(p, 'H1 swing high')
    for p in H1l: add(p, 'H1 swing low')
    # equal highs / lows (liquidity pools): H1 (n=2, 5d) + M15 (n=3, 2d) swings within 0.1 x ATR_H1
    eq = 0.1 * ah1
    for hs, kind, f in ((fractals(h1c, 2, T - pd.Timedelta(days=5))[0] + fractals(m15c, 3, T - pd.Timedelta(days=2))[0], 'EQH', max),
                        (fractals(h1c, 2, T - pd.Timedelta(days=5))[1] + fractals(m15c, 3, T - pd.Timedelta(days=2))[1], 'EQL', min)):
        hs = sorted(set(hs))
        for i in range(len(hs) - 1):
            if hs[i + 1] - hs[i] <= eq: add(f(hs[i], hs[i + 1]), kind)
    # sessions: today's and previous weekday's Asia/London (running ones up to T)
    yd = T - pd.Timedelta(days=1)
    while yd.weekday() >= 5: yd -= pd.Timedelta(days=1)
    for tag, ses in (('', L5.sessions_for(T)), ('prev ', L5.sessions_for(yd))):
        for nm in ('asia', 'london'):
            a, b = ses[nm]; s = m1[(m1.index >= a) & (m1.index < min(b, T))]
            if len(s) >= 15: add(s.h_b.max(), f'{tag}{nm} high'); add(s.l_b.min(), f'{tag}{nm} low')
    # volume profile (proxy) prev day + developing day
    for tag, seg in (('prev', pdm), ('dev', m1[m1.index >= d0])):
        vp = vprofile(seg)
        if vp:
            for k, p in vp.items(): add(p, f'VP {tag} {k}')
    # anchored VWAP (trading-day open), tick-volume proxy
    t = m1[m1.index >= d0]
    if len(t) >= 15:
        tp = (t.h_b + t.l_b + t.c_b) / 3; v = (t.v_b.fillna(0) + t.v_a.fillna(0)).replace(0, 1e-9)
        add(float((tp * v).sum() / v.sum()), 'VWAP')
    rng = rng or max(60.0, 8 * ah1)
    C = sorted([c for c in C if abs(c[0] - price) <= rng])
    clusters = []
    for c in C:
        if clusters and c[0] - clusters[-1][-1][0] <= tol: clusters[-1].append(c)
        else: clusters.append([c])
    # recent M15 for s4/s5
    r15 = m15c[m15c.index >= T - pd.Timedelta(days=5)]
    rh, rl, rc = r15.h.values, r15.l.values, r15.c.values; ri = r15.index
    lon_ny = np.zeros(len(r15), bool); recent72 = (ri >= T - pd.Timedelta(hours=72))
    cache = {}
    for j, tt in enumerate(ri):
        key = tt.normalize()
        if key not in cache: cache[key] = L5.sessions_for(tt)
        s = cache[key]; lon_ny[j] = s['london'][0] <= tt < s['ny'][1]
    out = []
    for cl in clusters:
        kinds = sorted({k for _, k in cl})
        st = [p for p, k in cl if not k.startswith(('VP', 'VWAP'))]
        p = float(np.mean(st if st else [x for x, _ in cl]))
        touch = (rl - tol <= p) & (rh + tol >= p)
        s1 = int(any(k.startswith(('H1 swing', 'H4 swing')) for k in kinds))
        s2 = int(any(k in ('EQH', 'EQL', 'PDH', 'PDL', 'PWH', 'PWL') for k in kinds))
        s3 = int(any(k.startswith('VP') for k in kinds))
        s4 = int((touch & lon_ny & recent72).any())
        s5 = 0
        for j in np.flatnonzero(touch):
            w = rc[j + 1:j + 5]
            if len(w) and np.max(np.abs(w - p)) >= 2 * a15: s5 = 1; break
        sc = s1 + s2 + s3 + s4 + s5
        out.append({'price': round(p, 2), 'side': 'resistance' if p > price else 'support', 'score': sc,
                    's1_structure': s1, 's2_liquidity': s2, 's3_volume': s3, 's4_session': s4, 's5_displacement': s5,
                    'priority': 'high' if sc >= 4 else 'watch' if sc == 3 else 'low', 'kinds': '|'.join(kinds),
                    'distance': round(p - price, 2)})
    return {'T': T, 'price_bid': price, 'atr_m5': a5, 'atr_m15': a15, 'atr_h1': ah1, 'tol': tol, 'levels': out,
            'volume_note': 'volume = Dukascopy tick-volume proxy, NOT COMEX GC volume'}

def main():
    m1 = pd.read_parquet('/workspace/m5-gold-team/data/xauusd_1m.parquet')
    r = compute(m1)
    print(f"levels_v2 (UNVALIDATED) price {r['price_bid']:.2f} ATR_M5 {r['atr_m5']:.2f} tol {r['tol']:.2f} — {r['volume_note']}")
    for l in sorted(r['levels'], key=lambda x: -x['price']):
        if abs(l['distance']) <= 40: print(f"{l['price']:>9.2f} {l['side']:<10} score {l['score']} ({l['priority']}) {l['kinds']}")

if __name__ == '__main__' and '--print' in sys.argv: main()
