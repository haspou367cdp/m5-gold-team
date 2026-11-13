# VERDICT (M5-Journal, 2026-11-12 Tehran)
- Q1: levels.py levels do NOT beat matched non-level prices. Strong/medium reversal rate is 0.7-2.8 pp BELOW controls (IS strong 72.7% vs 74.4%, OOS strong 67.7% vs 68.4%). The strength ranking does not separate strong/medium/weak. A 1xATR bounce after a touch happens ~70% of the time at ANY price.
- Q2: brief bias 2h hit rate IS 52.9% (CI 50.1-55.6), OOS 51.7% (48.4-54.9, p=0.33). No reliable edge. OOS NY 54.9% (p=0.043) is one of ~20 splits and IS NY was 52.7% (n.s.): treat as noise.
- Invalidation: an M15 close beyond the neutral_level happens within 2h in 54-57% of directional briefs. The level sits very close to price.
- News: no historical calendar existed in /workspace/m5-gold-team/data/. Used the FOMC + 08:30 ET proxy; it changes nothing.

# Level reaction + brief bias study — results (M5-Journal)

Prereg: PREREG_levels_bias.md (sha in HASHES.txt, written before results). Data: DataHunter's Dukascopy-derived 1m BID+ASK, 2020-01-02..2026-10-30.
Snapshots rebuilt (brief times 11:15/16:15 Tehran, market open, fresh data): 3525.

Q1 eligible levels: 140026, touched within 4h: 25020 (17.9%). Controls: 122566, touched 18704.

## Q1 level reaction (reversal = ≥1×ATR_M5 away before an M15 close beyond; 2h after touch). Control = matched non-level price

### by period × strength

| period   | strength   |   n_touch |   reversal% | rev_CI95   |   break% |   neither% |   ctrl_n |   ctrl_rev% | ctrl_CI95   |   ctrl_break% |   diff_pp |   p_two_sided |
|:---------|:-----------|----------:|------------:|:-----------|---------:|-----------:|---------:|------------:|:------------|--------------:|----------:|--------------:|
| IS       | strong     |      6941 |        72.7 | 71.6-73.7  |     27.3 |          0 |     5432 |        74.4 | 73.2-75.5   |          25.6 |      -1.7 |        0.0313 |
| IS       | medium     |      2995 |        72.6 | 70.9-74.1  |     27.4 |          0 |     2322 |        75.3 | 73.5-77.0   |          24.7 |      -2.8 |        0.0228 |
| IS       | weak       |      2449 |        73.9 | 72.1-75.6  |     26.1 |          0 |     1892 |        75.7 | 73.7-77.6   |          24.3 |      -1.8 |        0.1716 |
| OOS      | strong     |      5846 |        67.7 | 66.5-68.9  |     32.3 |          0 |     4386 |        68.4 | 67.0-69.8   |          31.6 |      -0.7 |        0.4781 |
| OOS      | medium     |      3338 |        69.8 | 68.3-71.4  |     30.2 |          0 |     2397 |        70.6 | 68.8-72.4   |          29.4 |      -0.8 |        0.5149 |
| OOS      | weak       |      3451 |        70.3 | 68.7-71.8  |     29.7 |          0 |     2275 |        71.2 | 69.3-73.0   |          28.8 |      -0.9 |        0.4667 |

### strong+medium by period × side

| period   | side       |   n_touch |   reversal% | rev_CI95   |   break% |   neither% |   ctrl_n |   ctrl_rev% | ctrl_CI95   |   ctrl_break% |   diff_pp |   p_two_sided |
|:---------|:-----------|----------:|------------:|:-----------|---------:|-----------:|---------:|------------:|:------------|--------------:|----------:|--------------:|
| IS       | resistance |      4778 |        70.6 | 69.3-71.8  |     29.4 |          0 |     3691 |        72.4 | 70.9-73.8   |          27.6 |      -1.8 |        0.0705 |
| IS       | support    |      5158 |        74.5 | 73.3-75.7  |     25.5 |          0 |     4063 |        76.8 | 75.4-78.0   |          23.2 |      -2.2 |        0.0138 |
| OOS      | resistance |      4262 |        65.9 | 64.4-67.3  |     34.1 |          0 |     3133 |        65.5 | 63.8-67.1   |          34.5 |       0.4 |        0.7282 |
| OOS      | support    |      4922 |        70.8 | 69.5-72.0  |     29.2 |          0 |     3650 |        72.4 | 70.9-73.8   |          27.6 |      -1.6 |        0.1066 |

