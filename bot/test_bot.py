#!/usr/bin/env python3
"""Offline end-to-end checks for bot.py: Telegram API, brief.py and the news refresh are mocked.
Never touches journal.csv, data/ or the network.  usage: STATE_DIR=$(mktemp -d) python3 bot/test_bot.py"""
import copy, json, os, sys, tempfile
from datetime import datetime
os.environ["STATE_DIR"] = os.environ.get("STATE_DIR") or tempfile.mkdtemp()
os.environ.pop("GITHUB_ACTIONS", None)
os.environ["TELEGRAM_BOT_TOKEN"] = "TEST"; os.environ["TELEGRAM_CHAT_ID"] = "111"
sys.path.insert(0, os.path.dirname(__file__))
import bot as B, broker_daryagold as DG
import level_view as LVIEW

JOURNAL = f"{B.ROOT}/journal.csv"
j_before = open(JOURNAL, "rb").read() if os.path.exists(JOURNAL) else None
SENT, SENT_TO, FAIL_HTML, FAIL_CHANNEL = [], [], [False], [False]
def fake_tg(method, **p):
    if method == "sendMessage":
        if str(p.get("chat_id")) != str(B.CHAT) and FAIL_CHANNEL[0]:
            return {"ok": False, "description": "Forbidden: bot is not a member"}
        if FAIL_HTML[0] and p.get("parse_mode") == "HTML":
            return {"ok": False, "description": "Bad Request: can't parse entities"}
        SENT.append(p["text"]); SENT_TO.append(str(p["chat_id"])); return {"ok": True, "result": {"message_id": len(SENT)}}
B.tg = fake_tg
CLOCK = [datetime(2026, 11, 11, 14, 0, tzinfo=B.TEH)]   # Wednesday
B.now_teh = lambda: CLOCK[0]
cfg = B.CFG = DG.load_config()
NEWS_OK = [True]
B.prepare_news = lambda state, force=False: NEWS_OK[0]


def mk_levels(price_bid=3880.0, computed_at="2026-11-11 14:00:00", **kw):
    """Shared snapshot fixture: 2 above + 2 below, H4/H1 disagree. Same object every card prints."""
    dg = round(price_bid + 0.3, 2)
    above = [
        {"price": 3895.0, "price_dg": 3895.3, "zone_dg": [3894.9, 3895.7], "side": "resistance",
         "kinds": ["PDH", "H4 swing high"], "label_fa": "سقف دیروز + سوئینگ H4",
         "touches_m15_3d": 2, "strength": "medium", "tag": "مهم", "distance": round(3895.3 - dg, 2)},
        {"price": 3910.0, "price_dg": 3910.3, "zone_dg": [3909.9, 3910.7], "side": "resistance",
         "kinds": ["Round $50"], "label_fa": "عدد رُند",
         "touches_m15_3d": 1, "strength": "weak", "tag": "معمولی", "distance": round(3910.3 - dg, 2)},
    ]
    below = [
        {"price": 3870.0, "price_dg": 3870.3, "zone_dg": [3869.9, 3870.7], "side": "support",
         "kinds": ["H1 swing low"], "label_fa": "سوئینگ H1",
         "touches_m15_3d": 3, "strength": "medium", "tag": "مهم", "distance": round(3870.3 - dg, 2)},
        {"price": 3850.0, "price_dg": 3850.3, "zone_dg": [3849.9, 3850.7], "side": "support",
         "kinds": ["Round $100"], "label_fa": "عدد رُند",
         "touches_m15_3d": 0, "strength": "weak", "tag": "معمولی", "distance": round(3850.3 - dg, 2)},
    ]
    # closer support first (nearest below)
    below = sorted(below, key=lambda x: -x["price"])
    # actually 3870 is closer than 3850; already in that order. For the 3887.545 brief test we override.
    if price_bid > 3885:
        below = [
            {"price": 3880.2, "price_dg": 3880.5, "zone_dg": [3880.1, 3880.9], "side": "support",
             "kinds": ["H1 swing low"], "label_fa": "سوئینگ H1",
             "touches_m15_3d": 2, "strength": "medium", "tag": "مهم", "distance": round(3880.5 - dg, 2)},
            {"price": 3870.0, "price_dg": 3870.3, "zone_dg": [3869.9, 3870.7], "side": "support",
             "kinds": ["Round $50"], "label_fa": "عدد رُند",
             "touches_m15_3d": 1, "strength": "weak", "tag": "معمولی", "distance": round(3870.3 - dg, 2)},
        ]
    snap = {
        "computed_at_tehran": computed_at,
        "price_bid": price_bid, "price_dg": dg,
        "trend": {"H4": {"trend": "نزولی"}, "H1": {"trend": "خنثی"}, "overall": "نامشخص", "verdict": "جمع‌بندی: نامشخص", "disagree": True},
        "short": {"above": above, "below": below},
        "nearest": {"above": above[0], "below": below[0]},
    }
    snap.update(kw)
    if "block" not in kw:
        snap["block"] = LVIEW.format_block(snap)
    return snap

def mk_brief(side="SELL", entry=3880.0, sl=3881.6, tp=3876.0, **kw):
    sz = DG.size_trade(entry, sl, tp, side, cfg, spread_usd=0.25)
    b = {"decision": {"decision": side, "reasons_reject": []}, "price_bid": entry, "bias": "bearish",
         "plan": {"side": side, "entry": entry, "sl": sl, "tp": tp}, "sizing": sz,
         "quality": {"ok": True, "age_minutes": 1}, "fallback": False, "news_window": {},
         "session_entry": {"blocked": False}, "resistances": [{"price": 3885.0}], "supports": [{"price": 3870.0}],
         "news_windows_next_24h": ["16:45–17:15 US x"],
         "levels": mk_levels(price_bid=entry)}
    b.update(kw); return b
BRIEF = [mk_brief()]
B.run_brief = lambda state: copy.deepcopy(BRIEF[0])

fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

NEXT_ID = [1]
def run(mode="scheduled", cmds=()):
    """cmds = commands queued by the Cloudflare Worker (pending_cmds in the pulled state)."""
    SENT.clear(); SENT_TO.clear()
    if cmds:
        s = json.load(open(B.STATE_JSON)) if os.path.exists(B.STATE_JSON) else {}
        for c in cmds:
            s.setdefault("pending_cmds", []).append({"id": NEXT_ID[0], "cmd": c}); NEXT_ID[0] += 1
        os.makedirs(B.STATE_DIR, exist_ok=True); json.dump(s, open(B.STATE_JSON, "w"))
    sys.argv = ["bot.py", "--mode", mode]; B.main()
    st = json.load(open(B.STATE_JSON))   # emulate the Worker's merge: done commands leave the queue
    st["pending_cmds"] = [x for x in st.get("pending_cmds", []) if x["id"] not in st.get("done_cmds", [])]
    json.dump(st, open(B.STATE_JSON, "w"))
    return list(SENT)

