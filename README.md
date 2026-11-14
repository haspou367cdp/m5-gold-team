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
  - Edge Function `tg-bot` (`supabase/functions/tg-bot/`) is the Telegram **webhook**: `/status /help /start /balance /loss /win /trade /undo /shadow /offset` are answered instantly; `/levels` reads the shared stored snapshot (or queues a run if it is stale); on the weekend (Friday after the close, Saturday, Sunday before the open) `/scan` and `/brief` get one line «🔒 بازار بسته است؛ بازگشایی دوشنبه ۰۱:۳۰» and nothing is dispatched; `/levels` on the weekend serves the last stored snapshot (with its age) or that same closed line, with no dispatch. When the market is open, a `/levels` snapshot newer than 15 minutes is answered instantly from `bot_state`; otherwise `/scan`, `/brief` and a stale `/levels` get «در حال بررسی…» and the function dispatches the GitHub workflow (answer in ~1 min). Only the owner's private chat (45639251) may issue commands; Telegram's `secret_token` header is checked. Signals, the 11:15 and 16:15 pre-session briefs, and the final replies to `/levels`, `/scan`, `/brief` and `/shadow` are also posted to the BAROBAX group (`channel_id` in `bot_state`). The owner's balance and daily loss cap are stripped from `/brief` and pre-session cards, toman P&L is stripped from `/shadow`, and the signal card's «ریسک … تومان» line is stripped (unit size, direction, entry, SL and TP stay), before the group copy is sent. Queue acks («در حال بررسی»), errors, `/status`, `/trade`, `/balance`, the Friday reminder and other personal replies stay private. Group messages and commands, including the owner's, are ignored. A failed group post never blocks the owner's message.
  - Postgres table `public.bot_state` (one row, jsonb) is the **single source of truth** for state (equity, today's results, queued commands, sent signals, briefs sent, news calendar). RLS on, no policies: only the service role (inside the function) can read/write. Writes from Telegram use optimistic versioning; the GitHub run merges only its own keys (`bot_merge`).
  - Secrets live in **Supabase Vault** (`telegram_bot_token`, `gh_dispatch_token`, `tg_webhook_secret`), readable only by the service role.
  - **pg_cron + pg_net** dispatch the workflow on the Tehran schedule (UTC crons `45 7 * * 1-5`, `*/15 8-17 * * 1-5`, `0 18 * * 1-5` = 11:15, 11:30–21:15 every 15 min, 21:30 Tehran, Mon–Fri; `*/30 0-7 * * 1-5` = 03:30–11:00 Tehran every 30 min, Asia shadow log only, never sends; `0 20 * * 5` = Friday 23:30 Tehran close reminder).
- **GitHub Actions** (`.github/workflows/telegram-bot.yml`) runs the analysis (`bot/bot.py` → `tools/brief.py` + automated risk check). It pulls/pushes state from the Edge Function using a GitHub **OIDC token** (no shared secret; only this repo's `main` branch is accepted). No Telegram polling.
- The GitHub `schedule:` stays as a fallback only; repo variable `SUPABASE_CRON=1` skips it at job level (no minutes).

Each run: answers queued `/scan` `/brief` `/levels`, refreshes the news calendar (ForexFactory weekly feed via `tools/ff_calendar.py`, every 3 h; USD events, Fed speakers = tier B, unclassified High impact = B), runs `tools/brief.py`, then an **automated risk check that replaces M5-Risk**: BUY/SELL from the brief, price data ≤10 min old and not the futures fallback, calendar ≤30 h old, outside A/B news windows, Friday rule (no entries from 23:30, flat by 01:30), daily stop (3 losses or 20% net loss from `/loss` `/win`), half/full unit only, risk ≤10% of equity incl. 14,000 toman fee, net R:R ≥ 1.5, SL ≥ $1. Max 1 position: after a signal, no new signal for 60 min unless `/loss` or `/win` records that the trade closed. A signal is sent **only** if every gate passes, and the same signal is never sent twice. Scheduled checks are silent otherwise; the NO TRADE card is sent only for `/scan` or `/brief`. Pre-session briefs (London ~11:15, New York ~16:15) are sent once per day, even if a run starts up to ~50 min late. If brief.py or Dukascopy fails, or the calendar is older than 30 h, no signal is sent. Signals have a single target (DaryaGold cannot partially close); entry, SL and TP are in Latin digits (e.g. `3884.2`) for tap-to-copy, the rest uses Persian digits.

### /brief, /scan, /trade, /shadow (2026-11-13)
- `/brief` = market summary (never a signal): DaryaGold price, trend, **day high/low** from 1-minute candles of the forex day (from 17:00 New York = 00:00 server = 01:30 Tehran in US winter, 00:30 in summer), nearest resistance/support (a level closer than max(0.3×ATR M5, $1) to price is skipped), all of today's remaining news windows, balance and today's loss cap. Pre-session briefs use the same card.
- `/scan` = risk check only: the signal card, or a 3-line «فعلاً معامله نه» card (reason + price).
- `/trade <buy|sell> <entry> <exit> <1|0.5>` (Persian digits/words accepted, e.g. `/trade فروش ۳۹۱۴٫۰۷ ۳۹۰۹٫۶۱ ۱`): gross = (exit − entry) × direction × 80,000 (1 unit) or 40,000 (0.5), net = gross − 14,000. Equity += net; the day ledger gets one win or loss record (net < 0 = loss), so do **not** also send `/loss`/`/win` for the same trade. Daily stop = 3 losses or net loss ≥ 20% of the day's **starting** equity (`day.start_equity`, set at the first command of the Tehran day, or by `/balance` before anything is recorded). `/undo` reverses the last record; for a trade it also restores equity (equity − net) and removes it from `state.trades`.
  Trades are stored in `bot_state.state.trades` (last 300). `journal.csv` stays on the box only (git-ignored): `python3 tools/sync_trades.py state.json` appends any new `/trade` rows (idempotent by `signal_id`).
- Shadow log (silent, research only): on scheduled runs, if entries were blocked by a gate (news A/B window or soon, volatility spike, abnormal spread, Friday/session) the setup is recomputed with the gates off (`tools/shadow.py`, `ignore_gates=True`; live gates unchanged). If that setup passes every non-gate check (sizing, R:R ≥ 1.5, SL ≥ $1, daily stop, 1-position lock) it is stored in `bot_state.state.shadow` (last 300; one open at a time). Later runs resolve it from 1-minute bid bars: limit fill within 30 min (else `unfilled`), then TP / SL (same bar = SL) or `expired` at market after 4 h or at the Friday close. Result in R and in toman for one full unit (80,000/$, 14,000 fee). `/shadow` shows the totals and the last 3.

### Weekend, Friday close, Asia, /offset (2026-11-14)
- Friday: no new entries from 23:30 Tehran (DST-aware session gate in `brief.py`, unchanged). The Friday 23:30 run sends one reminder «🏳️ جمعه: ورود جدید بسته است / همه‌ی معامله‌ها و سفارش‌ها را تا ۰۱:۳۰ ببندید» (once, `friday_reminder_sent`) and does no analysis.
- Weekend: Edge Function and `bot.py` answer `/scan` `/brief` with the closed line; `/levels` serves the last stored snapshot (with its age) or that closed line (reopen = Sunday 17:00 New York from `broker_daryagold.json`, exactly like forex: Monday 01:30 Tehran in winter, 00:30 in summer). Scheduled runs need `forex_open`, so they send nothing on the weekend. `GET /health` shows `market_closed` and the line (read-only, no Telegram).
- Asia (weekdays 03:30–11:15 Tehran): scheduled runs are **log-only**. A setup that passes every live check is stored as a shadow entry (`gates: ["asia"]`), a gate-blocked one as usual; both get `session: "asia"`. Nothing is sent; `/scan` on request still answers. `/shadow` has an «آسیا» line.
- `/trade` sanity check: one warning line (trade still recorded, `warned: true`) when exit = entry, the move is over $40, or entry/exit is more than $50 from the last analysed DaryaGold price (`last_price`, if under 24 h old).
- `/offset` shows the DaryaGold offset; `/offset 0.4` sets `bot_state.state.dg_offset` (−5…5, Persian digits ok; owner chat only). The next run applies it (`bot.py` → `p1()`, and `brief.py` via env `DG_OFFSET_USD`); default 0.3 from `broker_daryagold.json`. GitHub can never overwrite it.

Amounts accept Persian or Latin digits, separators and «تومان» (e.g. `/loss ۱۵۰٬۰۰۰`); invalid or non-positive amounts are rejected and nothing is recorded.

Secrets: GitHub secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GH_DISPATCH_TOKEN`; the setup run copies the two tokens into Supabase Vault. Nothing secret is in the repo.

Workflow modes (Actions → telegram-bot → Run workflow): `scheduled`, `command` (queued /scan /brief /levels only), `test` (one sample signal labelled «نمونه»), `setup` (copy the two tokens into Vault and set the webhook; safe to re-run, e.g. after rotating a token), `unhook` (emergency: delete the webhook; commands then wait in Telegram until `setup` is run again).

If Supabase is down: GitHub runs fail visibly (red) and send nothing. To fall back to GitHub's own (less punctual) schedule, delete repo variable `SUPABASE_CRON`.

Tests (offline, mocked network; never touch journal.csv):
`node supabase/functions/tg-bot/test.mjs` and `STATE_DIR=$(mktemp -d) python3 bot/test_bot.py`.

Budget: Supabase free (Edge Function invocations ≪ 500k/month, DB ≪ 500 MB); GitHub ~41 + 16 (Asia) scheduled runs × 22 weekdays + 4 Friday reminders + /scan runs ≈ 1,300–1,500 of 2,000 free minutes (each ~30 s run bills 1 minute). Note: Supabase pauses free projects after 7 days without activity; the 15-min schedule keeps it active on weekdays.
