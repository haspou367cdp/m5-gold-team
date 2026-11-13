Research toolkit, signal-only, unvalidated, no statistical edge. Not financial advice.

# M5 Gold Scalp toolkit (XAUUSD, M5) — `/workspace/m5-gold-team/tools/`

The owner (pouhasaa, $500 account, Asia/Tehran) uses this brief for a live layered read of XAUUSD.
`brief.py` prints: **(1) BUY / SELL / NO TRADE with accept/reject reasons, (2) regime + allowed engine, (3) direction (H4, H1, M15), (4) ADR and reference highs/lows (day, week, month, sessions, opening ranges), (5) macro (DXY / 2Y / 10Y / real yield / 5Y–10Y breakevens), (6) hard risk gates, (7) nearby highs/lows without strength labels.**
Trade setups with entry/SL/TP are **not** auto-printed here; they go through M5-Risk separately when asked. The two engines in `regime.py` are **unvalidated detectors** only (see `preregistration_engines.md`).
Signal-only research, not financial advice, nothing here places trades.

## One command
```bash
python3 /workspace/m5-gold-team/tools/brief.py            # fetch price + macro (in parallel) + levels + bias + regime + Persian brief (target < 60 s)
python3 /workspace/m5-gold-team/tools/brief.py --no-fetch # reuse cached price + macro (fast)
```
Outputs: stdout (Persian markdown), `/workspace/m5-gold-team/latest_brief.md`, `/workspace/m5-gold-team/latest_brief.json`.
Exit codes: 0 ok · 2 data stale or data-quality gate failed (brief says **NO TRADE** / stop, do not publish prices) · 3 no data source worked.

