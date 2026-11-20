// Owner assistant (owner decisions t226u-t232u, 2026-11-20): live DaryaGold price, /trend, /e, /setup, and the
// alert checks run by /tick. Pure functions except fetchMarket(). Never places trades.
//
// Shared numbers: levels ALWAYS come from the one stored snapshot (bot_state.levels, computed in the GitHub run by
// tools/levels.py + tools/level_view.py) and are shown with the same 1-decimal rounding as /levels; never recomputed here.
// The trend rule is a port of tools/level_view.py (EMA20/50 + confirmed 3-bar fractal swings), so /trend, the
// /levels block and the TradingView indicator read the same way. The live price is fetched at command time.
//
// Price frame: DaryaGold (chart) price = Dukascopy mid + dg_mid_offset (bot_state.state.dg_mid_offset, default 0.02).
// Orders: a buy fills at the ask (= chart + spread), a sell at the chart price. So buy entries, sell stop-losses and
// sell take-profits are moved up by SPREAD to trigger when the chart price reaches the intended level.
// Money: 1 unit = 80,000 toman per $1, 0.5 unit = 40,000; the 14,000 toman fee is charged once per trade.

export const RATE = { 1: 80000, 0.5: 40000 };
export const FEE = 14000;
export const SPREAD = 0.25;
export const DEFAULT_MID_OFFSET = 0.02;
export const SETUP_VALID_MIN = 45;
export const MAX_SL_USD = 9;          // beyond this a 1-unit stop-out (80% of 1M margin = $10) is too close
export const TF_MS = { M5: 3e5, M15: 9e5, H1: 3.6e6, H4: 1.44e7 };
const LOOK_MS = { H4: 20 * 864e5, H1: 8 * 864e5, M15: 2 * 864e5, M5: 864e5 };   // = tools/levels.py swings lookback
export const TFS = ["M5", "M15", "H1", "H4"];
export const TF_FA = { M5: "۵ دقیقه", M15: "۱۵ دقیقه", H1: "۱ ساعت", H4: "۴ ساعت" };
const UP = "صعودی", DOWN = "نزولی", FLAT = "خنثی", UNKNOWN = "نامشخص";

export const r2 = (x) => Math.round(x * 100) / 100;
export const p1 = (x) => String(Math.round(Number(x) * 10) / 10);           // level display (= /levels)
export const px = (x) => Number(x).toFixed(2);                                // copyable order price
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const DIG = { "۰": 0, "۱": 1, "۲": 2, "۳": 3, "۴": 4, "۵": 5, "۶": 6, "۷": 7, "۸": 8, "۹": 9,
  "٠": 0, "١": 1, "٢": 2, "٣": 3, "٤": 4, "٥": 5, "٦": 6, "٧": 7, "٨": 8, "٩": 9, "٫": "." };
const latin = (t) => String(t).replace(/[۰-۹٠-٩٫]/g, (c) => String(DIG[c]));

export function midOffsetOf(s) {
  const v = Number(s && s.dg_mid_offset);
  return s && s.dg_mid_offset !== null && s.dg_mid_offset !== "" && Number.isFinite(v) && Math.abs(v) <= 5 ? v : DEFAULT_MID_OFFSET;
}

// ---------------- Tehran clock helpers ----------------
const TEH_MS = 210 * 60000;
export function tehParts(ms) {
  const t = new Date(ms + TEH_MS), p = (n) => String(n).padStart(2, "0");
  return { date: `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())}`, hm: `${p(t.getUTCHours())}:${p(t.getUTCMinutes())}`,
    dow: t.getUTCDay(), min: t.getUTCHours() * 60 + t.getUTCMinutes() };
}
export const hmOf = (ms) => tehParts(ms).hm;
export const tehMs = (s) => Date.parse(String(s).slice(0, 16).replace(" ", "T") + ":00+03:30");   // "YYYY-MM-DD HH:MM" Tehran

// ---------------- market data (Dukascopy freeserv, free, no key) ----------------
const IV = { M1: "1MIN", M5: "5MIN", M15: "15MIN", H1: "1HOUR", H4: "4HOUR" };
export const dukaUrl = (iv, side, limit, ts) => "https://freeserv.dukascopy.com/2.0/index.php?path=chart%2Fjson3&instrument=XAU%2FUSD" +
  `&offer_side=${side}&interval=${IV[iv]}&splits=true&stocks=true&limit=${limit}&time_direction=P&timestamp=${ts}&jsonp=_cb`;
