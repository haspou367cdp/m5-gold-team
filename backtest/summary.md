# M5 Gold Scalp backtest — results

IS = entries 2020-01-01..2023-12-31; OOS = 2024-01-01..2026-10-30 (untouched, reported once).

Data: /workspace/data/gold_1m/xauusd_1m.parquet (DataHunter's Dukascopy-derived 1m BID+ASK feed). bad_quote bars dropped (0 present).
M5/M15/H1 resampled from 1m, left-labelled UTC. All signal OHLC = BID. Longs fill at ASK, exit at BID; shorts reverse.

## Interpretations of ambiguous rules (frozen)
- H1 bias = EMA20 vs EMA50 of BID close on the last CLOSED H1 bar. M5-News bias and M5-Levels "favored side" cannot be reproduced historically -> H1 bias alone is the direction filter for ALL setups.
- Ranked levels = last completed: previous trading day (17:00 ET roll) H/L, Asian session (00-07 UTC) H/L, London (07-12 UTC) H/L, NY (12-21 UTC) H/L. 8 levels, no ranking (team level ranking is unvalidated). Round numbers NOT used.
- Spread filter "≤ normal for the hour": trigger-bar closing spread ≤ 1.5 × trailing 20-day median spread for that UTC hour (prior days only).
- SL $3–8: risk R = |fill − SL| (fill includes entry spread). Trades with R outside [3,8] are skipped. The "≈1–1.5×ATR" note is descriptive, not a filter.
- Entry "trigger close" = market fill at the open of the next 1m bar after the trigger M5 bar closes (= next M5 open). Limit/retest alternatives not tested.
- Exits: 50% at TP1 = 1.5R, 50% at TP2 = 2.5R (fixed R; "next ranked level" not used). SL stays at original (no breakeven, not in rules). Invalidation: on an M5 close beyond the invalidation line, exit remaining at next 1m open. SL/TP checked on 1m bars; both in one 1m bar -> SL. Gap through SL fills at the open.
- One open position per setup at a time (new signals ignored while in trade). No time stop.
- 1 Sweep: long if prev M5 close > L, low ≤ L−0.5, close > L (short mirrored). SL = trigger low − 0.5. Invalidation close < trigger low.
- 2 Break&retest: break bar closes beyond L from the other side with body ≥ 0.6×ATR14(prev bar, Wilder). Within the next 6 bars: if any close back through L -> cancelled. Touch = low ≤ L + 0.1×ATR. Trigger = bar k that closes beyond L in break direction, and (this bar or previous post-break bar) touched, and is a pin (rejecting wick ≥ 2×body and close in the favourable half) or engulfing (opposite previous candle, body engulfs). SL = extreme of retest bars − 0.5. Invalidation close back through L.
- 3 EMA pullback: M5 EMA20>EMA50, EMA20 rising vs previous bar, H1 EMA20>EMA50 and last closed H1 EMA20 rising (short mirrored). Among the trigger bar and 2 previous bars: some low ≤ EMA20 and no close < EMA50. Trigger: bullish candle closing above EMA20. SL = min low of those 3 bars − 0.5. Invalidation close < EMA50.
- 4 Asian range breakout: range 00:00–07:00 UTC, width $5–25. First M5 bar starting 07:00–08:55 UTC closing beyond the H1-bias-side edge. SL = range midpoint if R in [3,8], else opposite side of breakout candle if R in [3,8], else skip. One per day. Invalidation close back inside range.
- News: no complete historical calendar found (BLS schedule pages returned 403). FOMC statement dates scraped from federalreserve.gov fomccalendars (saved as fomc_calendar_source.html). A sensitivity variant "news-proxy" blocks entries ±15 min of 14:00 ET on FOMC days and ±15 min of 08:30 ET on EVERY weekday (a proxy covering CPI/NFP/claims/PPI/retail; not a real calendar). Main results have NO news filter.
- Sessions (by entry UTC): Asia 00–07, London 07–12, NY 12–21, Late 21–24. Tehran (UTC+3:30, current): Asia 03:30–10:30, London 10:30–15:30, NY 15:30–00:30, Late 00:30–03:30 (Iran used UTC+4:30 in summer until 2022 -> +1h those months).

## Variants (counted trials: 4 setups × 7 = 28)
base; spread+50% (ask = bid + 1.5×spread); entry delay +1 M5 bar; news-proxy; $500 acct (R ≤ $5 incl. spread, 0.01 lot = 1 oz, single exit 100% at TP1 since 0.01 can't be split); $500 + $10/day cap (portfolio); portfolio with team risk rules (max 2 open, stop day after 3 losses or −2R).
Bias check (info only): H1 EMA20/50 + M15 EMA20/50 agree -> direction; scored vs BID close 2h later, per session.


Data: DataHunter's Dukascopy-derived 1m BID+ASK feed, /workspace/data/gold_1m/xauusd_1m.parquet, 2020-01-01 23:00 → 2026-10-30 12:02 UTC. R includes real per-bar spread; NO commission added.

## Main table (base and sensitivities), R per trade, 50/50 TP1 1.5R / TP2 2.5R

| variant          | period   | setup                        |    n |   win |   avgR |   PF |   maxDD |    totR |      t |   med_risk |   med_hold_min |
|:-----------------|:---------|:-----------------------------|-----:|------:|-------:|-----:|--------:|--------:|-------:|-----------:|---------------:|
| base             | IS       | 1 Sweep+reversal             |  666 |  32.6 | -0.199 | 0.7  |   139.8 |  -132.8 |  -4.13 |       3.75 |             37 |
| base             | IS       | 2 Break&retest               |  256 |  29.3 | -0.21  | 0.67 |    63.6 |   -53.9 |  -2.88 |       3.7  |             28 |
| base             | IS       | 3 EMA pullback               | 2241 |  30.1 | -0.121 | 0.76 |   274.7 |  -270.4 |  -5.55 |       3.75 |             63 |
| base             | IS       | 4 Asian range BO             |  286 |  10.5 | -0.138 | 0.56 |    39.4 |   -39.4 |  -3.46 |       4.88 |             15 |
| base             | IS       | ALL (each setup independent) | 3449 |  28.9 | -0.144 | 0.73 |   506.4 |  -496.5 |  -7.96 |       3.82 |             52 |
| base             | OOS      | 1 Sweep+reversal             | 2062 |  34.5 | -0.122 | 0.81 |   282.9 |  -250.9 |  -4.28 |       4.38 |             15 |
| base             | OOS      | 2 Break&retest               |  643 |  33   | -0.104 | 0.83 |    80.4 |   -66.8 |  -2.1  |       4.27 |             15 |
| base             | OOS      | 3 EMA pullback               | 2973 |  32.1 | -0.124 | 0.79 |   382.9 |  -368.2 |  -5.64 |       4.63 |             35 |
| base             | OOS      | 4 Asian range BO             |   85 |  21.2 |  0.049 | 1.16 |     4.8 |     4.2 |   0.49 |       5.25 |             20 |
| base             | OOS      | ALL (each setup independent) | 5763 |  32.9 | -0.118 | 0.81 |   702   |  -681.7 |  -7.27 |       4.49 |             24 |
| spread+50%       | IS       | 1 Sweep+reversal             |  736 |  29.9 | -0.272 | 0.61 |   206.1 |  -200.4 |  -6.1  |       3.78 |             34 |
| spread+50%       | IS       | 2 Break&retest               |  289 |  26   | -0.28  | 0.58 |    90.4 |   -81   |  -4.23 |       3.74 |             26 |
| spread+50%       | IS       | 3 EMA pullback               | 2414 |  27.7 | -0.177 | 0.67 |   429.9 |  -426.8 |  -8.59 |       3.73 |             62 |
| spread+50%       | IS       | 4 Asian range BO             |  285 |  10.2 | -0.166 | 0.52 |    47.4 |   -47.4 |  -4.04 |       4.94 |             15 |
| spread+50%       | IS       | ALL (each setup independent) | 3724 |  26.6 | -0.203 | 0.64 |   760.4 |  -755.5 | -11.86 |       3.81 |             50 |
| spread+50%       | OOS      | 1 Sweep+reversal             | 2192 |  32   | -0.191 | 0.72 |   431.9 |  -418.3 |  -7.1  |       4.42 |             14 |
| spread+50%       | OOS      | 2 Break&retest               |  680 |  31.8 | -0.138 | 0.78 |    99.4 |   -94   |  -2.89 |       4.31 |             14 |
| spread+50%       | OOS      | 3 EMA pullback               | 3031 |  29.7 | -0.188 | 0.7  |   579.4 |  -568.5 |  -9    |       4.69 |             34 |
| spread+50%       | OOS      | 4 Asian range BO             |   86 |  20.9 |  0.004 | 1.01 |     8   |     0.3 |   0.04 |       5.26 |             20 |
| spread+50%       | OOS      | ALL (each setup independent) | 5989 |  30.7 | -0.18  | 0.72 |  1098.5 | -1080.4 | -11.65 |       4.54 |             23 |
| delay+1bar       | IS       | 1 Sweep+reversal             |  784 |  32.5 | -0.186 | 0.72 |   159.5 |  -145.9 |  -4.15 |       4.09 |             64 |
| delay+1bar       | IS       | 2 Break&retest               |  344 |  29.4 | -0.188 | 0.71 |    79.8 |   -64.6 |  -2.91 |       3.89 |             60 |
| delay+1bar       | IS       | 3 EMA pullback               | 2166 |  30.2 | -0.092 | 0.81 |   218.9 |  -199.2 |  -4.19 |       3.82 |             75 |
| delay+1bar       | IS       | 4 Asian range BO             |  265 |  12.5 | -0.145 | 0.55 |    40   |   -38.6 |  -3.4  |       4.94 |             20 |
| delay+1bar       | IS       | ALL (each setup independent) | 3559 |  29.3 | -0.126 | 0.76 |   483.4 |  -448.2 |  -6.98 |       3.94 |             68 |
| delay+1bar       | OOS      | 1 Sweep+reversal             | 1633 |  36.6 | -0.071 | 0.89 |   145.8 |  -115.4 |  -2.15 |       4.7  |             23 |
| delay+1bar       | OOS      | 2 Break&retest               |  545 |  36.9 |  0.003 | 1    |    42.6 |     1.5 |   0.05 |       4.52 |             26 |
| delay+1bar       | OOS      | 3 EMA pullback               | 2537 |  32.5 | -0.107 | 0.81 |   293.8 |  -271.9 |  -4.59 |       4.86 |             40 |
| delay+1bar       | OOS      | 4 Asian range BO             |   88 |  22.7 | -0.089 | 0.75 |    14.2 |    -7.8 |  -1    |       4.91 |             15 |
| delay+1bar       | OOS      | ALL (each setup independent) | 4803 |  34.2 | -0.082 | 0.86 |   427.8 |  -393.7 |  -4.57 |       4.76 |             31 |
| news-proxy       | IS       | 1 Sweep+reversal             |  565 |  31.3 | -0.213 | 0.69 |   128.3 |  -120.2 |  -4.04 |       3.71 |             36 |
| news-proxy       | IS       | 2 Break&retest               |  214 |  27.6 | -0.253 | 0.62 |    60.8 |   -54.1 |  -3.2  |       3.72 |             28 |
| news-proxy       | IS       | 3 EMA pullback               | 2135 |  30.5 | -0.111 | 0.78 |   245.8 |  -236.6 |  -4.94 |       3.74 |             65 |
| news-proxy       | IS       | 4 Asian range BO             |  286 |  10.5 | -0.138 | 0.56 |    39.4 |   -39.4 |  -3.46 |       4.88 |             15 |
| news-proxy       | IS       | ALL (each setup independent) | 3200 |  28.7 | -0.141 | 0.73 |   459.8 |  -450.4 |  -7.51 |       3.81 |             55 |
| news-proxy       | OOS      | 1 Sweep+reversal             | 1943 |  34.1 | -0.132 | 0.8  |   287.9 |  -256.2 |  -4.52 |       4.36 |             15 |
| news-proxy       | OOS      | 2 Break&retest               |  603 |  32.8 | -0.108 | 0.83 |    80   |   -65.2 |  -2.12 |       4.23 |             15 |
| news-proxy       | OOS      | 3 EMA pullback               | 2927 |  31.8 | -0.13  | 0.78 |   391.5 |  -380.9 |  -5.88 |       4.61 |             35 |
| news-proxy       | OOS      | 4 Asian range BO             |   85 |  21.2 |  0.049 | 1.16 |     4.8 |     4.2 |   0.49 |       5.25 |             20 |
| news-proxy       | OOS      | ALL (each setup independent) | 5558 |  32.5 | -0.126 | 0.8  |   710.4 |  -698.1 |  -7.61 |       4.47 |             24 |
| acct500_R<=5_TP1 | IS       | 1 Sweep+reversal             |  590 |  33.4 | -0.163 | 0.75 |   104.9 |   -95.9 |  -3.35 |       3.58 |             23 |
| acct500_R<=5_TP1 | IS       | 2 Break&retest               |  228 |  30.3 | -0.175 | 0.72 |    47   |   -39.9 |  -2.37 |       3.63 |             20 |
| acct500_R<=5_TP1 | IS       | 3 EMA pullback               | 2195 |  29.9 | -0.135 | 0.74 |   302.4 |  -297.3 |  -6.31 |       3.57 |             50 |
| acct500_R<=5_TP1 | IS       | 4 Asian range BO             |  181 |  13.3 | -0.148 | 0.57 |    26.7 |   -26.7 |  -2.91 |       3.98 |             15 |
| acct500_R<=5_TP1 | IS       | ALL (each setup independent) | 3194 |  29.6 | -0.144 | 0.74 |   468.8 |  -459.9 |  -7.88 |       3.6  |             40 |
| acct500_R<=5_TP1 | OOS      | 1 Sweep+reversal             | 1517 |  32.9 | -0.177 | 0.74 |   276.6 |  -267.8 |  -5.86 |       3.83 |              9 |
| acct500_R<=5_TP1 | OOS      | 2 Break&retest               |  445 |  30.3 | -0.188 | 0.71 |    83.5 |   -83.5 |  -3.52 |       3.76 |             10 |
| acct500_R<=5_TP1 | OOS      | 3 EMA pullback               | 2424 |  31.7 | -0.153 | 0.75 |   384.6 |  -369.9 |  -6.59 |       3.82 |             25 |
| acct500_R<=5_TP1 | OOS      | 4 Asian range BO             |   41 |  22   | -0.071 | 0.82 |     5.2 |    -2.9 |  -0.51 |       4.26 |             20 |
| acct500_R<=5_TP1 | OOS      | ALL (each setup independent) | 4427 |  31.9 | -0.164 | 0.74 |   734.9 |  -724.1 |  -9.48 |       3.82 |             16 |

## Base by session

| period   | setup            | session                   |    n |   win |   avgR |   PF |   maxDD |   totR |     t |   med_risk |   med_hold_min |
|:---------|:-----------------|:--------------------------|-----:|------:|-------:|-----:|--------:|-------:|------:|-----------:|---------------:|
| IS       | 1 Sweep+reversal | Asia (03:30-10:30 Teh)    |   49 |  30.6 | -0.224 | 0.68 |    14.5 |  -11   | -1.25 |       3.64 |             73 |
| IS       | 1 Sweep+reversal | Late (00:30-03:30 Teh)    |   18 |  38.9 | -0.014 | 0.98 |     2.5 |   -0.3 | -0.04 |       3.81 |            144 |
| IS       | 1 Sweep+reversal | London (10:30-15:30 Teh)  |   78 |  35.9 | -0.033 | 0.95 |    15.2 |   -2.6 | -0.22 |       3.56 |             64 |
| IS       | 1 Sweep+reversal | NewYork (15:30-00:30 Teh) |  521 |  32.1 | -0.228 | 0.66 |   129   | -119   | -4.25 |       3.82 |             33 |
| IS       | 2 Break&retest   | Asia (03:30-10:30 Teh)    |   13 |  15.4 | -0.54  | 0.24 |     7   |   -7   | -2.32 |       3.63 |             20 |
| IS       | 2 Break&retest   | Late (00:30-03:30 Teh)    |    4 |  25   | -0.421 | 0.13 |     1.7 |   -1.7 | -1.6  |       3.82 |             46 |
| IS       | 2 Break&retest   | London (10:30-15:30 Teh)  |   31 |  19.4 | -0.415 | 0.45 |    16.9 |  -12.9 | -2.07 |       3.63 |             60 |
| IS       | 2 Break&retest   | NewYork (15:30-00:30 Teh) |  208 |  31.7 | -0.155 | 0.75 |    38.7 |  -32.3 | -1.87 |       3.78 |             25 |
| IS       | 3 EMA pullback   | Asia (03:30-10:30 Teh)    |  449 |  27.4 | -0.152 | 0.7  |    70.4 |  -68.2 | -3.21 |       3.59 |             75 |
| IS       | 3 EMA pullback   | Late (00:30-03:30 Teh)    |   89 |  29.2 | -0.04  | 0.91 |    10.1 |   -3.6 | -0.36 |       3.63 |             85 |
| IS       | 3 EMA pullback   | London (10:30-15:30 Teh)  |  551 |  30.7 | -0.084 | 0.83 |    52.8 |  -46   | -1.89 |       3.61 |             69 |
| IS       | 3 EMA pullback   | NewYork (15:30-00:30 Teh) | 1152 |  31   | -0.132 | 0.75 |   162.2 | -152.5 | -4.35 |       3.89 |             52 |
| IS       | 4 Asian range BO | London (10:30-15:30 Teh)  |  286 |  10.5 | -0.138 | 0.56 |    39.4 |  -39.4 | -3.46 |       4.88 |             15 |
| OOS      | 1 Sweep+reversal | Asia (03:30-10:30 Teh)    |  480 |  30.2 | -0.221 | 0.68 |   119.2 | -105.8 | -3.85 |       4.41 |             14 |
| OOS      | 1 Sweep+reversal | Late (00:30-03:30 Teh)    |   91 |  31.9 | -0.143 | 0.79 |    23.2 |  -13   | -1.03 |       4.78 |             19 |
| OOS      | 1 Sweep+reversal | London (10:30-15:30 Teh)  |  384 |  31   | -0.209 | 0.7  |    99.1 |  -80.4 | -3.28 |       4.09 |             19 |
| OOS      | 1 Sweep+reversal | NewYork (15:30-00:30 Teh) | 1107 |  37.8 | -0.047 | 0.92 |    86.4 |  -51.7 | -1.18 |       4.48 |             14 |
| OOS      | 2 Break&retest   | Asia (03:30-10:30 Teh)    |  134 |  33.6 | -0.092 | 0.85 |    16.3 |  -12.3 | -0.85 |       4.16 |             12 |
| OOS      | 2 Break&retest   | Late (00:30-03:30 Teh)    |   41 |  34.1 |  0.007 | 1.01 |    10.2 |    0.3 |  0.03 |       4.44 |             25 |
| OOS      | 2 Break&retest   | London (10:30-15:30 Teh)  |  125 |  29.6 | -0.148 | 0.77 |    30.7 |  -18.6 | -1.33 |       3.86 |             14 |
| OOS      | 2 Break&retest   | NewYork (15:30-00:30 Teh) |  343 |  33.8 | -0.106 | 0.83 |    42   |  -36.2 | -1.56 |       4.47 |             15 |
| OOS      | 3 EMA pullback   | Asia (03:30-10:30 Teh)    |  866 |  34.2 | -0.057 | 0.9  |    66.4 |  -49.1 | -1.37 |       4.53 |             35 |
| OOS      | 3 EMA pullback   | Late (00:30-03:30 Teh)    |  181 |  34.3 | -0.13  | 0.77 |    32.1 |  -23.4 | -1.54 |       4.38 |             40 |
| OOS      | 3 EMA pullback   | London (10:30-15:30 Teh)  |  709 |  29.5 | -0.165 | 0.73 |   125.7 | -116.7 | -3.81 |       4.53 |             37 |
| OOS      | 3 EMA pullback   | NewYork (15:30-00:30 Teh) | 1217 |  31.7 | -0.147 | 0.76 |   192.6 | -179   | -4.21 |       4.76 |             32 |
| OOS      | 4 Asian range BO | London (10:30-15:30 Teh)  |   85 |  21.2 |  0.049 | 1.16 |     4.8 |    4.2 |  0.49 |       5.25 |             20 |

## Base by year

| setup            |   year |    n |   win |   avgR |   PF |   maxDD |   totR |     t |   med_risk |   med_hold_min |
|:-----------------|-------:|-----:|------:|-------:|-----:|--------:|-------:|------:|-----------:|---------------:|
| 1 Sweep+reversal |   2020 |  262 |  32.8 | -0.175 | 0.74 |    53.6 |  -45.9 | -2.24 |       3.8  |             34 |
| 1 Sweep+reversal |   2021 |  118 |  32.2 | -0.269 | 0.6  |    39   |  -31.8 | -2.5  |       3.78 |             52 |
| 1 Sweep+reversal |   2022 |  149 |  28.9 | -0.285 | 0.6  |    44.5 |  -42.5 | -2.82 |       3.72 |             37 |
| 1 Sweep+reversal |   2023 |  137 |  36.5 | -0.092 | 0.85 |    23.1 |  -12.6 | -0.84 |       3.73 |             35 |
| 1 Sweep+reversal |   2024 |  278 |  39.6 |  0     | 1    |    15.1 |    0.1 |  0.01 |       3.86 |             35 |
| 1 Sweep+reversal |   2025 |  755 |  36.3 | -0.068 | 0.89 |    74.3 |  -51.2 | -1.42 |       4.26 |             19 |
| 1 Sweep+reversal |   2026 | 1029 |  31.8 | -0.194 | 0.72 |   216.7 | -199.9 | -4.95 |       4.69 |             11 |
| 2 Break&retest   |   2020 |  106 |  27.4 | -0.208 | 0.68 |    29.4 |  -22.1 | -1.77 |       3.85 |             25 |
| 2 Break&retest   |   2021 |   41 |  31.7 | -0.333 | 0.48 |    15.4 |  -13.6 | -2.1  |       3.67 |             36 |
| 2 Break&retest   |   2022 |   53 |  24.5 | -0.278 | 0.61 |    16.7 |  -14.7 | -1.67 |       3.53 |             25 |
| 2 Break&retest   |   2023 |   56 |  35.7 | -0.061 | 0.88 |    14   |   -3.4 | -0.39 |       3.67 |             34 |
| 2 Break&retest   |   2024 |  113 |  35.4 |  0.001 | 1    |    10.7 |    0.1 |  0.01 |       3.81 |             30 |
| 2 Break&retest   |   2025 |  247 |  34   | -0.052 | 0.92 |    29.4 |  -12.9 | -0.63 |       4.11 |             19 |
| 2 Break&retest   |   2026 |  283 |  31.1 | -0.191 | 0.7  |    54   |  -54   | -2.67 |       4.71 |             10 |
| 3 EMA pullback   |   2020 |  690 |  26.4 | -0.178 | 0.68 |   123   | -123   | -4.48 |       3.93 |             55 |
| 3 EMA pullback   |   2021 |  511 |  29.7 | -0.14  | 0.72 |    80.6 |  -71.4 | -3.19 |       3.67 |             65 |
| 3 EMA pullback   |   2022 |  597 |  33.8 | -0.062 | 0.87 |    56.9 |  -36.8 | -1.45 |       3.65 |             66 |
| 3 EMA pullback   |   2023 |  443 |  31.4 | -0.088 | 0.82 |    58.4 |  -39.1 | -1.8  |       3.64 |             69 |
| 3 EMA pullback   |   2024 |  752 |  34.2 | -0.036 | 0.93 |    42.6 |  -27.2 | -0.9  |       3.76 |             60 |
| 3 EMA pullback   |   2025 | 1200 |  31.5 | -0.115 | 0.8  |   139.1 | -137.6 | -3.37 |       4.6  |             38 |
| 3 EMA pullback   |   2026 | 1021 |  31.1 | -0.199 | 0.7  |   208.8 | -203.4 | -4.99 |       5.49 |             20 |
| 4 Asian range BO |   2020 |   60 |   6.7 | -0.221 | 0.33 |    13.3 |  -13.3 | -3.02 |       4.9  |             20 |
| 4 Asian range BO |   2021 |   77 |   7.8 | -0.139 | 0.5  |    15.4 |  -10.7 | -2.05 |       5.32 |             10 |
| 4 Asian range BO |   2022 |   76 |  17.1 | -0.067 | 0.81 |    12.4 |   -5.1 | -0.69 |       4.96 |             25 |
| 4 Asian range BO |   2023 |   73 |   9.6 | -0.142 | 0.52 |    11   |  -10.3 | -1.94 |       4.39 |             15 |
| 4 Asian range BO |   2024 |   61 |  19.7 |  0.028 | 1.1  |     4.4 |    1.7 |  0.27 |       5.25 |             15 |
| 4 Asian range BO |   2025 |   24 |  25   |  0.104 | 1.26 |     4.7 |    2.5 |  0.44 |       5.24 |             22 |

## Base ALL setups by session / year

| period   | session                   |    n |   win |   avgR |   PF |   maxDD |   totR |     t |   med_risk |   med_hold_min |
|:---------|:--------------------------|-----:|------:|-------:|-----:|--------:|-------:|------:|-----------:|---------------:|
| IS       | Asia (03:30-10:30 Teh)    |  511 |  27.4 | -0.169 | 0.68 |    88.3 |  -86.2 | -3.72 |       3.61 |             73 |
| IS       | Late (00:30-03:30 Teh)    |  111 |  30.6 | -0.05  | 0.9  |    12.4 |   -5.5 | -0.48 |       3.7  |             90 |
| IS       | London (10:30-15:30 Teh)  |  946 |  24.6 | -0.107 | 0.77 |   104.1 | -100.9 | -3.35 |       3.92 |             55 |
| IS       | NewYork (15:30-00:30 Teh) | 1881 |  31.4 | -0.162 | 0.72 |   324.5 | -303.8 | -6.32 |       3.85 |             45 |
| OOS      | Asia (03:30-10:30 Teh)    | 1480 |  32.8 | -0.113 | 0.82 |   186.6 | -167.2 | -3.52 |       4.45 |             25 |
| OOS      | Late (00:30-03:30 Teh)    |  313 |  33.5 | -0.116 | 0.81 |    55.3 |  -36.2 | -1.69 |       4.46 |             31 |
| OOS      | London (10:30-15:30 Teh)  | 1303 |  29.4 | -0.162 | 0.73 |   221   | -211.4 | -4.97 |       4.37 |             25 |
| OOS      | NewYork (15:30-00:30 Teh) | 2667 |  34.5 | -0.1   | 0.84 |   287.1 | -266.9 | -4.09 |       4.62 |             21 |
|   year |    n |   win |   avgR |   PF |   maxDD |   totR |     t |   med_risk |   med_hold_min |
|-------:|-----:|------:|-------:|-----:|--------:|-------:|------:|-----------:|---------------:|
|   2020 | 1118 |  26.9 | -0.183 | 0.68 |   211   | -204.2 | -5.57 |       3.93 |             48 |
|   2021 |  747 |  28   | -0.171 | 0.67 |   140.4 | -127.6 | -4.71 |       3.78 |             55 |
|   2022 |  875 |  31   | -0.113 | 0.78 |   106.1 |  -99.1 | -3.12 |       3.74 |             58 |
|   2023 |  709 |  30.5 | -0.092 | 0.81 |    85.9 |  -65.5 | -2.32 |       3.74 |             53 |
|   2024 | 1204 |  34.8 | -0.021 | 0.96 |    54.3 |  -25.3 | -0.62 |       3.84 |             48 |
|   2025 | 2226 |  33.3 | -0.089 | 0.85 |   226.1 | -199.2 | -3.41 |       4.42 |             28 |
|   2026 | 2333 |  31.4 | -0.196 | 0.71 |   464.7 | -457.2 | -7.52 |       5.02 |             14 |

## Base exit reasons

|                             |   SL |   TP2 |   gapSL |   inval |
|:----------------------------|-----:|------:|--------:|--------:|
| ('IS', '1 Sweep+reversal')  |  486 |   150 |       2 |      28 |
| ('IS', '2 Break&retest')    |  136 |    51 |       1 |      68 |
| ('IS', '3 EMA pullback')    |  549 |   308 |       2 |    1382 |
| ('IS', '4 Asian range BO')  |   10 |    23 |       0 |     253 |
| ('OOS', '1 Sweep+reversal') | 1508 |   526 |       2 |      26 |
| ('OOS', '2 Break&retest')   |  373 |   158 |       1 |     111 |
| ('OOS', '3 EMA pullback')   | 1381 |   594 |      15 |     983 |
| ('OOS', '4 Asian range BO') |    5 |    14 |       0 |      66 |

## Portfolio, team risk rules (all 4 setups, max 2 open, stop day after 3 losses or -2R)

| period   |    n |   win |   avgR |   PF |   maxDD |   totR |     t |   med_risk |   med_hold_min |
|:---------|-----:|------:|-------:|-----:|--------:|-------:|------:|-----------:|---------------:|
| IS       | 2632 |  28.2 | -0.147 | 0.72 |   395.4 | -387.2 | -7.26 |       3.77 |             55 |
| OOS      | 2660 |  32.4 | -0.106 | 0.82 |   301.3 | -283.1 | -4.54 |       4.27 |             30 |

## $500 account, 0.01 lot (1 oz; $1 move = $1), skip R>$5 incl. spread, single exit at TP1 1.5R

Per setup (independent):

| period   | setup            |    n |   win |   avgR |   PF |   maxDD |   totR |     t |   med_risk |   med_hold_min |
|:---------|:-----------------|-----:|------:|-------:|-----:|--------:|-------:|------:|-----------:|---------------:|
| IS       | 1 Sweep+reversal |  590 |  33.4 | -0.163 | 0.75 |   104.9 |  -95.9 | -3.35 |       3.58 |             23 |
| IS       | 2 Break&retest   |  228 |  30.3 | -0.175 | 0.72 |    47   |  -39.9 | -2.37 |       3.63 |             20 |
| IS       | 3 EMA pullback   | 2195 |  29.9 | -0.135 | 0.74 |   302.4 | -297.3 | -6.31 |       3.57 |             50 |
| IS       | 4 Asian range BO |  181 |  13.3 | -0.148 | 0.57 |    26.7 |  -26.7 | -2.91 |       3.98 |             15 |
| OOS      | 1 Sweep+reversal | 1517 |  32.9 | -0.177 | 0.74 |   276.6 | -267.8 | -5.86 |       3.83 |              9 |
| OOS      | 2 Break&retest   |  445 |  30.3 | -0.188 | 0.71 |    83.5 |  -83.5 | -3.52 |       3.76 |             10 |
| OOS      | 3 EMA pullback   | 2424 |  31.7 | -0.153 | 0.75 |   384.6 | -369.9 | -6.59 |       3.82 |             25 |
| OOS      | 4 Asian range BO |   41 |  22   | -0.071 | 0.82 |     5.2 |   -2.9 | -0.51 |       4.26 |             20 |

Portfolio of all 4 setups (max 2 open):

| rule                                             | period   |   trades |   net_usd |   worst_day_usd |   days_over_10_loss |   days_traded |   maxDD_usd |   win |   PF |
|:-------------------------------------------------|:---------|---------:|----------:|----------------:|--------------------:|--------------:|------------:|------:|-----:|
| no daily cap (max 2 open only)                   | IS       |     3162 |   -1634.2 |          -34.01 |                 109 |           904 |      1665.3 |  29.7 | 0.75 |
| no daily cap (max 2 open only)                   | OOS      |     4398 |   -2641.5 |          -57.1  |                 199 |           712 |      2682.6 |  31.9 | 0.75 |
| $10/day cap: no new trades after day P&L <= -$10 | IS       |     2936 |   -1472.8 |          -15.57 |                 130 |           904 |      1505.2 |  29.8 | 0.75 |
| $10/day cap: no new trades after day P&L <= -$10 | OOS      |     3485 |   -2188.9 |          -18.72 |                 279 |           712 |      2229.9 |  31.2 | 0.74 |

Note: with 2 positions open the cap is checked on closed trades only, so a day can still end below -$10.


## Bias check (info): H1 EMA20/50 and M15 EMA20/50 agree -> direction; hit = same sign as BID close 2h later

| period   | session   |   n_agree |   hit_H1M15_agree |   n_h1 |   hit_H1_only |   up_share |
|:---------|:----------|----------:|------------------:|-------:|--------------:|-----------:|
| IS       | Asia      |      5212 |             0.483 |   7219 |         0.493 |      0.504 |
| IS       | Late      |      1079 |             0.451 |   1473 |         0.458 |      0.56  |
| IS       | London    |      3523 |             0.506 |   5160 |         0.504 |      0.509 |
| IS       | NewYork   |      5663 |             0.503 |   8492 |         0.508 |      0.493 |
| OOS      | Asia      |      3644 |             0.496 |   5124 |         0.5   |      0.525 |
| OOS      | Late      |       767 |             0.472 |   1067 |         0.496 |      0.57  |
| OOS      | London    |      2432 |             0.498 |   3655 |         0.489 |      0.533 |
| OOS      | NewYork   |      4067 |             0.523 |   5993 |         0.518 |      0.523 |

meta: {"n_fomc_events": 56}