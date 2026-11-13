#!/usr/bin/env python3
"""bot.py - Telegram front-end for the M5 gold toolkit, run by GitHub Actions (no server).

Each run: read Telegram commands (getUpdates), optionally refresh the news calendar, run tools/brief.py,
apply the automated DaryaGold risk check (replaces M5-Risk), send a message only when needed, save state.

modes : scheduled  - full check; sends a signal only if every gate passes (deduped); pre-session briefs
        poll       - answer commands only; runs the brief only if /scan or /brief was asked
        test       - send 'سیستم راه‌اندازی شد' + current verdict
env   : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (only this chat is answered), STATE_DIR (state.json + news_windows.json)
Signal-only research. Never places trades. Not financial advice."""
import argparse, csv, json, os, subprocess, sys, time, urllib.parse, urllib.request
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
WARN = ("⚠️ سطوح و جهت تأییدنشده‌اند و هیچ مزیت آماری ندارند (هر دو موتور در آزمون خارج از نمونه رد شدند). "
        "اول روی حساب دمو امتحان کنید.\nاین تحلیل است، نه توصیه‌ی مالی")
HELP = """🤖 راهنمای بات طلا (XAUUSD M5، دریاگلد)

/scan — بررسی کامل؛ اگر ستاپی از همه‌ی گیت‌ها رد شود سیگنال، وگرنه «معامله نکنید» با دلیل
/brief — فقط تحلیل کوتاه
/balance 2085600 — به‌روزرسانی موجودی حساب (تومان)
/loss 150000 — ثبت یک معامله‌ی بسته‌شده با ضرر امروز (برای توقف روزانه)
/win 200000 — ثبت یک معامله‌ی بسته‌شده با سود امروز
/status — وضعیت سیستم
/help — همین راهنما

⏱ این بات سرور همیشه‌روشن ندارد و روی GitHub Actions اجرا می‌شود. دستورها فقط در اجرای بعدی جواب داده می‌شوند:
• دوشنبه تا جمعه حدود ۱۱:۳۰ تا ۲۱:۳۰ تهران هر ۱۵ دقیقه (گاهی چند دقیقه دیرتر)
• ۲۱:۳۰ تا ۰۰:۳۰ تهران هر ساعت فقط برای جواب دستورها
• شب‌ها و آخر هفته جوابی نمی‌آید.
سیگنال خودکار فقط وقتی فرستاده می‌شود که همه‌ی گیت‌ها رد شوند. بریف‌های پیش از سشن حدود ۱۱:۱۵ و ۱۶:۱۵.
سفارش را خودتان در دریاگلد ثبت کنید؛ بات به حساب شما دسترسی ندارد."""

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
        s["day"] = {"date": today, "losses": 0, "loss_toman": 0, "wins": 0, "win_toman": 0}
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
    ok = True
    while text:
        part, text = text[:3900], text[3900:]
        r = tg("sendMessage", chat_id=CHAT, text=part, disable_web_page_preview="true")
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
        reasons += dec.get("reasons_reject") or [((b.get("quality") or {}).get("fa")) or "ستاپ تأییدشده‌ای نیست."]
        return False, None, None, reasons
    eq = float(state["equity_toman"])
    q = b.get("quality") or {}
    if not q.get("ok") or (q.get("age_minutes") or 0) > 10:
        reasons.append("داده‌ی قیمت تازه نیست (حد ۱۰ دقیقه).")
    if b.get("fallback"):
        reasons.append("قیمت از منبع جایگزین (فیوچرز) است، نه اسپات؛ سیگنال داده نمی‌شود.")
    if not news_ok:
        reasons.append("تقویم خبری به‌روز در دسترس نیست؛ بدون آن سیگنال داده نمی‌شود.")
    nwin = b.get("news_window") or {}
    if nwin.get("inside") and nwin.get("action") == "block":
        reasons.append("داخل پنجره‌ی خبری ورود ممنوع.")
    if nwin.get("soon_block"):
        reasons.append("پنجره‌ی خبری ورود ممنوع خیلی نزدیک است.")
    if (b.get("session_entry") or {}).get("blocked"):
        reasons.append((b["session_entry"].get("reason_fa")) or "ساعت ورود مجاز نیست.")
    d = state["day"]
    cap_loss = eq * float(cfg.get("daily_loss_pct_max", 20)) / 100
    if int(d.get("losses") or 0) >= int(cfg.get("max_consecutive_losses", 3)):
        reasons.append(f"توقف روزانه: {d['losses']} ضرر امروز.")
    if float(d.get("loss_toman") or 0) - float(d.get("win_toman") or 0) >= cap_loss:
        reasons.append(f"توقف روزانه: ضرر خالص امروز به {DG.toman(cap_loss)} تومان (۲۰٪) رسید.")
    if not plan or not sizing or not sizing.get("ok") or not sizing.get("size"):
        reasons.append("حجم مجاز (نیم یا یک واحد) در سقف ریسک پیدا نشد.")
    else:
        s = sizing["size"]
        if s.get("key") not in ("half_unit", "full_unit"):
            reasons.append("حجم فقط نیم یا یک واحد مجاز است.")
        if plan.get("tp") is None:
            reasons.append("حد سود ساختاری ندارد.")
        if float(s.get("risk_toman") or 1e18) > eq * float(cfg.get("risk_per_trade_pct_max", 10)) / 100 + 1:
            reasons.append("ریسک بیش از ۱۰٪ حساب است.")
        if float(s.get("net_rr") or 0) < float(cfg.get("min_net_rr", 1.5)):
            reasons.append(f"نسبت خالص سود به ریسک {s.get('net_rr')} کمتر از ۱٫۵ است.")
        if abs(float(plan["entry"]) - float(plan["sl"])) + 1e-9 < float(cfg.get("min_sl_usd", 1.0)):
            reasons.append("حد ضرر کمتر از ۱ دلار است.")
        if float(s.get("fee") or 0) < 14000:
            reasons.append("کارمزد کمتر از ۱۴٬۰۰۰ تومان حساب شده؛ ناسازگار با قرارداد.")
        if float(s.get("margin") or 0) > eq:
            reasons.append("وجه تضمین بیش از موجودی است.")
    return (not reasons), plan, sizing, reasons

