// m5-gold-bot Edge Function: Telegram webhook + state API for the GitHub runner.
//   POST .../tg            Telegram webhook (X-Telegram-Bot-Api-Secret-Token checked against Vault; only CHAT_ID)
//   GET|POST .../state     GitHub Actions only (OIDC JWT: this repo, main branch)
//   POST .../admin/setup   GitHub Actions only: store secrets in Vault, set webhook, announce once
//   GET .../health
// /calibrate: owner-entered DaryaGold price + live Dukascopy 1-minute bid/ask -> public.price_observations (service role only).
// State: one row in public.bot_state (jsonb), optimistic versioning; secrets: Supabase Vault via RPC (service_role).
import { CAL, CAL_HELP, STATUS_FA, basisStats, basisStatus, parseDuka, pickFeed, sessionOf, statsLines } from "./calib.js";
import { sessionDate, offsetOf, CHAT_ID, teh, normalize, handle, send, tg, dispatch, verifyOidc, ANNOUNCE, HELP, menuCalls, MENU_VERSION, weekendClosed, closedLine, channelChat, publicReply, MIRROR_CMDS, GROUP_CMDS, GROUP_COOLDOWN_MS, forexOpen } from "./lib.js";
import * as A from "./assist.js";

export const BUILD = "2026-11-21-assistant-v3";
const DUKA = (side, ts) => "https://freeserv.dukascopy.com/2.0/index.php?path=chart%2Fjson3&instrument=XAU%2FUSD" +
  `&offer_side=${side}&interval=1MIN&splits=true&stocks=true&limit=30&time_direction=N&timestamp=${ts}&jsonp=_cb`;
