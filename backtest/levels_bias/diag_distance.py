"""Diagnostic (not pre-registered): level vs control reversal rate within distance-from-price bins (strong+medium)."""
import pandas as pd, numpy as np
q=pd.read_csv('q1_touches.csv'); t=q[(q.touched==True)&q.strength.isin(['strong','medium'])].copy()
t['dbin']=pd.cut(t.dist_atr,[0.3,1,2,4,8,100])
r=t.assign(rev=t.outcome.eq('reversal')).groupby(['period','dbin','kind'],observed=True).rev.agg(['size','mean']).unstack('kind')
r.columns=[f'{a}_{b}' for a,b in r.columns]; r['diff_pp']=100*(r.mean_level-r.mean_control)
print(r.round(3).to_markdown()); open('diag_distance.md','w').write('# Diagnostic (not pre-registered): reversal rate by distance-from-price bin (ATR units), strong+medium\n\n'+r.round(3).to_markdown())
