#!/usr/bin/env python3
"""bot.py - Telegram front-end for the M5 gold toolkit, run by GitHub Actions (no server).

The Supabase Edge Function (supabase/functions/tg-bot) owns Telegram input (webhook); Postgres holds the state; pg_cron owns the schedule.
Each run: the workflow pulls state from Supabase into STATE_DIR, this script answers queued /scan, /brief and /levels,
refreshes the news calendar, runs tools/brief.py, applies the automated DaryaGold risk check (replaces M5-Risk),
sends a message only when needed, and writes state.json; the workflow pushes the bot-owned keys back.

modes : scheduled  - full check; sends a signal only if every gate passes (deduped); pre-session briefs
        command    - answer queued /scan, /brief or /levels only
        test       - send one sample signal (labelled «نمونه»), nothing else
env   : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, STATE_DIR (state.json + news_windows.json pulled from Supabase)
Signal-only research. Never places trades. Not financial advice."""
import argparse, csv, html, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta

ROOT = "/workspace/m5-gold-team"
sys.path.insert(0, f"{ROOT}/tools")
from zoneinfo import ZoneInfo
TEH = ZoneInfo("Asia/Tehran")
import broker_daryagold as DG
import risk_gate as RG
import shadow as SH
import level_view as LVIEW

STATE_DIR = os.environ.get("STATE_DIR", f"{ROOT}/state")
STATE_JSON = f"{STATE_DIR}/state.json"
STATE_NEWS = f"{STATE_DIR}/news_windows.json"
DATA_NEWS = f"{ROOT}/data/news_windows.json"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
NEWS_REFRESH_H = 3
NEWS_MAX_AGE_H = 30          # older calendar => no signals (fail closed)
PRESESSION = {"am": ("11:10", "12:05"), "pm": ("16:10", "17:05")}  # wide: GitHub cron can run late; sent once per day
ASIA = ("03:30", "11:15")   # weekday Asia session (Tehran): scheduled runs only log shadow setups, never send anything
# /help, /status, /balance, /loss, /win, /undo, /groupoff, /groupon are answered by the Supabase Edge Function (supabase/functions/tg-bot).

# ---------------- state ----------------
def now_teh():
    return datetime.now(TEH)

def load_state():
    try:
        with open(STATE_JSON) as f:
            s = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        s = {}
    s.setdefault("equity_toman", float(DG.load_config()["equity_toman"]))
    s.setdefault("presession_sent", {})
    s.setdefault("signals_sent", [])
    today = now_teh().strftime("%Y-%m-%d")
    if (s.get("day") or {}).get("date") != today:
        s["day"] = {"date": today, "losses": 0, "loss_toman": 0, "wins": 0, "win_toman": 0, "records": []}
    s["presession_sent"] = {k: v for k, v in s["presession_sent"].items() if k >= today}
    s["signals_sent"] = s["signals_sent"][-20:]
    return s

def apply_offset(state, cfg):
    """bot_state dg_offset (set by /offset in Telegram) overrides the file's price_offset_usd, for this run and brief.py."""
    v = state.get("dg_offset")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return cfg
    if abs(v) > 5:
        return cfg
    cfg["price_offset_usd"] = v
    os.environ["DG_OFFSET_USD"] = str(v)
    return cfg

def save_state(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    s["updated_at_tehran"] = now_teh().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATE_JSON + ".tmp", "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(STATE_JSON + ".tmp", STATE_JSON)

SIGNAL_LOCK_MIN = 60   # max 1 position: after a signal, no new one for 60 min unless /loss or /win closes it

# ---------------- telegram ----------------
def tg(method, **params):
    if not TOKEN:
        print(f"[no token] {method}")
        return None
    data = urllib.parse.urlencode(params).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # never print the URL (contains the token)
            print(f"telegram {method} failed (attempt {attempt + 1}): {type(e).__name__}")
            time.sleep(2)
    return None

def group_enabled(state=None):
    """bot_state.group_enabled; missing flag means sending is on. Not mergeable from GitHub."""
    return not state or state.get("group_enabled") is not False

def channel_chat(state=None):
    """Mirror target from bot_state.channel_id (the BAROBAX group). Empty if unset, disabled, or equal to the owner chat."""
    if not group_enabled(state):
        return ""
    raw = (state or {}).get("channel_id")
    if raw is None or raw == "":
        return ""
    cid = str(raw).strip()
    return cid if cid and cid != str(CHAT) else ""

def send_chat(chat, text):
    if not chat:
        print("[no chat id] message not sent:\n" + text)
        return False
    text = render(text)
    ok = True
    while text:
        cut = text.rfind("\n", 0, 3900) if len(text) > 3900 else len(text)
        cut = cut if cut > 0 else min(len(text), 3900)
        part, text = text[:cut], text[cut:].lstrip("\n")
        r = tg("sendMessage", chat_id=chat, text=part, parse_mode="HTML", disable_web_page_preview="true")
        good = bool(r and r.get("ok"))
        if os.environ.get("BOT_ECHO") == "1":
            print("----- sent text -----\n" + part + "\n---------------------")
        if not good:  # never lose a message over formatting
            r = tg("sendMessage", chat_id=chat, text=html.unescape(re.sub(r"<[^>]+>", "", part)), disable_web_page_preview="true")
            good = bool(r and r.get("ok"))
        print(f"telegram send: {'ok message_id=' + str(r['result']['message_id']) if good else 'FAILED ' + str((r or {}).get('description'))}")
        ok = ok and good
    return ok

def public_card(kind, text):
    """Group copy of a mirrored card. Drops personal balance/loss-cap, signal risk in toman, and error cards."""
    if not text:
        return None
    if "داده‌ی قیمت در دسترس نیست" in text:
        return None
    if kind in ("brief", "presession"):
        lines = [ln for ln in text.split("\n") if not ("موجودی" in ln and "سقف ضرر امروز" in ln)]
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)
    if kind == "signal":
        lines = []
        for ln in text.split("\n"):
            ln = re.sub(r"(?:^| · )ریسک [^·\n]*تومان", "", ln)
            ln = re.sub(r"^ · ", "", ln)
            if "تومان" in ln:
                continue
            lines.append(ln)
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)
    return text

