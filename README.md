Research toolkit and Telegram decision aid. No backtested edge. Nothing here places trades.

# Xauscalper — M5 gold assistant for DaryaGold (XAUUSD)

**Start here: [HANDOFF.md](HANDOFF.md)** — goal, history and decisions, architecture, commands, cost model, price bases,
research results, what is deployed and what is pending, security rules, and how to test and deploy.

## What it is
- A Persian Telegram bot (Supabase Edge Function `tg-bot` + GitHub Actions) that answers on request with levels, trend
  and ready-made setups in DaryaGold prices, written in plain Persian for beginners. Alerts (level touch within $1,
  trend change, volatility, US news) go to the owner only.
- No automatic trade signals since 2026-11-20 (no edge in backtests), no order execution, no broker login.
- A TradingView indicator, **Xauscalper Map** (branch `tv-decision-map`), shows the same levels, trend and setups on a
  phone chart (free TradingView plan).

## Commands
| Where | Commands |
|---|---|
| Owner chat | `/setup` `/e` `/trend` `/levels` `/brief` `/status` `/balance` `/offset` `/calibrate` `/groupoff` `/groupon` `/help` |
| BAROBAX group | `/setup` `/trend` `/levels` `/brief` (no toman, no balance) |
| Hidden aliases | `/signal`, `/scan` → `/setup`; `/start` → `/help` |

## Layout
| Path | What |
|---|---|
| `supabase/functions/tg-bot/` | Edge Function: Telegram webhook, 2-minute alert tick, `/setup` `/e` `/trend` `/levels` (live price) |
| `bot/bot.py` | GitHub Actions job: levels snapshot, `/brief`, briefs at 07:00 / 11:15 / 16:15, news calendar |
| `tools/` | levels (`level_view.py`), news windows, broker model (`broker_daryagold.json`), brief — see [`tools/README.md`](tools/README.md) |
| `backtest/` | research and backtests (`backtest/phase4/REPORT.md`) |
| `tests/`, `bot/test_bot.py`, `supabase/functions/tg-bot/test*.mjs` | offline tests |
| `.github/workflows/telegram-bot.yml` | the Python job (runs from `main`) |

## Cost model (owner-confirmed)
1 unit = 80,000 toman per $1, 0.5 unit = 40,000; fee 14,000 toman once per trade; spread ~$0.25; margins
1,000,000 / 500,000. Prices: levels = bid + 0.30, live DaryaGold price = mid + 0.02 (unification pending).

## Tests
```bash
cd supabase/functions/tg-bot && node test.mjs && node test_assist.mjs
STATE_DIR=$(mktemp -d) python3 bot/test_bot.py
python3 -m pytest -q tests
```

## Research toolkit
```bash
python3 tools/brief.py             # fetch price + macro, levels, bias, regime, Persian brief
python3 tools/brief.py --no-fetch  # cached data
```

## Not in this repo
`journal.csv`, `data/` (parquet caches, news calendar), backups, logs and secrets are git-ignored. Secrets live in
Supabase Vault and GitHub secrets only.
