"""Static checks of the Supabase migrations added in Phase 1/2 (applied with the Supabase tools, verified live by SQL)."""
import os, re
MIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase", "migrations")
read = lambda n: open(os.path.join(MIG, n), encoding="utf-8").read()


def test_price_observations_server_role_only():
    s = read("20261120190000_price_observations.sql")
    assert "enable row level security" in s and "revoke all on table public.price_observations from public, anon, authenticated" in s
    assert not re.search(r"(?m)^grant[^;]*\b(anon|authenticated)\b", s) and "create policy" not in s
    for st in ("NORMAL_ALIGNMENT", "MINOR_BASIS", "ELEVATED_BASIS", "FEED_DESYNCHRONIZATION", "DATA_UNAVAILABLE"):
        assert st in s
    assert "3569.85" in s and "'user_report'" in s and "'oanda_m1_close'" in s and "-0.09" in s


def test_full_session_cron():
    s = read("20261120180000_bot_full_session_cron.sql")
    assert "'*/15 8-20 * * 1-5'" in s and "'*/15 4-7 * * 1-5'" in s and "'30,45 3 * * 1-5'" in s
    for j in ("m5-brief-am", "m5-last", "m5-friday-close", "m5-daily-close"):
        assert f"cron.unschedule('{j}')" in s


def test_signals_journal_server_role_only():
    s = read("20261120200000_signals_journal.sql")
    assert "alter table public.signals enable row level security" in s and "alter table public.journal enable row level security" in s
    assert "revoke all on table public.signals, public.journal from public, anon, authenticated" in s
    assert not re.search(r"(?m)^grant[^;]*\b(anon|authenticated)\b", s) and "create policy" not in s
    assert "'^S-\\d{8}-\\d{3}$'" in s
    for st in ("'sent'", "'entered'", "'closed'", "'expired'", "'not_taken'"):
        assert st in s
    # report cron: daily after the 00:30 close (21:15 UTC = 00:45 Tehran), weekly Saturday 10:00 Tehran
    assert "'15 21 * * 1-5'" in s and "'30 6 * * 6'" in s and "bot_webhook_secret()" in s
    assert "revoke all on function public.bot_report(text) from public, anon, authenticated" in s


def test_journal_csv_import_real_trades_only():
    s = read("20261120200000_signals_journal.sql")
    rows = re.findall(r"\('2026-11-13-M\d-(?:SELL|BUY)'", s)
    assert len(rows) == 4 and s.count("'USER_CONFIRMED'") >= 4 and "on conflict (trade_id) do nothing" in s
    for net in ("342800", "742800", "181200", "687600"):
        assert net in s


def test_signal_tracking_columns():
    s = read("20261120210000_signal_tracking.sql")
    for c in ("track_outcome", "track_fill_at", "mfe_usd", "mae_usd", "mfe_r", "mae_r", "tracked_at"):
        assert f"add column if not exists {c}" in s
    assert "'no_fill', 'open', 'tp', 'sl', 'close'" in s
    assert "grant" not in s.lower() and "policy" not in s.lower()   # privileges unchanged: service role only


def test_assistant_v2_setups_tick_and_reports_off():
    s = read("20261121000000_assistant_v2.sql")
    assert "alter table public.setups enable row level security" in s
    assert "revoke all on table public.setups from public, anon, authenticated" in s
    assert not re.search(r"(?m)^grant[^;]*\b(anon|authenticated)\b", s) and "create policy" not in s
    for st in ("'pending'", "'filled'", "'tp1'", "'tp2'", "'sl'", "'expired'", "'invalidated'", "'missed'", "'timeout'"):
        assert st in s
    assert "check (score between 0 and 100)" in s
    # alerts tick every 2 minutes on weekdays; the secret comes from Vault inside the function
    assert "cron.schedule('m5-tick', '*/2 3-20 * * 1-5'" in s and "/tg-bot/tick" in s and "bot_webhook_secret()" in s
    assert "revoke all on function public.bot_tick() from public, anon, authenticated" in s
    # journal reports switched off with the trade journal
    assert "cron.unschedule('m5-report-daily')" in s and "cron.unschedule('m5-report-weekly')" in s
    # the setup id format written by app.js matches the check
    assert "'^U-\\d{14}-[og][BS]\\d-[a-z0-9]{1,6}$'" in s