def send(text, *, also=None, also_text=None):
    """Send to the owner. If also is set, also try that chat (also_text if given); a failure there never changes the owner result."""
    ok = send_chat(CHAT, text)
    if also and str(also) != str(CHAT):
        try:
            body = text if also_text is None else also_text
            if body:
                send_chat(also, body)
        except Exception as e:
            print(f"telegram group send failed: {type(e).__name__}")
    return ok

def send_public(kind, text, state):
    """Owner gets the full card; the group gets public_card() or nothing."""
    pub = public_card(kind, text)
    cid = channel_chat(state) if pub is not None else ""
    return send(text, also=cid or None, also_text=pub if cid and pub != text else None)

# ---------------- news calendar ----------------
def prepare_news(state, force=False):
    """data/news_windows.json <- state copy, refreshed from ForexFactory every few hours."""
    if not IN_CI:  # on the box, data/news_windows.json belongs to M5-News; never overwrite it
        return True
    os.makedirs(os.path.dirname(DATA_NEWS), exist_ok=True)
    if os.path.exists(STATE_NEWS):
        with open(STATE_NEWS) as f, open(DATA_NEWS, "w") as g:
            g.write(f.read())
    last = state.get("news_fetched_at")
    age_h = None
    if last:
        age_h = (now_teh() - datetime.strptime(last, "%Y-%m-%d %H:%M").replace(tzinfo=TEH)).total_seconds() / 3600
    if force or age_h is None or age_h >= NEWS_REFRESH_H:
        try:
            p = subprocess.run([sys.executable, f"{ROOT}/tools/ff_calendar.py"], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            p = subprocess.CompletedProcess([], 4, "", "ForexFactory timeout")
        print(p.stdout.strip(), p.stderr.strip()[-300:])
        if p.returncode == 0:
            state["news_fetched_at"] = now_teh().strftime("%Y-%m-%d %H:%M")
            age_h = 0
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(DATA_NEWS) as f, open(STATE_NEWS, "w") as g:
                g.write(f.read())
    return age_h is not None and age_h < NEWS_MAX_AGE_H

# ---------------- brief + automated risk check ----------------
def day_cap(state, cfg=None):
    """Daily net-loss cap: 20% of the day's starting equity (set by the Edge Function at the first command of the day),
    so a /trade that changes equity during the day does not move the cap."""
    d = state.get("day") or {}
    base = float(d.get("start_equity") or 0) or float(state["equity_toman"])
    return base * float((cfg or {}).get("daily_loss_pct_max", 20)) / 100
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"

def write_journal(state):
    """Minimal journal.csv from today's /loss entries so brief.py's daily-stop gate sees them.
    Only on the GitHub runner: on the box the real journal.csv must never be touched."""
    if not IN_CI:
        return
    d = state["day"]
    with open(f"{ROOT}/journal.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["signal_id", "signal_time_tehran", "status", "outcome", "result_R"])
        w.writeheader()
        for i in range(int(d.get("losses") or 0)):
            w.writerow({"signal_id": f"tg-loss-{i}", "signal_time_tehran": d["date"] + " 00:00",
                        "status": "closed", "outcome": "loss", "result_R": "-1"})

def run_brief(state):
    write_journal(state)
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, f"{ROOT}/tools/brief.py", "--equity", str(int(state["equity_toman"]))],
                           capture_output=True, text=True, timeout=150)
    except subprocess.TimeoutExpired:
        p = subprocess.CompletedProcess([], 3, "", "brief.py timeout")
    print(f"brief rc={p.returncode} in {time.time() - t0:.1f}s")
    try:
        with open(f"{ROOT}/data/meta.json") as f:
            m = json.load(f)
        print(f"price source={m.get('source')} fallback={m.get('fallback')} as_of={m.get('as_of_tehran')} age={m.get('age_minutes')}")
    except Exception:
        pass
    if p.returncode not in (0, 2):
        print(p.stderr[-800:])
    try:
        if p.returncode not in (0, 2) or os.path.getmtime(f"{ROOT}/latest_brief.json") < t0 - 1:
            raise RuntimeError("brief failed or stale")  # never act on an old latest_brief.json
        with open(f"{ROOT}/latest_brief.json") as f:
            b = json.load(f)
    except Exception:
        b = {"decision": "NO TRADE", "error": True}
    if p.returncode == 3:
        b = {"decision": "NO TRADE", "error": True, "quality": {"ok": False, "fa": "هیچ منبع قیمتی در دسترس نیست."}}
    b["_rc"] = p.returncode
    return b

