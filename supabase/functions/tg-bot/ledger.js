// Phase 3: signal lifecycle, trade journal, P&L and reports. Pure helpers; app.js does Telegram + database work.
// Lifecycle: sent -> entered -> closed (tp | sl | manual), or sent -> not_taken; a sent signal past valid_until shows as expired.
// Net P&L of a signal trade = gross (unit rate) - market spread $0.25 - fee 14,000 toman charged once (owner-confirmed).
import { toman, tomanShort, sessionDate, teh, faDate } from "./lib.js";

export const UNIT_RATE = { "1U": 80000, "0.5U": 40000 };
export const FEE_TOMAN = 14000, SPREAD_USD = 0.25, MIN_HOLD_S = 60;
export const JOURNAL_CMDS = ["/entered", "/closed", "/tp", "/sl", "/journal", "/pnl"];
const ACT_FA = { e: "ورود", t: "حد سود", s: "حد ضرر", m: "بستن دستی", n: "وارد نشدم" };
const ST_FA = { sent: "ارسال‌شده", entered: "باز", closed: "بسته", expired: "منقضی", not_taken: "وارد نشدم" };
const EXIT_FA = { tp: "حد سود", sl: "حد ضرر", manual: "بستن دستی" };
const FA = "۰۱۲۳۴۵۶۷۸۹";
const DIG = (t) => String(t).replace(/[۰-۹]/g, (c) => String(FA.indexOf(c))).replace(/[٠-٩]/g, (c) => String("٠١٢٣٤٥٦٧٨٩".indexOf(c))).replace(/٫/g, ".");
const signedT = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + toman(Math.abs(v));
const r2 = (x) => Math.round(x * 100) / 100;
const px = (v) => String(r2(Number(v)));