# ---------------- messages ----------------
def strip_md(s):
    return (s or "").replace("**", "").replace("_", "")

def head(b):
    return b.get("evaluated_at_tehran") or b.get("generated_at_tehran") or now_teh().strftime("%Y-%m-%d %H:%M")

def news_line(b):
    w = b.get("news_windows_next_24h") or []
    return ("📰 پنجره‌های خبری ۲۴ ساعت آینده (تهران): " + "، ".join(w[:6])) if w else "📰 پنجره‌ی خبری مهمی در ۲۴ ساعت آینده ثبت نشده."

def short_brief(b, state, cfg, reasons=None, title="📊 بریف طلا (XAUUSD M5)"):
    px = lambda p: DG.fmt_px(p, cfg)
    if b.get("error") or b.get("price_bid") is None:
        q = (b.get("quality") or {}).get("fa") or "داده در دسترس نیست."
        return f"{title} · {head(b)} تهران\nتصمیم: معامله نکنید (NO TRADE)\nعلت: {q}\n\n{WARN}"
    fa = {"bullish": "صعودی", "bearish": "نزولی", "neutral": "خنثی"}
    dec = b.get("decision") if isinstance(b.get("decision"), dict) else {"decision": b.get("decision")}
    eq = float(state["equity_toman"])
    L = [f"{title} · {head(b)} تهران",
         f"تصمیم: {'معامله نکنید (NO TRADE)' if not reasons is None or dec.get('decision') not in ('BUY','SELL') else dec.get('decision')}"]
    rs = reasons if reasons else (dec.get("reasons_reject") or [])
    if rs:
        L.append("علت: " + " ".join(strip_md(r) for r in rs[:3]))
    L.append(f"قیمت دریاگلد: {px(b['price_bid'])} · کیفیت داده: {(b.get('quality') or {}).get('fa', '?')}")
    L.append(f"جهت: {fa.get(b.get('bias'), '?')} (H4 {fa.get((b.get('h4') or {}).get('trend'), '?')}، "
             f"H1 {fa.get((b.get('h1') or {}).get('trend'), '?')}، M15 {fa.get((b.get('m15') or {}).get('trend'), '?')})")
    inv = b.get("invalidation") or {}
    if inv.get("neutral_level"):
        word = "بالای" if b.get("bias") == "bearish" or (b.get("bias") == "neutral" and b.get("technical_bias") == "bearish") else "زیر"
        L.append(f"ابطال: بسته شدن M15 {word} {px(inv['neutral_level'])} → خنثی"
                 + (f"؛ H1 {word} {px(inv['off_level'])} → باطل" if inv.get("off_level") else ""))
    if b.get("resistances"):
        L.append("مقاومت‌ها: " + "، ".join(px(l["price"]) for l in b["resistances"][:3]))
    if b.get("supports"):
        L.append("حمایت‌ها: " + "، ".join(px(l["price"]) for l in b["supports"][:3]))
    L.append(news_line(b))
    d = state["day"]
    L.append(f"💰 موجودی {DG.toman(eq)} تومان · سقف ریسک هر معامله {DG.toman(eq * 0.10)} تومان · "
             f"توقف روزانه {DG.toman(eq * 0.20)} تومان یا ۳ ضرر · امروز {d.get('losses', 0)} ضرر")
    if now_teh().weekday() == 4:
        L.append("📅 جمعه: از ۲۳:۳۰ تهران ورود جدید ممنوع و همه‌چیز پیش از ۰۱:۳۰ بسته.")
    L.append("")
    L.append(WARN)
    return "\n".join(L)

