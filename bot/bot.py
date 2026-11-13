#!/usr/bin/env python3
"""bot.py - Telegram front-end for the M5 gold toolkit, run by GitHub Actions (no server).

Each run: read Telegram commands (getUpdates), optionally refresh the news calendar, run tools/brief.py,
apply the automated DaryaGold risk check (replaces M5-Risk), send a message only when needed, save state.

modes : scheduled  - full check; sends a signal only if every gate passes (deduped); pre-session briefs
        poll       - answer commands only; runs the brief only if /scan or /brief was asked
        test       - send 'سیستم راه‌اندازی شد' + current verdict
env   : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (only this chat is answered), STATE_DIR (state.json + news_windows.json)
Signal-only research. Never places trades. Not financial advice."""
import argparse, csv, html, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta

ROOT = "/workspace/m5-gold-team"
sys.path.insert(0, f"{ROOT}/tools")
from zoneinfo import ZoneInfo
TEH = ZoneInfo("Asia/Tehran")
import broker_daryagold as DG

STATE_DIR = os.environ.get("STATE_DIR", f"{ROOT}/state")
STATE_JSON = f"{STATE_DIR}/state.json"
STATE_NEWS = f"{STATE_DIR}/news_windows.json"
DATA_NEWS = f"{ROOT}/data/news_windows.json"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
NEWS_REFRESH_H = 3
NEWS_MAX_AGE_H = 30          # older calendar => no signals (fail closed)
PRESESSION = {"am": ("11:10", "11:44"), "pm": ("16:10", "16:44")}
HELP = """**🤖 راهنما**
~~بات طلای دریاگلد~~

/scan  بررسی بازار و سیگنال
/brief  وضعیت بازار
/balance 2085600  ثبت موجودی
/loss 150000  ثبت زیان امروز
/win 200000  ثبت سود امروز
/undo  حذف آخرین ثبت
/status  وضعیت سیستم

⏱ جواب در اجرای بعدی، حداکثر حدود ۱۵ دقیقه
📅 دوشنبه تا جمعه، ۱۱:۳۰ تا ۰۰:۳۰
🔕 بررسی‌های خودکار فقط وقتی پیام می‌دهند که سیگنال باشد"""

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
    s.setdefault("tg_offset", 0)
    s.setdefault("presession_sent", {})
    s.setdefault("signals_sent", [])
    today = now_teh().strftime("%Y-%m-%d")
    if (s.get("day") or {}).get("date") != today:
        s["day"] = {"date": today, "losses": 0, "loss_toman": 0, "wins": 0, "win_toman": 0, "records": []}
    s["presession_sent"] = {k: v for k, v in s["presession_sent"].items() if k >= today}
    s["signals_sent"] = s["signals_sent"][-20:]
    return s

