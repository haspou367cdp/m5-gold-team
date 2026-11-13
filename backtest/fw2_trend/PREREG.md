# PREREG fw2_trend — Framework v2 engine (1): trend continuation
Written 2026-11-13 12:59 Asia/Tehran (box `date` 12:59:31 +0330), BEFORE any trade, control or outcome was computed and BEFORE any evaluator was written.
Owner: M5-Journal. Requested by Boti after the owner (pouhasaa) adopted framework v2.
This is trial 1 of a NEW family (fw2 entry engines), tested SEPARATELY from engine (2) liquidity-sweep / mean-reversion (see ../fw2_sweep/PREREG.md). Do not pool trades with fw2_sweep. Holm is within this study's hypothesis family only. Prior levels/bias trials (levels_bias, levels_v2_build, levels_v2_confirm FAILED on net R vs matched controls 2020-2024; levels_v2_gc and gc_vp_hf were exploratory / fragile, no PASS) are disclosed as context and are NOT in this Holm family.
Parameters below are frozen now. 2020-2023 is a sanity period only (counts, no crash); NOTHING is tuned on IS or OOS. No order flow. No GC. Do not call tools/levels.py or brief.py.

## Data
- Source: /workspace/data/gold_1m/xauusd_1m.parquet (Dukascopy freeserv 1m bid/ask). Filter bad_quote==True (drop). File ends 2026-10-30; first bar 2020-01-01 23:00 UTC (early Jan 2020 lacks EMA50 H1 history and is skipped — require 50 completed H1 and 50 completed M15 bid bars before a signal).
- Resample M5 / M15 / H1 from 1m, label="left", closed="left", UTC. Signal OHLC = BID unless a fill rule says ASK.
- Volume, where used (session VWAP only): Dukascopy bid_vol+ask_vol, a TICK-VOLUME PROXY, not COMEX volume.
- ATR_M5(T) / ATR_H1(T) = Wilder ATR(14) on completed bid bars of that TF strictly before T: TR = max(h-l, |h-prev_c|, |l-prev_c|), ewm(alpha=1/14, adjust=False).mean(). Same formula as tools/levels.py atr(); that file is not modified or called.
- Market hours: m5lib.market_open (Sun 18:00 NY to Fri 17:00 NY, daily break 17:00-18:00 NY). No signals when closed.

## Sessions (DST-aware, code-ready)
Bounds from m5lib.sessions_for(t): Asia = 00:00 UTC -> 07:00 Europe/London; London = 07:00 Europe/London -> 08:30 America/New_York; NY = 08:30 NY -> 17:00 NY. Not fixed UTC hours.
Tehran labels (guide only; evaluation uses the UTC bounds above). Iran used UTC+4:30 in spring-summer through 2022, then UTC+3:30 year-round; UK/US DST still apply.
- Winter (UK GMT, US EST, Iran +03:30): Asia 03:30-10:30, London 10:30-17:00, NY 17:00-01:30 Tehran.
- Summer (UK BST, US EDT, Iran +03:30): Asia 03:30-09:30, London 09:30-16:00, NY 16:00-00:30 Tehran. Add +1h to Tehran clocks in Iran-DST summers 2020-2022.
Entries are taken in London and NY only. Asia is used only to form completed Asia H/L. Last allowed entry: the M5 bar must OPEN strictly before session end.

## Direction filter (H1 and M15 must agree; EMA, not swing structure)
At decision time T = close of the M5 bar under test (no look-ahead; only bars whose close <= T).
- EMA20 / EMA50 = ewm(span=20 or 50, adjust=False) of bid close on that TF. Require 50 completed bars.
- H1 up: EMA20 > EMA50 AND EMA20 > EMA20 of the previous completed H1 bar (slope). H1 down: EMA20 < EMA50 AND EMA20 < previous EMA20. Else H1 flat.
- M15 up / down: the same two conditions on M15.
- Long only if H1 up AND M15 up. Short only if H1 down AND M15 down. Otherwise no trend-continuation signal.

## Pullback levels (unranked; these are a price map, not a validated edge)
Eligible at T, using only completed bars:
- PDH / PDL = high / low of the previous gold trading day (m5lib.trading_day_start / previous_trading_day_start: 18:00 NY -> 17:00 NY).
- Completed prior-session H/L: current day's Asia H/L once Asia has ended; current day's London H/L once London has ended (NY entries only).
- Current-session VWAP, anchored at the current session start (sessions_for). Typical = (bid_h+bid_l+bid_c)/3 of each 1m bar; vol = bid_vol+ask_vol; VWAP = cumsum(typical*vol)/cumsum(vol) through the last completed 1m bar before T. Unavailable if cum vol = 0.
- Most recent confirmed M15 swing low (for longs) or swing high (for shorts) that has not been invalidated by an M15 bid close beyond it. M15 fractal: width w=2 (see BOS).
A level is an eligible support for a long if level <= last M5 bid close and (last M5 bid close − level) <= 2.0 * ATR_M5(T). Eligible resistance for a short: mirrored. All such levels are tried; a pullback to ANY one of them qualifies (first touch in time wins if several are touched on the same bar, tie -> the closest to price).