def risk_check(b, state, cfg, news_ok):
    """Automated M5-Risk. Returns (approved, plan, sizing, reasons_fa)."""
    dec = b.get("decision")
    dec = dec if isinstance(dec, dict) else {"decision": dec or "NO TRADE"}
    reasons = []
    side = dec.get("decision")
    plan, sizing = b.get("plan") or dec.get("plan"), b.get("sizing") or dec.get("sizing")
    if side not in ("BUY", "SELL"):
        reasons += dec.get("reasons_reject") or [((b.get("quality") or {}).get("fa")) or "ستاپ تأییدشده‌ای وجود ندارد."]
        return False, None, None, reasons
    eq = float(state["equity_toman"])
    q = b.get("quality") or {}
    if b.get("fallback"):
        reasons.append("قیمت از منبع جایگزین (قرارداد آتی) آمده است، نه بازار نقدی؛ با این داده سیگنال داده نمی‌شود.")
    # session, news blackout, data freshness, net R:R (worse fee scenario) and stop-out: tools/risk_gate.py
    gate = None
    if plan and sizing and sizing.get("size") and plan.get("tp") is not None:
        gate = RG.evaluate(now_teh(), side, plan.get("entry"), plan.get("sl"), plan.get("tp"),
                           unit=sizing["size"].get("key") or "full_unit", order_type="MARKET",
                           spread_usd=(b.get("spread") or {}).get("current"),
                           data_ok=bool(q.get("ok")), data_age_min=q.get("age_minutes"),
                           session=b.get("session_entry"), news_window=b.get("news_window") if "news_window" in b else None,
                           news_ok=news_ok, cfg=cfg, min_net_rr=float(cfg.get("min_net_rr", 1.5)))
        reasons += gate["reasons_fa"]
        sizing["gate"] = {"status": gate["status"], "warnings_fa": gate["warnings_fa"], "net_rr": gate["metrics"].get("net_rr")}
    else:   # no numeric plan: still report the market-condition reasons
        g = RG.evaluate(now_teh(), None, None, None, None, data_ok=bool(q.get("ok")), data_age_min=q.get("age_minutes"),
                        session=b.get("session_entry"), news_window=b.get("news_window") if "news_window" in b else None,
                        news_ok=news_ok, cfg=cfg)
        reasons += [r for r in g["reasons_fa"] if r != "ستاپ تأییدشده‌ای وجود ندارد."]
    d = state["day"]
    last = (state.get("signals_sent") or [None])[-1]
    if last and last.get("at"):
        age = (now_teh() - datetime.strptime(last["at"], "%Y-%m-%d %H:%M").replace(tzinfo=TEH)).total_seconds() / 60
        closed = any(f"{d['date']} {r.get('at', '')}" >= last["at"] for r in d.get("records", []))
        if 0 <= age < SIGNAL_LOCK_MIN and not closed:
            reasons.append("معامله‌ی سیگنال قبلی هنوز باز فرض می‌شود؛ بعد از بستن، `/loss` یا `/win` را بفرستید.")
    cap_loss = day_cap(state, cfg)
    if int(d.get("losses") or 0) >= int(cfg.get("max_consecutive_losses", 3)):
        reasons.append(f"توقف روزانه فعال است: امروز {d['losses']} ضرر ثبت شده است.")
    if float(d.get("loss_toman") or 0) - float(d.get("win_toman") or 0) >= cap_loss:
        reasons.append(f"توقف روزانه فعال است: ضرر خالص امروز به {DG.toman(cap_loss)} تومان (۲۰٪ حساب) رسیده است.")
    if not plan or not sizing or not sizing.get("ok") or not sizing.get("size"):
        reasons.append("با سقف ریسک فعلی، نه نیم واحد مجاز است و نه یک واحد.")
    else:
        s = sizing["size"]
        if s.get("key") not in ("half_unit", "full_unit"):
            reasons.append("فقط حجم نیم واحد یا یک واحد مجاز است.")
        if plan.get("tp") is None:
            reasons.append("حد سود مشخصی بر اساس ساختار بازار پیدا نشد.")
        if float(s.get("risk_toman") or 1e18) > eq * float(cfg.get("risk_per_trade_pct_max", 10)) / 100 + 1:
            reasons.append("ریسک این معامله بیش از ۱۰٪ حساب است.")
        if float(s.get("net_rr") or 0) < float(cfg.get("min_net_rr", 1.5)) and gate is None:
            reasons.append(f"نسبت سود به ضرر خالص ({s.get('net_rr')}) کمتر از ۱٫۵ است.")
        if abs(float(plan["entry"]) - float(plan["sl"])) + 1e-9 < float(cfg.get("min_sl_usd", 1.0)):
            reasons.append("فاصله‌ی حد ضرر کمتر از ۱ دلار است.")
        if float(s.get("fee") or 0) < 14000:
            reasons.append("کارمزد کمتر از ۱۴٬۰۰۰ تومان حساب شده است که با قرارداد دریاگلد نمی‌خواند.")
        if float(s.get("margin") or 0) > eq:
            reasons.append("وجه تضمین از موجودی حساب بیشتر است.")
    return (not reasons), plan, sizing, reasons

