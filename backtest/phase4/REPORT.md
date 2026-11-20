# Phase 4 replay — HISTORICAL SIMULATION (not live results; no edge claimed)

Rules frozen in PREREG.md before running (hashes in HASHES.txt). Live parameters were NOT changed from these results.
Live engines as of c80b513, DaryaGold cost model (fee 14,000 once, $0.25 spread, 1U 80,000/$ · 0.5U 40,000/$), 60 s rule,
Tehran 07:00–00:30 incl. 07:00–11:15, fixed equity 2,954,400 toman. News gate inactive (no historical calendar).

| period | sessions | evaluations | daily-stop hits | range |
|---|---|---|---|---|
| IS | 1042 | 71353 | 0 | 2020-01-02 … 2023-12-29 |
| OOS | 739 | 50552 | 2 | 2024-01-01 … 2026-10-29 |

Engine errors during replay: 0

| period | engine | session | signals | filled | win_rate | avg_R | total_R | net_toman | max_dd_toman | max_dd_R | tp | sl | close | stop_out | tp_deferred_60s | avg_R_spread050 | mfe_R_med | mae_R_med | t_stat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IS | ALL | ALL | 250 | 112 | 21.4 | -0.308 | -34.5 | -5925440 | 6509040 | 37.8 | 20 | 82 | 10 | 0 | 0 | -0.373 | 0.45 | 0.78 | -2.43 |
| IS | ALL | 07:00-11:15 | 50 | 25 | 24.0 | -0.037 | -0.9 | -330560 | 1141600 | 6.0 | 5 | 19 | 1 | 0 | 0 | -0.138 | 0.48 | 0.8 | -0.1 |
| IS | ALL | 11:15-16:15 | 82 | 49 | 14.3 | -0.57 | -27.9 | -4871600 | 5623600 | 32.7 | 7 | 42 | 0 | 0 | 0 | -0.609 | 0.47 | 0.79 | -3.72 |
| IS | ALL | 16:15-00:30 | 118 | 38 | 28.9 | -0.147 | -5.6 | -723280 | 1318000 | 8.7 | 8 | 21 | 9 | 0 | 0 | -0.222 | 0.41 | 0.73 | -0.76 |
| IS | continuation | ALL | 137 | 16 | 12.5 | -0.601 | -9.6 | -1615840 | 1799440 | 10.6 | 1 | 11 | 4 | 0 | 0 | -0.623 | 0.24 | 0.78 | -3.03 |
| IS | continuation | 07:00-11:15 | 27 | 3 | 0.0 | -1.0 | -3.0 | -581600 | 581600 | 3.0 | 0 | 3 | 0 | 0 | 0 | -1.0 | 0.22 | 0.84 |  |
| IS | continuation | 11:15-16:15 | 30 | 5 | 20.0 | -0.4 | -2.0 | -218800 | 622800 | 4.0 | 1 | 4 | 0 | 0 | 0 | -0.428 | 0.22 | 0.79 | -0.67 |
| IS | continuation | 16:15-00:30 | 80 | 8 | 12.5 | -0.577 | -4.6 | -815440 | 815440 | 4.6 | 0 | 4 | 4 | 0 | 0 | -0.603 | 0.27 | 0.64 | -3.46 |
| IS | sweep_reversion | ALL | 113 | 96 | 22.9 | -0.259 | -24.9 | -4309600 | 5143600 | 30.2 | 19 | 71 | 6 | 0 | 0 | -0.331 | 0.49 | 0.78 | -1.8 |
| IS | sweep_reversion | 07:00-11:15 | 23 | 22 | 27.3 | 0.094 | 2.1 | 251040 | 934800 | 5.0 | 5 | 16 | 1 | 0 | 0 | -0.021 | 0.52 | 0.78 | 0.22 |
| IS | sweep_reversion | 11:15-16:15 | 52 | 44 | 13.6 | -0.59 | -25.9 | -4652800 | 5177200 | 29.7 | 6 | 38 | 0 | 0 | 0 | -0.629 | 0.48 | 0.79 | -3.7 |
| IS | sweep_reversion | 16:15-00:30 | 38 | 30 | 33.3 | -0.033 | -1.0 | 92160 | 924320 | 7.0 | 8 | 17 | 5 | 0 | 0 | -0.12 | 0.5 | 0.76 | -0.14 |
| OOS | ALL | ALL | 300 | 135 | 22.2 | -0.281 | -37.9 | -7711200 | 8513600 | 43.7 | 28 | 104 | 3 | 0 | 0 | -0.344 | 0.7 | 0.83 | -2.29 |
| OOS | ALL | 07:00-11:15 | 88 | 38 | 31.6 | -0.031 | -1.2 | -387600 | 2680800 | 15.3 | 12 | 26 | 0 | 0 | 0 | -0.125 | 0.97 | 0.82 | -0.13 |
| OOS | ALL | 11:15-16:15 | 109 | 59 | 13.6 | -0.473 | -27.9 | -5265000 | 6191000 | 33.1 | 8 | 51 | 0 | 0 | 0 | -0.519 | 0.35 | 0.83 | -2.48 |
| OOS | ALL | 16:15-00:30 | 103 | 38 | 26.3 | -0.232 | -8.8 | -2058600 | 3187800 | 15.1 | 8 | 27 | 3 | 0 | 0 | -0.291 | 1.03 | 0.84 | -1.09 |
| OOS | continuation | ALL | 156 | 13 | 15.4 | -0.083 | -1.1 | -25600 | 780000 | 4.9 | 2 | 10 | 1 | 0 | 0 | -0.182 | 1.43 | 0.75 | -0.13 |
| OOS | continuation | 07:00-11:15 | 47 | 2 | 0.0 | -1.0 | -2.0 | -412000 | 412000 | 2.0 | 0 | 2 | 0 | 0 | 0 | -1.0 | 0.1 | 0.83 |  |
| OOS | continuation | 11:15-16:15 | 47 | 7 | 28.6 | 0.574 | 4.0 | 859600 | 366800 | 3.0 | 2 | 5 | 0 | 0 | 0 | 0.401 | 2.54 | 0.7 | 0.51 |
| OOS | continuation | 16:15-00:30 | 62 | 4 | 0.0 | -0.774 | -3.1 | -473200 | 473200 | 3.1 | 0 | 3 | 1 | 0 | 0 | -0.794 | 0.79 | 0.74 | -3.43 |
| OOS | sweep_reversion | ALL | 144 | 122 | 23.0 | -0.302 | -36.8 | -7685600 | 8978800 | 44.8 | 26 | 94 | 2 | 0 | 0 | -0.361 | 0.68 | 0.84 | -2.53 |
| OOS | sweep_reversion | 07:00-11:15 | 41 | 36 | 33.3 | 0.023 | 0.8 | 24400 | 2486800 | 14.3 | 12 | 24 | 0 | 0 | 0 | -0.076 | 1.02 | 0.82 | 0.09 |
| OOS | sweep_reversion | 11:15-16:15 | 62 | 52 | 11.5 | -0.614 | -31.9 | -6124600 | 6591800 | 34.3 | 6 | 46 | 0 | 0 | 0 | -0.643 | 0.3 | 0.84 | -4.01 |
| OOS | sweep_reversion | 16:15-00:30 | 41 | 34 | 29.4 | -0.168 | -5.7 | -1585400 | 2734600 | 12.1 | 8 | 24 | 2 | 0 | 0 | -0.232 | 1.03 | 0.84 | -0.71 |

## Reading (written after the run; no parameter was changed)
- Both periods are negative after DaryaGold costs: IS −0.31 R per filled trade (112 fills, t −2.4), OOS −0.28 R (135 fills, t −2.3). OOS net −7.71 M toman, max drawdown 8.51 M toman (43.7 R) at fixed 1U/0.5U sizing.
- The loss is concentrated in 11:15–16:15 (London): IS −27.9 R, OOS −27.9 R, win rate 13–14 %. 07:00–11:15 is roughly flat in both periods (IS −0.9 R, OOS −1.2 R).
- sweep_reversion produces most fills (218 of 247); continuation rarely fills (29 fills from 293 signals).
- Fill rate is low (45 %): many limit orders expire unfilled. Median MAE 0.8 R vs median MFE 0.45–0.7 R: price usually goes against the entry before it goes for the target.
- No stop-outs and no 60 s TP deferrals happened under these stops; daily stop hit twice (OOS).
- Limits: news gate inactive (no historical calendar), M1 bars (intrabar order unknown; SL assumed first when both touch), fixed DaryaGold offset, sample of ~250 fills over 6.8 years.
