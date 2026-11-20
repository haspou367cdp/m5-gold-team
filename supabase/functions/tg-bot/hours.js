// DaryaGold market hours, derived from New York time (owner t247u, 2026-11-21) so US daylight saving is followed:
// opens Sunday 17:00 NY, daily close 16:00 NY and reopen 17:00 NY (1 h break), last close Friday 16:00 NY,
// Friday no new setups from 15:00 NY (1 h before the close). Winter (EST) in Tehran: open 01:30, close 00:30,
// Friday cutoff 23:30; summer (EDT): 00:30 / 23:30 / 22:30. Tehran is UTC+3:30 with no DST.
// The bot's own automatic alerts/briefs start at 07:00 Tehran every day (ALERT_FROM_MIN), unchanged.
export const NY_OPEN_MIN = 17 * 60, NY_CLOSE_MIN = 16 * 60, NY_FRI_CUT_MIN = 15 * 60, ALERT_FROM_MIN = 7 * 60;
const H = 3.6e6, TEH = 210 * 60000;

// US rule since 2007: EDT from the 2nd Sunday of March 02:00 EST (07:00 UTC) to the 1st Sunday of November 02:00 EDT (06:00 UTC)
function nthSundayUtc(y, month, n) {   // month 0-based; date of the n-th Sunday
  const first = new Date(Date.UTC(y, month, 1)).getUTCDay();
  return 1 + ((7 - first) % 7) + 7 * (n - 1);
}
export function nyOffsetMin(ms) {   // minutes to add to UTC to get New York local time (-300 EST, -240 EDT)
  const y = new Date(ms).getUTCFullYear();
  const start = Date.UTC(y, 2, nthSundayUtc(y, 2, 2), 7), end = Date.UTC(y, 10, nthSundayUtc(y, 10, 1), 6);
  return ms >= start && ms < end ? -240 : -300;
}
const partsAt = (ms, offMin) => {
  const t = new Date(ms + offMin * 60000), p = (n) => String(n).padStart(2, "0");
  return { date: `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())}`, dow: t.getUTCDay(),
    min: t.getUTCHours() * 60 + t.getUTCMinutes(), hm: `${p(t.getUTCHours())}:${p(t.getUTCMinutes())}` };
};
export const nyParts = (ms) => partsAt(ms, nyOffsetMin(ms));
export const tehP = (ms) => partsAt(ms, 210);
// UTC ms of a New York wall-clock time (date "YYYY-MM-DD", minutes after midnight)
export function nyToMs(date, min) {
  const base = Date.parse(date + "T00:00:00Z") + min * 60000;
  let ms = base + 300 * 60000;                   // guess EST
  ms = base - nyOffsetMin(ms) * 60000;           // correct with the offset in force then
  return ms;
}
const addDays = (date, n) => new Date(Date.parse(date + "T00:00:00Z") + n * 864e5).toISOString().slice(0, 10);

// trading day (NY date the session closes on): a session opens 17:00 NY the day before and closes 16:00 NY
export function tradingDay(ms) {
  const n = nyParts(ms);
  return n.min >= NY_OPEN_MIN ? addDays(n.date, 1) : n.date;
}
export function marketOpen(ms) {
  const n = nyParts(ms);
  if (n.min >= NY_CLOSE_MIN && n.min < NY_OPEN_MIN) return false;   // daily break (Mon-Thu) / after Friday close
  const td = tradingDay(ms), dow = new Date(td + "T00:00:00Z").getUTCDay();
  return dow >= 1 && dow <= 5;                                       // trading days Mon-Fri (Sunday 17:00 = Monday's session)
}
export const sessionCloseMs = (ms) => nyToMs(tradingDay(ms), NY_CLOSE_MIN);
export const sessionOpenMs = (ms) => nyToMs(addDays(tradingDay(ms), -1), NY_OPEN_MIN);
export function fridayCutMs(ms) {   // Friday 15:00 NY of this trading day, or null if not a Friday session
  const td = tradingDay(ms);
  return new Date(td + "T00:00:00Z").getUTCDay() === 5 ? nyToMs(td, NY_FRI_CUT_MIN) : null;
}
// automatic alerts/briefs: market open, and not in the quiet part from a session open (same Tehran date) until 07:00 Tehran
export function alertWindowMs(ms) {
  if (!marketOpen(ms)) return false;
  const t = tehP(ms);
  if (t.min >= ALERT_FROM_MIN) return true;
  return tehP(sessionOpenMs(ms)).date !== t.date;   // still the tail of the session that opened on an earlier Tehran date
}
// Tehran wall-clock hours of the session in force (or the next one) — for messages
export function hoursFa(ms = Date.now()) {
  let probe = ms;
  for (let i = 0; i < 4 * 288 && !marketOpen(probe); i++) probe += 300000;
  const o = tehP(sessionOpenMs(probe)).hm, c = tehP(sessionCloseMs(probe)).hm;
  const td = tradingDay(probe);
  let f = tehP(nyToMs(td, NY_FRI_CUT_MIN)).hm;
  return { open: o, close: c, friCut: f };
}
