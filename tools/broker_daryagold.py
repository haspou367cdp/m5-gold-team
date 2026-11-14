#!/usr/bin/env python3
"""DaryaGold adapter: config, price offset, unit sizing, news/weekend gates.

Prices from Dukascopy stay in bid space for engines. Display conversion is
    daryagold ≈ bid + price_offset_usd
(calibrated; uncertainty is price_offset_uncertainty_usd).
Signal-only research. Not financial advice. Never places trades.
"""
from __future__ import annotations

import copy
import csv
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from m5lib import NEWS_JSON, NY, ROOT, TEH, TOOLS, UTC, load_json

CONFIG_PATH = f"{TOOLS}/broker_daryagold.json"
SIZE_ORDER = ("full_unit", "half_unit")  # try largest first


def load_config(equity=None):
    """Load broker_daryagold.json. equity override: arg, then EQUITY_TOMAN, then file."""
    cfg = load_json(CONFIG_PATH, {}) or {}
    if not cfg:
        raise FileNotFoundError(f"missing broker config: {CONFIG_PATH}")
    if equity is None:
        env = os.environ.get("EQUITY_TOMAN")
        if env is not None and str(env).strip() != "":
            equity = env
    if equity is not None:
        cfg = dict(cfg)
        cfg["equity_toman"] = float(equity)
    cfg["equity_toman"] = float(cfg["equity_toman"])
    off = os.environ.get("DG_OFFSET_USD")   # live recalibration (bot_state dg_offset via bot.py, /offset in Telegram)
    if off not in (None, ""):
        try:
            v = float(off)
            if abs(v) <= 5:
                cfg = dict(cfg)
                cfg["price_offset_usd"] = v
        except ValueError:
            pass
    return cfg


def offset_usd(cfg):
    off = cfg.get("price_offset_usd")
    return None if off is None else float(off)


def to_broker(price, cfg):
    """DaryaGold price from a Dukascopy bid. None offset => uncalibrated, return bid."""
    if price is None:
        return None
    off = offset_usd(cfg)
    p = float(price)
    return p if off is None else p + off


