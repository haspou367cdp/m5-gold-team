from datetime import datetime
from zoneinfo import ZoneInfo
import broker_daryagold as DG

TEH = ZoneInfo("Asia/Tehran")
CFG = DG.load_config()
T = lambda *a: datetime(*a, tzinfo=TEH)


def test_hours_monday_to_friday_0700_to_0030():
    assert not DG.market_open(T(2026, 11, 16, 6, 59), CFG)      # Monday before open
    assert DG.market_open(T(2026, 11, 16, 7, 0), CFG)
    assert DG.market_open(T(2026, 11, 17, 0, 29), CFG)          # Monday session tail
    assert not DG.market_open(T(2026, 11, 17, 0, 30), CFG)
    assert not DG.market_open(T(2026, 11, 17, 3, 0), CFG)
    assert DG.market_open(T(2026, 11, 21, 0, 29), CFG)          # Friday session tail (Saturday 00:29)
    assert not DG.market_open(T(2026, 11, 21, 7, 0), CFG)       # Saturday
    assert not DG.market_open(T(2026, 11, 22, 12, 0), CFG)      # Sunday
    assert not DG.market_open(T(2026, 11, 16, 0, 15), CFG)      # Monday 00:15 = Sunday night


def test_entry_block_and_close_times():
    w = DG.session_entry_block(T(2026, 11, 18, 14, 0), CFG)
    assert not w["blocked"] and w["close_tehran"] == "2026-11-19 00:30"
    n = DG.session_entry_block(T(2026, 11, 19, 1, 0), CFG)
    assert n["blocked"] and n["reopen_tehran"] == "2026-11-19 07:00" and "بازگشایی" in n["reason_fa"]
    f = DG.session_entry_block(T(2026, 11, 20, 22, 30), CFG)
    assert f["blocked"] and f["friday_window"] and f["close_tehran"] == "2026-11-21 00:30"
    assert not DG.session_entry_block(T(2026, 11, 20, 22, 29), CFG)["blocked"]
    sat = DG.session_entry_block(T(2026, 11, 21, 12, 0), CFG)
    assert sat["blocked"] and sat["reopen_tehran"] == "2026-11-23 07:00"


def test_close_reminder_never_closes():
    assert DG.close_reminder(T(2026, 11, 18, 23, 59), CFG) is None
    msg = DG.close_reminder(T(2026, 11, 19, 0, 0), CFG)
    assert msg and "۰۰:۳۰" in msg and "بررسی کن" in msg
    assert DG.close_reminder(T(2026, 11, 19, 0, 30), CFG) is None
    import execution_policy as EP
    assert EP.AUTO_CLOSE_POSITIONS is False


def test_no_old_forex_schedule_left():
    line = DG.session_entry_block(T(2026, 11, 18, 14, 0), CFG)["hours_line_fa"]
    assert "۰۷:۰۰" in line and "۰۰:۳۰" in line and "۰۱:۳۰" not in line and "نیویورک" not in line
