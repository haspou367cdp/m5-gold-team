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

KIND_FA = {
    "PDH": "PDH", "PDL": "PDL",
    "Week high": "سقف هفته", "Week low": "کف هفته",
    "Prev week high": "سقف هفته‌ی قبل", "Prev week low": "کف هفته‌ی قبل",
    "Asia high": "سقف آسیا", "Asia low": "کف آسیا",
    "London high": "سقف لندن", "London low": "کف لندن",
    "NY high": "سقف نیویورک", "NY low": "کف نیویورک",
    "Prev NY high": "سقف نیویورک دیروز", "Prev NY low": "کف نیویورک دیروز",
    "H1 swing high": "سوئینگ H1", "H1 swing low": "سوئینگ H1",
    "Round $100": "رُند", "Round $50": "رُند",
    "London OR high": "OR لندن", "London OR low": "OR لندن",
    "NY OR high": "OR نیویورک", "NY OR low": "OR نیویورک",
    "VWAP": "VWAP",
    "Equal high": "سقف برابر", "Equal low": "کف برابر",
    "Month high": "سقف ماه", "Month low": "کف ماه",
    "Prev month high": "سقف ماه قبل", "Prev month low": "کف ماه قبل",
}
# Stable label order when several sources coincide.
_KIND_ORDER = [
    "PDH", "PDL", "Week high", "Week low", "Prev week high", "Prev week low",
    "Asia high", "Asia low", "London high", "London low", "NY high", "NY low",
    "Prev NY high", "Prev NY low",
    "London OR high", "London OR low", "NY OR high", "NY OR low",
    "H1 swing high", "H1 swing low", "Equal high", "Equal low", "VWAP",
    "Round $100", "Round $50",
    "Month high", "Month low", "Prev month high", "Prev month low",
]
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


def label_fa(kinds, price_dg=None):
    seen, out = set(), []
    for k in sorted(kinds, key=lambda x: _KIND_ORDER.index(x) if x in _KIND_ORDER else 99):
        lab = KIND_FA.get(k)
        if k in ("Round $100", "Round $50") and price_dg is not None:
            lab = f"رُند {int(round(float(price_dg) / 50.0) * 50)}"
        if lab and lab not in seen:
            seen.add(lab)
            out.append(lab)
    return " + ".join(out)


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
    """One short line under the verdict: M5 ATR, and room to the next level in the trend direction.
    If that room is less than 2× ATR M5, append «جا کم است». If the trend is نامشخص, volatility only."""
    atr = snap.get("atr_m5")
    if atr is None:
        return ""
    parts = [f"نوسان M5 حدود {_usd(atr)} دلار"]
    overall = (snap.get("trend") or {}).get("overall")
    if overall in ("صعودی", "نزولی"):
        short = snap.get("short") or {}
        side = "above" if overall == "صعودی" else "below"
        nxt = (short.get(side) or [None])[0]
        if nxt and nxt.get("distance") is not None:
            room = abs(float(nxt["distance"]))
            bit = f"تا سطح بعدی {_usd(room)} دلار"
            if room < 2 * float(atr):
                bit += "؛ جا کم است"
            parts.append(bit)
    return " · ".join(parts)


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
    """Shared body for every market card: price, source, as-of, regime, HTF, news, Friday,
    four-frame trend, zone width, 2 above + 2 below. No importance labels, no M15 touch count,
    no disclaimer."""
    if not snap or snap.get("price_dg") is None:
        return "داده‌ی سطوح در دسترس نیست"
    lines = []
    head = f"طلا  `{_px(snap['price_dg'])}`  ·  دریاگلد"
    hm = _as_of_hm(snap)
    if hm:
        head += f"  ·  {hm} به وقت تهران"
    lines.append(head)
    src = _source_short(snap.get("source"))
    if src:
        lines.append(f"منبع: {src}")
    reg = _regime_fa(snap.get("regime"))
    htf = (snap.get("trend") or {}).get("overall")
    meta = []
    if reg:
        meta.append(f"رژیم: {reg}")
    if htf:
        meta.append(f"جهت: {htf}")
    if meta:
        lines.append("  ·  ".join(meta))
    if snap.get("news_line"):
        lines.append(snap["news_line"])
    if snap.get("friday_line"):
        lines.append(snap["friday_line"])
    tr = snap.get("trend") or {}
    lines.append("  ·  ".join(f"{tf} {(tr.get(tf) or {}).get('trend') or 'خنثی'}" for tf in TFS))
    verdict = tr.get("verdict")
    if verdict:
        lines.append(verdict)
    half = snap.get("zone_half") or snap.get("zone_width")
    if half:
        lines.append(f"پهنه سطح  ±{float(half):.1f} دلار")
    ctx = snap.get("context") or context_line(snap)
    if ctx:
        lines.append(ctx)
    short = snap.get("short") or {}
    atr = snap.get("atr_m5")
    for title, rows in (("بالا", short.get("above") or []),
                        ("پایین", short.get("below") or [])):
        lines.append("")
        lines.append(title)
        if not rows:
            lines.append("—")
            continue
        for r in rows:
            d = float(r.get("distance") or 0)
            sign = "−" if d < 0 else "+"
            dist = f"{sign}{abs(d):.1f}$"
            da = r.get("distance_atr")
            if da is None and atr:
                da = round(abs(d) / float(atr), 2)
            atr_bit = f" ≈ {da:.1f} ATR" if da is not None else ""
            lab = r.get("label_fa") or label_fa(r.get("kinds") or [], r.get("price_dg"))
            lines.append(f"▸ `{_px(r['price_dg'])}`  {dist}{atr_bit}")
            if lab:
                lines.append(f"  {lab}")
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
        "offset": float(cfg.get("price_offset_usd") or DG.offset_usd(cfg) or 0.3),
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
