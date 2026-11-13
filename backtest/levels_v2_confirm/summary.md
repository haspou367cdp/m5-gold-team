# levels_v2 independent confirmation 2020-2024: NET TRADING EDGE (prereg PREREG_v2_confirm.md)

**VERDICT: FAIL.** On the fixed fade rule, score>=4 levels lost MORE than matched control prices in every year 2020-2024.

Run by M5-Journal, 2026-11-13 (Asia/Tehran). Trial 2 on levels_v2 (trial 1 = levels_v2_build, p = 0.087, FAIL). Holm threshold p < 0.025.

## Timeline (file mtimes / hash log, Asia/Tehran)
- 08:09:52 frozen-code hashes verified (levels_v2.py 9aaeb469…, gen_levels.py 9def4b23… = levels_v2_build/HASHES.txt)
- 08:10:24 PREREG_v2_confirm.md written and hashed into ../PREREG_HASHES.txt (sha256 9d1a1190…62255), before levels and outcomes
- 08:10:45–08:11:12 levels generated with gen_confirm.py (only counts and the score histogram were looked at)
- 08:11:52 evaluate_confirm.py written (unit-tested on synthetic arrays only)
- 08:12:00 gen_confirm.py, levels CSV and evaluate_confirm.py hashed into ../PREREG_HASHES.txt, then the eval was started

## Criteria (all must hold)
| # | criterion | value | pass |
|---|---|---|---|
| a | day-block bootstrap one-sided p < 0.025 | p = 1.000 (diff 95% CI −0.159..−0.066 R) | no |
| b | paired diff >= +0.05 R/touch | **−0.112 R** | no |
| c | high-level mean net R > 0 | −0.647 R | no |
| d | diff > 0 in >= 4 of 5 years | 0 of 5 | no |
| e | >= 300 paired high touches | 3,850 | yes |
| f | week-block bootstrap p < 0.05 | p = 1.000 (CI −0.162..−0.062) | no |

## Key numbers
- Levels: 2,574 snapshots (of 2,610 candidates; the earliest Jan-2020 days had too little history), 72,452 level-rows, 0 errors.
  Score histogram: 0:37, 1:13,201, 2:15,787, 3:26,453, 4:13,364, 5:3,610.
- Eligible levels 71,233; controls 66,971; levels without a control 4,262 (high: 1,510 of 16,543).
- PRIMARY (paired, both touched, n = 3,850): high level −0.647 R, control −0.534 R, diff **−0.112 R**.
- Flat $0.50 round-trip cost: level −0.587, control −0.473, diff −0.114 R (p = 1.000). Cost assumptions don't change the result.
- Unpaired: 5,470 touched high levels −0.508 R vs 4,129 touched controls −0.456 R, diff −0.052 R (p_day = 0.989).
- Gross (before costs), paired: level −0.190 R vs control −0.077 R. Even with no costs, high levels are below their controls.
- H2 (high vs low score, net R): −0.037 R, one-sided p = 0.907. The score does not rank levels by profitability.
  By score (net R): 1: −0.36, 2: −0.50, 3: −0.45, 4: −0.48, 5: −0.57. Score 5 is the worst.

## Per-year (paired high, net R per touch)
| year | pairs | level R | control R | diff | diff (flat $0.50) | level win% | level PF | level rev% | ctrl rev% |
|---|---|---|---|---|---|---|---|---|---|
| 2020 | 762 | −0.676 | −0.547 | −0.129 | −0.133 | 32.4 | 0.33 | 72.6 | 73.1 |
| 2021 | 826 | −0.638 | −0.530 | −0.108 | −0.110 | 34.4 | 0.35 | 71.9 | 74.2 |
| 2022 | 798 | −0.680 | −0.575 | −0.105 | −0.107 | 31.6 | 0.33 | 72.7 | 75.4 |
| 2023 | 730 | −0.666 | −0.570 | −0.096 | −0.098 | 30.7 | 0.33 | 67.4 | 69.3 |
| 2024 | 734 | −0.570 | −0.447 | −0.123 | −0.121 | 32.6 | 0.39 | 71.0 | 68.1 |

