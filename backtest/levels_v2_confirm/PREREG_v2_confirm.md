# PREREG v2_confirm — independent 2020-2024 confirmation of levels_v2, primary metric = NET TRADING EDGE
Dated addendum to ../levels_v2_build/PREREG_v2.md. Written 2026-11-13 08:10 Asia/Tehran (box `date` 08:09:52 +0330),
BEFORE any level for 2020-2024 was generated and BEFORE any outcome (touch / trade / control) was computed.
Owner of this run: M5-Journal (independent of the levels_v2 builder). Requested by Boti on the owner's (pouhasaa) decision.
Trial count: this is trial 2 on levels_v2 (trial 1 = levels_v2_build, H1 one-sided p = 0.087, FAIL).

## Frozen code (verified before writing this file)
- tools/levels_v2.py sha256 9aaeb469c0baf4955529ab90af6fee4db27f365f3bdace93b811e85068e0f284 (= levels_v2_build/HASHES.txt)
- levels_v2_build/gen_levels.py sha256 9def4b23828e51b14a0b91c4c4bfcad6ed7c6b00293c4667030b53987cb23554 (= HASHES.txt)
Neither file is edited. A new wrapper gen_confirm.py imports gen_levels and calls its unchanged snap() (and therefore
levels_v2.compute()), only changing (i) the data load start date (gen_levels.load() hard-codes >= 2024-11-15) and (ii) the
snapshot date list (2020-01-01..2024-12-31). Load = same columns/renames/bad_quote filter as gen_levels.load().
Data: /workspace/data/gold_1m/xauusd_1m.parquet (Dukascopy 1m bid/ask; verified coverage 2020-01-01 23:00 UTC .. 2026-10-30,
~353-356k 1m rows per year 2020-2024, 0 bad_quote rows). Volume = Dukascopy bid_vol+ask_vol TICK-VOLUME PROXY (as before).
Known consequence: the file starts 2020-01-01 23:00 UTC; snapshots without the history gen_levels requires
(>= 5000 1m bars in the prior 24 days) are skipped by snap() unchanged, so the first days of Jan 2020 drop out.

## Levels
Snapshots at 11:15 and 16:15 Asia/Tehran every weekday 2020-01-01..2024-12-31, same eligibility as v2_build
(market_open(T), last 1m bar <= 15 min old, >= 5000 1m bars in prior 24 days). Buckets: high = score >= 4, watch = 3, low = score <= 2.
Before evaluation I may look ONLY at row/snapshot counts, error count and the score histogram (disclosed in summary).

## Touch / eligibility / reversal (identical to PREREG_v2.md, copied)
Eligible: |level − price_T| >= 0.3 × ATR_M5(T). Touch = first M5 BID bar opening >= T within 48 bars (4h) with high >= level
(resistance) / low <= level (support). After touch, over touch bar + next 23 M5 bars: reversal = BID moves 1 × ATR_M5(T) away
from the level (low <= level−ATR for resistance; high >= level+ATR for support); break = M15 BID close beyond the level;
first event wins; same bar -> break. Else "neither" (counted as non-reversal).
(Implementation: the same code as evaluate_v2.py test(); the 4h window and 2h window are clock windows as in evaluate_v2.py.)

## Controls
One control per eligible level, at the SAME snapshot time T (so session/hour, ATR regime and trend state are matched by
construction), same side, at distance d×(1±0.15k), k=1,2,3, order +1,−1,+2,−2,+3,−3 (closest first; same order as
evaluate_v2.py); take the first candidate that is >= 0.3×ATR_M5(T) from price_T and > tol from EVERY levels_v2 level at T
(all scores). Same touch/outcome/trade test as levels.
Round-number decision (made from the code, before any outcome): levels_v2.py has NO round-number component (candidates are
PDH/PDL, PWH/PWL, H4/H1 swings, EQH/EQL, Asia/London session H/L, VP POC/VAH/VAL, VWAP; the only `round` is round(p, 2)
formatting). Therefore controls do NOT exclude $5 multiples here (this removes the v2_build limitation). This is a deliberate,
pre-declared difference from v2_build.
Recorded per snapshot (and therefore identical for level and control): ATR tercile = tercile of ATR_M5(T) among all
snapshots of the same calendar year; trend state = H1 BID close EMA20 vs EMA50 (completed H1 bars before T, ~12 days history):
up if EMA20 > EMA50 else down. Balance table reported (expected identical by construction).