const r2 = (x) => Math.round(x * 100) / 100;
const sgn = (x) => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(r2(x));
export function makeApp(cfg) {
  const { url: SB, key: KEY } = cfg;   // SUPABASE_URL, service-role key
  const clock = cfg.clock || (() => new Date());   // injectable for tests (market hours)
  const MIRROR = MIRROR_CMDS, GROUPS = GROUP_CMDS;
  const hdr = { apikey: KEY, authorization: `Bearer ${KEY}`, "content-type": "application/json" };
  const rpc = async (fn, args = {}) => {
    const r = await fetch(`${SB}/rest/v1/rpc/${fn}`, { method: "POST", headers: hdr, body: JSON.stringify(args) });
    if (!r.ok) throw new Error(`rpc ${fn} ${r.status}`);
    const t = await r.text();   // void functions answer 204 with no body
    return t ? JSON.parse(t) : null;
  };
  const loadRow = async () => {
    const r = await fetch(`${SB}/rest/v1/bot_state?id=eq.1&select=state,news,version`, { headers: hdr });
    if (!r.ok) throw new Error(`load ${r.status}`);
    const [row] = await r.json();
    return row;
  };
  let SEC = null, SEC_AT = 0;   // warm-instance cache (5 min)
  const secrets = async () => {
    if (!SEC || Date.now() - SEC_AT > 300000) {
      const [t, g, w] = await Promise.all([rpc("bot_secret", { p_name: "telegram_bot_token" }),
        rpc("bot_secret", { p_name: "gh_dispatch_token" }), rpc("bot_webhook_secret")]);
      SEC = { TELEGRAM_BOT_TOKEN: t, GH_DISPATCH_TOKEN: g, WEBHOOK: w }; SEC_AT = Date.now();
    }
    return SEC;
  };
  // read-modify-write with optimistic concurrency (GitHub merges can land between read and write)
  const mutate = async (fn) => {
    for (let i = 0; i < 4; i++) {
      const row = await loadRow();
      const s = normalize(row.state);
      const out = await fn(s);
      if (out === null) return null;
      s.updated_at_tehran = teh().full;
      if (await rpc("bot_save", { p_state: s, p_version: row.version })) return out;
    }
    throw new Error("state busy");
  };

  async function feedNow(nowMs) {
    try {
      const ts = nowMs - (nowMs % 60000) - 20 * 60000;
      const [b, a] = await Promise.all(["B", "A"].map((side) => fetch(DUKA(side, ts), {
        headers: { "user-agent": "Mozilla/5.0", referer: "https://freeserv.dukascopy.com/" },
        signal: AbortSignal.timeout(8000) }).then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))));
      return pickFeed(parseDuka(b), parseDuka(a), nowMs);
    } catch { return null; }
  }
  async function onCalibrate(c) {
    const now = clock(), nowMs = now.getTime(), t = teh(now);
    const s0 = normalize((await loadRow()).state);
    const cur = offsetOf(s0);
    const L = [];
    if (c.show) L.push(CAL_HELP, "");
    else {
      const f = await feedNow(nowMs);
      const ok = !!f && f.age_s <= CAL.MAX_FEED_AGE_S;
      const basis = ok ? r2(c.price - f.feed_bid) : null;
      const status = basisStatus(basis, cur, ok);
      const r = await fetch(`${SB}/rest/v1/price_observations`, { method: "POST", headers: { ...hdr, prefer: "return=minimal" },
        body: JSON.stringify({ observed_at: now.toISOString(), source: "telegram_calibrate", darya_price: c.price, darya_ask: c.ask,
          reference: "dukascopy_bid", feed_bid: f ? f.feed_bid : null, feed_ask: f ? f.feed_ask : null, feed_ref: f ? f.feed_bid : null,
          feed_bar_at: f ? f.bar_at : null, feed_age_s: f ? f.age_s : null, basis_usd: basis, session: sessionOf(t.hm), status }) });
      if (!r.ok) throw new Error(`insert ${r.status}`);
      L.push("**🎯 قیمت دریاگلد ثبت شد**", `~~${t.hm} · دریاگلد \`${c.price}\`` + (ok ? ` · مرجع \`${f.feed_bid}\`` : "") + "~~", "");
      L.push(ok ? `اختلاف ${sgn(basis)} دلار · ${STATUS_FA[status]}` : `${STATUS_FA[status]}؛ این نمونه در محاسبه حساب نمی‌شود`);
    }
    const since = new Date(nowMs - CAL.WINDOW_DAYS * 86400000).toISOString();
    const q = await fetch(`${SB}/rest/v1/price_observations?select=observed_at,basis_usd,reference,session,status&observed_at=gte.${encodeURIComponent(since)}&order=observed_at.asc`, { headers: hdr });
    if (!q.ok) throw new Error(`select ${q.status}`);
    const st = basisStats(await q.json(), nowMs);
    let after = cur;
    await mutate(async (s) => {
      if (st.calibrated) { s.dg_offset = st.offset; s.dg_offset_source = "calibrate"; s.dg_offset_at = t.full; }
      else if (s.dg_offset_source === "calibrate") { s.dg_offset = null; s.dg_offset_source = null; s.dg_offset_at = t.full; }
      s.calibration = { status: st.calibrated ? "calibrated" : "not_calibrated", count: st.count, median: st.median, std: st.std,
        offset: st.offset, at: t.full };
      after = offsetOf(s);
      return true;
    });
    if (!c.show) L.push("");
    L.push(...statsLines(st, after));
    return L.join("\n");
  }

  // ---------------- REST helper; signals table = archive of the old automatic signals (written by the GitHub run) ----------------
  const rest = async (path, { method = "GET", body, prefer } = {}) => {
    const r = await fetch(`${SB}/rest/v1/${path}`, { method, headers: { ...hdr, ...(prefer ? { prefer } : {}) },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    if (!r.ok) throw new Error(`rest ${path.split("?")[0]} ${method} ${r.status}`);
    const t = await r.text();
    return t ? JSON.parse(t) : null;
  };
  const TRACK_OUT = ["no_fill", "open", "tp", "sl", "close"];
  const SIG_FIELDS = ["id", "sent_at", "session_date", "side", "unit", "entry", "sl", "tp", "valid_until", "net_rr", "risk_toman"];
  async function storeSignals(list) {
    const rows = (list || []).filter((x) => x && /^S-\d{8}-\d{3}$/.test(x.id || "") && ["BUY", "SELL"].includes(x.side) && ["1U", "0.5U"].includes(x.unit))
      .map((x) => Object.fromEntries(SIG_FIELDS.map((k) => [k, x[k] ?? null])));
    if (!rows.length) return 0;
    await rest("signals?on_conflict=id", { method: "POST", body: rows, prefer: "resolution=ignore-duplicates,return=minimal" });
    return rows.length;
  }
  // Phase 4: forward MFE/MAE of each signal (computed by the GitHub run from 1-minute data). Only fresh updates are written.
  async function storeTracking(list, nowMs) {
    let n = 0;
    for (const x of list || []) {
      const tr = x && x.track;
      if (!tr || !/^S-\d{8}-\d{3}$/.test(x.id || "") || !TRACK_OUT.includes(tr.outcome)) continue;
      const at = Date.parse(tr.tracked_at || "");
      if (!(at > nowMs - 30 * 60000)) continue;   // unchanged since an earlier run
      const num = (v) => (v === null || v === undefined || !Number.isFinite(Number(v)) ? null : Number(v));
      await rest(`signals?id=eq.${encodeURIComponent(x.id)}`, { method: "PATCH", prefer: "return=minimal",
        body: { track_outcome: tr.outcome, track_fill_at: tr.fill_at || null, mfe_usd: num(tr.mfe_usd), mae_usd: num(tr.mae_usd),
          mfe_r: num(tr.mfe_r), mae_r: num(tr.mae_r), tracked_at: new Date(at).toISOString() } });
      n++;
    }
    return n;
  }
  async function onCallback(env, u) {   // the bot sends no buttons any more; an old button just gets an empty answer
    await tg(env, "answerCallbackQuery", { callback_query_id: u.callback_query.id });
    return new Response("ok");
  }
  // ---------------- assistant: /setup /trend /e (owner t226u-t232u) ----------------
  const BAD_E = "**⚠️ ورود را بنویسید**\n~~جهت اختیاری است و قیمت با نقطه، مثل:~~\n\n`/e sell 3531.80`\n`/e 3531.80`";
  const NO_DIR = "**⚠️ جهت را بنویسید**\n~~روند فعلاً روشن نیست، مثل:~~ `/e sell 3531.80`";
  const NO_FEED = "**⚠️ قیمت زنده در دسترس نیست**\n~~ستاپ بدون قیمت لحظه‌ای چیده نمی‌شود؛ چند دقیقه‌ی دیگر دوباره بفرستید~~";
  async function marketNow(nowMs, opts) {
    try { return await A.fetchMarket(nowMs, opts); } catch (e) { console.error("feed:", String(e && e.message || e)); return null; }
  }
  async function logSetups(list, q, v, origin, nowMs, trend) {
    const stamp = new Date(nowMs + 210 * 60000).toISOString().replace(/\D/g, "").slice(0, 14);
    const tag = Math.random().toString(36).slice(2, 6);   // two requests in the same second never collide
    const rows = list.map((c, i) => ({ id: `U-${stamp}-${origin[0]}${c.side[0]}${i + 1}-${tag}`, created_at: new Date(nowMs).toISOString(), origin, side: c.side,
      rank: c.rank, entry_lo: c.lo, entry_hi: c.hi, better_half: c.half, sl: c.sl, tp1: c.tp1, tp2: c.tp2, score: c.score, factors: c.factors,
      reason: c.reason, price_at: q.dg, dg_bid_offset: q.bidOff, spread: q.spread, level_price: c.level.price,
      valid_until: new Date(v.untilMs).toISOString(), invalid_price: c.invalid, trend }));
    if (!rows.length) return 0;
    await rest("setups?on_conflict=id", { method: "POST", body: rows, prefer: "resolution=ignore-duplicates,return=minimal" });
    return rows.length;
  }
  async function onAssist(a, { group }) {
    const now = clock(), nowMs = now.getTime(), open = forexOpen(now);
    if (a.kind === "setup" && !open) return closedLine(now);
    let ent = null;
    if (a.kind === "e") {
      if (group) return null;
      try { ent = A.parseEntry(a.args || []); } catch { return BAD_E; }
    }
    const row = await loadRow(), s = normalize(row.state), snap = s.levels || null;
    const mkt = await marketNow(nowMs);
    const q = mkt ? A.quoteOf(mkt, A.midOffsetOf(s)) : null;
    const live = mkt ? A.trendsOf(mkt, "live") : null;
    const snapTrend = snap && snap.trend ? Object.fromEntries(A.TFS.map((tf) => [tf, (snap.trend[tf] || {}).trend || "خنثی"])) : null;
    const trend = live || snapTrend;
    const closedTail = open ? "" : "\n\n" + closedLine(now);
    if (a.kind === "trend") {
      if (!trend) return "**⚠️ داده‌ی قیمت در دسترس نیست**\n~~چند دقیقه‌ی دیگر دوباره بفرستید~~";
      return A.trendMsg(trend, { quote: q, dataAt: live ? q.barAt : A.tehMs(snap.computed_at_tehran), at: nowMs, stale: !live }) + closedTail;
    }
    const levels = A.snapLevels(snap);
    if (!levels.length) return "**⚠️ داده‌ی سطوح در دسترس نیست**\n~~بعد از بررسی خودکار بعدی دوباره بفرستید~~";
    const age = A.snapAgeMin(snap, nowMs);
    const snapNote = age !== null && age > 30 ? `سطوح مربوط به ساعت ${String(snap.computed_at_tehran).slice(11, 16)} است` : null;
    const m5 = mkt ? A.withLive(mkt.native.M5, mkt.m1B, A.TF_MS.M5).closed : [];
    const atr5 = m5.length > 20 ? A.atrSeries(m5).at(-1) : (Number(snap.atr_m5) || 8);
    const adrUsed = Number(snap.adr_used_pct);
    if (a.kind === "e") {
      const d = ent.dir ? { dir: ent.dir, why: null } : (trend ? A.directionFrom(trend) : null);
      if (!d) return NO_DIR;
      const plan = A.planEntry({ levels, atr5 }, d.dir, ent.price);
      return A.entryMsg(plan, { quote: q, nowMs, dirWhy: d.why }) + (snapNote ? `\n~~${snapNote}~~` : "") + closedTail;
    }
    // /setup
    if (!q || !live) return NO_FEED;
    if (q.ageS > 600) return "**⚠️ داده‌ی قیمت عقب است**\n~~آخرین قیمت بیش از ۱۰ دقیقه پیش است؛ ستاپ چیده نمی‌شود~~";
    const ctx = { levels, quote: q, atr5, trend, adrUsed: Number.isFinite(adrUsed) ? adrUsed : NaN, nowMs, news: row.news };
    const v = A.validity(ctx);
    const ns = A.noSetupMsg(v, nowMs);
    if (ns) return ns;
    const res = A.buildSetups(ctx);
    const list = [...res.SELL.map((c, i) => ({ ...c, rank: i + 1 })), ...res.BUY.map((c, i) => ({ ...c, rank: i + 1 }))];
    try { await logSetups(list, q, v, group ? "group" : "owner", nowMs, trend); }
    catch (e) { console.error("setups log:", String(e && e.message || e)); }   // silent calibration log; never blocks the answer
    return A.setupMsg(res, ctx, v, { group, snapNote });
  }

  // Telegram menus: owner chat = full list, groups/default = the 4 member commands. Re-applied once per MENU_VERSION.
  async function syncMenus(env) {
    let ok = true;
    for (const [m, b] of menuCalls()) {
      const r = await tg(env, m, b);
      if (m === "setMyCommands" && !(r && r.ok)) ok = false;
    }
    return ok;
  }

  // ---------------- /tick: pg_cron every 2 min (Mon-Fri). Alerts go to the owner's private chat only. ----------------
  async function onTick(req) {
    const env = await secrets();
    if (!env.WEBHOOK || (req.headers.get("x-report-key") || "") !== env.WEBHOOK) return new Response("forbidden", { status: 403 });
    const now = clock(), nowMs = now.getTime(), open = forexOpen(now), out = { ok: true, sent: 0, setups: 0 };
    try {   // menus follow the code: applied on the first tick after a deploy that changes MENU_VERSION
      const s0 = normalize((await loadRow()).state);
      if (s0.menu_version !== MENU_VERSION && await syncMenus(env)) {
        await mutate(async (x) => { x.menu_version = MENU_VERSION; return true; });
        out.menus = MENU_VERSION;
      }
    } catch (e) { console.error("menus:", String(e && e.message || e)); }
    let pend = [];
    try {
      pend = await rest(`setups?status=in.(pending,filled)&created_at=gte.${encodeURIComponent(new Date(nowMs - 8 * 3.6e6).toISOString())}&select=*&order=created_at.asc&limit=50`);
    } catch (e) { out.setups_error = true; console.error("setups read:", String(e && e.message || e)); }
    if (!open && !pend.length) return Response.json({ ...out, skipped: "closed" });
    const mkt = await marketNow(nowMs, { tfs: open ? A.TFS : [] });
    if (!mkt) return Response.json({ ...out, feed: false });
    for (const r of pend) {
      const u = A.resolveSetup(r, mkt.m1B, nowMs);
      if (u.status === r.status && !!u.tp1_hit === !!r.tp1_hit && Number(u.mfe_usd) === Number(r.mfe_usd) && Number(u.mae_usd) === Number(r.mae_usd)) continue;
      try { await rest(`setups?id=eq.${encodeURIComponent(r.id)}`, { method: "PATCH", body: u, prefer: "return=minimal" }); out.setups++; }
      catch (e) { console.error("setups update:", String(e && e.message || e)); }
    }
    if (!open) return Response.json(out);
    const row = await loadRow(), s = normalize(row.state), st = { ...(s.assist || {}) };
    const q = A.quoteOf(mkt, A.midOffsetOf(s)), msgs = [], sent = { ...(st.sent || {}) };
    // 1) level touch: once per level per trading day, at most one batch per 10 min
    const snap = s.levels, day = sessionDate(teh(now)), age = A.snapAgeMin(snap, nowMs);
    if (snap && age !== null && age < 60 && !(nowMs - (Number(st.level_alert_ms) || 0) < 10 * 60000)) {
      const since = Math.max(Number(st.tick_ms) || 0, nowMs - 10 * 60000) - 60000, o = q.bidOff;
      const bars = mkt.m1B.filter((b) => b[0] >= since).map((b) => [b[0], b[1] + o, b[2] + o, b[3] + o, b[4] + o]);
      const la = A.levelAlerts(A.snapLevels(snap), bars, { day, sent, snapAtMs: A.tehMs(snap.computed_at_tehran) });
      for (const x of la) { msgs.push(x.text); sent[x.key] = nowMs; }
      if (la.length) st.level_alert_ms = nowMs;
    }
    // 2) M15 / H1 trend change on completed bars, once per change
    const ct = A.trendsOf(mkt, "closed"), cur = { M15: ct.M15, H1: ct.H1 };
    msgs.push(...A.trendAlerts(st.trend, cur, A.trendSummary(ct), nowMs));
    st.trend = cur;
    // 3) volatility: entering "too volatile" / "too quiet", each at most once an hour
    const v = A.volState(A.withLive(mkt.native.M5, mkt.m1B, A.TF_MS.M5).closed, nowMs);
    if (v) {
      const va = { ...(st.vol_alert || {}) };
      if (v.state !== (st.vol || {}).state && v.state !== "normal" && nowMs - (Number(va[v.state]) || 0) > 3.6e6) {
        msgs.push(A.volAlert(v, nowMs)); va[v.state] = nowMs; st.vol_alert = va;
      }
      st.vol = { state: v.state, at: nowMs };
    }
    // 4) major news a few minutes ahead
    for (const n of A.newsAlerts(row.news, nowMs, sent)) { msgs.push(n.text); for (const k of n.keys) sent[k] = nowMs; }
    st.sent = Object.fromEntries(Object.entries(sent).filter(([, t]) => nowMs - Number(t) < 3 * 864e5));
    st.tick_ms = nowMs;
    await mutate(async (x) => { x.assist = { ...(x.assist || {}), ...st }; return true; });   // dedup first: a retry never repeats
    for (const m of msgs) { try { if (await send(env, m)) out.sent++; } catch { /* next alert */ } }
    return Response.json(out);
  }

  async function onTelegram(req) {
    const env = await secrets();
    if (!env.TELEGRAM_BOT_TOKEN || (req.headers.get("x-telegram-bot-api-secret-token") || "") !== env.WEBHOOK)
      return new Response("forbidden", { status: 403 });
    const u = await req.json();
    if (u.channel_post || u.edited_channel_post) return new Response("ok");
    if (u.callback_query) return await onCallback(env, u);
    const m = u.message || {};
    const chat = m.chat || {};
    const text = (m.text || "").trim();
    // Groups: only the BAROBAX group (bot_state.channel_id), only GROUP_CMDS, any member, read-only, cooldown per command.
    if (["group", "supergroup"].includes(chat.type)) return await onGroup(env, u, chat, text);
    // Everything else: commands only from the owner's private chat. Never reply anywhere else.
    if (chat.type === "channel") return new Response("ok");
    if (String(chat.id || "") !== CHAT_ID || !text.startsWith("/")) return new Response("ok");
    const res = await mutate(async (s) => {
      if ((s.seen_updates || []).includes(u.update_id)) return null;   // Telegram retry
      s.seen_updates = [...(s.seen_updates || []), u.update_id].slice(-50);
      const r = handle(s, text, teh(), clock());
      if (r.assist) return r;
      if (r.queue) {
        // a different command always gets its own run (a run already in progress may have pulled the state
        // before it was queued); only a repeat of a command that is still pending and was dispatched < 90 s ago is skipped
        // a pending group request answers only the group, so the owner always gets an item of their own
        const already = s.pending_cmds.some((x) => x.cmd === r.queue && x.origin !== "group");
        if (!already) s.pending_cmds.push({ id: u.update_id, cmd: r.queue, at: teh().full });
        r.recent = already && !!s.last_dispatch && Date.now() - s.last_dispatch < 90000;
        if (!r.recent) s.last_dispatch = Date.now();
      } else {
        r.mirror = channelChat(s);
      }
      return r;
    });
    if (!res) return new Response("ok");
    if (res.assist) {   // /setup /trend /e: live price at command time; owner's private chat only, never mirrored
      let msg;
      try { msg = await onAssist(res.assist, { group: false }); }
      catch (e) { console.error("assist:", String(e && e.message || e)); msg = "**⚠️ جواب آماده نشد**\n~~چند دقیقه‌ی دیگر دوباره بفرستید~~"; }
      if (msg) await send(env, msg);
      return new Response("ok");
    }
    if (res.calibrate) {
      let msg;
      try { msg = await onCalibrate(res.calibrate); }
      catch (e) { console.error("calibrate:", String(e && e.message || e)); msg = "**⚠️ ثبت نشد**\n~~ذخیره‌ی قیمت ممکن نشد؛ چند دقیقه‌ی دیگر دوباره بفرستید~~"; }
      await send(env, msg);   // owner's private chat only; never mirrored to the group
      return new Response("ok");
    }
    if (res.queue) {
      const d = res.recent ? { ok: true } : await dispatch(env, "command");
      await send(env, d.ok ? "**⏳ در حال بررسی…**\n~~جواب حدود یک دقیقه‌ی دیگر می‌رسد~~"
                           : "**⏳ در صف بررسی**\n~~جواب با بررسی خودکار بعدی می‌رسد~~");
      if (!d.ok) await mutate(async (s) => { s.last_dispatch = 0; s.last_dispatch_error = d.why; return true; });
    } else {
      await send(env, res.reply);
      const cmd = text.split(/\s+/)[0].split("@")[0].toLowerCase();
      const pub = (MIRROR.includes(cmd) && res.mirror) ? publicReply(cmd, res.reply) : null;
      if (pub) {
        try { await send(env, pub, res.mirror); } catch { /* a group failure must never break the owner's reply */ }
      }
    }
    return new Response("ok");
  }

  let BOT_USER = null;   // warm-instance cache of the bot's @username (for /levels@Name in groups)
  async function botUsername(env) {
    if (BOT_USER == null) {
      const r = await tg(env, "getMe", {});
      BOT_USER = String((r && r.ok && r.result && r.result.username) || "");
    }
    return BOT_USER;
  }

  // Group members (BAROBAX) may run GROUP_CMDS only. Replies are the group variants (publicReply / public_card):
  // no toman, no balance, no buttons. One answer per command per GROUP_COOLDOWN_MS; repeats are ignored silently.
  async function onGroup(env, u, chat, text) {
    const ok = new Response("ok");
    const head = text.split(/\s+/)[0] || "";
    if (!head.startsWith("/")) return ok;
    const [raw, at] = head.split("@");
    const cmd = GROUPS[raw.toLowerCase()];
    if (!cmd) return ok;
    if (at && at.toLowerCase() !== (await botUsername(env)).toLowerCase()) return ok;   // addressed to another bot
    const nowMs = clock().getTime();
    const res = await mutate(async (s) => {
      if (!channelChat(s) || String(chat.id) !== channelChat(s)) return null;   // other groups, or /groupoff
      if ((s.seen_updates || []).includes(u.update_id)) return null;
      s.seen_updates = [...(s.seen_updates || []), u.update_id].slice(-50);
      s.group_cmd_at = s.group_cmd_at && typeof s.group_cmd_at === "object" ? s.group_cmd_at : {};
      if (nowMs - (Number(s.group_cmd_at[cmd]) || 0) < GROUP_COOLDOWN_MS) return null;
      s.group_cmd_at[cmd] = nowMs;
      const r = handle(s, cmd, teh(), clock());   // read-only: assist, reply or queue
      if (r.assist) return { assist: r.assist, chat: String(chat.id) };
      if (r.queue) {
        const already = s.pending_cmds.some((x) => x.cmd === r.queue);
        if (!already) s.pending_cmds.push({ id: u.update_id, cmd: r.queue, at: teh().full, origin: "group" });
        r.recent = already && !!s.last_dispatch && Date.now() - s.last_dispatch < 90000;
        if (!r.recent) s.last_dispatch = Date.now();
      }
      return { queue: r.queue, recent: r.recent, reply: r.reply, chat: String(chat.id) };
    });
    if (!res) return ok;
    if (res.assist) {   // group variant: no toman, no balance; errors are never posted to the group
      let msg = null;
      try { msg = await onAssist(res.assist, { group: true }); } catch (e) { console.error("assist group:", String(e && e.message || e)); }
      if (msg && !msg.startsWith("**⚠️")) { try { await send(env, msg, res.chat); } catch { /* never retry into the group */ } }
      return ok;
    }
    if (res.queue) {   // the GitHub run answers in the group (group variant only); no "checking" line, to keep the group quiet
      if (!res.recent) {
        const d = await dispatch(env, "command");
        if (!d.ok) await mutate(async (s) => { s.last_dispatch = 0; s.last_dispatch_error = d.why; return true; });
      }
      return ok;
    }
    const pub = publicReply(cmd, res.reply);
    if (pub) { try { await send(env, pub, res.chat); } catch { /* never retry into the group */ } }
    return ok;
  }

  async function onSetup(req, origin) {
    const b = await req.json(), out = {};
    if (b.telegram_token) { await rpc("bot_set_secret", { p_name: "telegram_bot_token", p_value: b.telegram_token }); out.telegram_token = "stored"; }
    if (b.gh_token) { await rpc("bot_set_secret", { p_name: "gh_dispatch_token", p_value: b.gh_token }); out.gh_token = "stored"; }
    SEC = null;
    const env = await secrets();
    if (b.set_webhook) {
      const hook = `${origin}/tg`;
      const r = await tg(env, "setWebhook", { url: hook, secret_token: env.WEBHOOK, allowed_updates: ["message", "callback_query"],
        drop_pending_updates: false, max_connections: 1 });
      out.webhook = !!r.ok;
      const info = (await tg(env, "getWebhookInfo", {})).result || {};
      out.webhook_url_ok = info.url === hook; out.pending_update_count = info.pending_update_count;
      out.last_error = info.last_error_message || null;
    }
    if (b.set_commands) {
      out.commands = await syncMenus(env);
    }
    if (b.send_help) out.help_sent = await send(env, HELP);
    if (b.announce) {
      const s = normalize((await loadRow()).state);
      if (!s.announced_at && out.webhook_url_ok) {
        out.announced = await send(env, ANNOUNCE);
        if (out.announced) await mutate(async (x) => { x.announced_at = teh().full; return true; });
      }
    }
    return Response.json(out);
  }

  return async function app(req, jwks) {
    const url = new URL(req.url);
    const p = url.pathname.replace(/\/+$/, "");
    // public origin of this function as Telegram/GitHub see it
    const origin = `${SB}/functions/v1/tg-bot`;
    try {
      if (p.endsWith("/tg") && req.method === "POST") return await onTelegram(req);
      if (p.endsWith("/tick") && req.method === "POST") return await onTick(req);
      if (p.endsWith("/state") || p.endsWith("/admin/setup")) {
        if (!(await verifyOidc(req, jwks))) return new Response("unauthorized", { status: 401 });
        if (p.endsWith("/admin/setup")) return await onSetup(req, origin);
        if (req.method === "GET") {
          const row = await loadRow();
          return Response.json({ state: normalize(row.state), news_windows: row.news || null });
        }
        const b = await req.json();
        const merged = await rpc("bot_merge", { p_patch: b.patch || {}, p_done: b.done_cmds || [], p_news: b.news_windows || null });
        try {
          const n = await storeSignals((b.patch || {}).signals_sent); if (merged && n) merged.signals_stored = n;
          const k = await storeTracking((b.patch || {}).signals_sent, clock().getTime()); if (merged && k) merged.signals_tracked = k;
        } catch (e) { console.error("signals:", String(e && e.message || e)); if (merged) merged.signals_error = true; }
        return Response.json(merged);
      }
      if (p.endsWith("/health")) {   // public, read-only: lets a deploy be checked without touching Telegram
        const closed = weekendClosed(clock());
        return Response.json({ ok: true, service: "m5-gold-bot", build: BUILD, tehran: teh().full, market_closed: closed,
          ...(closed ? { closed_line: closedLine(clock()) } : {}) });
      }
      return new Response("not found", { status: 404 });
    } catch (e) {
      console.error("tg-bot error:", String(e && e.message || e));
      // a 200 to Telegram avoids endless retries of one bad update; GitHub sees 500 and fails loudly
      return new Response("error", { status: p.endsWith("/tg") ? 200 : 500 });
    }
  };
}
