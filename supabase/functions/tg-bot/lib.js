// Shared bot logic for the Supabase Edge Function (Deno) - pure functions, no I/O except tg()/dispatch().
// Telegram formatting is a port of bot/bot.py (Persian digits, RLM, card style, Latin tap-to-copy prices).
// Signal-only research tool. Never places trades.

export const CHAT_ID = "45639251";
const REPO = "haspou367cdp/m5-gold-team";
const WORKFLOW = "telegram-bot.yml";
export const OIDC_ISS = "https://token.actions.githubusercontent.com";
export const OIDC_AUD = "m5-gold-bot";
const DEFAULT_EQUITY = 2085600;
export const BOT_KEYS = ["signals_sent", "presession_sent", "last_run_tehran", "last_verdict", "news_fetched_at", "shadow",
  "last_price", "friday_reminder_sent"];
export const DEFAULT_OFFSET = 0.3;   // DaryaGold ≈ Dukascopy bid + dg_offset (bot_state.state.dg_offset, set by /offset)
const RATE = { 1: 80000, 0.5: 40000 }, FEE = 14000;

// ---------------- time (Tehran = UTC+3:30, no DST since 2022) ----------------
export function teh(d = new Date()) {
  const t = new Date(d.getTime() + 210 * 60000);
  const p = (n) => String(n).padStart(2, "0");
  const date = `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())}`;
  const hm = `${p(t.getUTCHours())}:${p(t.getUTCMinutes())}`;
  return { date, hm, full: `${date} ${hm}`, dow: t.getUTCDay() };
}

// ---------------- forex hours (DaryaGold = forex, DST via New York; tools/broker_daryagold.json session) ----------------
// Open Sunday 17:00 NY (exactly like forex), close Friday 17:00 NY, weekday daily break 17:00-18:00 NY.
const NY_FMT = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const WD = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
function nyClock(d) {
  const p = Object.fromEntries(NY_FMT.formatToParts(d).map((x) => [x.type, x.value]));
  return { wd: WD[p.weekday], min: Number(p.hour) * 60 + Number(p.minute) };
}
export function forexOpen(d = new Date()) {
  const { wd, min } = nyClock(d);
  if (wd === 6) return false;
  if (wd === 0) return min >= 17 * 60;
  if (wd === 5) return min < 17 * 60;
  return !(min >= 17 * 60 && min < 18 * 60);
}
// weekend closure (Friday after the close, Saturday, Sunday before the open, New York time), not the daily break
export const weekendClosed = (d = new Date()) => !forexOpen(d) && [5, 6, 0].includes(nyClock(d).wd);
export function reopenAt(d = new Date()) {
  let t = new Date(Math.ceil(d.getTime() / 300000) * 300000);
  for (let i = 0; i < 4 * 288 && !forexOpen(t); i++) t = new Date(t.getTime() + 300000);
  return t;
}
const FA_WD = ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه"];
export function closedLine(d = new Date()) {
  const r = teh(reopenAt(d));
  return `🔒 بازار بسته است؛ بازگشایی ${FA_WD[r.dow]} ${faNum(r.hm)}`;   // Persian digits, as Telegram shows them
}