## Pullback touch (tolerance 0.15 ATR)
Long: an M5 bid low in the current session, at or after direction is on, satisfies level − 0.15*ATR_M5(T) <= low <= level + 0.15*ATR_M5(T), AND that bar's bid close >= level − 0.15*ATR_M5(T). If the bar closes < level − 0.15*ATR (a close-through), it is a break, not a pullback — do not count the same bar's high/low as a reaction (same-bar OHLC order is unknown). Short: mirrored (high in [level−0.15ATR, level+0.15ATR], close <= level+0.15ATR; close > level+0.15ATR = break).
Touch bar = P. ATR_M5 at P's close.

## M5 BOS and retest
Fractal width w=2 (5-bar). Bar i is a confirmed swing high when bar i+2 has closed, iff high[i] > high[j] for every j in {i−2,i−1,i+1,i+2} (strict). Swing low: low[i] < all four neighbours (strict). Only confirmed swings are used (no look-ahead).
Most recent confirmed swing high / low at a bar B = the latest such i with i+2 already closed before B's close.
After a valid pullback P, search bars P+1 .. P+12 (inclusive) for the first bullish BOS (long) or bearish BOS (short):
- Bullish BOS: M5 bid close > the most recent confirmed swing high frozen at that bar's open (confirmed before this bar).
- Bearish BOS: M5 bid close < the most recent confirmed swing low, same freeze.
BOS bar = B. Retest window: bars B+1 .. B+6.
Retest confirm (long): some bar R in that window has low in [swing_high_broken − 0.15*ATR, swing_high_broken + 0.15*ATR] AND bid close > swing_high_broken. R may be the touch bar. If a bar in the window closes < swing_high_broken − 0.15*ATR before a confirm, this BOS is cancelled (wait for a new pullback+BOS). Short: mirrored.
If no confirm by B+6, this BOS dies; a later BOS in the P+1..P+12 window may still be used (first confirm wins).

## Entry, SL, TP, filters
- Entry: market fill at the OPEN of the next M5 bar after R closes (= first 1m bar of that M5 bar). Longs fill at ASK open (o_a); shorts fill at BID open (o_b). If that ask/bid is missing, skip. If the next M5 bar does not open within 5 minutes of R's close, skip (gap / weekend).
- SL (behind the pullback swing), long: min M5 bid low from bar P through bar B−1 (inclusive), minus buffer 0.10 * ATR_M5(T_R), where T_R = close of R. Short: max M5 bid high from P through B−1, plus the same buffer. If SL is on the wrong side of fill (long SL >= fill, short SL <= fill), skip.
- TP (next liquidity), long — candidate prices strictly above fill: (i) most recent confirmed M15 swing high above fill; (ii) PDH if above fill; (iii) current session high so far (completed 1m bars before entry) if above fill; (iv) prior completed session high (Asia high for London entries; max(Asia high, London high) for NY entries) if above fill. Short: mirrored (M15 swing low, PDL, session lows).
- Choose the nearest candidate (smallest |TP − fill|) whose planned RR = |TP − fill| / |fill − SL| is >= 1.5. If none, skip the trade. Planned fill for the RR / $5 filters = R's close quote of the fill side (ask_c of R for longs, bid_c of R for shorts) as a pre-trade proxy (the next M5 open is not yet known at R's close). After the next open is seen, use the actual fill for PnL; do not retro-skip (see slip note below).
- Primary account filter (M5-Risk, $500, 0.01 lot = 1 oz): skip if planned risk |proxy_fill − SL| > $5. Also report the UNFILTERED set (no $5 cap, still RR>=1.5) as a secondary table, not decisive.
- Spread filter: closing spread of bar R (ask_c − bid_c) <= 1.5 × the trailing 20-trading-day median of (ask_c − bid_c) for that UTC hour, using prior days only. If the median is undefined (< 10 prior days for that hour), skip. "Normal spread only."
- News filter (PRIMARY results WITH the filter): no new entry if the entry M5 open falls inside a high-impact window. Calendar: /workspace/m5-gold-team/data/news_calendar_hist.csv, rows with impact=high AND verified=true; use the recorded window_start_tehran .. window_end_tehran (already ±15 min around the release). FOMC dates are cross-checked against /workspace/m5-gold-team/backtest/fomc_calendar_source.html (federalreserve.gov fomccalendars); when the html has a "For release at" time, that time wins, else 14:00 ET; if the day has a press conference, the window is the union of the statement window and [14:15, 15:00] ET. Cancelled releases (2025 appropriations lapse, unpublished claims weeks, etc.) are not events: drop any row whose source notes cancellation, and do not invent replacements. Live / post-sample scoring uses data/news_windows.json from M5-News on the same ±15 min convention. Already-open trades are NOT force-closed for news.
- Time stop: exit at the conservative close of the earlier of (i) the 24th M5 bar counting the entry bar as 1 (~2h) and (ii) the end of the entry session (sessions_for). Long time-stop fill = bid close; short = ask close.
- Hard SL / TP on 1m path from the entry 1m bar: long SL if bid_l <= SL (fill SL, or bid_o if the bar gaps through); long TP if bid_h >= TP (fill TP, or bid_o if gapped). Short SL if ask_h >= SL; short TP if ask_l <= TP (ask_o if gapped). Same 1m bar both hit -> SL. On the entry 1m bar itself, only SL is checked (intra-bar order of TP vs entry unknown; conservative). First exit wins.
- Max 1 open trade: new signals ignored while a position is open. After an exit, a later signal may fire. Cap 3 entries per Tehran calendar date (pre-declared safety cap, not tuned).
- Slip after fill: R_risk for PnL = |actual_fill − SL|. If slippage pushes risk above $5, still keep the trade (the $5 filter is pre-trade). If it pushes planned RR below 1.5, still keep it. Do not retro-skip.