### strong+medium by period × session (of touch; m5lib sessions)

| period   | session   |   n_touch |   reversal% | rev_CI95   |   break% |   neither% |   ctrl_n |   ctrl_rev% | ctrl_CI95   |   ctrl_break% |   diff_pp |   p_two_sided |
|:---------|:----------|----------:|------------:|:-----------|---------:|-----------:|---------:|------------:|:------------|--------------:|----------:|--------------:|
| IS       | asia      |         8 |        75   | 40.9-92.9  |     25   |          0 |        6 |        50   | 18.8-81.2   |          50   |      25   |        0.334  |
| IS       | london    |      5472 |        67.8 | 66.5-69.0  |     32.2 |          0 |     3899 |        70.2 | 68.8-71.6   |          29.8 |      -2.4 |        0.0119 |
| IS       | ny        |      4456 |        78.6 | 77.4-79.8  |     21.4 |          0 |     3849 |        79.2 | 77.9-80.5   |          20.8 |      -0.6 |        0.4867 |
| OOS      | london    |      4384 |        62.6 | 61.2-64.0  |     37.4 |          0 |     3140 |        64   | 62.3-65.7   |          36   |      -1.4 |        0.2148 |
| OOS      | ny        |      4800 |        73.9 | 72.6-75.1  |     26.1 |          0 |     3643 |        73.6 | 72.2-75.1   |          26.4 |       0.2 |        0.8144 |

### by period × strength × side

| period   | strength   | side       |   n_touch |   reversal% | rev_CI95   |   break% |   neither% |   ctrl_n |   ctrl_rev% | ctrl_CI95   |   ctrl_break% |   diff_pp |   p_two_sided |
|:---------|:-----------|:-----------|----------:|------------:|:-----------|---------:|-----------:|---------:|------------:|:------------|--------------:|----------:|--------------:|
| IS       | strong     | resistance |      3383 |        70.8 | 69.3-72.3  |     29.2 |          0 |     2605 |        71.9 | 70.2-73.6   |          28.1 |      -1.1 |        0.3448 |
| IS       | strong     | support    |      3558 |        74.4 | 73.0-75.8  |     25.6 |          0 |     2827 |        76.7 | 75.1-78.2   |          23.3 |      -2.2 |        0.0398 |
| IS       | medium     | resistance |      1395 |        70   | 67.5-72.3  |     30   |          0 |     1086 |        73.4 | 70.7-75.9   |          26.6 |      -3.4 |        0.061  |
| IS       | medium     | support    |      1600 |        74.8 | 72.6-76.9  |     25.2 |          0 |     1236 |        77   | 74.6-79.3   |          23   |      -2.2 |        0.1731 |
| IS       | weak       | resistance |      1180 |        71.2 | 68.5-73.7  |     28.8 |          0 |      884 |        72.3 | 69.2-75.1   |          27.7 |      -1.1 |        0.5837 |
| IS       | weak       | support    |      1269 |        76.4 | 73.9-78.6  |     23.6 |          0 |     1008 |        78.7 | 76.0-81.1   |          21.3 |      -2.3 |        0.1904 |
| OOS      | strong     | resistance |      2718 |        64.6 | 62.8-66.4  |     35.4 |          0 |     2029 |        64.5 | 62.4-66.5   |          35.5 |       0.2 |        0.8991 |
| OOS      | strong     | support    |      3128 |        70.4 | 68.8-72.0  |     29.6 |          0 |     2357 |        71.8 | 69.9-73.6   |          28.2 |      -1.4 |        0.2726 |
| OOS      | medium     | resistance |      1544 |        68.1 | 65.7-70.3  |     31.9 |          0 |     1104 |        67.4 | 64.6-70.1   |          32.6 |       0.7 |        0.7125 |
| OOS      | medium     | support    |      1794 |        71.3 | 69.2-73.4  |     28.7 |          0 |     1293 |        73.4 | 70.9-75.7   |          26.6 |      -2   |        0.2105 |
| OOS      | weak       | resistance |      1508 |        66.6 | 64.2-68.9  |     33.4 |          0 |     1030 |        66.5 | 63.6-69.3   |          33.5 |       0.1 |        0.9693 |
| OOS      | weak       | support    |      1943 |        73.1 | 71.1-75.1  |     26.9 |          0 |     1245 |        75   | 72.5-77.3   |          25   |      -1.9 |        0.2371 |