# ---------------- messages ----------------
import re
FA_SIDE = {"BUY": "خرید", "SELL": "فروش"}
FA_TREND = {"bullish": "صعودی", "bearish": "نزولی", "neutral": "خنثی"}
_FIXED = [  # long tool sentences -> natural Persian
    (r"\s*[\(\[]\s*bid\s*[\d.]+\s*[\)\]]", ""),  # owner: show DaryaGold prices only, never the raw feed price
    (r"\s*\[خام:?\s*[\d.]+\]", ""),
    (r"موتور مجاز ادامه روند است، ولی ستاپ ادامه \(عقب‌نشینی به مرجع \+ شکست ساختار M5 و بازآزمایی\) دیده نشد\.",
     "بازار رونددار است، ولی ستاپ ادامه‌ی روند (اصلاح تا سطح مرجع، بعد شکست ساختار و برگشت به سطح در M5) هنوز شکل نگرفته است."),
    (r"موتور مجاز جاروی نقدینگی / بازگشت به میانگین است، ولی .*?دیده نشد\.",
     "بازار رنج است، ولی ستاپ جاروی نقدینگی (عبور از سقف یا کف، برگشت کندل M5 به داخل محدوده و شکست ساختار کوتاه‌مدت) هنوز شکل نگرفته است."),
    (r"صبر کن: قیمت روی سطح خلاف جهت \(([\d.]+)\) است؛ ورود (\S+) اینجا خلاف منطق سطح است\.",
     lambda m: f"صبر کنید: قیمت درست روی سطح {m.group(1)} است و ورود {'فروش' if m.group(2) == 'نزولی' else 'خرید'} در این نقطه منطقی نیست."),
    (r"ساختار در ([\d.]+) شکست و بازآزمایی شد", r"سطح ساختاری \1 شکسته شد و قیمت دوباره به آن برگشت"),
    (r"صبر کن(?!ید)", "صبر کنید"), (r"\bبمان\b", "بمانید"),
    (r"رژیم خبری / غیرعادی است: ", "بازار در وضعیت خبری یا غیرعادی است: "),
    (r"هیچ موتوری برای این رژیم مجاز نیست\.", "در وضعیت فعلی بازار هیچ ستاپی مجاز نیست."),
    (r"جهت یا حکم صبر با ستاپ هم‌خوان نیست\.", "جهت کلی بازار با ستاپ هم‌خوان نیست."),
]
_WORDS = [("ادامه روند", "ادامه‌ی روند"), ("جاروی نقدینگی / بازگشت به میانگین", "جاروی نقدینگی و بازگشت به میانگین"),
          ("بایاس تکنیکال", "جهت تکنیکال"), ("بایاس خبری", "جهت خبری"), ("بایاس", "جهت کلی"),
          ("رژیم رونددار است", "بازار رونددار است"), ("رژیم رنج است", "بازار رنج است"), ("رژیم", "وضعیت بازار"), ("بازآزمایی", "برگشت به سطح"), ("عقب‌نشینی", "اصلاح"), ("عقب نشست", "اصلاح کرد"),
          ("اوردر", "سفارش"), ("پوزیشن", "معامله‌ی باز"), ("تاییدنشده", "تأییدنشده"), ("نیم واحدی", "نیم واحد"),
          ("نسبت خالص", "نسبت سود به ضرر خالص"), ("پاداش", "سود"), ("NO TRADE", "معامله نکنید"),
          ("سطح A", "ردیف A"), ("سطح B", "ردیف B"), ("سطح C", "ردیف C"), ("تایم‌ها", "تایم‌فریم‌ها"),
          ("رنج سشن", "رنج جلسه‌ی معاملاتی"), ("سشن", "جلسه‌ی معاملاتی"),
          ("می شود", "می‌شود"), ("نمی شود", "نمی‌شود"), ("  ", " ")]
_PRICE = re.compile(r"(?<![\d\-:.])([2-6]\d{3}\.\d{1,3})(?![\d\-:])")
CFG = None

def px(p):
    """DaryaGold price (LTR-safe Latin digits)."""
    if p is None:
        return "—"
    bid = float(p)
    dg = DG.to_broker(bid, CFG) if CFG else bid + 0.3
    return f"{dg:.2f}".rstrip("0").rstrip(".")

def raw(p):
    return f"{float(p):.2f}".rstrip("0").rstrip(".")

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_NUM = re.compile(r"(?<![A-Za-z\d.])\d+(?:\.\d+)?")

def fa_num(t):
    """Persian digits and decimal separator; tokens like M5, H1, M15, EMA20, XAUUSD stay Latin."""
    t = re.sub(r"(?<=\d),(?=\d{3})", "٬", t)  # thousands separator
    return _NUM.sub(lambda m: m.group(0).replace(".", "٫").translate(_FA_DIGITS), t)

def render(t):
    """**bold** -> <b>, HTML-escaped, Persian digits."""
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"~~(.+?)~~", r"<i>\1</i>", t)
    # tap-to-copy prices stay Latin ("3884.2") so they paste into DaryaGold's order box; the rest is Persian
    parts = re.split(r"`(.+?)`", t)
    # a command inside code ("/loss 150000") gets LRM on both sides so "/" stays with it in right-to-left lines
    t = "".join((f"\u200e<code>{x}</code>\u200e" if x.startswith("/") else f"<code>{x}</code>") if i % 2 else fa_num(x)
                for i, x in enumerate(parts))
    # RLM at the start of every line keeps iPhone/Android Telegram in right-to-left order
    return "\n".join(("\u200f" + ln) if ln.strip() else ln for ln in t.split("\n"))

_LABEL_RANK = ["ماه قبل", "ماه جاری", "هفته", "نیویورک دیروز", "دیروز", "امروز", "روزانه", "بازگشایی",
               "لندن", "آسیا", "نیویورک", "برابر", "چرخشی H4", "چرخشی H1", "چرخشی M15", "VWAP", "چرخشی M5", "EMA", "رُند"]
_LABEL_SHORT = [("رنج بازگشایی", "بازگشایی"), (" (پروکسی حجم تیک)", ""), ("عدد رُند ۵", "عدد رُند"),
                ("سقف برابر M15", "سقف‌های برابر M15"), ("کف برابر M15", "کف‌های برابر M15")]

def one_label(labels):
    """Pick a single, short label (avoids contradictory pairs such as swing high + swing low)."""
    items = [x.strip() for x in re.split(r"[،,]", labels or "") if x.strip()]
    if not items:
        return ""
    rank = lambda x: next((i for i, k in enumerate(_LABEL_RANK) if k in x), len(_LABEL_RANK))
    best = sorted(items, key=rank)[0]
    for a, b in _LABEL_SHORT:
        best = best.replace(a, b)
    return best.strip()

def lvl(l):
    lab = one_label(l.get("label_fa"))
    return f"{px(l['price'])} ({lab})" if lab else px(l["price"])