def signal_msg(b, plan, sizing, state, cfg):
    px = lambda p: DG.fmt_px(p, cfg)
    dec = b["decision"]
    s = sizing["size"]
    eq = float(state["equity_toman"])
    side_fa = "خرید 🟢" if plan["side"] == "BUY" else "فروش 🔴"
    L = [f"🚨 سیگنال {side_fa} طلا (XAUUSD M5) · {head(b)} تهران",
         "از چک خودکار ریسک رد شد (۱۰٪ سقف، R:R خالص ≥ ۱٫۵، کارمزد ۱۴٬۰۰۰، خبر، جمعه، تازگی داده).",
         f"موتور: {dec.get('engine_fa', '?')} (تأییدنشده)",
         f"ورود (اوردر): {px(plan['entry'])}",
         f"حد ضرر: {px(plan['sl'])} (فاصله {abs(plan['entry'] - plan['sl']):.2f} دلار)",
         f"حد سود: {px(plan['tp'])} (فاصله {abs(plan['tp'] - plan['entry']):.2f} دلار)",
         f"حجم: {s['label_fa']} · ریسک {DG.toman(s['risk_toman'])} تومان ({DG.pct_of(s['risk_toman'], eq)}٪) · "
         f"پاداش {DG.toman(s['reward_toman'])} تومان ({DG.pct_of(s['reward_toman'], eq)}٪) · نسبت خالص {s['net_rr']} · "
         f"کارمزد {DG.toman(s['fee'])} · وجه تضمین {DG.toman(s['margin'])} تومان"]
    if dec.get("reasons_accept"):
        L.append("علت: " + " ".join(strip_md(r) for r in dec["reasons_accept"][:3]))
    nw_ = b.get("news_window") or {}
    if nw_.get("next_start"):
        L.append(f"⏰ پنجره‌ی خبری بعدی {nw_['next_start'][-5:]}–{nw_.get('next_end', '')} (سطح {nw_.get('next_tier')}): "
                 "پیش از شروعش اوردر را لغو و معامله را ببندید.")
    L.append("حداقل نگهداری ۶۰ ثانیه · فقط یک پوزیشن هم‌زمان · اگر ستاپ قبل از پر شدن باطل شد، اوردر را لغو کنید.")
    L.append("")
    L.append(WARN)
    return "\n".join(L)

