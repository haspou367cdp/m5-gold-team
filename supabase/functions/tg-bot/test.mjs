// Offline tests for the Edge Function (node >= 20): Telegram, GitHub, Supabase REST/RPC and JWKS are mocked.
// usage: node supabase/functions/tg-bot/test.mjs   (nothing is sent anywhere)
import { makeApp } from "./app.js";
import { HELP, render, parseAmount, parseTrade, normalize, teh, verifyOidc, toman, tomanShort, shadowMsg } from "./lib.js";
let fails = 0;
const check = (n, c) => { console.log((c ? "PASS " : "FAIL ") + n); if (!c) fails++; };
const SB = "https://x.supabase.co";
const DB = { row: { state: { equity_toman: 2085600, signals_sent: [], presession_sent: { "2026-11-13-pm": true } }, news: { windows: [] }, version: 0 }, vault: { tg_webhook_secret: "W".repeat(64) } };
const SENT = [], DISPATCHED = [];
let failHtml = false, ghStatus = 204, raceOnce = false;
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
      const keys = ["signals_sent", "presession_sent", "last_run_tehran", "last_verdict", "news_fetched_at", "shadow"];
      for (const k of keys) if (k in a.p_patch) DB.row.state[k] = a.p_patch[k];
      DB.row.state.pending_cmds = (DB.row.state.pending_cmds || []).filter((x) => !a.p_done.includes(x.id));
      if (a.p_news) DB.row.news = a.p_news; DB.row.version++;
      return J({ pending: DB.row.state.pending_cmds.length });
    }
  }
  if (url.includes("api.telegram.org")) {
    const b = JSON.parse(init.body);
    if (url.endsWith("/sendMessage")) {
      if (failHtml && b.parse_mode) return J({ ok: false });
      SENT.push(b); return J({ ok: true, result: { message_id: SENT.length } });
    }
    if (url.endsWith("/setMyCommands")) { DB.menu = b.commands; return J({ ok: true }); }
    if (url.endsWith("/deleteMyCommands")) { (DB.menuDeleted = DB.menuDeleted || []).push(b); return J({ ok: true }); }
    if (url.endsWith("/setWebhook")) { DB.hook = b; return J({ ok: true }); }
    if (url.endsWith("/getWebhookInfo")) return J({ ok: true, result: { url: DB.hook && DB.hook.url, pending_update_count: 0 } });
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
const app = makeApp({ url: SB, key: "service" });
const FN = SB + "/functions/v1/tg-bot";
const gh = async (path, method = "GET", body) => app(new Request(FN + path, { method, body: body && JSON.stringify(body),
  headers: { authorization: "Bearer " + (await jwt(good)) } }), jw);
let uid = 1;
async function tgSend(text, chat = 45639251, hdr = DB.vault.tg_webhook_secret) {
  SENT.length = 0;
  const r = await app(new Request(FN + "/tg", { method: "POST", headers: { "x-telegram-bot-api-secret-token": hdr },
    body: JSON.stringify({ update_id: uid++, message: { chat: { id: chat }, text } }) }), jw);
  return { status: r.status, out: SENT.map((x) => x.text) };
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
check("setup menu: 10 commands, same wording as /help, no examples or digits", o.commands && DB.menu.length === 10 &&
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
r = await tgSend("/status"); check("/status card", r.out[0].includes("وضعیت") && r.out[0].includes("۲ ضرر") && r.out[0].includes("۱۱:۱۵ تا ۲۱:۳۰"));
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
check("/help lists /trade and /shadow", HELP.includes("/trade sell 3914.07 3909.61 1") && HELP.includes("/shadow") && HELP.includes("بررسی سیگنال"));
// HTML fallback
failHtml = true; r = await tgSend("/help"); failHtml = false;
check("HTML failure -> plain-text fallback", r.out.length === 1 && !r.out[0].includes("<b>"));
// OIDC
const req = async (c) => new Request(FN + "/state", { headers: { authorization: "Bearer " + (await jwt(c)) } });
for (const [n, c] of [["other repo", { repository: "evil/x" }], ["other branch", { ref: "refs/heads/dev" }], ["wrong audience", { aud: "x" }], ["expired", { exp: 1 }]])
  check(`OIDC: ${n} rejected`, !(await verifyOidc(await req({ ...good, ...c }), jw)));
const t = await jwt(good);
check("OIDC: tampered payload rejected", !(await verifyOidc(new Request("https://x", { headers: { authorization: "Bearer " + t.split(".")[0] + "." + enc({ ...good, x: 1 }) + "." + t.split(".")[2] } }), jw)));
console.log(`\n${fails} failed`); process.exit(fails ? 1 : 0);