def state():
    return json.load(open(B.STATE_JSON))

# ---- (d) queued commands (all other commands are answered by the Worker; see worker/test.mjs)
out = run("command", ["/scan"]); check("queued /scan answered once", len(out) == 1)
check("done commands leave the queue", state().get("pending_cmds") == [])
out = run("command"); check("nothing queued -> silent", out == [])
out = run("command", ["/help"]); check("non-analysis command in queue ignored (Worker answers it)", out == [] and state()["pending_cmds"] == [])
st = state(); st["signals_sent"] = []; json.dump(st, open(B.STATE_JSON, "w"))

# ---- (e) gating
def gate(name, expect_ok, brief=None, news=True, setup=None):
    s = B.load_state(); NEWS_OK[0] = news
    if setup: setup(s)
    ok, plan, sz, why = B.risk_check(brief or mk_brief(), s, cfg, news)
    check(f"gate {name} -> {'signal' if expect_ok else 'blocked'}", ok == expect_ok)
    return why
gate("clean setup", True)
gate("inside A/B news window", False, mk_brief(news_window={"inside": True, "action": "block", "end": "2026-11-11 14:20"}))
gate("news window soon", False, mk_brief(news_window={"soon_block": True}))
gate("calendar unavailable (FF down >30h)", False, news=False)
gate("Friday 23:30 session block", False, mk_brief(session_entry={"blocked": True, "friday_window": True}))
gate("daily stop 3 losses", False, setup=lambda s: s["day"].update(losses=3))
gate("daily stop 20% net", False, setup=lambda s: s["day"].update(loss_toman=420000))
gate("net R:R < 1.5", False, mk_brief(tp=3877.6))
gate("SL < $1", False, mk_brief(sl=3880.8, tp=3877.0))
gate("stale data 11 min", False, mk_brief(quality={"ok": True, "age_minutes": 11}))
gate("futures fallback", False, mk_brief(fallback=True))
gate("no BUY/SELL", False, mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]}))
gate("data source down (brief error)", False, {"decision": "NO TRADE", "error": True})
fs = DG.session_entry_block(datetime(2026, 11, 13, 23, 31, tzinfo=B.TEH), cfg)
check("DaryaGold Friday 23:31 -> entries blocked", fs["blocked"])
check("DaryaGold Saturday -> market closed", not DG.forex_open(datetime(2026, 11, 14, 12, 0, tzinfo=B.TEH), cfg))

# ---- (e/f) scheduled: signal once, then silent; 1-position lock; single TP; Latin copy digits
st = state(); st["day"].update(losses=0, loss_toman=0, wins=0, win_toman=0, records=[]); json.dump(st, open(B.STATE_JSON, "w"))
NEWS_OK[0] = True; BRIEF[0] = mk_brief()
out = run("scheduled"); check("scheduled: signal sent once", len(out) == 1 and "فروش طلا" in out[0])
sig = out[0] if out else ""
check("single target (no TP2)", sig.count("<code>") == 3 and "هدف ۲" not in sig)
check("copy prices Latin '.' digits", "<code>3880.3</code>" in sig and "<code>3876.3</code>" in sig)
check("rest of signal Persian digits", "۱٫۸" in sig and "1.8" not in sig.replace("<code>", "|"))
check("every line RLM", all(l.startswith("\u200f") for l in sig.split("\n") if l.strip()))
CLOCK[0] = datetime(2026, 11, 11, 14, 15, tzinfo=B.TEH)
check("scheduled: duplicate not resent", run("scheduled") == [])
BRIEF[0] = mk_brief(entry=3875.0, sl=3876.6, tp=3871.0)
CLOCK[0] = datetime(2026, 11, 11, 14, 30, tzinfo=B.TEH)
check("1-position lock blocks a new signal", run("scheduled") == [])
st = state(); st["day"]["records"].append({"type": "loss", "toman": 162000, "at": "14:40"}); st["day"]["losses"] = 1
json.dump(st, open(B.STATE_JSON, "w")); CLOCK[0] = datetime(2026, 11, 11, 14, 45, tzinfo=B.TEH)
check("after /loss the lock releases", len(run("scheduled")) == 1)
st = state(); st["day"].update(losses=0, loss_toman=0, records=[]); st["signals_sent"] = []; json.dump(st, open(B.STATE_JSON, "w"))
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]})
CLOCK[0] = datetime(2026, 11, 11, 15, 0, tzinfo=B.TEH)
check("scheduled NO TRADE is silent", run("scheduled") == [])
out = run("command", ["/scan"]); check("/scan NO TRADE card", len(out) == 1 and "معامله نه" in out[0])
out = run("command", ["/brief"]); check("/brief card", len(out) == 1 and "طلا" in out[0])

# ---- (f) pre-session briefs once per day
CLOCK[0] = datetime(2026, 11, 11, 16, 15, tzinfo=B.TEH); a = run("scheduled")
CLOCK[0] = datetime(2026, 11, 11, 16, 30, tzinfo=B.TEH); b2 = run("scheduled")
CLOCK[0] = datetime(2026, 11, 11, 16, 58, tzinfo=B.TEH); c = run("scheduled")
check("16:15 brief sent once (late runs silent)", len(a) == 1 and "نیویورک" in a[0] and b2 == [] and c == [])
CLOCK[0] = datetime(2026, 11, 12, 11, 52, tzinfo=B.TEH); out = run("scheduled")
check("11:15 brief sent even if cron is 37 min late", len(out) == 1 and "لندن" in out[0])
check("Tehran-midnight daily reset", state()["day"]["date"] == "2026-11-12" and state()["day"]["losses"] == 0 and state()["day"]["records"] == [])
CLOCK[0] = datetime(2026, 11, 14, 11, 15, tzinfo=B.TEH)
check("Saturday: scheduled run silent", run("scheduled") == [])

# ---- (g) HTML escaping + fallback + length
r = B.render("**x** <script> & `1.5` 2.5"); check("HTML escaped", "&lt;script&gt;" in r and "&amp;" in r and "<code>1.5</code>" in r and "۲٫۵" in r)
CLOCK[0] = datetime(2026, 11, 12, 12, 0, tzinfo=B.TEH)
FAIL_HTML[0] = True; out = run("command", ["/brief"]); FAIL_HTML[0] = False
check("HTML failure -> plain-text fallback without tags", len(out) == 1 and "<" not in out[0] and "طلا" in out[0])
SENT.clear(); SENT_TO.clear(); B.send("\n".join(["خط آزمایشی " + str(i) for i in range(600)]))
check("long message split <=4096 on line breaks", len(SENT) >= 2 and all(len(x) <= 4096 for x in SENT) and all(x.split("\n")[-1].startswith("\u200fخط") for x in SENT))

