# Telegram redesign — before / after

Rendered on the `telegram-redesign` branch from the live 20 Nov 2026 16:40 Tehran snapshot (`data/levels.json` + `latest_brief.json`: DaryaGold `3575.5`, ATR M5 `5.56`, news window Waller B until 17:25). Message clock for /levels and /brief is 19:30 Tehran. Layout only; these are not a new live signal.

Prices in `code` stay Latin for tap-to-copy. After Telegram `render()`, other digits become Persian.

---

## 1. Signal

### Before (the card the owner saw)

```
🔴 فروش طلا
سفارش محدود · اعتبار تا ۱۶:۰۰

▸ ورود    3595.4
▸ حد ضرر  3597.2
▸ هدف     3566.4

یک واحد · ریسک ۱۸۵ هزار تومان · نسبت ۱۲٫۳
```

### After (same numbers, redesigned; this setup is now rejected — it would not be sent)

```
🔴 فروش طلا
سفارش محدود · اعتبار تا ۱۶:۰۰ به وقت تهران
شناسه `S-20261120-001`

▸ ورود    `3595.4`
▸ حد ضرر  `3597.2`
▸ هدف     `3566.4`

یک واحد · ریسک 158 هزار تومان · نسبت 14.6
```

The 185k figure was wrong: a LIMIT should be `1.8 × 80,000 + 14,000 = 158,000` (fee once, no spread). Net R:R on those card prices is 14.6, not 12.3. The bot now refuses this setup (tight stop vs 0.5×ATR, limit 19.9$ from price, entry above the M15 invalidation 3590.4, TP beyond the ADR/3×ATR cap, stop-out buffer, R:R above 8) and answers NO TRADE instead of re-arming an expired card.

---

## 2. NO TRADE card (`/scan`)

### Before (owner paste, around 18:30 Tehran)

```
⏸ فعلاً معامله نه
پنجره‌ی خبری تا ۱۸:۴۵

طلا  3576.6
H4 نزولی  ·  H1 نزولی  ·  M15 خنثی  ·  M5 خنثی
جمع‌بندی: نزولی
نوسان M5 حدود ۹ دلار · تا سطح بعدی ۴ دلار؛ جا کم است

بالا
▸ 3595.3  (+۱۸٫۸)  خیلی مهم
  سقف لندن + سوئینگ H1  ·  ۲ تماس M15
  پهنه  3594.1–3596.6
▸ 3600.3  (+۲۳٫۷)  مهم
  عدد رُند  ·  ۳ تماس M15
  پهنه  3599.0–3601.6

پایین
▸ 3572.9  (−۳٫۶)  مهم
  بازگشایی نیویورک  ·  ۸ تماس M15
  پهنه  3571.7–3574.2
▸ 3565.3  (−۱۱٫۳)  مهم
  بازگشایی لندن  ·  ۶ تماس M15
  پهنه  3564.0–3566.6
```

### After (live 16:40 snapshot, rendered at 19:30 Tehran)

```
⏸ فعلاً معامله نه
پنجره‌ی خبری تا 17:25

طلا  `3575.5`  ·  دریاگلد  ·  16:40 به وقت تهران
منبع: Dukascopy
رژیم: خبری  ·  جهت: نزولی
خبر: پنجره‌ی جاری تا 17:25
H4 نزولی  ·  H1 نزولی  ·  M15 خنثی  ·  M5 نزولی
جمع‌بندی: نزولی
پهنه سطح  ±1.4 دلار
نوسان M5 حدود 6 دلار · تا سطح بعدی 9 دلار؛ جا کم است

بالا
▸ `3595.3`  +19.9$ ≈ 3.6 ATR
  سقف لندن + سوئینگ H1
▸ `3600.3`  +24.8$ ≈ 4.5 ATR
  رُند 3600

پایین
▸ `3566.4`  −9.1$ ≈ 1.6 ATR
  VWAP
▸ `3562.5`  −13.0$ ≈ 2.3 ATR
  OR لندن
```

The reason and its clear time lead the card. The 2+2 zones are “where price is”: no entry / stop / target wording, no «مهم» / «خیلی مهم», no M15 touch count. Zone width is ±max(0.25×ATR M5, 1$) = ±1.4$ on this snapshot.

---

## 3. `/levels`

### Before (same shared block as the old NO TRADE card, plus a title)

```
سطوح
جمعه ۲۹ آبان · ۱۹:۳۰

طلا  3576.6
H4 نزولی  ·  H1 نزولی  ·  M15 خنثی  ·  M5 خنثی
جمع‌بندی: نزولی
نوسان M5 حدود ۹ دلار · تا سطح بعدی ۴ دلار؛ جا کم است

بالا
▸ 3595.3  (+۱۸٫۸)  خیلی مهم
  سقف لندن + سوئینگ H1  ·  ۲ تماس M15
  پهنه  3594.1–3596.6
…
```

### After (same 16:40 snapshot, rendered at 19:30 Tehran)

```
سطوح
جمعه 29 آبان · 19:30 به وقت تهران

طلا  `3575.5`  ·  دریاگلد  ·  16:40 به وقت تهران
منبع: Dukascopy
رژیم: خبری  ·  جهت: نزولی
خبر: پنجره‌ی جاری تا 17:25
H4 نزولی  ·  H1 نزولی  ·  M15 خنثی  ·  M5 نزولی
جمع‌بندی: نزولی
پهنه سطح  ±1.4 دلار
نوسان M5 حدود 6 دلار · تا سطح بعدی 9 دلار؛ جا کم است

بالا
▸ `3595.3`  +19.9$ ≈ 3.6 ATR
  سقف لندن + سوئینگ H1
▸ `3600.3`  +24.8$ ≈ 4.5 ATR
  رُند 3600

پایین
▸ `3566.4`  −9.1$ ≈ 1.6 ATR
  VWAP
▸ `3562.5`  −13.0$ ≈ 2.3 ATR
  OR لندن
```

`/brief` and the London / New York pre-session cards use this same block, then remaining news (if more than one window) and, in the private copy only, balance and the daily loss cap.

---

## 4. Daily report (private)

There was no previous daily-report card in the owner paste. After:

```
📊 گزارش روز
جمعه 29 آبان

🎯 سیگنال 1 · ورود 0 · وارد نشدم 0 · منقضی 1
📒 معامله‌ی بسته 2 · سود 1 · ضرر 1 · نرخ برد 50٪
📐 جمع +0.2R
💰 نتیجه‌ی خالص +23٬000 تومان
🕶 ستاپ ردشده با فیلتر: 0
🔭 پیگیری سیگنال: هدف 0 · حد ضرر 0 · پر نشد 1
🎚 قیمت دریاگلد: کالیبره نشده
```

The group copy of the same report drops every toman figure, the balance line, and the calibration line.

---

## Other cards (same typography, not pasted in full)

- `/brief` and ☀️/🌆 pre-session: title, Tehran clock, shared levels block, leftover news, private balance.
- `/shadow`, `/journal`, `/pnl`, confirmations, `/calibrate`, Friday 23:30 cutoff reminder, 00:30 close reminder: short title, italic subtitle, Latin times and prices in `code`, «ضرر» never «زیان», no disclaimer.
- Group variants of signals and briefs still strip toman and equity; buttons stay on the owner copy only.
