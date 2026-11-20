// Offline tests for the Edge Function (node >= 20): Telegram, GitHub, Supabase REST/RPC and JWKS are mocked.
// usage: node supabase/functions/tg-bot/test.mjs   (nothing is sent anywhere)
import { makeApp } from "./app.js";
import { CAL, basisStats, basisStatus, parseCalibrate, parseDuka, pickFeed, sessionOf, statsLines } from "./calib.js";
import { sessionDate, HELP, render, parseAmount, normalize, teh, verifyOidc, toman, tomanShort, forexOpen, weekendClosed, closedLine, levelsMsg, levelsFresh, faDate, channelChat, publicReply, groupEnabled } from "./lib.js";
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
    if (url.endsWith("/setMyCommands")) { (DB.menus = DB.menus || []).push(b); DB.menu = b.commands; return J({ ok: true }); }
    if (url.endsWith("/deleteMyCommands")) { (DB.menuDeleted = DB.menuDeleted || []).push(b); return J({ ok: true }); }
    if (url.endsWith("/setWebhook")) { DB.hook = b; return J({ ok: true }); }
    if (url.endsWith("/answerCallbackQuery")) { (DB.answers = DB.answers || []).push(b); return J({ ok: true }); }
    if (url.endsWith("/editMessageReplyMarkup")) { (DB.edits = DB.edits || []).push(b); return J({ ok: true }); }
    if (url.endsWith("/getMe")) return J({ ok: true, result: { username: "XauscalperBot" } });
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
check("setup menus: owner chat = 12 commands, groups/default = setup·trend·levels·brief; same wording as /help, no examples or digits; no removed command",
  o.commands && DB.menus.length === 3 && DB.menuDeleted.length === 2 && (() => {
    const own = DB.menus.find((m) => m.scope && m.scope.type === "chat" && m.scope.chat_id === 45639251), grp = DB.menus.find((m) => m.scope && m.scope.type === "all_group_chats"), def = DB.menus.find((m) => !m.scope);
    const names = (m) => m.commands.map((c) => c.command).join(",");
    return own && grp && def && own.commands.length === 12 && names(grp) === "setup,trend,levels,brief" && names(def) === names(grp) &&
      !own.commands.some((c) => ["scan", "signal", "trade", "journal", "shadow", "loss", "win", "undo", "pnl", "tp", "sl", "closed", "entered"].includes(c.command)) &&
      own.commands.every((c) => (c.command === "help" || (HELP.includes(`/${c.command}`) && HELP.includes(c.description))) && !/\d/.test(c.description)); })());
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
  r.out[0].includes("\u200f\u200e<code>/e sell 3531.80</code>\u200e  حد ضرر و حد سود برای یک ورود") && r.out[0].includes("۱۱:۱۵ و ۱۶:۱۵") &&
  !/زیان|۱۱:۳۰/.test(r.out[0]) && r.out[0].split("\n").every((l) => !l.trim() || l.startsWith("\u200f")));