# ---- (h) /brief vs /scan; day high/low from candles; nearest levels skip ones glued to price
B.day_hilo = lambda t: (3922.995, 3874.895)
CLOCK[0] = datetime(2026, 11, 11, 18, 50, tzinfo=B.TEH)
st = state(); st["equity_toman"] = 2954400; st["day"] = {"date": "2026-11-11", "losses": 0, "loss_toman": 0, "wins": 0, "win_toman": 0, "records": [], "start_equity": 1000000}
json.dump(st, open(B.STATE_JSON, "w"))
BRIEF[0] = mk_brief(entry=3887.545, sl=3889.2, tp=3882.0, atr_m5=1.6,
                    resistances=[{"price": 3888.1}, {"price": 3895.0}], supports=[{"price": 3887.465}, {"price": 3880.2}],
                    news_windows_next_24h=["16:45–17:15 (B)", "18:40–19:05 (B)", "19:30–19:50 (B)", "20:15–21:00 (B)", "22:00–22:30 (B)", "03:15–04:00 (B)"])
out = run("command", ["/brief"]); br = out[0] if out else ""
check("/brief: market summary title, never a signal (even with a BUY/SELL brief)", "خلاصه‌ی بازار" in br and "فروش طلا" not in br)
check("/brief: shared levels block with Latin tap-to-copy prices", "<code>3895.3</code>" in br and "<code>3880.5</code>" in br and "۳۸۸۸٫۴" not in br)
check("/brief: H4/H1 trend from the snapshot (disagree -> نامشخص)", "H4 نزولی" in br and "H1 خنثی" in br and "جمع‌بندی: نامشخص" in br)
check("/brief: no day-candle hilo and no glued-level skip line", "سقف روز" not in br and "مقاومت نزدیک" not in br and "حمایت نزدیک" not in br)
check("/brief: all remaining news today (incl. ongoing), none passed or tomorrow", all(x in br for x in ["۱۸:۴۰ تا ۱۹:۰۵", "۱۹:۳۰", "۲۰:۱۵", "۲۲:۰۰"]) and "۱۶:۴۵" not in br and "۰۳:۱۵" not in br)
check("/brief: balance and today's loss cap from the day's start equity", "موجودی ۲٫۹۵ میلیون" in br and "سقف ضرر امروز ۲۰۰ هزار" in br)
check("/brief: no 'strong'/قوی, no زیان", not any(w in br for w in ["قوی", "strong", "زیان"]))
check("/brief is the stored block (labels + nearest = top of /levels)", "سقف دیروز + سوئینگ H4" in br and "سوئینگ H1" in br)
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]}, news_window={"inside": True, "action": "block", "end": "2026-11-11 19:05"},
                    levels=mk_levels(price_bid=3880.0, computed_at="2026-11-11 18:50:00"))
out = run("command", ["/scan"]); sc = out[0] if out else ""
check("/scan no trade: title + one reason + the same levels block", "معامله نه" in sc and "پنجره‌ی خبری تا ۱۹:۰۵" in sc and "طلا" in sc and
      BRIEF[0]["levels"]["block"].split("\n")[0].startswith("طلا") and "موجودی" not in sc and "<code>3895.3</code>" in sc)
check("/scan and /brief share nearest prices", "<code>3895.3</code>" in sc and "<code>3870.3</code>" in sc)
CLOCK[0] = datetime(2026, 11, 11, 16, 15, tzinfo=B.TEH); st = state(); st["presession_sent"] = {}; json.dump(st, open(B.STATE_JSON, "w"))
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]},
                    levels=mk_levels(price_bid=3880.0, computed_at="2026-11-11 16:15:00"))
out = run("scheduled"); pre = out[0] if out else ""
check("pre-session brief uses the same levels block as /levels", len(out) == 1 and "نیویورک" in pre and "<code>3895.3</code>" in pre and "H4 نزولی" in pre and "سقف روز" not in pre)

# identical block across /brief /scan /levels /pre-session
CLOCK[0] = datetime(2026, 11, 11, 18, 50, tzinfo=B.TEH)
st = state(); st["presession_sent"] = {}; json.dump(st, open(B.STATE_JSON, "w"))
snap = mk_levels(price_bid=3887.545, computed_at="2026-11-11 18:50:00")
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]}, price_bid=3887.545, levels=snap)
br2 = run("command", ["/brief"])[0]
sc2 = run("command", ["/scan"])[0]
lv2 = run("command", ["/levels"])[0]
st = state(); st["presession_sent"] = {}; json.dump(st, open(B.STATE_JSON, "w"))
CLOCK[0] = datetime(2026, 11, 11, 16, 15, tzinfo=B.TEH)
pre2 = run("scheduled")[0]
def has_block(card, s=snap):
    return all(x in card for x in ("<code>3895.3</code>", "<code>3880.5</code>", "H4 نزولی", "H1 خنثی", "جمع‌بندی: نامشخص", "سقف دیروز + سوئینگ H4"))
check("same levels+trend in /brief, /scan, /levels and the pre-session brief",
      has_block(br2) and has_block(sc2) and has_block(lv2) and has_block(pre2))
check("/levels card title and no حساب footer", "سطوح" in lv2 and "موجودی" not in lv2)
check("state stores the same snapshot (no second computation)", state().get("levels", {}).get("block") == snap["block"])
a, btm = B.near_levels(BRIEF[0])
check("near_levels is the top of /levels", a["price_dg"] == 3895.3 and btm["price_dg"] == 3880.5)

check("forex day start: 17:00 New York = 01:30 Tehran (winter) / 00:30 (summer)",
      B.day_start(datetime(2026, 11, 13, 18, 0, tzinfo=B.TEH)).strftime("%m-%d %H:%M") == "11-13 01:30" and
      B.day_start(datetime(2026, 11, 13, 1, 0, tzinfo=B.TEH)).strftime("%m-%d %H:%M") == "11-12 01:30" and
      B.day_start(datetime(2026, 7, 15, 12, 0, tzinfo=B.TEH)).strftime("%H:%M") == "00:30")
check("risk_check daily cap uses start_equity", B.day_cap({"equity_toman": 2954400, "day": {"start_equity": 1000000}}, cfg) == 200000 and
      B.day_cap({"equity_toman": 2954400, "day": {}}, cfg) == 2954400 * 0.2)

# ---- (i) shadow log: silent record of gate-only blocks, resolved from later 1-minute bars
import shadow as SH
from datetime import timedelta as TD
def bars(start, rows):
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=B.TEH)
    return [(t0 + TD(minutes=i), h, l, c) for i, (h, l, c) in enumerate(rows)]
def ent(side="SELL", entry=3894.2, sl=3896.2, tp=3890.2, at="2026-11-11 18:00"):
    return {"at": at, "side": side, "entry": entry, "sl": sl, "tp": tp, "status": "pending", "gates": ["news"]}
