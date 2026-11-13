#!/usr/bin/env python3
"""brief.py - ONE command for the team: fetch -> levels -> bias -> macro -> regime -> Persian brief.

Prints: one final تصمیم BUY/SELL/NO TRADE (only if bias, regime, news, data and Friday/session gates all agree; otherwise NO TRADE + blocking reason) | علت پذیرش/رد | رژیم و موتور مجاز | جهت (H4/H1/M15) | ADR
        | سقف/کف مرجع (روز، هفته، ماه، سشن، رنج بازگشایی) | ماکرو | دروازه‌های ریسک دریاگلد
        | سقف‌ها و کف‌ها (بدون برچسب قوی/متوسط) | سطح ابطال | منبع + زمان داده
Prices are shown in DaryaGold terms (Dukascopy bid + price_offset_usd) with the raw bid in brackets.
Data-quality gate: if price data is missing, or older than 10 minutes while the market is open,
the brief prints NO TRADE / stop and does not emit a full analysis.
Writes : /workspace/m5-gold-team/latest_brief.md  and  /workspace/m5-gold-team/latest_brief.json
Level ranks are unvalidated and are not printed. Signal-only research, not financial advice.
usage  : python3 brief.py [--no-fetch] [--days N] [--n 4] [--at "YYYY-MM-DD HH:MM"] [--equity TOMAN]
exit   : 0 ok | 2 stale / no-trade data gate (short brief written) | 3 no data at all"""
import argparse, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
sys.path.insert(0, "/workspace/m5-gold-team/tools")
from m5lib import ROOT, TOOLS, TEH, META_JSON, DATA, load_json, save_json, market_open, now_utc, month_starts_utc
import pandas as pd
import levels as LV, bias as BI, news_windows as nw, macro as MAC
import regime as REG
import broker_daryagold as DG

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

def _write(md, payload, rc):
    print(md)
    with open(f"{ROOT}/latest_brief.md", "w", encoding="utf-8") as f:
        f.write(md + "\n")
    save_json(f"{ROOT}/latest_brief.json", payload)
    sys.exit(rc)

