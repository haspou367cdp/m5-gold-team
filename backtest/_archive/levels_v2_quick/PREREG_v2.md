# PREREG v2 — levels_v2 score validation (QUICK, REDUCED-SAMPLE TEST)
Written 2026-11-13 ~07:55 Tehran, BEFORE any outcome (touch / reversal / control) was computed.
Disclosure: the level CSV (levels_v2_hist.csv) was generated before this file; only its score histogram was looked at
(0:26, 1:3445, 2:6803, 3:11805, 4:4794, 5:871 level-rows). No price outcomes were looked at. No parameter of levels_v2.py
has been or will be changed after this file. Owner asked for a fast test: sample is 2025-01-01..2026-10-30 only.

## Levels under test
tools/levels_v2.py compute() (sha in HASHES.txt), run point-in-time by gen_levels.py at brief times 11:15 and 16:15 Tehran
every weekday (market open, last 1m bar <= 15 min old), on DataHunter's Dukascopy 1m BID file
(/workspace/data/gold_1m/xauusd_1m.parquet). Volume = Dukascopy tick-volume PROXY (not COMEX). Supply/demand zones, order
blocks, FVG, fib were skipped (owner's speed request). 945 snapshots, 27,744 level-rows.

## Split
Train/IS = snapshots 2025-01-01..2025-06-30. OOS = 2025-07-01..2026-10-30 (sub-periods for consistency: 2025H2, 2026).
Nothing is tuned on IS; IS is reported only as a sign check.

## Outcome (identical to levels_bias PREREG Q1)
Eligible: |level − price_T| >= 0.3 × ATR_M5(T). Touch = first M5 BID bar opening >= T within 48 bars (4h) with high >= level
(resistance) / low <= level (support). After touch, over touch bar + next 23 M5 bars: reversal = BID moves 1 × ATR_M5(T) away
from the level (low <= level−ATR for resistance; high >= level+ATR for support); break = M15 BID close beyond the level;
first event wins; same bar -> break. Else "neither" (counted as non-reversal).
Control (matched): for each eligible level at distance d, try d×(1±0.15k), k=1,2,3 (closest first, same side); take first that is
>= 0.3×ATR from price, > tol from EVERY levels_v2 level at T (all scores) and > tol from every $5 multiple. Same touch/outcome test.

## Buckets
high = score >= 4, watch = score 3, low = score <= 2.

## Primary hypothesis H1 (decides PASS/FAIL)
In OOS, for touched high (score>=4) levels: reversal% − matched-control reversal% > 0.
PASS only if ALL hold:
 (a) one-sided p < 0.05 from a day-clustered bootstrap (resample snapshot dates with replacement, 5000 reps, seed 20261113)
     of diff = rev%(high levels) − rev%(their controls);
 (b) diff >= +3.0 percentage points (practical size; previous v1 levels were −0.7..−2.8 pp);
 (c) diff > 0 in BOTH OOS sub-periods 2025H2 and 2026;
 (d) diff > 0 in IS (sign check);
 (e) at least 300 touched high levels in OOS.
Otherwise FAIL.
## Secondary H2 (ranking; reported, needed before calling the score a "ranking")
OOS rev%(high) − rev%(low) > 0 with one-sided day-clustered bootstrap p < 0.05.
Also reported (descriptive only): every bucket vs its controls, by period and by year, two-proportion z p-values, Wilson CIs.

## Trials
1 level definition, 1 outcome definition, 1 primary test. No variants. If any variant is ever run it is added as an
addendum before running and Holm-corrected together with this test.

## Review addendum — 2026-11-13 ~07:50 Tehran (M5-Journal review; FAIL verdict unchanged; nothing re-tuned, criteria text above unchanged)
1. **Paired controls.** 942 of 4,091 OOS score>=4 levels got no control (no candidate distance passed the exclusion rules); 341 of
   those were touched (64.2% reversals) but stayed in the level side of the original unpaired number. Paired result (level AND its
   own control both touched), recomputed from touches_v2.csv by the `pair` key — reported as primary alongside the unpaired one:
   | sample | n pairs | level rev% | control rev% | diff pp |
   |---|---|---|---|---|
   | OOS high (>=4) | 782 | 68.7 | 65.7 | +2.9 (2.94) |
   | IS 2025H1 high | 287 | 67.6 | 61.0 | +6.6 |
   | 2025H2 high | 330 | 69.4 | 69.4 | 0.0 |
   | 2026 high | 452 | 68.1 | 63.1 | +5.1 |
   | OOS watch (3) | 1366 | 68.7 | 68.4 | +0.2 |
   | OOS low (<=2) | 770 | 65.7 | 68.1 | −2.3 |
   Paired day-clustered bootstrap (5000 reps, seed 20261113): diff +2.94 pp, one-sided p = 0.088, 95% CI −1.2..+7.1.
   Unpaired (original): +2.8 pp, p = 0.087. Under both, criteria (a) p<0.05, (b) >= +3.0 pp and (c) >0 in both sub-periods fail
   (2025H2 is 0.0 paired, −0.5 unpaired). Verdict: FAIL.
2. **Timing (corrected to file mtimes, Asia/Tehran).** levels_v2_hist.csv 07:44:05; PREREG_v2.md 07:44:26; evaluate_v2.py 07:44:54;
   touches_v2.csv / tab_*.csv / eval.log 07:44:58; summary.md and HASHES.txt 07:45:20. The "~07:55" / "~08:05" times written in the
   documents were wrong. HASHES.txt was first written together with PREREG_v2.md but appended after the eval, so its mtime is after
   the eval and **the hash file does not prove the prereg existed before the outcomes**; only the ~28 s mtime gap supports that.
3. **Limitation — controls are non-round.** Controls exclude every $5 multiple and every v2 level (±tol), so they are systematically
   non-round, non-level prices. The comparison is "v2 level vs a nearby price that is neither a round number nor any v2 level",
   not "vs a uniformly random price".
4. **H2 is not a valid ranking.** The high-vs-low result (p = 0.033) is secondary, not monotonic (score 5 ≈ its controls; score 1 is
   the highest reversal rate), and low-score levels fall below their own controls (−2.8 pp unpaired, −2.3 pp paired). The 0-5 score
   must not be presented as a ranking.
5. **Any future 2020-2024 confirmation run** must: freeze levels_v2.py, gen_levels.py, evaluate_v2.py and these criteria in a new
   dated addendum; hash that prereg (and store the hash outside this folder, e.g. _archive) BEFORE running the eval; use the paired
   statistic as primary. It counts as a second trial (Holm correction across both runs).
