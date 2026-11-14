#!/usr/bin/env python3
"""One shared levels + trend snapshot for every Telegram consumer.

compute() in levels.py stays the single source of the FULL level set (signal engine reads that,
unchanged). This module builds a filtered short view (set B) and the H4/H1 trend from that same
result, once per run. /levels, /brief, /scan and the pre-session briefs all render the same block
from the stored snapshot. Research / display only; never changes a live signal gate.
"""
from __future__ import annotations
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "/workspace/m5-gold-team/tools")
import broker_daryagold as DG

TEH = ZoneInfo("Asia/Tehran")

# Short set B: structural types only. Opening-range H/L were added after the 2026-11-13
# trade review (London OR low sat on the H4 swing that framed M3/M4). M5/M15 swings,
# VWAP, EMA and $5/$10 rounds stayed out — they hugged price as noise.
SET_B = frozenset({
    "PDH", "PDL",
    "Prev week high", "Prev week low",
    "Asia high", "Asia low", "London high", "London low",
    "H4 swing high", "H4 swing low", "H1 swing high", "H1 swing low",
    "Round $100", "Round $50",
    "London OR high", "London OR low", "NY OR high", "NY OR low",
})

KIND_FA = {
    "PDH": "سقف دیروز", "PDL": "کف دیروز",
    "Prev week high": "سقف هفته‌ی قبل", "Prev week low": "کف هفته‌ی قبل",
    "Asia high": "سقف آسیا", "Asia low": "کف آسیا",
    "London high": "سقف لندن", "London low": "کف لندن",
    "H4 swing high": "سوئینگ H4", "H4 swing low": "سوئینگ H4",
    "H1 swing high": "سوئینگ H1", "H1 swing low": "سوئینگ H1",
    "Round $100": "عدد رُند", "Round $50": "عدد رُند",
    "London OR high": "بازگشایی لندن", "London OR low": "بازگشایی لندن",
    "NY OR high": "بازگشایی نیویورک", "NY OR low": "بازگشایی نیویورک",
}
# Stable label order when several sources coincide.
_KIND_ORDER = [
    "PDH", "PDL", "Prev week high", "Prev week low",
    "Asia high", "Asia low", "London high", "London low",
    "London OR high", "London OR low", "NY OR high", "NY OR low",
    "H4 swing high", "H4 swing low", "H1 swing high", "H1 swing low",
    "Round $100", "Round $50",
]

TAG = {"strong": "خیلی مهم", "medium": "مهم"}  # else معمولی; never «قوی»
N_EACH = 2
FRESH_MIN = 15  # Edge Function serves a stored snapshot newer than this; otherwise queues a run


def _dg(price, cfg):
    if price is None:
        return None
    return round(float(DG.to_broker(float(price), cfg)), 2)


def _px(dg):
    """One-decimal Latin price for tap-to-copy (same convention as bot.p1)."""
    if dg is None:
        return "—"
    return f"{float(dg):.1f}"


def tag_fa(strength):
    return TAG.get(strength, "معمولی")


def label_fa(kinds):
    seen, out = set(), []
    for k in sorted(kinds, key=lambda x: _KIND_ORDER.index(x) if x in _KIND_ORDER else 99):
        lab = KIND_FA.get(k)
        if lab and lab not in seen:
            seen.add(lab)
            out.append(lab)
    return " + ".join(out)


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


def trend_of(lv):
    """H4 and H1 trend from confirmed swings + EMA20/50. Disagree → روند نامشخص."""
    out = {}
    for tf in ("H4", "H1"):
        em = (lv.get("ema") or {}).get(tf)
        sw = (lv.get("swings") or {}).get(tf) or {}
        eb, ewhy = _ema_bias(em)
        st, swhy = _swing_struct(sw)
        tr = _tf_trend(st, eb)
        out[tf] = {"trend": tr, "structure": st, "structure_why": swhy, "ema": eb, "ema_why": ewhy,
                   "ema20": (em or {}).get("ema20"), "ema50": (em or {}).get("ema50"),
                   "close": (em or {}).get("close")}
    disagree = out["H4"]["trend"] != out["H1"]["trend"]
    out["overall"] = "روند نامشخص" if disagree else out["H4"]["trend"]
    out["disagree"] = disagree
    return out


def _zone(price_dg, width):
    half = width / 2.0
    return [round(price_dg - half, 2), round(price_dg + half, 2)]


def _from_cluster(cl, cfg, width, price_bid):
    kinds = [k for k in (cl.get("kinds") or []) if k in SET_B]
    if not kinds:
        return None
    price = float(cl["price"])
    price_dg = _dg(price, cfg)
    return {
        "price": price,
        "price_dg": price_dg,
        "zone_dg": _zone(price_dg, width),
        "side": "resistance" if price > price_bid else "support",
        "kinds": kinds,
        "label_fa": label_fa(kinds),
        "touches_m15_3d": int(cl.get("touches_m15_3d") or 0),
        "strength": cl.get("strength") or "weak",
        "tag": tag_fa(cl.get("strength")),
        "score": cl.get("score"),  # stored only; never printed
    }


