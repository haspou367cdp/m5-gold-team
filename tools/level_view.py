#!/usr/bin/env python3
"""One shared levels + trend snapshot for every Telegram consumer.

compute() in levels.py stays the single source of the FULL level set (signal engine reads that,
unchanged). This module builds a filtered short view (set B) and the H4/H1/M15/M5 trend from that
same result, once per run. /levels, /brief, /scan and the pre-session briefs all render the same
block from the stored snapshot. Research / display only; never changes a live signal gate.
"""
from __future__ import annotations
import math
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import broker_daryagold as DG
import levels as LV

TEH = ZoneInfo("Asia/Tehran")

# Display tags approved 2026-11-20 (levels specialist). No importance wording, no M15 touch count.
# H4 swings, $5/$10 rounds, VWAP bands, EMA, order-flow and volume-profile tags stay out.
SET_B = frozenset({
    "PDH", "PDL",
    "Week high", "Week low", "Prev week high", "Prev week low",
    "Asia high", "Asia low", "London high", "London low", "NY high", "NY low",
    "Prev NY high", "Prev NY low",
    "London OR high", "London OR low", "NY OR high", "NY OR low",
    "VWAP",
    "Equal high", "Equal low",
    "Round $100", "Round $50",
    "H1 swing high", "H1 swing low",
    "Month high", "Month low", "Prev month high", "Prev month low",
})

KIND_FA = {   # plain words for a beginner (same wording as the Edge Function's plainLabel)
    "PDH": "سقف دیروز", "PDL": "کف دیروز",
    "Week high": "سقف این هفته", "Week low": "کف این هفته",
    "Prev week high": "سقف هفته‌ی قبل", "Prev week low": "کف هفته‌ی قبل",
    "Asia high": "سقف صبح امروز", "Asia low": "کف صبح امروز",
    "London high": "سقف ظهر امروز", "London low": "کف ظهر امروز",
    "NY high": "سقف عصر", "NY low": "کف عصر",
    "Prev NY high": "سقف عصر دیروز", "Prev NY low": "کف عصر دیروز",
    "H1 swing high": "نقطه‌ی برگشت اخیر", "H1 swing low": "نقطه‌ی برگشت اخیر",
    "H4 swing high": "نقطه‌ی برگشت روزهای اخیر", "H4 swing low": "نقطه‌ی برگشت روزهای اخیر",
    "Round $100": "عدد رُند", "Round $50": "عدد رُند",
    "London OR high": "سقف شروع ظهر", "London OR low": "کف شروع ظهر",
    "NY OR high": "سقف شروع عصر", "NY OR low": "کف شروع عصر",
    "VWAP": "میانگین قیمت امروز",
    "Equal high": "دو سقف هم‌اندازه", "Equal low": "دو کف هم‌اندازه",
    "Month high": "سقف این ماه", "Month low": "کف این ماه",
    "Prev month high": "سقف ماه قبل", "Prev month low": "کف ماه قبل",
}
# Most telling names first; at most two per level so a phone line does not wrap (= assist.js KIND_RANK, owner t246u).
_KIND_ORDER = [
    "Prev month high", "Prev month low", "Month high", "Month low", "Prev week high", "Prev week low", "Week high", "Week low",
    "PDH", "PDL", "Asia high", "Asia low", "London high", "London low", "NY high", "NY low", "Prev NY high", "Prev NY low",
    "Equal high", "Equal low", "London OR high", "London OR low", "NY OR high", "NY OR low", "VWAP",
    "H1 swing high", "H1 swing low", "H4 swing high", "H4 swing low",
]
_OR_OF = {"London OR high": "London high", "London OR low": "London low", "NY OR high": "NY high", "NY OR low": "NY low"}
MONTH_KINDS = frozenset({"Month high", "Month low", "Prev month high", "Prev month low"})

# Display-only weights. Same figures as levels.W for set B kinds; previous-week H/L
# (stored in structure, not in compute() candidates) get the same weight as PDH/PDL.
DISPLAY_W = {k: float(v) for k, v in LV.W.items()}
DISPLAY_W["Prev week high"] = 3.0
DISPLAY_W["Prev week low"] = 3.0
DISPLAY_W["Week high"] = 3.0
DISPLAY_W["Week low"] = 3.0

