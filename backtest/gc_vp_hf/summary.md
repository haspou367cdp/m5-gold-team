# gc_vp_hf — GC (COMEX) volume-profile levels on XAUUSD M5, confirmation entries — SUMMARY
**Verdict: EXPLORATORY and UNDERPOWERED (~4 months, 176 snapshots). This study cannot PASS.**
Pre-declared reading: **H_rev (reversal) = no evidence**, with GC levels doing *worse* than their controls. **H_cont (continuation) = "positive hint"**.
The hint is fragile. The GC continuation trades still lose money in total (−0.13R net per trade, all trades). The paired gain
appears only in the subset where the control also triggered, and unpaired it is +0.045R (p=0.29).
Run 2026-11-13 08:23–08:26 Asia/Tehran by M5-Journal. Prereg: PREREG_gc_vp.md (hashed before any level or outcome).

## Headline numbers (net R after $0.56 fixed round-trip cost; R = PnL / 1 ATR_M5 stop)
Paired = level minus its own control, counting only pairs where both sides traded. Day-block bootstrap, one-sided, 5000 reps, seed 20261113. Holm across the 2 hypotheses.

| source | hypothesis | pairs | level R | control R | paired diff | p_day | p_Holm | half A diff (n) | half B diff (n) | reading |
|---|---|---|---|---|---|---|---|---|---|---|
| GC VP | H_rev | 254 | −0.217 | −0.069 | **−0.148** | 0.990 | 0.990 | −0.078 (128) | −0.218 (126) | no evidence |
| GC VP | H_cont | 183 | +0.030 | −0.188 | **+0.219** (95% CI +0.05..+0.38) | 0.0066 | 0.013 | +0.199 (88) | +0.237 (95) | positive hint |
| levels.py | H_rev | 1043 | −0.117 | −0.071 | −0.047 | 0.878 | 0.878 | −0.017 | −0.075 | no evidence |
| levels.py | H_cont | 829 | +0.037 | −0.031 | +0.068 | 0.063 | 0.126 | +0.079 | +0.057 | no evidence |
| levels.py strong (score>=6), secondary | rev / cont | 426 / 348 | | | −0.022 / +0.070 | 0.65 / 0.11 | | | | – |

GC paired diff minus levels.py paired diff: rev −0.10R, cont +0.15R (descriptive only).

**Unpaired (secondary, post-hoc bootstrap in post_checks.py):**
- GC rev: levels −0.123R (n=331) vs controls −0.095R (n=282), diff −0.028, p=0.65.
- GC cont: levels −0.134R (n=243) vs controls −0.179R (n=200), diff +0.045, p=0.29.
- The 60 GC continuation trades whose control did not trigger averaged −0.63R. The H_cont paired result therefore depends on the both-sides-traded selection.
- levels.py unpaired: rev −0.000, cont +0.005.

**Other secondary results (GC, paired):**
- Continuation win rate was 46.4% for levels vs 37.7% for controls. PF was 1.05 vs 0.73. MFE was 1.28 vs 1.06 ATR.
- Reversal win rate was 36.6% for levels vs 42.5% for controls. PF was 0.70 vs 0.89.
- Confirmation came on average 1.6–2.1 M5 bars after the touch.
- No GC continuation trade hit the time stop.

**Splits (GC paired diff, small n):**
- Continuation: London (11:15) +0.14 (n=55), NY (16:15) +0.25 (n=128); outside news +0.24 (n=159), inside news +0.10 (n=24).
- Reversal: London −0.34, NY −0.03; inside news n=17.
- ATR tercile and trend balance hold by construction, since level and control share the same T.
- Full tables are in tab_primary.csv, tab_secondary.csv, tab_splits.csv and tab_ltype.csv.

