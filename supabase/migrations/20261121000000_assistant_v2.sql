-- 2026-11-21 Assistant redesign (owner t226u-t232u): no automatic signals, no trade journal; /setup /trend /e answered
-- live by the Edge Function; alerts from /tick. Server role only; nothing for anon/authenticated.

-- Every setup shown by /setup (owner or group) and its silent outcome, for calibrating the 0-100 credibility score.
create table if not exists public.setups (
  id            text primary key check (id ~ '^U-\d{14}-[og][BS]\d-[a-z0-9]{1,6}$'),
  created_at    timestamptz not null default now(),
  origin        text not null check (origin in ('owner', 'group')),
  side          text not null check (side in ('BUY', 'SELL')),
  rank          smallint,
  entry_lo      numeric(10,2) not null,   -- DaryaGold chart prices as shown
  entry_hi      numeric(10,2) not null,
  better_half   text,
  sl            numeric(10,2) not null,
  tp1           numeric(10,2) not null,
  tp2           numeric(10,2),
  score         smallint not null check (score between 0 and 100),
  factors       jsonb,
  reason        text,
  trend         jsonb,
  price_at      numeric(10,2),
  dg_bid_offset numeric(6,2),             -- DaryaGold - Dukascopy bid at creation (tracking converts bid bars with it)
  spread        numeric(6,2),
  level_price   numeric(10,2),
  valid_until   timestamptz not null,
  invalid_price numeric(10,2),
  status        text not null default 'pending'
                check (status in ('pending', 'filled', 'tp1', 'tp2', 'sl', 'expired', 'invalidated', 'missed', 'timeout')),
  filled_at     timestamptz,
  resolved_at   timestamptz,
  tp1_hit       boolean,
  tp2_hit       boolean,
  sl_hit        boolean,
  mfe_usd       numeric(8,2),
  mae_usd       numeric(8,2),
  checked_at    timestamptz
);
create index if not exists setups_open on public.setups (status, created_at);
alter table public.setups enable row level security;
revoke all on table public.setups from public, anon, authenticated;
grant select, insert, update on table public.setups to service_role;

-- Alerts tick: pg_cron -> Edge Function /tick (authenticated with the webhook secret from Vault; never logged).
create or replace function public.bot_tick() returns bigint
language plpgsql security definer set search_path = '' as $$
begin
  return net.http_post(
    url := 'https://kinbkthbbwzrfogqqttl.supabase.co/functions/v1/tg-bot/tick',
    body := '{}'::jsonb,
    headers := jsonb_build_object('content-type', 'application/json', 'x-report-key', public.bot_webhook_secret()),
    timeout_milliseconds := 25000);
end $$;
revoke all on function public.bot_tick() from public, anon, authenticated;
grant execute on function public.bot_tick() to service_role;
-- Every 2 minutes Mon-Fri 03:00-20:58 UTC (06:30-00:28 Tehran); the function itself checks DaryaGold hours (07:00-00:30).
select cron.schedule('m5-tick', '*/2 3-20 * * 1-5', $$select public.bot_tick()$$);

-- The daily/weekly journal reports go with the trade journal (owner t225u/t226u: item 11 off).
do $$ begin
  perform cron.unschedule('m5-report-daily');
exception when others then null; end $$;
do $$ begin
  perform cron.unschedule('m5-report-weekly');
exception when others then null; end $$;