// ---------------- formatting (port of bot/bot.py) ----------------
const FA = "۰۱۲۳۴۵۶۷۸۹";
export function faNum(t) {
  t = t.replace(/(?<=\d),(?=\d{3})/g, "٬");
  return t.replace(/(?<![A-Za-z\d.])\d+(?:\.\d+)?/g, (m) => m.replace(".", "٫").replace(/\d/g, (c) => FA[+c]));
}
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
export function render(t) {
  t = esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/~~(.+?)~~/g, "<i>$1</i>");
  const parts = t.split(/`(.+?)`/);
  t = parts.map((x, i) => (i % 2 ? (x.startsWith("/") ? `\u200e<code>${x}</code>\u200e` : `<code>${x}</code>`) : faNum(x))).join("");
  return t.split("\n").map((l) => (l.trim() ? "\u200f" + l : l)).join("\n");
}
export function toman(n) {
  const v = Math.round(Number(n));
  return (v < 0 ? "−" : "") + Math.abs(v).toLocaleString("en-US").replace(/,/g, "٬");
}
export function tomanShort(v) {
  v = Number(v || 0);
  if (v >= 1e6) return (v / 1e6).toFixed(2).replace(/0+$/, "").replace(/\.$/, "") + " میلیون";
  if (v >= 1e3) return Math.round(v / 1e3) + " هزار";
  return String(Math.round(v));
}
const DIGIN = { "۰": 0, "۱": 1, "۲": 2, "۳": 3, "۴": 4, "۵": 5, "۶": 6, "۷": 7, "۸": 8, "۹": 9,
  "٠": 0, "١": 1, "٢": 2, "٣": 3, "٤": 4, "٥": 5, "٦": 6, "٧": 7, "٨": 8, "٩": 9, "٫": "." };