export function parseBars(text) {
  const t = String(text || ""), a = t.indexOf("("), b = t.lastIndexOf(")");
  const rows = JSON.parse(a >= 0 && b > a ? t.slice(a + 1, b) : t);
  if (!Array.isArray(rows)) throw new Error("bad feed");
  return rows.filter((r) => Array.isArray(r) && r.length >= 5 && r.slice(0, 5).every((x) => Number.isFinite(Number(x))))
    .map((r) => [Number(r[0]), Number(r[1]), Number(r[2]), Number(r[3]), Number(r[4])]).sort((x, y) => x[0] - y[0]);
}
// One parallel fetch: 1-minute bid (+ a few ask bars for the spread) and the native M5/M15/H1/H4 bid bars.
export async function fetchMarket(nowMs, { tfs = TFS, m1 = 300, n = 300, fetchImpl = fetch } = {}) {
  const get = (iv, side, limit) => fetchImpl(dukaUrl(iv, side, limit, nowMs), {
    headers: { "user-agent": "Mozilla/5.0", referer: "https://freeserv.dukascopy.com/" }, signal: AbortSignal.timeout(9000) })
    .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`feed ${r.status}`)))).then(parseBars);
  const [m1B, m1A, ...nat] = await Promise.all([get("M1", "B", m1), get("M1", "A", 5).catch(() => []), ...tfs.map((tf) => get(tf, "B", n))]);
  if (!m1B.length) throw new Error("empty feed");
  return { nowMs, m1B, m1A, native: Object.fromEntries(tfs.map((tf, i) => [tf, nat[i]])) };
}
// Native bars are completed bars only. Rebuild what came after them from the 1-minute bars:
// closed = native + completed rebuilt buckets; live = closed + the bucket in progress.
export function withLive(native, m1, tfMs) {
  const nat = (native || []).slice();
  const after = nat.length ? nat[nat.length - 1][0] + tfMs : -Infinity;
  const lastM1 = m1.length ? m1[m1.length - 1][0] + 60000 : 0;
  const buckets = new Map();
  for (const b of m1) {
    if (b[0] < after) continue;
    const k = Math.floor(b[0] / tfMs) * tfMs, x = buckets.get(k);
    if (!x) buckets.set(k, [k, b[1], b[2], b[3], b[4]]);
    else { x[2] = Math.max(x[2], b[2]); x[3] = Math.min(x[3], b[3]); x[4] = b[4]; }
  }
  const extra = [...buckets.values()].sort((a, b) => a[0] - b[0]);
  const closed = nat.concat(extra.filter((b) => b[0] + tfMs <= lastM1));
  const live = nat.concat(extra);
  return { closed, live };
}
export function quoteOf(mkt, midOff = DEFAULT_MID_OFFSET) {
  const b = mkt.m1B[mkt.m1B.length - 1];
  const a = (mkt.m1A || []).find((x) => x[0] === b[0]) || (mkt.m1A || [])[(mkt.m1A || []).length - 1];
  let spread = a && Math.abs(a[0] - b[0]) <= 120000 ? a[4] - b[4] : 0.35;
  if (!(spread > 0.02 && spread < 3)) spread = 0.35;
  const bid = b[4], mid = bid + spread / 2, dg = r2(mid + midOff);
  return { bid, ask: r2(bid + spread), spread: r2(spread), mid: r2(mid), dg, bidOff: r2(dg - bid), barAt: b[0] + 60000,
    ageS: Math.round((mkt.nowMs - b[0] - 60000) / 1000) };
}

// ---------------- indicators (ports of tools/levels.py) ----------------
export function emaLast(vals, n) {   // pandas ewm(span=n, adjust=False)
  if (!vals.length) return NaN;
  const a = 2 / (n + 1);
  let e = vals[0];
  for (let i = 1; i < vals.length; i++) e = a * vals[i] + (1 - a) * e;
  return e;
}
export function atrSeries(bars, n = 14) {   // Wilder: ewm(alpha=1/n, adjust=False) of the true range
  const out = [];
  let e = null;
  for (let i = 0; i < bars.length; i++) {
    const [, , h, l] = bars[i], pc = i ? bars[i - 1][4] : null;
    const tr = pc === null ? h - l : Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc));
    e = e === null ? tr : e + (tr - e) / n;
    out.push(e);
  }
  return out;
}
export function fractals(bars, n, since) {
  const x = bars.filter((b) => b[0] >= since), H = [], L = [];
  for (let k = n; k < x.length - n; k++) {
    let hi = true, lo = true;
    for (let j = k - n; j <= k + n; j++) { if (x[j][2] > x[k][2]) hi = false; if (x[j][3] < x[k][3]) lo = false; }
    if (hi) H.push([x[k][0], x[k][2]]);
    if (lo) L.push([x[k][0], x[k][3]]);
  }
  return { highs: H, lows: L };
}
export function tfTrend(bars, tf) {
  const out = { trend: FLAT, structure: "mixed", ema: "neutral" };
  if (!bars || bars.length < 10) return out;
  const last = bars[bars.length - 1];
  const sw = fractals(bars, 3, last[0] - LOOK_MS[tf]);
  const hs = sw.highs.slice(-5), ls = sw.lows.slice(-5);
  if (hs.length >= 2 && ls.length >= 2) {
    const uh = hs[hs.length - 1][1] > hs[hs.length - 2][1], ul = ls[ls.length - 1][1] > ls[ls.length - 2][1];
    out.structure = uh && ul ? "up" : !uh && !ul ? "down" : "mixed";
  }
  if (bars.length >= 56) {
    const c = bars.map((b) => b[4]), e20 = emaLast(c, 20), e50 = emaLast(c, 50), cl = last[4];
    out.ema = e20 > e50 && cl > e20 ? "bullish" : e20 < e50 && cl < e20 ? "bearish" : "neutral";
    Object.assign(out, { ema20: r2(e20), ema50: r2(e50), close: cl });
  }
  out.trend = out.structure === "up" && out.ema === "bullish" ? UP : out.structure === "down" && out.ema === "bearish" ? DOWN : FLAT;
  return out;
}
export function trendsOf(mkt, which = "live") {
  const t = {};
  for (const tf of TFS) t[tf] = tfTrend(withLive(mkt.native[tf], mkt.m1B, TF_MS[tf])[which], tf).trend;
  return t;
}

