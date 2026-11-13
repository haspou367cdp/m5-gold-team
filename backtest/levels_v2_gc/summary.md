# VERDICT (levels_v2 GC-volume test, 2026-11-13 Tehran): real COMEX volume moves the volume-profile levels by ~$7-11,
# but it does NOT improve the result vs control. FAIL (and underpowered by design).
Prereg: PREREG_v2gc.md, hashed 08:07:18 Tehran and copied to backtest/PREREG_HASHES.txt BEFORE any generation/eval
(gen/eval ran after that). Second trial on levels_v2 -> Holm over 2 tests.

## Data caveats (read first)
- GC source = FirstRate free sample, GC_F26 (Jan-2026) 1m. F26 is a thin, non-active delivery month (median 1 contract per bar),
  NOT the active front month. Real COMEX volume, but for one illiquid contract only.
- Usable density only from mid-Oct 2025: 86 eligible snapshots (84 after market-closed filter), 2025-10-17..2025-12-25 —
  ~10 weeks, entirely inside the earlier quick test's OOS window (not independent). Window stops before first notice (~12-30).
- Basis (GC − spot BID, per profile segment, same minutes): median $17.16, IQR $14.09-24.05, range $9.17-37.72 (carry to Jan,
  shrinking toward expiry). No roll inside the window.

## Does real volume change the levels?
- POC/VAH/VAL shift (GC vs tick, same 170 segments), median |Δ|: POC $11.25, VAH $7.00, VAL $7.50 (prev day POC $12.00,
  developing-day POC $9.25). ATR_M5 is ~$4-5, so these are material moves of the volume levels.
- But the final level map barely changes: score distribution tick {1:406,2:573,3:1061,4:439,5:74} vs GC {1:412,2:566,3:1061,4:420,5:84};
  84% of GC score>=4 levels are also score>=4 in the tick version; VP flag on 18.9% vs 18.2% of levels.

## Does it improve the result vs control? (paired, score>=4 vs own matched control, both touched)
| variant | pairs | level rev% | control rev% | diff pp | one-sided p | 95% CI |
|---|---|---|---|---|---|---|
| tick volume (same snapshots) | 110 | 70.0 | 73.6 | −3.6 | 0.836 | −11.7..+4.8 |
| GC volume | 118 | 72.0 | 75.4 | −3.4 | 0.837 | −11.6..+3.9 |
Diff-in-diff (GC − tick): +0.25 pp. Halves (GC): before Dec −12.5 pp (n=56), Dec +4.8 pp (n=62).
Holm-adjusted one-sided p: this test 0.837; levels_v2 quick test 0.176.
Criteria: (a) p<0.05 NO, (b) >=+3 pp NO, (c) both halves >0 NO, (e) >=300 pairs NO (118) => FAIL.
Other buckets (GC, paired): watch −3.4 pp (n=207), low +1.8 pp (n=114) — no ranking.

## Plain answer
Real COMEX volume (as available here) shifts POC/VAH/VAL by about $7-11, but levels_v2 score>=4 levels still bounce no more than
nearby random prices (both versions ≈ −3.5 pp, swamped by noise). Swapping tick volume for this GC volume gives no improvement.
Low power: a real effect smaller than ~±12 pp could not be detected, and F26 is not representative front-month volume. A fair
retest would need front-month GC 1m volume over 1+ year (paid data), preregistered as a third trial.

Files: PREREG_v2gc.md, HASHES.txt, gen_gc.py, eval_gc.py, vp_shift.py, {tick,gc}/levels_v2_hist.csv, {tick,gc}/touches_v2.csv,
{tick,gc}/tab_bucket.csv, basis_log.csv, vp_shift.csv, gen.log, vp_shift.log, eval.log.
