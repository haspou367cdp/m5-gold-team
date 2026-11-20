// Price calibration (Phase 2): owner-entered DaryaGold prices paired with the Dukascopy feed.
// Pure helpers; app.js does the network/database work. Basis = DaryaGold price - reference price.
// ONE basis since 2026-11-21 (owner t244u): DaryaGold = Dukascopy mid + offset. New samples are stored against the mid
// ("dukascopy_mid"); older "dukascopy_bid" samples are converted (basis - half the feed spread, or - 0.175 when unknown).
export const CAL = {
  WINDOW_DAYS: 7,         // samples used for stats
  MIN_SAMPLES: 5,         // fewer -> not calibrated (keep the current/default offset)
  MAX_STD: 0.5,           // wider spread of basis -> not calibrated
  MAX_LATEST_AGE_H: 72,   // newest sample older than this -> not calibrated
  MAX_FEED_AGE_S: 180,    // feed bar older than this when the price was entered -> DATA_UNAVAILABLE
  NORMAL: 0.30, MINOR: 0.75, ELEVATED: 2.00,   // |basis - expected| thresholds (USD)
};
export const STATUS_FA = {
  NORMAL_ALIGNMENT: "هم‌راستا", MINOR_BASIS: "اختلاف جزئی", ELEVATED_BASIS: "اختلاف زیاد",
  FEED_DESYNCHRONIZATION: "ناهمگامی داده‌ی مرجع", DATA_UNAVAILABLE: "داده‌ی مرجع در دسترس نیست",
};
const SESSION_FA = { asia: "آسیا", london: "لندن", newyork: "نیویورک", closed: "بسته" };
const FA = "۰۱۲۳۴۵۶۷۸۹";
const digits = (t) => String(t).replace(/[۰-۹]/g, (c) => String(FA.indexOf(c))).replace(/[٠-٩]/g, (c) => String("٠١٢٣٤٥٦٧٨٩".indexOf(c)));
const r2 = (x) => Math.round(x * 100) / 100;
const sgn = (x) => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(r2(x));

