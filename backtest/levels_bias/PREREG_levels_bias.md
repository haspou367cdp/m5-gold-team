# PREREG — level reaction + brief bias study (M5-Journal), written 2026-11-12 ~14:35 Tehran BEFORE any result
Requested by Boti. IS = snapshots 2020-01-01..2023-12-31 (frozen), OOS = 2024-01-01..2026-10-30 (reported once, never tuned).
Data: /workspace/data/gold_1m/xauusd_1m.parquet (DataHunter's Dukascopy-derived 1m BID+ASK). Columns mapped to the toolkit
names (bid_o->o_b ... ask_c->c_a, bid_vol->v_b, ask_vol->v_a). All level/bias prices = BID, as in the live tools.

## Point-in-time rebuild (code reuse, no re-implementation)
- Snapshot times = brief times, fixed Tehran clock 11:15 (London brief) and 16:15 (NY brief) every weekday (zoneinfo Asia/Tehran,
  so pre-2022 summer UTC+4:30 is handled). Skip a snapshot if the market is closed (m5lib.market_open False) or the last 1m bar
  opened > 15 min before T (same as fetch_xauusd --max-age 15).
- At each T: slice 1m bars with open in [T−10 days, T) (= live fetch --days 10), build m5/m15/h1 with fetch_xauusd.resample
  (imported; includes the partial last bar exactly like the live cache), then call tools/levels.compute() and tools/bias.compute()
  UNCHANGED by monkeypatching only their data loaders (load_bars, load_json for meta/levels) and news input.
  meta = {ok: True, stale: False, market_open: True}. News input = empty (no historical M5-News bias/windows exist), so
  bias = technical bias (news_agrees=True). Imports run with PYTHONDONTWRITEBYTECODE=1; nothing is written into tools/.
- Cannot rebuild: M5-News news bias and its live windows; the verdict's spread/news gates (not studied). Everything else in
  levels.py/bias.py is reproduced from code.

## Q1 level reaction
- Levels = every entry of levels.compute()["levels"] at T (strong/medium/weak as ranked by the tool; side as given vs price at T).
- Eligible only if |level − price_T| ≥ 0.3×ATR_M5(T) (not already at price). ATR = tool's atr_m5_14 at T.
- Touch = first M5 bar (BID) with open ≥ T, within 48 bars (4h), whose high ≥ level (resistance) / low ≤ level (support).
- After touch, over the touch bar + next 23 M5 bars (2h):
  reversal = BID low ≤ level − 1×ATR (resistance) / high ≥ level + 1×ATR (support);
  break = an M15 BID close beyond the level (close > level for resistance, < for support), checked at M15 closes;
  first event wins; if both in the same M5 bar -> break (conservative). Else "neither".
- Baseline (matched controls): for each eligible level with distance d, candidate control distances d×(1±0.15k), k=1,2,3 (closest
  first, same side); take the first that is ≥ 0.3×ATR from price, > tol (tool's cluster_tol) from every listed level and from every
  $5 multiple (round $5s are dropped from the list when score < 1). Same touch/outcome test. Report level vs control
  reversal rate with Wilson 95% CI and two-proportion z-test.
- Splits: strength, support/resistance, session of the TOUCH via m5lib.sessions_for (Asia 00:00 UTC–07:00 London, London 07:00
  London–08:30 NY, NY 08:30–17:00 NY = 03:30–10:30 / 10:30–17:00 / 17:00–01:30 Tehran in winter; DST-correct; else "off"), IS/OOS.

## Q2 brief bias
- bias = bias.compute()["bias"] at T. Outcome: BID close of the last 1m bar opening before T+2h (must be within 10 min of T+2h)
  minus price_bid at T. Hit = same sign as bias (neutral excluded). Threshold variant: only |move| ≥ 0.5×ATR_M5(T) counted
  (smaller moves = "no move", reported as share). Binomial test vs 50% (two-sided) + Wilson 95% CI. Splits: brief (London/NY),
  technical_confidence (strong/weak), IS/OOS.
- Invalidation: for directional briefs with invalidation.neutral_level: % where an M15 BID close in (T, T+2h] is beyond it
  (bearish: >, bullish: <); same for off_level with H1 closes. Hit rate split by invalidated or not.

## Q3 news
- /workspace/m5-gold-team/data/ holds only live news_windows.json (from 2026-11-12) — no historical calendar. Variant uses the
  proxy: ±15 min around 08:30 ET every weekday + 14:00 ET on FOMC statement days (federalreserve.gov list, ../fomc_calendar_source.html).
  Q1: drop touches inside a window. Q2: drop briefs whose [T, T+2h] overlaps a window (removes almost every NY brief — expected).

Trials counted: Q1 1 definition (+ news variant), Q2 2 (no threshold, 0.5 ATR) (+ news variant). No other variants will be run.

## ADDENDUM 1 — 2026-11-12 ~14:45 Tehran, written BEFORE running this variant (all rules above unchanged)
One added variant "calendar": M5-News historical calendar /workspace/m5-gold-team/data/news_calendar_hist.csv (709 rows,
CPI/PPI/NFP/claims ±15 min; FOMC statement 13:45–15:15 ET; FOMC minutes 13:45–14:15 ET; all rows incl. the 1 unverified).
Windows = [window_start_tehran, window_end_tehran) in Asia/Tehran, converted to UTC with zoneinfo.
- Q1: drop a touch (level and control alike) if its evaluation window [touch bar open, touch bar open + 2h] overlaps any window.
- Q2: drop a brief if [T, T+2h] overlaps any window.
Applied as a filter on the already-saved q1_touches.csv / q2_briefs.csv (no recomputation of levels, touches or outcomes).
Same tables (q1tab/q2tab from evaluate.py) for: base, proxy (as originally run), calendar. Outputs in news_variant/.
Trials: +1 variant.
