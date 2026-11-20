# Phase 4 PREREG — replay of the LIVE engines with the DaryaGold cost model (historical simulation)

Written 2026-11-20 ~18:00 Tehran, BEFORE any result of this replay was computed. Rules below are frozen.
Results are a **historical simulation**, not live trading and not a claim of edge. **Live strategy parameters are not changed
based on these results** (owner instruction 2026-11-20).

## What is tested
The exact live decision path, unmodified (`tools/levels.py` → `bias.py` → `regime.classify/decide` →
`brief._apply_broker_gates` (sizing + cost veto) → `risk_gate.evaluate`), i.e. the two live engines
(trend continuation, liquidity sweep / reversion) as of commit c80b513. Each engine is also reported separately.

## Data and no look-ahead
- Dukascopy 1-minute BID+ASK archive `/workspace/data/gold_1m/xauusd_1m.parquet`, 2020-01-01 23:00 → 2026-10-30 12:02 UTC.
- At evaluation instant t only 1-minute bars whose minute has closed (open ≤ t − 1 min) are visible. M5/M15/H1/H4 are
  resampled from those bars only; the last higher-TF bar is the partial bar, exactly as the live cache builds it.
- History depth per evaluation: 62 days (live brief keeps ≥ 35 days and the previous NY month).
- Leakage test (tests/test_backtest_phase4.py): decisions at t are identical when every bar after t is deleted or randomly
  perturbed; point-in-time frames equal a fresh resample of the truncated 1-minute data.

## Schedule (Tehran local time, historical Iranian DST via tzdata)
- DaryaGold session Mon–Fri 07:00 → 00:30 (next day). Evaluations every 15 min at 07:00, 07:15 … 00:15 (live cron cadence),
  each run at slot + 2 min (typical GitHub start delay). This includes the 07:00–11:15 window (live since 2026-11-20).
- Friday: no new entries in the last 2 h (from 22:30), as live. Weekends closed.
- Data stale (last 1-minute bar older than 10 min at t, e.g. holidays) → no evaluation (live: REJECTED stale data).
- News: no reliable historical calendar exists here → the news gate is INACTIVE in the replay (live has it). M5-News bias
  is not available historically → treated as absent (live default when the file has no bias).

## Orders and exits (bid prices; DaryaGold price = bid + offset cancels out)
- Signal = gate status APPROVED or APPROVED_WITH_WARNING. Limit order at the plan entry, valid 30 min, cut at the 00:30 close.
- Fill: BUY when a 1-minute bid low ≤ entry; SELL when a bid high ≥ entry; filled at the entry price (no price improvement).
- Stop loss: from the fill minute on; a bar opening beyond the stop fills at that open (gap).
- Take profit: **60-second rule** — a TP touch in the fill minute or the next minute is ignored (hold could be < 60 s);
  TP counts from fill minute + 2. A TP is filled at the TP price (no improvement). SL and TP in one bar → SL.
- Stop-out: if a bar's adverse move from entry reaches the DaryaGold stop-out loss (80% of initial margin: 800,000 toman for 1U,
  400,000 for 0.5U, i.e. $10 incl. costs) before SL, exit at that level (counted separately).
- Open position at the daily close: closed at the 00:29 bar close (the owner closes manually; the system never auto-closes live).
- One position at a time (max_positions 1): no new signal while an order is pending or a position is open.

## Cost model (DaryaGold, owner-confirmed 2026-11-20)
- 1U = 80,000 toman per $1, 0.5U = 40,000 per $1; margin 1,000,000 / 500,000; stop-out at 80% of margin.
- Fee 14,000 toman charged ONCE per trade; spread $0.25 per trade (× unit rate). Net = gross − spread − fee.
- R = net toman / (|entry − SL| × rate + spread + fee) (same as the live journal).
- Sizing: live `size_trade` with fixed equity 2,954,400 toman (the bot's current state equity; no compounding).
- Sensitivity (reported, not used for decisions): spread $0.50.

## Daily stop (as live)
3 losing trades in a session, or session net loss ≥ 20% of equity → no new signals that session. Counted as "daily-stop hits".

## Periods (frozen; OOS reported once, nothing tuned on it)
- In-sample (IS): sessions 2020-01-02 … 2023-12-31. Out-of-sample (OOS): 2024-01-01 … 2026-10-29.

## Reported
Per period × (all / per engine) × session (07:00–11:15, 11:15–16:15, 16:15–00:30 Tehran by signal time): signals, fills,
expired, trades, win rate, avg and total net R, net toman, max drawdown (toman and R on the fixed-size equity curve),
daily-stop hits, TP touches deferred by the 60 s rule, stop-outs, MFE/MAE (R) while open. Small samples are flagged (n < 30).
