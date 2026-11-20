// Shared bot logic for the Supabase Edge Function (Deno) - pure functions, no I/O except tg()/dispatch().
// Telegram formatting is a port of bot/bot.py (Persian digits, RLM, card style, Latin tap-to-copy prices).
// Signal-only research tool. Never places trades.
import { plainLabel, trendSummary } from "./assist.js";

export const CHAT_ID = "45639251";
const REPO = "haspou367cdp/m5-gold-team";
const WORKFLOW = "telegram-bot.yml";
export const OIDC_ISS = "https://token.actions.githubusercontent.com";
export const OIDC_AUD = "m5-gold-bot";
const DEFAULT_EQUITY = 2085600;
export const BOT_KEYS = ["signals_sent", "presession_sent", "last_run_tehran", "last_verdict", "news_fetched_at", "shadow",
  "last_price", "friday_reminder_sent", "levels"];
export const DEFAULT_OFFSET = 0.02;  // ONE basis (owner t244u): DaryaGold = Dukascopy mid + dg_offset (bot_state.state.dg_offset, /offset, /calibrate)

// ---------------- time (Tehran = UTC+3:30, no DST since 2022) ----------------
export function teh(d = new Date()) {
  const t = new Date(d.getTime() + 210 * 60000);
  const p = (n) => String(n).padStart(2, "0");
  const date = `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())}`;
  const hm = `${p(t.getUTCHours())}:${p(t.getUTCMinutes())}`;
  return { date, hm, full: `${date} ${hm}`, dow: t.getUTCDay() };
}

// ---------------- DaryaGold hours (owner 2026-11-20; tools/broker_daryagold.json session) ----------------
// Mon-Fri 07:00 to 00:30 (next day) Tehran; Saturday and Sunday closed. Tehran is UTC+3:30 with no DST.
const OPEN_MIN = 7 * 60, CLOSE_MIN = 30;
export function forexOpen(d = new Date()) {   // name kept for app.js; means "DaryaGold open"
  const { hm, dow } = teh(d);
  const min = Number(hm.slice(0, 2)) * 60 + Number(hm.slice(3, 5));
  if (min >= OPEN_MIN) return dow >= 1 && dow <= 5;          // session opened today (Mon-Fri)
  if (min < CLOSE_MIN) return dow >= 2 && dow <= 6;          // tail of yesterday's session (Tue-Sat 00:00-00:30)
  return false;
}
// trading-day key: the date the session opened (00:00-00:30 and the closed night belong to the previous day)
export function sessionDate(now = teh()) {
  if (now.hm >= "07:00") return now.date;
  const d = new Date(Date.parse(now.date + "T00:00:00Z") - 86400000);
  return d.toISOString().slice(0, 10);
}
// any closure (nightly 00:30-07:00 and the weekend): /brief and /setup get the closed line
export const weekendClosed = (d = new Date()) => !forexOpen(d);
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

import { parseCalibrate } from "./calib.js";
import { midOffsetOf, rebaseSnap, levelOffset, trendHead } from "./assist.js";
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