// Overall line (= level_view.verdict_line, worded for /trend): H4 and H1 decide; M15/M5 aligned or correcting.
export function trendSummary(t) {
  const h4 = t.H4, h1 = t.H1;
  let overall = UNKNOWN, higher = null;
  if (h4 === h1 && (h4 === UP || h4 === DOWN)) { overall = higher = h4; }
  else if (h4 === FLAT && h1 === FLAT) overall = FLAT;
  let line;
  if (higher) {
    const opp = higher === UP ? DOWN : UP, act = higher === UP ? "بخری" : "بفروشی";
    const pull = ["M15", "M5"].filter((tf) => t[tf] === opp), same = ["M15", "M5"].filter((tf) => t[tf] === higher);
    if (same.length === 2) line = `${higher} است و ۱۵ دقیقه و ۵ دقیقه هم با آن هم‌جهت‌اند.`;
    else if (pull.length === 2) line = `${higher} است، ولی تایم‌های پایین در اصلاح‌اند. اگر می‌خواهی در جهت روند اصلی ${act}، صبر کن تا ۵ و ۱۵ دقیقه دوباره ${higher} شوند.`;
    else if (pull.length === 1) line = `${higher} است، ولی ${TF_FA[pull[0]]} در اصلاح است. اگر می‌خواهی در جهت روند اصلی ${act}، صبر کن تا ${TF_FA[pull[0]]} دوباره ${higher} شود.`;
    else if (same.length === 1) line = `${higher} است؛ ${TF_FA[same[0]]} هم‌جهت است و ${TF_FA[same[0] === "M15" ? "M5" : "M15"]} فعلاً خنثی است.`;
    else line = `${higher} است؛ تایم‌های پایین فعلاً خنثی‌اند.`;
  } else if (overall === FLAT) line = "خنثی است؛ ۴ ساعت و ۱ ساعت جهت روشنی ندارند.";
  else line = `نامشخص است؛ ۴ ساعت ${h4} و ۱ ساعت ${h1} است.`;
  return { overall, higher, line };
}
export function trendMsg(t, { quote = null, dataAt = null, at, stale = false } = {}) {
  const sm = trendSummary(t);
  const L = ["**📊 روند طلا**", `~~${hmOf(at)} به وقت تهران` + (quote ? ` · دریاگلد \`${px(quote.dg)}\`` : "") + "~~", ""];
  for (const tf of TFS) L.push(`${TF_FA[tf]}: ${t[tf] || FLAT}`);
  L.push("", `**روند کلی:** ${sm.line}`);
  if (stale) L.push("", `~~داده‌ی زنده در دسترس نبود؛ این روند مربوط به ${dataAt ? hmOf(dataAt) : "آخرین بررسی"} است~~`);
  else if (dataAt) L.push("", `~~آخرین داده ${hmOf(dataAt)} به وقت تهران~~`);
  return L.join("\n");
}

// ---------------- levels from the shared snapshot ----------------
export function snapLevels(snap) {
  const out = [], seen = new Set(), half = Number(snap && snap.zone_half) || 1;
  for (const side of ["above", "below"]) {
    for (const x of ((snap && snap.short) || {})[side] || []) {
      const p = Number(x.price_dg);
      if (!Number.isFinite(p) || seen.has(p1(p))) continue;
      seen.add(p1(p));
      const z = Array.isArray(x.zone_dg) && x.zone_dg.length === 2 ? x.zone_dg.map(Number) : [p - half, p + half];
      out.push({ price: p, lo: Math.min(...z), hi: Math.max(...z), label: x.label_fa || "", kinds: x.kinds || [],
        strength: x.strength || "", touches: Number(x.touches_m15_3d) || 0, side: x.side || (side === "above" ? "resistance" : "support"),
        glued: Number.isFinite(Number(x.distance_atr)) && Math.abs(Number(x.distance_atr)) < 0.15 });
    }
  }
  return out.sort((a, b) => a.price - b.price);
}
export function snapAgeMin(snap, nowMs) {
  const t = snap && snap.computed_at_tehran ? tehMs(snap.computed_at_tehran) : NaN;
  return Number.isFinite(t) ? (nowMs - t) / 60000 : null;
}

// ---------------- money ----------------
export const netToman = (dir, entry, exit, u) => Math.round((exit - entry) * dir * RATE[u] - FEE);
export function tomanFa(v) {   // signed, short: −۲۴۸ هزار / +۱٫۴۸ میلیون (digits become Persian in render)
  const a = Math.abs(v), sg = v > 0 ? "+" : v < 0 ? "−" : "";
  if (a >= 1e6) return `${sg}${(a / 1e6).toFixed(2).replace(/0+$/, "").replace(/\.$/, "")} میلیون`;
  return `${sg}${Math.round(a / 1000)} هزار`;
}

// ---------------- price placement ----------------
const R5 = (lo, hi) => { const out = []; for (let r = Math.ceil(lo / 5) * 5; r <= hi; r += 5) out.push(r); return out; };
const offHalf = (x, away) => (Math.abs(x * 2 - Math.round(x * 2)) < 0.06 ? x + away * 0.07 : x);   // never sit on .00 / .50
// SL behind the level: zone edge + max($0.5, 0.3×ATR); at least max($1, 0.5×ATR) from the best entry; clear of a $5 round.
export function placeSL(dir, edge, bestEntry, atr5) {
  const buf = Math.max(0.5, 0.3 * atr5), minD = Math.max(1, 0.5 * atr5);
  let sl = dir < 0 ? Math.max(edge + buf, bestEntry + minD) : Math.min(edge - buf, bestEntry - minD);
  for (const r of R5(sl - 0.8, sl + 0.8)) {
    if (dir < 0 && r >= sl - 0.8 && r <= sl + 0.3) sl = r + 0.6;     // stops cluster just past round numbers: go further
    if (dir > 0 && r <= sl + 0.8 && r >= sl - 0.3) sl = r - 0.6;
  }
  sl = offHalf(sl, dir < 0 ? 1 : -1);
  return r2(dir < 0 ? sl + SPREAD : sl);   // a sell is closed at the ask
}
// TP just before the obstacle (next level's near zone edge) and before a $5 round number.
export function placeTP(dir, nearEdge) {
  let tp = dir < 0 ? nearEdge + 0.1 : nearEdge - 0.1;
  for (const r of R5(tp - 0.8, tp + 0.8)) {
    if (dir < 0 && r >= tp - 0.3 && r <= tp + 0.7) tp = r + 0.35;
    if (dir > 0 && r <= tp + 0.3 && r >= tp - 0.7) tp = r - 0.35;
  }
  tp = offHalf(tp, dir < 0 ? 1 : -1);
  return r2(dir < 0 ? tp + SPREAD : tp);   // a sell is closed at the ask
}
function placeRange(dir, L, atr5) {
  const w = clamp(0.2 * atr5, 0.5, 1.5);
  let lo, hi;
  if (dir < 0) { hi = L.price; lo = hi - w; for (const r of R5(lo, hi + 0.6)) if (r > lo) { hi = r - 0.15; lo = hi - w; } }
  else { lo = L.price; hi = lo + w; for (const r of R5(lo - 0.6, hi).reverse()) if (r < hi) { lo = r + 0.15; hi = lo + w; } }
  lo = offHalf(lo, 1); hi = offHalf(hi, -1);
  return dir < 0 ? [r2(lo), r2(hi)] : [r2(lo + SPREAD), r2(hi + SPREAD)];   // a buy limit fills at the ask
}
// Obstacles in the trade direction beyond `from` (nearest first), with their near zone edge.
function obstacles(levels, dir, from, skip) {
  return levels.filter((x) => x !== skip && (dir < 0 ? x.price < from - 0.5 : x.price > from + 0.5))
    .sort((a, b) => (dir < 0 ? b.price - a.price : a.price - b.price));
}
function targets(levels, dir, from, skip, atr5) {
  const ob = obstacles(levels, dir, from, skip);
  const edge = (x) => (dir < 0 ? x.hi : x.lo);
  const t1 = ob[0] ? { tp: placeTP(dir, edge(ob[0])), level: ob[0] } : { tp: r2(from + dir * Math.max(1.5, 1.2 * atr5)), level: null };
  let t2 = ob[1] ? { tp: placeTP(dir, edge(ob[1])), level: ob[1] } : null;
  if (!t2 || (t2.tp - t1.tp) * dir < 0.5) t2 = { tp: r2(t1.tp + dir * Math.max(1.5, 1.0 * atr5)), level: null };
  return { t1, t2 };
}

