# freqtrade research: XAUUSD M5 scalping families (DaryaGold costs), 2026-08-20 .. 2026-11-20

Research only. No live trading, no exchange keys, nothing deployed; Supabase bot untouched.

## Setup
- freqtrade 2026.10 in venv `/workspace/ftvenv` (`pip install "freqtrade[hyperopt]"`).
- Data: Dukascopy XAUUSD 1-minute **bid** (box files `/workspace/data/gold_1m/xauusd_1m_bid.parquet` + repo `data/xauusd_1m.parquet`
  + `analysis/real_trades_20261120/duka_1m_20261111_20261120.parquet`), converted by `build_data.py` to freqtrade feather
  as the dummy pair `XAU/USDT:USDT` (okx futures layout; funding = 0, mark = bid). Last bar 2026-11-20 19:18 Tehran.
- Data loaded from 2026-07-15 (warm-up for ADR20/ATR median); entries only inside the window set by `win_*.json` (`trade_from`/`trade_to`).
- Backtests use `--timeframe-detail 1m`, max 1 open trade, protections on (CooldownPeriod + StoplossGuard per day).
- Costs: freqtrade fee = 0; every report subtracts **$0.425 per 1U trade** ($0.25 spread + 14,000/80,000 fee), toman = $ × 80,000.
- DaryaGold rules: entries 07:00–00:30 Tehran Mon–Fri, no new entry Fri ≥ 23:30; hard SL on every trade (absolute price in `enter_tag`),
  60 s minimum hold for TP (SL exempt), SL + ATR ≤ buf_max (≤ $9, stop-out), TP ≤ min(remaining ADR, tp_atr × ATR), time stop 20–45 min.

## Families (`user_data/strategies/xau_families.py`)
XauZone (pine zones), XauS2 (momentum with H1 trend, L1 level-behind gate), XauS3 (counter-trend bounce), XauPullback (EMA20 pullback in H1+M15 trend),
XauORB (London opening range 10:30–11:00 Tehran breakout), XauVWAP (VWAP reversion), XauMR (RSI/BB reversion), XauRandom (control).

## Protocol
- Hyperopt (`run_hyperopt.sh`, 200–300 epochs, NSGA-III, `-j 1`, loss `XauNetLoss` = daily Sharpe of net $ + 0.5·PF, min 30 trades)
  on **2026-08-20..2026-10-20 only**. Tuned params: `best_params_is.json`, `user_data/strategies/xau_tuned.py`.
- OOS 2026-10-21..2026-11-20 was never used for tuning. `eval_windows.sh` → `final_report.py` → `results/summary.{csv,md}`.
- Random control (`rc.py`): same hours/filters/protections/exit machinery, random side and time, SL = sl_atr×ATR, TP = tp_r×SL,
  trade count calibrated to the candidate; 40 seeds → `results/random_control.csv`.

## Result
See `results/RESULTS.md`. Short version: every family is profitable in-sample after tuning, and 6 of 7 lose out-of-sample.
The only OOS-positive one (S2 momentum short) has 16 OOS trades, PF 1.13, and sits at the 62nd percentile of random — not an edge.
