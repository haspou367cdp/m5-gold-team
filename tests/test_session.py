from datetime import datetime
from zoneinfo import ZoneInfo
import broker_daryagold as DG

TEH = ZoneInfo("Asia/Tehran")
CFG = DG.load_config()
T = lambda *a: datetime(*a, tzinfo=TEH)


def test_hours_monday_0130_sessions_to_0030():
    assert not DG.market_open(T(2026, 11, 16, 1, 29), CFG)      # Monday before the 01:30 open
    assert DG.market_open(T(2026, 11, 16, 1, 30), CFG)
    assert DG.market_open(T(2026, 11, 16, 6, 59), CFG)
    assert DG.market_open(T(2026, 11, 16, 7, 0), CFG)
    assert DG.market_open(T(2026, 11, 17, 0, 29), CFG)          # Monday session tail
    assert not DG.market_open(T(2026, 11, 17, 0, 30), CFG)
    assert not DG.market_open(T(2026, 11, 17, 1, 29), CFG)      # daily break 00:30-01:30
    assert DG.market_open(T(2026, 11, 17, 1, 30), CFG)
    assert DG.market_open(T(2026, 11, 17, 3, 0), CFG)
    assert DG.market_open(T(2026, 11, 21, 0, 29), CFG)          # Friday session tail (Saturday 00:29)
    assert not DG.market_open(T(2026, 11, 21, 7, 0), CFG)       # Saturday
    assert not DG.market_open(T(2026, 11, 22, 12, 0), CFG)      # Sunday
    assert not DG.market_open(T(2026, 11, 16, 0, 15), CFG)      # Monday 00:15 = Sunday night


def test_entry_block_and_close_times():
    w = DG.session_entry_block(T(2026, 11, 18, 14, 0), CFG)
    assert not w["blocked"] and w["close_tehran"] == "2026-11-19 00:30"
    n = DG.session_entry_block(T(2026, 11, 19, 1, 0), CFG)
    assert n["blocked"] and n["reopen_tehran"] == "2026-11-19 01:30" and "بازگشایی" in n["reason_fa"]
    f = DG.session_entry_block(T(2026, 11, 20, 23, 30), CFG)
    assert f["blocked"] and f["friday_window"] and f["close_tehran"] == "2026-11-21 00:30"
    assert f["block_start_tehran"] == "2026-11-20 23:30"
    assert not DG.session_entry_block(T(2026, 11, 20, 23, 29), CFG)["blocked"]
    assert not DG.session_entry_block(T(2026, 11, 20, 22, 30), CFG)["blocked"]
    sat = DG.session_entry_block(T(2026, 11, 21, 12, 0), CFG)
    assert sat["blocked"] and sat["reopen_tehran"] == "2026-11-23 01:30"


def test_close_reminder_never_closes():
    assert DG.close_reminder(T(2026, 11, 18, 23, 59), CFG) is None
    msg = DG.close_reminder(T(2026, 11, 19, 0, 0), CFG)
    assert msg and "`00:30`" in msg and "بررسی کن" in msg
    assert DG.close_reminder(T(2026, 11, 19, 0, 30), CFG) is None
    import execution_policy as EP
    assert EP.AUTO_CLOSE_POSITIONS is False


def test_no_old_forex_schedule_left():
    line = DG.session_entry_block(T(2026, 11, 18, 14, 0), CFG)["hours_line_fa"]
    assert "۰۱:۳۰" in line and "۰۰:۳۰" in line and "۰۷:۰۰" not in line and "نیویورک" not in line


def test_alert_window_from_0700():
    assert not DG.alert_window(T(2026, 11, 16, 3, 0), CFG) and DG.market_open(T(2026, 11, 16, 3, 0), CFG)
    assert DG.alert_window(T(2026, 11, 16, 7, 0), CFG) and DG.alert_window(T(2026, 11, 17, 0, 29), CFG)
    assert not DG.alert_window(T(2026, 11, 17, 0, 30), CFG) and not DG.alert_window(T(2026, 11, 21, 12, 0), CFG)
    assert DG.session_end(T(2026, 11, 18, 14, 0), CFG).strftime("%Y-%m-%d %H:%M") == "2026-11-19 00:30"
    assert DG.session_end(T(2026, 11, 19, 0, 10), CFG).strftime("%Y-%m-%d %H:%M") == "2026-11-19 00:30"


def test_calibration_label(monkeypatch):
    monkeypatch.setenv("DG_CALIBRATION", "not_calibrated")
    c = DG.load_config()
    assert c["calibration_status"] == "not_calibrated" and "کالیبره نشده" in DG.price_convention_fa(c)
    monkeypatch.setenv("DG_CALIBRATION", "calibrated")
    monkeypatch.setenv("DG_OFFSET_USD", "0.12")
    c = DG.load_config()
    assert DG.offset_usd(c) == 0.295 and c["mid_offset_usd"] == 0.12 and "/calibrate" in DG.price_convention_fa(c)


def test_trading_day_key():
    assert DG.session_date(T(2026, 11, 21, 0, 20), CFG) == "2026-11-20"
    assert DG.session_date(T(2026, 11, 20, 7, 0), CFG) == "2026-11-20"
    assert DG.session_start(T(2026, 11, 20, 0, 10), CFG).strftime("%Y-%m-%d %H:%M") == "2026-11-19 01:30"
    assert DG.session_date(T(2026, 11, 20, 1, 29), CFG) == "2026-11-19" and DG.session_date(T(2026, 11, 20, 1, 30), CFG) == "2026-11-20"


def test_asia_window_is_live_since_owner_decision():
    """Owner decision 2026-11-20 17:08 Tehran: signals from the 07:00 open; the 07:00-11:15 window is no longer log-only."""
    import re, os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot", "bot.py"), encoding="utf-8").read()
    assert re.search(r"(?m)^ASIA_LOG_ONLY = False\b", src)
    assert "and ASIA_LOG_ONLY and in_asia(t)" in src


def test_persian_user_guide():
    import os, re
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "README_FA.md")
    s = open(p, encoding="utf-8").read()
    for cmd in ("/entered", "/tp", "/sl", "/closed", "/journal", "/pnl", "/calibrate", "/trade", "/scan", "/groupoff"):
        assert cmd in s
    for must in ("۰۱:۳۰ تا ۰۰:۳۰", "۰۷:۰۰ تا ۰۰:۳۰", "14,000", "0.25", "80,000", "40,000", "1,000,000", "500,000", "۶۰ ثانیه", "گزارش", "محدودیت"):
        assert must in s
    assert "زیان" not in s and not re.search(r"(^|[\s،.])قوی([\s،.]|$)", s)
