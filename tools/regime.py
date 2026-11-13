#!/usr/bin/env python3
"""regime.py - 4-state regime gate, ADX, VWAP deviation, and two unvalidated setup detectors.

States:
  news_abnormal         inside a tier-A or tier-B effective no-entry window (DaryaGold rule), or a spread anomaly → no trade
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
from levels import atr, fractals

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

def classify(lv, win=None, spread=None, h4=None, h1=None, m5=None, h1_df=None, m5_df=None, m15_df=None, ignore_gates=False):
    """Return a 4-state regime dict. Deterministic heuristics, not a forecast.
    ignore_gates=True skips the news/spread and volatility states (counterfactual for the shadow log only;
    the live brief never sets it)."""
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
    if ignore_gates:
        win, spread = {}, {}
    if win.get("action") == "block" or (win.get("inside") and win.get("tier") == "A"):
        why = f"داخل پنجره‌ی خبری سطح {win.get('tier') or 'A'} (ورود ممنوع) {win.get('start','')} تا {win.get('end','')}"
        if win.get("labels"):
            why += f" ({' + '.join(win['labels'])})"
        return _pack("news_abnormal", "خبری / غیرعادی", why, None, rng, adx_h1, adx_m15, atr_pct, rvol, vdev)
    if win.get("soon_block") or win.get("soon_action") == "block":
        return _pack("news_abnormal", "خبری / غیرعادی",
                     f"{win.get('minutes_to_next')} دقیقه تا پنجره‌ی خبری سطح {win.get('next_tier') or 'A'} (ورود ممنوع)",
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
    if exp and not ignore_gates:
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

SWING_N = 2
CONT_LOOKBACK = 48
RETEST_FRESH_BARS = 4
SWEEP_FRESH_BARS = 8
# Only a near_level bias verdict can agree with a setup; every wait_* / news / data code blocks.
SETUP_OK_VERDICT = frozenset({"near_level"})


def _confirmed_swings(m5, n=SWING_N, lookback=CONT_LOOKBACK):
    """Confirmed M5 fractal swings (n bars on each side)."""
    if m5 is None or len(m5) < 2 * n + 3:
        return [], []
    start = max(0, len(m5) - lookback - n)
    return fractals(m5.iloc[start:], n)


def _touch_tol(atr_m5):
    return max(0.15, 0.10 * float(atr_m5 or 1.0))


def _bos_and_retest(m5, side, atr_m5=1.0, lookback=CONT_LOOKBACK):
    """M5 BOS then retest, or None.

    BOS = M5 close beyond the most recent opposing M5 swing high (BUY) or
    swing low (SELL) within the pullback. Retest = a later bar touches the
    broken level and closes back in the trade direction. Unvalidated heuristic.
    """
    if m5 is None or len(m5) < 2 * SWING_N + 6:
        return None
    H, L = _confirmed_swings(m5, SWING_N, lookback)
    tol = _touch_tol(atr_m5)
    if side == "BUY":
        if not L or not H:
            return None
        pb_ts, pb_px = L[-1]
        after_hi = [h for h in H if h[0] > pb_ts]
        opposing = after_hi[-1] if after_hi else ([h for h in H if h[0] < pb_ts] or [None])[-1]
        if opposing is None:
            return None
        sw_ts, sw_px = opposing
        after = m5[m5.index > sw_ts]
        bos_ts = None
        for ts, bar in after.iterrows():
            if float(bar.c) > sw_px:
                bos_ts = ts
                break
        if bos_ts is None:
            return None
        later = m5[m5.index > bos_ts]
        retest_ts = None
        for ts, bar in later.iterrows():
            if float(bar.l) <= sw_px + tol and float(bar.c) >= sw_px - 1e-9:
                retest_ts = ts
                break
        if retest_ts is None:
            return None
        after_rt = m5[m5.index > retest_ts]
        if any(float(bar.c) < sw_px for _, bar in after_rt.iterrows()):
            return None
        pos = m5.index.get_loc(retest_ts)
        if isinstance(pos, slice):
            pos = pos.start
        if pos < len(m5) - RETEST_FRESH_BARS:
            return None
        window = m5[(m5.index >= min(pb_ts, sw_ts)) & (m5.index <= retest_ts)]
        extreme = float(window.l.min()) if len(window) else pb_px
        return {"bos_level": round(float(sw_px), 2), "bos_ts": bos_ts,
                "retest_ts": retest_ts, "extreme": round(extreme, 2),
                "pullback_extreme": round(float(pb_px), 2)}
    if side == "SELL":
        if not H or not L:
            return None
        pb_ts, pb_px = H[-1]
        after_lo = [x for x in L if x[0] > pb_ts]
        opposing = after_lo[-1] if after_lo else ([x for x in L if x[0] < pb_ts] or [None])[-1]
        if opposing is None:
            return None
        sw_ts, sw_px = opposing
        after = m5[m5.index > sw_ts]
        bos_ts = None
        for ts, bar in after.iterrows():
            if float(bar.c) < sw_px:
                bos_ts = ts
                break
        if bos_ts is None:
            return None
        later = m5[m5.index > bos_ts]
        retest_ts = None
        for ts, bar in later.iterrows():
            if float(bar.h) >= sw_px - tol and float(bar.c) <= sw_px + 1e-9:
                retest_ts = ts
                break
        if retest_ts is None:
            return None
        after_rt = m5[m5.index > retest_ts]
        if any(float(bar.c) > sw_px for _, bar in after_rt.iterrows()):
            return None
        pos = m5.index.get_loc(retest_ts)
        if isinstance(pos, slice):
            pos = pos.start
        if pos < len(m5) - RETEST_FRESH_BARS:
            return None
        window = m5[(m5.index >= min(pb_ts, sw_ts)) & (m5.index <= retest_ts)]
        extreme = float(window.h.max()) if len(window) else pb_px
        return {"bos_level": round(float(sw_px), 2), "bos_ts": bos_ts,
                "retest_ts": retest_ts, "extreme": round(extreme, 2),
                "pullback_extreme": round(float(pb_px), 2)}
    return None


def _reversal_bos(m5, side, sweep_ts, lookback=CONT_LOOKBACK):
    """M5 close beyond the most recent opposing short-term swing after a sweep.

    SELL (swept a high): close below the most recent M5 swing low.
    BUY (swept a low): close above the most recent M5 swing high.
    The BOS bar must be at or after the sweep and still recent. Unvalidated.
    """
    if m5 is None or sweep_ts is None:
        return None
    H, L = _confirmed_swings(m5, SWING_N, lookback)
    if side == "SELL":
        lows = [x for x in L if x[0] <= sweep_ts] or [x for x in L if x[0] <= m5.index[-1]]
        if not lows:
            return None
        sw_ts, sw_px = lows[-1]
        for ts, bar in m5[m5.index > sw_ts].iterrows():
            if ts < sweep_ts:
                continue
            if float(bar.c) < sw_px:
                pos = m5.index.get_loc(ts)
                if isinstance(pos, slice):
                    pos = pos.start
                if pos < len(m5) - SWEEP_FRESH_BARS:
                    return None
                return {"bos_level": round(float(sw_px), 2), "bos_ts": ts}
        return None
    if side == "BUY":
        highs = [x for x in H if x[0] <= sweep_ts] or [x for x in H if x[0] <= m5.index[-1]]
        if not highs:
            return None
        sw_ts, sw_px = highs[-1]
        for ts, bar in m5[m5.index > sw_ts].iterrows():
            if ts < sweep_ts:
                continue
            if float(bar.c) > sw_px:
                pos = m5.index.get_loc(ts)
                if isinstance(pos, slice):
                    pos = pos.start
                if pos < len(m5) - SWEEP_FRESH_BARS:
                    return None
                return {"bos_level": round(float(sw_px), 2), "bos_ts": ts}
        return None
    return None


def _when_teh(ts):
    if getattr(ts, "tz_convert", None):
        return ts.tz_convert(TEH).strftime("%H:%M")
    return str(ts)


def _pullback_visited_ref(m5, side, refs, atr_m5, price):
    """True if the recent pullback extreme (or current price) came to a valid ref."""
    if not refs or m5 is None or len(m5) < 3:
        return None
    recent = m5.iloc[-24:] if len(m5) >= 24 else m5
    pb = float(recent.l.min()) if side == "BUY" else float(recent.h.max())
    near_pb = min(refs, key=lambda r: abs(pb - r[0]))
    if abs(pb - near_pb[0]) <= 0.5 * atr_m5:
        return near_pb
    near_now = min(refs, key=lambda r: abs(price - r[0]))
    if abs(price - near_now[0]) <= 0.5 * atr_m5:
        return near_now
    return None


def detect_continuation(lv, bias, regime, m5=None):
    """Unvalidated trend-continuation detector. Returns a setup dict or None.

    Requires a pullback to a valid reference AND an M5 break of structure
    followed by a retest (close beyond the most recent opposing M5 swing
    within the pullback, then a later bar that touches the broken level and
    closes back in the trade direction). No statistical edge is claimed.
    """
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
    vdev = (regime or {}).get("vwap_deviation") or vwap_deviation(lv, price)
    if vdev and vdev.get("sigma") is not None:
        if side == "BUY" and vdev["sigma"] > 1.5:
            return None
        if side == "SELL" and vdev["sigma"] < -1.5:
            return None
    refs = _near_level_refs(lv, side, atr_m5)
    try:
        m5 = m5 if m5 is not None else load_bars("m5")
    except Exception:
        return None
    if m5 is None or len(m5) < 2 * SWING_N + 6:
        return None
    near = _pullback_visited_ref(m5, side, refs, atr_m5, price)
    if near is None:
        return None
    conf = _bos_and_retest(m5, side, atr_m5)
    if conf is None:
        return None
    # SL anchor: pullback extreme (plan_from_setup adds >= $1 and >= $0.5 beyond structure)
    ext = conf["extreme"]
    why = (f"رژیم رونددار است و H4 {'صعودی' if side == 'BUY' else 'نزولی'} است. "
           f"قیمت تا {near[1]} ({near[0]:.2f}) عقب نشست، سپس در M5 ساختار "
           f"در {conf['bos_level']:.2f} شکست و بازآزمایی شد "
           f"(ساعت {_when_teh(conf['retest_ts'])} تهران). "
           "این فقط یک آشکارساز تأییدنشده است و برتری آماری ندارد.")
    return {"engine": "continuation", "engine_fa": FA_ENGINE["continuation"],
            "side": side, "ref_price": round(near[0], 2), "ref_name": near[1],
            "extreme": ext, "bos_level": conf["bos_level"],
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
    """Unvalidated liquidity-sweep / mean-reversion detector. Returns a setup dict or None.

    Requires a wick beyond a session / opening-range / equal H/L, a close back
    inside the level, AND an M5 short-term BOS in the reversal direction.
    No statistical edge is claimed.
    """
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
    for ts, side, ref, name, ext in reversed(hits):
        if abs(price - ref) > 1.0 * atr_m5:
            continue
        bos = _reversal_bos(m5, side, ts)
        if bos is None:
            continue
        when = _when_teh(ts)
        why = (f"رژیم رنج است. در M5 ساعت {when} تهران، قیمت {name} ({ref:.2f}) را جارو کرد "
               f"و دوباره به داخل برگشت، سپس شکست ساختار کوتاه‌مدت M5 "
               f"در {bos['bos_level']:.2f} تأیید شد. "
               "این فقط یک آشکارساز تأییدنشده است و برتری آماری ندارد.")
        return {"engine": "sweep_reversion", "engine_fa": FA_ENGINE["sweep_reversion"],
                "side": side, "ref_price": round(ref, 2), "ref_name": name, "extreme": round(ext, 2),
                "bos_level": bos["bos_level"], "bar_tehran": when,
                "why_fa": why, "unvalidated": True}
    return None


def bias_allows_setup(bias, side):
    """A setup may print only when the bias verdict and direction agree with it."""
    v = (bias or {}).get("verdict") or {}
    code = v.get("code")
    fa = v.get("fa") or "صبر."
    if code not in SETUP_OK_VERDICT:
        return False, fa
    bdir = (bias or {}).get("bias")
    if side == "BUY" and bdir != "bullish":
        return False, "جهت بازار با خرید هم‌خوان نیست."
    if side == "SELL" and bdir != "bearish":
        return False, "جهت بازار با فروش هم‌خوان نیست."
    if side not in ("BUY", "SELL"):
        return False, fa
    return True, None


def _no_trade(rejects, accepts=None, engine=None, engine_fa=None):
    return {"decision": "NO TRADE", "engine": engine, "engine_fa": engine_fa or FA_ENGINE[None],
            "reasons_accept": list(accepts or []), "reasons_reject": list(rejects),
            "setup": None, "unvalidated": True}


def decide(lv, bias, regime, quality=None, journal_note=None):
    """BUY / SELL / NO TRADE plus accept/reject reasons. Never claims an edge.

    A BUY/SELL is emitted only when the data gate, news gate, regime/engine
    gate and the bias verdict all agree. Friday/session and sizing vetoes are
    applied later by brief.py so the printed decision stays a single verdict.
    """
    accepts, rejects = [], []
    win = (bias or {}).get("news_window") or {}
    spread = (bias or {}).get("spread") or {}
    if quality and not quality.get("ok"):
        return _no_trade([quality.get("fa") or "کیفیت داده قابل قبول نیست."])
    code = (regime or {}).get("code")
    if code == "news_abnormal":
        return _no_trade(["رژیم خبری / غیرعادی است: " + (regime or {}).get("why", "ورود مجاز نیست.")])
    if code == "volatility_expansion":
        return _no_trade(["جهش نوسان: " + (regime or {}).get("why", "") + " — صبر تا آرام شدن نوسان."])
    if spread.get("abnormal"):
        return _no_trade([f"اسپرد غیرعادی است ({spread.get('current')} دلار)."])
    # News block (covers any path where regime was not already news_abnormal)
    if win.get("action") == "block" or (win.get("inside") and win.get("tier") in ("A", "B")) \
            or win.get("soon_block") or win.get("soon_action") == "block":
        return _no_trade([((bias or {}).get("verdict") or {}).get("fa")
                          or "داخل یا در آستانه‌ی پنجره‌ی خبری (ورود ممنوع)."])

    det = None
    if (regime or {}).get("allowed_engine") == "continuation":
        det = detect_continuation(lv, bias, regime)
        if det is None:
            rejects.append("موتور مجاز ادامه روند است، ولی ستاپ ادامه (عقب‌نشینی به مرجع + شکست ساختار M5 و بازآزمایی) دیده نشد.")
    elif (regime or {}).get("allowed_engine") == "sweep_reversion":
        det = detect_sweep(lv, bias, regime)
        if det is None:
            rejects.append("موتور مجاز جاروی نقدینگی / بازگشت به میانگین است، ولی جاروی تازه‌ی M5 با بسته‌شدن برگشتی به داخل سطح و شکست ساختار کوتاه‌مدت M5 دیده نشد.")
    else:
        rejects.append("هیچ موتوری برای این رژیم مجاز نیست.")

    if not det:
        vcode = ((bias or {}).get("verdict") or {}).get("code")
        if vcode and vcode not in SETUP_OK_VERDICT:
            rejects.append(((bias or {}).get("verdict") or {}).get("fa") or "صبر.")
        return _no_trade(rejects, accepts, (regime or {}).get("allowed_engine"),
                         (regime or {}).get("allowed_engine_fa") or FA_ENGINE[None])

    ok, why = bias_allows_setup(bias, det["side"])
    if not ok:
        rejects.append(why or "جهت یا حکم صبر با ستاپ هم‌خوان نیست.")
        return _no_trade(rejects, accepts, (regime or {}).get("allowed_engine"),
                         (regime or {}).get("allowed_engine_fa") or FA_ENGINE[None])

    accepts.append(det["why_fa"])
    accepts.append("سطح‌ها و جهت تأییدنشده‌اند و این موتور برتری آماری ندارد.")
    return {"decision": det["side"], "engine": det["engine"], "engine_fa": det["engine_fa"],
            "reasons_accept": accepts, "reasons_reject": rejects, "setup": det, "unvalidated": True}


def fa_indicator_lines(regime, price_fmt=None):
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
        vwap_s = price_fmt(vdev["vwap"]) if price_fmt else f"{vdev['vwap']:.2f}"
        lines.append(f"**انحراف VWAP {vdev.get('session_fa') or ''}:** {vdev['distance']:+.2f} دلار{sig} "
                     f"(VWAP {vwap_s}، پروکسی حجم تیک)".replace("  ", " "))
    return lines

def _synth_m5(rows, start="2026-11-13 10:00", tz="Asia/Tehran"):
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz=tz)
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"o": o, "h": h, "l": l, "c": c}, index=idx)


def _self_check():
    # BUY continuation: pullback low, internal swing high, close through it, retest.
    # Fractal n=2: a swing high at k must be the max of h[k-2:k+3].
    rows = []
    px = 3900.0
    # 0-7: climb to a high, then start pullback
    for i in range(8):
        o = px
        px = px + 1.5
        rows.append((o, px + 0.2, o - 0.2, px))
    # 8-14: pullback down to ~3890, form a swing low around bar 16 later
    for i in range(7):
        o = px
        px = px - 2.0
        rows.append((o, o + 0.2, px - 0.2, px))
    # Ensure a clear swing low (n=2) at this bar: neighbors higher
    lo = px
    rows.append((lo + 0.4, lo + 0.6, lo - 0.3, lo + 0.5))  # swing low candidate
    # 2 bars after the low (confirmation), small bounce
    rows.append((lo + 0.5, lo + 1.2, lo + 0.3, lo + 1.0))
    rows.append((lo + 1.0, lo + 2.0, lo + 0.8, lo + 1.8))
    # internal swing high (opposing) — this bar's high is max of neighbors
    sh = lo + 4.0
    rows.append((lo + 1.8, sh, lo + 1.6, lo + 3.2))  # swing high
    rows.append((lo + 3.0, lo + 3.3, lo + 2.4, lo + 2.6))
    rows.append((lo + 2.6, lo + 3.0, lo + 2.2, lo + 2.4))  # confirmation of SH
    # BOS: close above swing high
    rows.append((lo + 2.4, sh + 0.8, lo + 2.2, sh + 0.4))
    # Retest: touch the broken level, close back above
    rows.append((sh + 0.2, sh + 0.6, sh - 0.2, sh + 0.3))
    m5 = _synth_m5(rows)
    conf = _bos_and_retest(m5, "BUY", atr_m5=3.0)
    assert conf is not None, "BUY BOS+retest should fire on synthetic path"
    assert conf["extreme"] <= lo + 0.5
    # Old rule (last candle in direction near a ref) is not enough: drop BOS/retest bars
    m5_old = m5.iloc[:-4]  # stop before swing-high confirmation / BOS / retest
    # last bar may be in direction; should NOT be enough
    assert _bos_and_retest(m5_old, "BUY", atr_m5=3.0) is None

    # SELL mirror
    srows = []
    px = 3900.0
    for i in range(8):
        o = px
        px = px - 1.5
        srows.append((o, o + 0.2, px - 0.2, px))
    for i in range(7):
        o = px
        px = px + 2.0
        srows.append((o, px + 0.2, o - 0.2, px))
    hi = px
    srows.append((hi - 0.4, hi + 0.3, hi - 0.6, hi - 0.5))  # swing high
    srows.append((hi - 0.5, hi - 0.3, hi - 1.2, hi - 1.0))
    srows.append((hi - 1.0, hi - 0.8, hi - 2.0, hi - 1.8))
    sl = hi - 4.0
    srows.append((hi - 1.8, hi - 1.6, sl, hi - 3.2))  # swing low
    srows.append((hi - 3.0, hi - 2.4, hi - 3.3, hi - 2.6))
    srows.append((hi - 2.6, hi - 2.2, hi - 3.0, hi - 2.4))
    srows.append((hi - 2.4, hi - 2.2, sl - 0.8, sl - 0.4))  # BOS close below SL
    srows.append((sl - 0.2, sl + 0.2, sl - 0.6, sl - 0.3))  # retest
    m5s = _synth_m5(srows)
    confs = _bos_and_retest(m5s, "SELL", atr_m5=3.0)
    assert confs is not None, "SELL BOS+retest should fire on synthetic path"

    # Sweep close-back-inside alone is not enough; need reversal BOS
    # Build: swing low, then sweep of a high and close back inside, then close below swing low.
    wrows = []
    p = 3900.0
    for i in range(6):
        wrows.append((p, p + 0.4, p - 0.4, p + 0.2))
        p += 0.2
    # swing low
    slv = p - 3.0
    wrows.append((p, p + 0.3, slv, p - 0.5))
    wrows.append((p - 0.5, p - 0.2, p - 0.8, p - 0.3))
    wrows.append((p - 0.3, p + 0.2, p - 0.6, p))
    # climb and sweep a ref high
    ref = p + 2.0
    wrows.append((p, ref - 0.2, p - 0.2, ref - 0.4))
    wrows.append((ref - 0.4, ref - 0.1, ref - 0.6, ref - 0.3))
    # sweep bar: wick above ref, close back inside
    sweep_i = len(wrows)
    wrows.append((ref - 0.3, ref + 0.5, ref - 0.8, ref - 0.4))
    # no BOS yet
    m5w = _synth_m5(wrows)
    sweep_ts = m5w.index[sweep_i]
    assert _reversal_bos(m5w, "SELL", sweep_ts) is None, "sweep without BOS must not confirm"
    # add BOS close below swing low
    wrows.append((ref - 0.4, ref - 0.2, slv - 0.4, slv - 0.2))
    m5w2 = _synth_m5(wrows)
    assert _reversal_bos(m5w2, "SELL", sweep_ts) is not None, "sweep + M5 BOS should confirm"

    # bias gate: wait_against cannot agree with a SELL setup
    ok, _ = bias_allows_setup({"bias": "bearish", "verdict": {"code": "wait_against", "fa": "صبر کن: سطح خلاف جهت."}}, "SELL")
    assert not ok
    ok, _ = bias_allows_setup({"bias": "bearish", "verdict": {"code": "near_level", "fa": "نزدیک سطح"}}, "SELL")
    assert ok
    ok, _ = bias_allows_setup({"bias": "bearish", "verdict": {"code": "near_level", "fa": "نزدیک سطح"}}, "BUY")
    assert not ok
    # decide() must return NO TRADE when bias says wait, even if a setup object is theoretically possible
    d = decide({"price_bid": 3900, "atr_m5_14": 3},
               {"bias": "bearish", "h4": {"trend": "bearish"}, "h1": {"trend": "bearish"},
                "verdict": {"code": "wait_against", "fa": "صبر کن: سطح خلاف جهت."},
                "news_window": {}, "spread": {}},
               {"code": "trend", "allowed_engine": "continuation", "allowed_engine_fa": "ادامه روند",
                "vwap_deviation": None})
    assert d["decision"] == "NO TRADE", d
    assert "صبر کن" in " ".join(d["reasons_reject"])
    print("self-check ok")


if __name__ == "__main__":
    _self_check()
