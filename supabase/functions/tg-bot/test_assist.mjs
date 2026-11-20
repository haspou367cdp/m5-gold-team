// Offline tests for the assistant redesign (owner t226u-t232u): /setup /trend /e, group replies, /tick alerts,
// silent setup logging. Production mode (legacy off). Dukascopy, Supabase, Telegram are mocked; nothing is sent anywhere.
// usage: node supabase/functions/tg-bot/test_assist.mjs
import { makeApp } from "./app.js";
import * as A from "./assist.js";
import { render, HELP, COMMANDS, levelsMsg } from "./lib.js";
let fails = 0;
const check = (n, c) => { console.log((c ? "PASS " : "FAIL ") + n); if (!c) fails++; };
const SB = "https://x.supabase.co", GID = "-1001958445009", OWNER = "45639251";
const U = (iso) => new Date(iso);
let CLOCK = U("2026-11-18T15:00:00Z");   // Wednesday 18:30 Tehran
// ---- synthetic market: a clean downtrend with swings on every timeframe
const TFMS = { "1MIN": 60000, "5MIN": 3e5, "15MIN": 9e5, "1HOUR": 3.6e6, "4HOUR": 1.44e7 };
let MARKET = { slope: -1, base: 3530, amp: 1, flat: false };
const priceAt = (t, tf) => {
  const k = (t - CLOCK.getTime()) / tf;   // bars from now (negative = past)
  const m = MARKET;
  return m.base + m.slope * k * (tf >= 3.6e6 ? 3 : 1) + (m.flat ? 0 : m.amp * (tf / 6e4) ** 0.5 * Math.sin((2 * Math.PI * k) / 16));
};
function bars(iv, side, limit, ts) {
  const tf = TFMS[iv], end = Math.floor(ts / tf) * tf - (iv === "1MIN" ? tf : 0), out = [];
  const lastStart = iv === "1MIN" ? end : end - tf;   // native higher-TF bars: completed only
  for (let i = 0; i < limit; i++) {
    const t = lastStart - i * tf, o = priceAt(t, tf), c = priceAt(t + tf, tf), sp = side === "A" ? 0.3 : 0;
    out.push([t, o + sp, Math.max(o, c) + 0.4 + sp, Math.min(o, c) - 0.4 + sp, c + sp, 1]);
  }
  return out;   // newest first, like Dukascopy with time_direction=P
}
let FEED_DOWN = false;
// ---- Supabase mock
const LEVELS = (p) => ({ computed_at_tehran: "2026-11-18 18:25:00", adr_used_pct: 70, zone_half: 1.5, atr_m5: 4, price_dg: p,
  trend: { M5: { trend: "نزولی" }, M15: { trend: "نزولی" }, H1: { trend: "نزولی" }, H4: { trend: "نزولی" } },
  short: { above: [
    { side: "resistance", kinds: ["London low"], price_dg: p + 6.2, zone_dg: [p + 4.7, p + 7.7], label_fa: "کف لندن", strength: "strong", touches_m15_3d: 2, distance_atr: 1.5 },
    { side: "resistance", kinds: ["Round $50"], price_dg: p + 40.3, zone_dg: [p + 38.8, p + 41.8], label_fa: "رُند", strength: "medium", touches_m15_3d: 1, distance_atr: 10 }],
    below: [
    { side: "support", kinds: ["H1 swing low"], price_dg: p - 7.4, zone_dg: [p - 8.9, p - 5.9], label_fa: "سوئینگ H1", strength: "strong", touches_m15_3d: 1, distance_atr: -1.8 },
    { side: "support", kinds: ["Week low"], price_dg: p - 19.6, zone_dg: [p - 21.1, p - 18.1], label_fa: "کف هفته", strength: "weak", touches_m15_3d: 0, distance_atr: -4.9 }] } });