### news-proxy variant: touches outside ±15 min of 08:30 ET (every weekday) and FOMC 14:00 ET

| period   | strength   |   n_touch |   reversal% | rev_CI95   |   break% |   neither% |   ctrl_n |   ctrl_rev% | ctrl_CI95   |   ctrl_break% |   diff_pp |   p_two_sided |
|:---------|:-----------|----------:|------------:|:-----------|---------:|-----------:|---------:|------------:|:------------|--------------:|----------:|--------------:|
| IS       | strong     |      5850 |        70.8 | 69.6-72.0  |     29.2 |          0 |     4526 |        72.1 | 70.7-73.3   |          27.9 |      -1.2 |        0.1636 |
| IS       | medium     |      2558 |        70.9 | 69.1-72.6  |     29.1 |          0 |     1969 |        73.8 | 71.9-75.7   |          26.2 |      -3   |        0.0271 |
| IS       | weak       |      2109 |        72.5 | 70.6-74.4  |     27.5 |          0 |     1625 |        74.2 | 72.0-76.3   |          25.8 |      -1.7 |        0.2401 |
| OOS      | strong     |      5290 |        67   | 65.7-68.2  |     33   |          0 |     4013 |        67.1 | 65.7-68.6   |          32.9 |      -0.2 |        0.8586 |
| OOS      | medium     |      3070 |        68.9 | 67.2-70.5  |     31.1 |          0 |     2201 |        69.4 | 67.4-71.3   |          30.6 |      -0.5 |        0.6884 |
| OOS      | weak       |      3203 |        69.7 | 68.1-71.3  |     30.3 |          0 |     2126 |        69.9 | 68.0-71.9   |          30.1 |      -0.2 |        0.8593 |

## Q2 brief bias vs BID move 2h later

Briefs with outcome: 3525; bias split: {'neutral': 1354, 'bullish': 1246, 'bearish': 925}

### all directional briefs

| period   |    n |   hit% | CI95      |   binom_p |
|:---------|-----:|-------:|:----------|----------:|
| IS       | 1265 |   52.9 | 50.1-55.6 |    0.0429 |
| OOS      |  904 |   51.7 | 48.4-54.9 |    0.3348 |
| period   | brief   |   n |   hit% | CI95      |   binom_p |
|:---------|:--------|----:|-------:|:----------|----------:|
| IS       | London  | 663 |   53.1 | 49.3-56.9 |    0.1202 |
| IS       | NY      | 602 |   52.7 | 48.7-56.6 |    0.2064 |
| OOS      | London  | 452 |   48.5 | 43.9-53.1 |    0.5409 |
| OOS      | NY      | 452 |   54.9 | 50.3-59.4 |    0.043  |
| period   | conf   |   n |   hit% | CI95      |   binom_p |
|:---------|:-------|----:|-------:|:----------|----------:|
| IS       | strong | 749 |   52.3 | 48.8-55.9 |    0.2141 |
| IS       | weak   | 516 |   53.7 | 49.4-57.9 |    0.1033 |
| OOS      | strong | 552 |   51.1 | 46.9-55.2 |    0.6397 |
| OOS      | weak   | 352 |   52.6 | 47.3-57.7 |    0.3649 |
| period   | brief   | bias    |   n |   hit% | CI95      |   binom_p |
|:---------|:--------|:--------|----:|-------:|:----------|----------:|
| IS       | London  | bearish | 302 |   50   | 44.4-55.6 |    1      |
| IS       | London  | bullish | 361 |   55.7 | 50.5-60.7 |    0.0351 |
| IS       | NY      | bearish | 272 |   53.3 | 47.4-59.2 |    0.3026 |
| IS       | NY      | bullish | 330 |   52.1 | 46.7-57.5 |    0.4743 |
| OOS      | London  | bearish | 179 |   45.8 | 38.7-53.1 |    0.2954 |
| OOS      | London  | bullish | 273 |   50.2 | 44.3-56.1 |    1      |
| OOS      | NY      | bearish | 172 |   58.7 | 51.3-65.8 |    0.0267 |
| OOS      | NY      | bullish | 280 |   52.5 | 46.7-58.3 |    0.4373 |

