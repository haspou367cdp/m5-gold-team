# PREREG gc_vp_hf — GC (COMEX) volume-profile levels on XAUUSD M5, confirmation-entry test
**EXPLORATORY and UNDERPOWERED. This study CANNOT PASS. It can only show a direction of evidence ("positive hint" or "no evidence").**
Written 2026-11-13 08:23:07 +0330 Asia/Tehran (box `date`), BEFORE any GC level, touch, trade, control or outcome was computed.
Owner: M5-Journal (independent run). Requested by Boti after owner (pouhasaa) approval of a small exploratory GC volume-profile test.
Trials on the "levels" idea so far: levels_bias (levels.py v1), levels_v2_build, levels_v2_confirm, levels_v2_gc (real-volume swap);
this is trial 5 on the family (none passed). Holm here is only across this study's 2 hypotheses; the family-wide count is disclosed.

## What I looked at before writing this (STEP 0, data hygiene only; logs step0.log, step0b.log)
- GC file: data/gc_free_sources/hf_commodity_futures_sample/data/minute/part-00000.parquet, contract_name == "COMEX Gold Futures":
  261,337 rows (GCF26 18,921; GCG26 106,332; GCH26 30,180; GCJ26 105,904). Weekly volumes per contract.
- Timezone: GC naive timestamps vs Dukascopy XAUUSD mid 1m log-returns, lags -12h..+12h in 30-min steps then 1-min steps around the
  peak. Raw peak at GC_ts + 360 min (corr 0.707; +300 min 0.281 = the post-DST part). => timestamps are **America/Chicago local
  time (CST/CDT)**. After tz_localize('America/Chicago') -> UTC: lag-0 corr 0.983 (pre-DST, n=100,152) and 0.985 (post-DST, n=20,291);
  all other lags |corr| < 0.04. Inferred, not documented by the data source.
- Front-month series (gc_front_1m.parquet): the naive rule ("roll when the next contract's daily volume exceeds current") rolled on
  single-digit-volume noise days in Apr 2025, when all four contracts were deferred. Hygiene fix (before any outcome): liquid window =
  Tehran dates where the max single-contract daily volume >= 20,000 => 2025-11-21..2026-03-27; inside it start with the highest-volume
  contract and roll forward only, to a later expiry whose daily volume exceeds the current one. Result: GCG26 2025-11-21..2026-01-27,
  GCJ26 from 2026-01-28. 120,997 1m bars, 107 Tehran dates, median 1,378 bars/day; 18 dates inside the window are below 20k (holidays,
  partial days). **No back-adjustment**: every level is mapped to spot through a rolling basis measured on the same contract, so the
  roll jump never enters a level (profiles never span the roll: a profile uses only bars of the contract that is front on each bar's date;
  if a profile window contains bars of 2 contracts, it is built only from the contract that is front at T).
- XAUUSD: /workspace/data/gold_1m/xauusd_1m.parquet (Dukascopy 1m bid/ask, bad_quote filtered), ends 2026-10-30, so it covers the GC window.
- levels.py comparison input: backtest/levels_bias/snapshots.pkl = point-in-time output of the UNCHANGED tools/levels.py at every
  11:15/16:15 Tehran weekday 2020-01-02..2026-10-30 (built 2026-11-12 by levels_bias/rebuild.py; tools_used.sha256 there matches today's
  tools/levels.py 6f2f6ba0..., m5lib.py c3761757..., fetch_xauusd.py 4176486e...). Reused instead of re-running (same code, same data;
  saves time). I have not looked at its levels or outcomes for the GC window.

## Snapshots
11:15 and 16:15 Asia/Tehran on weekdays, 2025-11-21..2026-03-27. Eligible: m5lib.market_open(T), last XAU 1m bar <= 15 min before T,
>= 30 minutes with both a GC front 1m close and an XAU 1m bar in [T-60min, T) (basis), and at least one GC profile available.
11:15 = "London" split, 16:15 = "NY" split.

## GC volume-profile levels (real GC volume, front contract at T)
- Profile: each GC 1m bar's volume is spread uniformly over the $0.10 bins from floor(low/0.1) to floor(high/0.1) (inclusive).
  POC = highest-volume bin (tie -> bin nearest the profile's volume-weighted mean price; then the lower one). Price of a bin = bin low + 0.05.
  Value area 70%: start at POC; repeatedly compare the next bin above and the next bin below and add the larger (tie -> above; if one side
  is exhausted add the other) until >= 70% of total volume. VAH = top bin's price, VAL = bottom bin's price.
- Prior day (PD): previous gold trading day, m5lib.previous_trading_day_start(trading_day_start(T)) .. +23h (18:00->17:00 NY). Needs >= 300 GC bars.
- Prior session (PS): the most recent session that is fully completed at T, of Asia / London / NY as defined by m5lib.sessions_for
  (Asia 00:00 UTC->07:00 London; London 07:00 London->08:30 NY; NY 08:30->17:00 NY; checked over today's and the previous weekdays'
  sessions). Needs >= 60 GC bars. In practice at 11:15 and at 16:15 Tehran this is today's Asia session (London ends 08:30 NY = 17:00
  Tehran in winter), stated in advance; so PS is the same profile at both snapshots of a day.