export function pnl(side, entry, exit, unit, withSpread = true) {
  const rate = UNIT_RATE[unit];
  if (!rate) throw new Error("bad unit");
  const dir = side === "BUY" ? 1 : side === "SELL" ? -1 : 0;
  if (!dir) throw new Error("bad side");
  const gross = Math.round((Number(exit) - Number(entry)) * dir * rate);
  const spread = withSpread ? Math.round(SPREAD_USD * rate) : 0;
  return { gross, spread, fee: FEE_TOMAN, net: gross - spread - FEE_TOMAN };
}
export function riskToman(sig) {
  return Math.round(Math.abs(Number(sig.entry) - Number(sig.sl)) * UNIT_RATE[sig.unit] + SPREAD_USD * UNIT_RATE[sig.unit] + FEE_TOMAN);
}
export function effectiveStatus(sig, nowMs) {
  return sig.status === "sent" && sig.valid_until && Date.parse(sig.valid_until) < nowMs ? "expired" : sig.status;
}
// "S-20261120-001" | "20261120-001" | "001" / "1" (today's trading day) | "" (latest signal)
export function resolveId(arg, now = teh()) {
  const a = DIG(arg || "").trim().toUpperCase();
  if (!a) return null;
  let m = a.match(/^S-(\d{8})-(\d{1,3})$/) || a.match(/^(\d{8})-(\d{1,3})$/);
  if (m) return `S-${m[1]}-${m[2].padStart(3, "0")}`;
  m = a.match(/^(\d{1,3})$/);
  if (m) return `S-${sessionDate(now).replace(/-/g, "")}-${m[1].padStart(3, "0")}`;
  throw new Error("bad id");
}
const parsePrice = (t) => {
  const v = parseFloat(DIG(t).replace(/[,٬]/g, ""));
  if (!(v > 500 && v < 20000) || !/^\d+(\.\d+)?$/.test(DIG(t).replace(/[,٬]/g, ""))) throw new Error("bad price");
  return r2(v);
};
// /entered [id] [price] · /closed [id] <price> · /tp [id] · /sl [id] · /journal · /pnl
export function parseJournalCmd(c, args, now = teh()) {
  if (c === "/journal" || c === "/pnl") return { view: c.slice(1) };
  const act = { "/entered": "e", "/closed": "m", "/tp": "t", "/sl": "s" }[c];
  let id = null, price = null;
  const xs = args.map((x) => DIG(x).trim()).filter(Boolean);
  for (const x of xs) {
    if (/^(S-)?\d{8}-\d{1,3}$/i.test(x) || /^\d{1,3}$/.test(x)) { if (id) throw new Error("bad"); id = resolveId(x, now); }
    else if (/^\d{3,5}(\.\d+)?$/.test(x)) { if (price !== null) throw new Error("bad"); price = parsePrice(x); }
    else throw new Error("bad");
  }
  if (act === "m" && price === null) throw new Error("price needed");
  if ((act === "t" || act === "s") && price !== null) throw new Error("bad");
  return { act, id, price };
}
// What a confirmed action does to a signal. Returns { error } or { update, journal, record }.
export function applyAction(sig, act, price, nowMs, opts = {}) {
  const st = effectiveStatus(sig, nowMs);
  const iso = new Date(nowMs).toISOString();
  if (act === "e") {
    if (!["sent", "expired"].includes(st)) return { error: `این سیگنال الان «${ST_FA[st]}» است و ورود ثبت نمی‌شود.` };
    return { update: { status: "entered", entered_at: iso, entry_fill: price ?? Number(sig.entry) } };
  }
  if (act === "n") {
    if (!["sent", "expired"].includes(st)) return { error: `این سیگنال الان «${ST_FA[st]}» است.` };
    return { update: { status: "not_taken" } };
  }
  if (!["sent", "expired", "entered"].includes(st)) return { error: `این سیگنال الان «${ST_FA[st]}» است و دوباره بسته نمی‌شود.` };
  const exitType = { t: "tp", s: "sl", m: "manual" }[act];
  const exit = act === "t" ? Number(sig.tp) : act === "s" ? Number(sig.sl) : price;
  const entry = sig.entry_fill != null ? Number(sig.entry_fill) : Number(sig.entry);
  const p = pnl(sig.side, entry, exit, sig.unit, !opts.fills);   // fills typed by the owner already include the spread
  const hold = sig.entered_at ? Math.round((nowMs - Date.parse(sig.entered_at)) / 1000) : null;
  const under = hold === null ? null : (exitType !== "sl" && hold < MIN_HOLD_S);   // SL is exempt from the 60 s rule
  const R = r2(p.net / (opts.fills ? riskToman(sig) - Math.round(SPREAD_USD * UNIT_RATE[sig.unit]) : riskToman(sig)));
  const update = { status: "closed", closed_at: iso, exit_price: exit, exit_type: exitType, net_toman: p.net, r_multiple: R, under_60s: under,
    ...(sig.entry_fill == null ? { entry_fill: entry } : {}) };
  const journal = { trade_id: sig.id, signal_id: sig.id, source: "signal", verification: "USER_CONFIRMED", side: sig.side, unit: sig.unit,
    entry, exit, opened_at: sig.entered_at || null, closed_at: iso, session_date: sessionDate(teh(new Date(nowMs))), exit_type: exitType,
    gross_toman: p.gross, spread_toman: p.spread, fee_toman: p.fee, net_toman: p.net, r_multiple: R, hold_seconds: hold, under_60s: under };
  return { update, journal, record: { type: p.net < 0 ? "loss" : "win", toman: Math.abs(p.net), net: p.net, trade: sig.id } };
}
export function previewText(sig, act, price, nowMs) {
  const head = `**${ACT_FA[act]}** \`${sig.id}\``;
  const side = `~~${sig.side === "BUY" ? "خرید" : "فروش"} · ${sig.unit === "1U" ? "یک واحد" : "نیم واحد"} · ورود \`${px(sig.entry_fill ?? sig.entry)}\`~~`;
  const L = [head, side, ""];
  if (act === "e") L.push(`ورود در \`${px(price ?? sig.entry)}\``);
  else if (act === "n") L.push("این سیگنال «وارد نشدم» ثبت می‌شود.");
  else {
    const r = applyAction(sig, act, price, nowMs);
    if (r.error) return r.error;
    L.push(`خروج \`${px(r.journal.exit)}\` · نتیجه‌ی خالص ${signedT(r.journal.net_toman)} تومان (${r.journal.r_multiple > 0 ? "+" : ""}${r.journal.r_multiple}R)`);
    L.push(`~~کارمزد ${toman(FEE_TOMAN)} و اسپرد ${toman(r.journal.spread_toman)} تومان کم شده~~`);
  }
  L.push("", "ثبت شود؟");
  return L.join("\n");
}
export const confirmKeyboard = (act, id, price) => ({ inline_keyboard: [[
  { text: "✅ تأیید", callback_data: `c:${act}:${id}${price != null ? ":" + price : ""}` }, { text: "❌ لغو", callback_data: "x" }]] });
