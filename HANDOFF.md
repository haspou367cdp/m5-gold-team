# HANDOFF — Z A R V A •|• BTV (M5 gold assistant for DaryaGold; formerly Xauscalper)

Last updated 2026-11-21 (Tehran). Read this first if you are a developer or an AI agent picking the project up.
Owner: pouhasaa (Asia/Tehran). All dates below are Tehran dates.

## 1. Goal
A Persian Telegram assistant for scalping XAUUSD on **DaryaGold** (an Iranian counterparty platform: prices in USD,
P&L and fees in toman, no partial close; market opens **Monday 01:30 Tehran** (Sunday 17:00 New York), each session
01:30 → 00:30 next day (daily break 00:30–01:30), last close Saturday 00:30; no new setups Friday after 23:30).
Commands (`/setup` `/trend` `/levels` `/e` `/brief`) work whenever the market is open; the bot's automatic alerts and
briefs run only **07:00–00:30** (`session.alerts_from`, JS `alertWindow`, Python `DG.alert_window`).
It gives levels, trend, ready-made setups and plain-language alerts on request. It **never places orders**, never
logs in to DaryaGold, and since 2026-11-20 it sends **no automatic trade signals** (research showed no edge, see §6).
A TradingView indicator (ZARVA Map, formerly Xauscalper Map) shows the same levels, trend and setups on the phone chart.
The audience includes complete beginners in the Telegram group «⬩ Z A R V A ⬩» (formerly BAROBAX), so every message must be plain Persian.
Names (2026-11-21, owner t244u): bot «Z A R V A •|• BTV» (@Xauscalperibot), group «⬩ Z A R V A ⬩». IDs and the username are unchanged
(owner chat 45639251, group -1001958445009, username @Xauscalperibot). `lib.js` `BOT_NAME` / `GROUP_NAME` hold the display names.

## 2. History and decisions
| Date | What happened / decided |
|---|---|
| 2026-11-13 | Repo started: research toolkit (`tools/`), `brief.py`, levels, bias, news windows; first Telegram bot (GitHub Actions + Supabase). Fee 14,000 toman once per trade; 1 unit = 80,000 toman/$, 0.5 unit = 40,000. |
| 2026-11-13 | v2 engines (trend continuation, liquidity sweep) **failed** out-of-sample (−0.35R / −0.45R). Levels are locations only, never "strong". |
| 2026-11-14 | Shared levels snapshot; group mirroring to BAROBAX (minus personal money); /groupoff, /groupon; weekend closed line; Friday reminder. |
| 2026-11-20 | Phase 1–3: DaryaGold model, deterministic risk gate, 07:00–00:30 hours (corrected 2026-11-21: market 01:30–00:30, alerts from 07:00), signal IDs, journal tables, /calibrate. |
| 2026-11-20 | Phase 4 backtest of the live engines under the DaryaGold cost model: negative expectancy IS and OOS (§6). |
| 2026-11-20 | **Assistant redesign** (owner t226u–t232u): automatic signals and the journal switched off; new `/setup`, `/trend`, `/e` from a live DaryaGold price; alerts tick every 2 min (level touch, trend change, volatility, news). Deployed as tg-bot v23; `main` = 737b446. |
| 2026-11-20 | **Command cleanup** (owner t238u): journal/trade commands deleted, scoped Telegram menus, Persian copy pass, `/e` SL side wording, Sun/Mon 00:00–00:30 entry-limit fix. tg-bot v24 (commit 2f3420a). |
| 2026-11-20 | **Plain Persian for beginners** (owner t240u–t243u): every message rewritten; level-touch alert only within $1 of the level, with how far price went, the gap and where it is now; plain `/levels` card; same wording on the indicator labels. tg-bot **v25** (commit c86c529), indicator commit e4d55cb. |
| 2026-11-21 00:04 | **Group post** (owner t238u): Xauscalper Map fa (msg 2979) and en (2980) files plus the plain group guide (2981–2982) posted to BAROBAX via a one-off workflow on branch `group-guide-post` (workflow deleted afterwards). |
| 2026-11-21 | `bot-assistant-v2` (fast-forward) and `tv-decision-map` (merge commit) merged into `main`; the Python plain wording is live from the next GitHub Actions run. |
| 2026-11-21 | **Telegram outage** (owner t245u «دستورها کار نمی‌کنه»): from ~Nov 20 evening every authenticated Bot API call for this bot hangs (invalid tokens get 401 at once), so no command replies. Not caused by our code; `tg()` now has a 20 s timeout. See §8. |
| 2026-11-21 | **Final audit** (owner t244u, t246u, branch `final-audit`): new names; ONE price basis DaryaGold = mid + 0.02 (levels too, old snapshots rebased); stricter SL rule (SL distance + M5 ATR ≤ $9); phone-friendly `/levels` ladder, `/brief`, setup cards, `/trend`; menu descriptions + bot description/short description; indicator renamed to ZARVA Map with the same basis and SL rule. tg-bot build `2026-11-21-assistant-v5.1-onebasis`. |

