# ZARVA Map (formerly Xauscalper Map): formulas shared by the indicator and the bot

The TradingView indicator `tradingview/xauscalper_map*.pine` (built from `tradingview/map/template.pine`) mirrors:
- the levels of `tools/levels.py` + `tools/level_view.py` (the snapshot behind `/levels`);
- the trend, price placement, setups, validity and credibility of `supabase/functions/tg-bot/assist.js`
  (branch `bot-assistant-v2`, commits f2652cb + 737b446, also on main).

**Price frames (same as the bot).**
- ONE price basis (owner t244u, 2026-11-21): DaryaGold = **Dukascopy mid + 0.02** (input «اختلاف قیمت دریاگلد با قیمت میانه»; bot:
  `bot_state.dg_offset`, `/offset`, `/calibrate`) for levels, the live price, setups, distance to entry, fills and alerts.
  Levels are built on bid bars and moved by half the typical feed spread: level = bid + 0.175 + 0.02 = bid + 0.195
  (bot `assist.levelOffset`, Python `broker_daryagold.set_mid_offset`). Until 2026-11-21 levels were bid + 0.30.
- The chart feed is bid by default (OANDA or Dukascopy), with mid = bid + spread/2 and a feed spread of 0.35 (the bot's fallback). With a mid feed, choose «mid».

## 1. Levels (port of levels.compute → level_view.short_view)
- Bars: 5m/15m/1h/4h are rebuilt on the chart as UTC clock buckets, like pandas `resample(label=left, closed=left)`. The forming bar is included, as in the bot.
- ATR = Wilder 14, seeded with the first TR. EMA20/50 are seeded with the first close (pandas `ewm(adjust=False)`).
- Candidates are the same kinds and weights as `levels.W`. Week and previous-week H/L are added via the structure step only, as in the bot.
  The candidate filter is `rng = max(60, 8×ATR_H1)`. Rounds every $5 are added after the filter.
- Cluster: sort, then chain while the gap is ≤ `tol = max(0.5, 0.25×ATR_M5)`. The price is the mean of the structural members (not Round/EMA/VWAP), rounded to 2 decimals.
- Display set B kinds only. Month kinds are dropped when more than 3×ATR_H4 away.
- `half = max(1, round(0.25×ATR_M5, 2))`, zone = `dg ± half`. Structure H/L within `half` of an item are merged into it.
  `merge_zones` merges overlaps sequentially and averages the price.
- Shown: 2 zones whose bid price is above the close and 2 below, nearest first. Labels use 1 decimal, like the bot's `_px`.
- Verified on the Dukascopy cache at 2026-11-20 16:40 Tehran. The bot gave 3600.3 / 3595.35 / 3566.4 / 3562.54. The indicator gave
  3600.3 / 3595.36 / 3566.4 / 3562.55. Same kinds; ±0.01 is float rounding.

## 2. Trend (port of level_view.trend_of / verdict_line)
- Per timeframe: fractal swings (n = 3) inside the lookback (H4 20 d, H1 8 d, M15 2 d, M5 1 d). The structure compares the last two highs and the last two lows.
  `up` means both rise and `down` means both fall. EMA: `e20 > e50 and close > e20` is bullish, the mirror is bearish. Fewer than 56 bars means no EMA, so neutral.
- A timeframe is صعودی only when structure is up AND EMA is bullish; نزولی is the mirror; anything else is خنثی.
- Overall: H4 and H1 equal and not neutral gives that direction, otherwise نامشخص. M15 or M5 opposite to it means «در اصلاح».
- Verified at the same snapshot: H4↓ H1↓ M15→ M5↓, overall نزولی. This matches the bot.

## 3. Price placement and setups (port of assist.js)
- `SPREAD = 0.25`. A buy fills at the ask, so buy ranges and sell SL/TP are moved up by the spread.
- `offHalf`: a price within 0.03 of .00/.50 moves 0.07 away.
- `R5(lo, hi)`: the $5 multiples in [lo, hi], in the DaryaGold frame.
- **Range** `w = clamp(0.2×ATR, 0.5, 1.5)`.
  - Sell: `[L−w, L]`. A round number in `(lo, hi+0.6]` moves the top to `round − 0.15`.
  - Buy: `[L, L+w]`. A round number in `[lo−0.6, hi)` moves the bottom to `round + 0.15`. The buy range then gets `+ SPREAD`.
- **SL**: `edge ± max(0.5, 0.3×ATR)`, at least `max(1, 0.5×ATR)` from the best edge.
  - A sell SL with a round number in `[sl−0.8, sl+0.3]` moves to `round + 0.6`. A buy SL is the mirror, moving to `round − 0.6`.
  - Then offHalf; a sell SL gets `+ SPREAD`.
- **TP**: the near zone edge of an obstacle among the four shown levels beyond `from ± 0.5` (from = range low for a sell, high for a buy), then `∓ 0.1`.
  - A round number in `[tp−0.3, tp+0.7]` (sell) moves the TP to `round + 0.35`. A buy TP is the mirror, moving to `round − 0.35`.
  - Then offHalf; a sell TP gets `+ SPREAD`.
  - With no obstacle, `TP1 = from ± max(1.5, 1.2×ATR)`.
  - TP2 = the next obstacle. If there is none, or it is less than 0.5 beyond TP1, `TP2 = TP1 ± max(1.5, ATR)`.
- **Direction**: sell when `P < L.lo` or (`P ≤ L.hi` and the level is a resistance), otherwise buy. Keep the best 2 per side by score.
- **Reject** a setup in any of these cases:
  - price is already past the SL;
  - risk (SL to worst edge) + M5 ATR(14) > $9 (stricter rule, owner t244u 2026-11-21; was risk > $9);
  - distance to the range > 4×ATR;
  - TP1 is not beyond mid, or room < max(1, 0.5×|SL−mid|);
  - net R:R (80,000 per $, fee 14,000) < 0.6.
- **ATR** is the ATR(14) of **closed** M5 bars.
- **Toman** = `Δ$ × 80,000 × units − 14,000`. The indicator shows both the best and the worst edge, like the bot.

## 4. Validity (assist.validity / entryLimit)
- No setups when DaryaGold is closed (07:00–00:30 Tehran, Mon–Fri), after Friday 23:30, or inside a major news window.
- `until = min(now + 45 min, close or Friday cutoff, next major news start)`. No new setups when less than 10 min is left.
- Pine cannot read the bot's news file, so it uses fixed releases: 08:30 and 10:00 New York, optional 14:00, from 15 min before to 20 min after.
- The indicator freezes a setup's numbers at birth and keeps it until `until`.
- A pending setup is removed if the SL is hit before the fill (invalidated) or TP1 is hit before the fill (missed), with the bot's fill tests:
  a sell fills when `high ≥ lo`, a buy when `low + spread ≤ hi`.
- After the fill, the setup is removed on SL, on TP2, or `holdMin` (60) minutes later. The bot tracks outcomes for up to 6 h.

## 5. Credibility (assist.scoreSetup)
Weights: trend 25, fill 15, level 15, room 10, rr 15, adr 8, session 7, hunt 5. Each factor is clamped to 0–1, and the total is rounded.
- trend: `(Σ w·(+1 same / −1 opposite / 0) + 1)/2` with H4 0.3, H1 0.3, M15 0.25, M5 0.15.
- fill: 1 if inside the range, else `1 − dist/(3×ATR)`.
- level: `0.6×STR + 0.4×FRESH[min(touches,5)]`.
  - STR is strong 1, medium 0.65, weak 0.35, from the compute() cluster score (Σ W + min(2, 0.5×touches); strong ≥ 6, medium ≥ 3.5).
    Items that come only from the structure block count as medium with 0 touches.
  - FRESH = [0.5, 0.9, 1, 0.9, 0.75, 0.6].
- room: `room/(1.5×ATR)`. rr: `(RR − 0.5)/1.5`. adr: `(130 − ADR used)/80`, or 0.5 when unknown.
- session: 0.6 at 07:00–10:30, 0.5 at 23:00–00:30, else 1. Capped at 0.4 when news starts within 60 min (fixed release times in Pine).
- hunt: `1 − 0.25` if the level has a high/low/PDH/PDL kind, and `− 0.25` more if a $5 round lies within ±1 of the SL.
- Below 40 the setup gets ⚠.

## 6. Market-state light
- Volatility follows `assist.volState`, using the closed M5 ATR:
  - percentile over the last 288 values ≥ 90, or one bar ≥ 2.5×ATR → پرنوسان;
  - ≤ 10 at 10:30–22:30 Tehran → کم‌تحرک;
  - otherwise مناسب.
- خبر نزدیک inside a fixed release window. «پایان کار نزدیک» within 30 min of 00:30, or of 23:30 on Friday.
- The trend-strip background turns orange for news, close-near, or after the Friday cutoff.
- Room to trade: $ from the price to the next zone in the overall trend direction. «جا دارد» if ≥ the target (default $5).

## Verification (Dukascopy cache, 2026-11-20 16:40 Tehran)
Same inputs to both: P 3575.41, closed ATR 5.458, trend ↓↓→↓, ADR used 130.2%.

| level | bot (assist.buildSetups) | indicator |
|---|---|---|
| 3595.35 sell | 3593.76–3594.85, SL 3598.63, TP 3568.14 / 3564.35, score 73 | 3593.76–3594.85, SL 3598.64, TP 3568.14 / 3564.29, score 73 |
| 3566.4 buy | 3566.65–3567.67, SL 3563.37, TP 3593.86 / 3598.81, score 60 | 3566.65–3567.67, SL 3563.37, TP 3593.87 / 3598.81, score 60 |
| 3600.3 sell | rejected (far) | rejected |
| 3562.54 buy | rejected (room) | rejected |

Strength and touches are identical (strong 2, weak 1, strong 5, medium 3). The ±0.01–0.06 differences come from levels that differ by 0.01
(Python vs Pine rounding of x.xx5 means, e.g. 3595.055 → .05 vs .06).

## Known differences from the bot
- The bot recomputes setups on every `/setup` call from a snapshot up to 15 min old. The indicator recomputes levels on every bar and freezes a setup from birth until it expires.
- `entryLimit` in the bot treats Sunday and Monday 00:00–00:30 Tehran as open (no market data then). The indicator treats them as closed.
- News: the bot uses its calendar (tier A/B/FOMC windows). The indicator uses fixed release times.
- The bot computes EMAs over the last 300 native bars; the indicator computes them from the chart start. The difference is negligible after warm-up.
- VWAP and session VWAPs use the chart's volume (OANDA tick volume), not Dukascopy bid+ask ticks on the mid price. This gives small shifts.
- The ADR uses the 20 previous chart days. The bot drops stub days (fewer than 800 1-min bars or less than 16 h). If fewer than 20 days are loaded, the daily series is used.
- The current month's H/L comes from the chart when the history reaches the month start, otherwise from the monthly series (TradingView month ≈ New York month).
- With about 5000 bars (free plan, about 18 trading days on M5), the EMA50 on H4 is close but not identical, and 20-day H4 swings near the start may be missing.
- Touches use M15 bars rebuilt on the chart, the same as the bot's touch definition, but only for credibility.

## Labels (2026-11-20, owner t242u)
Persian labels were rewritten in plain words for beginners; formulas are unchanged (the generated
xauscalper_map.pine differs from 90625ad only in string literals and the header comment).
- Level sources use the bot's plain names (KIND_FA / plainLabel): «سقف دیروز», «کف صبح امروز» (Asia),
  «سقف ظهر امروز» (London), «کف عصر» (NY), «شروع ظهر/عصر» (opening range), «برگشت اخیر قیمت» (H1 swing),
  «عدد رُند N», «میانگین قیمت امروز» (VWAP); joined with «، ».
- Trend strip: «صعودی (رو به بالا)», «نزولی (رو به پایین)», «بدون جهت», «جهت روشن نیست»; the lower-frame row says
  «کوتاه‌مدت هم همین جهت است» / «… فعلاً برعکس برگشته» instead of «در اصلاح».
- Market light: «شرایط عادی», «بازار خیلی پرنوسان است», «بازار خیلی آرام است», «خبر مهم نزدیک است»,
  «بسته‌شدن دریاگلد نزدیک است», «ورود جدید بسته است». Room: «جا برای سود هست / کم است».
- Setup labels: «حد ضرر», «حد سود ۱», «حد سود ۲» instead of SL/TP1/TP2. The English build is unchanged.