### threshold: only moves ≥ 0.5×ATR_M5

share of directional briefs with |move| ≥ 0.5 ATR: 90.1% (n=2171); hit% below = among those only

| period   |    n |   hit% | CI95      |   binom_p |
|:---------|-----:|-------:|:----------|----------:|
| IS       | 1149 |   52.5 | 49.6-55.4 |    0.0985 |
| OOS      |  808 |   53.5 | 50.0-56.9 |    0.0529 |
| period   | brief   |   n |   hit% | CI95      |   binom_p |
|:---------|:--------|----:|-------:|:----------|----------:|
| IS       | London  | 592 |   52.7 | 48.7-56.7 |    0.2026 |
| IS       | NY      | 557 |   52.2 | 48.1-56.4 |    0.3092 |
| OOS      | London  | 397 |   50.6 | 45.7-55.5 |    0.8409 |
| OOS      | NY      | 411 |   56.2 | 51.4-60.9 |    0.0136 |

### invalidation (M15 close beyond neutral_level / H1 close beyond off_level within 2h)

| period   |   n_with_neutral_level |   inv15_pct |   hit_if_inv15 |   hit_if_not |   n_with_off_level |   invH1_pct |
|:---------|-----------------------:|------------:|---------------:|-------------:|-------------------:|------------:|
| IS       |                   1267 |        54   |           29.1 |         80.8 |               1267 |         6.6 |
| OOS      |                    904 |        56.7 |           28.3 |         82.4 |                904 |         6.3 |

### news-proxy variant: drop briefs whose 2h window overlaps a proxy window

kept 1117 of 2171 directional briefs; by brief: {'London': 1117}

| period   | brief   |   n |   hit% | CI95      |   binom_p |
|:---------|:--------|----:|-------:|:----------|----------:|
| IS       | London  | 663 |   53.1 | 49.3-56.9 |    0.1202 |
| OOS      | London  | 452 |   48.5 | 43.9-53.1 |    0.5409 |# Diagnostic (not pre-registered): reversal rate by distance-from-price bin (ATR units), strong+medium

|                                               |   size_control |   size_level |   mean_control |   mean_level |   diff_pp |
|:----------------------------------------------|---------------:|-------------:|---------------:|-------------:|----------:|
| ('IS', Interval(0.3, 1.0, closed='right'))    |            333 |         1546 |          0.628 |        0.606 |    -2.155 |
| ('IS', Interval(1.0, 2.0, closed='right'))    |           1509 |         1888 |          0.695 |        0.699 |     0.399 |
| ('IS', Interval(2.0, 4.0, closed='right'))    |           2445 |         2784 |          0.738 |        0.735 |    -0.328 |
| ('IS', Interval(4.0, 8.0, closed='right'))    |           2317 |         2521 |          0.768 |        0.762 |    -0.663 |
| ('IS', Interval(8.0, 100.0, closed='right'))  |           1150 |         1197 |          0.824 |        0.831 |     0.69  |
| ('OOS', Interval(0.3, 1.0, closed='right'))   |            698 |         1773 |          0.622 |        0.584 |    -3.746 |
| ('OOS', Interval(1.0, 2.0, closed='right'))   |           1446 |         1981 |          0.645 |        0.655 |     0.949 |
| ('OOS', Interval(2.0, 4.0, closed='right'))   |           2228 |         2619 |          0.682 |        0.705 |     2.3   |
| ('OOS', Interval(4.0, 8.0, closed='right'))   |           1737 |         2043 |          0.736 |        0.743 |     0.67  |
| ('OOS', Interval(8.0, 100.0, closed='right')) |            674 |          768 |          0.782 |        0.772 |    -0.976 |