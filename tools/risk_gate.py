"""Deterministic risk gate: the last check before any signal is sent.

evaluate(...) -> {"status": APPROVED | APPROVED_WITH_WARNING | REJECTED | NO_TRADE, "reasons_fa", "warnings_fa", "metrics"}
  NO_TRADE  conditions are unsuitable (market closed, news blackout, no BUY/SELL setup)
  REJECTED  a setup exists but fails a risk rule (stale/invalid data, net R:R, stop-out, calculation failure)
Net R:R uses the owner-confirmed fee (14,000 toman once per trade) plus at least the $0.25 market spread.
Pure function apart from optional reads of the session config / news file when they are not passed in.
"""
from datetime import datetime

import darya_model as DM
import execution_policy as EP

APPROVED, APPROVED_WITH_WARNING, REJECTED, NO_TRADE = "APPROVED", "APPROVED_WITH_WARNING", "REJECTED", "NO_TRADE"
MIN_NET_RR = 1.5
MAX_DATA_AGE_MIN = 10


def _fa(x, nd=2):
    s = f"{float(x):.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫"))


def news_status_from_file(now):
    """Status of data/news_windows.json at `now` (same rules as brief.py); None if unreadable."""
    try:
        import news_windows as nw
        return nw.status(nw.effective_doc(nw.load()), at=now)
    except Exception:
        return None


def evaluate(now, side, entry, sl, tp, unit="1U", order_type="MARKET", spread_usd=None,
             data_ok=True, data_age_min=None, session=None, news_window=None, news_ok=True,
             cfg=None, min_net_rr=MIN_NET_RR, max_data_age_min=MAX_DATA_AGE_MIN,
             stopout_safety=0.25, stopout_warn=0.5):
    EP.assert_manual_only()
    no_trade, reject, warn, m = [], [], [], {}

    # 1. session (01:30-00:30 Tehran, Mon 01:30 to Sat 00:30, Friday cutoff 23:30)
    if session is None:
        try:
            import broker_daryagold as DG
            session = DG.session_entry_block(now, cfg)
        except Exception:
            session = {"blocked": True, "reason_fa": "وضعیت ساعت کار دریاگلد معلوم نیست. تصمیم: NO TRADE."}
    if session.get("blocked"):
        no_trade.append(session.get("reason_fa") or "در این ساعت ورود مجاز نیست.")

    # 2. news blackout (tier A/B windows in data/news_windows.json)
    if not news_ok:
        no_trade.append("تقویم خبری به‌روز در دسترس نیست و بدون آن سیگنال داده نمی‌شود.")
    nwin = news_window if news_window is not None else (news_status_from_file(now) or {"unknown": True})
    if nwin.get("unknown"):
        no_trade.append("فایل پنجره‌های خبری خوانده نشد و بدون آن سیگنال داده نمی‌شود.")
    if nwin.get("inside") and nwin.get("action") == "block":
        no_trade.append("اکنون داخل پنجره‌ی خبری هستیم و ورود ممنوع است.")
    if nwin.get("soon_block"):
        no_trade.append("پنجره‌ی خبری بعدی خیلی نزدیک است و ورود جدید ممنوع است.")

    # 3. a setup must exist
    if side not in DM.SIDES:
        no_trade.append("ستاپ تأییدشده‌ای وجود ندارد.")

    # 4. data quality
    if not data_ok:
        reject.append("داده‌ی قیمت معتبر نیست.")
    elif data_age_min is None or float(data_age_min) > max_data_age_min:
        reject.append(f"داده‌ی قیمت تازه نیست (بیش از {_fa(max_data_age_min, 0)} دقیقه گذشته است).")

    # 5. costs, net R:R (fee once, market spread) and stop-out proximity; any failure here rejects
    if side in DM.SIDES:
        r, w, mm = cost_checks(side, entry, sl, tp, unit, order_type, spread_usd, min_net_rr, stopout_safety, stopout_warn)
        reject += r; warn += w; m.update(mm)

    if no_trade:
        status = NO_TRADE
    elif reject:
        status = REJECTED
    elif warn:
        status = APPROVED_WITH_WARNING
    else:
        status = APPROVED
    return {"status": status, "approved": status in (APPROVED, APPROVED_WITH_WARNING),
            "reasons_fa": no_trade + reject, "warnings_fa": warn, "metrics": m,
            "at": now.strftime("%Y-%m-%d %H:%M") if isinstance(now, datetime) else None}


def cost_checks(side, entry, sl, tp, unit="1U", order_type="MARKET", spread_usd=None, min_net_rr=MIN_NET_RR,
                stopout_safety=0.25, stopout_warn=0.5):
    """(reject_reasons_fa, warnings_fa, metrics) for net R:R after costs (fee once, spread) and stop-out."""
    reject, warn, m = [], [], {}
    try:
        econ = DM.trade_economics(side, entry, sl, tp, unit, order_type, DM.DEFAULT_FEE_SCENARIO, spread_usd)
        alt = DM.trade_economics(side, entry, sl, tp, unit, order_type, DM.FEE_ENTRY_AND_EXIT, spread_usd)
        econ["scenarios"] = {DM.FEE_ONCE: econ, DM.FEE_ENTRY_AND_EXIT: alt}   # per-side case: reported, not gated
        so = DM.stop_out_check(side, entry, sl, unit, order_type, spread_usd, stopout_safety, stopout_warn)
        m.update(net_rr=econ["net_rr"], risk_toman=econ["risk_toman"], reward_toman=econ["reward_toman"],
                 fee_scenario=econ["fee_scenario"], unit=econ["unit"], order_type=econ["order_type"],
                 stop_out=so, scenarios={k: v["net_rr"] for k, v in econ["scenarios"].items()})
        if econ["net_rr"] is None or econ["net_rr"] < min_net_rr:
            reject.append(f"نسبت سود به ضرر خالص بعد از کارمزد و اسپرد {_fa(econ['net_rr'] or 0)} است "
                          f"(حداقل {_fa(min_net_rr)}).")
        if so["status"] == "REJECT":
            reject.append(f"حد ضرر به حراج (استاپ‌اوت) خیلی نزدیک است: ضرر در حد ضرر "
                          f"{_fa(so['ratio'] * 100, 0)}٪ ضرر حراج است.")
        elif so["status"] == "WARN":
            warn.append(f"ضرر در حد ضرر {_fa(so['ratio'] * 100, 0)}٪ ضرر حراج (استاپ‌اوت) است.")
    except Exception as e:
        reject.append("محاسبه‌ی ریسک ممکن نشد؛ سیگنال رد شد.")
        m["error"] = f"{type(e).__name__}: {e}"
    return reject, warn, m