export function parseAmount(args) {
  let t = args.join(" ").replace(/[۰-۹٠-٩٫]/g, (c) => String(DIGIN[c]));
  t = t.replace(/(تومان|toman|tmn)/gi, "").replace(/[\s,٬_']/g, "");
  if (!/^\d+(\.\d+)?$/.test(t)) throw new Error("bad amount");
  const v = parseFloat(t);
  if (!(v > 0 && v < 1e12)) throw new Error("bad amount");
  return v;
}

export const HELP = `**🤖 راهنما**
~~بات طلای دریاگلد~~

**بازار**
\`/scan\`  بررسی سیگنال
\`/brief\`  خلاصه‌ی بازار
\`/shadow\`  سیگنال‌های ردشده

**حساب**
\`/status\`  وضعیت حساب و سیستم
\`/trade sell 3914.07 3909.61 1\`  ثبت معامله
\`/balance 2085600\`  ثبت موجودی
\`/loss 150000\`  ثبت ضرر
\`/win 200000\`  ثبت سود
\`/undo\`  حذف آخرین ثبت
\`/offset\`  اختلاف قیمت دریاگلد

~~بررسی خودکار بی‌صداست، مگر سیگنال باشد · خلاصه‌ی بازار ۱۱:۱۵ و ۱۶:۱۵~~`;
// Telegram menu (setMyCommands): short, same wording as /help, no examples
export const COMMANDS = [["scan", "بررسی سیگنال"], ["brief", "خلاصه‌ی بازار"], ["shadow", "سیگنال‌های ردشده"],
  ["status", "وضعیت حساب و سیستم"], ["trade", "ثبت معامله"], ["balance", "ثبت موجودی"], ["loss", "ثبت ضرر"], ["win", "ثبت سود"], ["undo", "حذف آخرین ثبت"], ["offset", "اختلاف قیمت دریاگلد"], ["help", "راهنما"]]
  .map(([command, description]) => ({ command, description }));
export const ANNOUNCE = "**✅ بات از این به بعد فوری جواب می‌دهد.**\n~~راهنما:~~ `/help`";

// ---------------- state ----------------
export function normalize(s, now = teh()) {
  s = s && typeof s === "object" ? s : {};
  if (!(Number(s.equity_toman) > 0)) s.equity_toman = DEFAULT_EQUITY;
  s.presession_sent = s.presession_sent || {};
  s.signals_sent = (s.signals_sent || []).slice(-20);
  s.pending_cmds = s.pending_cmds || [];
  if (!s.day || s.day.date !== now.date)
    s.day = { date: now.date, losses: 0, loss_toman: 0, wins: 0, win_toman: 0, records: [] };
  s.day.records = s.day.records || [];
  if (!(Number(s.day.start_equity) > 0)) s.day.start_equity = s.equity_toman;   // daily-stop base (20%)
  s.trades = (s.trades || []).slice(-300);
  for (const k of Object.keys(s.presession_sent)) if (k < now.date) delete s.presession_sent[k];
  return s;
}
function newsOk(s, now = new Date()) {
  if (!s.news_fetched_at) return false;
  const t = Date.parse(s.news_fetched_at.replace(" ", "T") + ":00+03:30");
  return (now - t) / 3.6e6 < 30;
}
export function statusMsg(s) {
  const d = s.day, sig = s.signals_sent[s.signals_sent.length - 1];
  return ["**📋 وضعیت**", `~~آخرین بررسی ${(s.last_run_tehran || "—").slice(-5)}~~`, "",
    `💼 موجودی ${tomanShort(s.equity_toman)} تومان`,
    `📉 امروز ${d.losses || 0} ضرر · ${d.wins || 0} سود`,
    `🎯 آخرین سیگنال: ${sig ? sig.at.slice(-5) : "هنوز نه"}`,
    `📰 تقویم خبری: ${newsOk(s) ? "به‌روز ✅" : "قدیمی ⛔"}`,
    "⏱ بررسی خودکار دوشنبه تا جمعه، ۱۱:۱۵ تا ۲۱:۳۰"].join("\n");
}
export const dayCap = (s) => (Number(s.day.start_equity) || Number(s.equity_toman)) * 0.2;
const signed = (v) => (v > 0 ? "+" : "") + toman(v);
const digits = (t) => String(t).replace(/[۰-۹٠-٩٫]/g, (c) => String(DIGIN[c]));
// /trade <buy|sell> <entry> <exit> <units 1|0.5>; Persian digits and words accepted
export function parseTrade(args) {
  if (args.length !== 4) throw new Error("bad trade");
  const sd = args[0].toLowerCase();
  const dir = ["buy", "b", "long", "خرید"].includes(sd) ? 1 : ["sell", "s", "short", "فروش"].includes(sd) ? -1 : 0;
  const num = (x) => { const t = digits(x).replace(/[,٬]/g, ""); if (!/^\d+(\.\d+)?$/.test(t)) throw new Error("bad"); return parseFloat(t); };
  const entry = num(args[1]), exit = num(args[2]);
  const u = digits(args[3]).toLowerCase();
  const units = ["1", "1.0", "full", "یک", "کامل"].includes(u) ? 1 : ["0.5", ".5", "½", "half", "نیم"].includes(u) ? 0.5 : 0;
  if (!dir || !units || !(entry > 1000 && entry < 10000 && exit > 1000 && exit < 10000) || Math.abs(exit - entry) > 300)
    throw new Error("bad trade");
  const gross = Math.round((exit - entry) * dir * RATE[units]);
  return { side: dir > 0 ? "buy" : "sell", entry, exit, units, gross, net: gross - FEE, fee: FEE };
}
// /trade sanity check: warn (the trade is still recorded) when the input looks wrong
export const offsetOf = (s) => (Number.isFinite(Number(s.dg_offset)) && s.dg_offset !== null && s.dg_offset !== "" ? Number(s.dg_offset) : DEFAULT_OFFSET);
export function marketPrice(s, at = new Date()) {   // DaryaGold price from the last analysis run, if < 24 h old
  const lp = s.last_price;
  if (!lp || !Number(lp.bid) || !lp.at) return null;
  const t = Date.parse(String(lp.at).replace(" ", "T") + ":00+03:30");
  if (!(at - t < 24 * 3.6e6)) return null;
  return Math.round((Number(lp.bid) + offsetOf(s)) * 100) / 100;
}
export function tradeWarn(t, s, at = new Date()) {
  const w = [];
  if (t.exit === t.entry) w.push("ورود و خروج یکی است");
  if (Math.abs(t.exit - t.entry) > 40) w.push("حرکت قیمت بیش از ۴۰ دلار است");
  const m = marketPrice(s, at);
  if (m && (Math.abs(t.entry - m) > 50 || Math.abs(t.exit - m) > 50)) w.push("قیمت‌ها بیش از ۵۰ دلار با بازار فاصله دارند");
  return w.length ? `⚠️ ${w.join("؛ ")}؛ اگر اشتباه است \`/undo\`` : null;
}
const BAD_TRADE = "**⚠️ معامله ثبت نشد**\n~~جهت، ورود، خروج و حجم (۱ یا ۰٫۵) را بنویسید، مثل:~~\n\n`/trade sell 3914.07 3909.61 1`\n`/trade buy 3894.11 3898.99 0.5`";
const GATE_FA = { news: "خبر", volatility: "نوسان", spread: "اسپرد", friday: "جمعه", session: "ساعت", asia: "آسیا" };
const RES_FA = { tp: "هدف", sl: "حد ضرر", expired: "پایان مهلت", unfilled: "پر نشد", pending: "در انتظار", open: "باز" };
export function shadowMsg(s) {
  const e = (s.shadow || []);
  if (!e.length) return "**🕶 سیگنال‌های ردشده**\n~~هنوز موردی ثبت نشده~~";
  const n = (k) => e.filter((x) => x.status === k).length;
  const done = e.filter((x) => ["tp", "sl", "expired"].includes(x.status));
  const R = done.reduce((a, x) => a + Number(x.R || 0), 0), T = done.reduce((a, x) => a + Number(x.toman || 0), 0);
  const px = (v, off) => (Number(v) + Number(off ?? 0.3)).toFixed(2).replace(/\.?0+$/, "");
  const last = e.slice(-3).reverse().map((x) => `${x.at.slice(5, 10).replace("-", "/")} ${x.at.slice(-5)} ${x.side === "BUY" ? "خرید" : "فروش"} \`${px(x.entry, x.offset)}\` · ${(x.gates || []).map((g) => GATE_FA[g] || g).join("، ")} · ${RES_FA[x.status] || x.status}` +
    (["tp", "sl", "expired"].includes(x.status) ? ` ${Number(x.R) > 0 ? "+" : ""}${Number(x.R).toFixed(1)}R` : ""));
  const asia = done.filter((x) => x.session === "asia"), aR = asia.reduce((a, x) => a + Number(x.R || 0), 0);
  const aAll = e.filter((x) => x.session === "asia").length;
  return ["**🕶 سیگنال‌های ردشده**", "~~ستاپ‌هایی که فقط فیلتر جلویشان را گرفت~~", "",
    `بسته‌شده ${done.length} · هدف ${n("tp")} · حد ضرر ${n("sl")} · پایان مهلت ${n("expired")}`,
    `پر نشد ${n("unfilled")} · باز ${n("pending") + n("open")}`,
    ...(done.length ? [`جمع ${R > 0 ? "+" : ""}${R.toFixed(1)}R · یک واحد ${signed(T)} تومان`] : []),
    aAll ? `آسیا: بسته‌شده ${asia.length} · هدف ${asia.filter((x) => x.status === "tp").length} · حد ضرر ${asia.filter((x) => x.status === "sl").length}` +
      (asia.length ? ` · جمع ${aR > 0 ? "+" : ""}${aR.toFixed(1)}R` : "") : "آسیا: هنوز موردی ثبت نشده",
    "", "**آخرین‌ها**", ...last].join("\n");
}
const BAD = "**⚠️ چیزی ثبت نشد**\n~~مبلغ را به تومان بنویسید، مثل:~~\n\n`/loss 150000`\n`/win 200000`\n`/balance 2085600`";

// Pure command handler: mutates state, returns {reply, queue?}.
export function handle(s, text, now = teh(), at = new Date()) {
  const parts = text.trim().split(/\s+/);
  const c = parts[0].split("@")[0].toLowerCase(), args = parts.slice(1);
  const d = s.day;
  if (c === "/start" || c === "/help") return { reply: HELP };
  if (c === "/status") return { reply: statusMsg(s) };
  if (c === "/scan" || c === "/brief") return weekendClosed(at) ? { reply: closedLine(at) } : { queue: c };
  if (c === "/offset") {
    const cur = offsetOf(s);
    if (!args.length)
      return { reply: `**🎚 اختلاف قیمت دریاگلد**\n~~قیمت دریاگلد = قیمت مرجع + ${cur} دلار~~\n\nبرای تغییر: \`/offset 0.4\`` };
    const t = digits(args.join("")).replace(/[−–]/g, "-");
    const v = /^[-+]?\d+(\.\d+)?$/.test(t) ? Math.round(parseFloat(t) * 100) / 100 : NaN;
    if (!(Math.abs(v) <= 5)) return { reply: "**⚠️ ثبت نشد**\n~~عددی بین منفی ۵ و ۵ دلار بنویسید، مثل:~~ `/offset 0.4`" };
    s.dg_offset = v;
    s.dg_offset_at = now.full;
    return { reply: `**🎚 اختلاف قیمت ثبت شد**\n~~از ${cur} به ${v} دلار؛ از بررسی بعدی اعمال می‌شود~~` };
  }
  if (c === "/shadow") return { reply: shadowMsg(s) };
  if (c === "/trade") {
    let t;
    try { t = parseTrade(args); } catch (e) { return { reply: BAD_TRADE }; }
    const warn = tradeWarn(t, s, at);
    const n = s.trades.filter((x) => x.date === now.date).length + 1;
    const eqBefore = Number(s.equity_toman);
    const tr = { id: `${now.date}-T${n}-${t.side.toUpperCase()}`, date: now.date, at: now.hm, ...t, ...(warn ? { warned: true } : {}),
      equity_before: eqBefore, equity_after: eqBefore + t.net };
    s.equity_toman = tr.equity_after;
    s.trades.push(tr);
    const loss = t.net < 0;
    d.records.push({ type: loss ? "loss" : "win", toman: Math.abs(t.net), at: now.hm, trade: tr.id, net: t.net });
    if (loss) { d.losses += 1; d.loss_toman += -t.net; } else { d.wins += 1; d.win_toman += t.net; }
    const net = d.loss_toman - d.win_toman;
    const stop = d.losses >= 3 || net >= dayCap(s);
    return { reply: [loss ? "**📉 معامله ثبت شد**" : "**📈 معامله ثبت شد**",
      `~~${t.side === "buy" ? "خرید" : "فروش"} · ${t.units === 1 ? "یک واحد" : "نیم واحد"}~~`, "",
      `ورود \`${t.entry}\` · خروج \`${t.exit}\``,
      `نتیجه‌ی خالص ${signed(t.net)} تومان`,
      `موجودی جدید ${toman(s.equity_toman)} تومان`, "",
      `امروز ${d.losses} ضرر · ${d.wins} سود`,
      ...(stop ? ["", "⛔ توقف روزانه فعال شد؛ تا فردا سیگنالی فرستاده نمی‌شود"] : []),
      ...(warn ? ["", warn] : [])].join("\n") };
  }
  try {
    if (c === "/balance") {
      const v = parseAmount(args);
      s.equity_toman = v;
      if (!d.records.length) d.start_equity = v;   // nothing recorded yet today: this is the day's starting equity
      return { reply: `**💼 موجودی ثبت شد**\n~~${toman(v)} تومان~~\n\nریسک هر معامله تا ${tomanShort(v * 0.1)} تومان\nسقف ضرر روزانه ${tomanShort(dayCap(s))} تومان` };
    }
    if (c === "/loss" || c === "/win") {
      const v = parseAmount(args);
      d.records.push({ type: c.slice(1), toman: v, at: now.hm });
      if (c === "/loss") { d.losses += 1; d.loss_toman += v; } else { d.wins += 1; d.win_toman += v; }
      const net = d.loss_toman - d.win_toman;
      const stop = d.losses >= 3 || net >= dayCap(s);
      return { reply: [c === "/loss" ? "**📉 ضرر ثبت شد**" : "**📈 سود ثبت شد**", `~~${toman(v)} تومان~~`, "",
        `امروز ${d.losses} ضرر · ${d.wins} سود`,
        net > 0 ? `ضرر خالص امروز ${tomanShort(net)} تومان` : `سود خالص امروز ${tomanShort(-net)} تومان`,
        ...(stop ? ["", "⛔ توقف روزانه فعال شد؛ تا فردا سیگنالی فرستاده نمی‌شود"] : [])].join("\n") };
    }
  } catch (e) { return { reply: BAD }; }
  if (c === "/undo") {
    const r = d.records.pop();
    if (!r) return { reply: "**↩️ چیزی برای حذف نیست**\n~~امروز سود یا ضرری ثبت نشده~~" };
    if (r.type === "loss") { d.losses = Math.max(0, d.losses - 1); d.loss_toman = Math.max(0, d.loss_toman - r.toman); }
    else { d.wins = Math.max(0, d.wins - 1); d.win_toman = Math.max(0, d.win_toman - r.toman); }
    if (r.trade) {
      const i = s.trades.findIndex((x) => x.id === r.trade);
      const tr = i >= 0 ? s.trades.splice(i, 1)[0] : null;
      s.equity_toman = Number(s.equity_toman) - Number(r.net);
      return { reply: [`**↩️ آخرین معامله حذف شد**`,
        `~~${tr ? (tr.side === "buy" ? "خرید" : "فروش") + " · " : ""}${signed(r.net)} تومان~~`, "",
        `موجودی ${toman(s.equity_toman)} تومان`, `امروز ${d.losses} ضرر · ${d.wins} سود`].join("\n") };
    }
    return { reply: `**↩️ آخرین ثبت حذف شد**\n~~${r.type === "loss" ? "ضرر" : "سود"} ${toman(r.toman)} تومان~~\n\nامروز ${d.losses} ضرر · ${d.wins} سود` };
  }
  return { reply: "**❔ دستور ناشناخته**\n~~راهنما:~~ `/help`" };
}

// ---------------- telegram + github ----------------
export async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return r.json().catch(() => ({ ok: false }));
}
export async function send(env, text) {
  const html = render(text);
  let r = await tg(env, "sendMessage", { chat_id: CHAT_ID, text: html, parse_mode: "HTML", disable_web_page_preview: true });
  if (!r.ok) {  // never lose a message over formatting
    const plain = html.replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
    r = await tg(env, "sendMessage", { chat_id: CHAT_ID, text: plain, disable_web_page_preview: true });
  }
  return !!r.ok;
}
export async function dispatch(env, mode) {
  if (!env.GH_DISPATCH_TOKEN) return { ok: false, why: "no GH_DISPATCH_TOKEN" };
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST", body: JSON.stringify({ ref: "main", inputs: { mode } }),
    headers: { authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, accept: "application/vnd.github+json",
      "user-agent": "m5-gold-bot", "x-github-api-version": "2022-11-28" } });
  return { ok: r.status === 204, why: r.status === 204 ? "" : `github ${r.status}` };
}