def _add_prev_week(items, lv, cfg, width, price_bid, tol):
    """Prev week H/L live in compute()'s structure, not in the cluster list — include without
    changing the full candidate set (signal inputs stay the same). Merge when within cluster tol."""
    pw = (lv.get("structure") or {}).get("prev_week") or {}
    if pw.get("high") is None:
        return
    for kind, key in (("Prev week high", "high"), ("Prev week low", "low")):
        p = float(pw[key])
        # already represented in a short cluster?
        if any(abs(it["price"] - p) <= tol and kind in (it.get("kinds") or []) for it in items):
            continue
        merged = False
        for it in items:
            if abs(it["price"] - p) <= tol:
                if kind not in it["kinds"]:
                    it["kinds"].append(kind)
                    it["label_fa"] = label_fa(it["kinds"])
                merged = True
                break
        if merged:
            continue
        price_dg = _dg(p, cfg)
        items.append({
            "price": p, "price_dg": price_dg, "zone_dg": _zone(price_dg, width),
            "side": "resistance" if p > price_bid else "support",
            "kinds": [kind], "label_fa": label_fa([kind]),
            "touches_m15_3d": 0, "strength": "medium", "tag": tag_fa("medium"),
        })


def short_view(lv, cfg):
    """2 levels above and 2 below, filtered from the same compute() clusters (plus prev-week)."""
    price_bid = float(lv["price_bid"])
    atr_h1 = float(lv.get("atr_h1_14") or 8.0)
    width = max(0.2, round(0.1 * atr_h1, 2))
    tol = float(lv.get("cluster_tol") or max(0.5, 0.25 * float(lv.get("atr_m5_14") or 2)))
    items = []
    for cl in lv.get("levels") or []:
        row = _from_cluster(cl, cfg, width, price_bid)
        if row:
            items.append(row)
    _add_prev_week(items, lv, cfg, width, price_bid, tol)
    above = sorted((x for x in items if x["price"] > price_bid), key=lambda x: x["price"])[:N_EACH]
    below = sorted((x for x in items if x["price"] < price_bid), key=lambda x: -x["price"])[:N_EACH]
    # distances from the current DaryaGold price
    px_now = _dg(price_bid, cfg)
    for row in list(above) + list(below):
        row["distance"] = round(row["price_dg"] - px_now, 2)
    return {"above": above, "below": below, "zone_width": width, "price_dg": px_now}


def format_block(snap):
    """Shared body: price, trend, 2 above, 2 below. No title (callers add their own)."""
    if not snap or snap.get("price_dg") is None:
        return "داده‌ی سطوح در دسترس نیست"
    lines = [f"طلا  `{_px(snap['price_dg'])}`"]
    tr = snap.get("trend") or {}
    h4 = (tr.get("H4") or {}).get("trend") or "خنثی"
    h1 = (tr.get("H1") or {}).get("trend") or "خنثی"
    if tr.get("disagree") or tr.get("overall") == "روند نامشخص":
        lines.append(f"H4 {h4}  ·  H1 {h1}  ·  روند نامشخص")
    else:
        lines.append(f"H4 {h4}  ·  H1 {h1}")
    short = snap.get("short") or {}
    for title, rows, sign_hint in (("بالا", short.get("above") or [], "+"),
                                   ("پایین", short.get("below") or [], "−")):
        lines.append("")
        lines.append(title)
        if not rows:
            lines.append("—")
            continue
        for r in rows:
            d = float(r.get("distance") or 0)
            sign = "−" if d < 0 else "+"
            dist = f"{sign}{abs(d):.1f}"
            z = r.get("zone_dg") or [r["price_dg"], r["price_dg"]]
            lab = r.get("label_fa") or ""
            touches = int(r.get("touches_m15_3d") or 0)
            tag = r.get("tag") or tag_fa(r.get("strength"))
            lines.append(f"▸ `{_px(r['price_dg'])}`  ({dist})  {tag}")
            extra = lab
            if extra:
                extra += f"  ·  {touches} تماس M15"
            else:
                extra = f"{touches} تماس M15"
            lines.append(f"  {extra}")
            lines.append(f"  پهنه  `{_px(z[0])}`–`{_px(z[1])}`")
    return "\n".join(lines)


def snapshot(lv, cfg, now=None):
    """One stored object: short view, trend, and the exact block every card prints."""
    now = now or datetime.now(TEH)
    tr = trend_of(lv)
    short = short_view(lv, cfg)
    snap = {
        "computed_at_tehran": now.strftime("%Y-%m-%d %H:%M:%S"),
        "as_of_tehran": lv.get("as_of_tehran"),
        "price_bid": float(lv["price_bid"]),
        "price_dg": short["price_dg"],
        "offset": float(cfg.get("price_offset_usd") or DG.offset_usd(cfg) or 0.3),
        "atr_h1": lv.get("atr_h1_14"),
        "atr_m5": lv.get("atr_m5_14"),
        "zone_width": short["zone_width"],
        "trend": tr,
        "short": {"above": short["above"], "below": short["below"]},
        "full_n": len(lv.get("levels") or []),
    }
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
