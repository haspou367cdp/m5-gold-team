-- 2026-11-20 Phase 3: signal lifecycle + trade journal + reports. Server role only (Edge Function); nothing for anon/authenticated.
create table if not exists public.signals (
  id            text primary key check (id ~ '^S-\d{8}-\d{3}$'),
  created_at    timestamptz not null default now(),
  sent_at       timestamptz not null,
  session_date  date not null,
  side          text not null check (side in ('BUY', 'SELL')),
  unit          text not null check (unit in ('1U', '0.5U')),
  entry         numeric(10,2) not null,   -- DaryaGold prices as shown on the card
  sl            numeric(10,2) not null,
  tp            numeric(10,2) not null,
  valid_until   timestamptz,
  net_rr        numeric(6,2),
  risk_toman    integer,
  status        text not null default 'sent' check (status in ('sent', 'entered', 'closed', 'expired', 'not_taken')),
  entered_at    timestamptz,
  entry_fill    numeric(10,2),
  closed_at     timestamptz,
  exit_price    numeric(10,2),
  exit_type     text check (exit_type in ('tp', 'sl', 'manual')),
  net_toman     integer,
  r_multiple    numeric(6,2),
  under_60s     boolean,
  updated_at    timestamptz not null default now()
);
create index if not exists signals_session_date on public.signals (session_date);

create table if not exists public.journal (
  id            bigint generated always as identity primary key,
  trade_id      text not null unique,
  signal_id     text references public.signals (id),
  source        text not null check (source in ('signal', 'trade_cmd', 'journal_csv')),
  verification  text not null default 'USER_CONFIRMED',
  side          text not null check (side in ('BUY', 'SELL')),
  unit          text not null check (unit in ('1U', '0.5U')),
  entry         numeric(10,2) not null,
  exit          numeric(10,2) not null,
  opened_at     timestamptz,
  closed_at     timestamptz not null,
  session_date  date not null,
  exit_type     text check (exit_type in ('tp', 'sl', 'manual')),
  gross_toman   integer not null,
  spread_toman  integer not null default 0,
  fee_toman     integer not null,
  net_toman     integer not null,
  r_multiple    numeric(6,2),
  hold_seconds  integer,
  under_60s     boolean,
  note          text,
  recorded_at   timestamptz not null default now()
);
create index if not exists journal_session_date on public.journal (session_date);

alter table public.signals enable row level security;
alter table public.journal enable row level security;
revoke all on table public.signals, public.journal from public, anon, authenticated;
grant select, insert, update on table public.signals, public.journal to service_role;
grant delete on table public.journal to service_role;   -- /undo of a recorded trade removes its journal row

-- Reports: pg_cron -> Edge Function /report (authenticated with the Telegram webhook secret from Vault; never logged).
create or replace function public.bot_report(p_kind text) returns bigint
language plpgsql security definer set search_path = '' as $$
begin
  if p_kind not in ('daily', 'weekly') then raise exception 'bad kind'; end if;
  return net.http_post(
    url := 'https://kinbkthbbwzrfogqqttl.supabase.co/functions/v1/tg-bot/report',
    body := jsonb_build_object('kind', p_kind),
    headers := jsonb_build_object('content-type', 'application/json', 'x-report-key', public.bot_webhook_secret()),
    timeout_milliseconds := 20000);
end $$;
revoke all on function public.bot_report(text) from public, anon, authenticated;
grant execute on function public.bot_report(text) to service_role;
-- Daily report Tue-Sat 00:45 Tehran (Mon-Fri 21:15 UTC), after the 00:30 close. Weekly report Saturday 10:00 Tehran (06:30 UTC).
select cron.schedule('m5-report-daily', '15 21 * * 1-5', $$select public.bot_report('daily')$$);
select cron.schedule('m5-report-weekly', '30 6 * * 6', $$select public.bot_report('weekly')$$);

-- Import the owner's real manual trades from journal.csv (2026-11-13 M1-M4). Values as recorded: fee once, fills already
-- include the spread (spread_toman 0). Rows without a fill (no_trigger / withdrawn) are not trades and are not imported.
insert into public.journal (trade_id, source, verification, side, unit, entry, exit, opened_at, closed_at, session_date, exit_type,
                            gross_toman, spread_toman, fee_toman, net_toman, hold_seconds, under_60s, note)
values
 ('2026-11-13-M1-SELL', 'journal_csv', 'USER_CONFIRMED', 'SELL', '1U',   3914.07, 3909.61, '2026-11-13 09:04:11+03:30', '2026-11-13 09:10:32+03:30', '2026-11-13', 'manual', 356800, 0, 14000, 342800, 381, false, 'journal.csv, owner manual'),
 ('2026-11-13-M2-SELL', 'journal_csv', 'USER_CONFIRMED', 'SELL', '1U',   3902.68, 3893.22, '2026-11-13 09:16:17+03:30', '2026-11-13 09:17:31+03:30', '2026-11-13', 'manual', 756800, 0, 14000, 742800,  74, false, 'journal.csv, owner manual'),
 ('2026-11-13-M3-BUY',  'journal_csv', 'USER_CONFIRMED', 'BUY',  '0.5U', 3894.11, 3898.99, '2026-11-13 18:11:42+03:30', '2026-11-13 18:20:39+03:30', '2026-11-13', 'manual', 195200, 0, 14000, 181200, 537, false, 'journal.csv, owner manual'),
 ('2026-11-13-M4-SELL', 'journal_csv', 'USER_CONFIRMED', 'SELL', '1U',   3894.49, 3885.72, '2026-11-13 18:22:40+03:30', '2026-11-13 18:38:17+03:30', '2026-11-13', 'manual', 701600, 0, 14000, 687600, 937, false, 'journal.csv, owner manual')
on conflict (trade_id) do nothing;
