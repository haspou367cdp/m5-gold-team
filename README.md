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

## Telegram bot on GitHub Actions (free, no server)
`.github/workflows/telegram-bot.yml` runs `bot/bot.py` on a schedule (all times Tehran, Mon–Fri; GitHub cron can start a few minutes late):
- 11:15 pre-London brief; 11:30–21:30 a full check every 15 min (16:15 also sends the pre-New-York brief).
- 22:30, 23:30, 00:30: commands only. No runs at night or on weekends.

Each run: reads Telegram commands, refreshes the news calendar (ForexFactory weekly feed via `tools/ff_calendar.py`, every 3 h; USD events, Fed speakers = tier B, unclassified High impact = B), runs `tools/brief.py`, then an **automated risk check that replaces M5-Risk**: BUY/SELL from the brief, price data ≤10 min old and not the futures fallback, calendar ≤30 h old, outside A/B news windows, Friday rule (no entries from 23:30, flat by 01:30), daily stop (3 losses or 20% net loss from `/loss` `/win`), half/full unit only, risk ≤10% of equity incl. 14,000 toman fee, net R:R ≥ 1.5, SL ≥ $1. A signal is sent **only** if every gate passes, and the same signal is never sent twice.

Commands (answered at the next run, so up to ~15 min delay; only the owner's chat id is answered): `/scan`, `/brief`, `/balance <toman>`, `/loss <toman>`, `/win <toman>`, `/status`, `/help`.

Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (GitHub Actions secrets only, never in the repo). State (equity, Telegram offset, sent signals, today's results, news windows) lives in `state.json`/`news_windows.json` on the orphan branch `state` (one force-pushed commit, no secrets). Price parquet cache lives in the Actions cache. Budget: ~45 runs × ~22 weekdays ≈ 1,000 of the 2,000 free minutes per month.

Run manually: Actions → telegram-bot → Run workflow (`test` sends «سیستم راه‌اندازی شد» + the current verdict). Note: GitHub disables scheduled workflows after 60 days without repository activity; re-enable in the Actions tab if that happens.
