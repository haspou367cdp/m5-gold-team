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

JOURNAL = f"{B.ROOT}/journal.csv"
j_before = open(JOURNAL, "rb").read() if os.path.exists(JOURNAL) else None
SENT, FAIL_HTML = [], [False]
def fake_tg(method, **p):
    if method == "sendMessage":
        if FAIL_HTML[0] and p.get("parse_mode") == "HTML":
            return {"ok": False, "description": "Bad Request: can't parse entities"}
        SENT.append(p["text"]); return {"ok": True, "result": {"message_id": len(SENT)}}
B.tg = fake_tg
CLOCK = [datetime(2026, 11, 11, 14, 0, tzinfo=B.TEH)]   # Wednesday
B.now_teh = lambda: CLOCK[0]
cfg = B.CFG = DG.load_config()
NEWS_OK = [True]
B.prepare_news = lambda state, force=False: NEWS_OK[0]

def mk_brief(side="SELL", entry=3880.0, sl=3881.6, tp=3876.0, **kw):
    sz = DG.size_trade(entry, sl, tp, side, cfg, spread_usd=0.25)
    b = {"decision": {"decision": side, "reasons_reject": []}, "price_bid": entry, "bias": "bearish",
         "plan": {"side": side, "entry": entry, "sl": sl, "tp": tp}, "sizing": sz,
         "quality": {"ok": True, "age_minutes": 1}, "fallback": False, "news_window": {},
         "session_entry": {"blocked": False}, "resistances": [{"price": 3885.0}], "supports": [{"price": 3870.0}],
         "news_windows_next_24h": ["16:45–17:15 US x"]}
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
    SENT.clear()
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
SENT.clear(); B.send("\n".join(["خط آزمایشی " + str(i) for i in range(600)]))
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
check("/brief: market summary title, never a signal (even with a BUY/SELL brief)", "خلاصه‌ی بازار" in br and "<code>" not in br and "فروش طلا" not in br)
check("/brief: day high/low from candles, DaryaGold +0.3", "سقف روز  ۳۹۲۳٫۳" in br and "کف روز  ۳۸۷۵٫۲" in br)
check("/brief: nearest levels skip a level closer than max(0.3 ATR, $1)", "مقاومت نزدیک  ۳۸۹۵٫۳" in br and "حمایت نزدیک  ۳۸۸۰٫۵" in br and "۳۸۸۸٫۴" not in br)
check("/brief: all remaining news today (incl. ongoing), none passed or tomorrow", all(x in br for x in ["۱۸:۴۰ تا ۱۹:۰۵", "۱۹:۳۰", "۲۰:۱۵", "۲۲:۰۰"]) and "۱۶:۴۵" not in br and "۰۳:۱۵" not in br)
check("/brief: balance and today's loss cap from the day's start equity", "موجودی ۲٫۹۵ میلیون" in br and "سقف ضرر امروز ۲۰۰ هزار" in br)
check("/brief: no 'strong'/قوی, no زیان", not any(w in br for w in ["قوی", "strong", "زیان"]))
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]}, news_window={"inside": True, "action": "block", "end": "2026-11-11 19:05"})
out = run("command", ["/scan"]); sc = out[0] if out else ""
check("/scan no trade: title + one reason + price only", "معامله نه" in sc and "پنجره‌ی خبری تا ۱۹:۰۵" in sc and "طلا" in sc and
      len([l for l in sc.split("\n") if l.strip()]) == 3 and "سقف" not in sc and "موجودی" not in sc)
CLOCK[0] = datetime(2026, 11, 11, 16, 15, tzinfo=B.TEH); st = state(); st["presession_sent"] = {}; json.dump(st, open(B.STATE_JSON, "w"))
BRIEF[0] = mk_brief(decision={"decision": "NO TRADE", "reasons_reject": ["x"]}, resistances=[{"price": 3895.0}], supports=[{"price": 3870.0}])
out = run("scheduled"); check("pre-session brief uses the same summary (day high/low + nearest levels)", len(out) == 1 and "نیویورک" in out[0] and "سقف روز" in out[0] and "حمایت نزدیک" in out[0])
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
    st = state(); st.update(shadow=[], signals_sent=[], presession_sent={}, friday_reminder_sent=None); st.pop("dg_offset", None)
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
                 (datetime(2026, 11, 15, 20, 0, tzinfo=B.TEH), "Sunday 20:00"), (datetime(2026, 11, 16, 2, 0, tzinfo=B.TEH), "Monday 02:00")]:
    CLOCK[0] = when; CALLS[0] = 0; out = run("command", ["/scan", "/brief"])
    check(f"{nm}: /scan and /brief -> one closed line each (reopen Monday 02:30), no analysis",
          len(out) == 2 and all(x.count("\n") == 0 and "بازار بسته است" in x and "دوشنبه ۰۲:۳۰" in x for x in out) and CALLS[0] == 0)
for when in [datetime(2026, 11, 14, 11, 15, tzinfo=B.TEH), datetime(2026, 11, 15, 16, 15, tzinfo=B.TEH), datetime(2026, 11, 14, 3, 30, tzinfo=B.TEH)]:
    CLOCK[0] = when; CALLS[0] = 0
    check(f"weekend scheduled run {when:%a %H:%M}: silent, no analysis", run("scheduled") == [] and CALLS[0] == 0)
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

print(f"\n{len(fails)} failed" + (": " + "; ".join(fails) if fails else ""))
sys.exit(1 if fails else 0)
