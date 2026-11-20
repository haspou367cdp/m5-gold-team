// m5-gold-bot Edge Function: Telegram webhook + state API for the GitHub runner.
//   POST .../tg            Telegram webhook (X-Telegram-Bot-Api-Secret-Token checked against Vault; only CHAT_ID)
//   GET|POST .../state     GitHub Actions only (OIDC JWT: this repo, main branch)
//   POST .../admin/setup   GitHub Actions only: store secrets in Vault, set webhook, announce once
//   GET .../health
// /calibrate: owner-entered DaryaGold price + live Dukascopy 1-minute bid/ask -> public.price_observations (service role only).
// State: one row in public.bot_state (jsonb), optimistic versioning; secrets: Supabase Vault via RPC (service_role).
import { CAL, CAL_HELP, STATUS_FA, basisStats, basisStatus, parseDuka, pickFeed, sessionOf, statsLines } from "./calib.js";
import { JOURNAL_CMDS, BAD_JOURNAL, parseJournalCmd, parseCallback, applyAction, previewText, confirmKeyboard, doneText, journalMsg, pnlMsg, reportMsg, effectiveStatus } from "./ledger.js";
import { sessionDate, toman, offsetOf, DEFAULT_OFFSET, CHAT_ID, teh, normalize, handle, send, tg, dispatch, verifyOidc, ANNOUNCE, HELP, COMMANDS, weekendClosed, closedLine, channelChat, publicReply, MIRROR_CMDS } from "./lib.js";

export const BUILD = "2026-11-20-phase3-journal";
const DUKA = (side, ts) => "https://freeserv.dukascopy.com/2.0/index.php?path=chart%2Fjson3&instrument=XAU%2FUSD" +
  `&offer_side=${side}&interval=1MIN&splits=true&stocks=true&limit=30&time_direction=N&timestamp=${ts}&jsonp=_cb`;
