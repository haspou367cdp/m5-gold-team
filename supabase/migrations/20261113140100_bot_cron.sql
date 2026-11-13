-- UTC = Tehran - 3:30: 11:15, 11:30-21:15 every 15 min, 21:30 Tehran, Mon-Fri
select cron.schedule('m5-brief-am', '45 7 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
select cron.schedule('m5-scan', '*/15 8-17 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
select cron.schedule('m5-last', '0 18 * * 1-5', $$select public.bot_dispatch('scheduled')$$);
select cron.schedule('m5-cron-log-cleanup', '30 3 * * *', $$delete from cron.job_run_details where end_time < now() - interval '7 days'$$);