- HVN/LVN: **skipped** (keeps the run fast; no simple pre-declared definition chosen). Max 6 levels per T: PD_POC, PD_VAH, PD_VAL, PS_POC, PS_VAH, PS_VAL.
- Basis(T) = median(GC close - XAU (bid_c+ask_c)/2) over minutes in [T-60min, T) present in both. XAU level = GC level - basis(T).
  Basis logged per snapshot (basis_log.csv); distribution reported.
- Merge: XAU-mapped levels within tol = max(0.5, 0.25*ATR_M5(T)) of each other (sorted, chain) are merged into one level at their mean
  (labels joined). Side: resistance if level > price_T else support; price_T = last XAU bid close before T.
- ATR_M5(T) = Wilder ATR(14) of XAU bid M5 bars completed before T (same formula as tools/levels.py atr()).
- Eligible level: |level - price_T| >= 0.3*ATR_M5(T).

## Touch and entries (no entry on the touch itself)
- Touch = first XAU bid M5 bar opening >= T within 4h (clock) with high >= level (resistance) / low <= level (support). Touch bar = k.
- H_rev (reversal): first of bars k+1..k+6 whose bid close is back on the rejection side (resistance: close < level; support: close > level).
  Enter at the bid open of the next M5 bar, fading (resistance short, support long).
- H_cont (continuation): first of bars k+1..k+6 whose bid close is beyond the level by >= 0.25*ATR_M5(T) (resistance: close >= level+0.25ATR;
  support: close <= level-0.25ATR). Enter at the next M5 bar open in the breakout direction.
- Each hypothesis is evaluated independently on the same touches (a touch can give a rev trade, a cont trade, both or neither).
  No confirmation within 6 bars -> no trade. The entry bar must open within 15 min after the confirming bar closes, else no trade.
- Trade: stop 1.0*ATR_M5(T) from entry, target 1.5*ATR_M5(T); time stop = exit at the bid close of the 24th M5 bar counting the entry bar as 1.
  Path on XAU 1m bid high/low from the entry 1m bar; stop and target in the same 1m bar -> stop.
- Costs: fixed $0.36 spread + $0.20 slippage = $0.56 per round trip. R = (gross PnL - 0.56) / ATR_M5(T).
- Recorded: MAE/MFE in ATR (entry to exit), bars from touch to confirmation ("time to reversal/acceptance"), exit type.

## Controls
One per eligible level, at the same T (so session/hour, ATR tercile and trend state match by construction; ATR tercile within the study
period and trend = H1 bid EMA20 vs EMA50 recorded and balance reported), same side, distance d*(1+0.15k), k order +1,-1,+2,-2,+3,-3; first
candidate that is >= 0.3*ATR from price_T and > tol from every (merged) GC level at T. Same touch / entry / trade rules.

## Primary metric and reading (per hypothesis, separately)
Paired mean net R per trade = level R - control R over pairs where both sides traded. Day-block bootstrap (resample Tehran dates of T), 5000 reps,
seed 20261113, one-sided p = share of bootstrap diffs <= 0. Holm across H_rev and H_cont.
**Direction-of-evidence reading (pre-declared):** "positive hint" only if paired diff > 0 AND Holm-adjusted day-bootstrap p < 0.10 AND paired diff > 0 in
both halves (half A: T date < 2026-01-24 Tehran; half B: >= 2026-01-24). Otherwise "no evidence". Never "PASS".
Secondary (descriptive): unpaired level vs control, win rate (R>0), PF, MAE/MFE (ATR), time to confirmation, exit types, splits London (11:15) /
NY (16:15) and inside vs outside news (trade holding interval [entry, exit] overlaps a high-impact window in data/news_calendar_hist.csv,
Tehran times; tools/news_windows.py only reads the live data/news_windows.json, so the historical CSV is used), per level type (PD/PS, POC/VAH/VAL).

## Comparison: tools/levels.py on the same snapshots
Levels from backtest/levels_bias/snapshots.pkl (unchanged levels.py output) at the same eligible T; all levels (primary comparison) and strong
(score >= 6) as secondary; same eligibility, touch, both entry rules, costs, controls (control must be > levels.py tol from every levels.py level
at T), same paired statistic and bootstrap. Also reported: GC-level paired diff minus levels.py paired diff (descriptive only).

## Disclosure / limits stated in advance
- No aggressor / order-flow data in the sample => order flow skipped. Portara MGC snippet format check skipped (time).
- Timezone inferred (America/Chicago) from return correlation; ~4 months, one regime; basis includes carry and moves at the roll.
- Fixed costs (not the actual spread); bid-path approximation; fills at next-bar open assumed.
- No parameter is tuned after outcomes. If a bug is found after running, only the bug is fixed, documented as a dated deviation, and the run repeated once.