r = await tgSend("/balance ۲٬۰۸۵٬۶۰۰"); check("/balance Persian digits", st().equity_toman === 2085600 && r.out[0].includes("۲٬۰۸۵٬۶۰۰"));
for (const bad of ["/balance", "/balance -5", "/balance nan"]) {
  const before = st().equity_toman;
  r = await tgSend(bad); check(`invalid '${bad}' rejected`, r.out[0].includes("ثبت نشد") && st().equity_toman === before);
}
raceOnce = true; r = await tgSend("/balance 2085600"); check("/balance survives a concurrent GitHub write", st().equity_toman === 2085600 && r.out.length === 1 && !r.out[0].includes("سقف ضرر"));
for (const gone of ["/trade sell 3914.07 3909.61 1", "/loss 150000", "/win 1", "/undo", "/shadow", "/entered 001", "/tp 001", "/sl 001", "/closed 001 3900", "/journal", "/pnl", "/risk"]) {
  const v = JSON.stringify([st().equity_toman, st().day, st().trades]);
  r = await tgSend(gone); check(`removed command '${gone.split(" ")[0]}' -> unknown-command hint, nothing changes`, r.out.length === 1 && r.out[0].includes("دستور ناشناخته") && JSON.stringify([st().equity_toman, st().day, st().trades]) === v);
}
r = await tgSend("/status"); check("/status card", r.out[0].includes("وضعیت") && r.out[0].includes("سیگنال خودکار: خاموش") && r.out[0].includes("<code>07:00</code>") && r.out[0].includes("<code>00:30</code>"));
r = await tgSend("/foo"); check("unknown -> hint", r.out[0].includes("/help"));
const s0 = normalize({ day: { date: "2000-01-01", losses: 3 }, equity_toman: 5 });
check("Tehran-midnight reset", s0.day.losses === 0 && s0.day.date === sessionDate(teh()) && s0.equity_toman === 5);   // trading day (00:00-07:00 belongs to the previous day)
check("Tehran clock is UTC+3:30", teh(new Date("2026-11-13T20:30:00Z")).full === "2026-11-14 00:00");
// /levels -> queue + dispatch
DISPATCHED.length = 0; r = await tgSend("/levels");
check("/levels -> instant ack + workflow dispatch", r.out[0].includes("در حال بررسی") && DISPATCHED.length === 1 && DISPATCHED[0].inputs.mode === "command");
r = await tgSend("/brief"); check("/levels then /brief within 90 s: both dispatched, both queued", DISPATCHED.length === 2 &&
  DISPATCHED[1].inputs.mode === "command" && st().pending_cmds.length === 2 && r.out[0].includes("در حال بررسی"));
r = await tgSend("/levels"); check("repeated /levels within 90 s: deduped (no new dispatch, not queued twice), still acked",
  DISPATCHED.length === 2 && st().pending_cmds.length === 2 && r.out[0].includes("در حال بررسی"));
r = await tgSend("/brief"); check("repeated /brief within 90 s: deduped", DISPATCHED.length === 2 && st().pending_cmds.length === 2);
DB.row.state.last_dispatch = Date.now() - 120000; r = await tgSend("/levels");
check("same /levels still pending after 90 s: re-dispatched, not queued twice", DISPATCHED.length === 3 && st().pending_cmds.length === 2);
const before = uid; await tgSend("/help"); uid = before;
r = await tgSend("/help"); check("Telegram retry (same update_id) ignored", r.out.length === 0); uid += 5;
// GitHub state API
const g = await (await gh("/state")).json();
check("GET /state (OIDC) returns state + news", g.state.equity_toman === 2085600 && g.news_windows && g.state.pending_cmds.length === 2);
const ids = g.state.pending_cmds.map((x) => x.id);
await gh("/state", "POST", { patch: { last_run_tehran: "2026-11-13 17:30", equity_toman: 1, day: {} }, done_cmds: ids });
check("POST /state merges bot keys only, clears done cmds", st().last_run_tehran === "2026-11-13 17:30" && st().equity_toman === 2085600 && st().pending_cmds.length === 0);
check("/state without token -> 401", (await app(new Request(FN + "/state"), jw)).status === 401);
// GitHub dispatch failure -> honest reply, retried next time
ghStatus = 403; DB.row.state.last_dispatch = 0; r = await tgSend("/brief"); ghStatus = 204;
check("dispatch failure: queued, reply says next automatic check", r.out[0].includes("در صف") && st().pending_cmds.length === 1 && st().last_dispatch === 0);
check("/help lists the assistant set, no journal or signal commands", HELP.includes("`/setup`") && HELP.includes("`/trend`") && HELP.includes("`/e sell 3531.80`") && HELP.includes("`/levels`") && !HELP.includes("/trade") && !HELP.includes("/shadow") && !HELP.includes("/scan"));
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
r = await tgSend("/brief"); check("Saturday /brief: one closed line, no dispatch, nothing queued", r.out.length === 1 && r.out[0].includes("بازار بسته است") &&
  r.out[0].includes("دوشنبه ۰۷:۰۰") && r.out[0].split("\n").length === 1 && DISPATCHED.length === 0 && st().pending_cmds.length === pend0);