export function parseCallback(data) {
  const p = String(data || "").split(":");
  if (p[0] === "x") return { cancel: true };
  const okPx = (v) => Number(v) > 500 && Number(v) < 20000;
  if (p[0] === "c" && p[1] === "j" && /^S-\d{8}-\d{3}$/.test(p[2] || "") && okPx(p[3]) && okPx(p[4]) && ["1", "0.5"].includes(p[5]))
    return { step: "c", act: "j", id: p[2], entry: Number(p[3]), price: Number(p[4]), unit: p[5] === "1" ? "1U" : "0.5U" };
  if (p[0] === "tr" && ["buy", "sell"].includes(p[1]) && okPx(p[2]) && okPx(p[3]) && ["1", "0.5"].includes(p[4]))
    return { trade: `/trade ${p[1]} ${p[2]} ${p[3]} ${p[4]}` };
  if ((p[0] === "a" || p[0] === "c") && ["e", "t", "s", "m", "n"].includes(p[1]) && /^S-\d{8}-\d{3}$/.test(p[2] || "")) {
    const price = p[3] ? Number(p[3]) : null;
    if (p[3] && !(price > 500 && price < 20000)) return null;
    return { step: p[0], act: p[1], id: p[2], price };
  }
  return null;
}
export function doneText(sig, act, res) {
  if (act === "e") return `**✅ ورود ثبت شد** \`${sig.id}\`\n~~بعد از بستن، دکمه‌ی حد سود / حد ضرر یا \`/closed ${sig.id.slice(-3)} قیمت\`~~`;
  if (act === "n") return `**✅ ثبت شد** \`${sig.id}\`\n~~وارد نشدم~~`;
  const j = res.journal;
  const L = [`**${j.net_toman >= 0 ? "📈" : "📉"} ${EXIT_FA[j.exit_type]} ثبت شد** \`${sig.id}\``, `~~ورود \`${px(j.entry)}\` · خروج \`${px(j.exit)}\`~~`, "",
    `نتیجه‌ی خالص ${signedT(j.net_toman)} تومان (${j.r_multiple > 0 ? "+" : ""}${j.r_multiple}R)`];
  if (j.under_60s) L.push("⚠️ کمتر از ۶۰ ثانیه نگه داشته شد؛ دریاگلد ممکن است این معامله را نپذیرد");
  return L.join("\n");
}
const TRACK_FA = { no_fill: "پر نشد", open: "باز", tp: "به هدف رسید", sl: "به حد ضرر رسید", close: "تا بسته‌شدن بازار" };
const rr = (v) => (v === null || v === undefined ? "—" : `${Number(v) > 0 ? "+" : ""}${Number(v)}R`);
export const trackLine = (x) => x && x.track_outcome
  ? `${TRACK_FA[x.track_outcome] || x.track_outcome}${x.mfe_r != null ? ` · بیشترین سود ${rr(x.mfe_r)} · بیشترین ضرر ${rr(-Number(x.mae_r))}` : ""}` : "";