def strip_md(t):
    return (t or "").replace("**", "").replace("_", "")

def fa_polish(t):
    """Make tool text read naturally: glossary terms, polite imperative, DaryaGold prices."""
    t = strip_md(t)
    already_broker = bool(re.search(r"bid\s*[\d.]+|\[خام", t))  # text already in DaryaGold prices
    for a, b in _FIXED:
        t = re.sub(a, b, t)
    for a, b in _WORDS:
        t = t.replace(a, b)
    if not already_broker:
        t = _PRICE.sub(lambda m: px(float(m.group(1))), t)
    t = re.sub(r"\(([^()]*،[^()]*)\)", lambda m: f"({one_label(m.group(1))})", t)
    return t.strip()

def head(b):
    return (b.get("evaluated_at_tehran") or b.get("generated_at_tehran") or now_teh().strftime("%Y-%m-%d %H:%M"))[:16]

def px1(p):
    """Compact DaryaGold price, one decimal."""
    if p is None:
        return "—"
    bid = float(p)
    dg = DG.to_broker(bid, CFG) if CFG else bid + 0.3
    return f"{dg:.1f}"

def _hm(x):
    return str(x or "")[-5:]

def _windows(b):
    """[(start 'HH:MM', end 'HH:MM')] for the next 24 h, from the brief."""
    out = []
    for w in b.get("news_windows_next_24h") or []:
        m = re.match(r"\s*(\d\d:\d\d)\s*[–-]\s*(\d\d:\d\d)", w)
        if m:
            out.append((m.group(1), m.group(2)))
    return out

def next_news(b):
    nw_ = b.get("news_window") or {}
    if nw_.get("next_start"):
        return f"{_hm(nw_['next_start'])}–{_hm(nw_.get('next_end'))}"
    now = now_teh().strftime("%H:%M")
    for a, z in _windows(b):
        if a > now:
            return f"{a}–{z}"
    return None

def short_reason(b, reasons):
    """One short, plain reason for a NO TRADE."""
    nw_ = b.get("news_window") or {}
    text = " ".join(reasons or [])
    if nw_.get("inside"):
        return f"پنجره‌ی خبری تا {_hm(nw_.get('end'))}"
    if nw_.get("soon_block") or ("دقیقه تا پنجره" in text):
        return f"پنجره‌ی خبری از {_hm(nw_.get('next_start'))} تا {_hm(nw_.get('next_end'))}"
    if "پنجره‌ی خبری" in text and "ورود ممنوع" in text:
        return "داخل پنجره‌ی خبری"
    if (b.get("session_entry") or {}).get("blocked"):
        return "جمعه‌شب، ورود جدید ممنوع" if (b["session_entry"].get("friday_window")) else "بازار بسته است"
    if "باز فرض می‌شود" in text:
        return "معامله‌ی قبلی هنوز باز است"
    if "توقف روزانه" in text:
        return "توقف روزانه فعال است"
    if "تازه نیست" in text or "کهنه" in text or "منبع قیمتی" in text:
        return "داده‌ی قیمت تازه نیست"
    if "منبع جایگزین" in text:
        return "قیمت معتبر در دسترس نیست"
    if "تقویم خبری" in text:
        return "تقویم خبری در دسترس نیست"
    if "خلاف جهت" in text or "روی سطح" in text:
        return "قیمت روی سطح است؛ صبر کنید"
    if "وسط راه" in text:
        return "قیمت وسط محدوده است؛ صبر کنید"
    if "خنثی" in text:
        return "جهت بازار مشخص نیست"
    if "اسپرد" in text:
        return "اسپرد غیرعادی است"
    if "نسبت" in text:
        return "نسبت سود به ضرر کافی نیست"
    if "حجم" in text or "ریسک" in text:
        return "ریسک ستاپ بیش از سقف مجاز است"
    return "ستاپ تأییدشده‌ای نیست"

def sr_line(b):
    r = (b.get("resistances") or [None])[0]
    s_ = (b.get("supports") or [None])[0]
    parts = []
    if r: parts.append(f"مقاومت: {px1(r['price'])}")
    if s_: parts.append(f"حمایت: {px1(s_['price'])}")
    return [" · ".join(parts)] if parts else []

# ---------------- cards ----------------
ARROW = {"bearish": "↘️", "bullish": "↗️", "neutral": "↔️"}
FA_WEEKDAY = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
FA_MONTH = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

def jalali(gy, gm, gd):
    """Gregorian -> Solar Hijri (jalaali algorithm, no dependency)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053); days %= 12053
    jy += 4 * (days // 1461); days %= 1461
    if days > 365:
        jy += (days - 1) // 365; days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd

def fa_date(t):
    jy, jm, jd = jalali(t.year, t.month, t.day)
    return f"{FA_WEEKDAY[t.weekday()]} {jd} {FA_MONTH[jm - 1]}"

def toman_short(v):
    v = float(v or 0)
    if v >= 1e6:
        return f"{v / 1e6:.2f}".rstrip("0").rstrip(".") + " میلیون"
    if v >= 1e3:
        return f"{round(v / 1e3):.0f} هزار"
    return f"{v:.0f}"

def p1(bid):
    dg = DG.to_broker(float(bid), CFG) if CFG else float(bid) + 0.3
    return f"{dg:.1f}"

def friday_flag():
    """Friday-close note: shown from 1.5 h before the Friday entry cutoff (22:30 Tehran) until the 00:30 close."""
    t = now_teh()
    try:
        se = DG.session_entry_block(t, CFG)
        start = datetime.strptime(se["block_start_tehran"], "%Y-%m-%d %H:%M").replace(tzinfo=TEH)
        close = datetime.strptime(se["close_tehran"], "%Y-%m-%d %H:%M").replace(tzinfo=TEH)
    except Exception:
        return []
    if start - timedelta(minutes=90) <= t < start:
        return [f"🏳️ از {start:%H:%M} ورود بسته است"]
    if start <= t < close:
        return [f"🏳️ ورود بسته است؛ همه‌چیز تا {close:%H:%M} بسته شود"]
    return []

NY = ZoneInfo("America/New_York")
def day_start(t):
    """Forex trading day start: 17:00 New York (DaryaGold/MT server 00:00; 01:30 Tehran in US winter, 00:30 in summer)."""
    ny = t.astimezone(NY)
    st = ny.replace(hour=17, minute=0, second=0, microsecond=0)
    if ny < st:
        st -= timedelta(days=1)
    return st.astimezone(TEH)

def day_hilo(t):
    """(high_bid, low_bid) of today's forex day from 1-minute bid candles, or None."""
    try:
        import pandas as pd
        d = pd.read_parquet(f"{ROOT}/data/xauusd_1m.parquet", columns=["h_b", "l_b"])
        d = d[d.index >= pd.Timestamp(day_start(t)).tz_convert("UTC")]
        if d.empty:
            return None
        return float(d.h_b.max()), float(d.l_b.min())
    except Exception as e:
        print("day_hilo unavailable:", type(e).__name__)
        return None