## Pairing
Unit = (level, its control) keyed by `pair`. Each side evaluated independently; a side not touched within 4h contributes no trade.
PRIMARY statistic = mean net R per touch of high levels − mean net R per touch of their controls, over pairs where BOTH sides
touched (paired). Also reported: unpaired (all touched high levels vs all touched controls) and the count of levels without control.

## Fixed fade rule (declared exactly)
- Entry: at the first touch (first 1m BID bar inside the touch M5 bar whose high >= level for resistance / low <= level for
  support), enter fading the level AT THE LEVEL PRICE: resistance -> short, support -> long.
- Stop = 1.0 × ATR_M5(T) beyond the level; target = 1.5 × ATR_M5(T) toward price (away from the level, back toward price_T side).
- Time stop: exit at the BID close of the last 1m bar of the 24th M5 bar after the touch M5 bar (M5 bar position k+24, i.e. ~2h).
- Path evaluated on 1m BID highs/lows from the entry 1m bar through the time-stop bar. If stop and target are both hit in the
  same 1m bar, assume stop. On the entry 1m bar itself only the stop is checked (order of target vs entry unknown -> conservative).
- Costs (primary): actual Dukascopy spread (ask_c − bid_c, i.e. spread_c) of the entry 1m bar, charged once per round trip,
  PLUS slippage $0.10 per side ($0.20 round trip). Robustness: flat cost $0.50 round trip instead (spread+slippage replaced).
- R = net PnL / (1.0 × ATR_M5(T)). Gross: stop = −1.0 R, target = +1.5 R, time stop = signed (exit − entry)/ATR.
- Limitation stated in advance: bid-path approximation (stop for a short would really trigger on ask; spread is charged once
  instead), limit fill at the exact level assumed (no queue/no-fill modelling).

## Primary test (decides PASS/FAIL)
H1 (one-sided): paired diff (high-level net R − control net R) > 0. Day-block bootstrap: resample snapshot dates (Tehran-T date,
UTC date of T as in v2) with replacement, 5000 reps, seed 20261113; p = share of bootstrap diffs <= 0. Week-block (ISO week)
bootstrap, same reps/seed, as robustness. Holm across the 2 trials on v2 (trial 1 p = 0.087): PASS requires p < 0.025.
PASS only if ALL:
 (a) day-bootstrap one-sided p < 0.025;
 (b) paired diff >= +0.05 R per touch;
 (c) high levels' own mean net R per touch > 0 after primary costs (paired sample);
 (d) paired diff > 0 in at least 4 of 5 years (2020, 2021, 2022, 2023, 2024; year of T in UTC);
 (e) >= 300 paired touches of high levels (pairs with both sides touched);
 (f) week-bootstrap one-sided p < 0.05.
Otherwise FAIL. The flat-$0.50 robustness run is reported but not decisive.

## Secondary (reported, not decisive)
Reversal probability (v2 definition), MAE and MFE in ATR (over the trade, entry to exit), time to reversal (M5 bars from touch),
breakout-failure rate (share of touches with an M15 close beyond the level within the 2h window after which BID returns
1 ATR back on the original side before the window ends), profit factor (gross wins/gross losses of net R), win rate (net R > 0).
H2 = high vs low score levels mean net R (all touched levels, unpaired), one-sided day bootstrap (5000, seed 20261113).
Per-year table 2020-2024 (paired n, level R, control R, diff, plus reversal%). Also watch bucket descriptive.

## Disclosure
2020-2023 was the levels v1 in-sample period (v2 was not tuned there; v2 was built on 2025-2026 data). A PASS is only evidence of
historical generalization, not of future performance. Tick volume is a Dukascopy proxy, not COMEX volume.
No parameter is tuned after outcomes. If a bug is found after running, only the bug is fixed, documented as a dated deviation,
and the run is repeated once.