# Display tiers are relative to today's full set B (all structural clusters, not just the 2+2 shown).
# display_score = sum(DISPLAY_W of SET_B kinds in the cluster) + TOUCH_W * min(touches_m15_3d, TOUCH_CAP).
#   TOUCH_CAP = 4, TOUCH_W = 0.5  →  the touch bonus is at most +2.0, so a busy level cannot
#   monopolize the scale (compute() already caps touches at +2 for the signal ranks; we cap
#   the raw count here because the *relative* rank would otherwise collapse to "whoever was
#   touched most").
# Let p25, p50, p75 be the 25th/50th/75th nearest-rank percentiles of today's set B scores
# (inclusive: index = ceil(p/100 * n) - 1, clamped to [0, n-1]).
#   خیلی مهم : score >= p75 AND score > p50
#     (must sit strictly above the median, so a flat field stays «مهم»)
#   معمولی   : score <= p25 AND score < p50
#   مهم      : everything else, including the all-equal case
# Never prints «قوی». Does not change compute() strength used by the signal engine.
TOUCH_CAP = 4
TOUCH_W = 0.5
N_EACH = 2
FRESH_MIN = 15  # Edge Function serves a stored snapshot newer than this; otherwise queues a run
TFS = ("H4", "H1", "M15", "M5")


def _dg(price, cfg):
    if price is None:
        return None
    return round(float(DG.to_broker(float(price), cfg)), 2)


def _px(dg):
    """One-decimal Latin price for tap-to-copy (same convention as bot.p1)."""
    if dg is None:
        return "—"
    return f"{float(dg):.1f}"


def _usd(v):
    """Compact dollar figure for the context line (render() later turns the digits Persian).
    Whole dollars from 2 upward (as in «حدود ۳ دلار»); one decimal below that."""
    v = abs(float(v))
    if v >= 2:
        return str(int(round(v)))
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return s or "0"


def _kind_rank(k):
    if k.startswith("Round"):
        return 20.5
    return _KIND_ORDER.index(k) + 1 if k in _KIND_ORDER else 99


def label_fa(kinds, price_dg=None, limit=2):
    kinds = [k for k in kinds if not (k in _OR_OF and _OR_OF[k] in kinds)]
    seen, out = set(), []
    for k in sorted(kinds, key=_kind_rank):
        lab = KIND_FA.get(k)
        if k.startswith("Round") and price_dg is not None:
            lab = f"عدد رُند {int(round(float(price_dg) / 50.0) * 50)}"
        if lab and lab not in seen:
            seen.add(lab)
            out.append(lab)
    return " و ".join(out[:limit])


def display_score(item):
    kinds = item.get("kinds") or []
    w = sum(DISPLAY_W.get(k, 0.0) for k in kinds)
    touches = min(int(item.get("touches_m15_3d") or 0), TOUCH_CAP)
    return round(w + TOUCH_W * touches, 2)