export function journalMsg(rows, track = {}, recent = []) {
  const L = ["**📒 ژورنال**"];
  if (!rows.length) L.push("~~هنوز معامله‌ای ثبت نشده~~");
  else L.push("~~ده معامله‌ی آخر~~", "");
  for (const r of rows.slice(0, 10)) {
    const t = teh(new Date(r.closed_at));
    const tl = r.signal_id ? trackLine(track[r.signal_id]) : "";
    L.push(`${t.date.slice(5).replace("-", "/")} ${t.hm} ${r.side === "BUY" ? "خرید" : "فروش"} ${r.unit === "1U" ? "۱" : "۰٫۵"} واحد · \`${px(r.entry)}\` → \`${px(r.exit)}\` · ${signedT(Number(r.net_toman))}` +
      (r.under_60s ? " ⚠️" : "") + (r.signal_id ? ` · ${r.signal_id.slice(-3)}` : "") + (tl ? `\n   ~~سیگنال: ${tl}~~` : ""));
  }
  if (recent.length) {
    L.push("", "**🔭 پیگیری سیگنال‌ها**", "~~خود سیگنال، جدا از اینکه وارد شدید یا نه؛ R بر پایه‌ی فاصله‌ی حد ضرر~~");
    for (const x of recent.slice(0, 5)) L.push(`\`${x.id}\` ${x.side === "BUY" ? "خرید" : "فروش"} · ${trackLine(x)}`);
  }
  return L.join("\n");
}
function agg(rows) {
  const n = rows.length, wins = rows.filter((r) => Number(r.net_toman) > 0).length;
  const net = rows.reduce((a, r) => a + Number(r.net_toman || 0), 0);
  const rs = rows.filter((r) => r.r_multiple !== null && r.r_multiple !== undefined);
  return { n, wins, losses: n - wins, net, R: r2(rs.reduce((a, r) => a + Number(r.r_multiple), 0)), rN: rs.length,
    under: rows.filter((r) => r.under_60s).length };
}
export function pnlMsg(rows, now = teh()) {
  const today = sessionDate(now);
  const weekAgo = new Date(Date.parse(today + "T00:00:00Z") - 6 * 86400000).toISOString().slice(0, 10);
  const line = (name, a) => `${name}: ${a.n} معامله · ${a.wins} سود · ${a.losses} ضرر · ${signedT(a.net)} تومان`;
  return ["**💰 سود و ضرر خالص**", "~~بعد از کارمزد و اسپرد~~", "",
    line("امروز", agg(rows.filter((r) => r.session_date === today))),
    line("۷ روز", agg(rows.filter((r) => r.session_date >= weekAgo))),
    line("همه", agg(rows))].join("\n");
}
// Daily / weekly report. forGroup drops every toman figure and the balance.
export function reportMsg(kind, { signals, journal, shadow, calibration }, from, to, nowMs, forGroup = false) {
  const inP = (d) => d >= from && d <= to;
  const sg = signals.filter((x) => inP(String(x.session_date).slice(0, 10)));
  const jr = journal.filter((x) => inP(String(x.session_date).slice(0, 10)));
  const st = (k) => sg.filter((x) => effectiveStatus(x, nowMs) === k).length;
  const a = agg(jr);
  const sh = (shadow || []).filter((e) => e.at && inP(sessionDate({ date: e.at.slice(0, 10), hm: e.at.slice(11, 16) })));
  const gates = {};
  for (const e of sh) for (const g of e.gates || []) gates[g] = (gates[g] || 0) + 1;
  const GF = { news: "خبر", volatility: "نوسان", spread: "اسپرد", friday: "جمعه", session: "ساعت", asia: "آسیا" };
  const title = kind === "weekly" ? "**📊 گزارش هفته**" : "**📊 گزارش روز**";
  const span = kind === "weekly" ? `~~${from.slice(5).replace("-", "/")} تا ${to.slice(5).replace("-", "/")}~~` : `~~${faDate(new Date(Date.parse(to + "T12:00:00+03:30")))}~~`;
  const L = [title, span, "",
    `🎯 سیگنال ${sg.length} · ورود ${sg.filter((x) => ["entered", "closed"].includes(x.status)).length} · وارد نشدم ${st("not_taken")} · منقضی ${st("expired")}`,
    `📒 معامله‌ی بسته ${a.n} · سود ${a.wins} · ضرر ${a.losses}${a.n ? ` · نرخ برد ${Math.round((100 * a.wins) / a.n)}٪` : ""}`];
  if (a.rN) L.push(`📐 جمع ${a.R > 0 ? "+" : ""}${a.R}R`);
  if (!forGroup) L.push(`💰 نتیجه‌ی خالص ${signedT(a.net)} تومان`);
  if (a.under) L.push(`⚠️ زیر ۶۰ ثانیه: ${a.under}`);
  const gl = Object.entries(gates).map(([g, n]) => `${GF[g] || g} ${n}`);
  L.push(`🕶 ستاپ ردشده با فیلتر: ${sh.length}${gl.length ? ` (${gl.join("، ")})` : ""}`);
  const tracked = sg.filter((x) => x.track_outcome && x.track_outcome !== "open");
  if (tracked.length) {
    const filled = tracked.filter((x) => x.mfe_r !== null && x.mfe_r !== undefined);
    const avg = (k) => r2(filled.reduce((a, x) => a + Number(x[k] || 0), 0) / (filled.length || 1));
    L.push(`🔭 پیگیری سیگنال: هدف ${tracked.filter((x) => x.track_outcome === "tp").length} · حد ضرر ${tracked.filter((x) => x.track_outcome === "sl").length}` +
      ` · پر نشد ${tracked.filter((x) => x.track_outcome === "no_fill").length}` +
      (filled.length ? ` · میانگین بیشترین سود ${rr(avg("mfe_r"))} و بیشترین ضرر ${rr(-avg("mae_r"))}` : ""));
  }
  if (!forGroup && calibration) L.push(`🎚 قیمت دریاگلد: ${calibration.status === "calibrated" ? "کالیبره" : "کالیبره نشده"}`);
  return L.join("\n");
}
// Inline keyboard under a signal card (owner copy only)
export const signalKeyboard = (id) => ({ inline_keyboard: [
  [{ text: "✅ وارد شدم", callback_data: `a:e:${id}` }, { text: "🚫 وارد نشدم", callback_data: `a:n:${id}` }],
  [{ text: "🎯 حد سود", callback_data: `a:t:${id}` }, { text: "🛑 حد ضرر", callback_data: `a:s:${id}` }],
  [{ text: "✋ بستن دستی", callback_data: `a:m:${id}` }]] });
