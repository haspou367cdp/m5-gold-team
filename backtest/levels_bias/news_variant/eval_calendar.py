"""ADDENDUM 1 variant: filter saved Q1/Q2 rows by M5-News historical calendar windows. Original outputs untouched."""
import sys, os
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__)); PAR = os.path.dirname(HERE)
sys.path.insert(0, PAR)
from evaluate import q1tab, q2tab
CAL = '/workspace/m5-gold-team/data/news_calendar_hist.csv'

def windows():
    c = pd.read_csv(CAL)
    # window offsets relative to the event, measured on the naive Tehran clock, applied to the unambiguous datetime_utc
    # (avoids the ambiguous local hour at Iran's 2022-09-21 DST end)
    ev_utc = pd.to_datetime(c.datetime_utc, utc=True)
    ev_loc = pd.to_datetime(c.datetime_tehran.str[:16])
    s = ev_utc + (pd.to_datetime(c.window_start_tehran) - ev_loc)
    e = ev_utc + (pd.to_datetime(c.window_end_tehran) - ev_loc)
    o = np.argsort(s.values)
    return s.values[o].astype('datetime64[ns]').astype(np.int64), e.values[o].astype('datetime64[ns]').astype(np.int64), c.iloc[o].reset_index(drop=True)

def overlaps(a, b, S, E):
    """[a,b] overlaps any [S,E): exists S < b and E > a. Windows are short and sorted by start."""
    k = np.searchsorted(S, b, side='left')   # windows starting before b
    out = np.zeros(len(a), bool)
    for i in range(len(a)):
        j = k[i] - 1
        while j >= 0 and S[j] >= a[i] - 2*3600*10**9:   # FOMC windows <= 90 min, so look back 2h is enough
            if E[j] > a[i]: out[i] = True; break
            j -= 1
    return out

def main():
    S, E, cal = windows()
    Q1 = pd.read_csv(f'{PAR}/q1_touches.csv', parse_dates=['T', 'touch_ts'])
    Q2 = pd.read_csv(f'{PAR}/q2_briefs.csv', parse_dates=['T'])
    T = Q1[Q1.touched == True].copy()
    a = T.touch_ts.values.astype('datetime64[ns]').astype(np.int64)
    T['cal'] = overlaps(a, a + 2*3600*10**9, S, E)
    T['strength'] = pd.Categorical(T.strength, ['strong', 'medium', 'weak'])
    a2 = Q2['T'].values.astype('datetime64[ns]').astype(np.int64)
    Q2['cal'] = overlaps(a2, a2 + 2*3600*10**9, S, E)
    T.to_csv(f'{HERE}/q1_touches_calflag.csv', index=False); Q2.to_csv(f'{HERE}/q2_briefs_calflag.csv', index=False)
    md = ['# ADDENDUM 1 — calendar news variant (M5-News news_calendar_hist.csv)', '',
          'Filter only; levels, touches and outcomes are the original saved rows. Base/proxy tables are recomputed from the same files for side-by-side.', '']
    # removal counts
    rows = []
    for per in ('IS', 'OOS'):
        for kind in ('level', 'control'):
            x = T[(T.period == per) & (T.kind == kind)]
            rows.append(dict(set='Q1 touches', period=per, kind=kind, n=len(x), removed_calendar=int(x.cal.sum()), removed_pct=round(100*x.cal.mean(), 1),
                             removed_proxy=int(x.news.astype(bool).sum())))
        D = Q2[(Q2.period == per) & (Q2.bias != 'neutral')]
        for br in ('London', 'NY'):
            y = D[D.brief == br]
            rows.append(dict(set='Q2 directional briefs', period=per, kind=br, n=len(y), removed_calendar=int(y.cal.sum()), removed_pct=round(100*y.cal.mean(), 1),
                             removed_proxy=int(y.news.astype(bool).sum())))
    md.append('## Rows removed\n'); md.append(pd.DataFrame(rows).to_markdown(index=False))
    sm = lambda d: d[d.strength.isin(['strong', 'medium'])]
    for name, sub in (('base', T), ('proxy (touch inside 08:30ET/FOMC ±15)', T[~T.news.astype(bool)]), ('calendar', T[~T.cal])):
        md.append(f'\n## Q1 — {name}: by period × strength\n'); md.append(q1tab(sub, ['period', 'strength']).to_markdown(index=False))
    C = T[~T.cal]
    md.append('\n## Q1 — calendar: strong+medium by period × side\n'); md.append(q1tab(sm(C), ['period', 'side']).to_markdown(index=False))
    md.append('\n## Q1 — calendar: strong+medium by period × session\n'); md.append(q1tab(sm(C), ['period', 'session']).to_markdown(index=False))
    D = Q2[Q2.bias != 'neutral']
    for name, sub in (('base', D), ('proxy', D[~D.news.astype(bool)]), ('calendar', D[~D.cal])):
        md.append(f'\n## Q2 — {name}\n'); md.append(q2tab(sub, ['period']).to_markdown(index=False)); md.append(q2tab(sub, ['period', 'brief']).to_markdown(index=False))
        B = sub[sub.big == True]
        md.append(f'\n≥0.5 ATR moves only ({name}):\n'); md.append(q2tab(B, ['period', 'brief']).to_markdown(index=False))
    open(f'{HERE}/summary.md', 'w').write('\n'.join(md)); print('\n'.join(md))

if __name__ == '__main__': main()