// ---------------- credibility score (0-100) ----------------
export const WEIGHTS = { trend: 25, fill: 15, level: 15, room: 10, rr: 15, adr: 8, session: 7, hunt: 5 };
const POS = { trend: "هم‌جهت روند", fill: "قیمت نزدیک بازه‌ی ورود است", level: "سطح معتبر و کم‌مصرف", room: "جای کافی تا هدف",
  rr: "نسبت سود به ضرر خوب", adr: "دامنه‌ی روزانه هنوز جا دارد", session: "ساعت پرتحرک و دور از خبر", hunt: "حد ضرر دور از محل شکار" };
const NEG = { trend: "خلاف روند", fill: "تا بازه‌ی ورود فاصله زیاد است", level: "سطح ضعیف یا پرمصرف", room: "جای کم تا هدف",
  rr: "نسبت سود به ضرر ضعیف", adr: "دامنه‌ی روزانه بیشتر مصرف شده", session: "نزدیک خبر یا ساعت کم‌تحرک", hunt: "حد ضرر نزدیک محل شکار حد ضررها" };
export function scoreSetup(f) {
  const total = Math.round(Object.entries(WEIGHTS).reduce((a, [k, w]) => a + w * clamp(f[k] ?? 0.5), 0));
  const rank = Object.keys(WEIGHTS).map((k) => [k, WEIGHTS[k] * clamp(f[k] ?? 0.5), clamp(f[k] ?? 0.5)]);
  const pos = rank.filter((x) => x[2] >= 0.7).sort((a, b) => b[1] - a[1]).slice(0, 2).map((x) => POS[x[0]]);
  const neg = rank.filter((x) => x[2] <= 0.35).sort((a, b) => WEIGHTS[b[0]] * (1 - b[2]) - WEIGHTS[a[0]] * (1 - a[2])).slice(0, 1).map((x) => NEG[x[0]]);
  const reason = pos.length ? pos.join("، ") + (neg.length ? `؛ ولی ${neg[0]}` : "") : (neg.length ? neg[0] : "عامل برجسته‌ای ندارد");
  return { score: total, reason };
}
function trendFactor(t, dir) {
  const want = dir > 0 ? UP : DOWN, opp = dir > 0 ? DOWN : UP, w = { H4: 0.3, H1: 0.3, M15: 0.25, M5: 0.15 };
  let s = 0;
  for (const tf of TFS) s += w[tf] * (t[tf] === want ? 1 : t[tf] === opp ? -1 : 0);
  return (s + 1) / 2;
}
const FRESH = [0.5, 0.9, 1, 0.9, 0.75, 0.6];
const STR = { strong: 1, medium: 0.65, weak: 0.35 };
function sessionFactor(nowMs, news) {
  const m = tehParts(nowMs).min;
  let f = m >= 7 * 60 && m < 10 * 60 + 30 ? 0.6 : m >= 23 * 60 || m < 30 ? 0.5 : 1;
  const nx = nextNews(news, nowMs, ["A", "B", "C"]);
  if (nx && nx.startMs - nowMs < 60 * 60000) f = Math.min(f, 0.4);
  return f;
}

// ---------------- news windows (bot_state.news.windows, Tehran local times) ----------------
const isMajor = (w) => w && (w.fomc || ["A", "B"].includes(String(w.tier || "").toUpperCase()));
export function newsList(news) {
  return ((news && news.windows) || []).map((w) => ({ ...w, startMs: tehMs(w.start), endMs: tehMs(w.end),
    eventMs: tehMs(w.event_time_tehran || w.event_time || w.start) })).filter((w) => Number.isFinite(w.startMs) && Number.isFinite(w.endMs));
}
export function nextNews(news, nowMs, tiers = ["A", "B"]) {
  return newsList(news).filter((w) => w.startMs > nowMs && (w.fomc || tiers.includes(String(w.tier || "").toUpperCase())))
    .sort((a, b) => a.startMs - b.startMs)[0] || null;
}
export function insideNews(news, nowMs) {
  return newsList(news).filter((w) => isMajor(w) && w.startMs <= nowMs && nowMs < w.endMs).sort((a, b) => b.endMs - a.endMs)[0] || null;
}

// ---------------- session limits (DaryaGold Mon-Fri 07:00-00:30 Tehran; Friday no new entry from 23:30) ----------------
export function entryLimit(nowMs) {
  const p = tehParts(nowMs);
  const dayStart = Date.parse(p.date + "T00:00:00+03:30");
  if (p.min < 30) return p.dow === 6 ? { closed: "friday" } : { untilMs: dayStart + 30 * 60000, why: "close" };
  if (p.min < 7 * 60 || p.dow === 0 || p.dow === 6) return { closed: "closed" };
  if (p.dow === 5) return p.min >= 23 * 60 + 30 ? { closed: "friday" } : { untilMs: dayStart + (23 * 60 + 30) * 60000, why: "friday" };
  return { untilMs: dayStart + (24 * 60 + 30) * 60000, why: "close" };
}