const TGCALLS = [];
const DB = { row: { state: { equity_toman: 5689600, channel_id: GID, levels: LEVELS(3530) }, news: { windows: [] }, version: 0 }, vault: { tg_webhook_secret: "W".repeat(64), telegram_bot_token: "1:T" } };
const SETUPS = [], SENT = [];
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json" } });
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.includes("freeserv.dukascopy.com")) {
    if (FEED_DOWN) throw new Error("network");
    const q = new URL(url).searchParams;
    return new Response("_cb(" + JSON.stringify(bars(q.get("interval"), q.get("offer_side"), Number(q.get("limit")), Number(q.get("timestamp")))) + ");");
  }
  if (url.startsWith(SB + "/rest/v1/bot_state")) return J([structuredClone(DB.row)]);
  if (url.startsWith(SB + "/rest/v1/rpc/")) {
    const fn = url.split("/").pop(), a = JSON.parse(init.body || "{}");
    if (fn === "bot_secret") return J(DB.vault[a.p_name] ?? null);
    if (fn === "bot_webhook_secret") return J(DB.vault.tg_webhook_secret);
    if (fn === "bot_save") { if (a.p_version !== DB.row.version) return J(false); DB.row.state = a.p_state; DB.row.version++; return J(true); }
  }
  if (url.startsWith(SB + "/rest/v1/setups")) {
    const m = init.method || "GET";
    if (m === "POST") { for (const r of JSON.parse(init.body)) if (!SETUPS.some((x) => x.id === r.id)) SETUPS.push({ status: "pending", ...r }); return new Response(null, { status: 201 }); }
    if (m === "PATCH") { const id = decodeURIComponent(url.split("id=eq.")[1]); Object.assign(SETUPS.find((x) => x.id === id), JSON.parse(init.body)); return new Response(null, { status: 204 }); }
    return J(structuredClone(SETUPS.filter((x) => ["pending", "filled"].includes(x.status))));
  }
  if (url.includes("api.telegram.org")) {
    const b = JSON.parse(init.body);
    if (url.endsWith("/sendMessage")) { SENT.push(b); return J({ ok: true, result: { message_id: SENT.length } }); }
    if (url.endsWith("/getMe")) return J({ ok: true, result: { username: "XauscalperBot" } });
    if (/\/(setMyCommands|deleteMyCommands|answerCallbackQuery)$/.test(url)) { TGCALLS.push([url.split("/").pop(), b]); return J({ ok: true }); }
    return J({ ok: true });
  }
  throw new Error("unexpected fetch " + url);
};
const app = makeApp({ url: SB, key: "service", clock: () => CLOCK });
let uid = 1000;
async function upd(msg) {
  const n = SENT.length;
  await app(new Request(SB + "/functions/v1/tg-bot/tg", { method: "POST", headers: { "x-telegram-bot-api-secret-token": DB.vault.tg_webhook_secret },
    body: JSON.stringify({ update_id: ++uid, message: msg }) }));
  return SENT.slice(n);
}
const owner = (text) => upd({ chat: { id: Number(OWNER), type: "private" }, from: { id: Number(OWNER) }, text });
const group = (text, from = 777) => upd({ chat: { id: Number(GID), type: "supergroup" }, from: { id: from }, text });
async function tick(key = DB.vault.tg_webhook_secret) {
  const n = SENT.length;
  const r = await app(new Request(SB + "/functions/v1/tg-bot/tick", { method: "POST", headers: { "x-report-key": key }, body: "{}" }));
  return { status: r.status, body: r.status === 200 ? await r.json() : null, out: SENT.slice(n) };
}
const plain = (h) => h.replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const ALL = [];
const rules = (t) => !/زیان|قوی|داریاگلد|دریا گلد|مسئولیت|توصیه‌ی سرمایه|بسته شدن|پشت سطح|می‌خواهی |صبر کن |ببین|بگذار~|بخری|بفروشی/.test(t);

// ================= pure helpers =================
check("emaLast = pandas ewm(adjust=False)", Math.abs(A.emaLast([1, 2, 3], 2) - (2 / 3 * 3 + 1 / 3 * (2 / 3 * 2 + 1 / 3 * 1))) < 1e-9);
const fr = A.fractals([[0, 0, 1, 0, 0], [1, 0, 2, 0, 0], [2, 0, 3, -1, 0], [3, 0, 9, -2, 0], [4, 0, 3, -1, 0], [5, 0, 2, 0, 0], [6, 0, 1, 0, 0]], 3, 0);
check("fractals: 3-bar swing high confirmed only with 3 bars each side", fr.highs.length === 1 && fr.highs[0][1] === 9 && fr.lows.length === 1 && fr.lows[0][1] === -2);
const down = { M5: "نزولی", M15: "نزولی", H1: "نزولی", H4: "نزولی" };
check("trend summary: aligned", A.trendSummary(down).line === "جهت بزرگ بازار نزولی است (قیمت در ساعت‌های اخیر بیشتر پایین رفته) و حرکت کوتاه‌مدت هم با آن هم‌جهت است." && A.trendSummary(down).overall === "نزولی");
check("trend summary: lower TFs correcting (t228u wording)", A.trendSummary({ M5: "نزولی", M15: "نزولی", H1: "صعودی", H4: "صعودی" }).line ===
  "جهت بزرگ بازار صعودی است (قیمت در ساعت‌های اخیر بیشتر بالا رفته)، ولی در کوتاه‌مدت قیمت کمی برعکس برگشته است. برای خرید بهتر است صبر کنید تا ۵ و ۱۵ دقیقه‌ای هم دوباره صعودی شوند.");