def status_msg(state, news_ok):
    d = state["day"]
    sig = state["signals_sent"][-1] if state["signals_sent"] else None
    return "\n".join([
        "ℹ️ وضعیت سیستم",
        f"موجودی: {DG.toman(state['equity_toman'])} تومان",
        f"امروز ({d['date']}): {d.get('losses', 0)} ضرر ({DG.toman(d.get('loss_toman', 0))} تومان)، "
        f"{d.get('wins', 0)} سود ({DG.toman(d.get('win_toman', 0))} تومان)",
        f"آخرین اجرا: {state.get('last_run_tehran', '—')} تهران · آخرین حکم: {state.get('last_verdict', '—')}",
        f"آخرین سیگنال: {sig['at'] + ' ' + sig['key'] if sig else 'هیچ'}",
        f"تقویم خبری (ForexFactory): {state.get('news_fetched_at', '—')} {'✅' if news_ok else '⛔ کهنه'}",
        "اجرا: دوشنبه تا جمعه ۱۱:۳۰–۲۱:۳۰ تهران هر ۱۵ دقیقه؛ ۲۱:۳۰–۰۰:۳۰ ساعتی فقط برای دستورها.",
    ])

# ---------------- main ----------------
def in_window(name, t):
    a, z = PRESESSION[name]
    return a <= t.strftime("%H:%M") <= z

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["scheduled", "poll", "test"], default="scheduled")
    a = ap.parse_args()
    cfg = DG.load_config()
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
                send(f"✅ موجودی ثبت شد: {DG.toman(v)} تومان · سقف ریسک هر معامله {DG.toman(v * 0.1)} تومان · توقف روزانه {DG.toman(v * 0.2)} تومان.")
            elif c in ("/loss", "/win"):
                v = abs(float(args[0].replace(",", "").replace("٬", "")))  # amount required (bare tap = no-op)
                d = state["day"]
                if c == "/loss":
                    d["losses"] += 1; d["loss_toman"] += v
                else:
                    d["wins"] += 1; d["win_toman"] += v
                net = d["loss_toman"] - d["win_toman"]
                stop = d["losses"] >= 3 or net >= state["equity_toman"] * 0.2
                send(f"✅ ثبت شد. امروز {d['losses']} ضرر و {d['wins']} سود؛ ضرر خالص {DG.toman(max(net, 0))} تومان."
                     + ("\n⛔ توقف روزانه فعال است؛ تا روز معاملاتی بعد سیگنالی داده نمی‌شود." if stop else ""))
        except (ValueError, IndexError):
            send("⚠️ عدد لازم است. مثال: /balance 2085600 · /loss 150000 · /win 200000 (چیزی ثبت نشد)")

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
                 short_brief(b, state, cfg, reasons=why, title="🔎 اسکن طلا: معامله نکنید"))

    t = now_teh()
    if a.mode == "test":
        b = get_brief()
        ok, plan, sizing, why = risk_check(b, state, cfg, news_ok)
        send("✅ سیستم راه‌اندازی شد. بات طلا روی GitHub Actions فعال است. برای راهنما /help بفرستید.")
        send(signal_msg(b, plan, sizing, state, cfg) if ok else short_brief(b, state, cfg, reasons=why, title="📊 حکم فعلی"))
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
                    title = "🌅 بریف پیش از سشن لندن" if name == "am" else "🗽 بریف پیش از سشن نیویورک"
                    if send(short_brief(b, state, cfg, reasons=None if ok else why, title=title)):
                        state["presession_sent"][tag] = True
    state["last_run_tehran"] = t.strftime("%Y-%m-%d %H:%M")
    save_state(state)

if __name__ == "__main__":
    main()