// ---------------- /setup ----------------
// ctx: { levels, quote, atr5, trend, adrUsed, nowMs, news }
export function validity(ctx) {
  const lim = entryLimit(ctx.nowMs);
  if (lim.closed) return { closed: lim.closed };
  const inNews = insideNews(ctx.news, ctx.nowMs);
  if (inNews) return { news: inNews };
  let until = ctx.nowMs + SETUP_VALID_MIN * 60000, why = "time";
  if (lim.untilMs < until) { until = lim.untilMs; why = lim.why; }
  const nx = nextNews(ctx.news, ctx.nowMs);
  if (nx && nx.startMs < until) { until = nx.startMs; why = "news"; }
  return { untilMs: until, why, short: until - ctx.nowMs < 10 * 60000 };
}
function candidate(ctx, L, dir) {
  const { levels, quote, atr5, trend } = ctx, P = quote.dg;
  const [lo, hi] = placeRange(dir, L, atr5);
  const best = dir < 0 ? hi : lo, worst = dir < 0 ? lo : hi, mid = r2((lo + hi) / 2);
  const sl = placeSL(dir, dir < 0 ? L.hi : L.lo, best, atr5);
  const { t1, t2 } = targets(levels, dir, dir < 0 ? lo : hi, L, atr5);
  const risk = Math.abs(sl - worst), room = Math.abs(mid - t1.tp);
  const chartP = dir > 0 ? P + SPREAD : P;   // a buy compares the ask with the range
  const dist = dir < 0 ? Math.max(0, lo - chartP) : Math.max(0, chartP - hi);
  const inside = dir < 0 ? chartP >= lo : chartP <= hi;
  let reject = null;
  if (dir < 0 ? P + SPREAD >= sl : P <= sl) reject = "قیمت از سطح عبور کرده است";
  else if (risk > MAX_SL_USD) reject = "حد ضرر لازم بیش از ۹ دلار است";
  else if (dist > 4 * atr5) reject = "تا بازه‌ی ورود خیلی فاصله است";
  else if ((t1.tp - mid) * dir <= 0 || room < Math.max(1, 0.5 * Math.abs(sl - mid))) reject = "تا سطح بعدی جا کم است";
  const rr = (Math.abs(t1.tp - mid) * RATE[1] - FEE) / (Math.abs(sl - mid) * RATE[1] + FEE);
  if (!reject && rr < 0.6) reject = "نسبت سود به ضرر ضعیف است";
  const roundNearSL = R5(sl - 1, sl + 1).length > 0;
  const obvious = L.kinds.some((k) => /high|low|PDH|PDL/i.test(k));
  const f = {
    trend: trendFactor(trend, dir), fill: inside ? 1 : clamp(1 - dist / (3 * atr5)),
    level: 0.6 * (STR[L.strength] ?? 0.5) + 0.4 * FRESH[Math.min(L.touches, 5)],
    room: clamp(room / (1.5 * atr5)), rr: clamp((rr - 0.5) / 1.5),
    adr: Number.isFinite(ctx.adrUsed) ? clamp((130 - ctx.adrUsed) / 80) : 0.5,
    session: sessionFactor(ctx.nowMs, ctx.news), hunt: clamp(1 - (obvious ? 0.25 : 0) - (roundNearSL ? 0.25 : 0)),
  };
  const sc = scoreSetup(f);
  const half = (L.touches >= 2 || L.strength === "strong") ? "better" : "near";
  const halfFa = dir < 0 ? (half === "better" ? "بالا" : "پایین") : (half === "better" ? "پایین" : "بالا");
  const halfWhy = inside ? "قیمت همین الان داخل بازه است" : half === "better" ? "قیمت بهتری دارد و سطح معتبر است" : "زودتر پر می‌شود";
  return { side: dir > 0 ? "BUY" : "SELL", dir, lo, hi, best, worst, sl, tp1: t1.tp, tp2: t2.tp, tp1Level: t1.level, tp2Level: t2.level,
    level: L, rr: r2(rr), dist: r2(dist), inside, factors: Object.fromEntries(Object.entries(f).map(([k, v]) => [k, r2(v)])),
    score: sc.score, reason: sc.reason, half, halfFa, halfWhy, invalid: sl, reject };
}
export function buildSetups(ctx) {
  const P = ctx.quote.dg, out = { SELL: [], BUY: [], why: { SELL: null, BUY: null } };
  for (const L of ctx.levels) {
    const res = P < L.lo || (P <= L.hi && L.side === "resistance");
    for (const dir of res ? [-1] : [1]) {
      const c = candidate(ctx, L, dir);
      if (c.reject) { out.why[c.side] = out.why[c.side] || c.reject; continue; }
      out[c.side].push(c);
    }
  }
  for (const k of ["SELL", "BUY"]) {
    out[k].sort((a, b) => b.score - a.score);
    out[k] = out[k].slice(0, 2);
    if (!out[k].length && !out.why[k]) out.why[k] = k === "SELL" ? "سطحی بالای قیمت در دسترس نیست" : "سطحی زیر قیمت در دسترس نیست";
  }
  return out;
}
const SIDE_FA = { SELL: "فروش", BUY: "خرید" };
const ICON = { SELL: "🔴", BUY: "🟢" };
function moneyLines(c, price, group) {
  if (group) return [];
  const a = netToman(c.dir, c.best, price, 1), b = netToman(c.dir, c.worst, price, 1);
  const a5 = netToman(c.dir, c.best, price, 0.5), b5 = netToman(c.dir, c.worst, price, 0.5);
  return [`   یک واحد ${tomanFa(a)} تا ${tomanFa(b)} · نیم واحد ${tomanFa(a5)} تا ${tomanFa(b5)}`];
}
function setupBlock(c, i, untilMs, group) {
  const warn = c.score < 40 ? " ⚠" : "";
  const lv = c.level, t1 = c.tp1Level, t2 = c.tp2Level;
  const L = [`**${ICON[c.side]} ${SIDE_FA[c.side]} ${i}** · اعتبار سیگنال ${c.score} از 100${warn}`,
    `ورود \`${px(c.lo)}\` تا \`${px(c.hi)}\` · نیمه‌ی ${c.halfFa} بهتر است؛ ${c.halfWhy}`,
    `🛑 حد ضرر \`${px(c.sl)}\``, ...moneyLines(c, c.sl, group),
    `🎯 حد سود ۱ \`${px(c.tp1)}\``, ...moneyLines(c, c.tp1, group),
    `🎯 حد سود ۲ \`${px(c.tp2)}\``, ...moneyLines(c, c.tp2, group),
    `~~سطح \`${p1(lv.price)}\` (${lv.label || "سطح"})` + (t1 ? ` · هدف ۱ پیش از \`${p1(t1.price)}\`` : "") + (t2 ? ` · هدف ۲ پیش از \`${p1(t2.price)}\`` : "") + "~~",
    `~~معتبر تا ${hmOf(untilMs)}؛ اگر پیش از ورود قیمت به \`${px(c.invalid)}\` برسد، باطل است~~`,
    `دلیل: ${c.reason}`];
  if (c.score < 40) L.push("⚠ اعتبار زیر ۴۰ است؛ پرخطر");
  return L.join("\n");
}
const WHY_UNTIL = { time: "", news: " (پیش از خبر)", friday: " (پایان ورود جمعه)", close: " (بسته شدن دریاگلد)" };
export function setupMsg(res, ctx, v, { group = false, snapNote = null } = {}) {
  const t = ctx.trend;
  const head = ["**🎯 ستاپ‌ها**", `~~${hmOf(ctx.nowMs)} به وقت تهران · دریاگلد \`${px(ctx.quote.dg)}\` · معتبر تا ${hmOf(v.untilMs)}${WHY_UNTIL[v.why] || ""}~~`,
    `~~روند: ۴ ساعت ${t.H4} · ۱ ساعت ${t.H1} · ۱۵ دقیقه ${t.M15} · ۵ دقیقه ${t.M5}~~`];
  if (snapNote) head.push(`~~${snapNote}~~`);
  const L = [head.join("\n")];
  if (!group && (res.SELL.length || res.BUY.length)) L.push("~~مبلغ‌ها به تومان و با کسر کارمزد؛ اولی برای بهترین و دومی برای بدترین نقطه‌ی بازه~~");
  for (const k of ["SELL", "BUY"]) {
    if (res[k].length) res[k].forEach((c, i) => L.push(setupBlock(c, i + 1, v.untilMs, group)));
    else L.push(`${ICON[k]} فعلاً ستاپ معقولی برای ${SIDE_FA[k]} نیست؛ ${res.why[k]}.`);
  }
  if (res.SELL.length || res.BUY.length) L.push("~~حد سود ۱ و ۲ دو انتخاب‌اند؛ دریاگلد بستن بخشی ندارد، پس هنگام ورود یکی را بگذار~~");
  return L.join("\n\n");
}
export function noSetupMsg(v, nowMs) {
  if (v.closed === "friday") return "**🎯 ستاپ‌ها**\n~~ورود جدید جمعه از 23:30 بسته است؛ ستاپی چیده نمی‌شود~~";
  if (v.news) return `**🎯 ستاپ‌ها**\n~~${hmOf(nowMs)} به وقت تهران~~\n\nپنجره‌ی خبر تا ${hmOf(v.news.endMs)} ادامه دارد؛ تا آن موقع ستاپی چیده نمی‌شود.`;
  if (v.short) return `**🎯 ستاپ‌ها**\n~~${hmOf(nowMs)} به وقت تهران~~\n\nتا ${hmOf(v.untilMs)}${WHY_UNTIL[v.why] || ""} کمتر از ۱۰ دقیقه مانده؛ ستاپ تازه چیده نمی‌شود.`;
  return null;
}

