"""Collect per-window stats for tuned strategies -> results/summary.csv and results/summary.md (ranked by OOS net toman)."""
import sys, json, pandas as pd
from report import load, stats
strats = sys.argv[1:]
rows = []
for s in strats:
    for w in ['is', 'oos', 'full', 'm1', 'm2', 'm3']:
        try:
            t = load(f'user_data/bt_{w}', s)
        except Exception as e:
            t = pd.DataFrame()
        r = stats(t) if len(t) else dict(trades=0)
        r.update(strategy=s, window=w); rows.append(r)
df = pd.DataFrame(rows)
import os; os.makedirs('results', exist_ok=True)
df.to_csv('results/summary.csv', index=False)
oos = df[df.window == 'oos'].set_index('strategy').net_toman.sort_values(ascending=False)
df['rank_oos'] = df.strategy.map({s: i + 1 for i, s in enumerate(oos.index)})
df = df.sort_values(['rank_oos', 'window'])
cols = ['rank_oos', 'strategy', 'window', 'trades', 'win', 'pf', 'net_toman', 'maxdd_toman', 'avg_hold_min', 'sl_exits', 'roi', 'time']
open('results/summary.md', 'w').write(df[cols].to_markdown(index=False))
print(df[cols].to_string(index=False))