r = await tgSend("/brief"); check("Saturday /brief: same closed line, no dispatch", r.out.length === 1 && r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0);
r = await tgSend("/levels"); check("Saturday /levels with no snapshot: same closed line, no dispatch", r.out.length === 1 && r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0 && (st().pending_cmds || []).every((x) => x.cmd !== "/levels"));
const LVBLOCK = "طلا  `3900.3`\nH4 نزولی  ·  H1 خنثی  ·  روند نامشخص\n\nبالا\n▸ `3910.3`  (+10.0)  مهم\n  سقف دیروز + سوئینگ H4  ·  2 تماس M15\n  پهنه  `3909.9`–`3910.7`";
DB.row.state.levels = { computed_at_tehran: "2026-11-13 17:30:00", block: LVBLOCK };
r = await tgSend("/levels");
check("Saturday /levels with stored snapshot: served with age, no dispatch", r.out.length === 1 && r.out[0].includes("به‌روزشده") && r.out[0].includes("<code>3900.3</code>") && r.out[0].includes("H4 نزولی") && !r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0);
CLOCK = U("2026-11-13T22:10:00Z"); r = await tgSend("/brief"); check("Saturday 01:40, after the 00:30 close: closed line", r.out[0].includes("بازار بسته است") && DISPATCHED.length === 0);
CLOCK = U("2026-11-13T20:15:00Z"); DB.row.state.last_dispatch = 0; r = await tgSend("/brief");
check("Friday 23:45 (entries closed, market open): /brief still analysed (bot answers «جمعه‌شب»)", DISPATCHED.length === 1 && r.out[0].includes("در حال بررسی"));
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
check("/help lists /offset, /groupoff and /groupon; no زیان or قوی", HELP.includes("`/offset`") && HELP.includes("`/groupoff`") && HELP.includes("`/groupon`") && HELP.includes("قطع موقت ارسال به گروه") && HELP.includes("وصل دوباره‌ی ارسال به گروه") && !/زیان|قوی/.test(HELP));
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
DISPATCHED.length = 0; DB.row.state.last_dispatch = 0; DB.row.state.pending_cmds = [];
r = await tgSend("/brief");
check("private /brief ack stays private", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("در حال بررسی"));
DB.row.state.pending_cmds = []; DB.row.state.last_dispatch = 0; DISPATCHED.length = 0;
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:00:00", block: LVBLOCK };
r = await tgSend("/levels");
check("stale /levels ack stays private (not mirrored)", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("در حال بررسی") && DISPATCHED.length === 1);
CLOCK = U("2026-11-14T08:00:00Z"); DISPATCHED.length = 0;
DB.row.state.levels = { computed_at_tehran: "2026-11-13 17:30:00", block: LVBLOCK };
r = await tgSend("/levels");
check("Saturday /levels snapshot is mirrored", r.out.length === 2 && r.chats[1] === GID && r.out[0].includes("به‌روزشده") && DISPATCHED.length === 0);
r = await tgSend("/brief");
check("Saturday /brief closed line is mirrored", r.out.length === 2 && r.chats[1] === GID && r.out[0] === r.out[1] && r.out[0].includes("بازار بسته است"));
DB.row.state.group_cmd_at = {};
r = await tgUpdate({ message: { chat: { id: Number(GID), type: "supergroup", title: "BAROBAX" }, from: { id: 777 }, text: "/brief" } });
check("Saturday: member /brief in the group gets the closed line in the group only", r.out.length === 1 && r.chats[0] === GID && r.out[0].includes("بازار بسته است"));
check("publicReply leaves /levels untouched and drops data errors", publicReply("/levels", "سطوح") === "سطوح" && publicReply("/setup", "داده‌ی قیمت در دسترس نیست") === null);
CLOCK = U("2026-11-11T10:30:00Z");
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:50:00", block: LVBLOCK };
failGroup = true; r = await tgSend("/levels"); failGroup = false;
check("group send failure does not block the owner's /levels", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("سطوح"));
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
// ---- group read-only commands (t189u): any member; /scan (alias /signal), /levels, /brief; 60 s cooldown; @suffix; /groupoff
CLOCK = U("2026-11-11T10:30:00Z");
DB.row.state.levels = { computed_at_tehran: "2026-11-11 13:50:00", block: LVBLOCK };
DB.row.state.group_cmd_at = {}; DB.row.state.pending_cmds = []; DB.row.state.last_dispatch = 0; DISPATCHED.length = 0;
const G = (text, from = 777, id = Number(GID)) => tgUpdate({ message: { chat: { id, type: "supergroup", title: "BAROBAX" }, from: { id: from }, text } });
r = await G("/levels");
check("member /levels in the group: group copy only, no buttons, never to the owner", r.out.length === 1 && r.chats[0] === GID && r.out[0].includes("سطوح") && !r.out[0].includes("تومان") && !SENT[0].reply_markup);
r = await G("/levels");
check("group repeat within 60 s is ignored silently", r.out.length === 0);
CLOCK = U("2026-11-11T10:31:01Z");
r = await G("/levels@XauscalperBot");
check("/levels@BotName answers after the cooldown", r.out.length === 1 && r.chats[0] === GID);
CLOCK = U("2026-11-11T10:33:00Z");
r = await G("/levels@OtherBot");
check("/levels@OtherBot is ignored", r.out.length === 0);
r = await G("/brief");
check("member /brief: group-only queued run, dispatched, no ack line in the group", r.out.length === 0 && DISPATCHED.length === 1 && st().pending_cmds.some((x) => x.cmd === "/brief" && x.origin === "group"));
r = await tgSend("/brief");
check("owner /brief while a group /brief is pending: own item + private ack", r.out.length === 1 && r.chats[0] === "45639251" && r.out[0].includes("در حال بررسی") &&
  st().pending_cmds.filter((x) => x.cmd === "/brief").length === 2 && st().pending_cmds.some((x) => x.cmd === "/brief" && !x.origin));
