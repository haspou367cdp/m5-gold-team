-- 2026-11-20 Phase 1: DaryaGold hours are Mon-Fri 07:00 to 00:30 (next day) Tehran; Saturday and Sunday closed.
-- pg_cron upserts by job name. All times UTC (Tehran = UTC+3:30, no DST).
-- Friday 19:00 UTC = 22:30 Tehran: Friday entry cutoff reminder (was 23:30 with the old 01:30 forex close).
select cron.schedule('m5-friday-close', '0 19 * * 5', $$select public.bot_dispatch('scheduled')$$);
-- Mon-Fri 20:30 UTC = 00:00 Tehran (Tue-Sat): reminder that the market closes at 00:30; check open positions manually.
-- Nothing is closed automatically. Dedup key: bot_state.friday_reminder_sent ("close:<session date>"), already mergeable.
select cron.schedule('m5-daily-close', '30 20 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
-- Asia log-only runs: DaryaGold is closed before 07:00 Tehran, so start at 03:00 UTC (06:30 Tehran) instead of 00:00 UTC.
select cron.schedule('m5-asia-shadow', '*/30 3-7 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