check("trend summary: one TF correcting", A.trendSummary({ M5: "صعودی", M15: "نزولی", H1: "نزولی", H4: "نزولی" }).line.includes("ولی ۵ دقیقه‌ای فعلاً برعکس برگشته است"));
check("trend summary: H4≠H1 → نامشخص; both flat → خنثی", A.trendSummary({ M5: "نزولی", M15: "نزولی", H1: "خنثی", H4: "نزولی" }).overall === "نامشخص" &&
  A.trendSummary({ M5: "نزولی", M15: "نزولی", H1: "خنثی", H4: "خنثی" }).overall === "خنثی");
const tm = A.trendMsg(down, { quote: { dg: 3530.12 }, dataAt: CLOCK.getTime(), at: CLOCK.getTime() });
check("/trend card: plain summary first, then M5, M15, H1, H4 lines, last-data time, Latin price", ["جهت بزرگ بازار نزولی است", "۵ دقیقه‌ای: نزولی", "۱۵ دقیقه‌ای: نزولی", "۱ ساعته: نزولی", "۴ ساعته: نزولی", "**جزئیات**", "آخرین قیمت"].every((x) => tm.includes(x)) && tm.includes("`3530.12`"));
check("money: fee once per trade, 1U = 80k/$ and 0.5U = 40k/$", A.netToman(-1, 3540, 3530, 1) === 786000 && A.netToman(-1, 3540, 3530, 0.5) === 386000 && A.netToman(1, 3540, 3539, 1) === -94000);
check("tomanFa: short signed amounts", A.tomanFa(-248400) === "−248 هزار" && A.tomanFa(1480000) === "+1.48 میلیون");
const onHalf = (x) => Math.abs(x * 2 - Math.round(x * 2)) < 0.05;
const slS = A.placeSL(-1, 3544.6, 3542, 4);    // edge + 1.2 = 3545.8 → past 3545 round
check("sell SL: behind the zone, clear of the $5 round, plus spread (closed at the ask)", slS >= 3545.6 + 0.25 && !onHalf(slS - 0.25));
const slB = A.placeSL(1, 3515.4, 3517, 4);
check("buy SL: below the round number cluster, never on .00/.50", slB <= 3514.4 && !onHalf(slB));
const tpB = A.placeTP(1, 3550.2), tpS = A.placeTP(-1, 3499.8);
check("TP before a $5 round number (buy below it, sell above it + spread)", tpB < 3550 && tpB > 3549 && tpS > 3500.25 && tpS < 3501.2);
check("parseEntry: side optional, Persian digits", A.parseEntry(["sell", "۳۵۳۱٫۸۰"]).dir === -1 && A.parseEntry(["3531.8"]).dir === 0 && A.parseEntry(["خرید", "3531.8"]).dir === 1);
let bad = 0; for (const x of [[], ["hold", "3531"], ["sell"], ["3"], ["sell", "3531", "1"]]) { try { A.parseEntry(x); } catch { bad++; } }
check("parseEntry rejects bad input", bad === 5);

// session limits and validity
const ms = (iso) => U(iso).getTime();
check("entry limit: Friday 23:20 → until 23:30 (no new entry after)", A.entryLimit(ms("2026-11-20T19:50:00Z")).why === "friday" && A.hmOf(A.entryLimit(ms("2026-11-20T19:50:00Z")).untilMs) === "23:30");
check("entry limit: Sunday 00:10 and Monday 00:10 Tehran are closed (no session); Tuesday 00:10 open until 00:30",
  A.entryLimit(ms("2026-11-21T20:40:00Z")).closed === "closed" && A.entryLimit(ms("2026-11-22T20:40:00Z")).closed === "closed" &&
  A.hmOf(A.entryLimit(ms("2026-11-23T20:40:00Z")).untilMs) === "00:30" && A.entryLimit(ms("2026-11-23T20:40:00Z")).why === "close");
check("entry limit: Friday 23:40 and Saturday 00:10 closed; Wednesday until 00:30", A.entryLimit(ms("2026-11-20T20:10:00Z")).closed === "friday" &&
  A.entryLimit(ms("2026-11-20T20:40:00Z")).closed === "friday" && A.hmOf(A.entryLimit(ms("2026-11-18T15:00:00Z")).untilMs) === "00:30");