## 3. Architecture
```
Telegram ──webhook──▶ Supabase Edge Function tg-bot (Deno, verify_jwt=false)
                         │  /tg     Telegram updates (secret_token header checked)
                         │  /tick   pg_cron every 2 min (x-report-key header = webhook secret from Vault)
                         │  /state, /admin/setup   GitHub Actions (OIDC token, main branch only)
                         │  /health public, read-only (build, Tehran time, market_closed)
                         ▼
                  Postgres (RLS on, no policies; service role only)
                    bot_state (one jsonb row: settings, levels snapshot, queue, sent alerts, menu_version)
                    setups (every shown setup, tracked silently), price_observations (/calibrate),
                    signals, journal (legacy, read-only now)
                  Vault: telegram_bot_token, gh_dispatch_token, tg_webhook_secret

pg_cron ──dispatch──▶ GitHub Actions .github/workflows/telegram-bot.yml (runs bot/bot.py from **main**)
                         levels snapshot (tools/level_view.py), /brief, queued /levels, briefs 07:00 / 11:15 / 16:15,
                         news calendar (ForexFactory feed), Friday and close reminders
```
- Edge Function code: `supabase/functions/tg-bot/` — `app.js` (routes, tick, Telegram I/O), `lib.js` (commands, menus,
  `/levels` card, help), `assist.js` (market data from Dukascopy, trend, setups, `/e`, alerts), `calib.js` (/calibrate).
- Market data in the Edge Function: Dukascopy 1-minute bid/ask, aggregated to M5/M15/H1/H4. Trend per TF = confirmed
  swings + EMA20/50; the big direction = H4 and H1 agreeing.
- Python side: `bot/bot.py` + `tools/` (levels, news, brief). **Wording changes in Python go live only after merging to
  `main`**, because the workflow checks out `main`. Edge Function changes go live on deploy.
- Cron jobs (pg_cron, UTC): `m5-tick */2 3-20 * * 1-5`, `m5-early */15 4-7 * * 1-5`, `m5-scan */15 8-20 * * 1-5`,
  `m5-asia-shadow 30,45 3 * * 1-5`, `m5-cron-log-cleanup 30 3 * * *`. The old `m5-report` jobs are unscheduled.
- Telegram menus, the bot description and short description (fa + default) are set by `menuCalls()` once per `MENU_VERSION` on the next `/tick` (`state.menu_version`), or by
  `/admin/setup set_commands`.

## 4. Commands (tg-bot build 2026-11-21-assistant-v5.2-hours)
Owner private chat (45639251), menu order: `/setup` `/e` `/trend` `/levels` `/brief` `/status` `/balance` `/offset`
`/calibrate` `/groupoff` `/groupon` `/help`.
Group «⬩ Z A R V A ⬩» (-1001958445009) and default scope: `/setup` `/trend` `/levels` `/brief` (60 s cooldown per command, group
variant has no toman or balance; respects `/groupoff`).
Hidden aliases: `/signal` and `/scan` → `/setup`; `/start` → `/help`.
Removed for good (answer «دستور ناشناخته»): `/trade /loss /win /undo /shadow /entered /tp /sl /closed /journal /pnl`,
the `/report` endpoint, the old inline buttons, `ledger.js`.

- `/setup`: (phone card: 📍 ورود / 🛑 حد ضرر / 🎯 حد سود / ⏳ معتبر تا / 💡 why) up to 2 buy + 2 sell setups from the levels snapshot and the live price: entry range (≤ $1.5), SL, TP1, TP2,
  credibility 0–100 (⚠ under 40), valid until (45 min, cut at news / Friday 23:30 / close), plain "why" line. Owner card has
  toman for 1 and 0.5 unit after the fee (best and worst edge). A setup is rejected when SL distance + M5 ATR(14) > $9 or
  net R:R < 0.6 (with the fee). Every shown setup is logged to `setups` and resolved silently.