// Owner decision t226u-t232u (2026-11-20): the bot is an assistant. No automatic entry signals, no trade journal.
// t238u (2026-11-20): the old journal/signal commands are removed entirely (unknown command reply).
export const BOT_NAME = "Z A R V A •|• BTV", GROUP_NAME = "• Z A R V A •";   // display names (owner t244u/t246u); ids unchanged
export const HELP = `**🤖 راهنما**
~~${BOT_NAME} · دستیار طلای دریاگلد~~

**بازار**
\`/setup\`  نقشه‌ی ورود: خرید یا فروش، حد ضرر و سود
\`/e sell 3531.80\`  حد ضرر و سود برای قیمت ورود
\`/trend\`  جهت بازار در هر بازه‌ی زمانی
\`/levels\`  سقف‌ها و کف‌های مهم قیمت
\`/brief\`  خلاصه‌ی بازار همین الان

**هشدارهای خودکار**
~~رسیدن به سطح · تغییر روند ۱۵ دقیقه و ۱ ساعت · خبر مهم · نوسان خیلی زیاد یا خیلی کم · بسته‌شدن دریاگلد~~

**تنظیمات**
\`/status\`  وضعیت بات
\`/balance 2085600\`  ثبت موجودی حساب
\`/offset\`  اختلاف قیمت دریاگلد با قیمت مرجع
\`/calibrate 3569.85\`  تنظیم اختلاف با قیمت دریاگلد
\`/groupoff\`  قطع موقت ارسال به گروه
\`/groupon\`  وصل دوباره‌ی ارسال به گروه

~~خلاصه‌ی بازار ساعت‌های ۷، ۱۱:۱۵ و ۱۶:۱۵ · در گروه: /setup، /trend، /levels و /brief~~`;
// Telegram menus (setMyCommands): short, same wording as /help, no examples.
// Owner's private chat: the full list. Groups (and everyone else): the four read-only commands members may run.
const MENU = [["setup", "نقشه‌ی ورود: خرید یا فروش، حد ضرر و سود"], ["e", "حد ضرر و سود برای قیمت ورود"], ["trend", "جهت بازار در هر بازه‌ی زمانی"],
  ["levels", "سقف‌ها و کف‌های مهم قیمت"], ["brief", "خلاصه‌ی بازار همین الان"], ["status", "وضعیت بات"], ["balance", "ثبت موجودی حساب"],
  ["offset", "اختلاف قیمت دریاگلد با قیمت مرجع"], ["calibrate", "تنظیم اختلاف با قیمت دریاگلد"], ["groupoff", "قطع موقت ارسال به گروه"],
  ["groupon", "وصل دوباره‌ی ارسال به گروه"], ["help", "راهنمای دستورها"]];
export const COMMANDS = MENU.map(([command, description]) => ({ command, description }));
export const DESCRIPTION = `${BOT_NAME}، دستیار طلای گروه ${GROUP_NAME}.\nسقف‌ها و کف‌های مهم، روند، نقشه‌ی ورود و هشدارهای طلا (XAUUSD) برای دریاگلد، به زبان ساده.\nدستورها: /setup /trend /levels /brief`;
export const SHORT_DESCRIPTION = `دستیار طلای گروه ${GROUP_NAME}: سطح‌ها، روند و نقشه‌ی ورود به زبان ساده`;
export const GROUP_MENU = COMMANDS.filter((c) => ["setup", "trend", "levels", "brief"].includes(c.command));
export const MENU_VERSION = "2026-11-21-t246u";
// Telegram calls that make the menus exactly this (narrow scopes first are cleared, then set)
export function menuCalls() {
  return [
    ["deleteMyCommands", { scope: { type: "all_private_chats" } }],
    ["deleteMyCommands", { language_code: "fa" }],
    ["setMyCommands", { commands: GROUP_MENU }],                                            // default scope
    ["setMyCommands", { commands: GROUP_MENU, scope: { type: "all_group_chats" } }],
    ["setMyCommands", { commands: COMMANDS, scope: { type: "chat", chat_id: Number(CHAT_ID) } }],   // owner
    ...["", "fa"].flatMap((lc) => [   // profile texts (the display name itself is set by the owner in BotFather)
      ["setMyDescription", { description: DESCRIPTION, ...(lc ? { language_code: lc } : {}) }],
      ["setMyShortDescription", { short_description: SHORT_DESCRIPTION, ...(lc ? { language_code: lc } : {}) }]]),
  ];
}
export const ASSIST_CMDS = { "/setup": "setup", "/signal": "setup", "/scan": "setup", "/trend": "trend", "/e": "e" };
export const ANNOUNCE = "**✅ بات از این به بعد فوری جواب می‌دهد.**\n~~راهنما:~~ `/help`";

