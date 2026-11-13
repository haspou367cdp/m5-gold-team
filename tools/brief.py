#!/usr/bin/env python3
"""brief.py - ONE command for the team: fetch -> levels -> bias -> macro -> regime -> Persian brief.

Prints: تصمیم BUY/SELL/NO TRADE | علت پذیرش/رد | رژیم و موتور مجاز | جهت (H4/H1/M15) | ADR
        | سقف/کف مرجع (روز، هفته، ماه، سشن، رنج بازگشایی) | ماکرو | دروازه‌های ریسک
        | سقف‌ها و کف‌ها (بدون برچسب قوی/متوسط) | سطح ابطال | منبع + زمان داده
Data-quality gate: if price data is missing, or older than 10 minutes while the market is open,
the brief prints NO TRADE / stop and does not emit a full analysis.
Writes : /workspace/m5-gold-team/latest_brief.md  and  /workspace/m5-gold-team/latest_brief.json
Level ranks are unvalidated and are not printed. Signal-only research, not financial advice.
usage  : python3 brief.py [--no-fetch] [--days N] [--n 4] [--at "YYYY-MM-DD HH:MM"]
exit   : 0 ok | 2 stale / no-trade data gate (short brief written) | 3 no data at all"""
import argparse, csv, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
sys.path.insert(0, "/workspace/m5-gold-team/tools")
from m5lib import ROOT, TOOLS, TEH, META_JSON, DATA, load_json, save_json, market_open, now_utc
import pandas as pd
import levels as LV, bias as BI, news_windows as nw, macro as MAC
import regime as REG

FA_B = {"bullish": "صعودی ⬆️", "bearish": "نزولی ⬇️", "neutral": "خنثی ↔️"}
STALE_MIN = 10  # minutes, while the market is open
DISCLAIMER = "_سطح‌ها و جهت تاییدنشده‌اند و برتری آماری ندارند. این تحلیل است، نه توصیه‌ی مالی._"

def fmt(p):
    if p is None:
        return "—"
    return f"{float(p):.2f}".rstrip("0").rstrip(".")

def pick(levels, side, n):
    # still skip very weak isolated rounds so the brief stays short; ranks are NOT shown
    L = [l for l in levels if l["side"] == side]
    L.sort(key=lambda l: abs(l["distance"]))
    good = [l for l in L if l["strength"] in ("strong", "medium")][:n]
    return good

def label(l):
    k = " ".join(l["kinds"]); has_lo, has_hi = " low" in k, " high" in k
    if l["side"] == "resistance" and has_lo and not has_hi: return "کف شکسته‌شده (حالا مقاومت): " + l["label_fa"]
    if l["side"] == "support" and has_hi and not has_lo: return "سقف شکسته‌شده (حالا حمایت): " + l["label_fa"]
    return l["label_fa"]

def _macro_cached_or_empty():
    cached = MAC._read_cache()
    if cached is None:
        return {"ok": False, "dxy": {"unavailable": True}, "us10y": {"unavailable": True},
                "us2y": {"unavailable": True}, "real10y": {"unavailable": True},
                "be5": {"unavailable": True}, "be10": {"unavailable": True},
                "gold_lean": {"fa": "در دسترس نیست"}}
    if MAC._age_s(cached) > MAC.TTL:
        out = dict(cached); out["stale"] = True; out["from_cache"] = True
        return out
    out = dict(cached); out["from_cache"] = True
    return out

def _live_age_minutes(meta):
    """Minutes since last completed 1m bar close, computed from now — not the cached age_minutes field."""
    last_open = meta.get("last_bar_open_utc")
    now = pd.Timestamp(now_utc())
    if last_open:
        lo = pd.Timestamp(last_open)
        if lo.tzinfo is None:
            lo = lo.tz_localize("UTC")
        return (now - (lo + pd.Timedelta(minutes=1))).total_seconds() / 60.0
    as_of = meta.get("as_of_tehran")
    if as_of:
        try:
            t = datetime.strptime(as_of, "%Y-%m-%d %H:%M").replace(tzinfo=TEH)
            return (datetime.now(TEH) - t).total_seconds() / 60.0
        except ValueError:
            pass
    try:
        return float(meta["age_minutes"]) if meta.get("age_minutes") is not None else None
    except (TypeError, ValueError):
        return None