DUKA_DOWN = true; r = await G("/scan"); const r2s = await G("/signal"); DUKA_DOWN = false;
check("/scan and /signal are hidden aliases of /setup in the group (one cooldown; no live price -> nothing posted, no run queued)", r.out.length === 0 && r2s.out.length === 0 && DISPATCHED.length === 2 && !st().pending_cmds.some((x) => x.cmd === "/scan"));
let quiet = true;
for (const c of ["/status", "/help", "/trade sell 3900 3890 1", "/journal", "/pnl", "/calibrate 3569.8", "/groupoff", "/groupon", "/shadow", "/offset 0.5", "/entered S-20261111-001", "/undo"]) {
  const v = DB.row.version; r = await G(c, 45639251);
  quiet = quiet && r.out.length === 0 && DB.row.version === v;
}
check("every other command in the group is ignored, even from the owner (no reply, no state change)", quiet);
DB.row.state.group_cmd_at = {};
r = await G("/levels", 777, -100123456);
check("another group is ignored", r.out.length === 0);
DB.row.state.group_enabled = false;
r = await G("/levels");
check("group commands are ignored while /groupoff", r.out.length === 0);
DB.row.state.group_enabled = true; DB.row.state.pending_cmds = []; DB.row.state.group_cmd_at = {};
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

console.log(`\n${fails} failed`); process.exit(fails ? 1 : 0);
