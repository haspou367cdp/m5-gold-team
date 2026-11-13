# VERDICT: FAIL (levels_v2, quick reduced-sample test) — M5 team, 2026-11-13 07:45 Tehran (file mtime; see Review addendum)
**This is a REDUCED-SAMPLE QUICK TEST** (owner asked for speed): 2025-01-01..2026-10-30 only, 945 brief-time snapshots.
Train/IS = 2025H1, OOS = 2025-07-01..2026-10-30. Prereg: PREREG_v2.md (file mtime 07:44:26 Tehran, 28 s before the evaluator was written; the hash alone does not prove ordering — see Review addendum).
Volume = Dukascopy tick-volume proxy (not COMEX). Supply/demand zones, order blocks, FVG, fib were not implemented.

## Primary test H1 (score >= 4 levels vs matched random-distance controls, OOS)
| criterion | required | result | ok? |
|---|---|---|---|
| (a) day-clustered bootstrap, one-sided p | < 0.05 | 0.087 (diff 95% CI −1.2..+6.7 pp) | NO |
| (b) diff size | >= +3.0 pp | +2.8 pp (69.5% vs 66.7%) | NO |
| (c) diff > 0 in both OOS sub-periods | 2025H2 & 2026 > 0 | 2025H2 −0.5 pp, 2026 +5.2 pp | NO |
| (d) IS sign | > 0 | +4.0 pp (66.2% vs 62.2%, n=414) | yes |
| (e) OOS touched high levels | >= 300 | 1221 | yes |
=> **FAIL.** Score >= 4 levels do not reliably get more 1×ATR reactions than random prices at the same distance.

## Secondary H2 (ranking): OOS high vs low levels
rev% high 69.5 vs low 66.0, diff +3.5 pp, one-sided bootstrap p = 0.033 (95% CI −0.2..+7.1). Nominally < 0.05, but:
not monotonic (score 5: 67.4% vs its controls 67.3%, +0.1 pp; score 1: 73.3%), and low-score levels sit BELOW their own
controls (−2.8 pp), so most of the gap is "low levels are slightly worse than random", not "high levels are better".
Treat as a weak hint, not evidence.

## Reversal rate by score (OOS, touched levels vs controls)
| score | n | level rev% | control rev% | diff pp | p (z, two-sided) |
|---|---|---|---|---|---|
| 1 | 232 | 73.3 | 73.1 | +0.2 | 0.97 |
| 2 | 985 | 64.3 | 67.8 | −3.5 | 0.13 |
| 3 | 2214 | 69.9 | 70.5 | −0.6 | 0.69 |
| 4 | 991 | 69.9 | 66.5 | +3.4 | 0.14 |
| 5 | 230 | 67.4 | 67.3 | +0.1 | 0.98 |
Buckets OOS: high (>=4) 69.5 vs 66.7 (+2.8); watch (3) 69.9 vs 70.5 (−0.6); low (<=2) 66.0 vs 68.8 (−2.8).
By sub-period, high bucket: IS 2025H1 +4.0, 2025H2 −0.5, 2026 +5.2 pp (none individually significant).
Base rate: a 1×ATR_M5 bounce after a touch happens ~66-71% of the time at ANY price (same as the v1 study).

## Honest reading
- v2 is not worse than v1 (v1 strong levels were −0.7..−2.8 pp vs controls; v2 high is +2.8 pp), but the gain is inside the noise
  and disappeared in 2025H2. Nothing passes; levels_v2 must NOT replace levels.py and must not be called "valid/strong".
- No tuning was done after seeing results. One definition, one primary test (no multiple-testing correction needed).
- Possible next step (not run): a single preregistered confirmation on the untouched 2020-2024 data with the SAME frozen
  levels_v2.py and the same criteria. If it also fails, drop the score.

Files: tools/levels_v2.py (live CLI: `python3 levels_v2.py --print`), gen_levels.py, levels_v2_hist.csv (27,744 level-rows),
evaluate_v2.py, touches_v2.csv, tab_*.csv, eval.log, HASHES.txt.
Counts: eligible levels 27,155, touched within 4h 6,298; controls 22,568, touched 4,578.

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
