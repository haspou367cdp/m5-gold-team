"""Risk guards for pending-limit signals (not backtested; approved 2026-11-20 as hard vetoes).

1. An expired signal is never shown or re-armed (it becomes NO TRADE).
2. Min stop: max($1, structure+$0.5, 0.5×M5 ATR14). Never shrink; if it does not fit the
   size/risk cap, return NO TRADE.
3. Pending limit: entry within 1×M5 ATR and at most $5 of the current price. Expiry at most
   30 min, cut before A/B news and the daily close. Veto if entry is beyond the setup's
   invalidation (e.g. a short above the M15 neutralisation level).
4. TP distance at most min(remaining ADR, 3×M5 ATR) and at a mapped level. Net R:R > 5 warns;
   > 8 is rejected.
5. Stop-out buffer: SL distance + 1×M5 ATR <= 50% of the move to stop-out (~$10 for both sizes).
6. Displayed risk for a LIMIT uses the card's 1-decimal DaryaGold prices: sl×toman_per_usd + fee
   once, no spread.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import darya_model as DM

TEH = ZoneInfo("Asia/Tehran")
MAX_LIMIT_USD = 5.0
MAX_EXPIRY_MIN = 30
RR_WARN = 5.0
RR_REJECT = 8.0
STOP_OUT_BUFFER = 0.5  # fraction of the stop-out distance
MIN_SL_USD = 1.0
STRUCTURE_PAD_USD = 0.5
ATR_STOP_MULT = 0.5


def min_stop_usd(entry, structure, atr_m5, min_sl=MIN_SL_USD, structure_pad=STRUCTURE_PAD_USD,
                 atr_mult=ATR_STOP_MULT):
    """Minimum SL *distance* from entry: max($1, |entry-(structure±pad)|, 0.5×ATR)."""
    atr = max(0.0, float(atr_m5 or 0.0))
    parts = [float(min_sl), atr_mult * atr]
    if structure is not None:
        parts.append(abs(float(entry) - float(structure)) + float(structure_pad))
    return max(parts)


def sl_price(side, entry, structure, atr_m5, **kw):
    """SL price using the minimum stop; never tighter than that floor."""
    entry = float(entry)
    dist = min_stop_usd(entry, structure, atr_m5, **kw)
    return round(entry + dist, 2) if side == "SELL" else round(entry - dist, 2)


def pending_limit_reasons(side, entry, price, atr_m5, invalidation=None):
    """Reasons to veto a pending limit, or []."""
    why = []
    entry, price = float(entry), float(price)
    atr = max(0.0, float(atr_m5 or 0.0))
    dist = abs(entry - price)
    cap = min(atr if atr else MAX_LIMIT_USD, MAX_LIMIT_USD)
    if dist > cap + 1e-9:
        why.append(f"سفارش محدود {dist:.1f} دلار از قیمت فاصله دارد "
                   f"(حداکثر {cap:.1f} دلار: کمتر از ۱ برابر ATR پنج‌دقیقه و ۵ دلار).")
    if invalidation is not None:
        inv = float(invalidation)
        if side == "SELL" and entry > inv + 1e-9:
            why.append(f"ورود {entry:.1f} بالاتر از سطح ابطال M15 ({inv:.1f}) است.")
        if side == "BUY" and entry < inv - 1e-9:
            why.append(f"ورود {entry:.1f} پایین‌تر از سطح ابطال M15 ({inv:.1f}) است.")
    return why


def signal_expiry(now, news_window=None, session_close=None, max_minutes=MAX_EXPIRY_MIN):
    """Expiry at most 30 minutes, cut at the next A/B news block and the daily close.
    Never returns a time in the past (caller must not send an already-expired card)."""
    now = now if now.tzinfo else now.replace(tzinfo=TEH)
    exp = now + timedelta(minutes=int(max_minutes))
    nw = news_window or {}
    for key in ("next_start", "start"):
        raw = nw.get(key)
        if not raw:
            continue
        try:
            ns = _parse_teh(raw, now)
        except ValueError:
            continue
        # Only cut for a block window (A/B). A window we are already inside is a gate, not expiry.
        if key == "start" and nw.get("inside"):
            continue
        action = nw.get("soon_action") or nw.get("next_action") or nw.get("action")
        if key == "next_start" and nw.get("next_tier") in ("C", "c"):
            continue
        if key == "next_start" and action and action not in ("block", "soon_block"):
            continue
        if now < ns < exp:
            exp = ns
    if session_close is not None:
        close = session_close if getattr(session_close, "tzinfo", None) else _parse_teh(session_close, now)
        if now < close < exp:
            exp = close
    return exp


def _parse_teh(raw, now):
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=TEH)
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19] if "T" in s and len(s) >= 19 else s, fmt).replace(tzinfo=TEH)
        except ValueError:
            continue
    if len(s) >= 5 and s[-5] == ":":
        # "16:40" or "... 16:40"
        hm = s[-5:]
        h, m = int(hm[:2]), int(hm[3:])
        return now.replace(hour=h, minute=m, second=0, microsecond=0)
    raise ValueError(s)


def is_expired(valid_until, now):
    if valid_until is None:
        return False
    vu = valid_until if isinstance(valid_until, datetime) else datetime.fromisoformat(str(valid_until))
    if vu.tzinfo is None:
        vu = vu.replace(tzinfo=TEH)
    now = now if now.tzinfo else now.replace(tzinfo=TEH)
    return now >= vu


def tp_reasons(entry, tp, atr_m5, remaining_adr, mapped=True):
    why = []
    if tp is None:
        why.append("حد سود روی یک سطح مشخص قرار نگرفته است.")
        return why
    if not mapped:
        why.append("حد سود باید روی یک سطح نقشه‌شده باشد.")
    dist = abs(float(tp) - float(entry))
    atr = max(0.0, float(atr_m5 or 0.0))
    cap_parts = []
    if atr:
        cap_parts.append(3.0 * atr)
    if remaining_adr is not None and float(remaining_adr) >= 0:
        cap_parts.append(float(remaining_adr))
    if cap_parts and dist > min(cap_parts) + 1e-9:
        cap = min(cap_parts)
        why.append(f"فاصله‌ی حد سود {dist:.1f} دلار از سقف {cap:.1f} دلار "
                   f"(کمینه‌ی ADR باقی‌مانده و ۳ برابر ATR پنج‌دقیقه) بیشتر است.")
    return why


def rr_status(net_rr):
    if net_rr is None:
        return "reject", "نسبت سود به ضرر خالص در دسترس نیست."
    rr = float(net_rr)
    if rr > RR_REJECT:
        return "reject", f"نسبت سود به ضرر خالص {rr:.1f} است (بالای ۸ رد می‌شود)."
    if rr > RR_WARN:
        return "warn", f"نسبت سود به ضرر خالص {rr:.1f} است (بالای ۵؛ ستاپ را دوباره بررسی کن)."
    return "ok", None


def stop_out_buffer_ok(sl_usd, atr_m5, unit="1U"):
    """True when (SL distance + 1×ATR) stays within 50% of the move to stop-out."""
    u = DM.unit(unit)
    so_usd = u["stop_out_loss"] / u["toman_per_usd"]  # ~$10 for both sizes
    used = float(sl_usd) + max(0.0, float(atr_m5 or 0.0))
    cap = STOP_OUT_BUFFER * so_usd
    return used <= cap + 1e-9, used, cap, so_usd


def remaining_adr(lv):
    st = (lv or {}).get("structure") or lv or {}
    adr = st.get("adr")
    used = st.get("today_range")
    if adr is None:
        return None
    if used is None:
        pct = st.get("adr_used_pct")
        if pct is None:
            return float(adr)
        return max(0.0, float(adr) * (1.0 - float(pct) / 100.0))
    return max(0.0, float(adr) - float(used))


def display_prices(entry, sl, tp, cfg, to_broker):
    """1-decimal DaryaGold prices exactly as printed on the card."""
    def one(p):
        if p is None:
            return None
        dg = to_broker(float(p), cfg)
        return None if dg is None else round(float(dg), 1)
    return one(entry), one(sl), one(tp)


def limit_economics(side, entry_dg, sl_dg, tp_dg, unit="1U"):
    """Risk/reward on the card prices for a LIMIT (fee once, no spread)."""
    return DM.trade_economics(side, entry_dg, sl_dg, tp_dg, unit, order_type="LIMIT",
                              fee_scenario=DM.FEE_ONCE, spread_usd=None)


def evaluate(side, entry, sl, tp, *, price, atr_m5, remaining_adr_usd=None, structure=None,
             invalidation=None, mapped_tp=True, unit="1U", net_rr=None):
    """Run guards 2–5. Returns {ok, reasons_fa, warnings_fa, metrics}."""
    reasons, warnings, m = [], [], {}
    entry, sl = float(entry), float(sl)
    sl_usd = abs(entry - sl)
    floor = min_stop_usd(entry, structure, atr_m5)
    m["min_stop_usd"] = round(floor, 2)
    m["sl_usd"] = round(sl_usd, 2)
    if sl_usd + 1e-9 < floor:
        reasons.append(f"حد ضرر {sl_usd:.1f} دلار از حداقل {floor:.1f} دلار تنگ‌تر است "
                       f"(حداکثرِ ۱ دلار، ساختار به‌علاوه‌ی ۰٫۵ دلار، و ۰٫۵ برابر ATR پنج‌دقیقه)؛ "
                       f"حد ضرر جمع نمی‌شود.")
    reasons += pending_limit_reasons(side, entry, price, atr_m5, invalidation)
    reasons += tp_reasons(entry, tp, atr_m5, remaining_adr_usd, mapped=mapped_tp)
    ok_buf, used, cap, so = stop_out_buffer_ok(sl_usd, atr_m5, unit)
    m["stop_out_buffer_usd"] = round(used, 2)
    m["stop_out_cap_usd"] = round(cap, 2)
    m["stop_out_usd"] = round(so, 2)
    if not ok_buf:
        reasons.append(f"حد ضرر به‌علاوه‌ی ATR پنج‌دقیقه ({used:.1f} دلار) از نیمی از فاصله تا حراج "
                       f"({cap:.1f} دلار از {so:.1f} دلار) بیشتر است.")
    st, msg = rr_status(net_rr)
    if st == "reject":
        reasons.append(msg)
    elif st == "warn":
        warnings.append(msg)
    return {"ok": not reasons, "reasons_fa": reasons, "warnings_fa": warnings, "metrics": m}