// ---------------- state ----------------
export function normalize(s, now = teh()) {
  s = s && typeof s === "object" ? s : {};
  if (!(Number(s.equity_toman) > 0)) s.equity_toman = DEFAULT_EQUITY;
  s.presession_sent = s.presession_sent || {};
  s.signals_sent = (s.signals_sent || []).slice(-20);
  s.pending_cmds = s.pending_cmds || [];
  const tday = sessionDate(now);   // daily stop runs on the DaryaGold trading day (07:00-00:30 Tehran)
  if (!s.day || s.day.date !== tday)
    s.day = { date: tday, losses: 0, loss_toman: 0, wins: 0, win_toman: 0, records: [] };
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
  return ["**📋 وضعیت**", `~~آخرین بررسی ${(s.last_run_tehran || "—").slice(-5)}~~`, "",
    `💼 موجودی ${tomanShort(s.equity_toman)} تومان`,
    "🎯 سیگنال خودکار: خاموش · ستاپ با `/setup`",
    `📰 تقویم خبری: ${newsOk(s) ? "به‌روز ✅" : "قدیمی ⛔"}`,
    `📤 ارسال به گروه: ${groupEnabled(s) ? "وصل" : "قطع"}`,
    "⏱ بررسی خودکار دوشنبه تا جمعه، `07:00` تا `00:30`"].join("\n");
}
const digits = (t) => String(t).replace(/[۰-۹٠-٩٫]/g, (c) => String(DIGIN[c]));
export const offsetOf = (s) => midOffsetOf(s);


// ---------------- shared levels snapshot (computed in Python; never recomputed here) ----------------
const FRESH_MIN = 15;
const FA_MONTH = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
  "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
function jalali(gy, gm, gd) {
  const gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days = 355666 + 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100)
    + Math.floor((gy2 + 399) / 400) + gd + gdm[gm - 1];
  let jy = -1595 + 33 * Math.floor(days / 12053); days %= 12053;
  jy += 4 * Math.floor(days / 1461); days %= 1461;
  if (days > 365) { jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
  const jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
  const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
  return [jy, jm, jd];
}
export function faDate(d = new Date()) {
  const n = teh(d);
  const [y, m, day] = n.date.split("-").map(Number);
  const [, jm, jd] = jalali(y, m, day);
  return `${FA_WD[n.dow]} ${jd} ${FA_MONTH[jm - 1]}`;
}
export function levelsAgeMin(snap, at = new Date()) {
  if (!snap || !snap.computed_at_tehran) return null;
  const t = Date.parse(String(snap.computed_at_tehran).slice(0, 19).replace(" ", "T") + "+03:30");
  if (!Number.isFinite(t)) return null;
  return (at - t) / 60000;
}
export function levelsFresh(snap, at = new Date(), limit = FRESH_MIN) {
  const a = levelsAgeMin(snap, at);
  return a != null && a >= 0 && a <= limit;
}
export function levelsMsg(snap, at = new Date()) {
  const n = teh(at);
  const lines = ["**📏 سطوح مهم قیمت**", `~~${faDate(at)} · ${n.hm} به وقت تهران~~`, ""];
  const short = (snap && snap.short) || null;
  const rows = short ? [...(short.above || []), ...(short.below || [])] : [];
  if (!rows.length) {   // old snapshot without the structured fields: the stored block as it is
    if (snap && !levelsFresh(snap, at)) {
      const age = levelsAgeMin(snap, at);
      if (age != null && age >= 0) lines.push(`به‌روزشده ${Math.round(age)} دقیقه پیش`, "");
    }
    lines.push(snap && snap.block ? snap.block : "داده‌ی سطوح در دسترس نیست");
    return lines.join("\n");
  }
  // Phone ladder (owner t246u): levels above (far -> near), the current price, levels below (near -> far).
  const P = Number(snap.price_dg);
  if (!levelsFresh(snap, at)) {
    const age = levelsAgeMin(snap, at);
    if (age != null && age >= 0) lines.push(`~~این عددها مربوط به ${Math.round(age)} دقیقه پیش است.~~`);
  }
  const tr = snap.trend || {};
  if (tr.H4 || tr.H1) lines.push(trendHead(Object.fromEntries(["M5", "M15", "H1", "H4"].map((tf) => [tf, (tr[tf] || {}).trend || "خنثی"]))));
  const row = (r, up) => {
    const d = Math.abs(Number(r.price_dg) - P);
    const lab = plainLabel({ kinds: r.kinds || [], price: Number(r.price_dg), label: r.label_fa || "" });
    return [`${up ? "🔺" : "🔻"} \`${Number(r.price_dg).toFixed(1)}\` · ${String(Math.round(d * 10) / 10)} دلار ${up ? "بالاتر" : "پایین‌تر"}`,
      ...(lab ? [`~~      ${lab}~~`] : [])];
  };
  const above = [...(short.above || [])].sort((a, b) => Number(b.price_dg) - Number(a.price_dg));
  const below = [...(short.below || [])].sort((a, b) => Number(b.price_dg) - Number(a.price_dg));
  lines.push("", "**⬆️ بالای قیمت**");
  lines.push(...(above.length ? above.flatMap((r) => row(r, true)) : ["—"]));
  lines.push("", Number.isFinite(P) ? `**💰 قیمت الان: \`${P.toFixed(1)}\`**` : "**💰 قیمت الان: —**", "");
  lines.push("**⬇️ زیر قیمت**");
  lines.push(...(below.length ? below.flatMap((r) => row(r, false)) : ["—"]));
  lines.push("", "~~سطح = قیمتی که بازار قبلاً آنجا ایستاده یا برگشته؛ نزدیک سطح‌ها قیمت ممکن است بایستد یا برگردد.~~");
  const atr = Number(snap.atr_m5);
  if (atr > 0) lines.push(`~~قیمت معمولاً در هر ۵ دقیقه حدود ${String(Math.round(atr * 10) / 10)} دلار بالا و پایین می‌رود.~~`);
  return lines.join("\n");
}