const newsAt = (start, end, tier = "A", label = "US CPI m/m") => ({ windows: [{ start, end, tier, label, event_time_tehran: start.slice(0, 11) + "16:00", fomc: false }] });
const lv = A.snapLevels(LEVELS(3530));
const baseCtx = (over = {}) => ({ levels: lv, quote: { dg: 3530, bid: 3529.8, spread: 0.3, bidOff: 0.2 }, atr5: 4, trend: down, adrUsed: 70, nowMs: ms("2026-11-18T15:00:00Z"), news: { windows: [] }, ...over });
let v = A.validity(baseCtx());
check("setup valid 45 min by default", v.untilMs - ms("2026-11-18T15:00:00Z") === 45 * 60000 && v.why === "time");
v = A.validity(baseCtx({ news: newsAt("2026-11-18T18:55", "2026-11-18T19:30") }));
check("next major news cuts the validity at its window start", A.hmOf(v.untilMs) === "18:55" && v.why === "news");
v = A.validity(baseCtx({ news: newsAt("2026-11-18T18:20", "2026-11-18T19:00") }));
check("inside a news window: no setup, says until when", v.news && A.noSetupMsg(v, ms("2026-11-18T15:00:00Z")).includes("زمان یک خبر مهم آمریکاست") && A.noSetupMsg(v, ms("2026-11-18T15:00:00Z")).includes("تا 19:00 ستاپی داده نمی‌شود"));
v = A.validity(baseCtx({ news: newsAt("2026-11-18T18:20", "2026-11-18T19:00", "C") }));
check("tier C news does not block setups", !v.news);
check("Friday after 23:30: setup says entries are closed", A.noSetupMsg(A.validity(baseCtx({ nowMs: ms("2026-11-20T20:05:00Z") })), 0).includes("جمعه از ساعت 23:30 ورود جدید بسته است"));

// setups
const res = A.buildSetups(baseCtx());
const allS = [...res.SELL, ...res.BUY];
check("setups: at most 2 per side; a far level is rejected with a reason", res.SELL.length <= 2 && res.BUY.length <= 2 && res.SELL.length >= 1 && res.BUY.length >= 1 &&
  res.SELL.every((c) => c.level.price < 3560));
check("every setup: range narrow (≤ $1.5), SL behind, TP1 before TP2, score 0-100, reason", allS.every((c) => c.hi - c.lo <= 1.51 && c.hi > c.lo &&
  (c.dir < 0 ? c.sl > c.hi && c.tp1 < c.lo && c.tp2 < c.tp1 : c.sl < c.lo && c.tp1 > c.hi && c.tp2 > c.tp1) && c.score >= 0 && c.score <= 100 && c.reason.length > 3));
check("SL distance ≤ $9 and ≥ $1 from the best end", allS.every((c) => Math.abs(c.sl - c.worst) <= 9 && Math.abs(c.sl - c.best) >= 1));
check("buy range carries the spread (fills at the ask)", res.BUY.every((c) => c.lo >= c.level.price + 0.25 - 1e-9));
check("trend-aligned sell scores above the counter-trend buy", res.SELL[0].score > res.BUY[0].score);
check("no edge sits on .00 or .50", allS.every((c) => [c.lo, c.hi, c.sl, c.tp1].every((x) => !onHalf(x))));
const vv = A.validity(baseCtx());
const msgO = A.setupMsg(res, baseCtx(), vv), msgG = A.setupMsg(res, baseCtx(), vv, { group: true });
ALL.push(msgO, msgG);
check("owner setup card: entry range, SL, TP1, TP2, credibility, expiry, invalidation, best/worst toman for 1U and 0.5U",
  ["ستاپ یعنی یک نقشه‌ی آماده", "اعتبار ", "از ۱۰۰", " برسد، آنجا ", "حد ضرر `", "حد سود ۱ `", "حد سود ۲ `", "معتبر است", "این ستاپ را کنار بگذارید", "یک واحد", "نیم واحد", "بهترین", "دو انتخاب‌اند", "چرا اعتبار"].every((x) => msgO.includes(x)));
check("group setup card: same prices, no toman/balance", !/تومان|هزار|میلیون|موجودی/.test(msgG) && msgG.includes("از ۱۰۰") && msgG.includes(`\`${A.px(res.SELL[0].sl)}\``));
const weak = { ...res.BUY[0], score: 31 };
const msgW = A.setupMsg({ SELL: [], BUY: [weak], why: { SELL: "تا سطح بعدی جا کم است", BUY: null } }, baseCtx(), vv);
check("score under 40 is flagged ⚠; empty side says clearly why", msgW.includes("31 از ۱۰۰ ⚠") && msgW.includes("فعلاً فروش منطقی نیست، چون تا سطح بعدی جا کم است."));
const r0 = A.buildSetups(baseCtx({ levels: [] }));
check("no levels → both sides say no sensible setup", !r0.SELL.length && !r0.BUY.length && r0.why.SELL && r0.why.BUY);
// /e
const pe = A.planEntry({ levels: lv, atr5: 4 }, -1, 3535.5);
check("/e sell inside a resistance zone: SL behind that zone, TP1 before the next support", pe.sl > 3537.7 && pe.sl - 3535.5 <= 9 && pe.tp1 < 3530 && pe.tp2 < pe.tp1 && pe.slLevel && pe.tp1Level);
const em = A.entryMsg(pe, { quote: { dg: 3530 }, nowMs: ms("2026-11-18T15:00:00Z"), dirWhy: "روند کلی نزولی" });
ALL.push(em);
check("/e card: SL/TP1/TP2 with 1U and 0.5U net toman; alternatives note", ["حد ضرر `", "حد سود ۱ `", "حد سود ۲ `", "یک واحد", "نیم واحد", "فقط یکی از دو حد سود"].every((x) => em.includes(x)) &&
  em.includes(A.tomanFa(A.netToman(-1, 3535.5, pe.sl, 1))));