// ---------------- /e ----------------
export function parseEntry(args) {
  const a = args.map((x) => latin(x).toLowerCase().replace(/[,٬]/g, "")).filter(Boolean);
  let dir = 0;
  if (a.length === 2) {
    dir = ["buy", "b", "long", "خرید"].includes(a[0]) ? 1 : ["sell", "s", "short", "فروش"].includes(a[0]) ? -1 : NaN;
    a.shift();
  }
  if (a.length !== 1 || !(dir === 0 || dir === 1 || dir === -1) || !/^\d{3,5}(\.\d{1,3})?$/.test(a[0])) throw new Error("bad");
  const price = parseFloat(a[0]);
  if (!(price > 1000 && price < 10000)) throw new Error("bad");
  return { dir, price };
}
export function directionFrom(t) {
  const sm = trendSummary(t);
  if (sm.higher) return { dir: sm.higher === UP ? 1 : -1, why: `روند کلی ${sm.higher}` };
  for (const tf of ["H1", "M15"]) if (t[tf] === UP || t[tf] === DOWN) return { dir: t[tf] === UP ? 1 : -1, why: `روند ${TF_FA[tf]} ${t[tf]}` };
  return null;
}
export function planEntry(ctx, dir, E) {
  const { levels, atr5 } = ctx;
  // SL behind the nearest level on the losing side (the zone holding the entry, or the next one), if within $9
  const behind = levels.filter((x) => (dir < 0 ? x.hi >= E : x.lo <= E))
    .sort((a, b) => (dir < 0 ? a.hi - b.hi : b.lo - a.lo))[0];
  let sl = behind ? placeSL(dir, dir < 0 ? behind.hi : behind.lo, E, atr5) : null, slLevel = behind || null;
  if (sl === null || Math.abs(sl - E) > MAX_SL_USD) {
    sl = placeSL(dir, E + dir * -Math.max(1, 0.6 * atr5), E, atr5); slLevel = null;
  }
  const inZone = levels.find((x) => E >= x.lo && E <= x.hi);
  const { t1, t2 } = targets(levels, dir, E, inZone, atr5);
  let tp1 = t1.tp, tp2 = t2.tp;
  if ((tp1 - E) * dir < 0.5) { tp1 = r2(E + dir * Math.max(1.5, atr5)); tp2 = r2(tp1 + dir * Math.max(1.5, atr5)); }
  return { dir, entry: E, sl, tp1, tp2, slLevel, tp1Level: (tp1 === t1.tp ? t1.level : null), tp2Level: (tp2 === t2.tp ? t2.level : null) };
}
export function entryMsg(p, { quote, nowMs, dirWhy = null }) {
  const m = (price) => `   یک واحد ${tomanFa(netToman(p.dir, p.entry, price, 1))} · نیم واحد ${tomanFa(netToman(p.dir, p.entry, price, 0.5))}`;
  const L = [`**📐 ${p.dir > 0 ? "خرید" : "فروش"} از \`${px(p.entry)}\`**`,
    `~~${dirWhy ? `جهت از ${dirWhy} · ` : ""}${hmOf(nowMs)} به وقت تهران` + (quote ? ` · دریاگلد الان \`${px(quote.dg)}\`` : "") + "~~", "",
    `🛑 حد ضرر \`${px(p.sl)}\``, m(p.sl), `🎯 حد سود ۱ \`${px(p.tp1)}\``, m(p.tp1), `🎯 حد سود ۲ \`${px(p.tp2)}\``, m(p.tp2), ""];
  const why = [];
  why.push(p.slLevel ? `حد ضرر پشت سطح \`${p1(p.slLevel.price)}\`` : "حد ضرر بر پایه‌ی نوسان، چون سطحی در فاصله‌ی ۹ دلاری نبود");
  if (p.tp1Level) why.push(`حد سود ۱ پیش از \`${p1(p.tp1Level.price)}\``);
  if (p.tp2Level) why.push(`حد سود ۲ پیش از \`${p1(p.tp2Level.price)}\``);
  L.push(`~~${why.join("؛ ")}~~`, "~~مبلغ‌ها به تومان و با کسر کارمزد · حد سود ۱ و ۲ دو انتخاب‌اند؛ دریاگلد بستن بخشی ندارد~~");
  if (quote && Math.abs(p.entry - quote.dg) > 30) L.push("", "⚠ قیمت ورود بیش از ۳۰ دلار با قیمت فعلی فاصله دارد؛ عدد را دوباره ببین.");
  return L.join("\n");
}

