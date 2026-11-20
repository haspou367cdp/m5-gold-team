from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
import risk_gate as RG
import broker_daryagold as DG
import execution_policy as EP

TEH = ZoneInfo("Asia/Tehran")
WED = datetime(2026, 11, 18, 14, 0, tzinfo=TEH)
OPEN = {"blocked": False}
CLEAR = {"inside": False, "soon_block": False}


def ev(**kw):
    a = dict(now=WED, side="SELL", entry=3880.0, sl=3881.6, tp=3876.0, unit="1U", data_ok=True, data_age_min=1,
             session=OPEN, news_window=CLEAR, news_ok=True)
    a.update(kw)
    return RG.evaluate(**a)


def test_clean_setup_approved():
    g = ev()
    assert g["status"] == RG.APPROVED and g["approved"] and g["reasons_fa"] == []
    assert g["metrics"]["fee_scenario"] == "ONCE" and g["metrics"]["net_rr"] >= 1.5


def test_rr_uses_confirmed_once_fee_with_spread():
    # 1.55 with the fee once (gated) and 1.45 with entry+exit fees (reported only) -> approved
    g = ev(tp=3876.15)
    assert g["status"] == RG.APPROVED
    assert g["metrics"]["net_rr"] == g["metrics"]["scenarios"]["ONCE"] >= 1.5 > g["metrics"]["scenarios"]["ENTRY_AND_EXIT"]
    # spread is still charged: risk 1.6*80k + 0.25*80k + 14k
    assert g["metrics"]["risk_toman"] == 128_000 + 20_000 + 14_000
    r = ev(tp=3877.6)
    assert r["status"] == RG.REJECTED and any("نسبت سود به ضرر خالص" in x for x in r["reasons_fa"])


def test_stop_out_warning_and_reject():
    w = ev(side="BUY", entry=3550, sl=3545, tp=3560)
    assert w["status"] == RG.APPROVED_WITH_WARNING and w["warnings_fa"] and "استاپ‌اوت" in w["warnings_fa"][0]
    r = ev(side="BUY", entry=3550, sl=3542.5, tp=3570)
    assert r["status"] == RG.REJECTED and any("حراج" in x for x in r["reasons_fa"])


def test_session_closed_and_weekend():
    for t in (datetime(2026, 11, 18, 3, 0, tzinfo=TEH), datetime(2026, 11, 21, 12, 0, tzinfo=TEH)):
        g = ev(now=t, session=None)
        assert g["status"] == RG.NO_TRADE and "بسته است" in g["reasons_fa"][0]
    fri = ev(now=datetime(2026, 11, 20, 22, 45, tzinfo=TEH), session=None)
    assert fri["status"] == RG.NO_TRADE and "جمعه" in fri["reasons_fa"][0]
    assert ev(now=datetime(2026, 11, 20, 22, 15, tzinfo=TEH), session=None)["status"] == RG.APPROVED


def test_news_blackout():
    assert ev(news_window={"inside": True, "action": "block"})["status"] == RG.NO_TRADE
    assert ev(news_window={"soon_block": True})["status"] == RG.NO_TRADE
    assert ev(news_ok=False)["status"] == RG.NO_TRADE
    assert ev(news_window={"inside": True, "action": "monitor"})["status"] == RG.APPROVED


def test_news_from_file(monkeypatch):
    import news_windows as nw
    doc = {"date": "2026-11-18", "windows": []}
    monkeypatch.setattr(nw, "load", lambda: doc)
    monkeypatch.setattr(nw, "effective_doc", lambda d, floors=None: d)
    monkeypatch.setattr(nw, "status", lambda d, at=None, lookahead=30: {"inside": True, "action": "block"})
    assert ev(news_window=None)["status"] == RG.NO_TRADE
    monkeypatch.setattr(nw, "load", lambda: (_ for _ in ()).throw(OSError("missing")))
    g = ev(news_window=None)
    assert g["status"] == RG.NO_TRADE and "پنجره‌های خبری" in g["reasons_fa"][0]


def test_data_stale_or_invalid():
    assert ev(data_age_min=11)["status"] == RG.REJECTED
    assert ev(data_age_min=None)["status"] == RG.REJECTED
    assert ev(data_ok=False)["status"] == RG.REJECTED


def test_calc_failure_rejects():
    g = ev(entry=None)
    assert g["status"] == RG.REJECTED and any("محاسبه‌ی ریسک" in r for r in g["reasons_fa"])
    g = ev(side="BUY")   # BUY with a SELL geometry
    assert g["status"] == RG.REJECTED


def test_no_setup_is_no_trade():
    assert ev(side=None)["status"] == RG.NO_TRADE


def test_persian_wording():
    texts = []
    for kw in ({"tp": 3877.6}, {"side": "BUY", "entry": 3550, "sl": 3542.5, "tp": 3570}, {"news_ok": False},
               {"data_age_min": 30}, {"entry": None}):
        g = ev(**kw); texts += g["reasons_fa"] + g["warnings_fa"]
    blob = " ".join(texts)
    import re
    assert "زیان" not in blob and not re.search(r"(?<!\w)قوی(?!\w)", blob) and "فقط تحلیلی" not in blob
    assert "بیش از ۱۰ دقیقه" in blob


def test_policy_violation_blocks_gate(monkeypatch):
    monkeypatch.setattr(EP, "AUTOMATED_ORDER_EXECUTION", True)
    with pytest.raises(RuntimeError):
        ev()
