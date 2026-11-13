"""STEP 0 data hygiene only (no outcomes): GC coverage, timezone inference vs Dukascopy XAUUSD, front-month continuous series."""
import sys; sys.dont_write_bytecode = True
import numpy as np, pandas as pd
SRC = '/workspace/m5-gold-team/data/gc_free_sources/hf_commodity_futures_sample/data/minute/part-00000.parquet'
OUT = '/workspace/m5-gold-team/backtest/gc_vp_hf'
d = pd.read_parquet(SRC); g = d[d.contract_name == 'COMEX Gold Futures'].copy()
g['ts'] = pd.to_datetime(g.timestamp, unit='ms', utc=True)
print('GC rows', len(g)); print(g.groupby('contract_code').agg(n=('ts', 'size'), first=('ts', 'min'), last=('ts', 'max'), vol=('volume', 'sum')))
g['date'] = g.ts.dt.date
dv = g.groupby(['date', 'contract_code']).volume.sum().unstack(fill_value=0)
# front month: start with highest-volume contract on the first day; roll forward (never back) when the next listed contract's daily volume exceeds current
order = ['GCF26', 'GCG26', 'GCH26', 'GCJ26']; cur = dv.iloc[0].idxmax(); fm = {}
for day, r in dv.iterrows():
    i = order.index(cur)
    if i + 1 < len(order) and r[order[i+1]] > r[cur]: cur = order[i+1]
    fm[day] = cur
fm = pd.Series(fm, name='front'); print('roll dates:'); print(fm[fm != fm.shift()])
g = g[g.contract_code == g.date.map(fm)].sort_values('ts').drop_duplicates('ts')
c = g.set_index('ts')[['open', 'high', 'low', 'close', 'volume', 'contract_code']]
c.to_parquet(f'{OUT}/gc_front_1m.parquet')
dd = c.groupby(c.index.date).agg(bars=('close', 'size'), vol=('volume', 'sum'), contract=('contract_code', 'first'))
dd.to_csv(f'{OUT}/gc_front_daily_coverage.csv')
print('front series', c.index.min(), c.index.max(), 'bars', len(c))
print('daily bars by month (median):'); print(dd.groupby(pd.to_datetime(dd.index).to_period('M')).agg(days=('bars', 'size'), med_bars=('bars', 'median'), med_vol=('vol', 'median')))
# timezone: correlate 1m returns at shifts
x = pd.read_parquet('/workspace/data/gold_1m/xauusd_1m.parquet', columns=['ts_utc', 'bid_c', 'ask_c', 'bad_quote'])
x = x[~x.bad_quote]; x['ts_utc'] = x.ts_utc.astype('datetime64[ns, UTC]'); x = x.set_index('ts_utc')
mid = ((x.bid_c + x.ask_c)/2); mid = mid[(mid.index >= c.index.min() - pd.Timedelta(days=1)) & (mid.index <= c.index.max() + pd.Timedelta(days=1))]
# use dense period only (days with >=600 front bars) and 1m log returns of consecutive minutes
dense = set(dd.index[dd.bars >= 600]); cc = c[np.isin(c.index.date, list(dense))].close
full = pd.date_range(cc.index.min().floor('min'), cc.index.max().ceil('min'), freq='1min', tz='UTC')
rg = np.log(cc.reindex(full)).diff(); rx = np.log(mid.reindex(full.union(full + pd.Timedelta(hours=13)).union(full - pd.Timedelta(hours=13)))).diff()
res = []
for lag in range(-12*60, 12*60+1, 30):
    s = rx.reindex(full + pd.Timedelta(minutes=lag)).values; ok = ~np.isnan(rg.values) & ~np.isnan(s)
    res.append((lag, ok.sum(), np.corrcoef(rg.values[ok], s[ok])[0, 1] if ok.sum() > 100 else np.nan))
R = pd.DataFrame(res, columns=['lag_min', 'n', 'corr']); R.to_csv(f'{OUT}/tz_lag_corr.csv', index=False)
b = R.loc[R['corr'].idxmax()]; print('best 30m-step lag', dict(b)); print(R.sort_values('corr', ascending=False).head(5))
res2 = []
for lag in range(int(b.lag_min) - 30, int(b.lag_min) + 31):
    s = rx.reindex(full + pd.Timedelta(minutes=lag)).values; ok = ~np.isnan(rg.values) & ~np.isnan(s)
    res2.append((lag, ok.sum(), np.corrcoef(rg.values[ok], s[ok])[0, 1]))
R2 = pd.DataFrame(res2, columns=['lag_min', 'n', 'corr']); R2.to_csv(f'{OUT}/tz_lag_corr_fine.csv', index=False)
print('fine 1m lags top', R2.sort_values('corr', ascending=False).head(4))
