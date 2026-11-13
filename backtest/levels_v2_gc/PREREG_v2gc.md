# PREREG v2gc — does REAL COMEX GC volume change levels_v2? (second trial; tiny, low-power)
Written 2026-11-13 08:07:18 Asia/Tehran, BEFORE running gen_gc.py / eval_gc.py / vp_shift.py (no levels, touches or
outcomes computed yet for this study). Only data-availability counts were looked at (GC bars per day; 86 eligible snapshots).

## What changes vs levels_v2_build (frozen)
Only the volume source of the volume profile (POC/VAH/VAL, prev day + developing day). tools/levels_v2.py is NOT edited;
gen_gc.py replaces levels_v2.vprofile at run time with a wrapper that feeds the SAME function GC bars from the same time segment.
VWAP stays on tick volume (unchanged). Snapshot rules, scoring, outcome, controls and evaluator code (evaluate_v2.py) are reused
unchanged. The tick variant is the frozen levels_v2 rerun on the same snapshots.

## GC data and mapping to spot
- File: data/gc_volume_sample/firstratedata_sample/GC_F26_1min.csv (FirstRate free sample, Jan-2026 contract, 1m, US/Eastern bar
  start -> converted to UTC; DST-ambiguous minutes dropped).
- IMPORTANT data limit: F26 (January) is a minor, thinly traded delivery month — NOT the active front month (Feb/Apr/Jun/Aug/Oct/Dec).
  Median 1 contract per 1m bar; usable bar density only from ~mid-Oct 2025. Its volume is real COMEX volume but only for this one
  thin contract, so it is a weak stand-in for "COMEX gold volume".
- Basis: for each profile segment, basis = median(GC close − Dukascopy spot BID close) over minutes present in both, inside that same
  segment (point-in-time: segment ends before T). Require >= 30 GC bars and >= 20 matched minutes, else no GC profile (same as the
  code's >= 30-bar rule). GC high/low/close are shifted down by basis; volume = GC contracts.
- Roll/expiry: single contract, no roll inside the window. Window ends 2025-12-26 (before first notice day ~2025-12-30 and the
  January delivery period, when F26 liquidity collapses). Basis reflects carry to Jan-2026 and drifts toward 0 as expiry nears;
  per-segment estimation absorbs this.
## Sample
Brief-time snapshots (11:15 / 16:15 Tehran weekdays) from 2025-03-25 to 2025-12-26 whose PREVIOUS trading day has >= 200 GC 1m bars
-> 86 snapshots, 2025-10-17 .. 2025-12-25 (market-closed ones drop out). So the effective window is ~10 weeks, not 10 months,
and it lies entirely inside the levels_v2 quick test's OOS window (2025H2) — not independent data.

## Primary test (paired, as in the levels_v2 review addendum)
GC variant: touched score>=4 levels vs their own matched control (both touched), bounce (reversal) rate.
Statistic: paired diff; one-sided p from day-clustered bootstrap (5000 reps, seed 20261113).
This is the SECOND trial on levels_v2 -> Holm correction over {levels_v2 quick paired p = 0.0878, this p}.
PASS only if ALL: (a) Holm-adjusted one-sided p < 0.05; (b) diff >= +3.0 pp; (c) diff > 0 in both halves (before Dec / Dec 2025);
(e) >= 300 pairs. Expected pairs ≈ 80-110 (≈1.1 per snapshot in the earlier test), so (e) will almost surely fail: this test
CANNOT pass by design and can only show whether GC volume changes the levels and the direction of any effect (low power; a
minimum detectable effect is roughly ±13 pp).
## Secondary / descriptive
- Same metrics for the tick variant on the same snapshots; diff-in-diff (GC paired diff − tick paired diff).
- Score distribution of both variants; median absolute $ distance between GC and tick POC / VAH / VAL on the same segments;
  basis median / IQR.
No variants beyond these two. No tuning.
