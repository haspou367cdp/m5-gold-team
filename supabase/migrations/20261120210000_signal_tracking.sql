-- 2026-11-20 Phase 4: forward tracking of every signal (what the signal itself did, whatever the owner did).
-- Written by the Edge Function from the GitHub run's 1-minute data. Prices are DaryaGold prices (bid + offset).
alter table public.signals
  add column if not exists track_outcome  text check (track_outcome in ('no_fill', 'open', 'tp', 'sl', 'close')),
  add column if not exists track_fill_at  timestamptz,
  add column if not exists mfe_usd        numeric(8,2),
  add column if not exists mae_usd        numeric(8,2),
  add column if not exists mfe_r          numeric(6,2),
  add column if not exists mae_r          numeric(6,2),
  add column if not exists tracked_at     timestamptz;
