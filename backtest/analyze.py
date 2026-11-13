import numpy as np, pandas as pd, json
OUT='/workspace/m5-gold-team/backtest'
SPLIT=pd.Timestamp('2024-01-01',tz='UTC')
NAMES={1:'1 Sweep+reversal',2:'2 Break&retest',3:'3 EMA pullback',4:'4 Asian range BO'}
T=pd.read_csv(f'{OUT}/trades_all_variants.csv', parse_dates=['sig_bar_ts','entry_ts','exit_ts'])
hr=T.entry_ts.dt.hour
T['session']=np.select([hr<7,hr<12,hr<21],['Asia (03:30-10:30 Teh)','London (10:30-15:30 Teh)','NewYork (15:30-00:30 Teh)'],'Late (00:30-03:30 Teh)')
T['year']=T.entry_ts.dt.year; T['period']=np.where(T.entry_ts<SPLIT,'IS','OOS')
T['tday']=(T.entry_ts.dt.tz_convert('America/New_York')+pd.Timedelta('7h')).dt.date
T['hold_min']=(T.exit_ts-T.entry_ts).dt.total_seconds()/60

def met(g, col='R'):
    g=g.sort_values('exit_ts'); r=g[col].values
    if len(r)==0: return dict(n=0)
    cum=np.cumsum(r); dd=(np.maximum.accumulate(np.r_[0,cum])[1:]-cum).max()
    pos=r[r>0].sum(); neg=-r[r<0].sum()
    t = r.mean()/(r.std(ddof=1)/np.sqrt(len(r))) if len(r)>2 and r.std()>0 else np.nan
    return dict(n=len(r), win=round((r>0).mean()*100,1), avgR=round(r.mean(),3), PF=round(pos/neg,2) if neg>0 else np.inf,
                maxDD=round(dd,1), totR=round(r.sum(),1), t=round(t,2), med_risk=round(g.risk.median(),2), med_hold_min=round(g.hold_min.median(),0))

def table(df, by, col='R'):
    rows=[]
    for k,g in df.groupby(by): rows.append({**dict(zip(by if isinstance(by,list) else [by], k if isinstance(k,tuple) else (k,))), **met(g,col)})
    return pd.DataFrame(rows)

def portfolio(df, max_open=2, max_losses=3, day_stop=-2.0, col='R'):
    """team risk rules across setups: max open, stop day after N losses or day loss<=day_stop (closed trades only)."""
    df=df.sort_values('entry_ts').reset_index(drop=True); keep=[]; open_=[]; byday={}
    E=df.entry_ts.values; X=df.exit_ts.values; D=df.tday.values; V=df[col].values
    for i in range(len(df)):
        open_=[j for j in open_ if X[j]>E[i]]
        if len(open_)>=max_open: continue
        day=[j for j in byday.get(D[i],[]) if X[j]<=E[i]]
        if max_losses and sum(1 for j in day if V[j]<0)>=max_losses: continue
        if day_stop is not None and sum(V[j] for j in day)<=day_stop: continue
        keep.append(i); open_.append(i); byday.setdefault(D[i],[]).append(i)
    return df.iloc[keep]

md=['# M5 Gold Scalp backtest — results','',open(f'{OUT}/PREREG.md').read().split('\n',2)[2],'']
md.append('Data: DataHunter\'s Dukascopy-derived 1m BID+ASK feed, /workspace/data/gold_1m/xauusd_1m.parquet, 2020-01-01 23:00 → 2026-10-30 12:02 UTC. R includes real per-bar spread; NO commission added.\n')
summ=[]
for v,gv in T.groupby('variant', sort=False):
    for per in ['IS','OOS']:
        gp=gv[gv.period==per]
        for s in [1,2,3,4]:
            summ.append(dict(variant=v, period=per, setup=NAMES[s], **met(gp[gp.setup==s])))
        summ.append(dict(variant=v, period=per, setup='ALL (each setup independent)', **met(gp)))
S=pd.DataFrame(summ); S.to_csv(f'{OUT}/summary_table.csv',index=False)
base=T[T.variant=='base']
md.append('## Main table (base and sensitivities), R per trade, 50/50 TP1 1.5R / TP2 2.5R\n'); md.append(S.to_markdown(index=False))
md.append('\n## Base by session\n'); md.append(table(base.assign(setup=base.setup.map(NAMES)),['period','setup','session']).to_markdown(index=False))
md.append('\n## Base by year\n'); md.append(table(base.assign(setup=base.setup.map(NAMES)),['setup','year']).to_markdown(index=False))
md.append('\n## Base ALL setups by session / year\n'); md.append(table(base,['period','session']).to_markdown(index=False)); md.append(table(base,['year']).to_markdown(index=False))
md.append('\n## Base exit reasons\n'); md.append(pd.crosstab([base.period,base.setup.map(NAMES)],base.exit).to_markdown())
# portfolio with team rules
P=portfolio(base)
md.append('\n## Portfolio, team risk rules (all 4 setups, max 2 open, stop day after 3 losses or -2R)\n')
md.append(table(P,['period']).to_markdown(index=False))
# $500 account
A=T[T.variant=='acct500_R<=5_TP1'].copy(); A['usd']=A.pnl_px*1.0   # 0.01 lot = 1 oz
A=A.rename(columns={})
md.append('\n## $500 account, 0.01 lot (1 oz; $1 move = $1), skip R>$5 incl. spread, single exit at TP1 1.5R\n')
md.append('Per setup (independent):\n'); md.append(table(A.assign(setup=A.setup.map(NAMES)),['period','setup']).to_markdown(index=False))
rows=[]
for label,cap in [('no daily cap (max 2 open only)',None),('$10/day cap: no new trades after day P&L <= -$10',-10.0)]:
    PA=portfolio(A, max_open=2, max_losses=0, day_stop=cap, col='usd')
    for per,g in PA.groupby('period'):
        dd=g.groupby('tday').usd.sum()
        cum=g.sort_values('exit_ts').usd.cumsum().values; mdd=(np.maximum.accumulate(np.r_[0,cum])[1:]-cum).max()
        rows.append(dict(rule=label, period=per, trades=len(g), net_usd=round(g.usd.sum(),1), worst_day_usd=round(dd.min(),2),
                         days_over_10_loss=int((dd< -10).sum()), days_traded=len(dd), maxDD_usd=round(mdd,1),
                         win=round((g.usd>0).mean()*100,1), PF=round(g.usd[g.usd>0].sum()/-g.usd[g.usd<0].sum(),2)))
md.append('\nPortfolio of all 4 setups (max 2 open):\n'); md.append(pd.DataFrame(rows).to_markdown(index=False))
md.append('\nNote: with 2 positions open the cap is checked on closed trades only, so a day can still end below -$10.\n')
# bias check
B=pd.read_csv(f'{OUT}/bias_check.csv')
md.append('\n## Bias check (info): H1 EMA20/50 and M15 EMA20/50 agree -> direction; hit = same sign as BID close 2h later\n')
md.append(B.round(3).to_markdown(index=False))
md.append('\nmeta: '+json.dumps(json.load(open(f'{OUT}/meta.json'))))
open(f'{OUT}/summary.md','w').write('\n'.join(md))
base.to_csv(f'{OUT}/trades_base.csv',index=False)
print(S.to_string()); print(pd.DataFrame(rows).to_string()); print(B.round(3).to_string())
