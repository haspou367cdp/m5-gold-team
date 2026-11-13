# M5 Gold Scalp toolkit (XAUUSD, M5) — `/workspace/m5-gold-team/tools/`

The owner (pouhasaa, DaryaGold, Asia/Tehran) uses this brief for a live layered read of XAUUSD.
Account equity defaults to `tools/broker_daryagold.json` (`equity_toman`, overridable with `EQUITY_TOMAN` or `--equity`).
`brief.py` prints: **(1) BUY / SELL / NO TRADE with accept/reject reasons, (2) regime + allowed engine, (3) direction (H4, H1, M15), (4) ADR and reference highs/lows (day, week, month, sessions, opening ranges), (5) macro (DXY / 2Y / 10Y / real yield / 5Y–10Y breakevens), (6) DaryaGold risk gates and unit sizing, (7) nearby highs/lows without strength labels.**
Displayed gold prices are DaryaGold-adjusted (`bid + price_offset_usd`) with the raw Dukascopy bid in brackets. Engines still run on the bid. If a setup fires, a numeric plan is sized in نیم‌واحدی / یک واحد and may be vetoed. The two engines in `regime.py` are **unvalidated detectors** only (see `preregistration_engines.md`).
Signal-only research, not financial advice, nothing here places trades.

## One command
```bash
python3 /workspace/m5-gold-team/tools/brief.py                  # fetch price + macro (in parallel) + levels + bias + regime + Persian brief (target < 60 s)
python3 /workspace/m5-gold-team/tools/brief.py --no-fetch       # reuse cached price + macro (fast)
python3 /workspace/m5-gold-team/tools/brief.py --equity 2085600 # override equity (toman)
```
Outputs: stdout (Persian markdown), `/workspace/m5-gold-team/latest_brief.md`, `/workspace/m5-gold-team/latest_brief.json`.
Exit codes: 0 ok · 2 data stale or data-quality gate failed (brief says **NO TRADE** / stop, do not publish prices) · 3 no data source worked.