def levels_snap(b, state=None):
    """The one stored snapshot. Never recompute."""
    return (b or {}).get("levels") or ((state or {}).get("levels") if state is not None else None)

def near_levels(b, state=None):
    """Nearest above / below = the top items of /levels (same snapshot, not a second pick)."""
    n = (levels_snap(b, state) or {}).get("nearest") or {}
    return n.get("above"), n.get("below")

def hilo(b, state=None):
    """Day high/low from candles only (not the short level set)."""
    L = []
    hl = day_hilo(now_teh())
    if hl:
        L.append(f"سقف روز  {p1(hl[0])}   ·   کف روز  {p1(hl[1])}")
    return L

def levels_block(b, state=None):
    snap = levels_snap(b, state)
    if snap and snap.get("block"):
        return snap["block"]
    return "داده‌ی سطوح در دسترس نیست"

def levels_card(b, state, title="سطوح"):
    """Dedicated /levels message: the shared block, plus the age of the stored snapshot."""
    t = now_teh()
    L = [f"**{title}**", f"~~{fa_date(t)} · {t:%H:%M}~~", ""]
    snap = levels_snap(b, state)
    if snap and not LVIEW.is_fresh(snap, t):
        age = LVIEW.age_minutes(snap, t)
        if age is not None and age >= 0:
            mins = int(round(age))
            L.append(f"سن داده  {mins} دقیقه")
            L.append("")
    L.append(levels_block(b, state))
    return "\n".join(L)

def short_brief(b, state, cfg, reasons=None, title=None):
    """/scan without a signal: title, one-line reason, then the same levels block as /levels."""
    if b.get("error") or b.get("price_bid") is None:
        return "**⏸ فعلاً معامله نه**\n~~داده‌ی قیمت در دسترس نیست~~"
    dec = b.get("decision") if isinstance(b.get("decision"), dict) else {"decision": b.get("decision")}
    rs = reasons if reasons else (dec.get("reasons_reject") or [])
    return "\n".join(["**⏸ فعلاً معامله نه**", f"~~{short_reason(b, rs)}~~", "",
                      levels_block(b, state)])

def market_summary(b, state, title):
    """/brief and the pre-session briefs: the shared levels block, today's remaining news,
    balance and today's loss cap. Never a signal."""
    t = now_teh()
    L = [f"**{title}**", f"~~{fa_date(t)} · {t:%H:%M}~~", ""]
    if b.get("error") or b.get("price_bid") is None:
        L.append("داده‌ی قیمت در دسترس نیست")
    else:
        L.append(levels_block(b, state))
    now = t.strftime("%H:%M")
    wins = [(a, z) for a, z in _windows(b) if a >= now or z > now]
    L.append("")
    if wins:
        L.append("🔔 خبرهای باقی‌مانده‌ی امروز")
        L += [f" {a} تا {z}" for a, z in wins]
    else:
        L.append("🔔 امروز خبر مهم دیگری ثبت نشده")
    L += ["", f"💼 موجودی {toman_short(state['equity_toman'])} · سقف ضرر امروز {toman_short(day_cap(state, CFG))}"]
    L += friday_flag()
    return "\n".join(L)


def presession_brief(b, state, name):
    return market_summary(b, state, "☀️ لندن باز می‌شود" if name == "am" else "🌆 نیویورک باز می‌شود")

def brief_msg(b, state):
    return market_summary(b, state, "📊 خلاصه‌ی بازار")

def signal_msg(b, plan, sizing, state, cfg, sample=False):
    """Clean signal card: prices in <code> for tap-to-copy."""
    s = sizing["size"]
    now = now_teh()
    full = s.get("key") == "full_unit"
    exp = now + timedelta(minutes=30)
    nw_ = b.get("news_window") or {}
    if nw_.get("next_start"):
        try:
            ns = datetime.strptime(nw_["next_start"], "%Y-%m-%d %H:%M").replace(tzinfo=TEH)
            if now < ns < exp:
                exp = ns
        except ValueError:
            pass
    try:
        close = datetime.strptime(DG.session_entry_block(now, cfg)["close_tehran"], "%Y-%m-%d %H:%M").replace(tzinfo=TEH)
        if now < close < exp:
            exp = close   # signals stop at the daily close
    except Exception:
        pass
    g = sizing.get("gate") or {}
    icon, word = ("🟢", "خرید") if plan["side"] == "BUY" else ("🔴", "فروش")
    sub = ("نمونه · " if sample else "") + f"سفارش محدود · اعتبار تا {exp:%H:%M}"
    L = [f"**{icon} {word} طلا**", f"~~{sub}~~", "",
         f"▸ ورود    `{p1(plan['entry'])}`",
         f"▸ حد ضرر  `{p1(plan['sl'])}`",
         f"▸ هدف     `{p1(plan['tp'])}`"]  # DaryaGold cannot partial-close: single target only
    rr = g.get("net_rr") if g.get("net_rr") is not None else s["net_rr"]
    L += ["", f"{'یک واحد' if full else 'نیم واحد'} · ریسک {toman_short(s['risk_toman'])} تومان · نسبت {float(rr):.1f}"]
    L += [f"⚠️ {w}" for w in g.get("warnings_fa") or []]
    L += friday_flag()
    return "\n".join(L)