NOW = datetime(2026, 11, 11, 23, 0, tzinfo=B.TEH)
e = SH.resolve([ent()], bars("2026-11-11 18:00", [(3893.0, 3892.0, 3892.5), (3894.3, 3893.0, 3894.0), (3895.0, 3891.0, 3891.5), (3891.0, 3890.1, 3890.5)]), NOW)[0]
check("shadow: SELL fills, TP first -> +2R, +306,000 toman (1 unit, fee 14,000)", e["status"] == "tp" and e["R"] == 2.0 and e["toman"] == 306000 and e["filled_at"] == "2026-11-11 18:01")
e = SH.resolve([ent()], bars("2026-11-11 18:00", [(3894.5, 3893.0, 3894.0), (3896.3, 3893.0, 3896.0)]), NOW)[0]
check("shadow: SL first -> -1R, -174,000 toman", e["status"] == "sl" and e["R"] == -1.0 and e["toman"] == -174000)
e = SH.resolve([ent()], bars("2026-11-11 18:00", [(3894.5, 3893.0, 3894.0), (3896.5, 3890.0, 3893.0)]), NOW)[0]
check("shadow: TP and SL in the same bar -> SL (conservative)", e["status"] == "sl")
e = SH.resolve([ent(side="BUY", entry=3880, sl=3878, tp=3884)], bars("2026-11-11 18:00", [(3882, 3881, 3881.5)] * 40), NOW)[0]
check("shadow: limit not touched within 30 min -> unfilled, 0", e["status"] == "unfilled" and e["toman"] == 0)
e = SH.resolve([ent(side="BUY", entry=3880, sl=3878, tp=3884)], bars("2026-11-11 18:00", [(3880.5, 3879.8, 3880.4)] + [(3881.2, 3879.0, 3881.0)] * 250), NOW)[0]
check("shadow: open 4 h without TP/SL -> expired at market (+0.5R)", e["status"] == "expired" and e["R"] == 0.5 and e["exit"] == 3881.0)
e = SH.resolve([ent()], bars("2026-11-11 18:00", [(3894.5, 3893.0, 3894.0)] + [(3895.0, 3893.0, 3894.0)] * 3), datetime(2026, 11, 11, 18, 3, tzinfo=B.TEH))[0]
check("shadow: still open while data is too short; incomplete bars ignored", e["status"] == "open")
check("gates_active: news / volatility / Friday / none",
      SH.gates_active({"news_window": {"inside": True, "action": "block"}}) == ["news"] and
      SH.gates_active({"regime": {"code": "volatility_expansion"}, "news_window": {"soon_block": True}}) == ["news", "volatility"] and
      SH.gates_active({"session_entry": {"blocked": True, "friday_window": True}}) == ["friday"] and
      SH.gates_active({"regime": {"code": "trend"}, "news_window": {}, "session_entry": {"blocked": False}}) == [])
CAND = [None]
B.shadow_candidate = lambda cfg: CAND[0]
B.shadow_bars = lambda since: []
def cand(side="SELL", entry=3880.0, sl=3881.6, tp=3876.0):
    sz = DG.size_trade(entry, sl, tp, side, cfg, spread_usd=0.25)
    return ({"decision": side}, {"side": side, "entry": entry, "sl": sl, "tp": tp}, sz)
st = state(); st["shadow"] = []; st["signals_sent"] = []; st["day"].update(losses=0, loss_toman=0, records=[]); json.dump(st, open(B.STATE_JSON, "w"))
CLOCK[0] = datetime(2026, 11, 11, 18, 20, tzinfo=B.TEH)
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["news"]}, plan=None, sizing=None,
                    regime={"code": "news_abnormal"}, news_window={"inside": True, "action": "block", "tier": "B", "end": "2026-11-11 18:40"})
CAND[0] = cand(); out = run("scheduled")
sh = state().get("shadow") or []
check("shadow: news-blocked valid setup recorded silently (no Telegram message)", out == [] and len(sh) == 1 and sh[0]["gates"] == ["news"] and sh[0]["side"] == "SELL" and sh[0]["status"] == "pending" and sh[0]["at"] == "2026-11-11 18:20")
CLOCK[0] = datetime(2026, 11, 11, 18, 35, tzinfo=B.TEH); out = run("scheduled")
check("shadow: one open entry at a time (no duplicate while pending)", out == [] and len(state()["shadow"]) == 1)
st = state(); st["shadow"] = []; json.dump(st, open(B.STATE_JSON, "w"))
CAND[0] = cand(tp=3877.6); run("scheduled"); check("shadow: candidate failing R:R (a setup condition) not recorded", state()["shadow"] == [])
CAND[0] = cand(); BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["no setup"]}, regime={"code": "trend"})
run("scheduled"); check("shadow: NO TRADE without any gate -> not recorded", state()["shadow"] == [])
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["v"]}, regime={"code": "volatility_expansion"})
st = state(); st["day"]["losses"] = 3; json.dump(st, open(B.STATE_JSON, "w"))
run("scheduled"); check("shadow: daily stop active -> not recorded (account rule, not a gate)", state()["shadow"] == [])
st = state(); st["day"]["losses"] = 0; json.dump(st, open(B.STATE_JSON, "w"))
out = run("scheduled"); check("shadow: volatility-blocked setup recorded; live gate unchanged (nothing sent)", out == [] and state()["shadow"][-1]["gates"] == ["volatility"])
B.shadow_bars = lambda since: bars("2026-11-11 18:35", [(3880.5, 3879.0, 3879.5), (3879.0, 3875.5, 3876.0)])
CLOCK[0] = datetime(2026, 11, 11, 18, 50, tzinfo=B.TEH); BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]}, regime={"code": "trend"})
run("scheduled"); check("shadow: later run resolves the open entry (TP)", state()["shadow"][-1]["status"] == "tp")
B.shadow_candidate = lambda cfg: (_ for _ in ()).throw(RuntimeError("boom"))
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["v"]}, regime={"code": "volatility_expansion"})
out = run("scheduled"); check("shadow: a failing counterfactual never breaks the run", out == [] and state()["last_run_tehran"] == "2026-11-11 18:50")

# ---- (j) Friday close reminder, weekend, Asia log-only, dg_offset, last_price (2026-11-14)
B.shadow_candidate = lambda cfg: CAND[0]; B.shadow_bars = lambda since: []
CALLS = [0]
B.run_brief = lambda state: (CALLS.__setitem__(0, CALLS[0] + 1), copy.deepcopy(BRIEF[0]))[1]
def fresh(**kw):
    st = state(); st.update(shadow=[], signals_sent=[], presession_sent={}, friday_reminder_sent=None); st.pop("dg_offset", None); st.pop("channel_id", None)
    st["day"].update(losses=0, loss_toman=0, wins=0, win_toman=0, records=[]); st.update(kw); json.dump(st, open(B.STATE_JSON, "w"))