## Secondary (paired high: level vs control)
Reversal% 71.2 vs 72.2; win rate 32.4% vs 36.9%; profit factor 0.35 vs 0.42; MAE 1.25 vs 1.18 ATR; MFE 1.42 vs 1.50 ATR;
time to reversal 1.24 vs 1.16 M5 bars; breakout-failure 57.8% vs 58.6%; exits stop/target/time 67.5/32.3/0.2% vs 63.0/36.8/0.2%.
Balance: level and control share T, so ATR tercile (1158/1331/1361 pairs) and trend (down 1844 / up 2006) are identical by
construction. The diff is negative in every ATR tercile (−0.19/−0.13/−0.03), both trend states (−0.08/−0.14) and both sides (res −0.12, sup −0.10).
Tables: tab_year_primary.csv, tab_year_paired_high.csv, tab_secondary.csv, tab_score.csv.

## Cost assumptions
Primary cost: the actual Dukascopy spread_c of the entry 1m bar (median $0.36), charged once per round trip, plus $0.20 slippage
(0.10 per side). Median cost ≈ 0.42 R (median ATR_M5 $1.16–1.76 per year). Robustness: flat $0.50 round trip.
The fade rule loses for both levels and controls, mostly because of costs: gross is about 0 R for everything. That is expected
for a 1 ATR stop / 1.5 ATR target on M5 gold. The decisive comparison is level vs control, and it is negative before and after costs.

## Deviations / problems
- No deviations from the prereg. No re-run.
- Print artifact (2026-11-13 ~08:17 Tehran): eval.log shows "entry_1m_found false -56150", caused by bitwise NOT on an
  object-dtype column. Checked from touches_confirm.csv: all 28,075 touches found their entry 1m bar. No effect on any number;
  not fixed, to keep the hashed script unchanged.
- MAE/MFE include the full range of the entry 1m bar (it can contain movement before the fill), so they are slightly overstated.

## Limitations
2020-2023 was the levels v1 in-sample period (v2 was not tuned there). Tick volume is a Dukascopy proxy, not COMEX volume.
The bid-path approximation charges the spread once. Fills are assumed at exactly the level price. Controls no longer exclude $5
round numbers, because levels_v2 has no round-number component; this differs from v2_build. Supply/demand zones, order blocks,
FVG and fib were not part of levels_v2 and were not tested.

## Files
PREREG_v2_confirm.md, gen_confirm.py, levels_v2_confirm_hist.csv, evaluate_confirm.py, touches_confirm.csv (all touches/trades),
pairs_high_confirm.csv, tab_*.csv, gen.log, eval.log, HASHES.txt; hash log ../PREREG_HASHES.txt.

## خلاصه‌ی فارسی
آزمون مستقل levels_v2 روی داده‌ی ۲۰۲۰ تا ۲۰۲۴ رد شد (FAIL). این آزمون از قبل ثبت شده بود.
یک قاعده‌ی ثابت تست شد: در اولین برخورد قیمت به سطح، خلاف جهت حرکت وارد معامله می‌شویم. حد ضرر ۱ برابر ATR است، حد سود ۱.۵ برابر ATR، و اگر هیچ‌کدام نخورد بعد از ۲ ساعت خارج می‌شویم. اسپرد واقعی و لغزش هم حساب شد.
سطوح با امتیاز ۴ و ۵ به‌طور میانگین در هر معامله −0.65R دادند. قیمت‌های کنترلِ هم‌فاصله در همان لحظه −0.53R دادند. یعنی سطوح حدود 0.11R در هر معامله بدتر بودند و در هر پنج سال نتیجه منفی بود.
بدون هزینه‌ی معامله هم سطوح از قیمت‌های کنترل بدتر بودند. امتیاز بالاتر هم سود بیشتری نداد؛ امتیاز ۵ بدترین نتیجه را داشت.
این نتیجه فقط مربوط به گذشته است و هیچ سیگنال یا پیشنهاد ورود، حد ضرر یا حد سودی برای معامله‌ی واقعی ندارد.
سطوح و جهت در بک‌تست ۲۰۲۰ تا ۲۰۲۶ از قیمت‌های تصادفی بهتر نبوده‌اند؛ اعتبارسنجی‌نشده و بدون مزیت آماری.