## Tools
| File | What it does | Inputs | Outputs | Used by |
|---|---|---|---|---|
| `fetch_xauusd.py [--days 10] [--max-age 15] [--source auto\|dukascopy\|yahoo]` | Pulls XAU/USD 1m **bid + ask** from the Dukascopy public chart feed, resamples to M5/M15/H1/**H4** (bid OHLC, ask close, spread, tick volume). **Merges** with any older cached bars (kept back at least through the previous NY month, and not less than 80 calendar days) so a short incremental fetch does not wipe history needed for prev-month H/L and ADR(20). Fails loudly (exit 2, `stale: true`) if the last bar closed > `--max-age` min ago while the market is open (`brief.py` passes `--max-age 10`). Fallback: Yahoo `GC=F` (COMEX **futures**, no bid/ask, may be ~10 min delayed) — labelled `FALLBACK` everywhere. | internet | `data/xauusd_{1m,m5,m15,h1,h4}.parquet`, `data/meta.json` | everyone (`brief.py` calls it with `--days 3` when the cache already covers the previous NY calendar month, otherwise enough days for prev-month H/L and ADR20) |
| `levels.py [--print] [--range 60]` | Previous trading-day H/L, previous **calendar-month** H/L (NY month; flagged incomplete if the cache starts late) + month-to-date, older daily H/L (5 days), today's Asia/London/NY H/L + yesterday's NY, **opening range** (first 30 min of London and NY), **equal highs/lows on M15**, $5/$10 rounds, trading-day and **session VWAPs** (tick-volume proxy) ±1σ on the day VWAP, EMA20/50 on M5/M15/H1/**H4**, ATR(14) M5/H1/H4, fractal swings M5/M15/H1/H4. Clusters nearby candidates and stores ranks in JSON only. `--print` shows score, not قوی/متوسط/ضعیف. | cache | `data/levels.json` | M5-Levels (main), M5-Signal |
| `bias.py [--at "YYYY-MM-DD HH:MM"]` | **H4** (required) + H1 + M15 trend (EMA order, EMA20 slope, swing structure); M5 is context only; D1 is not used for direction. Combines with M5-News bias. News windows are tier-aware (A and B block entries under the DaryaGold rule, B also requires being flat before the window + spread check, C is monitor). "Now" verdict + invalidation levels. | cache, `levels.json`, `news_windows.json` | `data/bias.json` | M5-Signal (main), M5-Risk |
| `news_windows.py seed\|add\|event\|bias\|list\|now\|prune` | No-trade windows (Tehran time), M5-News bias, and **A/B/C tiers**. `event` defaults follow `window_policy` in `data/news_windows.json`: US A-data 15/30, FOMC statement 30/90 (30 before the statement to 60 after a presser starting ~30 min later), FOMC presser-only 30/60, Fed Chair speech 15/30, B data/minutes 15/15, B Fed speech 15/30, C 5/15. Stored `tier`/`fomc`/start/end are never overwritten. `now` checks the **effective** windows (stored ∪ DaryaGold floors) and exits 1 on an active **tier-A or tier-B block** (or the last 5 min before one); tier C never blocks. **stdlib only** (no pandas). | `/workspace/team/m5-news/latest.md` (seed) or CLI | `data/news_windows.json` | M5-News (writes), M5-Risk / bias.py (reads) |
| `macro.py [--no-fetch] [--ttl 600]` | DXY (Yahoo `DX-Y.NYB`, fallback `DX=F` then EURUSD proxy), US 10Y nominal (Yahoo `^TNX`, fallback FRED DGS10 lagged), **US 2Y** (Yahoo `2YY=F` 2-Year Yield Futures, *not* the cash 2Y; official cash is FRED DGS2 lagged — `^IRX` is the 13-week bill and is not used), 10Y real yield (FRED DFII10, lagged), **5Y/10Y inflation breakevens** (FRED T5YIE / T10YIE, lagged). 10-minute cache, 6 s HTTP timeout, 10 s overall budget. | internet or `data/macro.json` | `data/macro.json` | `brief.py` (parallel with the price fetch) |
| `regime.py` | 4-state regime gate: **trend** → continuation engine allowed; **range** → sweep/mean-reversion engine allowed; **volatility_expansion** (M5 ATR percentile, relative tick volume) → wait; **news_abnormal** (tier-A window or spread anomaly) → no trade. Optional ADX(14) on H1/M15 and session-VWAP deviation (tick-volume proxy). Two setup detectors, flagged unvalidated. | `levels.json`, bars, news/spread | used in-process by `brief.py` | `brief.py` |
| `broker_daryagold.json` / `broker_daryagold.py` | DaryaGold contract, equity, unit sizes, fees, price offset, and risk floors. `load_config(equity=)` honors `--equity` then `EQUITY_TOMAN`. Sizing picks the largest unit (full, else half) whose SL loss + fee + spread cost stays inside `risk_per_trade_pct_max`. Half-unit fee is conservatively 14000 toman (unconfirmed). News floors (A 15/30, B 10/15) are unioned with stored windows, never shrinking them. DaryaGold hours follow forex (Sun 18:00 NY to Fri 17:00 NY, DST-aware; closed Sat/Sun). Overnight weekday holds are allowed (no daily 22:30/00:30 cutoff). Friday only: no new entries in the last 2 hours before Friday 17:00 NY (23:30 Tehran in US winter) and all trades must be closed before that close (01:30 Tehran in US winter). Outside forex hours or on Sat/Sun → NO TRADE. | config + bid prices | sizing / formatted prices | `brief.py`, `bias.py` |
| `brief.py` | Runs fetch + macro (parallel), levels, bias, regime, engines, and the Persian brief. Prints gold prices as DaryaGold (bid + offset) with the raw bid in brackets. **Data-quality gate:** missing data or last bar older than 10 minutes while the market is open → **NO TRADE / stop**, no full analysis. **Does not print قوی/متوسط/ضعیف.** Always prints DaryaGold risk gates (including forex hours and the Friday 23:30/01:30 close, DST-aware), the 60-second hold rule, and the weekend/Iranian-holiday warning. | — | `latest_brief.md`, `latest_brief.json` | Boti (posts to owner), all bots |
| `preregistration_engines.md` | Pre-registration stub for the two engines' separate out-of-sample backtests. No results are claimed. | — | — | research, later backtests |
| `m5lib.py` | Shared paths, Tehran formatting, market hours, session clock, H4 fallback resample, NY month bounds. | — | — | imported |

### News-window semantics (single source of truth: `news_windows.py` `effective_doc`)
Effective window = union of the stored `[start, end)` in `data/news_windows.json` and the DaryaGold floors in `broker_daryagold.json` `news_buffers` (A: 15 min before / 30 after the release, B: 10 before / 15 after), never shrunk. **No new entries anywhere inside the effective window (tier A and B).** For tier B, close positions and cancel pending orders **before the effective start**. Example: PPI 17:00, stored 16:45–17:15 → effective 16:45–17:15 → no entries from **16:45** and be flat by 16:45 (not "from 16:50"). Tier C = monitor only. `brief.py`, `bias.py`, `regime.py` and `news_windows.py now` all use this.

### Sessions / clock (DST-correct via `zoneinfo`; values below are for US/UK winter time)
- Gold trading day: 18:00→17:00 New York = **02:30 → 01:30 Tehran**. Daily break 01:30–02:30 Tehran; weekend Fri 01:30 Tehran (Sat) → Mon 02:30 Tehran.
- Asia 00:00 UTC→07:00 London = **03:30–10:30 Tehran** · London 07:00 London→08:30 NY = **10:30–17:00 Tehran** · New York 08:30→17:00 NY = **17:00–01:30 Tehran**.
- Opening range = first **30 minutes** of London (10:30–11:00 Tehran in winter) and of New York (17:00–17:30 Tehran in winter).
- US 08:30 ET data = **17:00 Tehran** in winter.

### Regime gate and engines (heuristics, NOT backtested)
1. **news_abnormal** — inside a tier-A or tier-B effective no-entry window (or within 5 min of one), or spread > 2× typical for that hour **and** > $0.80 → no trade. Tier C is monitor only.
2. **volatility_expansion** — M5 ATR(14) at or above the 90th percentile of the last ~200 bars, or at/above the 80th with a rising ATR or relative tick volume ≥ 1.8× → wait.
3. **trend** — directional H4 (or H4+H1) with optional ADX(14) H1 ≥ 25 as confirmation, and the session range not tight → **continuation** engine may fire.
4. **range** — otherwise (tight session range vs H1 ATR, mixed structure, or low ADX) → **sweep / mean-reversion** engine may fire.

Engines are detectors only. They are flagged unvalidated in the brief. See `preregistration_engines.md`. VWAP and relative volume use **tick volume**, labelled as a tick-volume proxy, not exchange volume.

### Level ranking (heuristic, NOT backtested)
Candidates within `max($0.5, 0.25×ATR_M5)` are merged. Score = sum of source weights (H4/H1 swing / PDH / PDL / previous-month H/L 3, London/NY H/L 2.5, equal M15 H/L 2.5, older daily H/L 2.5, Asia H/L and opening ranges 2, M15 swing 2, VWAP / session VWAP 1.2–1.5, H4 EMA 2, H1 EMA 1.5, $100 round 2.5, …) + 0.5 per distinct M15 reaction in the last 3 days (max +2). Ranks (`strong ≥ 6`, `medium ≥ 3.5`) stay in JSON only. The brief still *selects* medium/strong candidates (so isolated weak $5/$10 rounds are not dumped) but **does not print** قوی/متوسط/ضعیف — those ranks are unvalidated and must not be treated as edge. A resistance built from old lows is shown as "کف شکسته‌شده (حالا مقاومت)". `levels.py` also writes `structure` (week, previous week, previous month, month-to-date, ADR-20, % used, D1 structure for levels only), `opening_ranges`, `equal`, and `session_vwap`.

### "Now" verdict rules (bias.py), first match wins
1. data stale / market closed → no opinion · 2. inside a **tier-A or tier-B block** window → wait until it ends · 3. a block window starts within 5 min → wait. Within 120 min of a block window the verdict also prints the flat-by time (close positions / cancel orders before the window start)
4. spread > 2× typical for that hour and > $0.8 → wait · 5. bias neutral (H4/H1/M15 disagree or technical ≠ M5-News) → wait for range edges
6. price within **0.3×ATR_M5** of a medium/strong level **in the bias direction** → `near_level` ("only with an M5 rejection candle")
7. sitting on a high-score level against the bias → wait · 8. otherwise mid-range → "wait for X".
The brief's **BUY / SELL / NO TRADE** is the regime+engine decision on top of this; a `near_level` verdict alone is not enough to print BUY/SELL.
Invalidation: bearish → M15 close above nearest high-score resistance = neutral; H1 close above last H1 swing high = bias off (mirrored for bullish).

### Hard risk gates — DaryaGold (printed every analysis)
Source of truth: `broker_daryagold.json` (equity is user-editable). Default equity 2,085,600 toman. Max risk per trade **10%**, daily loss cap **20%**, max 3 closed losses, 1 open position, net R:R after fee+spread ≥ **1.5**.
- Sizes: نیم واحدی (margin 500,000; 40,000 toman per $1) or یک واحد (margin 1,000,000; 80,000 toman per $1). Pick the largest size whose SL loss + fee + spread cost fits the risk budget; if even the half unit does not, **NO TRADE**.
- Half-unit fee is conservatively **14,000 toman** (unconfirmed; broker states 14,000 per unit).
- Min stop **$1.0** (broker flags tighter stops). Prefer a limit **order** (no entry spread). SL/TP are stated to have no spread; a typical/current spread is still added as a conservative cost.
- Liquidation is at **80%** of the whole portfolio, not just the blocked margin.
- News: effective window = the stricter of stored `news_windows.json` start/end and floors of **A 15 minutes before / 30 after**, **B 10 / 15**. Stored windows are never rewritten.
- Hours follow **forex** (Sun 18:00 NY open to Fri 17:00 NY close, DST-aware; closed Saturday and Sunday). Overnight weekday holds are allowed; there is **no** daily 22:30/00:30 cutoff. Friday only: no new entries from **2 hours** before Friday 17:00 New York (23:30 Tehran in US winter) and all trades must be closed before that close (01:30 Tehran in US winter). Outside forex hours or on Sat/Sun → **NO TRADE**. Do not hold over the weekend or official Iranian holidays (the platform may close). Manual or TP exits must stay open at least **60 seconds**.
- Spread anomaly unchanged: > 2× typical for that hour **and** > $0.80 → no entry.
- Price display: DaryaGold ≈ Dukascopy bid + `price_offset_usd` (0.3, calibrated 2026-11-13 15:37 Tehran, uncertainty ±0.5). Raw bid is shown in brackets. Engines still use the bid.

### News tiers
Auto-classification is only used for *new* `event`/`add` rows. If a window already has `tier` and/or `fomc` set (M5-News hand-set the current 37 windows at 12:59 Tehran on 2026-11-13), those fields and the stored start/end are **never overwritten**.

| Tier | Events (classifier) | Brief / `now` behaviour | Default `event` buffer |
|---|---|---|---|
| A | **US** CPI (country + event; UK/other CPI is not A), NFP, Core PCE / PCE; FOMC *decision/statement/presser* (`fomc=true`); Fed Chair speeches (`fomc=false`) | hard block | A data **15 / 30**; FOMC statement **30 / 90** (30 before the statement, 60 after a presser that starts ~30 min later); FOMC presser-only **30 / 60**; Chair speech **15 / 30** |
| B | **FOMC minutes** (`fomc=false`, not an FOMC block); PPI, ISM, Retail Sales, GDP; named non-US CPI; other Fed speeches (governors, vice chairs, presidents) | **no-entry block** (DaryaGold team rule 2026-11-13) + be flat before the window | B data / minutes **15 / 15**; B speech / Q&A **15 / 30** |
| C | everything else (claims, ceremonial remarks, …) | monitor only | 5 / 15 (calendar only) |

A bare label of just "CPI" or a lone "FOMC" without minutes/decision is **not** auto-upgraded to A. M5-News can still set the tier by hand.

## How each bot uses it
- **M5-News**: after each brief, `python3 news_windows.py seed` (reads `/workspace/team/m5-news/latest.md`; keep the `- HH:MM-HH:MM | label` format under `today_YYYY-MM-DD:` / `tomorrow_YYYY-MM-DD:`, add `(Fri)` for after-midnight events) and `python3 news_windows.py bias --bias bearish --why "..." --invalidation "..."`. Single event: `news_windows.py event --date 2026-11-13 --time 17:00 --label "US PPI"` (tier B, caution, 15/15). For a rate decision use a label such as `FOMC rate decision` (`--time` = statement time) so the 30/90 FOMC buffer applies. `FOMC minutes` is tier B, `fomc=false`, and does not hard-block.
- **M5-Levels**: `python3 fetch_xauusd.py && python3 levels.py --print`; full numbers in `data/levels.json`.
- **M5-Signal**: `python3 brief.py` → report decision / direction / now-or-wait / levels only (no entry/SL/TP unless the owner asks).
- **M5-Risk**: `python3 news_windows.py now` (effective windows; exit 1 = tier-A or tier-B block) and `jq .spread data/bias.json`; warn on stale data (`meta.json` `stale: true` or age > 10 min in session) or abnormal spread. Size in DaryaGold units from `broker_daryagold.py`; veto if the half unit exceeds the 10% budget, SL < $1, net R:R < 1.5, the market is outside forex hours or inside the Friday no-entry window (from 23:30 Tehran in US winter until Friday 17:00 NY / 01:30 Tehran), or the daily 20% / 3-loss stop.
- **M5-Journal**: log `latest_brief.json` (as_of, bias, decision, regime, levels) to `session_log.csv`; later check whether bias/levels/engines held.
- **Boti**: `python3 brief.py` and post the stdout to the owner.

## What was intentionally not built (no real data, or would be fabricated)
- **GC order flow**: delta, footprint, absorption, DOM, heatmap. No live or historical series is available here. A paid feed such as Databento would be needed; until then this layer stays out, not filled with invented numbers.
- **Exchange / real volume** and a real volume-profile (POC / VAH / VAL). Tick volume is a proxy only and is labelled as such on every VWAP and relative-volume line.
- **Live official cash 2Y** and **live real yield / breakevens**. FRED DGS2, DFII10, T5YIE and T10YIE are **daily and lagged**. Yahoo `2YY=F` is **2-Year Yield Futures**, not the cash Treasury; it is labelled as a futures proxy. Yahoo `^IRX` is the 13-week bill and is not used as a 2Y stand-in.
- **A statistical edge.** Prior backtests of direction / levels did not show one after costs. The two new engines are unvalidated and must be tested separately out of sample (`preregistration_engines.md`). The brief always says so.
- **Broker-identical quotes and spreads.** DaryaGold is shown as Dukascopy bid + 0.3 (calibrated 2026-11-13 15:37 Tehran, uncertainty ±0.5). The brief prints both. Live broker spread may still differ.

## Limitations
- Dukascopy prices are **bid**, a liquidity-provider feed. DaryaGold display uses bid + 0.3 (uncertainty ±0.5); spreads may still differ. Tick volume, not real volume (VWAP is approximate).
- The Dukascopy endpoint is an unofficial public chart feed (no SLA). If it fails, the Yahoo `GC=F` fallback is futures (basis vs spot, can be several $), has no spread and is delayed ~10 min.
- `/workspace/data/gold_1m` (old shared feed) is stale since 2026-11-06 — not used.
- Level strengths and verdict thresholds are heuristics, not backtested, and are not shown in the brief. News windows are only as good as what M5-News enters; tier keywords can mis-tag an unusual label.
- Macro figures come from Yahoo Finance and FRED public pages (no API key). Yahoo may rate-limit; FRED series are **daily lagged**. The 10-minute cache (`data/macro.json`) is used so a brief run does not wait on a hung download. If every source fails and no cache is younger than 24 h, the brief prints «در دسترس نیست».
- `news_windows.py` no longer imports pandas (it used to import `m5lib`, which loads pandas/pyarrow). That import could stall for minutes when the interpreter or parquet stack was under contention, which is the likely cause of the old `bias` / `now` hangs (timeout 124).
- Deriv public WebSocket (frxXAUUSD) returned HTTP 520 from this box on 2026-11-12, so it is not used as a source.