def sample_signal(b, cfg, state):
    bid = float(b["price_bid"])
    side = "SELL" if b.get("bias") == "bearish" else "BUY"
    sgn = -1 if side == "SELL" else 1
    entry = round(bid - sgn * 0.5, 2); sl = round(entry - sgn * 1.6, 2); tp = round(entry + sgn * 4.0, 2)
    sz = DG.size_trade(entry, sl, tp, side, cfg, spread_usd=0.25)
    if not sz.get("ok") or float(sz["size"]["net_rr"]) < 1.5:
        return None
    return signal_msg(b, {"side": side, "entry": entry, "sl": sl, "tp": tp}, sz, state, cfg, sample=True)

# ---------------- shadow log (silent; research only, never changes a live gate) ----------------
shadow_bars = SH.m1_bars          # hooks (mocked in tests)
shadow_candidate = SH.candidate

def shadow_step(state, b, cfg, news_ok, now, record=True, session=None, valid=None):
    """Resolve open shadow entries from later candles, then (if this run was blocked only by a gate)
    record the setup that would otherwise have been a signal. Never sends anything."""
    sh = list(state.get("shadow") or [])
    live = [e for e in sh if e.get("status") in ("pending", "open")]
    if live:
        try:
            since = min(SH._ts(e["at"]) for e in live)
            try:
                close_at = datetime.strptime(DG.session_entry_block(now, cfg)["close_tehran"], "%Y-%m-%d %H:%M").replace(tzinfo=TEH)
            except Exception:
                close_at = None
            SH.resolve(sh, shadow_bars(since), now, close_at)
        except Exception as e:
            print("shadow resolve skipped:", type(e).__name__, str(e)[:120])
    gates = SH.gates_active(b) if record and not b.get("error") else []
    dec = b.get("decision")
    side = dec.get("decision") if isinstance(dec, dict) else dec
    tag = {"session": session} if session else {}
    if valid and not SH.has_open(sh):
        # Asia: a setup that passed every live check is logged instead of sent (log-only window)
        plan, sizing = valid
        e = dict(SH.new_entry(now, plan, sizing, ["asia"], DG.offset_usd(cfg) or 0.0), **tag)
        sh.append(e)
        print(f"shadow: recorded {e['side']} {e['entry']} sl {e['sl']} tp {e['tp']} (valid setup, {session} log-only)")
    elif gates and side not in ("BUY", "SELL") and not SH.has_open(sh):
        try:
            cdec, plan, sizing = shadow_candidate(cfg)
        except Exception as e:
            print("shadow candidate failed:", type(e).__name__, str(e)[:120])
            cdec = plan = sizing = None
        if cdec and cdec.get("decision") in ("BUY", "SELL") and plan and plan.get("tp") is not None:
            cf = dict(b, decision=cdec, plan=plan, sizing=sizing, news_window={}, spread={},
                      session_entry={"blocked": False})
            ok, _, _, why = risk_check(cf, state, cfg, news_ok)
            if ok:
                e = dict(SH.new_entry(now, plan, sizing, gates, DG.offset_usd(cfg) or 0.0), **tag)
                sh.append(e)
                print(f"shadow: recorded {e['side']} {e['entry']} sl {e['sl']} tp {e['tp']} gates={gates}")
            else:
                print("shadow: candidate fails non-gate checks:", " | ".join(why)[:200])
        else:
            print(f"shadow: gates={gates}, but no setup without them")
    state["shadow"] = sh[-SH.KEEP:]

# ---------------- weekend / Friday close ----------------
def weekend_closed(t, cfg):
    """DaryaGold closed (00:30-07:00 Tehran, Saturday, Sunday): commands get the closed line, no analysis."""
    return not DG.market_open(t, cfg)

def reopen_at(t, cfg):
    x = t.replace(second=0, microsecond=0) + timedelta(minutes=(-t.minute) % 5)
    for _ in range(4 * 288):
        if DG.forex_open(x, cfg):
            break
        x += timedelta(minutes=5)
    return x.astimezone(TEH)

def closed_line(t, cfg):
    r = reopen_at(t, cfg)
    return f"🔒 بازار بسته است؛ بازگشایی {FA_WEEKDAY[r.weekday()]} {r:%H:%M}"

def friday_reminder(t, cfg):
    """Close reminder text while the Friday entry cutoff is active (22:30-00:30 Tehran), else None."""
    try:
        se = DG.session_entry_block(t, cfg)
    except Exception:
        return None
    if not (se.get("friday_window") and se.get("market_open")):
        return None
    close = datetime.strptime(se["close_tehran"], "%Y-%m-%d %H:%M").replace(tzinfo=TEH)
    return f"**🏳️ جمعه: ورود جدید بسته است**\n~~همه‌ی معامله‌ها و سفارش‌ها را تا {close:%H:%M} ببندید~~"