const pf = A.planEntry({ levels: [], atr5: 4 }, 1, 3530);
check("/e without a level nearby: volatility SL, still ≥ $1", pf.sl < 3529 && pf.tp1 > 3530 && !pf.slLevel);
check("direction from trend; none when nothing is clear", A.directionFrom(down).dir === -1 && A.directionFrom({ M5: "خنثی", M15: "خنثی", H1: "خنثی", H4: "خنثی" }) === null);

// alerts (pure)
const t0 = ms("2026-11-18T15:00:00Z");
check("level touch: price $1.2 short of the level (inside its zone) → no alert", A.levelAlerts(lv, [[t0 - 120000, 3532, 3533, 3531.5, 3533], [t0 - 60000, 3533, 3535.0, 3532.9, 3534.9]], { day: "2026-11-18", sent: {} }).length === 0);
const la = A.levelAlerts(lv, [[t0 - 180000, 3532, 3533, 3531.5, 3533], [t0 - 120000, 3533, 3535.6, 3532.9, 3535.4], [t0 - 60000, 3535.4, 3535.5, 3532.8, 3533.0]], { day: "2026-11-18", sent: {} });
check("level touch alert within $1: says how high price went, the gap, where it is now (bounced)", la.length === 1 && la[0].text.includes("سطح مقاومت `3536.2` نزدیک شد و برگشت") &&
  la[0].text.includes("قیمت تا `3535.60` بالا رفت") && la[0].text.includes("دلار مانده به سطح") && la[0].text.includes("الان قیمت `3533.00` است") && la[0].text.includes("👀"));
const lx = A.levelAlerts(lv, [[t0 - 120000, 3533, 3535.6, 3532.9, 3535.4], [t0 - 60000, 3535.4, 3538.9, 3535.3, 3538.6]], { day: "2026-11-18", sent: {} });
check("level crossed: says it broke through and where price is now", lx.length === 1 && lx[0].text.includes("از سطح مقاومت `3536.2` رد شد") && lx[0].text.includes("بالای سطح"));
check("level touch not repeated the same day", A.levelAlerts(lv, [[t0 - 60000, 3533, 3535.0, 3532.9, 3534.9]], { day: "2026-11-18", sent: { [la[0].key]: 1 } }).length === 0);
const ta = A.trendAlerts({ M15: "خنثی", H1: "نزولی" }, { M15: "نزولی", H1: "نزولی" }, A.trendSummary(down), t0);
check("trend change alert only for the TF that changed; none on first run", ta.length === 1 && ta[0].includes("روند ۱۵ دقیقه‌ای عوض شد: از خنثی به نزولی") && ta[0].includes("حالا رو به پایین می‌رود") &&
  A.trendAlerts(undefined, { M15: "نزولی", H1: "نزولی" }, A.trendSummary(down), t0).length === 0);
const nw = { windows: [{ start: "2026-11-18T18:40", end: "2026-11-18T19:15", tier: "A", label: "US Core CPI m/m", event_time_tehran: "2026-11-18T18:40" },
  { start: "2026-11-18T18:40", end: "2026-11-18T19:15", tier: "A", label: "US CPI y/y", event_time_tehran: "2026-11-18T18:40" },
  { start: "2026-11-18T18:35", end: "2026-11-18T18:50", tier: "C", label: "US Something", event_time_tehran: "2026-11-18T18:38" }] };
const na = A.newsAlerts(nw, t0, {});
check("news alert ~10 min ahead: one message per event time, Persian names, tier C skipped", na.length === 1 && na[0].text.includes("تا 10 دقیقه‌ی دیگر") &&
  na[0].text.includes("تورم هسته‌ی مصرف‌کننده‌ی آمریکا (Core CPI)") && na[0].text.includes("تورم مصرف‌کننده‌ی آمریکا (CPI)") && !na[0].text.includes("Something") && na[0].keys.length === 2);