def _apply_broker_gates(decision, lv, b, cfg, session):
    """Size any engine setup and apply DaryaGold vetoes (daily stop, forex/Friday close, sizing)."""
    vetoes = []
    day_veto, day_why, journal = DG.daily_loss_veto(cfg)
    if day_veto:
        vetoes.append(day_why)
    if session.get("blocked"):
        vetoes.append(session["reason_fa"])
    setup = (decision or {}).get("setup")
    plan, sizing = None, None
    if setup and decision.get("decision") in ("BUY", "SELL"):
        if setup.get("entry") is not None and setup.get("sl") is not None:
            plan = {"side": decision["decision"], "entry": float(setup["entry"]),
                    "sl": float(setup["sl"]), "tp": setup.get("tp"),
                    "entry_type": cfg.get("entry_type"), "source": "setup", "unvalidated": True}
        else:
            plan = DG.plan_from_setup(setup, lv, cfg)
        if plan:
            spread = (b.get("spread") or {}).get("current")
            sizing = DG.size_trade(plan["entry"], plan["sl"], plan.get("tp"), plan["side"],
                                   cfg, spread_usd=spread)
            if not sizing.get("ok"):
                vetoes.append(sizing["reason_fa"])
    out = dict(decision or {})
    if vetoes:
        if out.get("decision") in ("BUY", "SELL"):
            out["decision"] = "NO TRADE"
            out["broker_veto"] = True
            out["setup"] = None
            plan, sizing = None, None
        existing = list(out.get("reasons_reject") or [])
        for v in vetoes:
            if v not in existing:
                existing.append(v)
        out["reasons_reject"] = existing
    # Never attach a trade plan to a NO TRADE verdict
    if out.get("decision") not in ("BUY", "SELL"):
        plan, sizing = None, None
        out["setup"] = None
    out["plan"] = plan
    out["sizing"] = sizing
    out["journal"] = journal
    return out, plan, sizing, journal

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-fetch", action="store_true", help="use cached price + macro (no download)")
    ap.add_argument("--days", default=None, help="price look-back in calendar days (default: 3 if cache already covers the previous NY month, else enough days for prev-month H/L + ADR20)")
    ap.add_argument("--n", type=int, default=4, help="levels per side")
    ap.add_argument("--at", help="evaluate news windows at Tehran time (testing)")
    ap.add_argument("--equity", type=float, default=None,
                    help="account equity in toman (overrides EQUITY_TOMAN and broker_daryagold.json)")
    a = ap.parse_args()
    cfg = DG.load_config(equity=a.equity)
    px = lambda p: DG.fmt_px(p, cfg)
    rc = 0
    if a.days is None:
        # Need the full previous NY calendar month (prev-month H/L) and ~30 calendar days for ADR20.
        # Reuse a deep enough cache and only fetch a short tail when history already covers prev-month start.
        try:
            import pandas as pd
            p1 = f"{DATA}/xauusd_1m.parquet"
            now = now_utc()
            _, prev_m = month_starts_utc(now)
            prev_m = pd.Timestamp(prev_m)
            need = int((pd.Timestamp(now) - prev_m).total_seconds() // 86400) + 3
            need = max(need, 35)
            covered = False
            if os.path.exists(p1):
                idx = pd.read_parquet(p1, columns=["c_b"]).index
                if len(idx) and pd.Timestamp(idx[0]) <= prev_m + pd.Timedelta(hours=6):
                    covered = True
            a.days = "3" if covered else str(need)
        except Exception:
            a.days = "45"
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
            "broker": cfg.get("broker"), "equity_toman": cfg.get("equity_toman"),
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
    session = DG.session_entry_block(at or now, cfg)
    decision, plan, sizing, journal = _apply_broker_gates(decision, lv, b, cfg, session)

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
        lines += DG.fa_plan_lines(plan, sizing, cfg)
    else:
        reasons = decision.get("reasons_reject") or [v.get("fa") or "صبر."]
        lines.append("**علت رد:** " + " ".join(reasons))
    if v.get("note_fa"):
        lines.append(f"⚠️ {v['note_fa']}")
    if v.get("news_caution_fa"):
        lines.append(f"⚠️ {v['news_caution_fa']}")

    lines.append(f"**جهت:** {FA_B[b['bias']]}  (H4 {FA_B[h4t].split()[0]}، "
                 f"H1 {FA_B[b['h1']['trend']].split()[0]}، M15 {FA_B[b['m15']['trend']].split()[0]}؛ "
                 f"بایاس خبری M5-News: {FA_B.get(b['news_bias'], '—').split()[0] if b['news_bias'] else 'ثبت نشده'})")
    bid = lv["price_bid"]
    src_kind = "فیوچرز GC=F" if meta.get("fallback") else "دریاگلد"
    lines.append(f"**قیمت:** {px(bid)} ({src_kind})  ·  "
                 f"ATR پنج‌دقیقه: {lv['atr_m5_14']} دلار · کیفیت داده: {q['fa']}")
    lines.append(DG.price_convention_fa(cfg))
    lines += DG.fa_risk_lines(cfg, spread=b.get("spread"), sizing=sizing, friday=session)
    lines += MAC.fa_lines(macro, lv, b.get("news_window"), regime, price_fmt=px)
    lines += REG.fa_indicator_lines(regime, price_fmt=px)

    # equal highs / lows (M15)
    eq = lv.get("equal") or {}
    eq_bits = []
    if eq.get("highs"):
        eq_bits.append("سقف " + "، ".join(f"{px(e['price'])} (n={e['n']})" for e in eq["highs"][:3]))
    if eq.get("lows"):
        eq_bits.append("کف " + "، ".join(f"{px(e['price'])} (n={e['n']})" for e in eq["lows"][:3]))
    if eq_bits:
        lines.append("**برابری سقف/کف M15:** " + " · ".join(eq_bits) + f" · آستانه {eq.get('tolerance')} دلار")

    lines.append("**سقف‌های نزدیک:**")
    lines += [f"- {px(l['price'])} · {label(l)}" for l in res] or ["- (سطح نزدیکی در محدوده نیست)"]
    lines.append("**کف‌های نزدیک:**")
    lines += [f"- {px(l['price'])} · {label(l)}" for l in sup] or ["- (سطح نزدیکی در محدوده نیست)"]
    if inv:
        word = "بالای" if b["bias"] == "bearish" or (b["bias"] == "neutral" and b["technical_bias"] == "bearish") else "زیر"
        lines.append(f"**ابطال جهت:** بسته شدن کندل M15 {word} {px(inv['neutral_level'])} → خنثی؛ "
                     f"بسته شدن کندل H1 {word} {px(inv['off_level'])} → جهت باطل." if inv.get("off_level") else
                     f"**ابطال جهت:** بسته شدن کندل M15 {word} {px(inv['neutral_level'])} → خنثی.")
    if b.get("news_invalidation"):
        lines.append(f"**ابطال خبری (M5-News):** {b['news_invalidation']}")

    now_eval = at or datetime.now(TEH)
    news_doc = DG.expand_news_doc(nw.load(), cfg)
    wins = []
    for s, e, meta_w in nw.merged(news_doc):
        if e > now_eval and (s - now_eval).total_seconds() < 86400:
            tag = {"block": "ورود ممنوع", "caution": "احتیاط", "monitor": "پایش"}.get(meta_w.get("action"), meta_w.get("action") or "")
            wins.append(f"{s:%H:%M}–{e:%H:%M} (سطح {meta_w.get('tier')}، {tag})")
    if wins:
        lines.append("**پنجره‌های خبری (تهران، ۲۴ ساعت آینده، با بافر سخت‌گیرانه‌تر دریاگلد):** " + "، ".join(wins))

    src = meta.get("source", "?"); fb = " ⚠️ منبع جایگزین" if meta.get("fallback") else ""
    lines.append(f"**منبع:** {src}{fb} · داده تا {meta.get('as_of_tehran')} به وقت تهران"
                 + (" · ⛔ داده کهنه است" if meta.get("stale") else "")
                 + (" · ⚠️ این قیمت فیوچرز COMEX است نه اسپات؛ با بروکر چند دلار فرق دارد و اسپرد نامعلوم است." if meta.get("fallback")
                    else " · " + DG.price_convention_fa(cfg)))
    lines.append(DISCLAIMER)
    md = "\n".join(lines)
    payload = {
        "generated_at_tehran": datetime.now(TEH).strftime("%Y-%m-%d %H:%M:%S"),
        "evaluated_at_tehran": b["evaluated_at_tehran"],
        "as_of_tehran": meta.get("as_of_tehran"), "source": src, "fallback": meta.get("fallback"),
        "stale": meta.get("stale"), "quality": q,
        "price_bid": lv["price_bid"],
        "price_daryagold": DG.to_broker(lv["price_bid"], cfg),
        "price_offset_usd": cfg.get("price_offset_usd"),
        "price_offset_uncertainty_usd": cfg.get("price_offset_uncertainty_usd"),
        "price_ask": lv.get("price_ask"), "atr_m5": lv["atr_m5_14"],
        "bias": b["bias"], "technical_bias": b["technical_bias"], "technical_confidence": b["technical_confidence"],
        "news_bias": b["news_bias"], "h4": b.get("h4"), "h1": b["h1"], "m15": b["m15"],
        "verdict": v, "decision": decision, "regime": regime, "macro": macro,
        "resistances": res, "supports": sup, "invalidation": inv, "news_window": b["news_window"],
        "spread": b["spread"], "structure": lv.get("structure"),
        "opening_ranges": lv.get("opening_ranges"), "equal": lv.get("equal"),
        "session_vwap": lv.get("session_vwap"),
        "news_windows_next_24h": wins, "markdown": md,
        "broker": cfg.get("broker"),
        "equity_toman": cfg.get("equity_toman"),
        "plan": plan, "sizing": sizing, "session_entry": session, "friday_close": session,
        "journal_today": journal,
    }
    _write(md, payload, 0)

if __name__ == "__main__":
    main()
