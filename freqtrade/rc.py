"""Random-entry control, in-process freqtrade Backtesting (1m detail, protections on).
usage: python rc.py WINDOW N_TARGET SL_ATR TP_R TIME_STOP SEEDS -> net toman per seed (1U, after costs)"""
import os, sys, json, copy, numpy as np, pandas as pd
from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode
from freqtrade.optimize.backtesting import Backtesting
from report import stats
win, n_target, sl, tpr, ts, seeds = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6])
os.environ.update(RC_SL=sl, RC_TPR=tpr, RC_TS=ts)
args = {'config': ['config.json', f'win_{win}.json'], 'strategy': 'XauRandom', 'timerange': '20260715-20261121',
        'timeframe_detail': '1m', 'enable_protections': True, 'export': 'none'}
cfg = Configuration(args, RunMode.BACKTEST).get_config()
bt = Backtesting(cfg)
data, tr = bt.load_bt_data()
strat = bt.strategylist[0]
eligible = None
def run(p, seed):
    os.environ['RC_P'] = str(p); os.environ['RC_SEED'] = str(seed)
    bt.backtest_one_strategy(strat, data, tr)
    return bt.all_bt_content[strat.get_strategy_name()]['results']
# calibrate p to the candidate's trade count with seed 0
p = 0.02
for _ in range(4):
    r = run(p, 999); n = len(r)
    if n == 0: p *= 3; continue
    p = p * n_target / n
    if abs(n - n_target) / n_target < 0.1: break
rows = []
for s in range(seeds):
    r = run(p, s); st = stats(r); st['seed'] = s; rows.append(st)
df = pd.DataFrame(rows)
print(json.dumps({'window': win, 'p': p, 'n_target': n_target, 'sl_atr': sl, 'tp_r': tpr, 'time_stop': ts,
                  'mean_net_toman': int(df.net_toman.mean()), 'median_net_toman': int(df.net_toman.median()),
                  'min': int(df.net_toman.min()), 'max': int(df.net_toman.max()), 'mean_pf': round(df.pf.mean(), 2),
                  'mean_trades': round(df.trades.mean(), 1), 'mean_win': round(df.win.mean(), 1), 'nets': df.net_toman.tolist()}))
