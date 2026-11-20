-- 2026-11-20 Phase 1 gap: scheduled runs cover the whole DaryaGold session (Mon-Fri 07:00 to 00:30 Tehran).
-- UTC = Tehran - 3:30. pg_cron upserts by job name.
-- 07:00-11:15 Tehran (03:30-07:45 UTC): Asia/London-open runs every 15 min; bot.py keeps 07:00-11:15 log-only (existing rule).
select cron.schedule('m5-asia-shadow', '30,45 3 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
select cron.schedule('m5-early', '*/15 4-7 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
-- 11:30 Tehran to 00:15 Tehran (08:00-20:45 UTC) every 15 min. Covers the old 21:30 last check, the Friday 22:30
-- cutoff reminder and the 00:00-00:15 daily close reminder, so those separate jobs are removed.
select cron.schedule('m5-scan', '*/15 8-20 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
select cron.unschedule('m5-brief-am');   -- 07:45 UTC (11:15 Tehran) is now covered by m5-early
select cron.unschedule('m5-last');
select cron.unschedule('m5-friday-close');
select cron.unschedule('m5-daily-close');