// ---------------- alerts (/tick) ----------------
// Level touch: once per level per trading day; bars are DaryaGold-converted 1-minute bars since the last check.
export function levelAlerts(levels, bars, { day, sent = {}, snapAtMs = 0 }) {
  const out = [];
  for (const L of levels) {
    if (L.glued) continue;
    const key = `lvl:${day}:${p1(L.price)}`;
    if (sent[key]) continue;
    const hit = bars.filter((b) => b[0] >= snapAtMs && b[2] >= L.lo && b[3] <= L.hi);
    if (!hit.length) continue;
    const prev = bars[bars.indexOf(hit[0]) - 1], last = bars[bars.length - 1];
    const fromBelow = prev ? prev[4] < L.lo : hit[0][1] < L.price;
    const through = fromBelow ? last[4] > L.hi : last[4] < L.lo;
    const kind = fromBelow ? "مقاومت" : "حمایت";
    const head = through ? `از سطح \`${p1(L.price)}\` ${fromBelow ? "بالاتر" : "پایین‌تر"} رفت` : `به محدوده‌ی سطح \`${p1(L.price)}\` رسید`;
    out.push({ key, text: `**📍 قیمت ${head}**\n~~${kind}${L.label ? " · " + L.label : ""} · ${hmOf(last[0] + 60000)} به وقت تهران~~\n\nدریاگلد \`${px(last[4])}\`` });
  }
  return out.slice(0, 2);
}
export function trendAlerts(prev, now, summary, atMs) {
  const out = [];
  for (const tf of ["M15", "H1"]) {
    if (!prev || !prev[tf] || prev[tf] === now[tf]) continue;
    out.push(`**🔄 تغییر روند ${TF_FA[tf]}**\n~~از ${prev[tf]} به ${now[tf]} · ${hmOf(atMs)} به وقت تهران~~\n\nروند کلی: ${summary.line}`);
  }
  return out;
}
// Volatility from completed M5 bars: ATR(14) percentile over the last day, or one bar of 2.5× ATR.
export function volState(m5closed, nowMs) {
  if (!m5closed || m5closed.length < 60) return null;
  const a = atrSeries(m5closed), last = a[a.length - 1], hist = a.slice(-288);
  const pct = (hist.filter((x) => x <= last).length / hist.length) * 100;
  const b = m5closed[m5closed.length - 1], big = b[2] - b[3] >= 2.5 * a[a.length - 2];
  const m = tehParts(nowMs).min, active = m >= 10 * 60 + 30 && m < 22 * 60 + 30;
  const state = pct >= 90 || big ? "high" : pct <= 10 && active ? "low" : "normal";
  return { state, atr: r2(last), pct: Math.round(pct), big };
}
export function volAlert(v, atMs) {
  if (v.state === "high") return `**🌪 بازار خیلی پرنوسان است**\n~~نوسان ۵ دقیقه حدود ${Math.round(v.atr * 10) / 10} دلار` +
    (v.big ? "؛ یک کندل ۵ دقیقه‌ای بیش از ۲٫۵ برابر میانگین" : `؛ بالاتر از ${v.pct}٪ یک روز اخیر`) + ` · ${hmOf(atMs)} به وقت تهران~~\n\nحد ضرر باید دورتر باشد؛ حجم کمتر را در نظر بگیر.`;
  if (v.state === "low") return `**😴 بازار خیلی کم‌تحرک است**\n~~نوسان ۵ دقیقه حدود ${Math.round(v.atr * 10) / 10} دلار؛ پایین‌تر از ۹۰٪ یک روز اخیر · ${hmOf(atMs)} به وقت تهران~~\n\nحرکت‌ها کوتاه‌اند؛ هدف‌های نزدیک‌تر واقع‌بینانه‌ترند.`;
  return null;
}
const NEWS_FA = [[/non-?farm|nfp/i, "اشتغال غیرکشاورزی آمریکا (NFP)"], [/core cpi/i, "تورم هسته‌ی مصرف‌کننده‌ی آمریکا (Core CPI)"],
  [/\bcpi\b/i, "تورم مصرف‌کننده‌ی آمریکا (CPI)"], [/core pce/i, "شاخص PCE هسته"], [/\bppi\b/i, "تورم تولیدکننده‌ی آمریکا (PPI)"],
  [/fomc.*(statement|rate|decision)|federal funds|rate decision/i, "تصمیم نرخ بهره‌ی فدرال رزرو"], [/fomc.*minutes/i, "صورت‌جلسه‌ی فدرال رزرو"],
  [/powell/i, "سخنرانی پاول، رئیس فدرال رزرو"], [/fomc member|fed governor|fed chair|speaks/i, "سخنرانی مقام فدرال رزرو"],
  [/gdp/i, "تولید ناخالص داخلی آمریکا (GDP)"], [/retail sales/i, "خرده‌فروشی آمریکا"], [/unemployment claims|jobless/i, "مدعیان بیمه‌ی بیکاری آمریکا"],
  [/ism/i, "شاخص ISM آمریکا"]];
