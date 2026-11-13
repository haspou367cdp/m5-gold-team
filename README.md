Research toolkit, signal-only, unvalidated, no statistical edge. Not financial advice. Nothing here places trades.

# M5 Gold Scalp (XAUUSD, M5) — DaryaGold

Owner: pouhasaa (Asia/Tehran). Broker: **DaryaGold** (Iranian counterparty platform). Equity and all sizing are in **toman**, never USD lots.
Full tool documentation: [`tools/README.md`](tools/README.md). Broker contract and risk floors: [`tools/broker_daryagold.json`](tools/broker_daryagold.json) (single source of truth).

## One command
```bash
python3 tools/brief.py             # fetch price + macro, levels, bias, regime, Persian brief (~7 s)
python3 tools/brief.py --no-fetch  # cached data (<1 s)
python3 tools/brief.py --equity 2085600
```

## Current rules (owner decisions 2026-11-13)
- Sizes: half unit 40,000 toman per $1 (margin 500,000) or full unit 80,000 toman per $1 (margin 1,000,000). Fee 14,000 toman per trade for both the half unit and the full unit (confirmed by the owner, 2026-11-13). Spread ~$0.25; limit/order entries and SL/TP fills carry no spread.
- Risk (owner's maximum-risk choice): max 10% of equity per trade incl. costs; daily stop 20% or 3 losses; 1 position incl. pending orders; net R:R ≥ 1.5; SL ≥ $1 and ≥ $0.5 beyond structure; 60 s minimum hold for manual/TP close; liquidation at 80% loss of the whole portfolio.
- News: one definition in `tools/news_windows.py` (`effective_doc`). Effective window = stored window ∪ floors (A: 15 before / 30 after; B: 10 before / 15 after). Tier A and B: no entries inside the window; be flat before it starts. Tier C: monitor only.
- Hours: forex hours (closed Sat/Sun, DST-aware). Weekday overnight holds allowed. Friday only: no new entries from 23:30 Tehran, everything closed before 01:30 Tehran (17:00 New York). The old 22:30/00:30 nightly rule is cancelled.
- Prices are shown as DaryaGold ≈ Dukascopy bid + $0.3 (±0.5).
- Both v2 engines (trend continuation, liquidity sweep) **failed** their out-of-sample test (−0.35R / −0.45R). Levels are locations only, never "strong". Demo first.

## Not in this repo
`journal.csv`, `data/` (parquet caches, news calendar), backups (`bak_*`), logs, `.env`/secrets are git-ignored and stay on the box.
