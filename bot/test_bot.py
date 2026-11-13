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
SENT, UPDATES, FAIL_HTML = [], [], [False]
def fake_tg(method, **p):
    if method == "getUpdates":
        r = {"ok": True, "result": list(UPDATES)}; UPDATES.clear(); return r
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
FAIL_HTML[0] = True; out = run("command", ["/brief"]); FAIL_HTML[0] = False
check("HTML failure -> plain-text fallback without tags", len(out) == 1 and "<" not in out[0] and "طلا" in out[0])
SENT.clear(); B.send("\n".join(["خط آزمایشی " + str(i) for i in range(600)]))
check("long message split <=4096 on line breaks", len(SENT) >= 2 and all(len(x) <= 4096 for x in SENT) and all(x.split("\n")[-1].startswith("\u200fخط") for x in SENT))

j_after = open(JOURNAL, "rb").read() if os.path.exists(JOURNAL) else None
check("journal.csv untouched", j_before == j_after)
print(f"\n{len(fails)} failed" + (": " + "; ".join(fails) if fails else ""))
sys.exit(1 if fails else 0)
