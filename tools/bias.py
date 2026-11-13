#!/usr/bin/env python3
"""bias.py - higher-timeframe direction + "now: enter / wait for X" verdict (no entries/stops/targets).

Trend per timeframe (H4 required, then H1, M15; M5 is context only), score -3..+3:
  EMA20 vs EMA50 (±1) + EMA20 slope over last 5 bars (±1) + structure from the last two confirmed fractal swings
  (HH+HL = +1, LH+LL = -1).  score >= 2 bullish, <= -2 bearish, else neutral.
Technical bias: H4 is required. If H4 is directional and H1 agrees or is neutral -> H4;
H4 vs H1 conflict -> neutral. If H4 is neutral, fall back to H1+M15.
News bias (news_windows.json, from M5-News) is shown alongside; disagreement downgrades the verdict to caution.
D1 is not used for direction (levels only).

Verdict (first rule that fires wins):
  stale / market closed -> no_data | inside a tier-A (block) window, or one starting within its buffer -> wait
  tier B is ALSO a no-entry block (DaryaGold team rule), and positions must be flat before it; tier C is monitor only
  windows are the effective (stored ∪ DaryaGold floors) windows from news_windows.effective_doc
  spread abnormal (> 2x typical for that hour and > $0.8) -> wait
  bias neutral -> wait for range edges | price within 0.3*ATR_M5 of a medium/strong level IN the bias direction
  -> near_level (watch for an M5 rejection candle)
  price within 0.3*ATR of a high-score level AGAINST the bias -> wait | otherwise -> wait for X (mid-range)
Invalidation: bearish -> M15 close above the nearest high-score resistance (neutral) / H1 close above last H1 swing high (off);
mirrored for bullish. Output: /workspace/m5-gold-team/data/bias.json   usage: python3 bias.py [--at "YYYY-MM-DD HH:MM"]"""
import argparse, sys
from datetime import datetime
import pandas as pd
sys.path.insert(0, "/workspace/m5-gold-team/tools")
from m5lib import BIAS_JSON, LEVELS_JSON, META_JSON, TEH, load_bars, load_json, save_json, teh
from levels import ema, fractals
import news_windows as nw

FA = {"bullish": "صعودی", "bearish": "نزولی", "neutral": "خنثی"}

def tf_trend(df, n=3, lookback_days=8):
    if df is None or len(df) < 56:
        return {"trend": "neutral", "score": 0, "why": ["not enough bars"], "structure": "n/a",
                "ema20": None, "ema50": None, "last_swing_high": None, "last_swing_low": None}
    e20, e50 = ema(df.c, 20), ema(df.c, 50)
    H, L = fractals(df, n, df.index[-1] - pd.Timedelta(days=lookback_days))
    sc, why = 0, []
    sc += 1 if e20.iloc[-1] > e50.iloc[-1] else -1; why.append("EMA20>EMA50" if e20.iloc[-1] > e50.iloc[-1] else "EMA20<EMA50")
    sl = e20.iloc[-1] - e20.iloc[-6]; sc += 1 if sl > 0 else -1 if sl < 0 else 0; why.append(f"EMA20 slope {sl:+.2f}")
    st = "n/a"
    if len(H) >= 2 and len(L) >= 2:
        hh, hl_ = H[-1][1] > H[-2][1], L[-1][1] > L[-2][1]
        if hh and hl_: sc += 1; st = "HH/HL"
        elif not hh and not hl_: sc -= 1; st = "LH/LL"
        else: st = "mixed"
    why.append(f"structure {st}")
    close = float(df.c.iloc[-1]); why.append("price<EMAs" if close < min(e20.iloc[-1], e50.iloc[-1]) else "price>EMAs" if close > max(e20.iloc[-1], e50.iloc[-1]) else "price between EMAs")
    trend = "bullish" if sc >= 2 else "bearish" if sc <= -2 else "neutral"
    return {"trend": trend, "score": sc, "why": why, "structure": st, "ema20": round(float(e20.iloc[-1]), 2), "ema50": round(float(e50.iloc[-1]), 2),
            "last_swing_high": H[-1][1] if H else None, "last_swing_low": L[-1][1] if L else None}

def combine_bias(H4, H1, M15):
    """H4 is required for a directional technical bias."""
    if H4["trend"] in ("bullish", "bearish"):
        if H1["trend"] == H4["trend"]:
            conf = "aligned" if M15["trend"] in (H4["trend"], "neutral") else "h4_h1_m15_disagree"
            return H4["trend"], conf
        if H1["trend"] == "neutral":
            return H4["trend"], "h4_only"
        return "neutral", "conflict"
    # H4 neutral: fall back to H1 + M15 (D1 is not used for direction)
    if H1["trend"] == M15["trend"]:
        return H1["trend"], ("aligned" if H1["trend"] != "neutral" else "none")
    if M15["trend"] == "neutral" and H1["trend"] != "neutral":
        return H1["trend"], "h1_only"
    return "neutral", "conflict"