## Tools
| File | What it does | Inputs | Outputs | Used by |
|---|---|---|---|---|
| `fetch_xauusd.py [--days 10] [--max-age 15] [--source auto\|dukascopy\|yahoo]` | Pulls XAU/USD 1m **bid + ask** from the Dukascopy public chart feed, resamples to M5/M15/H1/**H4** (bid OHLC, ask close, spread, tick volume). **Merges** with any older cached bars (capped at 40 calendar days) so a short incremental fetch does not wipe history needed for ADR(14). Fails loudly (exit 2, `stale: true`) if the last bar closed > `--max-age` min ago while the market is open (`brief.py` passes `--max-age 10`). Fallback: Yahoo `GC=F` (COMEX **futures**, no bid/ask, may be ~10 min delayed) — labelled `FALLBACK` everywhere. | internet | `data/xauusd_{1m,m5,m15,h1,h4}.parquet`, `data/meta.json` | everyone (`brief.py` calls it with `--days 3` when the cache already spans 21 days, otherwise `--days 21`) |
| `levels.py [--print] [--range 60]` | Previous trading-day H/L, previous **calendar-month** H/L (NY month; flagged incomplete if the cache starts late) + month-to-date, older daily H/L (5 days), today's Asia/London/NY H/L + yesterday's NY, **opening range** (first 30 min of London and NY), **equal highs/lows on M15**, $5/$10 rounds, trading-day and **session VWAPs** (tick-volume proxy) ±1σ on the day VWAP, EMA20/50 on M5/M15/H1/**H4**, ATR(14) M5/H1/H4, fractal swings M5/M15/H1/H4. Clusters nearby candidates and stores ranks in JSON only. `--print` shows score, not قوی/متوسط/ضعیف. | cache | `data/levels.json` | M5-Levels (main), M5-Signal |
| `bias.py [--at "YYYY-MM-DD HH:MM"]` | **H4** (required) + H1 + M15 trend (EMA order, EMA20 slope, swing structure); M5 is context only; D1 is not used for direction. Combines with M5-News bias. News windows are tier-aware (A blocks, B is caution + spread check, C is monitor). "Now" verdict + invalidation levels. | cache, `levels.json`, `news_windows.json` | `data/bias.json` | M5-Signal (main), M5-Risk |
| `news_windows.py seed\|add\|event\|bias\|list\|now\|prune` | No-trade windows (Tehran time), M5-News bias, and **A/B/C tiers**. `event` defaults follow `window_policy` in `data/news_windows.json`: US A-data 15/15, FOMC statement 30/90 (30 before the statement to 60 after a presser starting ~30 min later), FOMC presser-only 30/60, Fed Chair speech 15/30, B data/minutes 15/15, B Fed speech 15/30, C 5/15. Stored `tier`/`fomc`/start/end are never overwritten. `now` exits 1 only on an active **tier-A hard block** (or the last 5 min before a stored A window) — not for B/C, and not for FOMC minutes (B, fomc=false). **stdlib only** (no pandas). | `/workspace/team/m5-news/latest.md` (seed) or CLI | `data/news_windows.json` | M5-News (writes), M5-Risk / bias.py (reads) |
| `macro.py [--no-fetch] [--ttl 600]` | DXY (Yahoo `DX-Y.NYB`, fallback `DX=F` then EURUSD proxy), US 10Y nominal (Yahoo `^TNX`, fallback FRED DGS10 lagged), **US 2Y** (Yahoo `2YY=F` 2-Year Yield Futures, *not* the cash 2Y; official cash is FRED DGS2 lagged — `^IRX` is the 13-week bill and is not used), 10Y real yield (FRED DFII10, lagged), **5Y/10Y inflation breakevens** (FRED T5YIE / T10YIE, lagged). 10-minute cache, 6 s HTTP timeout, 10 s overall budget. | internet or `data/macro.json` | `data/macro.json` | `brief.py` (parallel with the price fetch) |
| `regime.py` | 4-state regime gate: **trend** → continuation engine allowed; **range** → sweep/mean-reversion engine allowed; **volatility_expansion** (M5 ATR percentile, relative tick volume) → wait; **news_abnormal** (tier-A window or spread anomaly) → no trade. Optional ADX(14) on H1/M15 and session-VWAP deviation (tick-volume proxy). Two setup detectors, flagged unvalidated. | `levels.json`, bars, news/spread | used in-process by `brief.py` | `brief.py` |
| `brief.py` | Runs fetch + macro (parallel), levels, bias, regime, engines, and the Persian brief. **Data-quality gate:** missing data or last bar older than 10 minutes while the market is open → **NO TRADE / stop**, no full analysis. **Does not print قوی/متوسط/ضعیف.** Always prints hard risk gates and the unvalidated-levels line. | — | `latest_brief.md`, `latest_brief.json` | Boti (posts to owner), all bots |
| `preregistration_engines.md` | Pre-registration stub for the two engines' separate out-of-sample backtests. No results are claimed. | — | — | research, later backtests |
| `m5lib.py` | Shared paths, Tehran formatting, market hours, session clock, H4 fallback resample, NY month bounds. | — | — | imported |

### Sessions / clock (DST-correct via `zoneinfo`; values below are for US/UK winter time)
- Gold trading day: 18:00→17:00 New York = **02:30 → 01:30 Tehran**. Daily break 01:30–02:30 Tehran; weekend Fri 01:30 Tehran (Sat) → Mon 02:30 Tehran.
- Asia 00:00 UTC→07:00 London = **03:30–10:30 Tehran** · London 07:00 London→08:30 NY = **10:30–17:00 Tehran** · New York 08:30→17:00 NY = **17:00–01:30 Tehran**.
- Opening range = first **30 minutes** of London (10:30–11:00 Tehran in winter) and of New York (17:00–17:30 Tehran in winter).
- US 08:30 ET data = **17:00 Tehran** in winter.

### Regime gate and engines (heuristics, NOT backtested)
1. **news_abnormal** — inside a tier-A block window (or within the A/FOMC pre-buffer), or spread > 2× typical for that hour **and** > $0.80 → no trade. Tier B is caution + the same spread check, not an automatic block. Tier C is monitor only.
2. **volatility_expansion** — M5 ATR(14) at or above the 90th percentile of the last ~200 bars, or at/above the 80th with a rising ATR or relative tick volume ≥ 1.8× → wait.
3. **trend** — directional H4 (or H4+H1) with optional ADX(14) H1 ≥ 25 as confirmation, and the session range not tight → **continuation** engine may fire.
4. **range** — otherwise (tight session range vs H1 ATR, mixed structure, or low ADX) → **sweep / mean-reversion** engine may fire.

Engines are detectors only. They are flagged unvalidated in the brief. See `preregistration_engines.md`. VWAP and relative volume use **tick volume**, labelled as a tick-volume proxy, not exchange volume.

### Level ranking (heuristic, NOT backtested)
Candidates within `max($0.5, 0.25×ATR_M5)` are merged. Score = sum of source weights (H4/H1 swing / PDH / PDL / previous-month H/L 3, London/NY H/L 2.5, equal M15 H/L 2.5, older daily H/L 2.5, Asia H/L and opening ranges 2, M15 swing 2, VWAP / session VWAP 1.2–1.5, H4 EMA 2, H1 EMA 1.5, $100 round 2.5, …) + 0.5 per distinct M15 reaction in the last 3 days (max +2). Ranks (`strong ≥ 6`, `medium ≥ 3.5`) stay in JSON only. The brief still *selects* medium/strong candidates (so isolated weak $5/$10 rounds are not dumped) but **does not print** قوی/متوسط/ضعیف — those ranks are unvalidated and must not be treated as edge. A resistance built from old lows is shown as "کف شکسته‌شده (حالا مقاومت)". `levels.py` also writes `structure` (week, previous week, previous month, month-to-date, ADR-14, % used, D1 structure for levels only), `opening_ranges`, `equal`, and `session_vwap`.

### "Now" verdict rules (bias.py), first match wins
1. data stale / market closed → no opinion · 2. inside a **tier-A block** window → wait until it ends · 3. a stored tier-A window starts within 5 min → wait (the stored start already includes the official lead-in; FOMC minutes are B and do not block)
4. spread > 2× typical for that hour and > $0.8 → wait · 5. bias neutral (H4/H1/M15 disagree or technical ≠ M5-News) → wait for range edges
6. price within **0.3×ATR_M5** of a medium/strong level **in the bias direction** → `near_level` ("only with an M5 rejection candle")
7. sitting on a high-score level against the bias → wait · 8. otherwise mid-range → "wait for X".
The brief's **BUY / SELL / NO TRADE** is the regime+engine decision on top of this; a `near_level` verdict alone is not enough to print BUY/SELL.
Invalidation: bearish → M15 close above nearest high-score resistance = neutral; H1 close above last H1 swing high = bias off (mirrored for bullish).

### Hard risk gates (printed every analysis; not changed to 0.5%)
On a $500 account with 0.01 lot (≈ $1 per $1 of move):
- spread limit: > 2× typical for that hour **and** > $0.80 → no entry
- stop-loss ≤ **$5** at 0.01 lot
- reward:risk ≥ **1.5**
- stop the day after **3 losses** or **$10** lost

These stay the current M5-Risk rules. A 0.25–0.5% risk cap would be $1.25–$2.50, which is tighter than a typical M5 ATR and would mostly be stopped out by noise.

### News tiers
Auto-classification is only used for *new* `event`/`add` rows. If a window already has `tier` and/or `fomc` set (M5-News hand-set the current 37 windows at 12:59 Tehran on 2026-11-13), those fields and the stored start/end are **never overwritten**.

| Tier | Events (classifier) | Brief / `now` behaviour | Default `event` buffer |
|---|---|---|---|
| A | **US** CPI (country + event; UK/other CPI is not A), NFP, Core PCE / PCE; FOMC *decision/statement/presser* (`fomc=true`); Fed Chair speeches (`fomc=false`) | hard block | A data **15 / 15**; FOMC statement **30 / 90** (30 before the statement, 60 after a presser that starts ~30 min later); FOMC presser-only **30 / 60**; Chair speech **15 / 30** |
| B | **FOMC minutes** (`fomc=false` — not a hard block); PPI, ISM, Retail Sales, GDP; named non-US CPI; other Fed speeches (governors, vice chairs, presidents) | caution + spread check (not an automatic block) | B data / minutes **15 / 15**; B speech / Q&A **15 / 30** |
| C | everything else (claims, ceremonial remarks, …) | monitor only | 5 / 15 (calendar only) |

A bare label of just "CPI" or a lone "FOMC" without minutes/decision is **not** auto-upgraded to A. M5-News can still set the tier by hand.

## How each bot uses it
- **M5-News**: after each brief, `python3 news_windows.py seed` (reads `/workspace/team/m5-news/latest.md`; keep the `- HH:MM-HH:MM | label` format under `today_YYYY-MM-DD:` / `tomorrow_YYYY-MM-DD:`, add `(Fri)` for after-midnight events) and `python3 news_windows.py bias --bias bearish --why "..." --invalidation "..."`. Single event: `news_windows.py event --date 2026-11-13 --time 17:00 --label "US PPI"` (tier B, caution, 15/15). For a rate decision use a label such as `FOMC rate decision` (`--time` = statement time) so the 30/90 FOMC buffer applies. `FOMC minutes` is tier B, `fomc=false`, and does not hard-block.
- **M5-Levels**: `python3 fetch_xauusd.py && python3 levels.py --print`; full numbers in `data/levels.json`.
- **M5-Signal**: `python3 brief.py` → report decision / direction / now-or-wait / levels only (no entry/SL/TP unless the owner asks).
- **M5-Risk**: `python3 news_windows.py now` (exit 1 = **tier-A block** only) and `jq .spread data/bias.json`; warn on stale data (`meta.json` `stale: true` or age > 10 min in session) or abnormal spread. Keep the $5 / 1.5 R:R / 3-loss or $10 daily stop rules.
- **M5-Journal**: log `latest_brief.json` (as_of, bias, decision, regime, levels) to `session_log.csv`; later check whether bias/levels/engines held.
- **Boti**: `python3 brief.py` and post the stdout to the owner.

## What was intentionally not built (no real data, or would be fabricated)
- **GC order flow**: delta, footprint, absorption, DOM, heatmap. No live or historical series is available here. A paid feed such as Databento would be needed; until then this layer stays out, not filled with invented numbers.
- **Exchange / real volume** and a real volume-profile (POC / VAH / VAL). Tick volume is a proxy only and is labelled as such on every VWAP and relative-volume line.
- **Live official cash 2Y** and **live real yield / breakevens**. FRED DGS2, DFII10, T5YIE and T10YIE are **daily and lagged**. Yahoo `2YY=F` is **2-Year Yield Futures**, not the cash Treasury; it is labelled as a futures proxy. Yahoo `^IRX` is the 13-week bill and is not used as a 2Y stand-in.
- **A complete previous-month high/low** when the 1m cache does not cover the whole month (the cache currently starts around 2026-10-23, so October 2026 is flagged incomplete).
- **A statistical edge.** Prior backtests of direction / levels did not show one after costs. The two new engines are unvalidated and must be tested separately out of sample (`preregistration_engines.md`). The brief always says so.
- **Broker-identical quotes and spreads.** Dukascopy bid can differ from the broker by about $1.

## Limitations
- Dukascopy prices are **bid**, a liquidity-provider feed; broker quotes differ by ~$1 and spreads differ. Tick volume, not real volume (VWAP is approximate).
- The Dukascopy endpoint is an unofficial public chart feed (no SLA). If it fails, the Yahoo `GC=F` fallback is futures (basis vs spot, can be several $), has no spread and is delayed ~10 min.
- `/workspace/data/gold_1m` (old shared feed) is stale since 2026-11-06 — not used.
- Level strengths and verdict thresholds are heuristics, not backtested, and are not shown in the brief. News windows are only as good as what M5-News enters; tier keywords can mis-tag an unusual label.
- Macro figures come from Yahoo Finance and FRED public pages (no API key). Yahoo may rate-limit; FRED series are **daily lagged**. The 10-minute cache (`data/macro.json`) is used so a brief run does not wait on a hung download. If every source fails and no cache is younger than 24 h, the brief prints «در دسترس نیست».
- `news_windows.py` no longer imports pandas (it used to import `m5lib`, which loads pandas/pyarrow). That import could stall for minutes when the interpreter or parquet stack was under contention, which is the likely cause of the old `bias` / `now` hangs (timeout 124).
- Deriv public WebSocket (frxXAUUSD) returned HTTP 520 from this box on 2026-11-12, so it is not used as a source.