const r2 = (x) => Math.round(x * 100) / 100;
const sgn = (x) => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(r2(x));
export function makeApp(cfg) {
  const { url: SB, key: KEY } = cfg;   // SUPABASE_URL, service-role key
  const clock = cfg.clock || (() => new Date());   // injectable for tests (market hours)
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

  // ---------------- Phase 3: signals + journal (tables are service-role only) ----------------
  const rest = async (path, { method = "GET", body, prefer } = {}) => {
    const r = await fetch(`${SB}/rest/v1/${path}`, { method, headers: { ...hdr, ...(prefer ? { prefer } : {}) },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    if (!r.ok) throw new Error(`rest ${path.split("?")[0]} ${method} ${r.status}`);
    const t = await r.text();
    return t ? JSON.parse(t) : null;
  };
  const getSignal = async (id) => (await rest(`signals?id=eq.${encodeURIComponent(id)}&select=*`))[0] || null;
  const latestOpen = async () => (await rest("signals?status=in.(sent,entered)&select=*&order=sent_at.desc&limit=1"))[0] || null;
  const SIG_FIELDS = ["id", "sent_at", "session_date", "side", "unit", "entry", "sl", "tp", "valid_until", "net_rr", "risk_toman"];
  async function storeSignals(list) {
    const rows = (list || []).filter((x) => x && /^S-\d{8}-\d{3}$/.test(x.id || "") && ["BUY", "SELL"].includes(x.side) && ["1U", "0.5U"].includes(x.unit))
      .map((x) => Object.fromEntries(SIG_FIELDS.map((k) => [k, x[k] ?? null])));
    if (!rows.length) return 0;
    await rest("signals?on_conflict=id", { method: "POST", body: rows, prefer: "resolution=ignore-duplicates,return=minimal" });
    return rows.length;
  }
  const NOT_FOUND = "**⚠️ سیگنال پیدا نشد**\n~~شناسه را از پایین کارت سیگنال بردارید، مثل~~ `/tp 001`";
  // Confirmed action: guarded status update, journal row, then the day record + equity (feeds the daily stop).
  async function confirmAction(id, act, price) {
    const sig = await getSignal(id);
    if (!sig) return NOT_FOUND;
    const nowMs = clock().getTime();
    const res = applyAction(sig, act, price, nowMs);
    if (res.error) return `**⚠️ ثبت نشد**\n~~${res.error}~~`;
    const upd = await rest(`signals?id=eq.${encodeURIComponent(id)}&status=eq.${sig.status}`, { method: "PATCH",
      body: { ...res.update, updated_at: new Date(nowMs).toISOString() }, prefer: "return=representation" });
    if (!upd || !upd.length) return "**⚠️ قبلاً ثبت شده**\n~~وضعیت این سیگنال همین الان عوض شده بود~~";
    const L = [doneText(sig, act, res)];
    if (res.journal) {
      await rest("journal?on_conflict=trade_id", { method: "POST", body: [res.journal], prefer: "resolution=ignore-duplicates,return=minimal" });
      const now = teh(new Date(nowMs));
      const day = await mutate(async (s) => {
        const d = s.day, rec = res.record;
        d.records.push({ type: rec.type, toman: rec.toman, at: now.hm, at_full: now.full, trade: id, signal: id, net: rec.net });
        if (rec.type === "loss") { d.losses += 1; d.loss_toman += rec.toman; } else { d.wins += 1; d.win_toman += rec.toman; }
        s.equity_toman = Number(s.equity_toman) + rec.net;
        s.signals_done = [...(s.signals_done || []).filter((x) => x !== id), id].slice(-20);
        const cap = (Number(d.start_equity) || Number(s.equity_toman)) * 0.2;
        return { losses: d.losses, wins: d.wins, eq: s.equity_toman, stop: d.losses >= 3 || d.loss_toman - d.win_toman >= cap };
      });
      L.push(`موجودی جدید ${toman(day.eq)} تومان`, "", `امروز ${day.losses} ضرر · ${day.wins} سود`);
      if (day.stop) L.push("", "⛔ توقف روزانه فعال شد؛ تا فردا سیگنالی فرستاده نمی‌شود");
    } else if (act === "n") {
      await mutate(async (s) => { s.signals_done = [...(s.signals_done || []).filter((x) => x !== id), id].slice(-20); return true; });
    }
    return L.join("\n");
  }
  async function askConfirm(env, act, id, price) {
    const sig = id ? await getSignal(id) : await latestOpen();
    if (!sig) return send(env, NOT_FOUND);
    if (act === "m" && price == null)
      return send(env, `**✋ بستن دستی** \`${sig.id}\`\n~~قیمت خروج را بفرستید:~~\n\`/closed ${sig.id.slice(-3)} 3569.85\``);
    const text = previewText(sig, act, price, clock().getTime());
    const ok = !text.startsWith("این سیگنال");
    return send(env, ok ? text : `**⚠️ ثبت نشد**\n~~${text}~~`, CHAT_ID, ok ? confirmKeyboard(act, sig.id, price) : null);
  }
  async function onJournal(env, j) {
    if (j.error) return send(env, BAD_JOURNAL);
    if (j.view === "journal") return send(env, journalMsg(await rest("journal?select=*&order=closed_at.desc&limit=10")));
    if (j.view === "pnl") return send(env, pnlMsg(await rest("journal?select=session_date,net_toman,r_multiple,under_60s&limit=10000"), teh(clock())));
    return askConfirm(env, j.act, j.id, j.price);
  }
  async function onCallback(env, u) {
    const cq = u.callback_query, msg = cq.message || {};
    const owner = String((cq.from || {}).id || "") === CHAT_ID && String((msg.chat || {}).id || "") === CHAT_ID && (msg.chat || {}).type === "private";
    const answer = (text) => tg(env, "answerCallbackQuery", { callback_query_id: cq.id, ...(text ? { text } : {}) });
    if (!owner) { await answer(); return new Response("ok"); }
    const fresh = await mutate(async (s) => {
      if ((s.seen_updates || []).includes(u.update_id)) return null;
      s.seen_updates = [...(s.seen_updates || []), u.update_id].slice(-50);
      return true;
    });
    if (!fresh) return new Response("ok");
    const c = parseCallback(cq.data);
    const strip = () => tg(env, "editMessageReplyMarkup", { chat_id: msg.chat.id, message_id: msg.message_id, reply_markup: { inline_keyboard: [] } });
    if (!c) { await answer(); return new Response("ok"); }
    if (c.cancel) { await answer("لغو شد"); await strip(); return new Response("ok"); }
    if (c.step === "a") { await answer(); await askConfirm(env, c.act, c.id, c.price); return new Response("ok"); }
    await answer("ثبت شد");
    await strip();   // a confirmation card works once
    let out;
    try { out = await confirmAction(c.id, c.act, c.price); }
    catch (e) { console.error("confirm:", String(e && e.message || e)); out = "**⚠️ ثبت نشد**\n~~ذخیره ممکن نشد؛ چند دقیقه‌ی دیگر دوباره بزنید~~"; }
    await send(env, out);
    return new Response("ok");
  }
  async function onReport(req) {
    const env = await secrets();
    if (!env.WEBHOOK || (req.headers.get("x-report-key") || "") !== env.WEBHOOK) return new Response("forbidden", { status: 403 });
    const b = await req.json().catch(() => ({}));
    const kind = b.kind === "weekly" ? "weekly" : "daily";
    const now = clock(), nowMs = now.getTime(), sd = sessionDate(teh(now));
    const shift = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);
    const to = kind === "weekly" ? shift(sd, -1) : sd, from = kind === "weekly" ? shift(to, -6) : sd;
    const key = `${kind}:${to}`;
    const first = await mutate(async (s) => {
      if ((s.reports_sent || []).includes(key)) return null;
      s.reports_sent = [...(s.reports_sent || []), key].slice(-30);
      return true;
    });
    if (!first) return Response.json({ ok: true, skipped: "already sent", key });
    await rest(`signals?status=eq.sent&valid_until=lt.${encodeURIComponent(now.toISOString())}`, { method: "PATCH",
      body: { status: "expired", updated_at: now.toISOString() }, prefer: "return=minimal" });
    const [signals, journal, row] = await Promise.all([
      rest(`signals?select=*&session_date=gte.${from}&session_date=lte.${to}`),
      rest(`journal?select=*&session_date=gte.${from}&session_date=lte.${to}`), loadRow()]);
    const s = normalize(row.state);
    const text = reportMsg(kind, { signals, journal, shadow: s.shadow, calibration: s.calibration }, from, to, nowMs, false);
    const sent = await send(env, text);   // owner's private chat only
    return Response.json({ ok: sent, key, signals: signals.length, trades: journal.length });
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
    // Commands only from the owner's private chat. Ignore groups, channels, and everyone else. Never reply there.
    if (["group", "supergroup", "channel"].includes(chat.type)) return new Response("ok");
    if (String(chat.id || "") !== CHAT_ID || !text.startsWith("/")) return new Response("ok");
    const res = await mutate(async (s) => {
      if ((s.seen_updates || []).includes(u.update_id)) return null;   // Telegram retry
      s.seen_updates = [...(s.seen_updates || []), u.update_id].slice(-50);
      const c0 = text.split(/\s+/)[0].split("@")[0].toLowerCase();
      if (JOURNAL_CMDS.includes(c0)) {
        try { return { journal: parseJournalCmd(c0, text.split(/\s+/).slice(1), teh(clock())) }; }
        catch { return { journal: { error: true } }; }
      }
      const r = handle(s, text, teh(), clock());
      if (r.queue) {
        // a different command always gets its own run (a run already in progress may have pulled the state
        // before it was queued); only a repeat of a command that is still pending and was dispatched < 90 s ago is skipped
        const already = s.pending_cmds.some((x) => x.cmd === r.queue);
        if (!already) s.pending_cmds.push({ id: u.update_id, cmd: r.queue, at: teh().full });
        r.recent = already && !!s.last_dispatch && Date.now() - s.last_dispatch < 90000;
        if (!r.recent) s.last_dispatch = Date.now();
      } else {
        r.mirror = channelChat(s);
      }
      return r;
    });
    if (!res) return new Response("ok");
    if (res.journal) {   // private chat only; never mirrored
      try { await onJournal(env, res.journal); }
      catch (e) { console.error("journal:", String(e && e.message || e)); await send(env, "**⚠️ ثبت نشد**\n~~ژورنال در دسترس نیست؛ چند دقیقه‌ی دیگر دوباره بفرستید~~"); }
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
      await send(env, d.ok ? "**⏳ در حال بررسی…**\n~~جواب تا حدود یک دقیقه‌ی دیگر~~"
                           : "**⏳ در صف بررسی**\n~~جواب در بررسی خودکار بعدی~~");
      if (!d.ok) await mutate(async (s) => { s.last_dispatch = 0; s.last_dispatch_error = d.why; return true; });
    } else {
      await send(env, res.reply);
      try {
        if (res.journal_row) await rest("journal?on_conflict=trade_id", { method: "POST", body: [res.journal_row], prefer: "resolution=ignore-duplicates,return=minimal" });
        if (res.undo) {
          await rest(`journal?trade_id=eq.${encodeURIComponent(res.undo.trade)}`, { method: "DELETE", prefer: "return=minimal" });
          if (res.undo.signal) await rest(`signals?id=eq.${encodeURIComponent(res.undo.signal)}&status=eq.closed`, { method: "PATCH", prefer: "return=minimal",
            body: { status: "entered", closed_at: null, exit_price: null, exit_type: null, net_toman: null, r_multiple: null, under_60s: null, updated_at: new Date().toISOString() } });
        }
      } catch (e) { console.error("journal sync:", String(e && e.message || e)); }
      const cmd = text.split(/\s+/)[0].split("@")[0].toLowerCase();
      const pub = (MIRROR_CMDS.includes(cmd) && res.mirror) ? publicReply(cmd, res.reply) : null;
      if (pub) {
        try { await send(env, pub, res.mirror); } catch { /* a group failure must never break the owner's reply */ }
      }
    }
    return new Response("ok");
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
      // one menu for everyone: clear narrower menus that would shadow the default one, then set it
      for (const x of [{ scope: { type: "all_private_chats" } }, { language_code: "fa" }, { scope: { type: "chat", chat_id: Number(CHAT_ID) } }])
        await tg(env, "deleteMyCommands", x);
      out.commands = !!(await tg(env, "setMyCommands", { commands: COMMANDS })).ok;
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
      if (p.endsWith("/report") && req.method === "POST") return await onReport(req);
      if (p.endsWith("/state") || p.endsWith("/admin/setup")) {
        if (!(await verifyOidc(req, jwks))) return new Response("unauthorized", { status: 401 });
        if (p.endsWith("/admin/setup")) return await onSetup(req, origin);
        if (req.method === "GET") {
          const row = await loadRow();
          return Response.json({ state: normalize(row.state), news_windows: row.news || null });
        }
        const b = await req.json();
        const merged = await rpc("bot_merge", { p_patch: b.patch || {}, p_done: b.done_cmds || [], p_news: b.news_windows || null });
        try { const n = await storeSignals((b.patch || {}).signals_sent); if (merged && n) merged.signals_stored = n; }
        catch (e) { console.error("signals:", String(e && e.message || e)); if (merged) merged.signals_error = true; }
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