## Data, timezone, coverage
- **Timezone:** the GC 1m timestamps are naive **America/Chicago** local time. I inferred this by cross-correlating 1m returns with Dukascopy XAUUSD from −12h to +12h. The raw peak is at +360 min (corr 0.71). After localizing to Chicago, the lag-0 correlation is 0.983 before DST and 0.985 after. Files: tz_lag_corr*.csv, step0*.log.
- **Front month:** GCG26 from 2025-11-21 to 2026-01-27, then GCJ26 from 2026-01-28 to 2026-03-27. That is 120,997 1m bars over 107 Tehran dates, median 1,378 bars/day. No back-adjustment, because levels are mapped through a same-contract basis.
- **Coverage:** 176 eligible snapshots (2 basis-short and 4 stale-XAU skipped). They produced 1,024 merged GC levels, of which 979 were eligible and 395 were touched.
- **Profile availability:** the prior-day profile exists at 172 snapshots and the prior-session profile at all 176. The prior session was Asia 161 times and London 15 times (London completes before 16:15 once US DST starts).
- **Basis, GC minus spot mid over the prior 60 min:**
  - median +18.55 (5–95% range −1.35..+33.17);
  - monthly medians: Nov +33.3, Dec +29.5, Jan +8.0 (min −4.7), Feb +20.1, Mar +4.8 (min −6.1);
  - large swings, which the per-snapshot rolling estimate absorbs; logged in basis_log.csv.
- **levels.py comparison** uses backtest/levels_bias/snapshots.pkl, which is point-in-time output of the unchanged tools/levels.py. The tools sha256 match today's files, and all 176 T were matched. levels.py was not re-run.

## Deviations / limits
1. **Hygiene, before the prereg:** the naive roll rule rolled on noise days in April 2025, when all contracts were deferred. I replaced it with a liquid-window, forward-only roll (described in the prereg).
2. **DEVIATION 1, after the prereg and before any outcome:** eval crashed when localizing the news-window columns to Tehran. I fixed it to use the CSV's datetime_utc ±15 min, which gives identical windows (verified 0 mismatches). The script was re-hashed before the run.
3. HVN/LVN were skipped. Order flow was skipped because there is no aggressor data. The Portara MGC format check was skipped.
4. tools/news_windows.py only reads the live JSON, so I used data/news_calendar_hist.csv. It shows the Oct–Nov 2025 shutdown-delayed releases.
5. Other limits:
   - only ~4 months in one regime;
   - fixed costs;
   - bid-path approximation;
   - trades from different levels at the same T overlap, which the day blocks handle only partly;
   - this is the 5th trial on the levels family, and Holm covers only the 2 hypotheses here.

## Persian summary
تست اکتشافی و کم‌توان: حجم واقعی بورس COMEX، حدود ۴ ماه (۳۰ آبان ۱۴۰۴ تا ۷ فروردین ۱۴۰۵)، ۱۷۶ اسنپ‌شات. این تست نمی‌تواند «قبول» بدهد.
- برگشت از سطوح POC/VAH/VAL حجم GC (ورود فقط بعد از تأیید کندل M5): **هیچ شاهدی**. این سطوح از قیمت‌های تصادفی هم‌فاصله بدتر بودند (−0.15R در هر معامله).
- ادامه‌ی حرکت بعد از شکست و پذیرش سطح: **نشانه‌ی ضعیف مثبت** طبق قاعده‌ی ازپیش‌ثبت‌شده (+0.22R نسبت به کنترل، p تعدیل‌شده 0.013، مثبت در هر دو نیمه). ولی خود این معاملات بعد از هزینه در مجموع زیان‌ده بودند (−0.13R). مقایسه‌ی بدون جفت‌سازی هم معنادار نبود (+0.045R، p=0.29). پس این فقط یک فرضیه برای تست مستقل بعدی است، نه مزیت.
- سطوح فعلی levels.py در همین دوره: نه در برگشت و نه در ادامه‌ی حرکت شاهدی نداشتند.
- منطقه‌ی زمانی داده‌ی GC شیکاگو تشخیص داده شد (همبستگی 0.98).

این تحقیق است و سیگنال معاملاتی نیست.

سطوح و جهت در بک‌تست ۲۰۲۰ تا ۲۰۲۶ از قیمت‌های تصادفی بهتر نبوده‌اند؛ اعتبارسنجی‌نشده و بدون مزیت آماری.