## Costs
- PRIMARY: fills already use the conservative side (long enter ask / exit bid; short enter bid / exit ask), PLUS $0.20 slippage per round trip, subtracted from dollar PnL. Do NOT also add a flat $0.36 on top of bid/ask fills (that would double-count the spread).
- Robustness (reported, not decisive): bid-path only (longs enter bid open, all exits on bid) plus a flat $0.36 spread + $0.20 slippage = $0.56 per round trip.
- Net R = (dollar PnL after the chosen cost model) / R_risk. R_risk = |actual_fill − SL|.

## Controls (matched random, not a level map)
For each accepted strategy trade, N=20 controls, RNG seed 20261113, numpy default_rng, sampling without replacement.
Each control has the SAME session type (London/NY), SAME UTC hour-of-day, SAME direction, SAME SL distance and SAME TP distance in dollars as the actual fill-to-SL and fill-to-TP, and the SAME time-stop rule and cost model.
Control entry time: a random M5 bar open drawn from eligible bars that (a) fall in the same session type and same UTC hour-of-day, (b) are in a ±20 trading-day window around the trade's Tehran date, EXCLUDING the trade's own Tehran date, (c) pass the same spread filter and news filter, (d) are inside the same data split (IS or OOS; WF test windows use only that window). If fewer than 20 remain, expand to ±40 trading days, then to all remaining dates in the same split and same year; if still short, use all remaining and record n_controls (pairs with n_controls < 5 are dropped from the paired sample, kept in unpaired).
Control fill: same side as the strategy (ask open long, bid open short) at that M5 open; SL/TP placed at the same dollar distances in the same direction; path / costs / time stop identical. A control that cannot be placed (missing quotes) is redrawn once; if still impossible it is dropped (counts toward the <5 rule).
Paired value for a trade = strategy net R − mean(net R of its controls).

## Splits (descriptive except where named in PASS)
Year (UTC year of entry), London vs NY, news-day vs no-news-day (the Tehran date has at least one high-impact window in the calendar, regardless of whether the trade itself was inside a window — entries inside windows are already excluded in the primary set), ATR tercile of ATR_M5 at T_R among all strategy-eligible session days of the same UTC year, and trend-strength regime: "trend" if |EMA20_H1 − EMA50_H1| / ATR_H1 >= 0.25 else "weak-trend" (this engine never trades a flat H1, so this is a strength split, not a range split).

## Data split and walk-forward (no re-fitting)
- IS (sanity only): entries 2020-01-01 .. 2023-12-31 UTC. Look at trade counts and engine errors only, not at whether to change a parameter.
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
Past level and bias tests on this desk found no edge: levels_v2 independent confirmation 2020-2024 failed (paired fade net R worse than matched controls; negative in all 5 years, even gross); the GC volume-profile exploratory test gave only a fragile continuation hint and could not PASS. This engine is unvalidated until the OOS test is run against this exact file's hash. Bid/ask fills assume next-bar liquidity at the quoted open; no queue / no-fill model. Tick volume is a proxy. A PASS is only historical evidence, not a licence to size up, and is not financial advice (signal-only research).
No parameter is tuned after outcomes. If a bug is found after running, only the bug is fixed, documented as a dated deviation, and the run is repeated once. Hash this file and append to ../PREREG_HASHES.txt BEFORE any outcome code is written or run.
