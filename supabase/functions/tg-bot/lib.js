// Shared bot logic for the Supabase Edge Function (Deno) - pure functions, no I/O except tg()/dispatch().
// Telegram formatting is a port of bot/bot.py (Persian digits, RLM, card style, Latin tap-to-copy prices).
// Signal-only research tool. Never places trades.

export const CHAT_ID = "45639251";
const REPO = "haspou367cdp/m5-gold-team";
const WORKFLOW = "telegram-bot.yml";
export const OIDC_ISS = "https://token.actions.githubusercontent.com";
export const OIDC_AUD = "m5-gold-bot";
const DEFAULT_EQUITY = 2085600;
export const BOT_KEYS = ["signals_sent", "presession_sent", "last_run_tehran", "last_verdict", "news_fetched_at"];

// ---------------- time (Tehran = UTC+3:30, no DST since 2022) ----------------
export function teh(d = new Date()) {
  const t = new Date(d.getTime() + 210 * 60000);
  const p = (n) => String(n).padStart(2, "0");
  const date = `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())}`;
  const hm = `${p(t.getUTCHours())}:${p(t.getUTCMinutes())}`;
  return { date, hm, full: `${date} ${hm}`, dow: t.getUTCDay() };
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
\`/scan\`  بررسی بازار و سیگنال
\`/brief\`  خلاصه‌ی بازار

**حساب**
\`/status\`  وضعیت حساب و سیستم
\`/balance 2085600\`  ثبت موجودی
\`/loss 150000\`  ثبت ضرر
\`/win 200000\`  ثبت سود
\`/undo\`  حذف آخرین ثبت

~~بررسی خودکار بی‌صداست، مگر سیگنال باشد · خلاصه‌ی بازار ۱۱:۱۵ و ۱۶:۱۵~~`;
// Telegram menu (setMyCommands): short, same wording as /help, no examples
export const COMMANDS = [["scan", "بررسی بازار و سیگنال"], ["brief", "خلاصه‌ی بازار"], ["status", "وضعیت حساب و سیستم"],
  ["balance", "ثبت موجودی"], ["loss", "ثبت ضرر"], ["win", "ثبت سود"], ["undo", "حذف آخرین ثبت"], ["help", "راهنما"]]
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
const BAD = "**⚠️ چیزی ثبت نشد**\n~~مبلغ را به تومان بنویسید، مثل:~~\n\n`/loss 150000`\n`/win 200000`\n`/balance 2085600`";

// Pure command handler: mutates state, returns {reply, queue?}.
export function handle(s, text, now = teh()) {
  const parts = text.trim().split(/\s+/);
  const c = parts[0].split("@")[0].toLowerCase(), args = parts.slice(1);
  const d = s.day;
  if (c === "/start" || c === "/help") return { reply: HELP };
  if (c === "/status") return { reply: statusMsg(s) };
  if (c === "/scan" || c === "/brief") return { queue: c };
  try {
    if (c === "/balance") {
      const v = parseAmount(args);
      s.equity_toman = v;
      return { reply: `**💼 موجودی ثبت شد**\n~~${toman(v)} تومان~~\n\nریسک هر معامله تا ${tomanShort(v * 0.1)} تومان\nسقف ضرر روزانه ${tomanShort(v * 0.2)} تومان` };
    }
    if (c === "/loss" || c === "/win") {
      const v = parseAmount(args);
      d.records.push({ type: c.slice(1), toman: v, at: now.hm });
      if (c === "/loss") { d.losses += 1; d.loss_toman += v; } else { d.wins += 1; d.win_toman += v; }
      const net = d.loss_toman - d.win_toman;
      const stop = d.losses >= 3 || net >= s.equity_toman * 0.2;
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