fresh(); BRIEF[0] = mk_brief()
CLOCK[0] = datetime(2026, 11, 13, 22, 0, tzinfo=B.TEH); out = run("scheduled")
check("Friday 22:00 (before the cutoff): normal signal", len(out) == 1 and "فروش طلا" in out[0])
fresh(); CLOCK[0] = datetime(2026, 11, 13, 23, 30, tzinfo=B.TEH); CALLS[0] = 0; out = run("scheduled")
check("Friday 23:30: one short close reminder (flat by 01:30), no signal, no analysis", len(out) == 1 and "ورود جدید بسته است" in out[0] and "۰۱:۳۰" in out[0] and
      "<code>" not in out[0] and len([l for l in out[0].split("\n") if l.strip()]) == 2 and CALLS[0] == 0 and state()["signals_sent"] == [])
CLOCK[0] = datetime(2026, 11, 13, 23, 45, tzinfo=B.TEH); a1 = run("scheduled")
CLOCK[0] = datetime(2026, 11, 14, 0, 45, tzinfo=B.TEH); a2 = run("scheduled")
check("close reminder sent once (23:45 and Saturday 00:45 silent)", a1 == [] and a2 == [])
fresh(); CLOCK[0] = datetime(2026, 7, 17, 23, 30, tzinfo=B.TEH); out = run("scheduled")
check("summer Friday 23:30: reminder says flat by 00:30", len(out) == 1 and "۰۰:۳۰" in out[0])
fresh(); BRIEF[0] = mk_brief(session_entry={"blocked": True, "friday_window": True}, decision={"decision": "NO TRADE", "reasons_reject": ["x"]})
CLOCK[0] = datetime(2026, 11, 14, 0, 45, tzinfo=B.TEH); out = run("command", ["/scan"])
check("Saturday 00:45 (entries closed, market open): /scan analysed -> «جمعه‌شب»", len(out) == 1 and "جمعه‌شب" in out[0])
BRIEF[0] = mk_brief()
for when, nm in [(datetime(2026, 11, 14, 1, 45, tzinfo=B.TEH), "Saturday 01:45"), (datetime(2026, 11, 14, 12, 0, tzinfo=B.TEH), "Saturday noon"),
                 (datetime(2026, 11, 15, 20, 0, tzinfo=B.TEH), "Sunday 20:00"), (datetime(2026, 11, 16, 1, 15, tzinfo=B.TEH), "Monday 01:15")]:
    CLOCK[0] = when; CALLS[0] = 0; out = run("command", ["/scan", "/brief"])
    check(f"{nm}: /scan and /brief -> one closed line each (reopen Monday 01:30), no analysis",
          len(out) == 2 and all(x.count("\n") == 0 and "بازار بسته است" in x and "دوشنبه ۰۱:۳۰" in x for x in out) and CALLS[0] == 0)

# /levels on the weekend: never re-analyse; last snapshot (with age) or the same closed line
CLOCK[0] = datetime(2026, 11, 14, 12, 0, tzinfo=B.TEH)
st = state(); st.pop("levels", None); json.dump(st, open(B.STATE_JSON, "w")); CALLS[0] = 0
out = run("command", ["/levels"])
check("Saturday /levels with no snapshot: same closed line, no analysis",
      len(out) == 1 and out[0].count("\n") == 0 and "بازار بسته است" in out[0] and "دوشنبه ۰۱:۳۰" in out[0] and CALLS[0] == 0)
snap = mk_levels(price_bid=3880.0, computed_at="2026-11-13 17:30:00")
st = state(); st["levels"] = snap; json.dump(st, open(B.STATE_JSON, "w")); CALLS[0] = 0
out = run("command", ["/levels"])
check("Saturday /levels with a stored snapshot: served with age, no analysis",
      len(out) == 1 and CALLS[0] == 0 and "سن داده" in out[0] and "<code>3895.3</code>" in out[0] and "H4 نزولی" in out[0] and "بازار بسته است" not in out[0])

for when in [datetime(2026, 11, 14, 11, 15, tzinfo=B.TEH), datetime(2026, 11, 15, 16, 15, tzinfo=B.TEH), datetime(2026, 11, 14, 3, 30, tzinfo=B.TEH)]:
    CLOCK[0] = when; CALLS[0] = 0
    check(f"weekend scheduled run {when:%a %H:%M}: silent, no analysis", run("scheduled") == [] and CALLS[0] == 0)
check("forex open Sunday 17:00 NY: Monday 01:30 Tehran open, 01:29 closed; summer 00:30; close Friday 17:00 NY = Saturday 01:30",
      DG.forex_open(datetime(2026, 11, 16, 1, 30, tzinfo=B.TEH), cfg) and not DG.forex_open(datetime(2026, 11, 16, 1, 29, tzinfo=B.TEH), cfg) and
      DG.forex_open(datetime(2026, 7, 20, 0, 30, tzinfo=B.TEH), cfg) and not DG.forex_open(datetime(2026, 7, 20, 0, 29, tzinfo=B.TEH), cfg) and
      DG.forex_open(datetime(2026, 11, 14, 1, 29, tzinfo=B.TEH), cfg) and not DG.forex_open(datetime(2026, 11, 14, 1, 30, tzinfo=B.TEH), cfg) and
      DG.session_entry_block(datetime(2026, 11, 13, 20, 0, tzinfo=B.TEH), cfg)["close_tehran"] == "2026-11-14 01:30")
check("daily break is not a weekend closure; weekday market open", not B.weekend_closed(datetime(2026, 11, 12, 1, 45, tzinfo=B.TEH), cfg) and
      not B.weekend_closed(datetime(2026, 11, 12, 14, 0, tzinfo=B.TEH), cfg))
# Asia: log-only
check("Asia window 03:30-11:15 weekdays only", B.in_asia(datetime(2026, 11, 16, 3, 30, tzinfo=B.TEH)) and not B.in_asia(datetime(2026, 11, 16, 3, 29, tzinfo=B.TEH)) and
      not B.in_asia(datetime(2026, 11, 16, 11, 15, tzinfo=B.TEH)) and B.in_asia(datetime(2026, 11, 16, 11, 0, tzinfo=B.TEH)) and not B.in_asia(datetime(2026, 11, 14, 9, 0, tzinfo=B.TEH)))
fresh(); BRIEF[0] = mk_brief(); CLOCK[0] = datetime(2026, 11, 16, 9, 4, tzinfo=B.TEH); out = run("scheduled"); sh = state()["shadow"]
check("Asia 09:04 valid SELL: nothing sent, logged as shadow (session=asia, gate asia), no signal lock",
      out == [] and len(sh) == 1 and sh[0]["session"] == "asia" and sh[0]["gates"] == ["asia"] and sh[0]["side"] == "SELL" and state()["signals_sent"] == [])
