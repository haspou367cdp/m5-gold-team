"""Build freqtrade OHLCV feathers for XAU/USDT:USDT from Dukascopy XAUUSD 1m BID (box files, read-only).
Window 2026-07-01 .. 2026-11-20 (warmup + Aug-20..Nov-20 test). Funding = 0, mark = bid OHLC."""
import pandas as pd
srcs=[]
h=pd.read_parquet('/workspace/data/gold_1m/xauusd_1m_bid.parquet').set_index('ts_utc')[['o','h','l','c','vol']]
h.columns=['open','high','low','close','volume']; srcs.append(h)
for p in ['/workspace/m5-gold-team/data/xauusd_1m.parquet','/workspace/m5-gold-team/analysis/real_trades_20261120/duka_1m_20261111_20261120.parquet']:
    d=pd.read_parquet(p); d=d[['o_b','h_b','l_b','c_b','v_b']]; d.columns=['open','high','low','close','volume']; srcs.append(d)
try:
    lv=pd.read_parquet('/workspace/data/gold_1m/xauusd_1m_live.parquet'); print('live cols',lv.columns.tolist()[:12], len(lv))
except Exception as e: print('live',e)
m=pd.concat(srcs); m=m[~m.index.duplicated(keep='last')].sort_index()
m=m.loc['2026-07-01':'2026-11-21'].dropna(); m=m[m.volume>=0]
gaps=m.index.to_series().diff(); print('1m rows',len(m),m.index[0],m.index[-1]); print('gaps>60min (non-weekend):'); 
g=gaps[(gaps>pd.Timedelta('60min'))&(gaps<pd.Timedelta('40h'))]; print(g.to_string())
out='user_data/data/okx/futures/'
def save(df,name):
    x=df.reset_index().rename(columns={'ts_utc':'date','index':'date'}); x['date']=pd.to_datetime(x['date'],utc=True); x.to_feather(out+name)
def rs(rule):
    return m.resample(rule,label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
save(m,'XAU_USDT_USDT-1m-futures.feather')
m5=rs('5min'); save(m5,'XAU_USDT_USDT-5m-futures.feather'); print('5m rows',len(m5))
for tf,r in [('1h','60min'),('4h','240min'),('8h','480min')]:
    x=rs(r); save(x,f'XAU_USDT_USDT-{tf}-mark.feather')
    f=x.copy(); f[['open','high','low','close']]=0.0; f['volume']=0.0
    f=f.reindex(pd.date_range(f.index[0],f.index[-1],freq=r)).fillna(0.0); save(f,f'XAU_USDT_USDT-{tf}-funding_rate.feather')