check("news alert not repeated; not sent > 12 min ahead", A.newsAlerts(nw, t0, Object.fromEntries(na[0].keys.map((k) => [k, 1]))).length === 0 && A.newsAlerts(nw, t0 - 5 * 60000, {}).length === 0);
const calm = Array.from({ length: 300 }, (_, i) => [i * 3e5, 3500, 3502, 3498, 3500]);
const spike = calm.concat([[300 * 3e5, 3500, 3520, 3495, 3518]]);
check("volatility: one huge M5 bar → too volatile; message", A.volState(spike, t0).state === "high" && A.volAlert(A.volState(spike, t0), t0).includes("خیلی پرنوسان"));
const quiet = Array.from({ length: 300 }, (_, i) => [i * 3e5, 3500, 3500 + (i < 250 ? 4 : 0.5), 3500 - (i < 250 ? 4 : 0.5), 3500]);
check("volatility: quiet in active hours → too quiet; not flagged in Asia hours", A.volState(quiet, t0).state === "low" && A.volState(quiet, ms("2026-11-18T05:00:00Z")).state === "normal");
// outcome tracking
const row = { side: "SELL", entry_lo: 3535, entry_hi: 3536, sl: 3540.25, tp1: 3528.25, tp2: 3522.25, dg_bid_offset: 0, created_at: new Date(t0).toISOString(), valid_until: new Date(t0 + 45 * 60000).toISOString(), status: "pending" };
const b1 = (i, h, l) => [t0 + i * 60000, (h + l) / 2, h, l, (h + l) / 2];
let u = A.resolveSetup(row, [b1(1, 3534, 3532), b1(2, 3535.4, 3533)], t0 + 3 * 60000);
check("tracking: filled when the range is touched", u.status === "filled" && u.filled_at);
u = A.resolveSetup({ ...row, ...u }, [b1(3, 3534, 3527.5)], t0 + 4 * 60000);
check("tracking: TP1 hit (sell TP fills at the ask) then still open for TP2", u.status === "filled" && u.tp1_hit === true);
u = A.resolveSetup({ ...row, ...u }, [b1(4, 3541, 3530)], t0 + 5 * 60000);
check("tracking: stop after TP1 → outcome tp1", u.status === "tp1" && u.resolved_at);
check("tracking: pending past expiry → expired; through SL before fill impossible → filled+sl same bar = sl",
  A.resolveSetup(row, [b1(50, 3534, 3533)], t0 + 51 * 60000).status === "expired" && A.resolveSetup(row, [b1(1, 3541, 3534)], t0 + 2 * 60000).status === "sl");
check("tracking: target reached before the range → missed", A.resolveSetup(row, [b1(1, 3530, 3527)], t0 + 2 * 60000).status === "missed");

// ================= app level =================
CLOCK = U("2026-11-18T15:00:00Z");
let out = await owner("/trend");
ALL.push(...out.map((x) => x.text));
check("owner /trend: live trend card, private, Persian digits outside code, Latin price in code", out.length === 1 && String(out[0].chat_id) === OWNER &&
  plain(out[0].text).includes("جهت بزرگ بازار") && /<code>\d{4}\.\d{2}<\/code>/.test(out[0].text) && out[0].text.includes("۱۵ دقیقه"));
out = await owner("/setup");
ALL.push(...out.map((x) => x.text));
check("owner /setup: setup card in private chat and every shown setup logged silently (origin owner)", out.length === 1 && String(out[0].chat_id) === OWNER &&
  out[0].text.includes("ستاپ‌ها") && SETUPS.length >= 2 && SETUPS.every((x) => x.origin === "owner" && x.valid_until && x.score >= 0 && x.dg_bid_offset !== undefined));
check("setup ids match the table check (^U-\\d{14}-[og][BS]\\d-[a-z0-9]{1,6}$)", SETUPS.every((x) => /^U-\d{14}-[og][BS]\d-[a-z0-9]{1,6}$/.test(x.id)));
check("owner /setup is not mirrored to the group", out.every((x) => String(x.chat_id) !== GID));
const nLog = SETUPS.length;
out = await owner("/signal");
check("/signal and /scan are aliases of /setup", out.length === 1 && out[0].text.includes("ستاپ‌ها") && SETUPS.length > nLog);
out = await owner("/e sell 3535.50");
ALL.push(...out.map((x) => x.text));
check("owner /e sell: SL/TP card with toman", out.length === 1 && out[0].text.includes("فروش از") && out[0].text.includes("یک واحد"));
out = await owner("/e 3530.10");
check("owner /e without side: direction from the trend is named", out.length === 1 && /جهت را ننوشتید؛ (فروش|خرید) در نظر گرفته شد، چون/.test(plain(out[0].text)));
out = await owner("/e hold");
check("/e bad input: usage", out.length === 1 && out[0].text.includes("/e sell 3531.80"));
check("/e card: SL side named correctly (sell = بالای سطح, never «پشت سطح»)", !plain(ALL.at(-1)).includes("پشت سطح") && (/حد ضرر کمی بالای سطح/.test(plain(ALL.at(-1))) || /اندازه‌ی معمول حرکت قیمت/.test(plain(ALL.at(-1)))));
{ const pb = A.entryMsg(A.planEntry({ levels: A.snapLevels(LEVELS(3530)), atr5: 3 }, 1, 3524.9), { quote: null, nowMs: CLOCK.getTime() });
  check("/e buy card: SL «زیر سطح» or volatility, never «پشت سطح»", !plain(pb).includes("پشت سطح") && (/حد ضرر کمی زیر سطح/.test(plain(pb)) || /اندازه‌ی معمول حرکت قیمت/.test(plain(pb)))); ALL.push(pb); }