fresh(); BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["news"]}, plan=None, sizing=None, regime={"code": "news_abnormal"},
                             news_window={"inside": True, "action": "block", "tier": "B", "end": "2026-11-16 09:30"})
CAND[0] = cand(); out = run("scheduled"); sh = state()["shadow"]
check("Asia news-blocked setup: logged with session=asia, nothing sent", out == [] and len(sh) == 1 and sh[0]["gates"] == ["news"] and sh[0]["session"] == "asia")
fresh(); BRIEF[0] = mk_brief(); CLOCK[0] = datetime(2026, 11, 16, 11, 0, tzinfo=B.TEH); out = run("scheduled")
check("Asia 11:00: no pre-session brief, no signal", out == [] and state()["presession_sent"] == {})
fresh(); CLOCK[0] = datetime(2026, 11, 16, 11, 15, tzinfo=B.TEH); out = run("scheduled")
check("11:15 (Asia over): signal + London brief as before", len(out) == 2 and any("فروش طلا" in x for x in out) and any("لندن" in x for x in out) and not state()["shadow"])
fresh(); CLOCK[0] = datetime(2026, 11, 16, 9, 0, tzinfo=B.TEH); out = run("command", ["/scan"])
check("/scan on request in Asia still answers (only scheduled runs are silent)", len(out) == 1)
# dg_offset from bot_state
fresh(dg_offset=0.5); BRIEF[0] = mk_brief(); CLOCK[0] = datetime(2026, 11, 16, 14, 0, tzinfo=B.TEH); out = run("scheduled")
check("dg_offset 0.5 from state: signal prices = bid + 0.5", len(out) == 1 and "<code>3880.5</code>" in out[0] and "<code>3876.5</code>" in out[0])
check("dg_offset passed to brief.py (env) and load_config honours it", os.environ.get("DG_OFFSET_USD") == "0.5" and DG.load_config()["price_offset_usd"] == 0.5)
fresh(dg_offset="bad"); B.CFG = cfg = DG.load_config(); os.environ.pop("DG_OFFSET_USD", None); cfg2 = B.apply_offset({"dg_offset": 9}, DG.load_config())
check("invalid dg_offset ignored (default 0.3 stays)", cfg2["price_offset_usd"] == 0.3 and B.apply_offset({"dg_offset": "x"}, DG.load_config())["price_offset_usd"] == 0.3)
fresh(dg_offset=0.4); CLOCK[0] = datetime(2026, 11, 16, 9, 30, tzinfo=B.TEH); run("scheduled")
check("shadow entry records the offset in use (0.4)", state()["shadow"][-1]["offset"] == 0.4)
os.environ.pop("DG_OFFSET_USD", None); B.CFG = cfg = DG.load_config()
check("last_price stored for the /trade check", state()["last_price"] == {"bid": 3880.0, "at": "2026-11-16 09:30"})


# ---- shared snapshot: signal-engine inputs unchanged; trend / filter rules
cfg_lv = DG.load_config()
full = [
    {"price": 3900.0, "side": "resistance", "kinds": ["M15 swing high", "VWAP"], "strength": "strong", "score": 7, "touches_m15_3d": 2},
    {"price": 3910.0, "side": "resistance", "kinds": ["PDH", "H4 swing high"], "strength": "medium", "score": 4, "touches_m15_3d": 1},
    {"price": 3890.0, "side": "support", "kinds": ["EMA20 M15"], "strength": "weak", "score": 1, "touches_m15_3d": 0},
    {"price": 3880.0, "side": "support", "kinds": ["H1 swing low", "London OR low"], "strength": "strong", "score": 8, "touches_m15_3d": 3},
]
lv = {"price_bid": 3895.0, "atr_h1_14": 8.0, "atr_m5_14": 2.0, "cluster_tol": 0.5,
      "levels": [dict(x) for x in full],
      "structure": {"prev_week": {"high": 4020.0, "low": 3800.0}},
      "ema": {"H4": {"ema20": 3890.0, "ema50": 3900.0, "close": 3888.0},
              "H1": {"ema20": 3898.0, "ema50": 3890.0, "close": 3899.0}},
      "swings": {"H4": {"highs": [(0, 3920.0), (1, 3910.0)], "lows": [(0, 3880.0), (1, 3870.0)]},
                 "H1": {"highs": [(0, 3900.0), (1, 3910.0)], "lows": [(0, 3870.0), (1, 3880.0)]}}}
before = [dict(x) for x in lv["levels"]]
snap = LVIEW.snapshot(lv, cfg_lv, now=datetime(2026, 11, 11, 14, 0, tzinfo=B.TEH))
check("snapshot does not mutate the full cluster list (signal inputs unchanged)", lv["levels"] == before)
kinds_short = {k for row in snap["short"]["above"] + snap["short"]["below"] for k in row["kinds"]}
check("short view drops M15/VWAP/EMA and keeps PDH/H4/H1/OR",
      "M15 swing high" not in kinds_short and "VWAP" not in kinds_short and "EMA20 M15" not in kinds_short
      and "PDH" in kinds_short and "H4 swing high" in kinds_short and "H1 swing low" in kinds_short and "London OR low" in kinds_short)
check("prev-week levels are in the short view only (not injected into compute clusters)",
      any("Prev week high" in (r["kinds"] or []) or r.get("label_fa") == "سقف هفته‌ی قبل" for r in snap["short"]["above"])
      and all("Prev week" not in "".join(x.get("kinds") or []) for x in lv["levels"]))
# H4: LH/LL + bearish EMA -> نزولی; H1: HH/HL + bullish EMA -> صعودی; disagree -> نامشخص
check("trend: H4 down + H1 up => نامشخص (structure + EMA)",
      snap["trend"]["H4"]["trend"] == "نزولی" and snap["trend"]["H1"]["trend"] == "صعودی" and snap["trend"]["overall"] == "نامشخص" and snap["trend"]["verdict"] == "جمع‌بندی: نامشخص")
# mixed structure -> خنثی even if EMA agrees
lv2 = dict(lv, swings={"H4": {"highs": [(0, 3920.0), (1, 3910.0)], "lows": [(0, 3870.0), (1, 3880.0)]},
                       "H1": lv["swings"]["H1"]})
tr2 = LVIEW.trend_of(lv2)
check("mixed H4 swings => خنثی even with bearish EMA", tr2["H4"]["trend"] == "خنثی")
check("format_block never prints قوی or a 0–100 score", "قوی" not in snap["block"] and "score" not in snap["block"] and " ۱۲ " not in snap["block"])
# risk_check ignores the display snapshot
s = B.load_state()
ok1, *_ = B.risk_check(mk_brief(), s, cfg, True)
b_no = mk_brief(); b_no.pop("levels", None)
ok2, *_ = B.risk_check(b_no, s, cfg, True)
check("risk_check result is the same with or without the display snapshot", ok1 is True and ok1 == ok2)


