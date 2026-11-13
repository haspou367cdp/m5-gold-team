#!/usr/bin/env python3
"""regime.py - 4-state regime gate, ADX, VWAP deviation, and two unvalidated setup detectors.

States:
  news_abnormal         inside a tier-A block window, or a spread anomaly → no trade
  volatility_expansion  high ATR percentile and/or elevated tick volume → wait
  trend                 directional H4/H1 (ADX as optional confirmation) → continuation engine allowed
  range                 otherwise (tight session range or mixed structure) → sweep / mean-reversion engine allowed

Detectors are heuristics flagged as unvalidated; they do not claim a statistical edge.
See preregistration_engines.md for the separate out-of-sample backtest each engine still needs.
Signal-only research. Not financial advice."""
import sys
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, "/workspace/m5-gold-team/tools")
from m5lib import TEH, load_bars
from levels import atr

FA_SIDE = {"BUY": "خرید", "SELL": "فروش", "NO TRADE": "بدون معامله"}
FA_ENGINE = {
    "continuation": "ادامه روند",
    "sweep_reversion": "جاروی نقدینگی / بازگشت به میانگین",
    None: "هیچ (صبر)",
}

def _wilder(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()

def adx(df, n=14):
    """Wilder ADX(n). Returns None if not enough bars. Optional confirmation only."""
    if df is None or len(df) < 2 * n + 2:
        return None
    up = df.h.diff()
    down = -df.l.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    pc = df.c.shift(1)
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    atr_ = _wilder(tr, n)
    plus_di = 100 * _wilder(plus_dm, n) / atr_.replace(0, np.nan)
    minus_di = 100 * _wilder(minus_dm, n) / atr_.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_s = _wilder(dx, n)
    last = float(adx_s.iloc[-1]) if pd.notna(adx_s.iloc[-1]) else None
    if last is None:
        return None
    return {"adx": round(last, 1), "plus_di": round(float(plus_di.iloc[-1]), 1),
            "minus_di": round(float(minus_di.iloc[-1]), 1), "n": n}

def atr_percentile(df, n=14, lookback=200):
    s = atr(df, n).dropna()
    if s.empty:
        return None
    w = s.iloc[-lookback:]
    cur = float(w.iloc[-1])
    pct = 100.0 * float((w <= cur).mean())
    expanding = bool(len(w) > 6 and cur > float(w.iloc[-6]))
    return {"atr": round(cur, 2), "percentile": round(pct, 1), "expanding": expanding, "lookback_bars": int(len(w))}

def rel_tick_volume(df, lookback=48):
    """Last closed bar tick volume vs the median of the previous `lookback` bars. Tick-volume proxy."""
    col = "v" if "v" in df.columns else None
    if col is None:
        return None
    v = df[col].fillna(0)
    if len(v) < 5:
        return None
    cur = float(v.iloc[-1])
    hist = v.iloc[-lookback-1:-1] if len(v) > lookback + 1 else v.iloc[:-1]
    med = float(hist.median()) if len(hist) else None
    ratio = (cur / med) if (med and med > 0) else None
    return {"current": round(cur, 4), "median": None if med is None else round(med, 4),
            "ratio": None if ratio is None else round(ratio, 2),
            "lookback_bars": int(len(hist)),
            "volume_note": "tick-volume proxy (not exchange volume)"}

def _active_session(lv):
    ses = lv.get("sessions") or {}
    # priority: in-progress NY, else in-progress London, else in-progress Asia, else today
    for key, name in (("ny", "نیویورک"), ("london", "لندن"), ("asia", "آسیا")):
        block = ses.get(key)
        if block and block.get("high") is not None and not block.get("complete"):
            return key, name, block
    # if NY already complete today (after 01:30 Tehran next calendar day this won't run often)
    if ses.get("london") and not ses["london"].get("complete"):
        return "london", "لندن", ses["london"]
    if ses.get("today"):
        return "today", "امروز", ses["today"]
    return None, None, None

def vwap_deviation(lv, price=None):
    """Deviation of last price from the active session VWAP (fallback: trading-day VWAP). Tick-volume proxy."""
    price = float(price if price is not None else lv.get("price_bid") or 0)
    key, name, _ = _active_session(lv)
    block = None
    src = None
    if key and key in (lv.get("session_vwap") or {}):
        block = lv["session_vwap"][key]
        src = f"سشن {name}"
    elif lv.get("vwap"):
        block = lv["vwap"]
        src = "روز معاملاتی"
    if not block or block.get("vwap") is None:
        return None
    vw = float(block["vwap"])
    sd = float(block.get("sd") or 0) or None
    dist = price - vw
    z = (dist / sd) if (sd and sd > 0) else None
    atr_m5 = float(lv.get("atr_m5_14") or 0) or None
    atr_x = (dist / atr_m5) if atr_m5 else None
    return {"vwap": vw, "sd": sd, "distance": round(dist, 2),
            "sigma": None if z is None else round(z, 2),
            "atr_m5_x": None if atr_x is None else round(atr_x, 2),
            "session": key, "session_fa": src,
            "volume_note": "tick-volume proxy (not exchange volume)"}

def classify(lv, win=None, spread=None, h4=None, h1=None, m5=None, h1_df=None, m5_df=None, m15_df=None):
    """Return a 4-state regime dict. Deterministic heuristics, not a forecast."""
    win = win or {}
    spread = spread or {}
    st = lv.get("structure") or {}
    atr_h1 = float(lv.get("atr_h1_14") or 0) or None
    key, sname, sess = _active_session(lv)
    rng = None
    if sess and sess.get("high") is not None and sess.get("low") is not None:
        rng = float(sess["high"]) - float(sess["low"])

    # optional indicators
    if h1_df is None:
        try:
            h1_df = load_bars("h1")
        except Exception:
            h1_df = None
    if m5_df is None:
        try:
            m5_df = load_bars("m5")
        except Exception:
            m5_df = None
    if m15_df is None:
        try:
            m15_df = load_bars("m15")
        except Exception:
            m15_df = None

    adx_h1 = adx(h1_df, 14) if h1_df is not None else None
    adx_m15 = adx(m15_df, 14) if m15_df is not None else None
    atr_pct = atr_percentile(m5_df, 14, 200) if m5_df is not None else None
    rvol = rel_tick_volume(m5_df, 48) if m5_df is not None else None
    vdev = vwap_deviation(lv)

    # --- state 1: news / spread ---
    if win.get("action") == "block" or (win.get("inside") and win.get("tier") == "A"):
        why = f"داخل پنجره‌ی خبری سطح A {win.get('start','')} تا {win.get('end','')}"
        if win.get("labels"):
            why += f" ({' + '.join(win['labels'])})"
        return _pack("news_abnormal", "خبری / غیرعادی", why, None, rng, adx_h1, adx_m15, atr_pct, rvol, vdev)
    if win.get("soon_block") or win.get("soon_action") == "block":
        return _pack("news_abnormal", "خبری / غیرعادی",
                     f"{win.get('minutes_to_next')} دقیقه تا پنجره‌ی خبری سطح A",
                     None, rng, adx_h1, adx_m15, atr_pct, rvol, vdev)
    if spread.get("abnormal"):
        return _pack("news_abnormal", "خبری / غیرعادی",
                     f"اسپرد غیرعادی است ({spread.get('current')} دلار، معمول این ساعت {spread.get('typical_this_hour')})",
                     None, rng, adx_h1, adx_m15, atr_pct, rvol, vdev)

    # --- state 2: volatility expansion ---
    pct = (atr_pct or {}).get("percentile")
    expanding = bool((atr_pct or {}).get("expanding"))
    rv = (rvol or {}).get("ratio")
    exp = False
    exp_why = []
    if pct is not None and pct >= 90:
        exp, exp_why = True, [f"صدک ATR پنج‌دقیقه {pct:.0f}"]
    elif pct is not None and pct >= 80 and (expanding or (rv is not None and rv >= 1.8)):
        exp = True
        exp_why = [f"صدک ATR پنج‌دقیقه {pct:.0f}"]
        if expanding:
            exp_why.append("ATR در حال گسترش")
        if rv is not None and rv >= 1.8:
            exp_why.append(f"حجم تیک نسبی {rv}× (پروکسی)")
    elif rv is not None and rv >= 2.5 and expanding:
        exp, exp_why = True, [f"حجم تیک نسبی {rv}× همراه با گسترش ATR (پروکسی حجم تیک)"]
    if exp:
        return _pack("volatility_expansion", "جهش نوسان", "، ".join(exp_why),
                     None, rng, adx_h1, adx_m15, atr_pct, rvol, vdev)

    # --- state 3/4: trend vs range ---
    d1 = st.get("d1_structure")
    h4_tr = (h4 or {}).get("trend") if isinstance(h4, dict) else None
    h1_tr = (h1 or {}).get("trend") if isinstance(h1, dict) else None
    adx_v = (adx_h1 or {}).get("adx")
    tight = bool(atr_h1 and rng is not None and rng <= 2.5 * atr_h1)
    directional = h4_tr in ("bullish", "bearish") or (h4_tr in (None, "neutral") and h1_tr in ("bullish", "bearish"))
    adx_trendish = adx_v is not None and adx_v >= 25
    adx_rangeish = adx_v is not None and adx_v < 20

    if tight and not adx_trendish:
        why = f"رنج سشن {sname or 'امروز'}" + (f" (دامنه {rng:.1f} دلار)" if rng is not None else "")
        if d1 == "LH/LL":
            why += " داخل روند روزانه نزولی"
        elif d1 == "HH/HL":
            why += " داخل روند روزانه صعودی"
        if adx_v is not None:
            why += f" · ADX(14) H1={adx_v}"
        return _pack("range", "رنج", why, "sweep_reversion", rng, adx_h1, adx_m15, atr_pct, rvol, vdev)

    if directional and (h4_tr in ("bullish", "bearish") or adx_trendish) and not adx_rangeish:
        bits = []
        if h4_tr in ("bullish", "bearish"):
            bits.append("H4 " + ("نزولی" if h4_tr == "bearish" else "صعودی"))
        if h1_tr in ("bullish", "bearish"):
            bits.append("H1 " + ("نزولی" if h1_tr == "bearish" else "صعودی"))
        if adx_v is not None:
            bits.append(f"ADX(14) H1={adx_v}")
        return _pack("trend", "رونددار", "، ".join(bits) or "ساختار جهت‌دار",
                     "continuation", rng, adx_h1, adx_m15, atr_pct, rvol, vdev)

    if d1 in ("LH/LL", "HH/HL") and not tight and h4_tr in ("bullish", "bearish"):
        return _pack("trend", "رونددار",
                     f"روند روزانه {'نزولی' if d1 == 'LH/LL' else 'صعودی'} و H4 هم‌جهت",
                     "continuation", rng, adx_h1, adx_m15, atr_pct, rvol, vdev)

    why = "رژیم رونددار مشخصی دیده نمی‌شود"
    if adx_v is not None:
        why += f" · ADX(14) H1={adx_v}"
    return _pack("range", "رنج", why, "sweep_reversion", rng, adx_h1, adx_m15, atr_pct, rvol, vdev)

def _pack(code, fa, why, engine, rng, adx_h1, adx_m15, atr_pct, rvol, vdev):
    return {
        "code": code, "fa": fa, "why": why,
        "allowed_engine": engine,
        "allowed_engine_fa": FA_ENGINE[engine],
        "session_range": None if rng is None else round(rng, 2),
        "adx_h1": adx_h1, "adx_m15": adx_m15,
        "atr_percentile_m5": atr_pct,
        "rel_tick_volume_m5": rvol,
        "vwap_deviation": vdev,
    }

def _near_level_refs(lv, side, atr_m5):
    """Reference prices for a pullback (continuation) or a sweep."""
    refs = []
    emas = lv.get("ema") or {}
    for tf in ("H4", "H1"):
        if tf in emas and emas[tf].get("ema20") is not None:
            refs.append((float(emas[tf]["ema20"]), f"EMA20 {tf}"))
    vdev = vwap_deviation(lv)
    if vdev:
        refs.append((vdev["vwap"], f"VWAP {vdev.get('session_fa') or ''}".strip()))
    # nearby clustered levels in the pullback direction
    for l in lv.get("levels") or []:
        if l.get("strength") not in ("strong", "medium"):
            continue
        if side == "BUY" and l["side"] == "support":
            refs.append((float(l["price"]), l.get("label_fa") or "حمایت"))
        if side == "SELL" and l["side"] == "resistance":
            refs.append((float(l["price"]), l.get("label_fa") or "مقاومت"))
    return refs

def detect_continuation(lv, bias, regime, m5=None):
    """Unvalidated trend-continuation detector. Returns a setup dict or None."""
    if (regime or {}).get("code") != "trend" or (regime or {}).get("allowed_engine") != "continuation":
        return None
    h4 = ((bias or {}).get("h4") or {}).get("trend")
    h1 = ((bias or {}).get("h1") or {}).get("trend")
    if h4 not in ("bullish", "bearish"):
        return None
    if h1 in ("bullish", "bearish") and h1 != h4:
        return None
    side = "BUY" if h4 == "bullish" else "SELL"
    price = float(lv["price_bid"])
    atr_m5 = float(lv.get("atr_m5_14") or 0) or 1.0
    # do not chase an extended move
    vdev = (regime or {}).get("vwap_deviation") or vwap_deviation(lv, price)
    if vdev and vdev.get("sigma") is not None:
        if side == "BUY" and vdev["sigma"] > 1.5:
            return None
        if side == "SELL" and vdev["sigma"] < -1.5:
            return None
    refs = _near_level_refs(lv, side, atr_m5)
    if not refs:
        return None
    near = min(refs, key=lambda r: abs(price - r[0]))
    if abs(price - near[0]) > 0.5 * atr_m5:
        return None
    try:
        m5 = m5 if m5 is not None else load_bars("m5")
    except Exception:
        return None
    last = m5.iloc[-1]
    # require the last M5 close to be in the trend direction (no claim this is an edge)
    if side == "BUY" and not (float(last.c) >= float(last.o)):
        return None
    if side == "SELL" and not (float(last.c) <= float(last.o)):
        return None
    why = (f"رژیم رونددار است و H4 {'صعودی' if side == 'BUY' else 'نزولی'} است. "
           f"قیمت تا {near[1]} ({near[0]:.2f}) عقب نشسته و آخرین کندل M5 در جهت روند بسته شد. "
           "این فقط یک آشکارساز تأییدنشده است.")
    return {"engine": "continuation", "engine_fa": FA_ENGINE["continuation"],
            "side": side, "ref_price": round(near[0], 2), "ref_name": near[1],
            "why_fa": why, "unvalidated": True}

def _sweep_refs(lv):
    highs, lows = [], []
    ses = lv.get("sessions") or {}
    for key, fa in (("asia", "آسیا"), ("london", "لندن"), ("ny", "نیویورک"),
                    ("prev_day", "دیروز"), ("prev_ny", "نیویورک دیروز")):
        b = ses.get(key)
        if not b:
            continue
        if b.get("high") is not None:
            highs.append((float(b["high"]), f"سقف {fa}"))
        if b.get("low") is not None:
            lows.append((float(b["low"]), f"کف {fa}"))
    for key, fa in (("london", "رنج بازگشایی لندن"), ("ny", "رنج بازگشایی نیویورک")):
        b = (lv.get("opening_ranges") or {}).get(key)
        if not b:
            continue
        if b.get("high") is not None:
            highs.append((float(b["high"]), f"سقف {fa}"))
        if b.get("low") is not None:
            lows.append((float(b["low"]), f"کف {fa}"))
    for e in (lv.get("equal") or {}).get("highs") or []:
        highs.append((float(e["price"]), "سقف برابر M15"))
    for e in (lv.get("equal") or {}).get("lows") or []:
        lows.append((float(e["price"]), "کف برابر M15"))
    return highs, lows

def detect_sweep(lv, bias, regime, m5=None):
    """Unvalidated liquidity-sweep / mean-reversion detector. Returns a setup dict or None."""
    if (regime or {}).get("code") != "range" or (regime or {}).get("allowed_engine") != "sweep_reversion":
        return None
    try:
        m5 = m5 if m5 is not None else load_bars("m5")
    except Exception:
        return None
    if m5 is None or len(m5) < 8:
        return None
    price = float(lv["price_bid"])
    atr_m5 = float(lv.get("atr_m5_14") or 0) or 1.0
    pad = max(0.3, 0.15 * atr_m5)
    highs, lows = _sweep_refs(lv)
    recent = m5.iloc[-6:]
    hits = []
    for ts, bar in recent.iterrows():
        for ref, name in highs:
            if float(bar.h) >= ref + pad and float(bar.c) < ref:
                hits.append((ts, "SELL", ref, name, float(bar.h)))
        for ref, name in lows:
            if float(bar.l) <= ref - pad and float(bar.c) > ref:
                hits.append((ts, "BUY", ref, name, float(bar.l)))
    if not hits:
        return None
    ts, side, ref, name, ext = hits[-1]  # most recent
    # late if price has already travelled more than 1×ATR away from the swept level
    if abs(price - ref) > 1.0 * atr_m5:
        return None
    when = ts.tz_convert(TEH).strftime("%H:%M") if getattr(ts, "tz_convert", None) else str(ts)
    why = (f"رژیم رنج است. در M5 ساعت {when} تهران، قیمت {name} ({ref:.2f}) را جارو کرد و دوباره به داخل برگشت. "
           "این فقط یک آشکارساز تأییدنشده است.")
    return {"engine": "sweep_reversion", "engine_fa": FA_ENGINE["sweep_reversion"],
            "side": side, "ref_price": round(ref, 2), "ref_name": name, "extreme": round(ext, 2),
            "bar_tehran": when, "why_fa": why, "unvalidated": True}

def decide(lv, bias, regime, quality=None, journal_note=None):
    """BUY / SELL / NO TRADE plus accept/reject reasons. Never claims an edge."""
    accepts, rejects = [], []
    win = (bias or {}).get("news_window") or {}
    spread = (bias or {}).get("spread") or {}
    if quality and not quality.get("ok"):
        rejects.append(quality.get("fa") or "کیفیت داده قابل قبول نیست.")
        return {"decision": "NO TRADE", "engine": None, "engine_fa": FA_ENGINE[None],
                "reasons_accept": [], "reasons_reject": rejects,
                "unvalidated": True}
    code = (regime or {}).get("code")
    if code == "news_abnormal":
        rejects.append("رژیم خبری / غیرعادی است: " + (regime or {}).get("why", "ورود مجاز نیست."))
        return {"decision": "NO TRADE", "engine": None, "engine_fa": FA_ENGINE[None],
                "reasons_accept": [], "reasons_reject": rejects, "unvalidated": True}
    if code == "volatility_expansion":
        rejects.append("جهش نوسان: " + (regime or {}).get("why", "") + " — صبر تا آرام شدن نوسان.")
        return {"decision": "NO TRADE", "engine": None, "engine_fa": FA_ENGINE[None],
                "reasons_accept": [], "reasons_reject": rejects, "unvalidated": True}
    if spread.get("abnormal"):
        rejects.append(f"اسپرد غیرعادی است ({spread.get('current')} دلار).")
        return {"decision": "NO TRADE", "engine": None, "engine_fa": FA_ENGINE[None],
                "reasons_accept": [], "reasons_reject": rejects, "unvalidated": True}

    det = None
    if (regime or {}).get("allowed_engine") == "continuation":
        det = detect_continuation(lv, bias, regime)
        if det is None:
            rejects.append("موتور مجاز ادامه روند است، ولی ستاپ ادامه (عقب‌نشینی به مرجع + کندل M5 هم‌جهت) دیده نشد.")
    elif (regime or {}).get("allowed_engine") == "sweep_reversion":
        det = detect_sweep(lv, bias, regime)
        if det is None:
            rejects.append("موتور مجاز جاروی نقدینگی / بازگشت به میانگین است، ولی جاروی تازه‌ی M5 روی سقف/کف سشن، رنج بازگشایی یا سقف/کف برابر دیده نشد.")
    else:
        rejects.append("هیچ موتوری برای این رژیم مجاز نیست.")

    # tier B caution does not by itself block, but it is always disclosed
    if win.get("inside") and win.get("action") == "caution":
        note = "خبر سطح B فعال است (احتیاط + کنترل اسپرد)؛ بلوک خودکار نیست."
        if det:
            accepts.append(note)
        else:
            rejects.append(note)
    elif win.get("soon_action") == "caution":
        note = f"{win.get('minutes_to_next')} دقیقه تا خبر سطح B (احتیاط)."
        if det:
            accepts.append(note)
        else:
            rejects.append(note)

    if not det:
        if (bias or {}).get("verdict", {}).get("code") in ("wait_neutral", "wait_level", "wait", "wait_against"):
            rejects.append((bias["verdict"].get("fa") or "صبر.").split("صبر کن: ")[-1] if False else (bias["verdict"].get("fa") or "صبر."))
        return {"decision": "NO TRADE", "engine": (regime or {}).get("allowed_engine"),
                "engine_fa": (regime or {}).get("allowed_engine_fa") or FA_ENGINE[None],
                "reasons_accept": accepts, "reasons_reject": rejects, "setup": None, "unvalidated": True}

    accepts.append(det["why_fa"])
    accepts.append("سطح‌ها و جهت تأییدنشده‌اند و این موتور برتری آماری ندارد.")
    return {"decision": det["side"], "engine": det["engine"], "engine_fa": det["engine_fa"],
            "reasons_accept": accepts, "reasons_reject": rejects, "setup": det, "unvalidated": True}

def fa_indicator_lines(regime):
    """Short Persian lines for ADX / ATR percentile / VWAP deviation (no strength words)."""
    lines = []
    adx_h1 = (regime or {}).get("adx_h1") or {}
    if adx_h1.get("adx") is not None:
        lines.append(f"**ADX(14) H1:** {adx_h1['adx']}  (+DI {adx_h1.get('plus_di')} / −DI {adx_h1.get('minus_di')}) — فقط تأیید اختیاری، نه سیگنال.")
    atrp = (regime or {}).get("atr_percentile_m5") or {}
    rvol = (regime or {}).get("rel_tick_volume_m5") or {}
    bits = []
    if atrp.get("percentile") is not None:
        bits.append(f"صدک ATR پنج‌دقیقه {atrp['percentile']:.0f}")
    if rvol.get("ratio") is not None:
        bits.append(f"حجم تیک نسبی {rvol['ratio']}× (پروکسی حجم تیک)")
    if bits:
        lines.append("**نوسان/حجم:** " + " · ".join(bits))
    vdev = (regime or {}).get("vwap_deviation") or {}
    if vdev.get("vwap") is not None:
        sig = f" / {vdev['sigma']}σ" if vdev.get("sigma") is not None else ""
        lines.append(f"**انحراف VWAP {vdev.get('session_fa') or ''}:** {vdev['distance']:+.2f} دلار{sig} "
                     f"(VWAP {vdev['vwap']:.2f}، پروکسی حجم تیک)".replace("  ", " "))
    return lines