def quality_gate(meta):
    """Fail closed: missing or stale (>10 min in-session) price data => NO TRADE / stop."""
    if not meta or (not meta.get("source") and not meta.get("as_of_tehran") and not meta.get("ok")):
        return {"ok": False, "code": "missing",
                "fa": "داده‌ی قیمت موجود نیست؛ توقف. تصمیم: NO TRADE."}
    age_f = _live_age_minutes(meta)
    open_ = bool(market_open(now_utc()))
    stale = (open_ and age_f is not None and age_f > STALE_MIN)
    if stale and open_:
        shown = f"{age_f:.1f}" if age_f is not None else "؟"
        return {"ok": False, "code": "stale",
                "fa": f"داده‌ی قیمت کهنه است (سن {shown} دقیقه، حد {STALE_MIN} دقیقه در سشن)؛ توقف. تصمیم: NO TRADE."}
    if meta.get("ok") is False and open_ and (age_f is None or age_f > STALE_MIN):
        return {"ok": False, "code": "unusable",
                "fa": "داده‌ی قیمت قابل استفاده نیست؛ توقف. تصمیم: NO TRADE."}
    if age_f is not None:
        return {"ok": True, "code": "ok", "fa": f"تازه (سن {age_f:.1f} دقیقه)", "age_minutes": round(age_f, 1)}
    return {"ok": True, "code": "ok", "fa": "تازه"}

def daily_risk_note():
    """Hard daily stop is always printed. If today's journal has closed losses, mention the count."""
    path = f"{ROOT}/journal.csv"
    if not os.path.exists(path):
        return "در ژورنال معامله‌ی بسته‌شده‌ای برای امروز دیده نشد."
    today = datetime.now(TEH).strftime("%Y-%m-%d")
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
        return "خواندن ژورنال امروز ممکن نشد."
    if losses:
        return f"در ژورنال امروز {losses} ضرر بسته‌شده ثبت شده است."
    return "در ژورنال معامله‌ی بسته‌شده‌ای برای امروز دیده نشد."

def risk_lines(spread):
    sp = spread or {}
    cur = sp.get("current")
    typ = sp.get("typical_this_hour")
    cur_s = f"{cur:.2f}" if isinstance(cur, (int, float)) else "نامعلوم"
    typ_s = f"{typ:.2f}" if isinstance(typ, (int, float)) else "نامعلوم"
    flag = " — الان غیرعادی است، ورود ممنوع" if sp.get("abnormal") else ""
    known = "" if sp.get("known") is not False else " (اسپرد در این منبع موجود نیست)"
    return (f"**دروازه‌های ریسک (اجباری، حساب ۵۰۰ دلار، حجم ۰٫۰۱ لات):** "
            f"اسپرد فعلی {cur_s} دلار / معمول این ساعت {typ_s} دلار "
            f"(حد: بیشتر از ۲ برابر معمول همین ساعت و هم‌زمان بالاتر از ۰٫۸۰ دلار → ورود ممنوع){flag}{known} · "
            f"حد ضرر حداکثر ۵ دلار با حجم ۰٫۰۱ لات · نسبت پاداش به ریسک حداقل ۱٫۵ · "
            f"توقف روز بعد از ۳ ضرر یا ۱۰ دلار ضرر. "
            + daily_risk_note())

