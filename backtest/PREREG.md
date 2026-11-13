# PREREG — M5 Gold Scalp, 4 setups from /workspace/m5signal/SETUP_RULES.md v0.1
Written 2026-11-12 ~14:10 Tehran, BEFORE any result was computed. Interpretations below are frozen; nothing is tuned on IS or OOS.
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