def close_reminder(t, cfg):
    """Daily close reminder (last 30 min before 00:30). Only a message; nothing is ever closed automatically."""
    try:
        return DG.close_reminder(t, cfg)
    except Exception:
        return None

def in_asia(t):
    return t.weekday() < 5 and ASIA[0] <= t.strftime("%H:%M") < ASIA[1]

# ---------------- main ----------------
def in_window(name, t):
    a, z = PRESESSION[name]
    return a <= t.strftime("%H:%M") <= z

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["scheduled", "command", "test"], default="scheduled")
    a = ap.parse_args()
    global CFG
    cfg = CFG = DG.load_config()
    state = load_state()
    apply_offset(state, cfg)
    # /scan, /brief and /levels are queued by the Edge Function; every other command is answered there.
    pending = [x for x in state.get("pending_cmds") or [] if x.get("cmd") in ("/scan", "/brief", "/levels")]
    cmds = [(x["cmd"], []) for x in pending]
    state["done_cmds"] = [x["id"] for x in state.get("pending_cmds") or []]
    print(f"mode={a.mode} commands={[c for c, _ in cmds]}")
    news_ok = None
    brief = None
    def get_brief():
        nonlocal brief, news_ok
        if brief is None:
            news_ok = prepare_news(state)
            brief = run_brief(state)
            dec = brief.get("decision")
            state["last_verdict"] = dec.get("decision") if isinstance(dec, dict) else dec
            if brief.get("price_bid") is not None and not brief.get("error"):   # for the /trade sanity check
                state["last_price"] = {"bid": round(float(brief["price_bid"]), 2), "at": now_teh().strftime("%Y-%m-%d %H:%M")}
            if brief.get("levels"):
                state["levels"] = brief["levels"]
            elif not brief.get("error") and brief.get("price_bid") is not None:
                # tests / older briefs may omit the snapshot; never invent a second computation
                pass
        return brief

    def emit_signal(b, plan, sizing, on_request=False):
        """Send a signal at most once (dedup key), and record it so the 1-position lock applies."""
        t = now_teh()
        key = f"{t:%Y-%m-%d}|{plan['side']}|{round(plan['entry'] * 2) / 2}|{round(plan['sl'] * 2) / 2}"
        if key in [x["key"] for x in state["signals_sent"]] and not on_request:
            print("signal already sent:", key)
            return False
        ok = send_public("signal", signal_msg(b, plan, sizing, state, cfg), state)
        if ok and key not in [x["key"] for x in state["signals_sent"]]:
            state["signals_sent"].append({"key": key, "at": t.strftime("%Y-%m-%d %H:%M")})
        return ok

    closed = weekend_closed(now_teh(), cfg)
    for c, _ in cmds:
        if c == "/levels":
            # Weekend: never re-analyse. Serve the last stored snapshot (with its age) or the closed line.
            if closed:
                snap = state.get("levels")
                send(levels_card({"levels": snap}, state) if snap else closed_line(now_teh(), cfg), also=channel_chat(state))
            else:
                send(levels_card(get_brief(), state), also=channel_chat(state))
        elif closed:   # queued just before the close: never analyse stale weekend data
            send(closed_line(now_teh(), cfg), also=channel_chat(state))
        elif c == "/brief":
            b = get_brief()
            send_public("brief", brief_msg(b, state), state)
        elif c == "/scan":
            b = get_brief()
            ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
            if ok:
                emit_signal(b, plan, sizing, on_request=True)
            else:
                send_public("scan", short_brief(b, state, cfg, reasons=why), state)

    t = now_teh()
    if a.mode == "test":
        b = get_brief()
        ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
        smp = sample_signal(b, cfg, state)
        if smp:
            send(smp)
    elif a.mode == "scheduled" and DG.forex_open(t, cfg) and friday_reminder(t, cfg):
        # Friday after the entry cutoff: one short close reminder, no analysis, no signal
        tag = f"{t:%Y-%m-%d}"
        if state.get("friday_reminder_sent") not in (tag, (t - timedelta(days=1)).strftime("%Y-%m-%d")):
            if send(friday_reminder(t, cfg)):
                state["friday_reminder_sent"] = tag
    elif a.mode == "scheduled" and DG.forex_open(t, cfg) and close_reminder(t, cfg):
        # last 30 min before the 00:30 close: one reminder per session, no analysis, no signal
        tag = f"close:{(t - timedelta(hours=7)):%Y-%m-%d}"
        if state.get("friday_reminder_sent") != tag:
            if send(close_reminder(t, cfg)):
                state["friday_reminder_sent"] = tag
    elif a.mode == "scheduled" and DG.forex_open(t, cfg) and in_asia(t):
        # Asia: log-only. Shadow setups are recorded and resolved; nothing is ever sent.
        b = get_brief()
        ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
        print("asia log-only:", "valid setup (not sent)" if ok else " | ".join(why)[:300])
        shadow_step(state, b, cfg, news_ok, t, record=not ok, session="asia", valid=(plan, sizing) if ok else None)
    elif a.mode == "scheduled" and DG.forex_open(t, cfg):
        b = get_brief()
        ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
        if ok:
            emit_signal(b, plan, sizing)
        else:
            print("no signal:", " | ".join(why)[:300])
        shadow_step(state, b, cfg, news_ok, t, record=not ok)
        if t.weekday() < 5:
            for name in PRESESSION:
                tag = f"{t:%Y-%m-%d}-{name}"
                if in_window(name, t) and not state["presession_sent"].get(tag):
                    if send_public("presession", presession_brief(b, state, name), state):
                        state["presession_sent"][tag] = True
    state["last_run_tehran"] = t.strftime("%Y-%m-%d %H:%M")
    save_state(state)

if __name__ == "__main__":
    main()
