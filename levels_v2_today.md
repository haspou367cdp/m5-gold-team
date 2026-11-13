> **SUPERSEDED / historical snapshot (2026-11-13 07:45 Tehran).** Do not use for trading. The levels_v2 score FAILED its backtest; the strong/medium labels below are unvalidated and must not be read as edge. Current source of truth: `tools/brief.py` / `latest_brief.md`.

# XAUUSD key levels v2 (scored framework) — Fri 2026-11-13

> **UNVALIDATED — backtest pending; scores are a heuristic.** The earlier locked backtest (2020–2026) found levels and direction **no better than random**. This is analysis only, not financial advice and not a trade signal.

- **Generated:** 2026-11-13 07:45 Tehran, by M5-Levels using `/workspace/team/m5-levels/levels_v2.py`. The raw output is in `levels_v2_raw.json`. No toolkit files were changed.
- **Data:** Dukascopy freeserv spot XAU/USD 1-minute **bid**, fetched with `fetch_xauusd.py` (16 days of bars, from 2026-10-28). Prices are about $1 off the broker.
- **Last candle:** the bar opened at 07:41 Tehran and closed at **07:42 Tehran**. The data was 1.3 minutes old and not stale.
- **Price:** **3915.22 bid** / 3915.77 ask.
- **Volatility:** ATR(14) is 3.82 on M5 and 15.66 on H1.
- **Trading day:** today's trading day opened at 02:30 Tehran, and the Asia session (03:30–10:30) is still in progress.
- **Reference periods:**
  - Prior day (PD) is Thursday 2026-11-12: H 4000.33, L 3852.35, C 3876.50.
  - Prior week (PW) is 2026-11-02 to 11-06: H 4146.78, L 3869.05.

## Direction (swing structure)

- **Daily: bearish break of structure.**
  - Earlier daily swings were bullish: highs 4146.78 (11-05) and 4148.58 (11-09), and higher lows 3869.05 (11-02) and 4027.18 (11-06).
  - The 11-10, 11-11 and 11-12 candles then broke the 4027.18 higher low. Thursday closed at 3876.50, well below it, and its low of 3852.35 went under the prior-week low of 3869.05.
  - So the up-structure is broken, and no new daily higher low has formed yet.
- **4H: bearish (lower highs and lower lows).**
  - Lower highs: 4148.58 (11-09 22:30) then 4066.79 (11-11 10:30).
  - Lower lows: 4013.36 (11-10 18:30) then 3852.35 (11-12 18:30).
  - Price is now bouncing inside the down-leg: today's range so far is 3874.90–3923.00.

## Scoring (1 point each, 0–5)

1. **Structure:** the zone is an H1 swing (3 bars on each side, last 7 days) or an H4 swing (2 bars on each side).
2. **Liquidity:** PDH, PDL, PWH or PWL, or equal highs or lows from H1 swings, lie within $2.
3. **Volume profile:** the zone is within $2 of a POC, VAH or VAL. These come from a **tick-volume proxy**: Dukascopy tick volume, $1 bins, 70% value area. They are not real exchange volume.
   - Thursday: POC 3880.5, VAH 3974.0, VAL 3852.0.
   - Prior week: POC 4064.5, VAH 4147.0, VAL 3944.0.
4. **Tested:** in the last 3 days during London or New York hours, an M5 bar touched within $1 and price then moved at least 1×ATR(M5) away within 30 minutes.
5. **Displacement:** within 3 hours of the level forming, an M15 candle with range above 1.5×ATR left it, or an M15 close broke the prior M15 swing.

Candidates within $1.5 of each other are merged (chain merge, zone at most $6 wide). VWAP is anchored at 02:30 Tehran on tick volume: today 3901.42, Thursday 3927.52.

## Resistances above 3915.22

| # | Level / zone | Score | Sources and reasons |
|---|---|---|---|
| R1 | **3917.22** | **2/5** | Thursday's NY high. ④ Tested: rejected on 2026-11-12 at 16:55. ⑤ Displacement: a large M15 candle at 17:15 broke the 3924.30 swing. No ①, ②, ③. |
| R2 | **3922.99–3924.30** | **1/5** | Today's Asia high so far (3923.00) and the H1 swing low of 11-12 12:30 (3924.30), now a broken low acting as resistance. ① Structure only. Thursday's VWAP at 3927.52 sits just above and scores 1/5 (tested once). |
| R3 | **3944.0** | **2/5** | Prior-week VAL (tick-volume proxy). ③ Volume profile. ④ Tested: reacted on 11-12 at 15:25. |
| R4 | **3968.55–3974.0** area | **3/5** (core 3970.07–3972.16) | The core holds the H4 swing highs of 11-02 and 11-03 and Thursday's London high (3972.16). It scores ① structure, ④ tested (London 11-12 10:30) and ⑤ displacement. The neighbours are 3968.55, the H1 swing low of 11-12 03:30 (2/5), and Thursday's VAH at 3974.0 (1/5). |

Also above: 3962.24 (Thursday's Asia low, 2/5), and then PDH/Asia-H 4000.33 further up.

## Supports below 3915.22

| # | Level / zone | Score | Sources and reasons |
|---|---|---|---|
| S1 | **3904.99** | **2/5** | Thursday's London low. ④ Tested (11-12 16:55) and ⑤ displacement (M15 at 17:30). Today's VWAP 3901.42 (1/5) and the H4 swing low 3895.28 (1/5) are just below. |
| S2 | **3887.45** | **2/5** | H1 swing high of 11-12 21:30, a former high now acting as support. ① Structure and ④ tested (11-12 17:30). |
| S3 | **3878.91–3880.5** | **3/5** | Today's Asia low (in progress) and Thursday's POC at 3880.5 (tick-volume proxy). ③ Volume profile, ④ tested 2–3 times on Thursday's NY (last 22:45–22:50), and ⑤ displacement (M15 at 04:30 today broke 3880.34). |
| S4 | **3869.05–3872.05** | **4/5** (PWL 3869.05) | The PWL and H4 swing low of 11-02 score ①②④⑤. Next to it, the H1 swing low of 11-13 00:30 at 3872.05 scores 3/5 (①④⑤, tested 3 times). |

Also below: **3852.0–3852.35, at 4/5** (PDL, Thursday's NY low and H1/H4 swing low, Thursday's VAL). It scores ①②③④ and is 63 points under price.

## Toolkit `data/levels.json` for comparison (as_of 07:33 Tehran, its own heuristic)

- **Resistances:** 3923.0 medium, 3924.3 strong, 3955.43 medium, 3968.88 strong.
- **Supports:** 3916.75 strong (it calls 3917 support because price was just above it at 07:33), 3904.51 strong, 3900.83 medium, 3887.18 strong, 3884.34 strong, 3880.5 medium, 3878.91 medium, 3875.15 strong, 3871.93 strong.
- **How v2 differs:** v2 has no M15 swings and no round numbers, so the toolkit's 3955.43 does not appear here.

## Caveats

- These scores are untested. Their weights are equal by design, and per the team rule, no level should be described as "strong" or "reliable".
- Volume is Dukascopy tick volume, so the POC/VAH/VAL figures and VWAP are proxies.
- Point ④ ("tested") can credit a touch from either side of the level.
- Point ⑤ for the PWL uses its 11-02 origin.
- Today's Asia high and low are still forming.