// ---------------- GitHub OIDC (no shared secret between GitHub and Supabase) ----------------
let JWKS = null, JWKS_AT = 0;
const b64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
export async function verifyOidc(req, fetchJwks) {
  const m = (req.headers.get("authorization") || "").match(/^Bearer\s+(.+)$/i);
  if (!m) return null;
  const [h, p, sig] = m[1].split(".");
  if (!sig) return null;
  let head, claims;
  try { head = JSON.parse(new TextDecoder().decode(b64u(h))); claims = JSON.parse(new TextDecoder().decode(b64u(p))); }
  catch { return null; }   // garbage token -> 401, not 500
  if (head.alg !== "RS256") return null;
  if (!JWKS || Date.now() - JWKS_AT > 3.6e6 || !JWKS.keys.some((k) => k.kid === head.kid)) {
    JWKS = await (fetchJwks ? fetchJwks() : fetch(`${OIDC_ISS}/.well-known/jwks`).then((r) => r.json())); JWKS_AT = Date.now();
  }
  const jwk = JWKS.keys.find((k) => k.kid === head.kid);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64u(sig), new TextEncoder().encode(`${h}.${p}`));
  const now = Date.now() / 1000;
  if (!ok || claims.iss !== OIDC_ISS || claims.aud !== OIDC_AUD || claims.repository !== REPO ||
      claims.ref !== "refs/heads/main" || !(claims.exp > now) || (claims.nbf && claims.nbf > now + 60)) return null;
  return claims;
}

