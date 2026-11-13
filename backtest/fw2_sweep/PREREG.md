# PREREG fw2_sweep — Framework v2 engine (2): liquidity sweep / mean reversion
Written 2026-11-13 12:59 Asia/Tehran (box `date` 12:59:31 +0330), BEFORE any trade, control or outcome was computed and BEFORE any evaluator was written.
Owner: M5-Journal. Requested by Boti after the owner (pouhasaa) adopted framework v2.
This is trial 1 of engine (2) in the fw2 family, tested SEPARATELY from engine (1) trend continuation (see ../fw2_trend/PREREG.md). Do not pool trades with fw2_trend. Holm is within this study's hypothesis family only. Prior levels/bias trials (levels_bias, levels_v2_build, levels_v2_confirm FAILED on net R vs matched controls 2020-2024; levels_v2_gc and gc_vp_hf were exploratory / fragile, no PASS) are disclosed as context and are NOT in this Holm family.
Parameters below are frozen now. 2020-2023 is a sanity period only (counts, no crash); NOTHING is tuned on IS or OOS. No order flow. No GC. Do not call tools/levels.py or brief.py. POC below is a Dukascopy TICK-VOLUME PROXY, not COMEX volume — say so in every report.

## Data
- Source: /workspace/data/gold_1m/xauusd_1m.parquet (Dukascopy freeserv 1m bid/ask). Filter bad_quote==True (drop). File ends 2026-10-30; first bar 2020-01-01 23:00 UTC. Require 50 completed H1 and 50 completed M15 bid bars before a signal (early Jan 2020 skipped).
- Resample M5 / M15 / H1 from 1m, label="left", closed="left", UTC. Signal OHLC = BID unless a fill rule says ASK.
- Volume for VWAP and POC: Dukascopy bid_vol+ask_vol (tick/quote volume proxy, not exchange volume).
- ATR_M5 / ATR_M15 / ATR_H1 (T) = Wilder ATR(14) on completed bid bars of that TF strictly before T: TR = max(h-l, |h-prev_c|, |l-prev_c|), ewm(alpha=1/14, adjust=False).mean(). Same formula as tools/levels.py atr(); that file is not modified or called.
- Market hours: m5lib.market_open (Sun 18:00 NY to Fri 17:00 NY, daily break 17:00-18:00 NY). No signals when closed.

## Sessions (DST-aware, code-ready)
Identical to fw2_trend: m5lib.sessions_for(t). Asia = 00:00 UTC -> 07:00 Europe/London; London = 07:00 London -> 08:30 NY; NY = 08:30 NY -> 17:00 NY.
Tehran guide (evaluation uses the UTC bounds). Iran used UTC+4:30 in spring-summer through 2022, then UTC+3:30 year-round; UK/US DST still apply.
- Winter (UK GMT, US EST, Iran +03:30): Asia 03:30-10:30, London 10:30-17:00, NY 17:00-01:30 Tehran.
- Summer (UK BST, US EDT, Iran +03:30): Asia 03:30-09:30, London 09:30-16:00, NY 16:00-00:30 Tehran. Add +1h to Tehran clocks in Iran-DST summers 2020-2022.
Entries in London and NY only. Asia H/L are sweepable only after Asia has ended. London H/L are sweepable only after London has ended (NY session). Last allowed entry: the M5 bar must OPEN strictly before session end.

## Range-regime filter (required)
At decision time T (close of the M5 bar under test; only bars with close <= T):
- (R1) |EMA20_H1 − EMA50_H1| < 0.25 * ATR_H1(T), where EMA20/EMA50 = ewm(span=20 or 50, adjust=False) of H1 bid close (50 completed H1 required).
- (R2) The last completed H1 bid close sits strictly inside the high/low of the prior 12 completed H1 bars excluding itself (range of bars t−12 .. t−1; close of t is < that high and > that low). If it equals or breaks that 12-bar high or low, the regime is not range.
Both R1 and R2 must hold. This is independent of fw2_trend's direction filter (a bar may theoretically be eligible in one, both, or neither; studies stay separate).