def _write(md, payload, rc):
    print(md)
    with open(f"{ROOT}/latest_brief.md", "w", encoding="utf-8") as f:
        f.write(md + "\n")
    save_json(f"{ROOT}/latest_brief.json", payload)
    sys.exit(rc)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-fetch", action="store_true", help="use cached price + macro (no download)")
    ap.add_argument("--days", default=None, help="price look-back in calendar days (default: 3 if cache already covers ~21 calendar days, else 21)")
    ap.add_argument("--n", type=int, default=4, help="levels per side")
    ap.add_argument("--at", help="evaluate news windows at Tehran time (testing)")
    a = ap.parse_args()
    rc = 0
    if a.days is None:
        # Need ~21 calendar days for 14 full gold sessions; reuse a deep cache and only fetch a short tail.
        try:
            import pandas as pd
            p1 = f"{DATA}/xauusd_1m.parquet"
            if os.path.exists(p1):
                idx = pd.read_parquet(p1, columns=["c_b"]).index
                span = (idx[-1] - idx[0]).days if len(idx) else 0
                a.days = "3" if span >= 20 else "21"
            else:
                a.days = "21"
        except Exception:
            a.days = "21"
    if a.no_fetch:
        macro = _macro_cached_or_empty()
    else:
        # price fetch and macro fetch in parallel (macro has its own 10s budget + 10-min cache)
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_macro = ex.submit(MAC.fetch, False)
            fut_px = ex.submit(subprocess.run, [sys.executable, f"{TOOLS}/fetch_xauusd.py",
                                                 "--days", a.days, "--max-age", str(STALE_MIN), "--quiet"])
            rc = fut_px.result().returncode
            if rc == 3:
                print("⛔ هیچ منبع داده‌ای در دسترس نیست؛ بریف تولید نشد. تصمیم: NO TRADE.")
                sys.exit(3)
            try:
                macro = fut_macro.result(timeout=14)
            except Exception:
                macro = _macro_cached_or_empty()

    meta = load_json(META_JSON, {}) or {}
    q = quality_gate(meta)
    now = datetime.now(TEH)
    header = f"**بریف XAUUSD (M5)** · {now.strftime('%Y-%m-%d %H:%M:%S')} به وقت تهران"
    if not q["ok"]:
        md = "\n".join([
            header,
            "**تصمیم: NO TRADE**",
            f"**علت رد:** {q['fa']}",
            "تحلیل کامل تا به‌روز شدن داده متوقف شد.",
            DISCLAIMER,
        ])
        _write(md, {
            "generated_at_tehran": now.strftime("%Y-%m-%d %H:%M:%S"),
            "decision": "NO TRADE", "quality": q, "stale": True,
            "as_of_tehran": meta.get("as_of_tehran"), "source": meta.get("source"),
            "markdown": md,
        }, 2)

    lv = LV.compute(); save_json(LV.LEVELS_JSON, lv)
    at = datetime.strptime(a.at, "%Y-%m-%d %H:%M").replace(tzinfo=TEH) if a.at else None
    b = BI.compute(at); save_json(BI.BIAS_JSON, b)
    res = pick(lv["levels"], "resistance", a.n); sup = pick(lv["levels"], "support", a.n)
    v = b["verdict"]; inv = b.get("invalidation") or {}
    regime = REG.classify(lv, win=b.get("news_window"), spread=b.get("spread"),
                          h4=b.get("h4"), h1=b.get("h1"))
    decision = REG.decide(lv, b, regime, quality=q)

    h4t = (b.get("h4") or {}).get("trend", "neutral")
    lines = [
        f"**بریف XAUUSD (M5)** · {b['evaluated_at_tehran']} به وقت تهران",
        f"**تصمیم: {decision['decision']}**",
    ]
    if decision["decision"] in ("BUY", "SELL"):
        lines.append(f"**موتور:** {decision.get('engine_fa')} (تأییدنشده؛ بک‌تست خارج از نمونه جدا لازم است)")
        if decision.get("reasons_accept"):
            lines.append("**علت پذیرش:** " + " ".join(decision["reasons_accept"]))
        if decision.get("reasons_reject"):
            lines.append("**علت احتیاط:** " + " ".join(decision["reasons_reject"]))
    else:
        reasons = decision.get("reasons_reject") or [v.get("fa") or "صبر."]
        lines.append("**علت رد:** " + " ".join(reasons))
        if decision.get("reasons_accept"):
            lines.append("**یادداشت:** " + " ".join(decision["reasons_accept"]))
    if v.get("note_fa"):
        lines.append(f"⚠️ {v['note_fa']}")
    if v.get("news_caution_fa"):
        lines.append(f"⚠️ {v['news_caution_fa']}")

    lines.append(f"**جهت:** {FA_B[b['bias']]}  (H4 {FA_B[h4t].split()[0]}، "
                 f"H1 {FA_B[b['h1']['trend']].split()[0]}، M15 {FA_B[b['m15']['trend']].split()[0]}؛ "
                 f"بایاس خبری M5-News: {FA_B.get(b['news_bias'], '—').split()[0] if b['news_bias'] else 'ثبت نشده'})")
    lines.append(f"**قیمت:** {fmt(lv['price_bid'])} ({'فیوچرز GC=F' if meta.get('fallback') else 'bid'})  ·  "
                 f"ATR پنج‌دقیقه: {lv['atr_m5_14']} دلار · کیفیت داده: {q['fa']}")
    lines.append(risk_lines(b.get("spread")))
    lines += MAC.fa_lines(macro, lv, b.get("news_window"), regime)
    lines += REG.fa_indicator_lines(regime)

    # equal highs / lows (M15)
    eq = lv.get("equal") or {}
    eq_bits = []
    if eq.get("highs"):
        eq_bits.append("سقف " + "، ".join(f"{e['price']:.2f} (n={e['n']})" for e in eq["highs"][:3]))
    if eq.get("lows"):
        eq_bits.append("کف " + "، ".join(f"{e['price']:.2f} (n={e['n']})" for e in eq["lows"][:3]))
    if eq_bits:
        lines.append("**برابری سقف/کف M15:** " + " · ".join(eq_bits) + f" · آستانه {eq.get('tolerance')} دلار")

    lines.append("**سقف‌های نزدیک:**")
    lines += [f"- {fmt(l['price'])} · {label(l)}" for l in res] or ["- (سطح نزدیکی در محدوده نیست)"]
    lines.append("**کف‌های نزدیک:**")
    lines += [f"- {fmt(l['price'])} · {label(l)}" for l in sup] or ["- (سطح نزدیکی در محدوده نیست)"]
    if inv:
        word = "بالای" if b["bias"] == "bearish" or (b["bias"] == "neutral" and b["technical_bias"] == "bearish") else "زیر"
        lines.append(f"**ابطال جهت:** بسته شدن کندل M15 {word} {fmt(inv['neutral_level'])} → خنثی؛ "
                     f"بسته شدن کندل H1 {word} {fmt(inv['off_level'])} → جهت باطل." if inv.get("off_level") else
                     f"**ابطال جهت:** بسته شدن کندل M15 {word} {fmt(inv['neutral_level'])} → خنثی.")
    if b.get("news_invalidation"):
        lines.append(f"**ابطال خبری (M5-News):** {b['news_invalidation']}")

    now_eval = at or datetime.now(TEH)
    wins = []
    for s, e, meta_w in nw.merged(nw.load()):
        if e > now_eval and (s - now_eval).total_seconds() < 86400:
            tag = {"block": "بلوک", "caution": "احتیاط", "monitor": "پایش"}.get(meta_w.get("action"), meta_w.get("action") or "")
            wins.append(f"{s:%H:%M}–{e:%H:%M} (سطح {meta_w.get('tier')}، {tag})")
    if wins:
        lines.append("**پنجره‌های خبری (تهران، ۲۴ ساعت آینده):** " + "، ".join(wins))

    src = meta.get("source", "?"); fb = " ⚠️ منبع جایگزین" if meta.get("fallback") else ""
    lines.append(f"**منبع:** {src}{fb} · داده تا {meta.get('as_of_tehran')} به وقت تهران"
                 + (" · ⛔ داده کهنه است" if meta.get("stale") else "")
                 + (" · ⚠️ این قیمت فیوچرز COMEX است نه اسپات؛ با بروکر چند دلار فرق دارد و اسپرد نامعلوم است." if meta.get("fallback")
                    else " · قیمت‌ها bid هستند و با بروکر حدود ۱ دلار فرق دارند."))
    lines.append(DISCLAIMER)
    md = "\n".join(lines)
    payload = {
        "generated_at_tehran": datetime.now(TEH).strftime("%Y-%m-%d %H:%M:%S"),
        "evaluated_at_tehran": b["evaluated_at_tehran"],
        "as_of_tehran": meta.get("as_of_tehran"), "source": src, "fallback": meta.get("fallback"),
        "stale": meta.get("stale"), "quality": q,
        "price_bid": lv["price_bid"], "price_ask": lv.get("price_ask"), "atr_m5": lv["atr_m5_14"],
        "bias": b["bias"], "technical_bias": b["technical_bias"], "technical_confidence": b["technical_confidence"],
        "news_bias": b["news_bias"], "h4": b.get("h4"), "h1": b["h1"], "m15": b["m15"],
        "verdict": v, "decision": decision, "regime": regime, "macro": macro,
        "resistances": res, "supports": sup, "invalidation": inv, "news_window": b["news_window"],
        "spread": b["spread"], "structure": lv.get("structure"),
        "opening_ranges": lv.get("opening_ranges"), "equal": lv.get("equal"),
        "session_vwap": lv.get("session_vwap"),
        "news_windows_next_24h": wins, "markdown": md,
    }
    _write(md, payload, 0)

if __name__ == "__main__":
    main()