- `/e [buy|sell] <price>`: SL/TP1/TP2 for an entry; side optional (taken from the big direction).
- `/trend`, `/levels`, `/brief`: see `docs/bot_messages_samples_fa.md` (before/after samples of every message type).
- Alerts (owner only, from `/tick`): level touch (only within **$1 of the level price**, once per level per day; says how
  far price went, the gap and where it is now: bounced / at the level / crossed / crossed and came back), M15/H1 trend
  change, volatility high/low, major US news ~10 min ahead.
- Wording rules (enforced by tests): «دریاگلد», «ضرر» (never «زیان»), never «قوی» for levels, no disclaimers, formal
  imperative, ZWNJ, prices in Latin digits inside code for tap-to-copy, other digits Persian.

## 5. Cost model and price bases
- 1 unit = 80,000 toman per $1, 0.5 unit = 40,000; fee 14,000 toman once per trade; spread margin $0.25 (a buy fills at
  the ask); margins 1,000,000 / 500,000; stop-out at 80% loss of equity.
- **ONE price basis since 2026-11-21 (owner t244u): DaryaGold = Dukascopy mid + `dg_offset` (default 0.02)** for levels,
  the live price, setups, `/e`, alerts and the indicator. Levels are built on bid bars and shifted by half the typical
  feed spread: level = bid + 0.175 + 0.02 = bid + 0.195 (`assist.levelOffset`, Python `broker_daryagold.set_mid_offset`,
  fallback 0.195 in `bot.py`). Old snapshots carry `snap.offset` (0.30 = old bid basis) and are moved by `rebaseSnap`.
  `/offset <x>` sets the one offset; `/calibrate <DaryaGold price>` measures it against the mid ("dukascopy_mid").
  Before 2026-11-21: levels = bid + 0.30, live = mid + 0.02 (about 0.1 apart).

## 6. Research results (no edge)
- Phase 4 (`backtest/phase4/REPORT.md`): live engines under the DaryaGold cost model — IS −0.31R per fill (112 fills,
  t −2.4), OOS −0.28R (135 fills, t −2.3), OOS net −7.71M toman; losses concentrated 11:15–16:15 Tehran.
- v2 engines failed out-of-sample (2026-11-13).
- Freqtrade research (branch `freqtrade-research`, commit 32c6f01, `freqtrade/results/RESULTS.md`): **S2 momentum short
  is the only weak candidate** — IS 30 trades PF 1.34; OOS 16 trades, 43.8% win, PF 1.13, +355,680 toman, 62nd percentile
  vs random. Not significant; not deployed.
- Conclusion: no backtested edge. The bot is a decision aid, not a signal service.

## 7. TradingView indicator (ZARVA Map, formerly Xauscalper Map)
- Merged into `main` from branch `tv-decision-map` (commits 90625ad, e4d55cb). The older Xauscalper Zones indicator
  (`tradingview/xauscalper_zones*.pine`, `tradingview/src/`) came along with the merge and is superseded by the Map.
- Source `tradingview/map/template.pine` + `tradingview/map/build.py` → `tradingview/xauscalper_map.pine` (Persian) and
  `xauscalper_map_en.pine` (identical logic, only texts differ). Copies on the box: `/workspace/xauscalper_map.pine`,
  `/workspace/xauscalper_map_en.pine`. Spec `docs/decision_map_spec.md`; phone how-to `tradingview/map_howto_fa.md`.
- Features: phone mode, trend strip (5/15/1H/4H + big direction + short-term state), market light, room-to-trade,
  best setup with entry band, SL, TP1/TP2 with toman, credibility and countdown. One basis: mid + 0.02 (bid chart + 0.175 + 0.02);
  same SL rule (risk + ATR ≤ 9). Display title «ZARVA Map · XAUUSD» (short ZRV); file names kept (`xauscalper_map*.pine`).
  Free TradingView plan: 2 `request.security` calls.
- Sun/Mon 00:00–00:30 (checked 2026-11-21): `f_limit` and `f_clock` already treat 00:00–00:30 as the previous trading
  day's tail (Saturday = Friday tail until 00:30 with entries closed after Friday 23:30; Sunday/Monday = closed), same as
  the bot's `entryLimit`.