def _percentile(sorted_vals, p):
    """Nearest-rank inclusive: i = ceil(p/100 * n) - 1, clamped to [0, n-1]."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    i = max(0, min(n - 1, math.ceil(p / 100.0 * n) - 1))
    return sorted_vals[i]


def assign_tiers(items):
    """Stamp a relative display tag on every set B level. See module comment for the rule."""
    if not items:
        return items
    scores = [display_score(it) for it in items]
    for it, sc in zip(items, scores):
        it["display_score"] = sc  # stored only; never printed
    xs = sorted(scores)
    p25, p50, p75 = _percentile(xs, 25), _percentile(xs, 50), _percentile(xs, 75)
    for it in items:
        sc = it["display_score"]
        if sc >= p75 and sc > p50:
            it["tag"] = "خیلی مهم"
        elif sc <= p25 and sc < p50:
            it["tag"] = "معمولی"
        else:
            it["tag"] = "مهم"
    return items


def _ema_bias(em):
    if not em:
        return "neutral", "ema missing"
    e20, e50, c = float(em["ema20"]), float(em["ema50"]), float(em["close"])
    if e20 > e50 and c > e20:
        return "bullish", f"EMA20 {e20} > EMA50 {e50}, close above EMA20"
    if e20 < e50 and c < e20:
        return "bearish", f"EMA20 {e20} < EMA50 {e50}, close below EMA20"
    if e20 > e50:
        return "neutral", "EMA20 above EMA50 but close is not above EMA20"
    if e20 < e50:
        return "neutral", "EMA20 below EMA50 but close is not below EMA20"
    return "neutral", "EMA20 equals EMA50"


def _swing_struct(sw):
    hs = (sw or {}).get("highs") or []
    ls = (sw or {}).get("lows") or []
    if len(hs) < 2 or len(ls) < 2:
        return "mixed", "fewer than two confirmed swings"
    h2, h1 = float(hs[-2][1]), float(hs[-1][1])
    l2, l1 = float(ls[-2][1]), float(ls[-1][1])
    up_h, up_l = h1 > h2, l1 > l2
    if up_h and up_l:
        return "up", "HH/HL"
    if (not up_h) and (not up_l):
        return "down", "LH/LL"
    return "mixed", "mixed swings"


def _tf_trend(structure, ema_b):
    if structure == "up" and ema_b == "bullish":
        return "صعودی"
    if structure == "down" and ema_b == "bearish":
        return "نزولی"
    return "خنثی"


def _htf_bias(h4, h1):
    """Higher-timeframe direction only when H4 and H1 agree on صعودی or نزولی."""
    if h4 == h1 and h4 in ("صعودی", "نزولی"):
        return h4
    return None


def verdict_line(h4, h1, m15, m5):
    """One short overall line: agreement, or a lower-frame pullback against the higher frames.
    No M1 — the stored snapshot can be up to 15 minutes old."""
    higher = _htf_bias(h4, h1)
    if not higher:
        return "جمع‌بندی: نامشخص"
    opp = "صعودی" if higher == "نزولی" else "نزولی"
    pull = [tf for tf, tr in (("M15", m15), ("M5", m5)) if tr == opp]
    if not pull:
        return f"جمع‌بندی: {higher}"
    if pull == ["M15", "M5"]:
        return f"جمع‌بندی: {higher}؛ M15 و M5 در اصلاح {opp}"
    return f"جمع‌بندی: {higher}؛ {pull[0]} در اصلاح {opp}"


_TF_FA = {"M5": "۵ دقیقه‌ای", "M15": "۱۵ دقیقه‌ای", "H1": "۱ ساعته", "H4": "۴ ساعته"}


def plain_trend_line(h4, h1, m15, m5):
    """One plain sentence about direction (same wording as the Edge Function's trendSummary)."""
    t = {"M15": m15, "M5": m5}
    higher = _htf_bias(h4, h1)
    if higher:
        opp = "صعودی" if higher == "نزولی" else "نزولی"
        act = "خرید" if higher == "صعودی" else "فروش"
        pull = [tf for tf in ("M15", "M5") if t[tf] == opp]
        same = [tf for tf in ("M15", "M5") if t[tf] == higher]
        big = f"جهت بزرگ بازار {higher} است (قیمت در ساعت‌های اخیر بیشتر {'بالا' if higher == 'صعودی' else 'پایین'} رفته)"
        if len(same) == 2:
            return f"{big} و حرکت کوتاه‌مدت هم با آن هم‌جهت است."
        if len(pull) == 2:
            return f"{big}، ولی در کوتاه‌مدت قیمت کمی برعکس برگشته است. برای {act} بهتر است صبر کنید تا ۵ و ۱۵ دقیقه‌ای هم دوباره {higher} شوند."
        if len(pull) == 1:
            return f"{big}، ولی {_TF_FA[pull[0]]} فعلاً برعکس برگشته است. برای {act} بهتر است صبر کنید تا {_TF_FA[pull[0]]} هم دوباره {higher} شود."
        if len(same) == 1:
            other = "M5" if same[0] == "M15" else "M15"
            return f"{big}؛ {_TF_FA[same[0]]} هم {higher} است و {_TF_FA[other]} فعلاً جهت مشخصی ندارد."
        return f"{big}، ولی در کوتاه‌مدت قیمت فعلاً جهت مشخصی ندارد."
    if h4 == "خنثی" and h1 == "خنثی":
        return "بازار فعلاً جهت مشخصی ندارد و بیشتر در یک محدوده بالا و پایین می‌رود."
    return f"روند ۴ ساعته {h4} و ۱ ساعته {h1} است و با هم نمی‌خوانند؛ پس جهت بزرگ بازار فعلاً روشن نیست."


_ARROW = {"صعودی": "⬆️", "نزولی": "⬇️", "خنثی": "➖", "نامشخص": "❔"}


def trend_head(h4, h1):
    """Short phone headline (= assist.js trendHead): «⬇️ جهت کلی: نزولی (رو به پایین)»."""
    higher = _htf_bias(h4, h1)
    o = higher or ("خنثی" if h4 == "خنثی" and h1 == "خنثی" else "نامشخص")
    word = {"خنثی": "بدون جهت"}.get(o, o)
    what = {"صعودی": "رو به بالا", "نزولی": "رو به پایین", "خنثی": "بالا و پایین در یک محدوده"}.get(o, "۴ و ۱ ساعته با هم نمی‌خوانند")
    return f"{_ARROW[o]} جهت کلی: {word} ({what})"


def trend_of(lv):
    """H4, H1, M15 and M5 from confirmed swings + EMA20/50. H4≠H1 → جمع‌بندی نامشخص."""
    out = {}
    for tf in TFS:
        em = (lv.get("ema") or {}).get(tf)
        sw = (lv.get("swings") or {}).get(tf) or {}
        eb, ewhy = _ema_bias(em)
        st, swhy = _swing_struct(sw)
        tr = _tf_trend(st, eb)
        out[tf] = {"trend": tr, "structure": st, "structure_why": swhy, "ema": eb, "ema_why": ewhy,
                   "ema20": (em or {}).get("ema20"), "ema50": (em or {}).get("ema50"),
                   "close": (em or {}).get("close")}
    h4 = out["H4"]["trend"]
    h1 = out["H1"]["trend"]
    m15 = out["M15"]["trend"]
    m5 = out["M5"]["trend"]
    higher = _htf_bias(h4, h1)
    out["disagree"] = higher is None
    out["overall"] = higher or "نامشخص"
    out["verdict"] = verdict_line(h4, h1, m15, m5)
    return out


def zone_half(atr_m5):
    """Half-width of a displayed zone: max(0.25×M5 ATR, $1.0)."""
    return max(1.0, round(0.25 * float(atr_m5 or 0.0), 2))


def _zone(price_dg, half):
    return [round(float(price_dg) - half, 2), round(float(price_dg) + half, 2)]


def _from_cluster(cl, cfg, half, price_bid, atr_h4=None):
    kinds = [k for k in (cl.get("kinds") or []) if k in SET_B]
    if not kinds:
        return None
    price = float(cl["price"])
    if any(k in MONTH_KINDS for k in kinds) and atr_h4 and abs(price - price_bid) > 3 * float(atr_h4) + 1e-9:
        kinds = [k for k in kinds if k not in MONTH_KINDS]
        if not kinds:
            return None
    price_dg = _dg(price, cfg)
    return {
        "price": price,
        "price_dg": price_dg,
        "zone_dg": _zone(price_dg, half),
        "side": "resistance" if price > price_bid else "support",
        "kinds": kinds,
        "label_fa": label_fa(kinds, price_dg),
        "touches_m15_3d": int(cl.get("touches_m15_3d") or 0),
        "strength": cl.get("strength") or "weak",
        "score": cl.get("score"),
    }


_STRUCT = (
    ("week", "Week high", "Week low"),
    ("prev_week", "Prev week high", "Prev week low"),
    ("month", "Month high", "Month low"),
    ("prev_month", "Prev month high", "Prev month low"),
)


def _add_structure_levels(items, lv, cfg, half, price_bid, atr_h4=None):
    """Week / month H/L live in compute()'s structure, not in the cluster list.
    Monthly levels more than 3×ATR(H4) away are dropped."""
    st = lv.get("structure") or {}
    for key, hi, lo in _STRUCT:
        block = st.get(key) or {}
        if block.get("high") is None:
            continue
        for kind, field in ((hi, "high"), (lo, "low")):
            p = float(block[field])
            if kind in MONTH_KINDS and atr_h4 and abs(p - price_bid) > 3 * float(atr_h4) + 1e-9:
                continue
            if any(abs(it["price"] - p) <= half and kind in (it.get("kinds") or []) for it in items):
                continue
            merged = False
            for it in items:
                if abs(it["price"] - p) <= half:
                    if kind not in it["kinds"]:
                        it["kinds"].append(kind)
                        it["label_fa"] = label_fa(it["kinds"], it["price_dg"])
                    merged = True
                    break
            if merged:
                continue
            price_dg = _dg(p, cfg)
            items.append({
                "price": p, "price_dg": price_dg, "zone_dg": _zone(price_dg, half),
                "side": "resistance" if p > price_bid else "support",
                "kinds": [kind], "label_fa": label_fa([kind], price_dg),
                "touches_m15_3d": 0, "strength": "medium",
            })


def merge_zones(items, price_bid):
    """Merge overlapping display zones and keep every tag."""
    rows = sorted((dict(it) for it in items), key=lambda x: x["price"])
    out = []
    for it in rows:
        if out and out[-1]["zone_dg"][1] >= it["zone_dg"][0] - 1e-9:
            a = out[-1]
            kinds = list(a["kinds"])
            for k in it["kinds"]:
                if k not in kinds:
                    kinds.append(k)
            lo = min(a["zone_dg"][0], it["zone_dg"][0])
            hi = max(a["zone_dg"][1], it["zone_dg"][1])
            price = (float(a["price"]) + float(it["price"])) / 2.0
            price_dg = round((float(a["price_dg"]) + float(it["price_dg"])) / 2.0, 2)
            a.update(price=round(price, 4), price_dg=price_dg, zone_dg=[lo, hi], kinds=kinds,
                     label_fa=label_fa(kinds, price_dg),
                     side="resistance" if price > price_bid else "support")
        else:
            out.append(it)
    return out


def short_view(lv, cfg):
    """2 levels above and 2 below, picked by distance only, after overlapping zones are merged."""
    price_bid = float(lv["price_bid"])
    atr_m5 = float(lv.get("atr_m5_14") or 0.0)
    atr_h4 = lv.get("atr_h4_14")
    half = zone_half(atr_m5)
    items = []
    for cl in lv.get("levels") or []:
        row = _from_cluster(cl, cfg, half, price_bid, atr_h4)
        if row:
            items.append(row)
    _add_structure_levels(items, lv, cfg, half, price_bid, atr_h4)
    items = merge_zones(items, price_bid)
    above = sorted((x for x in items if x["price"] > price_bid), key=lambda x: x["price"])[:N_EACH]
    below = sorted((x for x in items if x["price"] < price_bid), key=lambda x: -x["price"])[:N_EACH]
    px_now = _dg(price_bid, cfg)
    for row in list(above) + list(below):
        row["distance"] = round(row["price_dg"] - px_now, 2)
        atr = atr_m5 or None
        row["distance_atr"] = round(abs(row["distance"]) / atr, 2) if atr else None
        row["label_fa"] = label_fa(row.get("kinds") or [], row.get("price_dg"))
    return {"above": above, "below": below, "zone_width": half, "zone_half": half, "price_dg": px_now,
            "set_b": items}


def context_line(snap):
    """One plain line: how far price usually moves in 5 minutes, and the room to the next level in the
    trend direction («جا کم است» when it is under twice that move). Unclear trend: the move only."""
    atr = snap.get("atr_m5")
    if atr is None:
        return ""
    line = f"قیمت معمولاً در هر ۵ دقیقه حدود {_usd(atr)} دلار بالا و پایین می‌رود"
    overall = (snap.get("trend") or {}).get("overall")
    if overall in ("صعودی", "نزولی"):
        short = snap.get("short") or {}
        side = "above" if overall == "صعودی" else "below"
        nxt = (short.get(side) or [None])[0]
        if nxt and nxt.get("distance") is not None:
            room = abs(float(nxt["distance"]))
            line += f"؛ در جهت روند تا سطح بعدی {_usd(room)} دلار جا هست"
            if room < 2 * float(atr):
                line += " و این جا کم است"
    return line + "."


def _regime_fa(regime):
    if not regime:
        return None
    if isinstance(regime, str):
        return regime
    code = (regime.get("code") or "") if isinstance(regime, dict) else ""
    fa = (regime.get("fa") if isinstance(regime, dict) else None) or ""
    table = {
        "trend": "روند", "trend_following": "روند", "range": "رنج",
        "volatility_expansion": "گسترش نوسان", "vol_expansion": "گسترش نوسان",
        "news_abnormal": "خبری",
    }
    return table.get(code) or fa or None


def _source_short(src):
    if not src:
        return None
    s = str(src)
    if "Dukascopy" in s or "دوکاس" in s:
        return "Dukascopy"
    return s.split("(")[0].strip()[:40] or None


def _as_of_hm(snap):
    raw = snap.get("as_of_tehran") or snap.get("computed_at_tehran") or ""
    s = str(raw)
    if len(s) >= 16 and s[13] == ":":
        return s[11:16]
    if len(s) >= 5 and s[2] == ":":
        return s[:5]
    return None


def format_block(snap):
    """Shared body for every market card, phone layout in plain Persian (owner t240u-t246u; = lib.js levelsMsg):
    trend headline, news / Friday notes, a price ladder (levels above far -> near, the current price, levels below
    near -> far) with dollar distances and at most two plain origins per level, then what a level is and how far
    price usually moves in 5 minutes. No jargon (ATR, H1, OR, swing, zone), no importance labels, no disclaimer."""
    if not snap or snap.get("price_dg") is None:
        return "داده‌ی سطوح در دسترس نیست"
    lines = []
    tr = snap.get("trend") or {}
    if tr:
        g = lambda tf: (tr.get(tf) or {}).get("trend") or "خنثی"
        lines.append(trend_head(g("H4"), g("H1")))
    notes = [x for x in (snap.get("news_line"), snap.get("friday_line")) if x]
    if notes:
        lines += [""] + notes
    short = snap.get("short") or {}
    P = float(snap["price_dg"])

    def rows(items, up):
        out = []
        for r in sorted(items, key=lambda x: -float(x["price_dg"])):
            d = abs(float(r["price_dg"]) - P)
            lab = label_fa(r.get("kinds") or [], r.get("price_dg")) or r.get("label_fa")
            out.append(f"{'🔺' if up else '🔻'} `{_px(r['price_dg'])}` · {d:.1f} دلار {'بالاتر' if up else 'پایین‌تر'}")
            if lab:
                out.append(f"~~      {lab}~~")
        return out or ["—"]

    lines += ["", "**⬆️ بالای قیمت**"] + rows(short.get("above") or [], True)
    hm = _as_of_hm(snap)
    lines += ["", f"**💰 قیمت الان: `{_px(P)}`**" + (f" ~~(ساعت {hm})~~" if hm else ""), ""]
    lines += ["**⬇️ زیر قیمت**"] + rows(short.get("below") or [], False)
    lines += ["", "~~سطح = قیمتی که بازار قبلاً آنجا ایستاده یا برگشته؛ نزدیک سطح‌ها قیمت ممکن است بایستد یا برگردد.~~"]
    ctx = context_line(snap)
    if ctx:
        lines.append(f"~~{ctx}~~")
    return "\n".join(lines)


def snapshot(lv, cfg, now=None, context=None):
    """One stored object: short view, trend, context line, and the exact block every card prints."""
    now = now or datetime.now(TEH)
    ctx = context or {}
    tr = trend_of(lv)
    short = short_view(lv, cfg)
    snap = {
        "computed_at_tehran": now.strftime("%Y-%m-%d %H:%M:%S"),
        "as_of_tehran": lv.get("as_of_tehran"),
        "source": ctx.get("source") or lv.get("source"),
        "regime": ctx.get("regime"),
        "news_window": ctx.get("news_window"),
        "invalidation": ctx.get("invalidation"),
        "price_bid": float(lv["price_bid"]),
        "price_dg": short["price_dg"],
        "offset": float(cfg.get("price_offset_usd") or DG.offset_usd(cfg) or 0.195),
        "atr_h1": lv.get("atr_h1_14"),
        "atr_h4": lv.get("atr_h4_14"),
        "atr_m5": lv.get("atr_m5_14"),
        "zone_width": short["zone_width"],
        "zone_half": short.get("zone_half") or short["zone_width"],
        "trend": tr,
        "short": {"above": short["above"], "below": short["below"]},
        "full_n": len(lv.get("levels") or []),
        "set_b_n": len(short.get("set_b") or []),
    }
    st = lv.get("structure") or {}
    if st.get("adr") is not None:
        snap["adr"] = st.get("adr")
        snap["today_range"] = st.get("today_range")
        snap["adr_used_pct"] = st.get("adr_used_pct")
    nw = snap.get("news_window") or {}
    if nw.get("inside") and nw.get("end"):
        end = str(nw.get("end"))[-5:]
        snap["news_line"] = f"خبر: پنجره‌ی جاری تا {end}"
    elif nw.get("next_start"):
        snap["news_line"] = f"خبر بعدی: {str(nw.get('next_start'))[-5:]}–{str(nw.get('next_end') or '')[-5:]}"
    snap["friday_line"] = ctx.get("friday_line")
    snap["context"] = context_line(snap)
    snap["block"] = format_block(snap)
    snap["nearest"] = {
        "above": (short["above"][0] if short["above"] else None),
        "below": (short["below"][0] if short["below"] else None),
    }
    return snap


def age_minutes(snap, now=None):
    if not snap or not snap.get("computed_at_tehran"):
        return None
    now = now or datetime.now(TEH)
    try:
        t = datetime.strptime(snap["computed_at_tehran"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TEH)
    except ValueError:
        return None
    return (now - t).total_seconds() / 60.0


def is_fresh(snap, now=None, limit=FRESH_MIN):
    age = age_minutes(snap, now)
    return age is not None and 0 <= age <= limit