// Pure command handler: mutates state, returns {reply, queue?}.
export function handle(s, text, now = teh(), at = new Date()) {
  const parts = text.trim().split(/\s+/);
  const c = parts[0].split("@")[0].toLowerCase(), args = parts.slice(1);
  if (c === "/start" || c === "/help") return { reply: HELP };
  if (ASSIST_CMDS[c]) return { assist: { kind: ASSIST_CMDS[c], args } };
  if (c === "/status") return { reply: statusMsg(s) };
  if (c === "/brief") return weekendClosed(at) ? { reply: closedLine(at) } : { queue: c };
  if (c === "/levels") {
    if (weekendClosed(at))
      return { reply: (s.levels && s.levels.block) ? levelsMsg(rebaseSnap(s.levels, levelOffset(s)), at) : closedLine(at) };
    if (levelsFresh(s.levels, at)) return { reply: levelsMsg(rebaseSnap(s.levels, levelOffset(s)), at) };
    return { queue: c };
  }
  if (c === "/calibrate") {   // private chat only (onTelegram drops groups); never mirrored
    if (!args.length) return { calibrate: { show: true } };
    try { return { calibrate: parseCalibrate(args) }; }
    catch { return { reply: "**⚠️ ثبت نشد**\n~~قیمت دریاگلد را با نقطه بنویسید، مثل:~~ `/calibrate 3569.85`" }; }
  }
  if (c === "/offset") {   // ONE basis (owner t244u): DaryaGold = Dukascopy mid + offset, for levels, live price, /e, /setup, alerts
    const cur = offsetOf(s);
    const a2 = args.length === 2 && args[0].toLowerCase() === "live" ? args.slice(1) : args;   // old «/offset live x» = same
    if (!a2.length)
      return { reply: `**🎚 اختلاف قیمت دریاگلد**\n~~قیمت دریاگلد = میانه‌ی Dukascopy + ${cur} دلار (برای سطح‌ها، قیمت زنده، ستاپ‌ها و هشدارها)~~\n\nبرای تغییر: \`/offset 0.05\`` };
    const t = digits(a2.join("")).replace(/[−–]/g, "-");
    const v = /^[-+]?\d+(\.\d+)?$/.test(t) ? Math.round(parseFloat(t) * 100) / 100 : NaN;
    if (!(Math.abs(v) <= 5)) return { reply: "**⚠️ ثبت نشد**\n~~عددی بین منفی ۵ و ۵ دلار بنویسید، مثل:~~ `/offset 0.05`" };
    s.dg_offset = v;
    s.dg_offset_at = now.full;
    s.dg_offset_source = "manual";
    return { reply: `**🎚 اختلاف قیمت ثبت شد**\n~~از ${cur} به ${v} دلار؛ همین الان برای همه‌ی دستورها اعمال می‌شود~~` };
  }
  if (c === "/groupoff") { s.group_enabled = false; return { reply: "**⏸ ارسال به گروه موقتاً قطع شد.**" }; }
  if (c === "/groupon") { s.group_enabled = true; return { reply: "**▶️ ارسال به گروه دوباره وصل شد.**" }; }
  if (c === "/balance") {
    let v;
    try { v = parseAmount(args); } catch { return { reply: "**⚠️ ثبت نشد**\n~~موجودی را به تومان بنویسید، مثل:~~ `/balance 2085600`" }; }
    s.equity_toman = v;
    return { reply: `**💼 موجودی ثبت شد**\n~~${toman(v)} تومان~~` };
  }
  return { reply: "**❔ دستور ناشناخته**\n~~راهنما:~~ `/help`" };
}

