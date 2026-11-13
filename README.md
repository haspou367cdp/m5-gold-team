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

## Telegram bot (Supabase + GitHub Actions, free, no server)
Architecture (all free tiers, no card):
- **Supabase project `m5-gold-bot`** (eu-central-1):
  - Edge Function `tg-bot` (`supabase/functions/tg-bot/`) is the Telegram **webhook**: `/status /help /start /balance /loss /win /undo` are answered instantly; `/scan` and `/brief` get «در حال بررسی…» and the function dispatches the GitHub workflow (answer in ~1 min). Only chat 45639251 is answered and Telegram's `secret_token` header is checked.
  - Postgres table `public.bot_state` (one row, jsonb) is the **single source of truth** for state (equity, today's results, queued commands, sent signals, briefs sent, news calendar). RLS on, no policies: only the service role (inside the function) can read/write. Writes from Telegram use optimistic versioning; the GitHub run merges only its own keys (`bot_merge`).
  - Secrets live in **Supabase Vault** (`telegram_bot_token`, `gh_dispatch_token`, `tg_webhook_secret`), readable only by the service role.
  - **pg_cron + pg_net** dispatch the workflow on the Tehran schedule (UTC crons `45 7 * * 1-5`, `*/15 8-17 * * 1-5`, `0 18 * * 1-5` = 11:15, 11:30–21:15 every 15 min, 21:30 Tehran, Mon–Fri).
- **GitHub Actions** (`.github/workflows/telegram-bot.yml`) runs the analysis (`bot/bot.py` → `tools/brief.py` + automated risk check). It pulls/pushes state from the Edge Function using a GitHub **OIDC token** (no shared secret; only this repo's `main` branch is accepted). No Telegram polling.
- The GitHub `schedule:` stays as a fallback only; repo variable `SUPABASE_CRON=1` skips it at job level (no minutes).

Each run: answers queued `/scan` `/brief`, refreshes the news calendar (ForexFactory weekly feed via `tools/ff_calendar.py`, every 3 h; USD events, Fed speakers = tier B, unclassified High impact = B), runs `tools/brief.py`, then an **automated risk check that replaces M5-Risk**: BUY/SELL from the brief, price data ≤10 min old and not the futures fallback, calendar ≤30 h old, outside A/B news windows, Friday rule (no entries from 23:30, flat by 01:30), daily stop (3 losses or 20% net loss from `/loss` `/win`), half/full unit only, risk ≤10% of equity incl. 14,000 toman fee, net R:R ≥ 1.5, SL ≥ $1. Max 1 position: after a signal, no new signal for 60 min unless `/loss` or `/win` records that the trade closed. A signal is sent **only** if every gate passes, and the same signal is never sent twice. Scheduled checks are silent otherwise; the NO TRADE card is sent only for `/scan` or `/brief`. Pre-session briefs (London ~11:15, New York ~16:15) are sent once per day, even if a run starts up to ~50 min late. If brief.py or Dukascopy fails, or the calendar is older than 30 h, no signal is sent. Signals have a single target (DaryaGold cannot partially close); entry, SL and TP are in Latin digits (e.g. `3884.2`) for tap-to-copy, the rest uses Persian digits.

Amounts accept Persian or Latin digits, separators and «تومان» (e.g. `/loss ۱۵۰٬۰۰۰`); invalid or non-positive amounts are rejected and nothing is recorded.

Secrets: GitHub secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GH_DISPATCH_TOKEN`; the setup run copies the two tokens into Supabase Vault. Nothing secret is in the repo.

Workflow modes (Actions → telegram-bot → Run workflow): `scheduled`, `command` (queued /scan /brief only), `test` (one sample signal labelled «نمونه»), `setup` (copy the two tokens into Vault and set the webhook; safe to re-run, e.g. after rotating a token), `unhook` (emergency: delete the webhook; commands then wait in Telegram until `setup` is run again).

If Supabase is down: GitHub runs fail visibly (red) and send nothing. To fall back to GitHub's own (less punctual) schedule, delete repo variable `SUPABASE_CRON`.

Tests (offline, mocked network; never touch journal.csv):
`node supabase/functions/tg-bot/test.mjs` and `STATE_DIR=$(mktemp -d) python3 bot/test_bot.py`.

Budget: Supabase free (Edge Function invocations ≪ 500k/month, DB ≪ 500 MB); GitHub ~45 scheduled runs × 22 weekdays + /scan runs ≈ 1,000–1,200 of 2,000 free minutes. Note: Supabase pauses free projects after 7 days without activity; the 15-min schedule keeps it active on weekdays.