## 8. Deployed vs pending
Deployed (2026-11-21 01:58 Tehran):
- tg-bot **v28** (build `2026-11-21-assistant-v5.2-hours`; market open Mon 01:30, alerts from 07:00; v27 = v5.1 exact group title): ZARVA names, one price basis, SL + ATR ≤ $9, phone cards,
  20 s `tg()` timeout. `MENU_VERSION` `2026-11-21-t246u-b` (menus + bot description/short description) is applied by the
  first `/tick` after deploy (the tick cron runs Mon–Fri only) or by the setup workflow (`mode=setup`).
- `main` contains everything (branch `final-audit` fast-forwarded). Python changes (0.195 level basis, news lines in the
  brief, plain ladder) are live from the next GitHub Actions run.
- An older group guide and both indicator files were posted to the group on 2026-11-21 00:04 (messages 2979–2982);
  they still say «Xauscalper» / «Xauscalper Map». Updated texts: `docs/group_guide_fa.md`, `tradingview/map_howto_fa.md`,
  regenerated `tradingview/xauscalper_map*.pine`. Not reposted (needs the owner's go-ahead).

**Telegram outage (resolved 2026-11-21 ~02:00 Tehran, outside our code):** from ~2026-11-20 evening every authenticated
Bot API call for this bot hung (from Supabase and GitHub runners) while a wrong token got 401 at once, so commands got no
reply. At 01:59 Tehran the setup workflow got through: webhook OK, menus and descriptions set, and Telegram delivered the
queued updates (POST /tg 200, no errors; the group's queued /setup /trend /levels /brief were answered by the bot).
getMe/getWebhookInfo answer in 0.4 s (pending 0, no error). If it happens again: branch `name-probe` (push → read-only
getMe, getWebhookInfo, names, descriptions, menus); when getMe answers, run
`gh workflow run telegram-bot.yml --ref main -f mode=setup` and check `webhook_url_ok: true` and `POST /tg 200` in the logs.
If it never recovers: check the bot in @BotFather, or regenerate the token, update the `TELEGRAM_BOT_TOKEN` GitHub
secret and run the setup workflow (it stores the token in Vault).

Pending / owner questions:
1. Hours settled (owner 2026-11-21): market open Mon 01:30, sessions 01:30–00:30, Friday cutoff 23:30, alerts/briefs
   from 07:00. Implemented in build `2026-11-21-assistant-v5.2-hours`. Note: the 01:30 open is fixed in Tehran time; if
   DaryaGold follows New York summer time (EDT), the open/close would move one hour earlier in Tehran — change
   `session.open`/`close` in `tools/broker_daryagold.json`, `OPEN_MIN`/`CLOSE_MIN` in `lib.js`, `entryLimit` and the Pine inputs.
2. Repost the updated guide/indicator to the group (owner decision; nothing is posted without approval).

## 9. Security rules
- Never print, commit or log tokens. Secrets live in Supabase Vault and GitHub secrets only.
- No paid services, no order execution, no DaryaGold login.
- Nothing is posted to the group and no message is sent for the owner without explicit approval.
- The group never gets toman amounts, balance or personal data.
- Only the owner's chat may run owner commands; group commands are read-only.

## 10. How to test and deploy
```bash
# Edge Function tests (offline, mocked network)
cd supabase/functions/tg-bot && node test.mjs && node test_assist.mjs      # both must print "0 failed"
# Python
STATE_DIR=$(mktemp -d) python3 bot/test_bot.py                               # "0 failed"
python3 -m pytest -q tests                                                   # run from repo root; not plain `pytest` (bot/test_bot.py exits)
# Bundle (the Supabase MCP deploy takes one file)
npx esbuild supabase/functions/tg-bot/index.ts --bundle --format=esm --platform=neutral --target=es2022 --outfile=/tmp/deploy/index.js
# Deploy: Supabase deploy_edge_function, project kinbkthbbwzrfogqqttl, name tg-bot, verify_jwt=false, entrypoint index.js
curl -s https://kinbkthbbwzrfogqqttl.supabase.co/functions/v1/tg-bot/health   # check the build tag
```
Bump `BUILD` in `app.js` on every deploy; bump `MENU_VERSION` in `lib.js` only when the command menus change.
Indicator: edit `tradingview/map/template.pine` / `build.py`, run `python3 tradingview/map/build.py`, keep formulas identical
between fa and en.