export function parseCalibrate(args) {
  const nums = args.map((a) => digits(a).replace(/[٫,]/g, ".").trim()).filter(Boolean);
  if (nums.length < 1 || nums.length > 2 || !nums.every((t) => /^\d{3,5}(\.\d{1,3})?$/.test(t))) throw new Error("bad");
  const price = parseFloat(nums[0]), ask = nums[1] ? parseFloat(nums[1]) : null;
  if (!(price > 500 && price < 20000) || (ask !== null && !(ask >= price && ask - price <= 5))) throw new Error("bad");
  return { price, ask };
}
// Tehran trading sessions inside the DaryaGold day (07:00-00:30)
export function sessionOf(hm) {
  if (hm >= "07:00" && hm < "11:15") return "asia";
  if (hm >= "11:15" && hm < "16:15") return "london";
  if (hm >= "16:15" || hm < "00:30") return "newyork";
  return "closed";
}
export function parseDuka(text) {
  const t = String(text || "");
  const a = t.indexOf("("), b = t.lastIndexOf(")");
  const rows = JSON.parse(a >= 0 && b > a ? t.slice(a + 1, b) : t);
  if (!Array.isArray(rows)) throw new Error("bad feed");
  return rows.filter((r) => Array.isArray(r) && r.length >= 5 && Number.isFinite(r[0]) && Number.isFinite(r[4]));
}
// Latest 1-minute bar at or before `nowMs`; age = seconds since that bar's last tick could have been (bar end, capped at now).
export function pickFeed(bid, ask, nowMs) {
  const b = bid.filter((r) => r[0] <= nowMs).sort((x, y) => x[0] - y[0]).pop();
  if (!b) return null;
  const a = ask.find((r) => r[0] === b[0]);
  const end = Math.min(b[0] + 60000, nowMs);
  return { feed_bid: b[4], feed_ask: a ? a[4] : null, bar_at: new Date(b[0]).toISOString(), age_s: Math.round((nowMs - end) / 1000) };
}
export function basisStatus(basis, expected, feedOk = true) {
  if (!feedOk || !Number.isFinite(basis)) return "DATA_UNAVAILABLE";
  const d = Math.abs(basis - (Number(expected) || 0));
  if (d <= CAL.NORMAL) return "NORMAL_ALIGNMENT";
  if (d <= CAL.MINOR) return "MINOR_BASIS";
  if (d <= CAL.ELEVATED) return "ELEVATED_BASIS";
  return "FEED_DESYNCHRONIZATION";
}
const median = (v) => { const s = [...v].sort((a, b) => a - b), n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };
const std = (v) => { if (v.length < 2) return null; const m = v.reduce((a, b) => a + b, 0) / v.length; return Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / (v.length - 1)); };
// rows: {observed_at ISO, basis_usd, reference, session, status}
const HALF = 0.175;
const midBasis = (r) => {
  const b = Number(r.basis_usd);
  if (r.reference === "dukascopy_mid") return b;
  const fb = Number(r.feed_bid), fa = Number(r.feed_ask);
  return r2(b - (Number.isFinite(fb) && Number.isFinite(fa) && fa > fb && r.feed_ask !== null && r.feed_bid !== null ? (fa - fb) / 2 : HALF));
};
export function basisStats(rows, nowMs) {
  const since = nowMs - CAL.WINDOW_DAYS * 86400000;
  rows = rows.map((r) => (r.reference === "dukascopy_bid" && r.basis_usd !== null && r.basis_usd !== undefined ? { ...r, reference: "dukascopy_mid", basis_usd: midBasis(r) } : r));
  const use = rows.filter((r) => r.reference === "dukascopy_mid" && r.status !== "DATA_UNAVAILABLE" && r.basis_usd !== null &&
    Number.isFinite(Number(r.basis_usd)) && Date.parse(r.observed_at) >= since && Date.parse(r.observed_at) <= nowMs)
    .sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at));
  const v = use.map((r) => Number(r.basis_usd));
  const latest = use.length ? use[use.length - 1] : null;
  const ageH = latest ? (nowMs - Date.parse(latest.observed_at)) / 3.6e6 : null;
  const by = {};
  for (const r of use) (by[r.session] = by[r.session] || []).push(Number(r.basis_usd));
  const bySession = Object.fromEntries(Object.entries(by).map(([k, x]) => [k, { count: x.length, median: r2(median(x)) }]));
  const m = median(v), sd = std(v);
  const why = [];
  if (v.length < CAL.MIN_SAMPLES) why.push("few");
  if (sd !== null && sd > CAL.MAX_STD) why.push("wide");
  if (ageH !== null && ageH > CAL.MAX_LATEST_AGE_H) why.push("old");
  const calibrated = why.length === 0 && v.length >= CAL.MIN_SAMPLES;
  const other = rows.filter((r) => r.reference !== "dukascopy_mid").length;
  return { count: v.length, median: m === null ? null : r2(m), std: sd === null ? null : Math.round(sd * 1000) / 1000,
    latest: latest ? { basis: Number(latest.basis_usd), observed_at: latest.observed_at } : null,
    latest_age_h: ageH === null ? null : Math.round(ageH * 10) / 10, by_session: bySession,
    calibrated, offset: calibrated ? r2(m) : null, why, other_reference_samples: other };
}
const faN = (x) => String(x).replace(/\d/g, (c) => FA[+c]).replace(".", "٫");
export function statsLines(st, cur) {
  const L = [`نمونه‌های ${faN(CAL.WINDOW_DAYS)} روز اخیر: ${faN(st.count)}` +
    (st.count ? ` · میانه ${faN(sgn(st.median))} · انحراف معیار ${st.std === null ? "—" : faN(r2(st.std))}` : "")];
  const ses = Object.entries(st.by_session).map(([k, x]) => `${SESSION_FA[k] || k} ${faN(x.count)} (${faN(sgn(x.median))})`);
  if (ses.length) L.push("به تفکیک بازار: " + ses.join(" · "));
  if (st.latest_age_h !== null) L.push(`آخرین نمونه ${faN(st.latest_age_h)} ساعت پیش`);
  if (st.calibrated) L.push(`✅ اختلاف دریاگلد از این به بعد ${faN(sgn(st.offset))} دلار (میانه‌ی نمونه‌ها)`);
  else {
    const why = st.why.map((w) => ({ few: `حداقل ${faN(CAL.MIN_SAMPLES)} نمونه لازم است`, wide: "پراکندگی نمونه‌ها زیاد است", old: "نمونه‌ها قدیمی‌اند" }[w])).join("، ");
    L.push(`⏳ کالیبره نشده؛ اختلاف فعلی ${faN(sgn(cur))} دلار می‌ماند${why ? ` (${why})` : ""}`);
  }
  return L;
}
export const CAL_HELP = "**🎯 کالیبره‌کردن قیمت**\n~~قیمت فعلی دریاگلد را بفرستید، مثل:~~ `/calibrate 3569.85`\n~~با قیمت خرید:~~ `/calibrate 3569.85 3570.10`";