def spread_check(m1):
    s = (m1.c_a - m1.c_b).dropna()
    if s.empty: return {"known": False, "abnormal": False, "limit_rule": "spread > 2× typical for the hour AND > $0.80"}
    cur = float(s.tail(5).median()); hr = s.index[-1].hour
    hist = s[(s.index >= s.index[-1] - pd.Timedelta(days=5)) & (s.index.hour == hr)]
    typ = float(hist.median()) if len(hist) > 30 else float(s.median())
    return {"known": True, "current": round(cur, 2), "typical_this_hour": round(typ, 2),
            "abnormal": bool(cur > 2 * typ and cur > 0.8),
            "limit_rule": "spread > 2× typical for the hour AND > $0.80",
            "hard_floor": 0.80}

def compute(at=None, pre=20):
    meta = load_json(META_JSON, {}); lv = load_json(LEVELS_JSON)
    if lv is None: raise SystemExit("ERROR: levels.json missing - run levels.py first")
    m1, m15, h1, h4 = load_bars("1m"), load_bars("m15"), load_bars("h1"), load_bars("h4")
    try:
        m5 = load_bars("m5")
    except Exception:
        m5 = None
    price = float(m1.c_b.iloc[-1]); a5 = lv["atr_m5_14"]
    H4, H1, M15 = tf_trend(h4, lookback_days=20), tf_trend(h1, lookback_days=8), tf_trend(m15, lookback_days=8)
    M5 = tf_trend(m5, lookback_days=2) if m5 is not None else None
    tech, conf = combine_bias(H4, H1, M15)
    news = (nw.load().get("news_bias") or {})
    nb = news.get("bias")
    agree = (nb is None) or nb == tech
    out = {"as_of_tehran": meta.get("as_of_tehran"), "source": meta.get("source"), "price_bid": price, "atr_m5": a5,
           "h4": H4, "h1": H1, "m15": M15, "m5": M5,
           "technical_bias": tech, "technical_confidence": conf, "news_bias": nb,
           "news_why": news.get("why"), "news_invalidation": news.get("invalidation"), "news_agrees": agree}
    bias = tech if agree or tech == "neutral" else "neutral"
    out["bias"] = bias
    # levels (ranks used only as an internal filter; never printed as قوی)
    L = lv["levels"]; key = [l for l in L if l["strength"] in ("strong", "medium")]
    res = sorted([l for l in key if l["side"] == "resistance"], key=lambda l: l["distance"])
    sup = sorted([l for l in key if l["side"] == "support"], key=lambda l: -l["distance"])
    top_res = [l for l in res if l["strength"] == "strong"] or res
    top_sup = [l for l in sup if l["strength"] == "strong"] or sup
    near = 0.3 * a5
    # invalidation
    if bias == "bearish" or (bias == "neutral" and tech == "bearish"):
        sh = [x for x in (H1["last_swing_high"],) if x and x > price]
        out["invalidation"] = {"neutral_if": f"M15 close above {top_res[0]['price']}" if top_res else None,
                               "off_if": f"H1 close above {sh[0] if sh else (top_res[1]['price'] if len(top_res) > 1 else None)}",
                               "neutral_level": top_res[0]["price"] if top_res else None,
                               "off_level": sh[0] if sh else (top_res[1]["price"] if len(top_res) > 1 else None)}
    elif bias == "bullish" or (bias == "neutral" and tech == "bullish"):
        sl = [x for x in (H1["last_swing_low"],) if x and x < price]
        out["invalidation"] = {"neutral_if": f"M15 close below {top_sup[0]['price']}" if top_sup else None,
                               "off_if": f"H1 close below {sl[0] if sl else (top_sup[1]['price'] if len(top_sup) > 1 else None)}",
                               "neutral_level": top_sup[0]["price"] if top_sup else None,
                               "off_level": sl[0] if sl else (top_sup[1]["price"] if len(top_sup) > 1 else None)}
    else:
        out["invalidation"] = None
    # verdict
    now = at or datetime.now(TEH)
    news_doc = nw.load()
    try:
        import broker_daryagold as DG
        news_doc = DG.expand_news_doc(news_doc)
    except Exception:
        pass
    win = nw.status(news_doc, now, pre)
    sp = spread_check(m1)
    out["news_window"] = win; out["spread"] = sp; out["evaluated_at_tehran"] = now.strftime("%Y-%m-%d %H:%M")
    v = {}
    block_now = win.get("action") == "block" or (win.get("inside") and win.get("tier") == "A")
    block_soon = win.get("soon_block") or win.get("soon_action") == "block"
    if not meta.get("ok", False) or meta.get("stale"):
        v = {"code": "no_data", "fa": "داده‌ی قیمت معتبر/تازه نیست؛ تا به‌روز شدن داده هیچ نظری درباره‌ی ورود نمی‌دهیم."}
    elif not meta.get("market_open", True):
        v = {"code": "market_closed", "fa": "بازار بسته است؛ صبر کن."}
    elif block_now:
        v = {"code": "wait_news", "fa": f"صبر کن: داخل پنجره‌ی خبری سطح {win.get('tier') or 'A'} (ورود ممنوع) {win.get('start','')} تا {win.get('end','')} به وقت تهران ({' + '.join(win.get('labels') or [])}).", "until": win.get("end")}
    elif block_soon:
        v = {"code": "wait_news_soon", "fa": f"صبر کن: {win.get('minutes_to_next')} دقیقه‌ی دیگر پنجره‌ی خبری سطح {win.get('next_tier') or 'A'} {str(win.get('next_start') or '')[-5:]} تا {win.get('next_end')} شروع می‌شود.", "until": win.get("next_end")}
    elif sp["abnormal"]:
        v = {"code": "wait_spread", "fa": f"صبر کن: اسپرد غیرعادی است ({sp['current']} دلار، معمول این ساعت {sp['typical_this_hour']})."}
    elif bias == "neutral":
        r0 = res[0]["price"] if res else None; s0 = sup[0]["price"] if sup else None
        why = "تایم‌ها هم‌جهت نیستند" if conf == "conflict" else ("بایاس تکنیکال با بایاس خبری M5-News هم‌جهت نیست" if not agree else "روند مشخصی نیست")
        v = {"code": "wait_neutral", "fa": f"صبر کن: جهت خنثی است ({why}). منتظر واکنش قیمت در لبه‌ها بمان: سقف {r0} / کف {s0}.", "levels": [r0, s0]}
    else:
        with_ = res if bias == "bearish" else sup
        against = top_sup if bias == "bearish" else top_res
        if with_ and abs(with_[0]["distance"]) <= near:
            l = with_[0]
            v = {"code": "near_level", "fa": f"قیمت به سطح {l['price']} ({l['label_fa']}) رسیده است؛ "
                                             f"فقط در صورت کندل برگشتی M5 در جهت {FA[bias]} وقت ورود است.", "level": l["price"]}
        elif against and abs(against[0]["distance"]) <= near:
            v = {"code": "wait_against", "fa": f"صبر کن: قیمت روی سطح خلاف جهت ({against[0]['price']}) است؛ ورود {FA[bias]} اینجا خلاف منطق سطح است.",
                 "level": against[0]["price"]}
        elif with_:
            l = with_[0]
            v = {"code": "wait_level", "fa": f"صبر کن: قیمت وسط راه است. منتظر رسیدن به {l['price']} ({l['label_fa']}) بمان.",
                 "level": l["price"], "distance": l["distance"]}
        else:
            v = {"code": "wait", "fa": "صبر کن: سطح معتبری در جهت بایاس نزدیک قیمت نیست."}
    if win.get("inside") and win.get("action") == "caution":
        v["news_caution_fa"] = f"خبر سطح {win.get('tier')} فعال است ({' + '.join(win.get('labels') or [])})؛ احتیاط و کنترل اسپرد."
    elif (not win.get("inside")) and win.get("next_action") == "block" and win.get("minutes_to_next") is not None \
            and win["minutes_to_next"] <= 120:
        st_ = str(win.get("next_start") or "")[-5:]
        v["news_caution_fa"] = (f"{win['minutes_to_next']} دقیقه تا پنجره‌ی خبری سطح {win.get('next_tier')} "
                                f"({st_} تا {win.get('next_end')}، {' + '.join(win.get('next_labels') or [])}). "
                                f"از {st_} ورود ممنوع است و هر پوزیشن یا اوردر باید پیش از {st_} بسته یا لغو شود.")
        v["flat_by_tehran"] = st_
    v["near_threshold"] = round(near, 2)
    if not agree and nb and tech != "neutral": v["note_fa"] = f"بایاس تکنیکال {FA[tech]} ولی بایاس خبری {FA.get(nb, nb)} است."
    out["verdict"] = v
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", help='evaluate news windows at this Tehran time "YYYY-MM-DD HH:MM" (testing)')
    ap.add_argument("--pre", type=int, default=20, help="lookahead (minutes) for listing the next window; stored A windows already include their lead-in, and soon-block is the last 5 min before start")
    a = ap.parse_args()
    at = datetime.strptime(a.at, "%Y-%m-%d %H:%M").replace(tzinfo=TEH) if a.at else None
    out = compute(at, a.pre); save_json(BIAS_JSON, out)
    print(f"bias {out['bias']} (tech {out['technical_bias']}/{out['technical_confidence']}, news {out['news_bias']}) | "
          f"H4 {out['h4']['trend']} {out['h4']['score']} | H1 {out['h1']['trend']} {out['h1']['score']} | "
          f"M15 {out['m15']['trend']} {out['m15']['score']} | verdict {out['verdict']['code']}")
    print(out["verdict"]["fa"])

if __name__ == "__main__":
    main()