for (const c of ["/trade sell 3900 3890 1", "/journal", "/pnl", "/entered 001", "/shadow", "/undo", "/loss 1000", "/win 1000", "/tp 001", "/sl 001", "/closed 001 3900"]) {
  out = await owner(c);
  check(`${c.split(" ")[0]}: removed (unknown-command hint, nothing recorded)`, out.length === 1 && out[0].text.includes("دستور ناشناخته") && !out[0].text.includes("خاموش"));
}
await app(new Request(SB + "/functions/v1/tg-bot/tg", { method: "POST", headers: { "x-telegram-bot-api-secret-token": DB.vault.tg_webhook_secret },
  body: JSON.stringify({ update_id: ++uid, callback_query: { id: "cb1", data: "c:a:tp:S-1", from: { id: Number(OWNER) }, message: { chat: { id: Number(OWNER), type: "private" }, message_id: 1 } } }) }));
check("old inline button: answered silently, nothing sent", TGCALLS.some(([m, b]) => m === "answerCallbackQuery" && b.callback_query_id === "cb1"));
// group
SENT.length = 0; const before = SETUPS.length;
out = await group("/setup");
ALL.push(...out.map((x) => x.text));
check("member /setup: group-safe card in the group (no toman), logged as group", out.length === 1 && String(out[0].chat_id) === GID && !/تومان|هزار|میلیون/.test(out[0].text) &&
  SETUPS.length > before && SETUPS.slice(before).every((x) => x.origin === "group"));
out = await group("/setup");
check("group cooldown: a repeat within 60 s is ignored", out.length === 0);
out = await group("/trend@XauscalperBot");
check("member /trend: group reply", out.length === 1 && String(out[0].chat_id) === GID && out[0].text.includes("روند"));
out = await group("/trend@OtherBot");
check("/trend addressed to another bot: ignored", out.length === 0);
for (const c of ["/e sell 3530", "/trade sell 3900 3890 1", "/status", "/offset live 0.1", "/balance 1"]) {
  out = await group(c);
  check(`group ${c.split(" ")[0]}: ignored (owner-only)`, out.length === 0);
}
CLOCK = U("2026-11-18T15:02:00Z");
out = await group("/signal");
check("group /signal shares the /setup cooldown, answers after 60 s", out.length === 1 && out[0].text.includes("ستاپ‌ها"));
// feed down
FEED_DOWN = true; CLOCK = U("2026-11-18T15:04:00Z");
out = await owner("/setup");
check("feed down: /setup refuses without a live price", out.length === 1 && out[0].text.includes("قیمت زنده در دسترس نیست"));
out = await owner("/trend");
check("feed down: /trend falls back to the stored snapshot and says so", out.length === 1 && plain(out[0].text).includes("قیمت زنده در دسترس نبود") && plain(out[0].text).includes("۱۸:۲۵"));
CLOCK = U("2026-11-18T15:06:00Z");
out = await group("/setup");
check("feed down: nothing posted to the group", out.length === 0);
FEED_DOWN = false;
// weekend
CLOCK = U("2026-11-21T10:00:00Z");
out = await owner("/setup");
check("Saturday /setup: closed line", out.length === 1 && out[0].text.includes("بازار بسته است"));
out = await owner("/trend");
check("Saturday /trend: last data + closed line", out.length === 1 && out[0].text.includes("جهت بزرگ بازار") && out[0].text.includes("بازار بسته است"));
// offset live
out = await owner("/offset live 0.05");
check("/offset live sets the DaryaGold mid offset", DB.row.state.dg_mid_offset === 0.05 && out[0].text.includes("میانه"));
DB.row.state.dg_mid_offset = null;

// ================= /tick =================
CLOCK = U("2026-11-18T15:10:00Z");
check("tick: wrong key → 403, no menu change", (await tick("x")).status === 403 && !TGCALLS.some(([m]) => m === "setMyCommands"));
DB.row.state.levels = LEVELS(3530); DB.row.state.levels.computed_at_tehran = "2026-11-18 18:35:00";
let tk = await tick();
{ const sets = TGCALLS.filter(([m]) => m === "setMyCommands").map(([, b]) => b);
  check("tick: menus synced once after a deploy (owner 12, groups/default 4)", tk.body.menus && sets.length === 3 && DB.row.state.menu_version === tk.body.menus &&
    sets.find((b) => b.scope && b.scope.type === "chat").commands.length === 12 && sets.filter((b) => !b.scope || b.scope.type === "all_group_chats").every((b) => b.commands.map((c) => c.command).join() === "setup,trend,levels,brief")); }