def fa_digits(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _n(x, nd=2):
    s = f"{float(x):.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def toman(n):
    """Integer toman with Iranian thousands separator."""
    v = int(round(float(n)))
    sign = "−" if v < 0 else ""
    return sign + f"{abs(v):,}".replace(",", "٬")


def pct_of(part, whole, nd=1):
    if not whole:
        return "—"
    return f"{(100.0 * float(part) / float(whole)):.{nd}f}".rstrip("0").rstrip(".")


def fmt_px(price, cfg, with_bid=True, nd=2):
    """DaryaGold-adjusted price with raw Dukascopy bid in brackets when calibrated."""
    if price is None:
        return "—"
    p = float(price)
    off = offset_usd(cfg)
    if off is None:
        return _n(p, nd)
    broker = p + off
    if with_bid:
        return f"{_n(broker, nd)} (bid {_n(p, nd)})"
    return _n(broker, nd)


def fmt_hl(block, cfg, nd=2):
    if not block or block.get("high") is None:
        return "در دسترس نیست"
    extra = " (ناقص)" if block.get("incomplete") else ""
    return f"{fmt_px(block['high'], cfg, nd=nd)} / {fmt_px(block['low'], cfg, nd=nd)}{extra}"


def calibrated(cfg):
    return offset_usd(cfg) is not None


def price_convention_fa(cfg):
    off = offset_usd(cfg)
    unc = cfg.get("price_offset_uncertainty_usd")
    when = cfg.get("calibrated_at") or ""
    if off is None:
        return ("قیمت‌ها bid دوکاسکوپی هستند؛ افست دریاگلد هنوز کالیبره نشده. "
                "قبل از هر ورود، عدد را روی نمودار دریاگلد تطبیق بده.")
    unc_s = f"عدم قطعیت حدود ±{_n(unc)} دلار" if unc is not None else "عدم قطعیت اعلام نشده"
    cal = f"، کالیبره {when}" if when else ""
    return (f"قیمت‌های دریاگلد = bid دوکاسکوپی + {_n(off)} دلار ({unc_s}{cal}). "
            "اعداد داخل پرانتز bid خام هستند.")


def _sizes(cfg):
    raw = cfg.get("sizes") or {}
    out = []
    for key in SIZE_ORDER:
        block = raw.get(key)
        if not block:
            continue
        item = dict(block)
        item["key"] = key
        out.append(item)
    return out


def _spread_cost_usd(cfg, spread_usd=None):
    if spread_usd is not None:
        try:
            return max(0.0, float(spread_usd))
        except (TypeError, ValueError):
            pass
    return float(cfg.get("typical_spread_usd") or 0.0)


def evaluate_size(size, sl_usd, tp_usd, cfg, spread_usd=None):
    """Risk/reward in toman for one unit size. Returns a dict (ok may still be False)."""
    equity = float(cfg["equity_toman"])
    tpu = float(size["toman_per_usd"])
    fee = float(size["fee"])
    margin = float(size["margin"])
    spread_u = _spread_cost_usd(cfg, spread_usd)
    spread_toman = spread_u * tpu
    risk_toman = sl_usd * tpu + fee + spread_toman
    reward_toman = tp_usd * tpu - fee - spread_toman if tp_usd is not None else None
    budget = equity * float(cfg["risk_per_trade_pct_max"]) / 100.0
    min_rr = float(cfg["min_net_rr"])
    net_rr = None
    reasons = []
    ok = True
    if margin > equity:
        ok = False
        reasons.append(f"وجه تضمین {toman(margin)} تومان از ارزش حساب بیشتر است.")
    if risk_toman > budget + 1e-6:
        ok = False
        reasons.append(
            f"زیان احتمالی {toman(risk_toman)} تومان "
            f"({pct_of(risk_toman, equity)}٪ حساب) از سقف "
            f"{toman(budget)} تومان ({_n(cfg['risk_per_trade_pct_max'], 0)}٪) بیشتر است."
        )
    if reward_toman is not None and risk_toman > 0:
        net_rr = reward_toman / risk_toman
        if net_rr < min_rr:
            ok = False
            reasons.append(
                f"نسبت سود به ضرر خالص بعد از کارمزد و اسپرد {net_rr:.2f} است "
                f"(حداقل { _n(min_rr) })."
            )
    elif tp_usd is None:
        ok = False
        reasons.append("حد سود عددی برای محاسبه نسبت خالص در دسترس نیست.")
    return {
        "ok": ok,
        "key": size.get("key"),
        "label_fa": size.get("label_fa") or size.get("key"),
        "margin": margin,
        "toman_per_usd": tpu,
        "fee": fee,
        "fee_unconfirmed": bool(size.get("fee_unconfirmed")),
        "spread_usd": spread_u,
        "spread_toman": spread_toman,
        "risk_toman": risk_toman,
        "reward_toman": reward_toman,
        "risk_pct": (100.0 * risk_toman / equity) if equity else None,
        "reward_pct": (100.0 * reward_toman / equity) if (equity and reward_toman is not None) else None,
        "net_rr": None if net_rr is None else round(net_rr, 2),
        "budget_toman": budget,
        "reasons": reasons,
    }


def size_trade(entry, sl, tp, side, cfg, spread_usd=None):
    """Pick the largest unit (full, else half) that fits the risk budget.

    Loss at SL includes fee and a conservative spread cost (typical or current),
    even though a limit order itself has no entry spread.
    If even the half unit exceeds the budget, or SL < min_sl_usd, returns ok=False.
    """
    if entry is None or sl is None:
        return {"ok": False, "decision": "NO TRADE",
                "reason_fa": "ورود یا حد ضرر عددی در دسترس نیست.", "size": None}
    entry, sl = float(entry), float(sl)
    tp_v = None if tp is None else float(tp)
    sl_usd = abs(entry - sl)
    tp_usd = None if tp_v is None else abs(tp_v - entry)
    min_sl = float(cfg.get("min_sl_usd") or 0)
    if sl_usd + 1e-9 < min_sl:
        return {
            "ok": False, "decision": "NO TRADE", "size": None,
            "sl_usd": sl_usd, "tp_usd": tp_usd,
            "reason_fa": (
                f"فاصله حد ضرر {_n(sl_usd)} دلار از حداقل {_n(min_sl)} دلار کمتر است "
                "(بروکر حد ضرر خیلی نزدیک را شناسایی می‌کند)."
            ),
        }
    tried, chosen = [], None
    for size in _sizes(cfg):
        ev = evaluate_size(size, sl_usd, tp_usd, cfg, spread_usd=spread_usd)
        tried.append(ev)
        if ev["ok"] and chosen is None:
            chosen = ev
    if chosen:
        return {
            "ok": True, "decision": "APPROVED", "size": chosen, "tried": tried,
            "sl_usd": sl_usd, "tp_usd": tp_usd,
            "entry": entry, "sl": sl, "tp": tp_v, "side": side,
            "reason_fa": (
                f"حجم {chosen['label_fa']} تأیید شد: ریسک {toman(chosen['risk_toman'])} تومان "
                f"({pct_of(chosen['risk_toman'], cfg['equity_toman'])}٪ حساب)، "
                f"پاداش {toman(chosen['reward_toman'])} تومان "
                f"({pct_of(chosen['reward_toman'], cfg['equity_toman'])}٪)، "
                f"نسبت خالص {chosen['net_rr']}."
            ),
        }
    half = next((t for t in tried if t.get("key") == "half_unit"), tried[-1] if tried else None)
    why = "حتی نیم واحدی از بودجه ریسک یا نسبت خالص عبور می‌کند."
    if half and half.get("reasons"):
        why = " ".join(half["reasons"])
    return {
        "ok": False, "decision": "NO TRADE", "size": None, "tried": tried,
        "sl_usd": sl_usd, "tp_usd": tp_usd,
        "entry": entry, "sl": sl, "tp": tp_v, "side": side,
        "reason_fa": why,
    }


def _level_prices(lv, side):
    prices = []
    for l in lv.get("levels") or []:
        if l.get("side") == side and l.get("strength") in ("strong", "medium") and l.get("price") is not None:
            prices.append(float(l["price"]))
    ses = lv.get("sessions") or {}
    ors = lv.get("opening_ranges") or {}
    key = "low" if side == "support" else "high"
    for block in list(ses.values()) + list(ors.values()):
        if block and block.get(key) is not None:
            prices.append(float(block[key]))
    return sorted(set(prices))


def plan_from_setup(setup, lv, cfg):
    """Build a numeric plan (bid space) from an engine setup, or None."""
    if not setup or setup.get("side") not in ("BUY", "SELL"):
        return None
    side = setup["side"]
    price = float(lv["price_bid"])
    atr = float(lv.get("atr_m5_14") or 0) or 1.0
    ref = float(setup["ref_price"]) if setup.get("ref_price") is not None else price
    extreme = setup.get("extreme")
    entry = ref
    pad = max(float(cfg.get("min_sl_usd") or 1.0), float(cfg.get("min_sl_beyond_structure_usd") or 0.5),
              min(2.0, 0.35 * atr))
    if side == "SELL":
        anchor = max(ref, float(extreme) if extreme is not None else ref)
        sl = max(anchor + pad, entry + float(cfg.get("min_sl_usd") or 1.0))
        targets = [p for p in _level_prices(lv, "support") if p < entry]
        targets.sort(reverse=True)
    else:
        anchor = min(ref, float(extreme) if extreme is not None else ref)
        sl = min(anchor - pad, entry - float(cfg.get("min_sl_usd") or 1.0))
        targets = [p for p in _level_prices(lv, "resistance") if p > entry]
        targets.sort()
    sl_usd = abs(entry - sl)
    # smallest size sets the minimum TP distance that can still clear net R:R
    half = (cfg.get("sizes") or {}).get("half_unit") or {}
    ev_floor = evaluate_size(
        {**half, "key": "half_unit"}, sl_usd, sl_usd * 10, cfg
    )  # dummy wide TP to get risk only
    risk = ev_floor["risk_toman"]
    tpu = float(half.get("toman_per_usd") or 40000)
    fee = float(half.get("fee") or 14000)
    spread_t = _spread_cost_usd(cfg) * tpu
    min_reward = float(cfg.get("min_net_rr") or 1.5) * risk
    min_tp = (min_reward + fee + spread_t) / tpu if tpu else sl_usd * 2
    tp = None
    for p in targets:
        if abs(p - entry) + 1e-9 >= min_tp:
            tp = p
            break
    return {
        "side": side,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp": None if tp is None else round(tp, 2),
        "entry_type": cfg.get("entry_type") or "order (limit, no spread)",
        "source": "setup",
        "unvalidated": True,
    }


def inferred_event_time(start, end, tier, fomc=False):
    """Delegates to news_windows.py (single source of truth for window semantics)."""
    import news_windows as _nw
    return _nw.inferred_event_time(start, end, tier, fomc=fomc)


def effective_bounds(start, end, tier, fomc=False, cfg=None):
    """Union of the stored window and the DaryaGold floor buffers. Never shrinks."""
    import news_windows as _nw
    cfg = cfg or load_config()
    return _nw.effective_bounds(start, end, tier, fomc=fomc, floors=cfg.get("news_buffers") or {})


def expand_news_doc(doc, cfg=None):
    """Copy of news_windows.json with start/end widened to effective floors (in memory only)."""
    import news_windows as _nw
    cfg = cfg or load_config()
    return _nw.effective_doc(copy.deepcopy(doc or {}), floors=cfg.get("news_buffers") or {})


def _hm(s, default="17:00"):
    raw = str(s if s is not None else default)
    parts = raw.split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def session_cfg(cfg=None):
    """DaryaGold session = forex hours, times from broker_daryagold.json (DST via NY)."""
    cfg = cfg or load_config()
    s = cfg.get("session") or {}
    hours = s.get("no_new_entries_hours_before_friday_close")
    if hours is None:
        hours = cfg.get("friday_close_no_entry_hours") or 2
    return {
        "tz": ZoneInfo(s.get("timezone") or "America/New_York"),
        "open_day": int(s.get("open_day", 6)),
        "open": _hm(s.get("open"), "18:00"),
        "close_day": int(s.get("close_day", 4)),
        "close": _hm(s.get("close"), "17:00"),
        "break_start": _hm(s.get("daily_break_start"), "17:00"),
        "break_end": _hm(s.get("daily_break_end"), "18:00"),
        "hours": float(hours),
    }


def forex_open(now=None, cfg=None):
    """True while the forex/gold session is open (Sun 18:00 NY to Fri 17:00 NY, daily break excluded)."""
    sc = session_cfg(cfg)
    t = now or datetime.now(UTC)
    if t.tzinfo is None:
        t = t.replace(tzinfo=TEH)
    n = t.astimezone(sc["tz"])
    wd, hm = n.weekday(), n.hour * 60 + n.minute
    oh, om = sc["open"]
    ch, cm = sc["close"]
    bh, bm = sc["break_start"]
    eh, em = sc["break_end"]
    if wd == 5:
        return False
    if wd == sc["open_day"]:
        return hm >= oh * 60 + om
    if wd == sc["close_day"]:
        return hm < ch * 60 + cm
    return not (bh * 60 + bm <= hm < eh * 60 + em)


def _friday_close_ny(now, sc):
    n = now.astimezone(sc["tz"])
    ch, cm = sc["close"]
    return (n + timedelta(days=(sc["close_day"] - n.weekday()))).replace(
        hour=ch, minute=cm, second=0, microsecond=0
    )


def session_entry_block(now=None, cfg=None):
    """No new entries outside forex hours, or in the last N hours before Friday 17:00 NY close.

    Overnight weekday holds are allowed. There is no daily 22:30/00:30 cutoff.
    Friday close and the entry cutoff are DST-aware (computed in America/New_York).
    """
    cfg = cfg or load_config()
    sc = session_cfg(cfg)
    t = now or datetime.now(UTC)
    if t.tzinfo is None:
        t = t.replace(tzinfo=TEH)
    n = t.astimezone(sc["tz"])
    teh = n.astimezone(TEH)
    hours = sc["hours"]
    close = _friday_close_ny(t, sc)
    start = close - timedelta(hours=hours)
    in_friday_window = start <= n < close
    is_open = forex_open(t, cfg)
    blocked = (not is_open) or in_friday_window
    close_teh = close.astimezone(TEH)
    start_teh = start.astimezone(TEH)
    start_fa, close_fa, close_ny_fa = (fa_digits(x.strftime("%H:%M")) for x in (start_teh, close_teh, close))
    if in_friday_window:
        reason = (
            f"فقط جمعه: از {start_fa} تهران ورود جدید ممنوع است "
            f"و همه معاملات باید پیش از بسته شدن فارکس "
            f"({close_ny_fa} نیویورک / {close_fa} تهران) بسته شوند. "
            "تصمیم: NO TRADE."
        )
    elif not is_open:
        reason = (
            "بازار دریاگلد خارج از ساعت فارکس است "
            "(ساعت کاری برابر فارکس: از دوشنبه تا جمعه، شنبه و یکشنبه تعطیل). "
            "تصمیم: NO TRADE."
        )
    else:
        reason = (
            f"ورود جدید از {start_fa} تهران جمعه تا بسته شدن فارکس "
            f"({close_fa} تهران / {close_ny_fa} نیویورک) ممنوع است. "
            "نگهداری شبانه در روزهای هفته مجاز است."
        )
    return {
        "blocked": blocked,
        "hours": hours,
        "forex_open": is_open,
        "friday_window": in_friday_window,
        "close_tehran": close_teh.strftime("%Y-%m-%d %H:%M"),
        "block_start_tehran": start_teh.strftime("%Y-%m-%d %H:%M"),
        "close_ny": close.strftime("%Y-%m-%d %H:%M"),
        "now_tehran": teh.strftime("%Y-%m-%d %H:%M"),
        "reason_fa": reason,
        "hours_line_fa": (
            f"ساعت کاری دریاگلد برابر ساعت فارکس است (از دوشنبه تا جمعه، شنبه و یکشنبه تعطیل). "
            f"نگهداری شبانه در روزهای هفته مجاز است و قطع روزانه ۲۲:۳۰/۰۰:۳۰ وجود ندارد. "
            f"فقط جمعه: از {start_fa} تهران ورود جدید نیست و همه معاملات باید "
            f"پیش از {close_fa} تهران "
            f"(بسته شدن فارکس، {close_ny_fa} نیویورک، با احتساب تغییر ساعت) بسته شوند."
        ),
    }


def friday_close_block(now=None, cfg=None):
    """Back-compat alias for session_entry_block."""
    return session_entry_block(now, cfg)


def journal_today(cfg=None):
    """Closed-loss count for today from journal.csv (best-effort)."""
    path = f"{ROOT}/journal.csv"
    today = datetime.now(TEH).strftime("%Y-%m-%d")
    if not os.path.exists(path):
        return {"losses": 0, "note_fa": "در ژورنال معامله‌ی بسته‌شده‌ای برای امروز دیده نشد.", "path": path}
    losses = 0
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = (row.get("signal_time_tehran") or row.get("logged_at_tehran") or "")[:10]
                if t != today:
                    continue
                status = (row.get("status") or "").lower()
                outcome = (row.get("outcome") or "").lower()
                if "reject" in status or "arm" in status or "cancel" in status:
                    continue
                r = row.get("result_R") or ""
                try:
                    r_f = float(r)
                except (TypeError, ValueError):
                    r_f = None
                if outcome in ("loss", "sl", "stopped", "lose") or (r_f is not None and r_f < 0):
                    losses += 1
    except Exception:
        return {"losses": None, "note_fa": "خواندن ژورنال امروز ممکن نشد.", "path": path}
    if losses:
        note = f"در ژورنال امروز {losses} ضرر بسته‌شده ثبت شده است."
    else:
        note = "در ژورنال معامله‌ی بسته‌شده‌ای برای امروز دیده نشد."
    return {"losses": losses, "note_fa": note, "path": path}


def daily_loss_veto(cfg):
    j = journal_today(cfg)
    cap = int(cfg.get("max_consecutive_losses") or 3)
    if j.get("losses") is not None and j["losses"] >= cap:
        return True, (
            f"توقف روزانه: {j['losses']} ضرر بسته‌شده امروز به سقف {cap} ضرر رسید. "
            "تا روز معاملاتی بعد ورود جدید ممنوع است."
        ), j
    return False, None, j


def hold_rules_fa(cfg):
    sec = int(cfg.get("min_hold_seconds") or 60)
    return (f"حداقل نگهداری معامله {sec} ثانیه است (بستن دستی و حد سود؛ حد ضرر و حراج مستثنی‌اند). "
            "نگهداری شبانه در روزهای هفته مجاز است. "
            "معامله را روی تعطیلی آخر هفته یا تعطیلات رسمی ایران باز نگذار؛ "
            "پلتفرم ممکن است در تعطیلات رسمی ایران بسته شود.")


def fa_risk_lines(cfg, spread=None, sizing=None, friday=None):
    """Standing DaryaGold risk block printed on every brief."""
    equity = float(cfg["equity_toman"])
    risk_pct = float(cfg["risk_per_trade_pct_max"])
    day_pct = float(cfg["daily_loss_pct_max"])
    budget = equity * risk_pct / 100.0
    day_budget = equity * day_pct / 100.0
    sp = spread or {}
    cur, typ = sp.get("current"), sp.get("typical_this_hour")
    cur_s = f"{cur:.2f}" if isinstance(cur, (int, float)) else "نامعلوم"
    typ_s = f"{typ:.2f}" if isinstance(typ, (int, float)) else "نامعلوم"
    flag = " — الان غیرعادی است، ورود ممنوع" if sp.get("abnormal") else ""
    known = "" if sp.get("known") is not False else " (اسپرد در این منبع موجود نیست)"
    half = (cfg.get("sizes") or {}).get("half_unit") or {}
    full = (cfg.get("sizes") or {}).get("full_unit") or {}
    fee_note = (f" کارمزد هر معامله برای نیم واحدی و یک واحد "
                f"{toman(half.get('fee') or 14000)} تومان است (تأیید مالک، 2026-11-13).")
    _, _, j = daily_loss_veto(cfg)
    fri = friday or session_entry_block(cfg=cfg)
    liq = int(cfg.get("liquidation_pct") or 80)
    lines = (
        f"**دروازه‌های ریسک (دریاگلد، ارزش حساب {toman(equity)} تومان، "
        f"سقف ریسک هر معامله { _n(risk_pct, 0)}٪ = {toman(budget)} تومان، "
        f"سقف ضرر روزانه { _n(day_pct, 0)}٪ = {toman(day_budget)} تومان):** "
        f"حجم فقط «نیم واحدی» (وجه تضمین {toman(half.get('margin') or 500000)}، "
        f"هر ۱ دلار {toman(half.get('toman_per_usd') or 40000)}) یا «یک واحد» "
        f"(وجه تضمین {toman(full.get('margin') or 1000000)}، "
        f"هر ۱ دلار {toman(full.get('toman_per_usd') or 80000)})؛ "
        f"بزرگ‌ترین حجمی انتخاب می‌شود که زیان حد ضرر + کارمزد + هزینه اسپرد از بودجه ریسک بیشتر نشود. "
        f"ورود ترجیحاً با اوردر (حد، بدون اسپرد). "
        f"حد ضرر حداقل {_n(cfg.get('min_sl_usd') or 1)} دلار. "
        f"نسبت سود به ضرر خالص بعد از کارمزد و اسپرد حداقل {_n(cfg.get('min_net_rr') or 1.5)}. "
        f"حداکثر {cfg.get('max_positions') or 1} پوزیشن باز. "
        f"توقف روز بعد از {cfg.get('max_consecutive_losses') or 3} ضرر یا {toman(day_budget)} تومان ضرر. "
        f"حراج وقتی {liq}٪ کل پرتفو درگیر زیان شود. "
        f"اسپرد فعلی {cur_s} دلار / معمول این ساعت {typ_s} دلار "
        f"(حد: بیشتر از ۲ برابر معمول همین ساعت و هم‌زمان بالاتر از ۰٫۸۰ دلار → ورود ممنوع)"
        f"{flag}{known}.{fee_note} "
        + (j.get("note_fa") or "")
    )
    extra = [lines, fri.get("hours_line_fa") or "", hold_rules_fa(cfg)]
    extra = [x for x in extra if x]
    if fri.get("blocked"):
        extra.append("⚠️ " + fri["reason_fa"])
    if sizing and sizing.get("reason_fa"):
        if sizing.get("ok"):
            extra.append("**حجم طرح:** " + sizing["reason_fa"])
        else:
            extra.append("**وتوی ریسک:** " + sizing["reason_fa"])
    return extra


def fa_plan_lines(plan, sizing, cfg):
    """Persian lines for a numeric plan in DaryaGold prices (bid in brackets)."""
    if not plan:
        return []
    side_fa = "خرید" if plan["side"] == "BUY" else "فروش"
    lines = [
        f"**طرح معامله (تأییدنشده، دریاگلد، ورود با اوردر):** {side_fa} · "
        f"ورود {fmt_px(plan['entry'], cfg)} · "
        f"حد ضرر {fmt_px(plan['sl'], cfg)} "
        f"(فاصله {_n(abs(plan['entry'] - plan['sl']))} دلار) · "
        + (f"حد سود {fmt_px(plan['tp'], cfg)} (فاصله {_n(abs(plan['tp'] - plan['entry']))} دلار)"
           if plan.get("tp") is not None else "حد سود ساختاری کافی دیده نشد")
    ]
    if sizing and sizing.get("size"):
        s = sizing["size"]
        lines.append(
            f"**ریسک/پاداش:** حجم {s['label_fa']} · "
            f"ریسک {toman(s['risk_toman'])} تومان ({pct_of(s['risk_toman'], cfg['equity_toman'])}٪ حساب) · "
            f"پاداش {toman(s['reward_toman'])} تومان ({pct_of(s['reward_toman'], cfg['equity_toman'])}٪ حساب) · "
            f"نسبت خالص {s['net_rr']} · "
            f"وجه تضمین {toman(s['margin'])} تومان "
            f"({'قبول' if s['margin'] <= cfg['equity_toman'] else 'بیش از ارزش حساب'}) · "
            f"کارمزد {toman(s['fee'])} تومان"
            f" · هزینه اسپرد محافظه‌کارانه {toman(s['spread_toman'])} تومان."
        )
    return lines


if __name__ == "__main__":
    # small self-check (no I/O beyond the config file)
    cfg = load_config()
    assert cfg["price_offset_usd"] == 0.3
    assert cfg["sizes"]["half_unit"]["fee"] == 14000
    assert cfg["sizes"]["full_unit"]["fee"] == 14000
    assert cfg["sizes"]["half_unit"].get("fee_unconfirmed") is False
    assert "7000" not in (cfg["sizes"]["half_unit"].get("fee_note") or "")
    assert "unconfirmed" not in (cfg["sizes"]["half_unit"].get("fee_note") or "").lower()
    # full unit should fit a 1.5 USD stop; a very wide stop should drop to half or veto
    s_ok = size_trade(3900, 3901.5, 3894, "SELL", cfg, spread_usd=0.25)
    assert s_ok["ok"], s_ok
    s_wide = size_trade(3900, 3906.0, 3888, "SELL", cfg, spread_usd=0.25)
    # 6 USD * 40000 + 14000 + 10000 = 264000 > 208560 budget → veto half
    assert not s_wide["ok"], s_wide
    s_tight = size_trade(3900, 3900.4, 3890, "SELL", cfg)
    assert not s_tight["ok"] and "حد ضرر" in s_tight["reason_fa"]
    # A 15/15 window should extend after by 15 minutes
    start = datetime(2026, 11, 16, 16, 45, tzinfo=TEH)
    end = datetime(2026, 11, 16, 17, 15, tzinfo=TEH)
    s2, e2 = effective_bounds(start, end, "A", False, cfg)
    assert s2 == start and e2 == datetime(2026, 11, 16, 17, 30, tzinfo=TEH), (s2, e2)
    # B 15/15 already covers the 10/15 floor
    s3, e3 = effective_bounds(start, end, "B", False, cfg)
    assert (s3, e3) == (start, end)
    # Forex hours + Friday window (winter 2026: 17:00 NY = 01:30 Tehran next day)
    wed = datetime(2026, 11, 11, 23, 45, tzinfo=TEH)
    w = session_entry_block(wed, cfg)
    assert not w["blocked"] and w["forex_open"], w
    fri_before = datetime(2026, 11, 13, 23, 0, tzinfo=TEH)
    assert not session_entry_block(fri_before, cfg)["blocked"], session_entry_block(fri_before, cfg)
    fri_cut = datetime(2026, 11, 13, 23, 30, tzinfo=TEH)
    fc = session_entry_block(fri_cut, cfg)
    assert fc["blocked"] and fc["friday_window"] and "NO TRADE" in fc["reason_fa"], fc
    sat_pre_close = datetime(2026, 11, 14, 1, 0, tzinfo=TEH)
    assert session_entry_block(sat_pre_close, cfg)["friday_window"]
    sat_closed = datetime(2026, 11, 14, 12, 0, tzinfo=TEH)
    scb = session_entry_block(sat_closed, cfg)
    assert scb["blocked"] and not scb["forex_open"]
    mon_pre = datetime(2026, 11, 16, 1, 0, tzinfo=TEH)
    assert session_entry_block(mon_pre, cfg)["blocked"]
    mon_open = datetime(2026, 11, 16, 3, 0, tzinfo=TEH)
    assert not session_entry_block(mon_open, cfg)["blocked"]
    # US summer DST: Friday 17:00 NY = 00:30 Tehran Saturday; cutoff 22:30 Tehran Friday
    summer = session_entry_block(datetime(2026, 7, 17, 22, 30, tzinfo=TEH), cfg)
    assert summer["blocked"] and summer["friday_window"], summer
    assert summer["close_tehran"].endswith("00:30"), summer
    print("self-check ok", fmt_px(3886.28, cfg), s_ok["size"]["key"], s_ok["size"]["net_rr"])