def save_state(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    s["updated_at_tehran"] = now_teh().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATE_JSON + ".tmp", "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(STATE_JSON + ".tmp", STATE_JSON)

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

def send(text):
    if not CHAT:
        print("[no chat id] message not sent:\n" + text)
        return False
    text = render(text)
    ok = True
    while text:
        part, text = text[:3900], text[3900:]
        r = tg("sendMessage", chat_id=CHAT, text=part, parse_mode="HTML", disable_web_page_preview="true")
        good = bool(r and r.get("ok"))
        if os.environ.get("BOT_ECHO") == "1":
            print("----- sent text -----\n" + part + "\n---------------------")
        if not good:  # never lose a message over formatting
            r = tg("sendMessage", chat_id=CHAT, text=re.sub(r"</?b>", "", html.unescape(part)), disable_web_page_preview="true")
            good = bool(r and r.get("ok"))
        print(f"telegram send: {'ok message_id=' + str(r['result']['message_id']) if good else 'FAILED ' + str((r or {}).get('description'))}")
        ok = ok and good
    return ok

def read_commands(state):
    r = tg("getUpdates", offset=int(state.get("tg_offset", 0)) + 1 if state.get("tg_offset") else 0, timeout=0)
    cmds = []
    if not r or not r.get("ok"):
        return cmds
    for u in r.get("result", []):
        state["tg_offset"] = max(int(state.get("tg_offset") or 0), int(u["update_id"]))
        m = u.get("message") or u.get("edited_message") or {}
        chat_id = str((m.get("chat") or {}).get("id", ""))
        text = (m.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        if not CHAT or chat_id != CHAT:
            print("ignored a command from an unknown chat")
            continue
        parts = text.split()
        c = (parts[0].split("@")[0].lower(), parts[1:])
        if c[0] in ("/start", "/help", "/scan", "/brief", "/status") and any(x[0] == c[0] for x in cmds):
            continue  # answer repeated read-only commands once per run
        cmds.append(c)
    return cmds

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
        p = subprocess.run([sys.executable, f"{ROOT}/tools/ff_calendar.py"], capture_output=True, text=True)
        print(p.stdout.strip(), p.stderr.strip()[-300:])
        if p.returncode == 0:
            state["news_fetched_at"] = now_teh().strftime("%Y-%m-%d %H:%M")
            age_h = 0
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(DATA_NEWS) as f, open(STATE_NEWS, "w") as g:
                g.write(f.read())
    return age_h is not None and age_h < NEWS_MAX_AGE_H

# ---------------- brief + automated risk check ----------------
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
    p = subprocess.run([sys.executable, f"{ROOT}/tools/brief.py", "--equity", str(int(state["equity_toman"]))],
                       capture_output=True, text=True)
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
    if not q.get("ok") or (q.get("age_minutes") or 0) > 10:
        reasons.append("داده‌ی قیمت تازه نیست (بیش از ۱۰ دقیقه گذشته است).")
    if b.get("fallback"):
        reasons.append("قیمت از منبع جایگزین (قرارداد آتی) آمده است، نه بازار نقدی؛ با این داده سیگنال داده نمی‌شود.")
    if not news_ok:
        reasons.append("تقویم خبری به‌روز در دسترس نیست و بدون آن سیگنال داده نمی‌شود.")
    nwin = b.get("news_window") or {}
    if nwin.get("inside") and nwin.get("action") == "block":
        reasons.append("اکنون داخل پنجره‌ی خبری هستیم و ورود ممنوع است.")
    if nwin.get("soon_block"):
        reasons.append("پنجره‌ی خبری بعدی خیلی نزدیک است و ورود جدید ممنوع است.")
    if (b.get("session_entry") or {}).get("blocked"):
        reasons.append((b["session_entry"].get("reason_fa")) or "در این ساعت ورود مجاز نیست.")
    d = state["day"]
    cap_loss = eq * float(cfg.get("daily_loss_pct_max", 20)) / 100
    if int(d.get("losses") or 0) >= int(cfg.get("max_consecutive_losses", 3)):
        reasons.append(f"توقف روزانه فعال است: امروز {d['losses']} معامله‌ی زیان‌ده ثبت شده است.")
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
        if float(s.get("net_rr") or 0) < float(cfg.get("min_net_rr", 1.5)):
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
    """DaryaGold price with the raw Dukascopy bid in brackets (LTR-safe digits)."""
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
    return _NUM.sub(lambda m: m.group(0).replace(".", "٫").translate(_FA_DIGITS), t)

def render(t):
    """**bold** -> <b>, HTML-escaped, Persian digits."""
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"~~(.+?)~~", r"<i>\1</i>", t)
    # tap-to-copy prices stay Latin ("3884.2") so they paste into DaryaGold's order box; the rest is Persian
    parts = re.split(r"`(.+?)`", t)
    t = "".join(f"<code>{x}</code>" if i % 2 else fa_num(x) for i, x in enumerate(parts))
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

WARN_LINE = ""  # owner (2026-11-13): no disclaimer/warning lines in Telegram messages

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

def friday_line():
    t = now_teh()
    if t.weekday() == 4 and t.hour >= 22:
        return ["جمعه: از ۲۳:۳۰ ورود ممنوع؛ همه‌چیز تا ۰۱:۳۰ بسته شود."]
    return []

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
    t = now_teh()
    return ["🏳️ از ۲۳:۳۰ ورود بسته است"] if (t.weekday() == 4 and t.hour >= 22) else []

def hilo(b):
    r = (b.get("resistances") or [None])[0]
    s_ = (b.get("supports") or [None])[0]
    parts = []
    if r: parts.append(f"سقف  {p1(r['price'])}")
    if s_: parts.append(f"کف  {p1(s_['price'])}")
    return ["   ·   ".join(parts)] if parts else []

def short_brief(b, state, cfg, reasons=None, title=None):
    """NO TRADE card for /scan and /brief (or a pointer to the signal if one passes)."""
    if b.get("error") or b.get("price_bid") is None:
        return "**⏸ فعلاً معامله نه**\n~~داده‌ی قیمت در دسترس نیست~~"
    dec = b.get("decision") if isinstance(b.get("decision"), dict) else {"decision": b.get("decision")}
    rs = reasons if reasons else (dec.get("reasons_reject") or [])
    bias = b.get("bias")
    L = ["**⏸ فعلاً معامله نه**", f"~~{short_reason(b, rs)}~~", "",
         f"طلا  **{p1(b['price_bid'])}**  {ARROW.get(bias, '↔️')}"]
    L += hilo(b)
    nn = next_news(b)
    reason = L[1]
    if nn and nn.split("–")[1] in reason:
        later = [a for a, z in _windows(b) if a > nn.split("–")[0]]
        nn = (later[0] + "–") if later else None
    if nn:
        L += ["", f"🔔 خبر بعدی {nn.split('–')[0]}"]
    L += friday_flag()
    return "\n".join(L)

def presession_brief(b, state, name):
    t = now_teh()
    title = "☀️ لندن باز می‌شود" if name == "am" else "🌆 نیویورک باز می‌شود"
    L = [f"**{title}**", f"~~{fa_date(t)} · {t:%H:%M}~~", ""]
    if b.get("error") or b.get("price_bid") is None:
        L.append("داده‌ی قیمت در دسترس نیست")
    else:
        bias = b.get("bias")
        L.append(f"طلا  **{p1(b['price_bid'])}**  {ARROW.get(bias, '↔️')} {FA_TREND.get(bias, '')}")
        L += hilo(b)
    today = t.strftime("%H:%M")
    wins = [(a, z) for a, z in _windows(b) if a >= today or z > today]
    wins = [w for w in wins if w[0] >= "00:00"][:4]
    L.append("")
    if wins:
        L.append("🔔 خبرهای امروز")
        L += [f" {a} تا {z}" for a, z in wins]
    else:
        L.append("🔔 امروز خبر مهمی ثبت نشده")
    eq = float(state["equity_toman"])
    L += ["", f"💼 موجودی {toman_short(eq)} · سقف ضرر امروز {toman_short(eq * 0.2)}"]
    L += friday_flag()
    return "\n".join(L)

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
    icon, word = ("🟢", "خرید") if plan["side"] == "BUY" else ("🔴", "فروش")
    sub = ("نمونه · " if sample else "") + f"سفارش محدود · اعتبار تا {exp:%H:%M}"
    L = [f"**{icon} {word} طلا**", f"~~{sub}~~", "",
         f"▸ ورود    `{p1(plan['entry'])}`",
         f"▸ حد ضرر  `{p1(plan['sl'])}`",
         f"▸ هدف     `{p1(plan['tp'])}`"]  # DaryaGold cannot partial-close: single target only
    L += ["", f"{'یک واحد' if full else 'نیم واحد'} · ریسک {toman_short(s['risk_toman'])} تومان · نسبت {float(s['net_rr']):.1f}"]
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

def status_msg(state, news_ok):
    d = state["day"]
    sig = state["signals_sent"][-1] if state["signals_sent"] else None
    last = (state.get("last_run_tehran") or "—")[-5:]
    return "\n".join([
        "**📋 وضعیت**", f"~~آخرین بررسی {last}~~", "",
        f"💼 موجودی {toman_short(state['equity_toman'])} تومان",
        f"📉 امروز {d.get('losses', 0)} زیان · {d.get('wins', 0)} سود",
        f"🎯 آخرین سیگنال: {sig['at'][-5:] if sig else 'هنوز نه'}",
        f"📰 تقویم خبری: {'به‌روز ✅' if news_ok else 'قدیمی ⛔'}",
        "⏱ بررسی هر ۱۵ دقیقه، دوشنبه تا جمعه ۱۱:۳۰ تا ۲۱:۳۰",
    ])

# ---------------- main ----------------
def in_window(name, t):
    a, z = PRESESSION[name]
    return a <= t.strftime("%H:%M") <= z

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["scheduled", "poll", "test"], default="scheduled")
    a = ap.parse_args()
    global CFG
    cfg = CFG = DG.load_config()
    state = load_state()
    cmds = read_commands(state)
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
        return brief

    # cheap commands first (balance/loss/win change what the scan computes)
    for c, args in cmds:
        try:
            if c in ("/start", "/help"):
                send(HELP)
            elif c == "/balance":
                v = float(args[0].replace(",", "").replace("٬", ""))
                if v <= 0: raise ValueError
                state["equity_toman"] = v
                send(f"✅ موجودی ثبت شد: {DG.toman(v)} تومان.\nسقف ریسک هر معامله: {DG.toman(v * 0.1)} تومان؛ توقف روزانه: {DG.toman(v * 0.2)} تومان ضرر.")
            elif c in ("/loss", "/win"):
                v = float(args[0].replace(",", "").replace("٬", ""))  # positive amount required, else nothing is recorded
                if v <= 0:
                    raise ValueError
                d = state["day"]
                d.setdefault("records", []).append({"type": c[1:], "toman": v, "at": now_teh().strftime("%H:%M")})
                if c == "/loss":
                    d["losses"] += 1; d["loss_toman"] += v
                else:
                    d["wins"] += 1; d["win_toman"] += v
                net = d["loss_toman"] - d["win_toman"]
                stop = d["losses"] >= 3 or net >= state["equity_toman"] * 0.2
                send(f"✅ ثبت شد. امروز {d['losses']} معامله‌ی زیان‌ده و {d['wins']} معامله‌ی سودده دارید؛ ضرر خالص: {DG.toman(max(net, 0))} تومان."
                     + ("\n⛔ توقف روزانه فعال شد؛ تا روز معاملاتی بعد سیگنالی فرستاده نمی‌شود." if stop else ""))
            elif c == "/undo":
                d = state["day"]
                recs = d.setdefault("records", [])
                if not recs:
                    send("چیزی برای حذف وجود ندارد؛ امروز هیچ سود یا زیانی ثبت نشده است.")
                else:
                    r = recs.pop()
                    if r["type"] == "loss":
                        d["losses"] = max(0, d["losses"] - 1); d["loss_toman"] = max(0, d["loss_toman"] - r["toman"])
                    else:
                        d["wins"] = max(0, d["wins"] - 1); d["win_toman"] = max(0, d["win_toman"] - r["toman"])
                    kind = "زیان" if r["type"] == "loss" else "سود"
                    send(f"↩️ آخرین مورد حذف شد: {kind} {DG.toman(r['toman'])} تومان. "
                         f"امروز {d['losses']} معامله‌ی زیان‌ده و {d['wins']} معامله‌ی سودده ثبت شده است.")
        except (ValueError, IndexError):
            send("⚠️ مبلغ مثبت را هم بنویسید؛ چیزی ثبت نشد.\nمثال: /balance 2085600 یا /loss 150000 یا /win 200000\nبرای حذف آخرین مورد ثبت‌شده: /undo")

    for c, _ in cmds:
        if c == "/status":
            if news_ok is None:
                news_ok = prepare_news(state)
            send(status_msg(state, news_ok))
        elif c == "/brief":
            b = get_brief()
            send(short_brief(b, state, cfg))
        elif c == "/scan":
            b = get_brief()
            ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
            send(signal_msg(b, plan, sizing, state, cfg) if ok else
                 short_brief(b, state, cfg, reasons=why))

    t = now_teh()
    if a.mode == "test":
        b = get_brief()
        ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
        smp = sample_signal(b, cfg, state)
        if smp:
            send(smp)
    elif a.mode == "scheduled" and DG.forex_open(t, cfg):
        b = get_brief()
        ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
        if ok:
            key = f"{t:%Y-%m-%d}|{plan['side']}|{round(plan['entry'] * 2) / 2}|{round(plan['sl'] * 2) / 2}"
            if key not in [x["key"] for x in state["signals_sent"]]:
                if send(signal_msg(b, plan, sizing, state, cfg)):
                    state["signals_sent"].append({"key": key, "at": t.strftime("%Y-%m-%d %H:%M")})
            else:
                print("signal already sent:", key)
        else:
            print("no signal:", " | ".join(why)[:300])
        if t.weekday() < 5:
            for name in PRESESSION:
                tag = f"{t:%Y-%m-%d}-{name}"
                if in_window(name, t) and not state["presession_sent"].get(tag):
                    if send(presession_brief(b, state, name)):
                        state["presession_sent"][tag] = True
    state["last_run_tehran"] = t.strftime("%Y-%m-%d %H:%M")
    save_state(state)

if __name__ == "__main__":
    main()
