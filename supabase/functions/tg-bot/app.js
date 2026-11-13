// m5-gold-bot Edge Function: Telegram webhook + state API for the GitHub runner.
//   POST .../tg            Telegram webhook (X-Telegram-Bot-Api-Secret-Token checked against Vault; only CHAT_ID)
//   GET|POST .../state     GitHub Actions only (OIDC JWT: this repo, main branch)
//   POST .../admin/setup   GitHub Actions only: store secrets in Vault, set webhook, announce once
//   GET .../health
// State: one row in public.bot_state (jsonb), optimistic versioning; secrets: Supabase Vault via RPC (service_role).
import { CHAT_ID, teh, normalize, handle, send, tg, dispatch, verifyOidc, ANNOUNCE, HELP, COMMANDS } from "./lib.js";

export function makeApp(cfg) {
  const { url: SB, key: KEY } = cfg;   // SUPABASE_URL, service-role key
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

  async function onTelegram(req) {
    const env = await secrets();
    if (!env.TELEGRAM_BOT_TOKEN || (req.headers.get("x-telegram-bot-api-secret-token") || "") !== env.WEBHOOK)
      return new Response("forbidden", { status: 403 });
    const u = await req.json();
    const m = u.message || {};
    const text = (m.text || "").trim();
    if (String((m.chat || {}).id || "") !== CHAT_ID || !text.startsWith("/")) return new Response("ok");
    const res = await mutate(async (s) => {
      if ((s.seen_updates || []).includes(u.update_id)) return null;   // Telegram retry
      s.seen_updates = [...(s.seen_updates || []), u.update_id].slice(-50);
      const r = handle(s, text);
      if (r.queue) {
        if (!s.pending_cmds.some((x) => x.cmd === r.queue)) s.pending_cmds.push({ id: u.update_id, cmd: r.queue, at: teh().full });
        r.recent = s.last_dispatch && Date.now() - s.last_dispatch < 90000;
        if (!r.recent) s.last_dispatch = Date.now();
      }
      return r;
    });
    if (!res) return new Response("ok");
    if (res.queue) {
      const d = res.recent ? { ok: true } : await dispatch(env, "command");
      await send(env, d.ok ? "**⏳ در حال بررسی…**\n~~جواب تا حدود یک دقیقه‌ی دیگر~~"
                           : "**⏳ در صف بررسی**\n~~جواب در بررسی خودکار بعدی~~");
      if (!d.ok) await mutate(async (s) => { s.last_dispatch = 0; s.last_dispatch_error = d.why; return true; });
    } else {
      await send(env, res.reply);
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
      const r = await tg(env, "setWebhook", { url: hook, secret_token: env.WEBHOOK, allowed_updates: ["message"],
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
      if (p.endsWith("/state") || p.endsWith("/admin/setup")) {
        if (!(await verifyOidc(req, jwks))) return new Response("unauthorized", { status: 401 });
        if (p.endsWith("/admin/setup")) return await onSetup(req, origin);
        if (req.method === "GET") {
          const row = await loadRow();
          return Response.json({ state: normalize(row.state), news_windows: row.news || null });
        }
        const b = await req.json();
        return Response.json(await rpc("bot_merge", { p_patch: b.patch || {}, p_done: b.done_cmds || [], p_news: b.news_windows || null }));
      }
      if (p.endsWith("/health")) return Response.json({ ok: true, service: "m5-gold-bot" });
      return new Response("not found", { status: 404 });
    } catch (e) {
      console.error("tg-bot error:", String(e && e.message || e));
      // a 200 to Telegram avoids endless retries of one bad update; GitHub sees 500 and fails loudly
      return new Response("error", { status: p.endsWith("/tg") ? 200 : 500 });
    }
  };
}
