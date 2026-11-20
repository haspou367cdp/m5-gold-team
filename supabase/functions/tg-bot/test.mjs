// Offline tests for the Edge Function (node >= 20): Telegram, GitHub, Supabase REST/RPC and JWKS are mocked.
// usage: node supabase/functions/tg-bot/test.mjs   (nothing is sent anywhere)
import { makeApp } from "./app.js";
import * as JR from "./ledger.js";
import { CAL, basisStats, basisStatus, parseCalibrate, parseDuka, pickFeed, sessionOf, statsLines } from "./calib.js";
import { sessionDate, HELP, render, parseAmount, parseTrade, normalize, teh, verifyOidc, toman, tomanShort, shadowMsg, forexOpen, weekendClosed, closedLine, tradeWarn, marketPrice, levelsMsg, levelsFresh, faDate, channelChat, publicReply, groupEnabled } from "./lib.js";
let fails = 0;
const check = (n, c) => { console.log((c ? "PASS " : "FAIL ") + n); if (!c) fails++; };
const SB = "https://x.supabase.co";
const DB = { row: { state: { equity_toman: 2085600, signals_sent: [], presession_sent: { "2026-11-13-pm": true } }, news: { windows: [] }, version: 0 }, vault: { tg_webhook_secret: "W".repeat(64) } };
const SENT = [], DISPATCHED = [];
const OBS = []; let OBS_FAIL = false, DUKA_DOWN = false; const DUKA = { A: [], B: [] };
const TBL = { signals: [], journal: [] }, TBL_CALLS = []; let TBL_FAIL = false;
let failHtml = false, failGroup = false, ghStatus = 204, raceOnce = false;
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json" } });
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.startsWith(SB + "/rest/v1/bot_state")) return J([structuredClone(DB.row)]);
  if (url.startsWith(SB + "/rest/v1/rpc/")) {
    const fn = url.split("/").pop(), a = JSON.parse(init.body || "{}");
    if (fn === "bot_secret") return J(DB.vault[a.p_name] ?? null);
    if (fn === "bot_webhook_secret") return J(DB.vault.tg_webhook_secret);
    if (fn === "bot_set_secret") { DB.vault[a.p_name] = a.p_value; return new Response(null, { status: 204 }); }
    if (fn === "bot_save") {
      if (raceOnce) { raceOnce = false; DB.row.version++; return J(false); }   // simulate a GitHub merge in between
      if (a.p_version !== DB.row.version) return J(false);
      DB.row.state = a.p_state; DB.row.version++; return J(true);
    }
    if (fn === "bot_merge") {
      const keys = ["signals_sent", "presession_sent", "last_run_tehran", "last_verdict", "news_fetched_at", "shadow", "last_price", "friday_reminder_sent", "levels"];   // = SQL bot_merge allowed
      for (const k of keys) if (k in a.p_patch) DB.row.state[k] = a.p_patch[k];
      DB.row.state.pending_cmds = (DB.row.state.pending_cmds || []).filter((x) => !a.p_done.includes(x.id));
      if (a.p_news) DB.row.news = a.p_news; DB.row.version++;
      return J({ pending: DB.row.state.pending_cmds.length });
    }
  }
  if (url.includes("api.telegram.org")) {
    const b = JSON.parse(init.body);
    if (url.endsWith("/sendMessage")) {
      if (failGroup && String(b.chat_id) === "-1001958445009") return J({ ok: false, description: "Forbidden" });
      if (failHtml && b.parse_mode) return J({ ok: false });
      SENT.push(b); return J({ ok: true, result: { message_id: SENT.length } });
    }
    if (url.endsWith("/setMyCommands")) { DB.menu = b.commands; return J({ ok: true }); }
    if (url.endsWith("/deleteMyCommands")) { (DB.menuDeleted = DB.menuDeleted || []).push(b); return J({ ok: true }); }
    if (url.endsWith("/setWebhook")) { DB.hook = b; return J({ ok: true }); }
    if (url.endsWith("/answerCallbackQuery")) { (DB.answers = DB.answers || []).push(b); return J({ ok: true }); }
    if (url.endsWith("/editMessageReplyMarkup")) { (DB.edits = DB.edits || []).push(b); return J({ ok: true }); }
    if (url.endsWith("/getWebhookInfo")) return J({ ok: true, result: { url: DB.hook && DB.hook.url, pending_update_count: 0 } });
  }
  const tm = url.match(/\/rest\/v1\/(signals|journal)(\?.*)?$/);
  if (tm) {   // tiny PostgREST: eq / in / gte / lte / lt filters, order, limit, on_conflict ignore, return=representation
    if (TBL_FAIL) return new Response("x", { status: 500 });
    TBL_CALLS.push({ t: tm[1], method: init.method || "GET", url });
    const T = TBL[tm[1]], q = new URLSearchParams((tm[2] || "").slice(1)), pk = tm[1] === "signals" ? "id" : "trade_id";
    const fl = [...q.entries()].filter(([k]) => !["select", "order", "limit", "on_conflict"].includes(k));
    const ok = (r) => fl.every(([k, v]) => { const [op, ...rest] = v.split("."); const val = rest.join(".");
      const x = r[k] == null ? null : String(r[k]);
      if (op === "eq") return x === val; if (op === "in") return val.slice(1, -1).split(",").includes(x);
      if (op === "not" && val === "is.null") return x !== null;
      if (op === "gte") return x !== null && x >= val; if (op === "lte") return x !== null && x <= val; if (op === "lt") return x !== null && x < val; return false; });
    const m = init.method || "GET";
    if (m === "POST") { for (const r of JSON.parse(init.body)) if (!T.some((y) => y[pk] === r[pk])) T.push({ status: "sent", ...r }); return new Response(null, { status: 201 }); }
    if (m === "PATCH") { const b = JSON.parse(init.body), hit = T.filter(ok); for (const r of hit) Object.assign(r, b); return String(init.headers.prefer || "").includes("representation") ? J(hit) : new Response(null, { status: 204 }); }
    if (m === "DELETE") { for (const r of T.filter(ok)) T.splice(T.indexOf(r), 1); return new Response(null, { status: 204 }); }
    let rows = T.filter(ok);
    const ord = q.get("order"); if (ord) { const [k, d] = ord.split("."); rows = [...rows].sort((a, b) => (String(a[k]) < String(b[k]) ? -1 : 1) * (d === "desc" ? -1 : 1)); }
    if (q.get("limit")) rows = rows.slice(0, Number(q.get("limit")));
    return J(structuredClone(rows));
  }
  if (url.startsWith(SB + "/rest/v1/price_observations")) {
    if (OBS_FAIL) return new Response("x", { status: 500 });
    if ((init.method || "GET") === "POST") { OBS.push(JSON.parse(init.body)); return new Response(null, { status: 201 }); }
    const since = decodeURIComponent(url.split("observed_at=gte.")[1].split("&")[0]);
    return J(OBS.filter((o) => o.observed_at >= since).map(({ observed_at, basis_usd, reference, session, status }) => ({ observed_at, basis_usd, reference, session, status })));
  }
  if (url.includes("freeserv.dukascopy.com")) {
    if (DUKA_DOWN) throw new Error("network");
    const side = url.includes("offer_side=A") ? "A" : "B";
    return new Response("_cb(" + JSON.stringify(DUKA[side]) + ");", { status: 200 });
  }
  if (url.includes("api.github.com")) { DISPATCHED.push(JSON.parse(init.body)); return new Response(null, { status: ghStatus }); }
  throw new Error("unexpected fetch " + url);
};
// ---- OIDC test key
const kp = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
const jwk = { ...(await crypto.subtle.exportKey("jwk", kp.publicKey)), kid: "k1" };
const jw = async () => ({ keys: [jwk] });
const enc = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
async function jwt(claims) {
  const h = enc({ alg: "RS256", kid: "k1" }), p = enc(claims);
  const sig = Buffer.from(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", kp.privateKey, new TextEncoder().encode(`${h}.${p}`))).toString("base64url");
  return `${h}.${p}.${sig}`;
}
const good = { iss: "https://token.actions.githubusercontent.com", aud: "m5-gold-bot", repository: "haspou367cdp/m5-gold-team", ref: "refs/heads/main", exp: Date.now() / 1000 + 300 };
let CLOCK = new Date("2026-11-11T10:30:00Z");   // Wednesday 14:00 Tehran (market open)
const app = makeApp({ url: SB, key: "service", clock: () => CLOCK });
const FN = SB + "/functions/v1/tg-bot";
const gh = async (path, method = "GET", body) => app(new Request(FN + path, { method, body: body && JSON.stringify(body),
  headers: { authorization: "Bearer " + (await jwt(good)) } }), jw);
let uid = 1;
async function tgSend(text, chat = 45639251, hdr = DB.vault.tg_webhook_secret) {
  SENT.length = 0;
  const r = await app(new Request(FN + "/tg", { method: "POST", headers: { "x-telegram-bot-api-secret-token": hdr },
    body: JSON.stringify({ update_id: uid++, message: { chat: { id: chat }, text } }) }), jw);
  return { status: r.status, out: SENT.map((x) => x.text), chats: SENT.map((x) => String(x.chat_id)) };
}
const st = () => DB.row.state;

// formatting parity with bot.py
check("render: bold/italic/code, Persian digits, Latin code, RLM", render("**a 1.5**\n`3884.2` 2,085,600") === "\u200f<b>a ۱٫۵</b>\n\u200f<code>3884.2</code> ۲٬۰۸۵٬۶۰۰");
check("render: command in code isolated with LRM", render("`/loss 150000`  ثبت ضرر") === "\u200f\u200e<code>/loss 150000</code>\u200e  ثبت ضرر");
check("render escapes HTML", render("<x> & y").includes("&lt;x&gt; &amp;"));
check("toman / tomanShort", toman(2085600) === "2٬085٬600" && tomanShort(2085600) === "2.09 میلیون" && tomanShort(417120) === "417 هزار");
for (const [a, v] of [[["۲٬۰۸۵٬۶۰۰"], 2085600], [["2,085,600", "تومان"], 2085600], [["150", "000"], 150000], [["۱۵۰۰۰۰"], 150000]])
  check(`parseAmount ${a.join(" ")}`, parseAmount(a) === v);
for (const bad of [[], ["-5"], ["abc"], ["nan"], ["inf"], ["0"], ["1e5"]]) {
  let ok = false; try { parseAmount(bad); } catch { ok = true; } check(`parseAmount rejects '${bad.join(" ")}'`, ok);
}
// setup (GitHub OIDC): secrets into Vault, migrate state, webhook, announce once
let o = await (await gh("/admin/setup", "POST", { telegram_token: "123:TESTTOKEN", gh_token: "github_pat_TEST",
  set_webhook: true, set_commands: true, announce: true })).json();
check("setup menu: 21 commands (incl. /levels, /offset, /calibrate, /groupoff and /groupon), same wording as /help, no examples or digits", o.commands && DB.menu.length === 21 && DB.menu.some((c) => c.command === "calibrate") && DB.menu.some((c) => c.command === "levels") && DB.menu.some((c) => c.command === "offset") && DB.menu.some((c) => c.command === "groupoff") && DB.menu.some((c) => c.command === "groupon") &&
  DB.menuDeleted.length === 3 && DB.menu.every((c) => (c.command === "help" || HELP.includes(`/${c.command}`)) && !/\d/.test(c.description) &&
  (c.command === "help" || HELP.includes(c.description))));
check("setup: secrets stored, webhook set, announced once", o.telegram_token === "stored" && o.gh_token === "stored" &&
  o.webhook_url_ok && o.announced && SENT.length === 1 && SENT[0].text.includes("فوری جواب") &&
  st().equity_toman === 2085600 && DB.hook.max_connections === 1 &&
  DB.hook.secret_token === DB.vault.tg_webhook_secret && DB.hook.url === FN + "/tg");
SENT.length = 0;
o = await (await gh("/admin/setup", "POST", { set_webhook: true, announce: true })).json();
check("setup again: no second announcement, state untouched", SENT.length === 0 && st().equity_toman === 2085600);
SENT.length = 0;
o = await (await gh("/admin/setup", "POST", { send_help: true })).json();
check("setup send_help: exactly the /help card once", o.help_sent && SENT.length === 1 && SENT[0].text.includes("راهنما"));
SENT.length = 0;
check("garbage bearer token -> 401", (await app(new Request(FN + "/state", { headers: { authorization: "Bearer x.y.z" } }), jw)).status === 401);
// webhook auth + chat filter
check("wrong secret_token -> 403", (await tgSend("/help", 45639251, "nope")).status === 403);
const v0 = DB.row.version;
check("other chat ignored", (await tgSend("/balance 1", 999)).out.length === 0 && DB.row.version === v0);
let r = await tgSend("/help"); check("/help instant card", r.out.length === 1 && r.out[0].includes("راهنما") && r.out[0].startsWith("\u200f") &&
  r.out[0].includes("\u200f\u200e<code>/loss 150000</code>\u200e  ثبت ضرر") && r.out[0].includes("۱۱:۱۵ و ۱۶:۱۵") &&
  !/زیان|۱۱:۳۰/.test(r.out[0]) && r.out[0].split("\n").every((l) => !l.trim() || l.startsWith("\u200f")));
r = await tgSend("/balance ۲٬۰۸۵٬۶۰۰"); check("/balance Persian digits", st().equity_toman === 2085600 && r.out[0].includes("۲٬۰۸۵٬۶۰۰"));
for (const bad of ["/balance", "/balance -5", "/balance nan", "/loss", "/loss 0", "/win abc"]) {
  const before = JSON.stringify([st().equity_toman, st().day]);
  r = await tgSend(bad); check(`invalid '${bad}' rejected`, r.out[0].includes("چیزی ثبت نشد") && JSON.stringify([st().equity_toman, st().day]) === before);
}
r = await tgSend("/loss ۱۵۰۰۰۰"); check("/loss", st().day.losses === 1 && st().day.loss_toman === 150000 && r.out[0].includes("ضرر ثبت شد"));
raceOnce = true; r = await tgSend("/win 150 000"); check("/win with space (survives a concurrent GitHub write)", st().day.win_toman === 150000 && r.out.length === 1);
r = await tgSend("/undo"); check("/undo last (win)", st().day.wins === 0 && st().day.losses === 1);
await tgSend("/undo"); r = await tgSend("/undo"); check("/undo empty safe", r.out[0].includes("چیزی برای حذف"));
await tgSend("/loss 100000"); await tgSend("/loss 100000"); r = await tgSend("/loss 100000");
check("3 losses -> daily stop notice", r.out[0].includes("توقف روزانه"));
DB.row.state.day = { date: teh().date, losses: 0, loss_toman: 0, wins: 0, win_toman: 0, records: [] };
await tgSend("/loss 300000"); r = await tgSend("/loss 120000"); check("20% net loss -> daily stop notice", r.out[0].includes("توقف روزانه"));
r = await tgSend("/status"); check("/status card", r.out[0].includes("وضعیت") && r.out[0].includes("۲ ضرر") && r.out[0].includes("۰۷:۰۰ تا ۰۰:۳۰"));
r = await tgSend("/foo"); check("unknown -> hint", r.out[0].includes("/help"));
const s0 = normalize({ day: { date: "2000-01-01", losses: 3 }, equity_toman: 5 });
check("Tehran-midnight reset", s0.day.losses === 0 && s0.day.date === teh().date && s0.equity_toman === 5);
check("Tehran clock is UTC+3:30", teh(new Date("2026-11-13T20:30:00Z")).full === "2026-11-14 00:00");
// /scan -> queue + dispatch
DISPATCHED.length = 0; r = await tgSend("/scan");
check("/scan -> instant ack + workflow dispatch", r.out[0].includes("در حال بررسی") && DISPATCHED.length === 1 && DISPATCHED[0].inputs.mode === "command");
r = await tgSend("/brief"); check("/scan then /brief within 90 s: both dispatched, both queued", DISPATCHED.length === 2 &&
  DISPATCHED[1].inputs.mode === "command" && st().pending_cmds.length === 2 && r.out[0].includes("در حال بررسی"));
r = await tgSend("/scan"); check("repeated /scan within 90 s: deduped (no new dispatch, not queued twice), still acked",
  DISPATCHED.length === 2 && st().pending_cmds.length === 2 && r.out[0].includes("در حال بررسی"));
r = await tgSend("/brief"); check("repeated /brief within 90 s: deduped", DISPATCHED.length === 2 && st().pending_cmds.length === 2);
DB.row.state.last_dispatch = Date.now() - 120000; r = await tgSend("/scan");
check("same /scan still pending after 90 s: re-dispatched, not queued twice", DISPATCHED.length === 3 && st().pending_cmds.length === 2);
const before = uid; await tgSend("/help"); uid = before;
r = await tgSend("/help"); check("Telegram retry (same update_id) ignored", r.out.length === 0); uid += 5;
// GitHub state API
const g = await (await gh("/state")).json();
check("GET /state (OIDC) returns state + news", g.state.equity_toman === 2085600 && g.news_windows && g.state.pending_cmds.length === 2);
const ids = g.state.pending_cmds.map((x) => x.id);
await gh("/state", "POST", { patch: { last_run_tehran: "2026-11-13 17:30", equity_toman: 1, day: {} }, done_cmds: ids });
check("POST /state merges bot keys only, clears done cmds", st().last_run_tehran === "2026-11-13 17:30" && st().equity_toman === 2085600 && st().day.losses === 2 && st().pending_cmds.length === 0);
check("/state without token -> 401", (await app(new Request(FN + "/state"), jw)).status === 401);
// GitHub dispatch failure -> honest reply, retried next time
ghStatus = 403; DB.row.state.last_dispatch = 0; r = await tgSend("/scan"); ghStatus = 204;
check("dispatch failure: queued, reply says next automatic check", r.out[0].includes("در صف") && st().pending_cmds.length === 1 && st().last_dispatch === 0);
// /trade (manual trades): equity, day ledger, daily stop, /undo
const day0 = () => { DB.row.state.day = { date: teh().date, losses: 0, loss_toman: 0, wins: 0, win_toman: 0, records: [], start_equity: 2954400 }; DB.row.state.equity_toman = 2954400; DB.row.state.trades = []; };
day0();
check("parseTrade sell full", JSON.stringify(parseTrade(["sell", "3914.07", "3909.61", "1"])) === JSON.stringify({ side: "sell", entry: 3914.07, exit: 3909.61, units: 1, gross: 356800, net: 342800, fee: 14000 }));
check("parseTrade buy half, Persian digits", parseTrade(["خرید", "۳۸۹۴٫۱۱", "۳۸۹۸٫۹۹", "۰٫۵"]).gross === 195200 && parseTrade(["buy", "3894.11", "3898.99", "نیم"]).net === 181200);
for (const bad of [[], ["sell", "3914", "3909"], ["hold", "3914", "3909", "1"], ["sell", "3914", "3909", "2"], ["sell", "abc", "3909", "1"], ["sell", "39", "3909", "1"], ["sell", "3914", "3909", "-1"]]) {
  let ok = false; try { parseTrade(bad); } catch { ok = true; } check(`parseTrade rejects '${bad.join(" ")}'`, ok);
}
r = await tgSend("/trade sell 3914.07 3909.61 1");
check("/trade win: equity + net, one win, reply", st().equity_toman === 3297200 && st().day.wins === 1 && st().day.win_toman === 342800 &&
  st().trades.length === 1 && st().trades[0].id.endsWith("-T1-SELL") && r.out[0].includes("<code>3914.07</code>") &&
  r.out[0].includes("+۳۴۲٬۸۰۰") && r.out[0].includes("۳٬۲۹۷٬۲۰۰") && r.out[0].includes("یک واحد") && !/زیان/.test(r.out[0]));
r = await tgSend("/undo"); check("/undo reverses the last /trade exactly", st().equity_toman === 2954400 && st().day.wins === 0 && st().day.win_toman === 0 && st().trades.length === 0 && r.out[0].includes("۲٬۹۵۴٬۴۰۰"));
r = await tgSend("/trade buy ۳۹۰۰ ۳۸۹۹ ۰٫۵"); check("/trade loss half (Persian digits): -54,000 net, loss counted once", st().equity_toman === 2900400 && st().day.losses === 1 && st().day.loss_toman === 54000 && r.out[0].includes("نیم واحد") && r.out[0].includes("ضرر"));
const v1 = DB.row.version; r = await tgSend("/trade buy 3900"); check("/trade bad syntax: nothing recorded, usage shown", r.out[0].includes("ثبت نشد") && r.out[0].includes("/trade sell") && st().trades.length === 1);
await tgSend("/trade sell 3900 3901 1"); r = await tgSend("/trade sell 3900 3901 1");
check("3 losing trades -> daily stop", st().day.losses === 3 && r.out[0].includes("توقف روزانه"));
day0(); r = await tgSend("/trade buy 3900 3893 1");
check("20% cap uses the day's starting equity (equity drop does not shrink it)", st().day.loss_toman === 574000 && !r.out[0].includes("توقف روزانه"));
r = await tgSend("/trade buy 3900 3899.8 1"); check("…and the cap triggers at 20% of 2,954,400 = 590,880", st().day.loss_toman === 604000 && r.out[0].includes("توقف روزانه"));
day0(); DB.row.state.day.start_equity = 0; await tgSend("/balance 1000000"); check("/balance before any record sets the day's start equity", st().day.start_equity === 1000000);
await tgSend("/loss 1000"); await tgSend("/balance 2000000"); check("/balance after a record keeps the day's start equity", st().day.start_equity === 1000000);
day0();
// /shadow
check("/shadow empty", shadowMsg({ shadow: [] }).includes("هنوز موردی"));
DB.row.state.shadow = [{ at: "2026-11-13 18:10", side: "SELL", entry: 3894.2, sl: 3896.2, tp: 3890.2, offset: 0.3, gates: ["news"], status: "tp", R: 2, toman: 306000 },
  { at: "2026-11-13 18:40", side: "BUY", entry: 3880, sl: 3878, tp: 3884, offset: 0.3, gates: ["volatility", "news"], status: "sl", R: -1, toman: -174000 },
  { at: "2026-11-13 19:00", side: "SELL", entry: 3890, sl: 3892, tp: 3886, offset: 0.3, gates: ["friday"], status: "pending" }];
r = await tgSend("/shadow"); check("/shadow summary: counts, R, toman, DaryaGold Latin prices, no ‘زیان’", r.out[0].includes("هدف ۱") && r.out[0].includes("حد ضرر ۱") &&
  r.out[0].includes("+۱٫۰R") && r.out[0].includes("+۱۳۲٬۰۰۰") && r.out[0].includes("<code>3894.5</code>") && r.out[0].includes("نوسان، خبر") && !/زیان|قوی/.test(r.out[0]));
const g2 = await (await gh("/state")).json(); await gh("/state", "POST", { patch: { shadow: [{ at: "x", status: "pending" }] }, done_cmds: [] });
check("GitHub may merge 'shadow' but not equity/trades", st().shadow.length === 1 && st().equity_toman === 2954400 && Array.isArray(st().trades) && g2.state.day.start_equity === 2954400);
check("/help lists /trade, /shadow and /levels", HELP.includes("/trade sell 3914.07 3909.61 1") && HELP.includes("/shadow") && HELP.includes("`/levels`") && HELP.includes("بررسی سیگنال"));
// HTML fallback
failHtml = true; r = await tgSend("/help"); failHtml = false;
check("HTML failure -> plain-text fallback", r.out.length === 1 && !r.out[0].includes("<b>"));
// OIDC
const req = async (c) => new Request(FN + "/state", { headers: { authorization: "Bearer " + (await jwt(c)) } });
for (const [n, c] of [["other repo", { repository: "evil/x" }], ["other branch", { ref: "refs/heads/dev" }], ["wrong audience", { aud: "x" }], ["expired", { exp: 1 }]])
  check(`OIDC: ${n} rejected`, !(await verifyOidc(await req({ ...good, ...c }), jw)));
const t = await jwt(good);
// ---- DaryaGold hours (Tehran, no DST)
const U = (x) => new Date(x);
check("DaryaGold hours Mon-Fri 07:00-00:30 Tehran: Mon 07:00 open / 06:59 closed, Tue 00:29 open / 00:30 closed, Sat 00:29 open / 00:30 closed, Sunday and Mon 00:15 closed",
  forexOpen(U("2026-11-16T03:30:00Z")) && !forexOpen(U("2026-11-16T03:29:00Z")) && forexOpen(U("2026-11-16T20:59:00Z")) && !forexOpen(U("2026-11-16T21:00:00Z")) &&
  forexOpen(U("2026-11-13T20:59:00Z")) && !forexOpen(U("2026-11-13T21:00:00Z")) && !forexOpen(U("2026-11-15T08:30:00Z")) && !forexOpen(U("2026-11-15T20:45:00Z")) &&
  forexOpen(U("2026-11-11T10:30:00Z")));
check("weekendClosed = any closure (weekend and nightly 00:30-07:00)", weekendClosed(U("2026-11-14T08:00:00Z")) && weekendClosed(U("2026-11-11T22:15:00Z")) &&
  !weekendClosed(U("2026-11-11T10:30:00Z")) && !weekendClosed(U("2026-11-13T20:15:00Z")));
check("closed line: reopen Monday ۰۷:۰۰ / Thursday ۰۷:۰۰ at night, Persian digits", closedLine(U("2026-11-14T08:00:00Z")) === "🔒 بازار بسته است؛ بازگشایی دوشنبه ۰۷:۰۰" &&
  closedLine(U("2026-11-11T22:15:00Z")).endsWith("پنجشنبه ۰۷:۰۰") && !/\d/.test(closedLine(U("2026-11-14T08:00:00Z"))));
check("trading day: 00:15 Tehran belongs to the previous day; 07:00 starts a new one",
  sessionDate({ date: "2026-11-13", hm: "00:15" }) === "2026-11-12" && sessionDate({ date: "2026-11-13", hm: "07:00" }) === "2026-11-13" &&
  sessionDate({ date: "2026-12-01", hm: "06:59" }) === "2026-11-30");
{ const s0 = normalize({ day: { date: "2026-11-12", losses: 3, loss_toman: 1, wins: 0, win_toman: 0, records: [] } }, { date: "2026-11-13", hm: "00:20", full: "2026-11-13 00:20" });
  const s1 = normalize({ day: { date: "2026-11-12", losses: 3, loss_toman: 1, wins: 0, win_toman: 0, records: [] } }, { date: "2026-11-13", hm: "07:05", full: "2026-11-13 07:05" });
  check("daily stop kept until the 00:30 close and reset at 07:00", s0.day.losses === 3 && s1.day.losses === 0 && s1.day.date === "2026-11-13"); }
CLOCK = U("2026-11-14T08:00:00Z"); DISPATCHED.length = 0; const pend0 = st().pending_cmds.length;
r = await tgSend("/scan"); check("Saturday /scan: one closed line, no dispatch, nothing queued", r.out.length === 1 && r.out[0].includes("بازار بسته است") &&
  r.out[0].includes("دوشنبه ۰۷:۰۰") && r.out[0].split("\n").length === 1 && DISPATCHED.length === 0 && st().pending_cmds.length === pend0);
r = await tgSend("/brief"); check("Saturday /brief: same closed line, no dispatch", r.out.length === 1 && r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0);
r = await tgSend("/levels"); check("Saturday /levels with no snapshot: same closed line, no dispatch", r.out.length === 1 && r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0 && (st().pending_cmds || []).every((x) => x.cmd !== "/levels"));
const LVBLOCK = "طلا  `3900.3`\nH4 نزولی  ·  H1 خنثی  ·  روند نامشخص\n\nبالا\n▸ `3910.3`  (+10.0)  مهم\n  سقف دیروز + سوئینگ H4  ·  2 تماس M15\n  پهنه  `3909.9`–`3910.7`";
DB.row.state.levels = { computed_at_tehran: "2026-11-13 17:30:00", block: LVBLOCK };
r = await tgSend("/levels");
check("Saturday /levels with stored snapshot: served with age, no dispatch", r.out.length === 1 && r.out[0].includes("سن داده") && r.out[0].includes("<code>3900.3</code>") && r.out[0].includes("H4 نزولی") && !r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0);
CLOCK = U("2026-11-13T22:10:00Z"); r = await tgSend("/scan"); check("Saturday 01:40, after the 00:30 close: closed line", r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0);
CLOCK = U("2026-11-13T20:15:00Z"); DB.row.state.last_dispatch = 0; r = await tgSend("/scan");
check("Friday 23:45 (entries closed, market open): /scan still analysed (bot answers «جمعه‌شب»)", DISPATCHED.length === 1 && r.out[0].includes("در حال بررسی"));
DB.row.state.pending_cmds = [];
// weekday /levels: fresh snapshot is served instantly; stale queues like /scan
CLOCK = U("2026-11-11T10:30:00Z");  // Wednesday 14:00 Tehran
DISPATCHED.length = 0;
DB.row.state.last_dispatch = 0;
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:50:00", block: LVBLOCK };
r = await tgSend("/levels");
check("weekday /levels with a fresh snapshot: instant card, no dispatch", r.out.length === 1 && r.out[0].includes("<code>3900.3</code>") && r.out[0].includes("سطوح") && !r.out[0].includes("در حال بررسی") && DISPATCHED.length === 0);
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:00:00", block: LVBLOCK };
r = await tgSend("/levels");
check("weekday /levels with a stale snapshot: ack + dispatch like /scan", r.out[0].includes("در حال بررسی") && DISPATCHED.length === 1 && st().pending_cmds.some((x) => x.cmd === "/levels"));
r = await tgSend("/levels");
check("repeated stale /levels within 90 s: deduped, still acked", DISPATCHED.length === 1 && st().pending_cmds.filter((x) => x.cmd === "/levels").length === 1 && r.out[0].includes("در حال بررسی"));
DB.row.state.pending_cmds = [];
check("levelsFresh helper", levelsFresh({ computed_at_tehran: "2026-11-11 13:50:00" }, CLOCK) && !levelsFresh({ computed_at_tehran: "2026-11-11 13:00:00" }, CLOCK));
check("faDate Jalali matches Python (11 Nov 2026 = 20 Aban)", faDate(CLOCK).includes("آبان"));
CLOCK = U("2026-11-14T08:00:00Z"); SENT.length = 0; let h = await (await app(new Request(FN + "/health"))).json();
check("/health on Saturday: market_closed + closed line, no Telegram call", h.ok && h.market_closed === true && h.closed_line.includes("دوشنبه ۰۷:۰۰") && h.build && SENT.length === 0);
CLOCK = U("2026-11-11T10:30:00Z"); h = await (await app(new Request(FN + "/health"))).json();
check("/health on a weekday: market open", h.market_closed === false && !h.closed_line);
// ---- /trade sanity check (warn, still record)
day0(); DB.row.state.last_price = { bid: 3900, at: teh(CLOCK).full }; DB.row.state.dg_offset = undefined;
r = await tgSend("/trade buy 3900.3 3903.3 1"); check("/trade normal: no warning", !r.out[0].includes("⚠️") && st().trades.length === 1 && !st().trades[0].warned);
r = await tgSend("/trade sell 3900 3900 1"); check("/trade exit = entry: one warning line, still recorded", r.out[0].includes("ورود و خروج یکی است") && r.out[0].includes("/undo") &&
  r.out[0].split("\n").filter((l) => l.includes("⚠️")).length === 1 && st().trades.length === 2 && st().trades[1].warned);
r = await tgSend("/trade buy ۳۹۰۰ ۳۹۴۵ ۰٫۵"); check("/trade move > $40 (Persian digits): warning, recorded", r.out[0].includes("بیش از ۴۰ دلار") && st().trades.length === 3);
r = await tgSend("/trade sell 3990 3985 1"); check("/trade > $50 from the last known price: warning", r.out[0].includes("بیش از ۵۰ دلار با بازار") && st().trades.length === 4);
DB.row.state.last_price = { bid: 3900, at: "2026-11-09 10:00" }; r = await tgSend("/trade sell 3990 3985 1");
check("/trade: stale price (> 24 h) -> no distance warning", !r.out[0].includes("⚠️") && st().trades.length === 5);
check("tradeWarn/marketPrice pure: uses dg_offset, combines reasons in one line", marketPrice({ last_price: { bid: 3900, at: teh(CLOCK).full }, dg_offset: 0.5 }, CLOCK) === 3900.5 &&
  tradeWarn({ entry: 3800, exit: 3800 }, { last_price: { bid: 3900, at: teh(CLOCK).full } }, CLOCK).split("؛").length === 3);
day0();
// ---- /offset (owner chat only)
r = await tgSend("/offset"); check("/offset shows the default 0.3", r.out[0].includes("۰٫۳") && r.out[0].includes("<code>/offset 0.4</code>"));
r = await tgSend("/offset ۰٫۴"); check("/offset ۰٫۴ (Persian digits) sets 0.4", st().dg_offset === 0.4 && r.out[0].includes("ثبت شد") && r.out[0].includes("۰٫۴"));
for (const bad of ["/offset abc", "/offset 9", "/offset 0.4 0.5x"]) { r = await tgSend(bad); check(`/offset rejects '${bad}'`, st().dg_offset === 0.4 && r.out[0].includes("ثبت نشد")); }
r = await tgSend("/offset -0.2"); check("/offset accepts a negative offset", st().dg_offset === -0.2);
await tgSend("/offset 0.4");
r = await tgSend("/offset 0.5", 999); check("/offset from another chat ignored", r.out.length === 0 && st().dg_offset === 0.4);
await gh("/state", "POST", { patch: { dg_offset: 9, last_price: { bid: 3901, at: "2026-11-11 14:00" } }, done_cmds: [] });
check("GitHub may merge last_price but never dg_offset", st().dg_offset === 0.4 && st().last_price.bid === 3901);
await gh("/state", "POST", { patch: { levels: { block: "x", computed_at_tehran: "2026-11-11 14:00:00" }, dg_offset: 1 }, done_cmds: [] });
check("GitHub may merge levels but never dg_offset", st().levels && st().levels.block === "x" && st().dg_offset === 0.4);
// ---- /shadow Asia line
const asiaS = { shadow: [{ at: "2026-11-11 09:04", side: "SELL", entry: 3900, sl: 3902, tp: 3896, offset: 0.3, gates: ["asia"], session: "asia", status: "tp", R: 2, toman: 306000 },
  { at: "2026-11-11 15:00", side: "BUY", entry: 3880, sl: 3878, tp: 3884, offset: 0.3, gates: ["news"], status: "sl", R: -1, toman: -174000 }] };
check("/shadow: Asia line with its own counts; empty Asia says so", shadowMsg(asiaS).includes("آسیا: بسته‌شده 1 · هدف 1 · حد ضرر 0 · جمع +2.0R") &&
  shadowMsg({ shadow: [asiaS.shadow[1]] }).includes("آسیا: هنوز موردی ثبت نشده") && !/زیان|قوی/.test(shadowMsg(asiaS)));
check("/help lists /offset, /groupoff and /groupon; no زیان or قوی", HELP.includes("`/offset`") && HELP.includes("`/groupoff`") && HELP.includes("`/groupon`") && HELP.includes("قطع موقت ارسال به گروه") && HELP.includes("وصل دوباره ارسال به گروه") && !/زیان|قوی/.test(HELP));
check("OIDC: tampered payload rejected", !(await verifyOidc(new Request("https://x", { headers: { authorization: "Bearer " + t.split(".")[0] + "." + enc({ ...good, x: 1 }) + "." + t.split(".")[2] } }), jw)));

// ---- group mirror (BAROBAX / channel_id): only /levels from the private chat
const GID = "-1001958445009";
check("channelChat empty without a distinct id", channelChat({}) === "" && channelChat({ channel_id: "" }) === "" && channelChat({ channel_id: "45639251" }) === "");
check("channelChat reads bot_state", channelChat({ channel_id: GID }) === GID && channelChat({ channel_id: -1001958445009 }) === GID);
const vG = DB.row.version;
DB.row.state.channel_id = GID;
CLOCK = U("2026-11-11T10:30:00Z");
async function tgUpdate(update) {
  SENT.length = 0;
  const r = await app(new Request(FN + "/tg", { method: "POST", headers: { "x-telegram-bot-api-secret-token": DB.vault.tg_webhook_secret },
    body: JSON.stringify({ update_id: uid++, ...update }) }), jw);
  return { status: r.status, out: SENT.map((x) => x.text), chats: SENT.map((x) => String(x.chat_id)) };
}
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup", title: "BAROBAX" }, from: { id: 45639251 }, text: "/levels" } });
check("owner /levels in the group is ignored", r.out.length === 0 && DB.row.version === vG);
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup", title: "BAROBAX" }, from: { id: 45639251 }, text: "/status" } });
check("owner /status in the group is ignored", r.out.length === 0 && DB.row.version === vG);
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup" }, text: "TEST2" } });
check("plain group message is ignored", r.out.length === 0);
r = await tgUpdate({ channel_post: { chat: { id: Number(GID), type: "channel", title: "BAROBAX" }, text: "/levels" } });
check("channel_post updates are ignored", r.out.length === 0 && DB.row.version === vG);
DISPATCHED.length = 0; DB.row.state.last_dispatch = 0; DB.row.state.pending_cmds = [];
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:50:00", block: LVBLOCK };
r = await tgSend("/levels");
check("private /levels is mirrored to the group, same text", r.out.length === 2 && r.chats[0] === "45639251" && r.chats[1] === GID && r.out[0] === r.out[1] && r.out[0].includes("سطوح") && DISPATCHED.length === 0);
r = await tgSend("/status");
check("private /status stays private", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("وضعیت"));
r = await tgSend("/help");
check("private /help stays private", r.out.length === 1 && r.chats.every((c) => c === "45639251"));
day0(); r = await tgSend("/trade sell 3914.07 3909.61 1");
check("private /trade stays private", r.out.length === 1 && r.chats[0] === "45639251");
DISPATCHED.length = 0; DB.row.state.last_dispatch = 0; DB.row.state.pending_cmds = [];
r = await tgSend("/scan");
check("private /scan ack stays private", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("در حال بررسی"));
r = await tgSend("/brief");
check("private /brief ack stays private", r.out.length === 1 && r.chats[0] === "45639251");
DB.row.state.pending_cmds = []; DB.row.state.last_dispatch = 0; DISPATCHED.length = 0;
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:00:00", block: LVBLOCK };
r = await tgSend("/levels");
check("stale /levels ack stays private (not mirrored)", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("در حال بررسی") && DISPATCHED.length === 1);
CLOCK = U("2026-11-14T08:00:00Z"); DISPATCHED.length = 0;
DB.row.state.levels = { computed_at_tehran: "2026-11-13 17:30:00", block: LVBLOCK };
r = await tgSend("/levels");
check("Saturday /levels snapshot is mirrored", r.out.length === 2 && r.chats[1] === GID && r.out[0].includes("سن داده") && DISPATCHED.length === 0);
r = await tgSend("/scan");
check("Saturday /scan closed line is mirrored", r.out.length === 2 && r.chats[1] === GID && r.out[0] === r.out[1] && r.out[0].includes("بازار بسته است"));
r = await tgSend("/brief");
check("Saturday /brief closed line is mirrored", r.out.length === 2 && r.chats[1] === GID && r.out[0] === r.out[1] && r.out[0].includes("بازار بسته است"));
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup", title: "BAROBAX" }, from: { id: 45639251 }, text: "/scan" } });
check("owner /scan in the group is ignored", r.out.length === 0);
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup", title: "BAROBAX" }, from: { id: 45639251 }, text: "/shadow" } });
check("owner /shadow in the group is ignored", r.out.length === 0);
DB.row.state.shadow = [{ at: "2026-11-13 18:10", side: "SELL", entry: 3894.2, sl: 3896.2, tp: 3890.2, offset: 0.3, gates: ["news"], status: "tp", R: 2, toman: 306000 },
  { at: "2026-11-13 18:40", side: "BUY", entry: 3880, sl: 3878, tp: 3884, offset: 0.3, gates: ["volatility", "news"], status: "sl", R: -1, toman: -174000 }];
r = await tgSend("/shadow");
check("private /shadow is mirrored without the toman P&L line", r.out.length === 2 && r.chats[0] === "45639251" && r.chats[1] === GID &&
  r.out[0].includes("تومان") && r.out[0].includes("یک واحد") && !r.out[1].includes("تومان") && !r.out[1].includes("یک واحد") &&
  r.out[1].includes("+۱٫۰R") && r.out[1].includes("<code>3894.5</code>") && r.out[1].includes("هدف ۱"));
DB.row.state.shadow = [];
r = await tgSend("/shadow");
check("empty /shadow is mirrored in full (no money)", r.out.length === 2 && r.out[0] === r.out[1] && r.out[0].includes("هنوز موردی") && !r.out[0].includes("تومان"));
check("publicReply drops toman P&L from /shadow and leaves /levels untouched",
  publicReply("/shadow", "جمع +1.0R · یک واحد +132,000 تومان\nآسیا: بسته‌شده 1").includes("جمع +1.0R") &&
  !publicReply("/shadow", "جمع +1.0R · یک واحد +132,000 تومان").includes("تومان") &&
  publicReply("/levels", "سطوح") === "سطوح" && publicReply("/scan", "داده‌ی قیمت در دسترس نیست") === null);
CLOCK = U("2026-11-11T10:30:00Z");
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:50:00", block: LVBLOCK };
failGroup = true; r = await tgSend("/levels"); failGroup = false;
check("group send failure does not block the owner's /levels", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("سطوح"));
failGroup = true; r = await tgSend("/shadow"); failGroup = false;
check("group send failure does not block the owner's /shadow", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("سیگنال‌های ردشده"));
const kept = st().channel_id;
await gh("/state", "POST", { patch: { channel_id: "999", last_price: { bid: 3911, at: "2026-11-11 14:00" } }, done_cmds: [] });
check("GitHub may not overwrite channel_id", st().channel_id === kept && st().last_price.bid === 3911);
check("groupEnabled defaults to on", groupEnabled({}) && groupEnabled({ group_enabled: true }) && groupEnabled({ group_enabled: null }) && !groupEnabled({ group_enabled: false }));
check("channelChat is empty when group sending is off", channelChat({ channel_id: GID, group_enabled: false }) === "" && channelChat({ channel_id: GID }) === GID);
CLOCK = U("2026-11-11T10:30:00Z");
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:50:00", block: LVBLOCK };
DB.row.state.group_enabled = undefined;
r = await tgSend("/groupoff");
check("/groupoff is private, sets the flag, and uses the pause line", r.out.length === 1 && r.chats[0] === "45639251" && st().group_enabled === false && r.out[0].includes("ارسال به گروه موقتاً قطع شد"));
r = await tgSend("/status");
check("/status shows group sending is off", r.out.length === 1 && r.out[0].includes("ارسال به گروه: قطع") && !r.out[0].includes("ارسال به گروه: وصل"));
DISPATCHED.length = 0;
r = await tgSend("/levels");
check("/levels is not mirrored while group sending is off", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("سطوح") && DISPATCHED.length === 0);
r = await tgSend("/shadow");
check("/shadow is not mirrored while group sending is off", r.out.length === 1 && r.chats[0] === "45639251");
const geOff = st().group_enabled;
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup", title: "BAROBAX" }, from: { id: 45639251 }, text: "/groupon" } });
check("/groupon in the group is ignored", r.out.length === 0 && st().group_enabled === geOff);
r = await tgSend("/groupon", 999);
check("/groupon from another chat is ignored", r.out.length === 0 && st().group_enabled === false);
r = await tgSend("/groupon");
check("/groupon is private, clears the flag, and uses the resume line", r.out.length === 1 && r.chats[0] === "45639251" && st().group_enabled === true && r.out[0].includes("ارسال به گروه دوباره وصل شد"));
r = await tgSend("/status");
check("/status shows group sending is on", r.out.length === 1 && r.out[0].includes("ارسال به گروه: وصل"));
r = await tgSend("/levels");
check("/levels is mirrored again after /groupon", r.out.length === 2 && r.chats[1] === GID && r.out[0].includes("سطوح"));
const geKept = st().group_enabled;
await gh("/state", "POST", { patch: { group_enabled: false, last_price: { bid: 3912, at: "2026-11-11 14:00" } }, done_cmds: [] });
check("GitHub may not overwrite group_enabled", st().group_enabled === geKept && st().last_price.bid === 3912);
// ---- Phase 2: /calibrate (private only, stored with the live feed, offset from the median only when enough samples)
check("parseCalibrate: price, optional ask, Persian digits; rejects junk", parseCalibrate(["3569.85"]).price === 3569.85 &&
  parseCalibrate(["۳۵۶۹٫۸۵", "3570.10"]).ask === 3570.1 && [[], ["abc"], ["35"], ["3569.85", "3560"], ["1", "2", "3"], ["3569.85", "3580"]].every((a) => { try { parseCalibrate(a); return false; } catch { return true; } }));
check("sessionOf: asia 07:00, london 11:15, new york 16:15 to 00:30, closed after", sessionOf("07:00") === "asia" && sessionOf("11:15") === "london" &&
  sessionOf("16:07") === "london" && sessionOf("16:15") === "newyork" && sessionOf("00:29") === "newyork" && sessionOf("00:30") === "closed" && sessionOf("06:59") === "closed");
check("basisStatus thresholds around the expected offset", basisStatus(0.3, 0.3) === "NORMAL_ALIGNMENT" && basisStatus(0.9, 0.3) === "MINOR_BASIS" &&
  basisStatus(2.0, 0.3) === "ELEVATED_BASIS" && basisStatus(3.0, 0.3) === "FEED_DESYNCHRONIZATION" && basisStatus(null, 0.3) === "DATA_UNAVAILABLE" && basisStatus(0.3, 0.3, false) === "DATA_UNAVAILABLE");
const T0 = Date.parse("2026-11-20T12:37:44Z");
check("parseDuka + pickFeed: latest bar at or before now, ask matched, age from bar end",
  (() => { const b = parseDuka("_cb([[" + (T0 - 104000) + ",1,1,1,3569.5,1],[" + (T0 - 44000) + ",1,1,1,3569.78,1]]);"), a = parseDuka("_cb([[" + (T0 - 44000) + ",1,1,1,3570.32,1]]);");
    const f = pickFeed(b, a, T0); return f.feed_bid === 3569.78 && f.feed_ask === 3570.32 && f.age_s === 0; })());
const mk = (n, basis, hAgo = 1, ref = "dukascopy_bid", ses = "london") => Array.from({ length: n }, (_, i) => ({ observed_at: new Date(T0 - (hAgo + i) * 3.6e6).toISOString(), basis_usd: basis + (i % 2 ? 0.02 : -0.02), reference: ref, session: ses, status: "NORMAL_ALIGNMENT" }));
let bs = basisStats(mk(4, 0.1), T0);
check("stats: 4 samples -> not calibrated (keep current offset)", !bs.calibrated && bs.offset === null && bs.count === 4 && bs.why.includes("few"));
bs = basisStats([...mk(5, 0.1), ...mk(3, -0.09, 1, "oanda_m1_close")], T0);
check("stats: 5 recent Dukascopy samples -> calibrated at the median; other references ignored", bs.calibrated && bs.offset === 0.08 && bs.count === 5 && bs.other_reference_samples === 3 && bs.std < 0.05 && bs.by_session.london.count === 5);
check("stats: newest sample older than 72 h -> not calibrated", !basisStats(mk(6, 0.1, 80), T0).calibrated);
check("stats: samples outside 7 days ignored", basisStats(mk(6, 0.1, 24 * 8), T0).count === 0);
check("stats: wide spread -> not calibrated", !basisStats([...mk(3, 0.1), ...mk(3, 1.6, 4)], T0).calibrated);
check("stats lines: Persian, no «زیان»", statsLines(bs, 0.1).join(" ").includes("میانه") && !statsLines(bs, 0.1).join(" ").includes("زیان"));
// end to end through the webhook
CLOCK = new Date(T0); OBS.length = 0;
DUKA.B = [[T0 - 44000, 1, 1, 1, 3569.55, 1]]; DUKA.A = [[T0 - 44000, 1, 1, 1, 3569.9, 1]];
st().dg_offset = null; st().dg_offset_source = null;
r = await tgSend("/calibrate 3569.85");
check("/calibrate stores the price with the live feed (basis +0.3, normal), private reply, not calibrated yet",
  r.out.length === 1 && r.chats[0] === "45639251" && OBS.length === 1 && OBS[0].basis_usd === 0.3 && OBS[0].reference === "dukascopy_bid" &&
  OBS[0].source === "telegram_calibrate" && OBS[0].status === "NORMAL_ALIGNMENT" && OBS[0].session === "london" && OBS[0].feed_ask === 3569.9 &&
  r.out[0].includes("<code>3569.85</code>") && r.out[0].includes("کالیبره نشده") && st().calibration.status === "not_calibrated" && st().dg_offset == null);
for (const p of ["3569.95", "3569.95", "3569.85", "3569.95"]) await tgSend("/calibrate " + p);
check("/calibrate: 5th sample -> offset = median (0.4), source calibrate", OBS.length === 5 && st().calibration.status === "calibrated" && st().dg_offset === 0.4 && st().dg_offset_source === "calibrate");
r = await tgSend("/calibrate");
check("/calibrate without a price: help + stats, nothing stored", r.out.length === 1 && OBS.length === 5 && r.out[0].includes("کالیبره"));
DUKA_DOWN = true; r = await tgSend("/calibrate 3569.9"); DUKA_DOWN = false;
check("feed down: stored as DATA_UNAVAILABLE, excluded from stats", OBS.length === 6 && OBS[5].status === "DATA_UNAVAILABLE" && OBS[5].basis_usd === null && r.out[0].includes("در دسترس نیست") && st().calibration.count === 5);
DUKA.B = [[T0 - 600000, 1, 1, 1, 3569.55, 1]]; r = await tgSend("/calibrate 3569.9");
check("stale feed bar (10 min) -> DATA_UNAVAILABLE", OBS[6].status === "DATA_UNAVAILABLE");
DUKA.B = [[T0 - 44000, 1, 1, 1, 3569.55, 1]];
r = await tgSend("/calibrate 35");
check("/calibrate junk -> format hint, nothing stored", r.out[0].includes("ثبت نشد") && OBS.length === 7);
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup", title: "BAROBAX" }, from: { id: 45639251 }, text: "/calibrate 3569.85" } });
check("/calibrate in the group is ignored (private only)", r.out.length === 0 && OBS.length === 7);
r = await tgSend("/calibrate 3569.85", 999);
check("/calibrate from another chat is ignored", r.out.length === 0 && OBS.length === 7);
OBS_FAIL = true; r = await tgSend("/calibrate 3569.85"); OBS_FAIL = false;
check("database failure -> short error to the owner only", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("ثبت نشد"));
await tgSend("/offset 0.5");
check("/offset marks a manual offset", st().dg_offset === 0.5 && st().dg_offset_source === "manual");

// ---------------- Phase 3: signals, journal, buttons, reports ----------------
{
  const p = JR.pnl("SELL", 3914.07, 3909.61, "1U");
  check("pnl: SELL 1U 4.46 → gross 356,800, spread 20,000, fee once 14,000 → net 322,800", p.gross === 356800 && p.spread === 20000 && p.fee === 14000 && p.net === 322800);
  const h = JR.pnl("BUY", 3894.11, 3898.99, "0.5U", false);
  check("pnl: BUY 0.5U without spread = journal.csv M3 net 181,200", h.net === 181200);
  check("riskToman = stop distance·rate + spread + fee", JR.riskToman({ entry: 3880.3, sl: 3881.9, unit: "1U" }) === 128000 + 20000 + 14000);
  const now = { date: "2026-11-20", hm: "13:30" }, late = { date: "2026-11-21", hm: "00:10" };
  check("resolveId: full, short, Persian digits, trading day after midnight",
    JR.resolveId("S-20261120-001", now) === "S-20261120-001" && JR.resolveId("20261120-7", now) === "S-20261120-007" &&
    JR.resolveId("۲", now) === "S-20261120-002" && JR.resolveId("3", late) === "S-20261120-003");
  const pc = (c, a) => { try { return JR.parseJournalCmd(c, a, now); } catch { return "ERR"; } };
  check("parseJournalCmd: /closed needs a price; /tp takes none; junk rejected",
    pc("/closed", ["001"]) === "ERR" && pc("/closed", ["001", "3569.85"]).price === 3569.85 && pc("/closed", ["3569.85"]).id === null &&
    pc("/tp", ["001", "3570"]) === "ERR" && pc("/tp", []).act === "t" && pc("/entered", ["2", "3880.1"]).price === 3880.1 && pc("/sl", ["abc"]) === "ERR" &&
    pc("/journal", []).view === "journal");
  check("parseCallback: only known actions and IDs", JR.parseCallback("a:e:S-20261120-001").act === "e" && JR.parseCallback("c:m:S-20261120-001:3569.85").price === 3569.85 &&
    JR.parseCallback("x").cancel && JR.parseCallback("c:z:S-20261120-001") === null && JR.parseCallback("c:t:DROP") === null && JR.parseCallback("c:m:S-20261120-001:1") === null);
}
CLOCK = new Date("2026-11-20T10:00:00Z");   // Friday 13:30 Tehran
DB.row.state.channel_id = GID; DB.row.state.equity_toman = 3000000; TBL.journal.length = 0; TBL.signals.length = 0;
const SIG = (n, side = "SELL", extra = {}) => ({ key: `k${n}`, at: "2026-11-20 13:30", id: `S-20261120-00${n}`, sent_at: "2026-11-20T13:30:00+03:30",
  session_date: "2026-11-20", side, unit: "1U", entry: 3880.3, sl: side === "SELL" ? 3881.9 : 3878.7, tp: side === "SELL" ? 3876.3 : 3884.3,
  valid_until: "2026-11-20T14:00:00+03:30", net_rr: 1.6, risk_toman: 162000, ...extra });
let sr = await (await gh("/state", "POST", { patch: { signals_sent: [SIG(1), SIG(2, "BUY"), { key: "legacy", at: "x" }, { ...SIG(9), id: "S-1; drop" }] }, done_cmds: [] })).json();
check("/state stores new signals (server table), ignores legacy/bad IDs", sr.signals_stored === 2 && TBL.signals.length === 2 && TBL.signals[0].status === "sent");
sr = await (await gh("/state", "POST", { patch: { signals_sent: [SIG(1), SIG(2, "BUY")] }, done_cmds: [] })).json();
check("/state again: no duplicates", TBL.signals.length === 2);
const cb = (data, from = 45639251, chat = 45639251, type = "private", mid = 77) => tgUpdate({ callback_query: { id: "q" + uid, data, from: { id: from },
  message: { message_id: mid, chat: { id: chat, type } } } });
DB.answers = []; DB.edits = [];
r = await cb("a:e:S-20261120-001");
check("button «وارد شدم» → confirmation card with ✅/❌, nothing recorded yet", r.out.length === 1 && r.chats[0] === "45639251" &&
  SENT[0].reply_markup.inline_keyboard[0][0].callback_data === "c:e:S-20261120-001" && TBL.signals[0].status === "sent" && DB.answers.length === 1);
r = await cb("x");
check("❌ cancel: buttons removed, nothing recorded", r.out.length === 0 && DB.edits.length === 1 && TBL.signals[0].status === "sent");
r = await cb("c:e:S-20261120-001");
check("✅ confirm entry → status entered with fill = card entry", TBL.signals[0].status === "entered" && TBL.signals[0].entry_fill === 3880.3 && r.out[0].includes("ورود ثبت شد"));
r = await cb("c:e:S-20261120-001");
check("second confirm of the same action → «already» error, no change", r.out[0].includes("ثبت نشد") && TBL.signals[0].status === "entered");
r = await cb("c:t:S-20261120-001", 999);
check("button from another user → ignored (answered only)", r.out.length === 0 && TBL.signals[0].status === "entered");
r = await cb("c:t:S-20261120-001", 45639251, Number(GID), "supergroup");
check("button in the group → ignored", r.out.length === 0 && TBL.signals[0].status === "entered");
CLOCK = new Date(CLOCK.getTime() + 40000);   // 40 s later
r = await tgSend("/tp 001");
check("/tp 001 → preview with net P&L and R, confirm buttons, private only", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("حد سود") &&
  r.out[0].includes("<code>3876.3</code>") && SENT[0].reply_markup.inline_keyboard[0][0].callback_data === "c:t:S-20261120-001" && TBL.journal.length === 0);
const eq0 = Number(st().equity_toman), w0 = st().day.wins, l0 = st().day.losses;
r = await cb("c:t:S-20261120-001");
const j1 = TBL.journal.find((x) => x.trade_id === "S-20261120-001");
check("confirm TP → closed, journal row (net = 4.0·80k − 20k − 14k = 286,000), +R, held 40 s → under-60s flag", TBL.signals[0].status === "closed" &&
  j1 && j1.net_toman === 286000 && j1.gross_toman === 320000 && j1.spread_toman === 20000 && j1.fee_toman === 14000 && j1.under_60s === true &&
  j1.hold_seconds === 40 && j1.source === "signal" && j1.verification === "USER_CONFIRMED" && TBL.signals[0].r_multiple === Math.round(286000 / 162000 * 100) / 100 &&
  r.out[0].includes("۶۰ ثانیه"));
check("TP feeds the daily record and equity (daily stop input) and releases the signal lock", Number(st().equity_toman) === eq0 + 286000 &&
  st().day.wins === w0 + 1 && st().day.records.at(-1).signal === "S-20261120-001" && st().signals_done.includes("S-20261120-001"));
r = await cb("c:s:S-20261120-001");
check("closing a closed signal again → refused, journal still one row", r.out[0].includes("ثبت نشد") && TBL.journal.length === 1);
r = await tgSend("/undo");
check("/undo of a signal close: equity back, journal row deleted, signal reopened (entered)", Number(st().equity_toman) === eq0 &&
  TBL.journal.length === 0 && TBL.signals[0].status === "entered" && !st().signals_done.includes("S-20261120-001"));
CLOCK = new Date(CLOCK.getTime() + 60000);
r = await tgSend("/closed 001 3878.3");
check("/closed 001 3878.3 → preview (manual), then confirm with the price", r.out[0].includes("بستن دستی") && SENT[0].reply_markup.inline_keyboard[0][0].callback_data === "c:m:S-20261120-001:3878.3");
r = await cb("c:m:S-20261120-001:3878.3");
const j2 = TBL.journal.find((x) => x.trade_id === "S-20261120-001");
check("manual close 2.0 × 80k − 20k − 14k = 126,000; held 100 s → no flag", j2 && j2.net_toman === 126000 && j2.exit_type === "manual" && j2.under_60s === false);
r = await cb("a:m:S-20261120-002");
check("button «بستن دستی» asks for the price with the /closed format", r.out[0].includes("/closed 002"));
r = await cb("c:e:S-20261120-002"); CLOCK = new Date(CLOCK.getTime() + 20000); r = await cb("c:s:S-20261120-002");
const j3 = TBL.journal.find((x) => x.trade_id === "S-20261120-002");
check("SL after 20 s: loss −1.6×80k −20k −14k = −162,000 = −1R; SL is exempt from the 60 s flag; loss counted", j3 && j3.net_toman === -162000 &&
  Number(TBL.signals[1].r_multiple) === -1 && j3.under_60s === false && st().day.losses === l0 + 1 && r.out[0].includes("حد ضرر"));
r = await tgSend("/trade sell 3914.07 3909.61 1");
check("/trade also writes a journal row (trade_cmd, user-confirmed, spread 0)", TBL.journal.some((x) => x.source === "trade_cmd" && x.net_toman === 342800 && x.spread_toman === 0));
r = await tgSend("/journal");
check("/journal lists rows, private only, Latin prices", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("<code>3914.07</code>") && r.out[0].includes("ژورنال"));
r = await tgSend("/pnl");
check("/pnl: today / 7 days / all, net after costs", r.out.length === 1 && r.out[0].includes("امروز") && r.out[0].includes("۷ روز") && r.out[0].includes("همه"));
r = await tgSend("/tp 9xx");
check("/tp junk → format hint", r.out[0].includes("ثبت نشد") && r.out[0].includes("/closed 001"));
r = await tgSend("/sl 005");
check("/sl unknown ID → not found", r.out[0].includes("پیدا نشد"));
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup" }, from: { id: 45639251 }, text: "/pnl" } });
check("/pnl in the group is ignored", r.out.length === 0);
// expiry + not taken
await gh("/state", "POST", { patch: { signals_sent: [SIG(3, "SELL", { valid_until: "2026-11-20T13:31:00+03:30" }), SIG(4)] }, done_cmds: [] });
r = await cb("c:n:S-20261120-004");
check("«وارد نشدم» → not_taken, lock released", TBL.signals.find((x) => x.id === "S-20261120-004").status === "not_taken" && st().signals_done.includes("S-20261120-004"));
check("effectiveStatus: sent past valid_until shows expired", JR.effectiveStatus(TBL.signals.find((x) => x.id === "S-20261120-003"), CLOCK.getTime()) === "expired");
// reports (pg_cron → /report with the webhook secret)
const rep = (kind, key = DB.vault.tg_webhook_secret) => { SENT.length = 0; return app(new Request(FN + "/report", { method: "POST", headers: { "x-report-key": key }, body: JSON.stringify({ kind }) }), jw); };
let rr = await rep("daily", "wrong");
check("/report with a wrong key → 403, nothing sent", rr.status === 403 && SENT.length === 0);
CLOCK = new Date("2026-11-20T21:15:00Z");   // Saturday 00:45 Tehran → reports Friday's session
rr = await (await rep("daily")).json();
check("daily report after 00:30: Friday session, private chat only, counts + net + expired marked",
  rr.ok && rr.key === "daily:2026-11-20" && SENT.length === 1 && String(SENT[0].chat_id) === "45639251" && SENT[0].text.includes("گزارش روز") &&
  SENT[0].text.includes("تومان") && TBL.signals.find((x) => x.id === "S-20261120-003").status === "expired");
rr = await (await rep("daily")).json();
check("daily report is sent once per day", rr.skipped && SENT.length === 0);
CLOCK = new Date("2026-11-21T06:30:00Z");   // Saturday 10:00 Tehran
rr = await (await rep("weekly")).json();
check("weekly report Saturday: Sat–Fri range ending Friday, private only", rr.key === "weekly:2026-11-20" && SENT.length === 1 && String(SENT[0].chat_id) === "45639251" && SENT[0].text.includes("گزارش هفته"));
const gtxt = JR.reportMsg("daily", { signals: TBL.signals, journal: TBL.journal, shadow: [], calibration: null }, "2026-11-20", "2026-11-20", CLOCK.getTime(), true);
check("group version of a report carries no toman/balance", !gtxt.includes("تومان") && !gtxt.includes("موجودی") && gtxt.includes("R"));
const allTxt = [JR.BAD_JOURNAL, gtxt, SENT[0].text, JR.journalMsg(TBL.journal), JR.pnlMsg(TBL.journal)].join("\n");
check("Phase 3 texts: Persian, «ضرر» not «زیان», never «قوی»", !allTxt.includes("زیان") && !/(^|[\s،.])قوی([\s،.]|$)/.test(allTxt));
TBL_FAIL = true; r = await tgSend("/journal"); TBL_FAIL = false;
check("journal database down → short error to the owner", r.out.length === 1 && r.out[0].includes("ثبت نشد"));
o = await (await gh("/admin/setup", "POST", { set_webhook: true })).json();
check("setup: webhook also receives button presses (callback_query)", DB.hook.allowed_updates.includes("callback_query") && DB.hook.allowed_updates.includes("message"));

// ---------------- Phase 4: forward tracking (MFE/MAE) + /trade double-count guard ----------------
CLOCK = new Date("2026-11-23T10:00:00Z");   // Monday 13:30 Tehran
TBL.signals.length = 0; TBL.journal.length = 0;
const S5 = { ...SIG(5), id: "S-20261123-005", session_date: "2026-11-23", sent_at: "2026-11-23T13:00:00+03:30", valid_until: "2026-11-23T13:30:00+03:30" };
const fresh = { outcome: "tp", fill_at: "2026-11-23T09:31:00+00:00", mfe_usd: 4.1, mae_usd: 0.6, mfe_r: 2.56, mae_r: 0.38, tracked_at: "2026-11-23T09:59:00+00:00", final: true };
sr = await (await gh("/state", "POST", { patch: { signals_sent: [S5, { ...SIG(6), id: "S-20261123-006", session_date: "2026-11-23",
  track: { ...fresh, tracked_at: "2026-11-23T08:00:00+00:00" } }] }, done_cmds: [] })).json();
sr = await (await gh("/state", "POST", { patch: { signals_sent: [{ ...S5, track: fresh }, { ...SIG(6), id: "S-20261123-006", session_date: "2026-11-23",
  track: { ...fresh, outcome: "sl", tracked_at: "2026-11-23T08:00:00+00:00" } }] }, done_cmds: [] })).json();
const t5 = TBL.signals.find((x) => x.id === "S-20261123-005"), t6 = TBL.signals.find((x) => x.id === "S-20261123-006");
check("tracking: fresh MFE/MAE written to the signal row; stale tracking (older than 30 min) not rewritten",
  sr.signals_tracked === 1 && t5.track_outcome === "tp" && t5.mfe_r === 2.56 && t5.mae_r === 0.38 && t5.mfe_usd === 4.1 && !t6.track_outcome);
sr = await (await gh("/state", "POST", { patch: { signals_sent: [{ ...S5, id: "S-1;x", track: fresh }, { ...S5, track: { ...fresh, outcome: "drop table" } }] }, done_cmds: [] })).json();
check("tracking: bad IDs / unknown outcomes ignored", !sr.signals_tracked);
r = await tgSend("/journal");
check("/journal shows signal tracking (outcome, best/worst in R)", r.out[0].includes("پیگیری سیگنال") && r.out[0].includes("<code>S-20261123-005</code>") &&
  r.out[0].includes("به هدف رسید") && r.out[0].includes("+۲٫۵۶R") && (r.out[0].includes("−۰٫۳۸R") || r.out[0].includes("-۰٫۳۸R")));
const wk = JR.reportMsg("weekly", { signals: TBL.signals, journal: [], shadow: [], calibration: null }, "2026-11-23", "2026-11-23", CLOCK.getTime());
check("weekly report includes the tracking line (TP/SL/no-fill and average MFE/MAE)", wk.includes("پیگیری سیگنال") && wk.includes("هدف 1") && wk.includes("+2.56R"));
// /trade guard
const eqT = Number(st().equity_toman), nJ = TBL.journal.length;
r = await tgSend("/trade sell 3880.0 3876.5 1");
check("/trade that matches an open signal → question card (same signal / separate / cancel), nothing recorded yet",
  r.out.length === 1 && r.out[0].includes("همان سیگنال") && SENT[0].reply_markup.inline_keyboard[0][0].callback_data === "c:j:S-20261123-005:3880:3876.5:1" &&
  SENT[0].reply_markup.inline_keyboard[1][0].callback_data === "tr:sell:3880:3876.5:1" && TBL.journal.length === nJ && Number(st().equity_toman) === eqT);
r = await cb("c:j:S-20261123-005:3880:3876.5:1");
const jl = TBL.journal.find((x) => x.trade_id === "S-20261123-005");
check("«همان سیگنال» → one journal row from the signal with the owner's fills (no extra spread): 3.5×80k − 14k = 266,000",
  jl && jl.net_toman === 266000 && jl.spread_toman === 0 && jl.entry === 3880 && TBL.signals.find((x) => x.id === "S-20261123-005").status === "closed" &&
  Number(st().equity_toman) === eqT + 266000 && TBL.journal.filter((x) => x.source === "trade_cmd").length === 0);
r = await tgSend("/trade buy 3880.0 3882.5 0.5");
check("/trade with no matching open signal is recorded directly", r.out[0].includes("معامله ثبت شد") && TBL.journal.some((x) => x.source === "trade_cmd" && x.unit === "0.5U"));
await gh("/state", "POST", { patch: { signals_sent: [{ ...SIG(7), id: "S-20261123-007", session_date: "2026-11-23" }] }, done_cmds: [] });
r = await tgSend("/trade sell 3880.5 3879 1");
r = await cb("tr:sell:3880.5:3879:1");
check("«معامله‌ی جدا» → recorded as its own trade; the signal stays open", r.out[0].includes("معامله ثبت شد") &&
  TBL.journal.some((x) => x.source === "trade_cmd" && x.entry === 3880.5) && TBL.signals.find((x) => x.id === "S-20261123-007").status === "sent");
check("parseCallback rejects malformed link/trade buttons", JR.parseCallback("c:j:S-20261123-005:1:2:1") === null && JR.parseCallback("tr:hold:3880:3879:1") === null &&
  JR.parseCallback("tr:sell:3880:3879:2") === null);
console.log(`\n${fails} failed`); process.exit(fails ? 1 : 0);