## Sweep levels
Eligible at T, completed data only:
- PDH / PDL of the previous gold trading day (m5lib.trading_day_start / previous_trading_day_start: 18:00 NY -> 17:00 NY).
- Asia session high / low of the current trading day, only after Asia has ended.
- London session high / low of the current trading day, only after London has ended.
- Equal highs / equal lows on M15: confirmed M15 swing highs (fractal w=2, same definition as below) among the last 48 completed M15 bars. Two or more swings whose prices lie within 0.15 * ATR_M15(T) form a cluster (transitive: join if any pair is within tol). Equal-high level = the MAXIMUM high in the cluster (the liquidity pool extreme). Equal-low level = the MINIMUM low in the cluster. Each cluster of size >= 2 is one level. Isolated swings are not equal-H/L levels (they are not used unless they coincide with PDH/PDL/session H/L).

## Sweep, close-back-inside, M5 BOS (reversal)
Tolerance / excursion caps are in ATR_M5(T_S) at the sweep bar's close.
High sweep (sets up a short):
- Sweep bar S: M5 bid high >= level + 0.10 * ATR_M5 AND M5 bid high <= level + 0.50 * ATR_M5. A high > level + 0.50 ATR is a breakout, not a sweep (no trade on this level until a later qualifying sweep).
- Close back inside: bid close of S is < level, OR bid close of S+1 or S+2 is < level. The first such bar is C. If an M15 bid close prints strictly above the level at or before C, the event is a break, not a sweep — cancel (do not treat the sweep bar's low as a reversal; same-bar OHLC order is unknown).
- If S itself closes >= level and neither S+1 nor S+2 closes back inside, the sweep dies.
Low sweep (sets up a long): mirrored (low <= level − 0.10 ATR and >= level − 0.50 ATR; close back > level; M15 close below the level cancels).
M5 BOS in the reversal direction, window C+1 .. C+6:
- Fractal width w=2 (5-bar). Bar i is a confirmed swing high when i+2 has closed, iff high[i] > high[j] for all j in {i−2,i−1,i+1,i+2} (strict). Swing low: low[i] < all four neighbours (strict). Only confirmed swings (no look-ahead).
- After a high sweep: bearish BOS = M5 bid close < the most recent confirmed M5 swing low frozen before this bar. First such bar in the window is R (confirm).
- After a low sweep: bullish BOS = M5 bid close > the most recent confirmed M5 swing high, same freeze.
If no BOS by C+6, the setup dies. One setup per (level, sweep S); the first confirm wins.

## Entry, SL, TP, filters
- Entry: market fill at the OPEN of the next M5 bar after R closes. Longs fill at ASK open (o_a); shorts fill at BID open (o_b). Missing quote, or next M5 open not within 5 minutes of R's close -> skip.
- SL beyond the sweep extreme: short SL = max M5 bid high from bar S through bar C (inclusive) + 0.10 * ATR_M5(T_R). Long SL = min M5 bid low from S through C − 0.10 * ATR_M5(T_R). T_R = close of R. Wrong-side SL -> skip.
- TP candidates in the trade direction, from the following set (skip a candidate that is missing or on the wrong side of fill):
  (i) Current-session VWAP, anchored at the current session start (sessions_for). Typical = (bid_h+bid_l+bid_c)/3 of each 1m bar; vol = bid_vol+ask_vol; VWAP = cumsum(typical*vol)/cumsum(vol) through the last completed 1m before T_R. Unavailable if cum vol = 0.
  (ii) Prior-day tick-volume POC (PROXY, not COMEX): all 1m bars of the previous gold trading day (18:00 NY -> 17:00 NY). Need >= 300 1m bars, else unavailable. $0.10 bins; each bar's (bid_vol+ask_vol) is spread uniformly over bins from floor(bid_l/0.1) to floor(bid_h/0.1) inclusive. POC = highest-volume bin; tie -> the bin nearest the profile's volume-weighted mean price; if still tied, the lower bin. Bin price = bin_low + 0.05.
  (iii) Opposite edge of the 12-H1 range used in (R2), as of the last completed H1 before T_R: the range low for a short, the range high for a long.
- Choose the nearest candidate (smallest |TP − fill|) whose planned RR = |TP − fill| / |fill − SL| is >= 1.5. If none, skip. Pre-trade proxy fill for the RR and $5 filters = R's close quote of the fill side (ask_c of R for longs, bid_c of R for shorts). After the next open is seen, use actual fill for PnL; do not retro-skip (see slip note).
- Primary account filter (M5-Risk, $500, 0.01 lot = 1 oz): skip if planned risk |proxy_fill − SL| > $5. Also report the UNFILTERED set (no $5 cap, still RR>=1.5) as a secondary table, not decisive.
- Spread filter: closing spread of bar R (ask_c − bid_c) <= 1.5 × the trailing 20-trading-day median of (ask_c − bid_c) for that UTC hour, prior days only. If the median is undefined (< 10 prior days for that hour), skip.
- News filter (PRIMARY results WITH the filter): no new entry if the entry M5 open falls inside a high-impact window. Calendar: /workspace/m5-gold-team/data/news_calendar_hist.csv, rows with impact=high AND verified=true; use window_start_tehran .. window_end_tehran (already ±15 min). FOMC dates are cross-checked against /workspace/m5-gold-team/backtest/fomc_calendar_source.html (federalreserve.gov fomccalendars); when the html has a "For release at" time, that time wins, else 14:00 ET; if the day has a press conference, the window is the union of the statement window and [14:15, 15:00] ET. Cancelled releases (2025 lapse, unpublished claims weeks, etc.) are not events: drop rows whose source notes cancellation; do not invent replacements. Live / post-sample scoring uses data/news_windows.json from M5-News on the same ±15 min convention. Already-open trades are NOT force-closed for news.
- Time stop: exit at the conservative close of the earlier of (i) the 24th M5 bar counting the entry bar as 1 (~2h) and (ii) the end of the entry session. Long time-stop fill = bid close; short = ask close.
- Hard SL / TP on 1m path from the entry 1m bar: long SL if bid_l <= SL (fill SL, or bid_o if gapped through); long TP if bid_h >= TP (fill TP, or bid_o if gapped). Short SL if ask_h >= SL; short TP if ask_l <= TP (ask_o if gapped). Same 1m bar both hit -> SL. On the entry 1m bar itself, only SL is checked (conservative). First exit wins.
- Max 1 open trade: new signals ignored while a position is open. After an exit, a later signal may fire. Cap 3 entries per Tehran calendar date (pre-declared safety cap, not tuned).
- Slip after fill: R_risk for PnL = |actual_fill − SL|. If slippage pushes risk above $5 or planned RR below 1.5, still keep the trade (filters are pre-trade). Do not retro-skip.

## Costs
- PRIMARY: fills already use the conservative side (long enter ask / exit bid; short enter bid / exit ask), PLUS $0.20 slippage per round trip, subtracted from dollar PnL. Do NOT also add a flat $0.36 on top of bid/ask fills (double-count).
- Robustness (reported, not decisive): bid-path only (longs enter bid open, all exits on bid) plus a flat $0.36 spread + $0.20 slippage = $0.56 per round trip.
- Net R = (dollar PnL after the chosen cost model) / R_risk. R_risk = |actual_fill − SL|.

## Controls (matched random)
For each accepted strategy trade, N=20 controls, RNG seed 20261113, numpy default_rng, sampling without replacement.
Each control has the SAME session type (London/NY), SAME UTC hour-of-day, SAME direction, SAME SL distance and SAME TP distance in dollars, and the SAME time-stop rule and cost model.
Control entry time: a random M5 bar open from eligible bars that (a) fall in the same session type and same UTC hour-of-day, (b) are in a ±20 trading-day window around the trade's Tehran date, EXCLUDING the trade's own Tehran date, (c) pass the same spread filter and news filter, (d) are inside the same data split (IS or OOS; WF test windows use only that window). If fewer than 20 remain, expand to ±40 trading days, then to all remaining dates in the same split and same year; if still short, use all remaining and record n_controls (pairs with n_controls < 5 are dropped from the paired sample, kept in unpaired).
Control fill: same side as the strategy at that M5 open; SL/TP at the same dollar distances; path / costs / time stop identical. A control that cannot be placed (missing quotes) is redrawn once; if still impossible it is dropped (counts toward the <5 rule).
Paired value for a trade = strategy net R − mean(net R of its controls).

## Splits (descriptive except where named in PASS)
Year (UTC year of entry), London vs NY, news-day vs no-news-day (the Tehran date has at least one high-impact window in the calendar; entries inside windows are already excluded in the primary set), ATR tercile of ATR_M5 at T_R among all strategy-eligible session days of the same UTC year, and regime already required to be range — further split by which level was swept (PDH/PDL vs session H/L vs equal H/L) as descriptive only.

## Data split and walk-forward (no re-fitting)
- IS (sanity only): entries 2020-01-01 .. 2023-12-31 UTC. Counts and engine errors only; no parameter change.
- OOS (confirmatory, reported once): entries 2024-01-01 .. 2026-10-30 UTC.
- Walk-forward (stability of the FROZEN rules; windows never re-estimate parameters):
  WF1 train 2020-01-01..2021-12-31, test 2022-01-01..2022-12-31
  WF2 train 2021-01-01..2022-12-31, test 2023-01-01..2023-12-31
  WF3 train 2022-01-01..2023-12-31, test 2024-01-01..2024-12-31
  WF4 train 2023-01-01..2024-12-31, test 2025-01-01..2025-12-31
  WF5 train 2024-01-01..2025-12-31, test 2026-01-01..2026-10-30
  Train folds are not used to choose or drop rules.

## Hypothesis family (Holm, α=0.05, m=3)
All on the PRIMARY cost model, PRIMARY $5 filter, OOS, paired as defined, one-sided.
- H_primary: mean paired diff (strategy − control-mean) > 0, all OOS trades.
- H_london: the same, London entries only.
- H_ny: the same, NY entries only.
Inference: day-block bootstrap, block = Tehran calendar date of entry, 5000 reps, seed 20261113; p = share of bootstrap mean diffs <= 0. 95% CI = 2.5th and 97.5th percentiles. Week-block (ISO week of entry) bootstrap, same reps/seed, is robustness only. Holm adjusts the three p-values in this family.

## PASS / FAIL / KILL / INCONCLUSIVE (OOS, pre-declared)
PASS only if ALL of:
  (a) H_primary Holm-adjusted day-bootstrap p < 0.05;
  (b) OOS mean paired diff > 0;
  (c) OOS strategy own mean net R > 0 after primary costs;
  (d) paired diff > 0 in at least 2 of the 3 OOS years (2024, 2025, 2026; UTC year of entry);
  (e) neither London nor NY OOS paired diff is negative (both sessions not < 0);
  (f) n >= 200 OOS primary-filtered trades;
  (g) walk-forward: paired diff > 0 in at least 3 of the 5 WF test windows.
KILL if OOS own mean net R < 0 AND OOS paired diff <= 0, OR if OOS paired diff <= −0.10 R (materially worse than matched random).
INCONCLUSIVE (cannot PASS) if n_OOS < 80.
Otherwise FAIL (tested, did not meet PASS, not KILL).
The unfiltered and flat-$0.56 robustness tables are reported and not decisive.

## Disclosure
Past level and bias tests on this desk found no edge: levels_v2 independent confirmation 2020-2024 failed (paired fade net R worse than matched controls; negative in all 5 years, even gross); the GC volume-profile exploratory test gave only a fragile continuation hint and could not PASS. Tick-volume POC / VWAP here are not a substitute for COMEX volume or order flow, and are unvalidated until the OOS test is run against this exact file's hash. Bid/ask fills assume next-bar liquidity at the quoted open; no queue / no-fill model. A PASS is only historical evidence, not a licence to size up, and is not financial advice (signal-only research).
No parameter is tuned after outcomes. If a bug is found after running, only the bug is fixed, documented as a dated deviation, and the run is repeated once. Hash this file and append to ../PREREG_HASHES.txt BEFORE any outcome code is written or run.
