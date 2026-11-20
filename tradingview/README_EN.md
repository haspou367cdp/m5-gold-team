# Xauscalper Zones — TradingView indicator (English)

Companion to the Xauscalper Telegram bot. It draws the bot's logic on the chart: multi-timeframe trend, level zones, the zone-entry setup with a single TP, net R:R with DaryaGold costs, and the risk filters.

Files: `xauscalper_zones_en.pine` (English) and `xauscalper_zones.pine` (Persian). The logic is identical; only labels, table text, inputs and alerts differ. Both are generated from `src/template.pine` by `python3 src/build.py`, so edit the template only.

## Install
1. Open `OANDA:XAUUSD` (or any XAUUSD) on **M5**. M1/M3 also work; the table warns when the chart is not M5.
2. Open **Pine Editor**, replace everything with the file's contents, **Save**, then **Add to chart**.
3. Alerts: Alert → Condition "Xauscalper Zones" → "Any alert() function call" (full message with entry/SL/TP/RR), or "XSZ long setup" / "XSZ short setup".

## Table (4 columns: name | number | second number | text)
- Bias: H4 + H1 (Bullish/Bearish/Neutral). "aligned" = M15 agrees; "correction" = M15 or M5 is against it.
- H4 H1 M15 M5 arrows: EMA20 vs EMA50 and price beyond EMA50, closed bars only (no repaint).
- ATR M5 and its median (orange = volatility expansion). ADR used % and the 20-day ADR. Zone half-width.
- Above 1/2, Below 1/2: price, $ distance, level sources.
- Risk status, DaryaGold price (chart + offset), chart price.
- Blocked today: how many setups were blocked today and by which filter. If one filter blocks most setups, its threshold is an input (e.g. "Max SL + ATR" for the stop-out buffer).

## Zones
Levels: PDH/PDL, PWH/PWL, Asia H/L (03:30–11:30 Tehran), London H/L (07:00 London → 08:30 New York), London opening range (first 30 min), NY open (08:30 New York), day VWAP, $50/$00 round numbers. Zone = level ± max(0.25 × M5 ATR, $1). Overlapping zones merge. 2 above and 2 below are shown by distance. Labels sit at the right edge: price to the right, first source to the left (hover for all). Zones closer than $3 share one label. Labels name the source only; they are not a ranking.

## Zone-entry setup
- Price in a zone, direction = H1 and M15 trend, next level at least 2 × SL away.
- SL = beyond the zone's far edge + max($0.5, 0.3 × ATR), at least max($1, 0.6 × ATR).
- TP = just before the next level (max($0.3, 0.1 × ATR)). One TP.
- Net R:R includes the once-per-trade fee, toman per $ by size, and $0.25 spread on market entries. Minimum 1.5; above 8 is rejected.
- Coloured marker: ▲ Buy / ▼ Sell, then E (entry), SL, TP, RR. Lines last 6 bars (30-minute order expiry).
- Tiny grey cross: a setup blocked by a filter; hover for the reason. Default "First per streak" (only when the reason changes); "All" and "None" are available.

## Filters
Outside DaryaGold hours (Mon–Fri 07:00–00:30 Tehran), Friday after 23:30, ADR used > 100%, M5 ATR > 2 × median, SL + ATR > $5 (stop-out is about $10 away), TP > 3 × ATR, and three manual news windows (Pine can't read a calendar; enter tier A/B times from the bot's /brief).

## Using it with the bot
1. A bot signal arrives → check the price is in that zone and the table says Allowed.
2. A setup on the chart but no bot signal → send /scan to see why.
3. An expired signal means no trade.
4. Keep the DaryaGold offset in sync with the bot's /calibrate value.

## Optimisations in this version
- 4 request.security calls instead of 6 (base-timeframe trend and ATR share one tuple call).
- ATR median from one sample per hour, recomputed only when a sample is added.
- Arrays are allocated once and cleared; levels and setups are evaluated only on the last 3,000 bars (input).
- Zones and table are redrawn only on the last bar.
- Session levels reset at the trading-day change, so yesterday's London levels never show as today's.

## Limitations
- The Asia session uses fixed Tehran times; London and New York follow their own DST.
- PDH/PDL and ADR use the chart symbol's trading day (17:00 New York on OANDA), not the bot's 18:00 New York.
- VWAP uses the chart broker's tick volume.
- ADR needs at least 5 days of chart history; the ATR median needs 24 hourly samples.