export const newsFa = (label) => { for (const [re, fa] of NEWS_FA) if (re.test(label || "")) return fa; return String(label || "خبر مهم"); };
export function newsAlerts(news, nowMs, sent = {}, leadMin = 12) {
  const due = newsList(news).filter((w) => isMajor(w) && w.eventMs > nowMs && w.eventMs - nowMs <= leadMin * 60000 && !sent[`news:${w.label}|${w.eventMs}`]);
  if (!due.length) return [];
  const byT = new Map();
  for (const w of due) { const k = w.eventMs; if (!byT.has(k)) byT.set(k, []); byT.get(k).push(w); }
  return [...byT.entries()].map(([t, ws]) => {
    const mins = Math.max(1, Math.round((t - nowMs) / 60000));
    const names = [...new Set(ws.map((w) => newsFa(w.label)))];
    const a = Math.min(...ws.map((w) => w.startMs)), z = Math.max(...ws.map((w) => w.endMs));
    return { keys: ws.map((w) => `news:${w.label}|${w.eventMs}`),
      text: `**📰 خبر مهم تا ${mins} دقیقه‌ی دیگر**\n~~ساعت ${hmOf(t)} به وقت تهران~~\n\n${names.join("\n")}\n\nپنجره‌ی پرهیز \`${hmOf(a)}\` تا \`${hmOf(z)}\`؛ در این بازه ستاپی چیده نمی‌شود.` };
  });
}

// ---------------- silent outcome tracking of every shown setup ----------------
// rows: setups (DaryaGold prices); bars: 1-minute BID bars; each row carries the bid->DaryaGold offset it was built with.
export function resolveSetup(row, bars, nowMs) {
  const dir = row.side === "BUY" ? 1 : -1, off = Number(row.dg_bid_offset) || 0;
  const lo = Number(row.entry_lo), hi = Number(row.entry_hi), sl = Number(row.sl), tp1 = Number(row.tp1), tp2 = Number(row.tp2);
  const created = Date.parse(row.created_at), until = Date.parse(row.valid_until);
  const upd = {};
  let status = row.status, filledAt = row.filled_at ? Date.parse(row.filled_at) : null;
  let mfe = Number(row.mfe_usd) || 0, mae = Number(row.mae_usd) || 0, tp1hit = !!row.tp1_hit, tp2hit = !!row.tp2_hit;
  const mid = (lo + hi) / 2;
  for (const b of bars) {
    if (b[0] < created || (status !== "pending" && status !== "filled")) continue;
    const h = b[2] + off, l = b[3] + off;   // chart price; a buy order/stop compares the ask = chart + spread
    if (status === "pending") {
      if (b[0] >= until) { status = "expired"; break; }
      const fill = dir < 0 ? h >= lo : l + SPREAD <= hi;
      const broke = dir < 0 ? h + SPREAD >= sl : l <= sl;
      const missed = dir < 0 ? l + SPREAD <= tp1 : h >= tp1;
      if (!fill && broke) { status = "invalidated"; break; }
      if (!fill && missed) { status = "missed"; break; }
      if (!fill) continue;
      status = "filled"; filledAt = b[0];
    }
    mfe = Math.max(mfe, dir < 0 ? mid - l : h - mid); mae = Math.max(mae, dir < 0 ? h - mid : mid - l);
    const slHit = dir < 0 ? h + SPREAD >= sl : l <= sl;
    if (slHit) { status = tp1hit ? "tp1" : "sl"; upd.sl_hit = true; break; }   // same bar as a target: count the stop first
    if (dir < 0 ? l + SPREAD <= tp1 : h >= tp1) tp1hit = true;
    if (dir < 0 ? l + SPREAD <= tp2 : h >= tp2) { tp2hit = true; status = "tp2"; break; }
    if (b[0] - filledAt > 6 * 3.6e6) { status = tp1hit ? "tp1" : "timeout"; break; }
  }
  if (status === "pending" && nowMs >= until && (!bars.length || bars[bars.length - 1][0] >= until - 60000)) status = "expired";
  Object.assign(upd, { status, tp1_hit: tp1hit, tp2_hit: tp2hit, mfe_usd: r2(mfe), mae_usd: r2(mae), checked_at: new Date(nowMs).toISOString() });
  if (filledAt) upd.filled_at = new Date(filledAt).toISOString();
  if (!["pending", "filled"].includes(status)) upd.resolved_at = new Date(nowMs).toISOString();
  return upd;
}