# ---- display tiers, M15/M5 trend, context line, no «زیان» in rendered text
# relative tiers (deterministic percentiles; documented in level_view.py)
def _item(kinds, touches, price):
    return {"price": price, "kinds": kinds, "touches_m15_3d": touches, "label_fa": LVIEW.label_fa(kinds)}
eq = [_item(["Round $50"], 0, 3900 + i) for i in range(6)]
LVIEW.assign_tiers(eq)
check("flat set B stays مهم (no خیلی مهم, no معمولی)", all(x["tag"] == "مهم" for x in eq) and len({x["display_score"] for x in eq}) == 1)
mix = [
    _item(["Round $50"], 0, 3800),                 # weight 2, touches 0 → 2.0  معمولی
    _item(["Round $50"], 0, 3810),
    _item(["H1 swing low"], 1, 3820),               # 3+0.5=3.5
    _item(["H1 swing low"], 2, 3830),               # 4.0  مهم
    _item(["PDH", "H4 swing high"], 2, 3840),       # 3+3+1=7.0
    _item(["PDH", "H4 swing high", "Round $100"], 4, 3850),  # 3+3+2.5+2=10.5  خیلی مهم
    _item(["PDH", "H4 swing high", "London high"], 8, 3860), # 3+3+2.5+2=10.5 (touch cap 4)
]
LVIEW.assign_tiers(mix)
check("touch cap: 8 touches scores the same as 4", mix[-1]["display_score"] == mix[-2]["display_score"] == 10.5)
tags = {x["tag"] for x in mix}
check("mixed set B uses all three display tiers", tags == {"معمولی", "مهم", "خیلی مهم"})

# last-close fixture (Friday 13 Nov 2026 close; captured from Dukascopy cache)
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "last_close_20261113.json")
lv_fix = json.load(open(FIX))
snap_fix = LVIEW.snapshot(lv_fix, cfg, now=datetime(2026, 11, 14, 6, 50, tzinfo=B.TEH))
tc = snap_fix.get("tier_counts") or {}
shown_tags = [r["tag"] for r in snap_fix["short"]["above"] + snap_fix["short"]["below"]]
check("last-close set B tiers are not all equal", len(set(tc) | set(shown_tags)) >= 2 and len(tc) >= 2)
check("last-close set B has معمولی, مهم and خیلی مهم", set(tc) == {"معمولی", "مهم", "خیلی مهم"})
check("last-close short view is not all خیلی مهم", len(set(shown_tags)) >= 2 and shown_tags.count("خیلی مهم") < 4)
# trend + context on that same snapshot
check("last-close block has M15 and M5 trend plus جمع‌بندی",
      "M15 " in snap_fix["block"] and "M5 " in snap_fix["block"] and snap_fix["block"].startswith("طلا") and "جمع‌بندی:" in snap_fix["block"])
check("last-close context line: ATR and tight room",
      "نوسان M5 حدود 4 دلار" in snap_fix["block"] and "تا سطح بعدی" in snap_fix["block"] and "جا کم است" in snap_fix["block"])
# نامشخص → volatility only
tr_ns = dict(snap_fix["trend"]); tr_ns["overall"] = "نامشخص"; tr_ns["verdict"] = "جمع‌بندی: نامشخص"
ctx_only = LVIEW.context_line({**snap_fix, "trend": tr_ns})
check("نامشخص context is volatility only", ctx_only == "نوسان M5 حدود 4 دلار" and "تا سطح بعدی" not in ctx_only)
# pullback wording
check("pullback verdict names the lower frame",
      LVIEW.verdict_line("نزولی", "نزولی", "خنثی", "صعودی") == "جمع‌بندی: نزولی؛ M5 در اصلاح صعودی" and
      LVIEW.verdict_line("نزولی", "نزولی", "صعودی", "صعودی") == "جمع‌بندی: نزولی؛ M15 و M5 در اصلاح صعودی" and
      LVIEW.verdict_line("نزولی", "خنثی", "نزولی", "نزولی") == "جمع‌بندی: نامشخص")
# room >= 2×ATR: no «جا کم است»
wide = LVIEW.context_line({"atr_m5": 3.0, "trend": {"overall": "نزولی"},
                           "short": {"below": [{"distance": -8.0}], "above": []}})
check("room at least 2×ATR does not say جا کم است", "تا سطح بعدی 8 دلار" in wide and "جا کم است" not in wide)

# no «زیان» in any rendered user-facing message
s = B.load_state()
cards = [
    B.brief_msg(mk_brief(), s),
    B.short_brief(mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]}), s, cfg, reasons=["x"]),
    B.levels_card(mk_brief(), s),
    B.presession_brief(mk_brief(), s, "am"),
    B.presession_brief(mk_brief(), s, "pm"),
    B.signal_msg(mk_brief(), {"side": "SELL", "entry": 3880, "sl": 3881.6, "tp": 3876}, DG.size_trade(3880, 3881.6, 3876, "SELL", cfg, spread_usd=0.25), s, cfg),
    B.closed_line(datetime(2026, 11, 14, 12, 0, tzinfo=B.TEH), cfg),
    B.friday_reminder(datetime(2026, 11, 13, 23, 30, tzinfo=B.TEH), cfg) or "",
    snap_fix["block"],
]
cards += DG.fa_risk_lines(cfg)
sz_bad = DG.size_trade(3880, 4000, 3870, "SELL", cfg, spread_usd=0.25)  # huge SL → reason_fa
if sz_bad.get("reason_fa"):
    cards.append(sz_bad["reason_fa"])
rendered = "\n".join(B.render(c) if c else "" for c in cards) + "\n" + "\n".join(c or "" for c in cards)
check("no «زیان» in any rendered bot/brief/risk message", "زیان" not in rendered)
check("fa_risk_lines now says ضرر", any("ضرر حد ضرر" in (x or "") or "درگیر ضرر شود" in (x or "") for x in DG.fa_risk_lines(cfg)))

j_after = open(JOURNAL, "rb").read() if os.path.exists(JOURNAL) else None
check("journal.csv untouched", j_before == j_after)
# Friday flag follows the DST-aware session gate (winter cutoff 23:30, close 01:30; summer 22:30 / 00:30)
def flag_at(dt):
    CLOCK[0] = dt; return B.friday_flag()
_c = CLOCK[0]
check("Friday flag: none on Friday afternoon", flag_at(datetime(2026, 11, 13, 18, 0, tzinfo=B.TEH)) == [])
check("Friday flag: winter warning 22:30 -> 23:30", "23:30" in "".join(flag_at(datetime(2026, 11, 13, 22, 30, tzinfo=B.TEH))))
check("Friday flag: Saturday 00:30 still closing (01:30)", "01:30" in "".join(flag_at(datetime(2026, 11, 14, 0, 30, tzinfo=B.TEH))))
check("Friday flag: none after the close", flag_at(datetime(2026, 11, 14, 2, 0, tzinfo=B.TEH)) == [])
check("Friday flag: summer cutoff 22:30", "22:30" in "".join(flag_at(datetime(2026, 7, 17, 21, 30, tzinfo=B.TEH))))
check("Friday flag: none on a Wednesday night", flag_at(datetime(2026, 11, 11, 22, 45, tzinfo=B.TEH)) == [])
CLOCK[0] = _c