export const BAD_JOURNAL = "**⚠️ ثبت نشد**\n~~نمونه:~~\n`/entered 001` · `/tp 001` · `/sl 001`\n`/closed 001 3569.85`";

// /trade double-count guard: a /trade that looks like an open signal asks whether it is that signal.
export function matchSignal(t, sigs, today) {
  const side = t.side.toUpperCase();
  const prev = new Date(Date.parse(today + "T00:00:00Z") - 86400000).toISOString().slice(0, 10);
  return (sigs || []).find((x) => x.side === side && ["sent", "entered", "expired"].includes(x.status) && String(x.session_date).slice(0, 10) >= prev &&
    Math.abs(Number(x.entry_fill ?? x.entry) - t.entry) <= 2.0) || null;
}
export function tradeMatchCard(t, sig) {
  const u = t.units === 1 ? "1" : "0.5";
  return { text: [`**❓ این معامله همان سیگنال** \`${sig.id}\` **است؟**`,
    `~~سیگنال: ${sig.side === "BUY" ? "خرید" : "فروش"} · ورود \`${px(sig.entry)}\` · ${sig.unit === "1U" ? "یک واحد" : "نیم واحد"}~~`,
    `~~معامله: ورود \`${px(t.entry)}\` · خروج \`${px(t.exit)}\` · ${t.units === 1 ? "یک واحد" : "نیم واحد"}~~`, "",
    "اگر همان است، فقط یک بار ثبت می‌شود."].join("\n"),
    markup: { inline_keyboard: [[{ text: "✅ همان سیگنال است", callback_data: `c:j:${sig.id}:${t.entry}:${t.exit}:${u}` }],
      [{ text: "➕ معامله‌ی جدا", callback_data: `tr:${t.side}:${t.entry}:${t.exit}:${u}` }], [{ text: "❌ لغو", callback_data: "x" }]] } };
}