check("tick: first run stores trend/vol state; alerts only to the owner", tk.status === 200 && DB.row.state.assist && DB.row.state.assist.trend && tk.out.every((x) => String(x.chat_id) === OWNER));
// force a level touch: put a resistance right above the live price
const live = A.quoteOf(await A.fetchMarket(CLOCK.getTime(), { tfs: [] }), 0.02).dg;
DB.row.state.levels.short.above[0] = { side: "resistance", kinds: ["NY high"], price_dg: live + 0.6, zone_dg: [live - 0.2, live + 1.4], label_fa: "سقف نیویورک", strength: "strong", touches_m15_3d: 1, distance_atr: 0.5 };
DB.row.state.assist.tick_ms = CLOCK.getTime() - 4 * 60000;
CLOCK = U("2026-11-18T15:12:00Z");
tk = await tick();
const lvlMsgs = tk.out.filter((x) => x.text.includes("سطح"));
check("tick: level touch alert sent once", lvlMsgs.length === 1 && String(lvlMsgs[0].chat_id) === OWNER);
CLOCK = U("2026-11-18T15:24:00Z");
tk = await tick();
check("tick: menus not re-sent on later ticks", !tk.body.menus && TGCALLS.filter(([m]) => m === "setMyCommands").length === 3);
check("tick: same level not alerted again that day", tk.out.filter((x) => x.text.includes("سطح")).length === 0);
// trend change
DB.row.state.assist.trend = { M15: "صعودی", H1: "نزولی" };
CLOCK = U("2026-11-18T15:26:00Z");
tk = await tick();
check("tick: M15 change alert once", tk.out.filter((x) => x.text.includes("روند ۱۵ دقیقه‌ای عوض شد")).length === 1);
CLOCK = U("2026-11-18T15:28:00Z");
tk = await tick();
check("tick: no repeat while the trend is unchanged", tk.out.filter((x) => x.text.includes("تغییر روند")).length === 0);
// news
DB.row.news = { windows: [{ start: "2026-11-18T19:05", end: "2026-11-18T19:40", tier: "A", label: "US Non-Farm Employment Change", event_time_tehran: "2026-11-18T19:08" }] };
CLOCK = U("2026-11-18T15:30:00Z");
tk = await tick();
check("tick: NFP alert ~8 min ahead", tk.out.filter((x) => x.text.includes("اشتغال غیرکشاورزی")).length === 1);
CLOCK = U("2026-11-18T15:32:00Z");
tk = await tick();
check("tick: news alert not repeated", tk.out.filter((x) => x.text.includes("خبر مهم")).length === 0);
// setups get resolved by the tick
check("tick: logged setups are tracked (status/checked_at written)", SETUPS.some((x) => x.checked_at));
// weekend
CLOCK = U("2026-11-21T10:00:00Z");
for (const x of SETUPS) x.status = "expired";
tk = await tick();
check("tick: weekend with nothing pending → skipped, no message", tk.body.skipped === "closed" && tk.out.length === 0);
// group never gets alerts
check("no alert or assistant reply ever went to the group except member-requested ones", SENT.filter((x) => String(x.chat_id) === GID).every((x) => /ستاپ‌ها|روند طلا/.test(x.text)));

// ================= wording rules =================
ALL.push(HELP, ...COMMANDS.map((c) => c.description), ...SENT.map((x) => x.text));
check("wording: never «زیان», «قوی», «داریاگلد», or disclaimer lines", ALL.every(rules));
check("menu: no digits in descriptions; /setup /e /trend present", COMMANDS.every((c) => !/\d/.test(c.description)) && ["setup", "e", "trend"].every((k) => COMMANDS.some((c) => c.command === k)));
check("ZWNJ: half-spaces in common words (دقیقه‌ای، هم‌جهت، نقشه‌ی)", tm.includes("دقیقه‌ای") && msgO.includes("نقشه‌ی") && A.trendSummary(down).line.includes("هم‌جهت") && msgO.includes("هم‌جهت"));
{ const lm = levelsMsg(LEVELS(3530), CLOCK); ALL.push(lm);
  check("/levels plain card: price, what a level is, above/below with $ distance, no ATR/H1/OR jargon", ["سطوح مهم قیمت", "سطح یعنی", "**⬆️ بالای قیمت**", "**⬇️ زیر قیمت**", "دلار بالاتر", "دلار پایین‌تر"].every((x) => lm.includes(x)) &&
    !/ATR|H1|H4|OR |سوئینگ|رژیم|پهنه/.test(lm)); }
check("render keeps copyable prices Latin", render("ورود `3535.10`").includes("<code>3535.10</code>"));
console.log(`\n${fails} failed`);
process.exit(fails ? 1 : 0);
