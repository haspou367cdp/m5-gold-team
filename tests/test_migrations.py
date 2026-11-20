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