# ---- group mirror: signals, 11:15/16:15 briefs and /levels only
GID, OWNER = "-1001958445009", "111"
def with_group(**kw):
    fresh(**kw)
    st = state(); st["channel_id"] = GID; json.dump(st, open(B.STATE_JSON, "w"))

BRIEF[0] = mk_brief(); B.run_brief = lambda state: (CALLS.__setitem__(0, CALLS[0] + 1), copy.deepcopy(BRIEF[0]))[1]
with_group(); CLOCK[0] = datetime(2026, 11, 13, 22, 0, tzinfo=B.TEH); out = run("scheduled")
check("signal is mirrored to the group, same text",
      len(out) == 2 and SENT_TO == [OWNER, GID] and out[0] == out[1] and "فروش طلا" in out[0])
with_group(); CLOCK[0] = datetime(2026, 11, 13, 23, 30, tzinfo=B.TEH); CALLS[0] = 0; out = run("scheduled")
check("Friday reminder stays private",
      len(out) == 1 and SENT_TO == [OWNER] and "ورود جدید بسته است" in out[0] and CALLS[0] == 0)
CLOCK[0] = datetime(2026, 11, 14, 12, 0, tzinfo=B.TEH)
snap = mk_levels(price_bid=3880.0, computed_at="2026-11-13 17:30:00")
st = state(); st["channel_id"] = GID; st["levels"] = snap; json.dump(st, open(B.STATE_JSON, "w")); CALLS[0] = 0
out = run("command", ["/levels"])
check("/levels is mirrored to the group, same text",
      len(out) == 2 and SENT_TO == [OWNER, GID] and out[0] == out[1] and "سن داده" in out[0] and CALLS[0] == 0)
CALLS[0] = 0; out = run("command", ["/scan", "/brief"])
check("/scan and /brief closed lines are mirrored",
      len(out) == 4 and SENT_TO == [OWNER, GID, OWNER, GID] and out[0] == out[1] and out[2] == out[3] and
      all("بازار بسته است" in x for x in out) and CALLS[0] == 0)
CLOCK[0] = datetime(2026, 11, 11, 14, 0, tzinfo=B.TEH)
st = state(); st["channel_id"] = GID; st["presession_sent"] = {}; json.dump(st, open(B.STATE_JSON, "w"))
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]})
out = run("command", ["/brief"])
check("/brief is mirrored without balance or the daily loss cap",
      len(out) == 2 and SENT_TO == [OWNER, GID] and "خلاصه‌ی بازار" in out[0] and "موجودی" in out[0] and "سقف ضرر امروز" in out[0] and
      "خلاصه‌ی بازار" in out[1] and "موجودی" not in out[1] and "سقف ضرر" not in out[1] and "<code>3895.3</code>" in out[1])
out = run("command", ["/scan"])
check("/scan no-trade is mirrored, same text (no balance)",
      len(out) == 2 and SENT_TO == [OWNER, GID] and out[0] == out[1] and "معامله نه" in out[0] and "موجودی" not in out[0])
CLOCK[0] = datetime(2026, 11, 11, 16, 15, tzinfo=B.TEH)
st = state(); st["channel_id"] = GID; st["presession_sent"] = {}; st["signals_sent"] = []; json.dump(st, open(B.STATE_JSON, "w"))
out = run("scheduled")
check("pre-session brief is mirrored without balance or the daily loss cap",
      len(out) == 2 and SENT_TO == [OWNER, GID] and "نیویورک" in out[0] and "موجودی" in out[0] and "سقف ضرر امروز" in out[0] and
      "نیویورک" in out[1] and "موجودی" not in out[1] and "سقف ضرر" not in out[1])
with_group(); BRIEF[0] = mk_brief(); CLOCK[0] = datetime(2026, 11, 16, 11, 15, tzinfo=B.TEH); out = run("scheduled")
check("11:15 signal and London brief are both mirrored; brief balance stays private",
      len(out) == 4 and SENT_TO == [OWNER, GID, OWNER, GID] and "فروش طلا" in out[0] and out[0] == out[1] and
      "لندن" in out[2] and "موجودی" in out[2] and "لندن" in out[3] and "موجودی" not in out[3] and "سقف ضرر" not in out[3])
out = run("test")
check("sample signal stays private", len(out) == 1 and SENT_TO == [OWNER] and "نمونه" in out[0])
FAIL_CHANNEL[0] = True
with_group(); BRIEF[0] = mk_brief(); CLOCK[0] = datetime(2026, 11, 13, 22, 0, tzinfo=B.TEH); out = run("scheduled")
FAIL_CHANNEL[0] = False
check("group send failure does not block the owner's signal",
      len(out) == 1 and SENT_TO == [OWNER] and "فروش طلا" in out[0] and state()["signals_sent"])
fresh(); BRIEF[0] = mk_brief(); CLOCK[0] = datetime(2026, 11, 13, 22, 0, tzinfo=B.TEH); out = run("scheduled")
check("no channel_id means the signal stays with the owner only", len(out) == 1 and SENT_TO == [OWNER] and "فروش طلا" in out[0])


BRIEF[0] = {"error": "down", "price_bid": None, "decision": {"decision": "NO TRADE", "reasons_reject": []}}
st = state(); st["channel_id"] = GID; json.dump(st, open(B.STATE_JSON, "w"))
CLOCK[0] = datetime(2026, 11, 11, 14, 0, tzinfo=B.TEH)
out = run("command", ["/brief"])
check("price-data error on /brief stays private",
      len(out) == 1 and SENT_TO == [OWNER] and "داده‌ی قیمت در دسترس نیست" in out[0] and "موجودی" in out[0])
out = run("command", ["/scan"])
check("price-data error on /scan stays private",
      len(out) == 1 and SENT_TO == [OWNER] and "داده‌ی قیمت در دسترس نیست" in out[0])
br = B.brief_msg(mk_brief(), state())
pub = B.public_card("brief", br)
check("public_card keeps the market card and drops only the balance line",
      "خلاصه‌ی بازار" in (pub or "") and "موجودی" in br and "موجودی" not in (pub or "") and "سقف ضرر امروز" not in (pub or ""))
check("public_card drops error cards", B.public_card("scan", "**⏸ فعلاً معامله نه**\n~~داده‌ی قیمت در دسترس نیست~~") is None)

print(f"\n{len(fails)} failed" + (": " + "; ".join(fails) if fails else ""))
sys.exit(1 if fails else 0)