// ---------------- telegram + github ----------------
export async function tg(env, method, body) {
  // Bounded: a hung Bot API backend must not hold the function until its 150 s wall-clock limit (HTTP 546).
  try {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      signal: AbortSignal.timeout(20000) });
    return await r.json().catch(() => ({ ok: false }));
  } catch (e) {
    return { ok: false, description: `telegram ${method}: ${e && e.name || "error"}` };
  }
}
export function groupEnabled(s) {
  return !s || s.group_enabled !== false;   // missing flag => sending is on
}
export function channelChat(s) {
  if (!groupEnabled(s)) return "";
  const id = s && s.channel_id != null && s.channel_id !== "" ? String(s.channel_id).trim() : "";
  return id && id !== String(CHAT_ID) ? id : "";
}
// Group copy of a mirrored card. Drops personal toman/balance and error cards; otherwise the same text.
export const MIRROR_CMDS = ["/levels", "/brief"];
// Group: members may run /setup, /trend, /levels, /brief (t189u, t231u/t232u); /signal and /scan are hidden aliases of /setup. Group-safe replies.
export const GROUP_CMDS = { "/setup": "/setup", "/signal": "/setup", "/scan": "/setup", "/trend": "/trend", "/levels": "/levels", "/brief": "/brief" };
export const GROUP_COOLDOWN_MS = 60000;
export function publicReply(cmd, text) {
  if (!text) return null;
  if (text.includes("داده‌ی قیمت در دسترس نیست")) return null;
  return text;
}
export async function send(env, text, chatId = CHAT_ID, markup = null) {
  const html = render(text);
  const km = markup ? { reply_markup: markup } : {};
  let r = await tg(env, "sendMessage", { chat_id: chatId, text: html, parse_mode: "HTML", disable_web_page_preview: true, ...km });
  if (!r || !r.ok) {  // never lose a message over formatting
    const plain = html.replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
    r = await tg(env, "sendMessage", { chat_id: chatId, text: plain, disable_web_page_preview: true, ...km });
  }
  return !!(r && r.ok);
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

