-- 2026-11-20 Phase 2: price calibration. Owner-entered DaryaGold prices paired with a reference feed.
-- basis_usd = darya_price - feed_ref. Only reference 'dukascopy_bid' feeds the bot's offset (DaryaGold = Dukascopy bid + offset).
-- Server role only: RLS on, no policies, nothing granted to anon/authenticated. Written by the tg-bot Edge Function.
create table if not exists public.price_observations (
  id           bigint generated always as identity primary key,
  observed_at  timestamptz not null,
  recorded_at  timestamptz not null default now(),
  source       text not null check (source in ('telegram_calibrate', 'user_report')),
  darya_price  numeric(10,2) not null check (darya_price > 0),
  darya_ask    numeric(10,2) check (darya_ask is null or darya_ask >= darya_price),
  reference    text not null check (reference in ('dukascopy_bid', 'oanda_m1_close')),
  feed_bid     numeric(10,3),
  feed_ask     numeric(10,3),
  feed_ref     numeric(10,3),
  feed_bar_at  timestamptz,
  feed_age_s   integer,
  basis_usd    numeric(8,3),
  session      text check (session in ('asia', 'london', 'newyork', 'closed')),
  status       text not null check (status in ('NORMAL_ALIGNMENT', 'MINOR_BASIS', 'ELEVATED_BASIS', 'FEED_DESYNCHRONIZATION', 'DATA_UNAVAILABLE')),
  note         text
);
create index if not exists price_observations_observed_at on public.price_observations (observed_at);
alter table public.price_observations enable row level security;
revoke all on table public.price_observations from public, anon, authenticated;
grant select, insert on table public.price_observations to service_role;

-- Seed: owner's sample 2026-11-20 16:07:44 Tehran (OANDA M1 chart; not Dukascopy, so it is shown but never sets the offset).
insert into public.price_observations (observed_at, source, darya_price, reference, feed_bid, feed_ask, feed_ref, basis_usd, session, status, note)
select '2026-11-20 16:07:44+03:30', 'user_report', 3569.85, 'oanda_m1_close', 3569.78, 3570.32, 3569.94, -0.09, 'london', 'NORMAL_ALIGNMENT',
       'Owner screenshot: OANDA M1 close 3569.94 (bid 3569.78 / ask 3570.32) vs DaryaGold 3569.85'
where not exists (select 1 from public.price_observations where source = 'user_report' and observed_at = '2026-11-20 16:07:44+03:30');
