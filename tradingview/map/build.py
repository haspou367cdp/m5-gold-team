#!/usr/bin/env python3
"""Builds the Persian and English «decision map» indicators from template.pine (identical logic, only texts differ)."""
import os, re, sys
D = os.path.dirname(os.path.abspath(__file__))
Z = "\u200c"  # ZWNJ (نیم‌فاصله)
FA_DIGITS = 'str.replace_all(str.replace_all(str.replace_all(str.replace_all(str.replace_all(str.replace_all(str.replace_all(str.replace_all(str.replace_all(str.replace_all(str.replace_all(s, "0", "۰"), "1", "۱"), "2", "۲"), "3", "۳"), "4", "۴"), "5", "۵"), "6", "۶"), "7", "۷"), "8", "۸"), "9", "۹"), ".", "٫")'
FA = {
 "LANG": "fa",
 "HDR1": "نقشه‌ی تصمیم برای اسکالپ طلا در دریاگلد، همراه بات Z A R V A •|• BTV",
 "HDR2": "دو سطح بالا و دو سطح پایین (همان سطح‌های بات)، نوار روند ۵ و ۱۵ دقیقه و ۱ و ۴ ساعت، فضای معامله و چراغ وضعیت بازار.",
 "HDR3": "ستاپ فقط وقتی معتبر باشد کشیده می‌شود: بازه‌ی ورود، حد ضرر، حد سود ۱ و ۲ با سود و ضرر تومانی بعد از کارمزد، و عدد اعتبار از ۰ تا ۱۰۰.",
 "G_INPUTS": "تنظیمات", "G_DISPLAY": "۱. نمایش", "G_PRICE": "۲. قیمت و هزینه‌ها", "G_SETUP": "۳. ستاپ‌ها", "G_TIME": "۴. ساعت‌ها و خبرها",
 "I_MODE": "حالت نمایش", "V_PHONE": "گوشی", "V_DESK": "دسکتاپ",
 "T_MODE": "گوشی: فقط سطح‌های نزدیک، نوار روند و بهترین ستاپ. دسکتاپ: هر چهار سطح با نام منبع و همه‌ی ستاپ‌ها.",
 "I_SIZE": "اندازه‌ی نوشته‌ها", "V_S": "کوچک", "V_M": "متوسط", "V_L": "بزرگ",
 "I_POS": "جای نوار روند", "V_TR": "بالا، راست", "V_TL": "بالا، چپ", "V_BR": "پایین، راست", "V_BL": "پایین، چپ",
 "I_NEAR": "گوشی: فقط سطح‌های نزدیک‌تر از این فاصله (دلار)",
 "I_FEED": "قیمت چارت", "T_FEED": "bid یعنی چارت قیمت فروش را نشان می‌دهد (OANDA و Dukascopy)، mid یعنی قیمت میانه.",
 "I_FSPR": "اسپرد معمول فید چارت (دلار)", "T_FSPR": "فقط برای تبدیل bid به میانه به کار می‌رود (همان ۰٫۳۵ پیش‌فرض بات).",
 "I_MOFF": "اختلاف قیمت دریاگلد با قیمت میانه (دلار)", "T_MOFF": "مثل بات: قیمت دریاگلد = قیمت میانه + این عدد (پیش‌فرض ۰٫۰۲)، برای سطح‌ها، قیمت زنده، ستاپ‌ها و هشدارها. اگر در بات با /offset عدد دیگری ثبت کرده‌اید، همان را اینجا بگذارید.",
 "T_FLAT": "بدون جهت", "T_FLATSUB": "قیمت در یک محدوده بالا و پایین می‌رود", "T_HALF15": "۱۵ دقیقه هم همین جهت است، ۵ دقیقه بی‌جهت", "T_HALF5": "۵ دقیقه هم همین جهت است، ۱۵ دقیقه بی‌جهت",
 "I_UNIT": "حجم", "V_1U": "یک واحد", "V_05U": "نیم واحد",
 "I_TPU": "تومان به ازای هر دلار حرکت، برای یک واحد", "I_FEE": "کارمزد هر معامله (تومان، یک بار)",
 "I_SPR": "حاشیه‌ی اسپرد (دلار)",
 "T_SPR": "مثل بات: خرید با قیمت خرید (ask) پر می‌شود، پس بازه‌ی ورود خرید و حد ضرر و حد سود فروش به همین اندازه بالاتر گذاشته می‌شوند.",
 "I_SHOWSET": "نمایش ستاپ‌ها", "I_EXP": "اعتبار هر ستاپ (دقیقه)", "I_WARN": "ستاپ با اعتبار کمتر از این عدد علامت ⚠ بگیرد",
 "I_RRMIN": "کمترین نسبت سود به ضرر خالص تا حد سود ۱", "I_TPMIN": "کمترین فاصله‌ی حد سود ۱ از ورود (دلار)",
 "I_BUF": "سقف حد ضرر به‌اضافه‌ی حرکت معمول ۵ دقیقه (دلار)", "T_BUF": "اگر فاصله‌ی حد ضرر به‌اضافه‌ی اندازه‌ی معمول حرکت قیمت در ۵ دقیقه از این عدد بیشتر شود، ستاپ کشیده نمی‌شود تا به استاپ‌اوت (بسته‌شدن اجباری حساب) نزدیک نشوید.",
 "I_TGT": "تارگت معمول من (دلار)", "I_HOLD": "بعد از ورود، ستاپ تا چند دقیقه روی چارت بماند",
 "I_OPEN": "باز شدن دریاگلد به وقت نیویورک (یکشنبه و هر روز؛ ۱۷۰۰ = تهران ۰۱:۳۰ زمستان)", "I_CLOSE": "بسته شدن به وقت نیویورک (۱۶۰۰ = تهران ۰۰:۳۰ زمستان)",
 "I_FRI": "جمعه: ورود تازه ممنوع از ساعت (نیویورک؛ ۱۵۰۰ = تهران ۲۳:۳۰ زمستان)", "I_SOON": "هشدار نارنجی از چند دقیقه قبل از بسته شدن",
 "I_N830": "خبر ساعت ۸:۳۰ نیویورک (۱۷:۰۰ تهران در زمستان)", "I_N1000": "خبر ساعت ۱۰:۰۰ نیویورک (۱۸:۳۰ تهران در زمستان)",
 "I_N1400": "خبر ساعت ۱۴:۰۰ نیویورک، فدرال رزرو (۲۲:۳۰ تهران در زمستان)",
 "I_PRE": "از چند دقیقه قبل از خبر", "I_POST": "تا چند دقیقه بعد از خبر",
 "S_CONST": "ثابت‌ها", "S_AGG": "ساخت کندل‌های ۵ و ۱۵ دقیقه و ۱ و ۴ ساعت از روی چارت", "S_DAY": "روز، هفته، ماه و دامنه‌ی روزانه",
 "S_SESS": "سشن‌ها", "S_HOURS": "ساعت کار دریاگلد و خبرها", "S_LEVELS": "سطح‌ها (همان فرمول بات)", "S_EVAL": "محاسبه‌ی سطح‌ها و روند",
 "S_SETUP": "ستاپ‌ها و عدد اعتبار", "S_DRAW": "رسم (فقط روی آخرین کندل)",
 "K3": "سقف این هفته", "K4": "کف این هفته", "K5": "سقف هفته‌ی قبل", "K6": "کف هفته‌ی قبل", "K7": "سقف صبح امروز", "K8": "کف صبح امروز",
 "K9": "سقف ظهر امروز", "K10": "کف ظهر امروز", "K11": "سقف عصر", "K12": "کف عصر", "K13": "سقف عصر دیروز", "K14": "کف عصر دیروز",
 "K15": "شروع ظهر", "K17": "شروع عصر", "K20": "دو سقف هم‌اندازه", "K21": "دو کف هم‌اندازه", "K22": "عدد رُند", "K24": "نقطه‌ی برگشت اخیر",
 "K26": "سقف این ماه", "K27": "کف این ماه", "K28": "سقف ماه قبل", "K29": "کف ماه قبل",
 "T_UP": "صعودی (رو به بالا)", "T_DN": "نزولی (رو به پایین)", "T_UNK": "جهت روشن نیست",
 "T_DISAGREE": "۱ و ۴ ساعته با هم نمی‌خوانند", "T_CORR2": "کوتاه‌مدت فعلاً برعکس برگشته", "T_CORR15": "۱۵ دقیقه فعلاً برعکس برگشته",
 "T_CORR5": "۵ دقیقه فعلاً برعکس برگشته", "T_ALIGN": "کوتاه‌مدت هم همین جهت است", "T_LOWN": "کوتاه‌مدت فعلاً بی‌جهت",
 "FA_DIGITS": FA_DIGITS,
 "MONEY_EXPR": '(v1 >= 0 and v2 >= 0 ? "سود " : v1 < 0 and v2 < 0 ? "ضرر " : "") + f_fa((v1 < 0 and v2 >= 0 ? "−" : "") + a1) + " تا " + f_fa((v2 < 0 and v1 >= 0 ? "−" : "") + a2) + (mil ? " میلیون تومان" : " هزار تومان")',
 "LEFT_EXPR": 'f_fa(str.tostring(math.max(0, left))) + " دقیقه مانده"',
 "DIST_EXPR": 'f_fa(str.tostring(dist, "0.0")) + " دلار تا ورود"',
 "T_BUY": "خرید", "T_SELL": "فروش", "T_CRED": "اعتبار", "T_ACTIVE": "قیمت وارد بازه شد؛ حد ضرر را بگذارید", "T_INRANGE": "قیمت داخل بازه‌ی ورود است",
 "L_CLOSED": "دریاگلد بسته است", "L_FRI": "ورود جدید بسته است", "L_NEWS": "خبر مهم نزدیک است", "L_SOON": "بسته‌شدن دریاگلد نزدیک است",
 "L_HOT": "بازار خیلی پرنوسان است", "L_COLD": "بازار خیلی آرام است", "L_OK": "شرایط عادی",
 "R_OK": "جا برای سود هست", "R_LOW": "جا برای سود کم است",
 "T_ROOM": "فاصله تا سطح بعدی در جهت روند بزرگ، در مقایسه با تارگت معمول شما.",
 "T_TFWARN": "چارت را روی ۵ دقیقه یا کمتر بگذارید", "T_ADR": "مصرف حرکت معمول روزانه",
 "K1": "سقف دیروز", "K2": "کف دیروز", "K19": "میانگین قیمت امروز", "K_JOIN": "، ", "T_SLL": "حد ضرر", "T_TP1L": "حد سود ۱", "T_TP2L": "حد سود ۲",
}
EN = {
 "LANG": "en",
 "HDR1": "decision map for scalping gold on DaryaGold, companion to the Z A R V A •|• BTV bot",
 "HDR2": "two levels above and two below (the bot's levels), a 5m/15m/1H/4H trend strip, room to trade and a market-state light.",
 "HDR3": "Setups are drawn only when valid: entry range, SL, TP1 and TP2 with net toman after the fee, and a 0-100 credibility.",
 "G_INPUTS": "Inputs", "G_DISPLAY": "1. Display", "G_PRICE": "2. Price & costs", "G_SETUP": "3. Setups", "G_TIME": "4. Hours & news",
 "I_MODE": "Display mode", "V_PHONE": "Phone", "V_DESK": "Desktop",
 "T_MODE": "Phone: nearby levels, the trend strip and the best setup only. Desktop: all four levels with their sources and every live setup.",
 "I_SIZE": "Text size", "V_S": "Small", "V_M": "Normal", "V_L": "Large",
 "I_POS": "Trend strip position", "V_TR": "Top right", "V_TL": "Top left", "V_BR": "Bottom right", "V_BL": "Bottom left",
 "I_NEAR": "Phone: only levels closer than ($)",
 "I_FEED": "Chart price", "T_FEED": "bid = the chart shows the bid (OANDA, Dukascopy); mid = mid price.",
 "I_FSPR": "Typical chart-feed spread ($)", "T_FSPR": "Only used to turn bid into mid (the bot's default is 0.35).",
 "I_MOFF": "DaryaGold offset vs mid ($)", "T_MOFF": "Same as the bot: DaryaGold = mid + this value (default 0.02) for levels, the live price, setups and alerts. If you set another value with /offset in the bot, use it here too.",
 "T_FLAT": "Neutral", "T_FLATSUB": "4H and 1H show no clear direction", "T_HALF15": "15m aligned, 5m neutral", "T_HALF5": "5m aligned, 15m neutral",
 "I_UNIT": "Size", "V_1U": "1 unit", "V_05U": "0.5 unit",
 "I_TPU": "Toman per $1 move, 1 unit", "I_FEE": "Fee per trade (toman, charged once)",
 "I_SPR": "Spread margin ($)",
 "T_SPR": "As in the bot: a buy fills at the ask, so buy entry ranges and sell SL/TP are moved up by this amount.",
 "I_SHOWSET": "Show setups", "I_EXP": "Setup lifetime (minutes)", "I_WARN": "Mark setups below this credibility with ⚠",
 "I_RRMIN": "Minimum net R:R to TP1", "I_TPMIN": "Minimum TP1 distance ($)",
 "I_BUF": "Max SL + ATR ($)", "T_BUF": "If the SL distance plus the M5 ATR is above this, no setup is drawn (stop-out protection).",
 "I_TGT": "My usual target ($)", "I_HOLD": "Keep a setup on the chart this many minutes after entry",
 "I_OPEN": "DaryaGold open (HHMM New York; Sunday and daily; 1700 = 01:30 Tehran in winter)", "I_CLOSE": "Daily close (HHMM New York; 1600 = 00:30 Tehran in winter)",
 "I_FRI": "Friday: no new entries from (HHMM New York; 1500 = 23:30 Tehran in winter)", "I_SOON": "Orange warning this many minutes before the close",
 "I_N830": "08:30 New York release (17:00 Tehran in winter)", "I_N1000": "10:00 New York release (18:30 Tehran in winter)",
 "I_N1400": "14:00 New York, Fed (22:30 Tehran in winter)",
 "I_PRE": "Minutes before a release", "I_POST": "Minutes after a release",
 "S_CONST": "Constants", "S_AGG": "5m/15m/1H/4H bars built from the chart", "S_DAY": "Day, week, month, ADR",
 "S_SESS": "Sessions", "S_HOURS": "DaryaGold hours and news", "S_LEVELS": "Levels (same formulas as the bot)", "S_EVAL": "Levels and trend",
 "S_SETUP": "Setups and credibility", "S_DRAW": "Drawing (last bar only)",
 "K3": "Week high", "K4": "Week low", "K5": "Prev week high", "K6": "Prev week low", "K7": "Asia high", "K8": "Asia low",
 "K9": "London high", "K10": "London low", "K11": "NY high", "K12": "NY low", "K13": "Prev NY high", "K14": "Prev NY low",
 "K15": "London OR", "K17": "NY OR", "K20": "Equal highs", "K21": "Equal lows", "K22": "Round", "K24": "H1 swing",
 "K26": "Month high", "K27": "Month low", "K28": "Prev month high", "K29": "Prev month low",
 "T_UP": "Bullish", "T_DN": "Bearish", "T_UNK": "Unclear",
 "T_DISAGREE": "1H and 4H disagree", "T_CORR2": "15m and 5m correcting", "T_CORR15": "15m correcting",
 "T_CORR5": "5m correcting", "T_ALIGN": "All aligned", "T_LOWN": "Lower frames neutral",
 "FA_DIGITS": "s",
 "MONEY_EXPR": '(v1 >= 0 and v2 >= 0 ? "profit " : v1 < 0 and v2 < 0 ? "loss " : "") + (v1 < 0 and v2 >= 0 ? "−" : "") + a1 + " to " + (v2 < 0 and v1 >= 0 ? "−" : "") + a2 + (mil ? "M toman" : "k toman")',
 "LEFT_EXPR": 'str.tostring(math.max(0, left)) + " min left"',
 "DIST_EXPR": '"$" + str.tostring(dist, "0.00") + " to entry"',
 "T_BUY": "Buy", "T_SELL": "Sell", "T_CRED": "credibility", "T_ACTIVE": "Entered; set your SL", "T_INRANGE": "Price in entry range",
 "L_CLOSED": "DaryaGold closed", "L_FRI": "No new entries", "L_NEWS": "News near", "L_SOON": "Close near",
 "L_HOT": "Volatile", "L_COLD": "Quiet", "L_OK": "Good",
 "R_OK": "room", "R_LOW": "tight",
 "T_ROOM": "Distance to the next level in the overall trend direction, compared with your usual target.",
 "T_TFWARN": "Use a 5-minute or lower chart", "T_ADR": "ADR used",
 "K1": "PDH", "K2": "PDL", "K19": "VWAP", "K_JOIN": " + ", "T_SLL": "SL", "T_TP1L": "TP1", "T_TP2L": "TP2",
}
def build(tpl, d):
    out = tpl
    for k, v in d.items():
        out = out.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", out)
    if left:
        sys.exit(f"unfilled placeholders: {sorted(set(left))}")
    return out
def main():
    tpl = open(os.path.join(D, "template.pine"), encoding="utf-8").read()
    for name, d in (("xauscalper_map.pine", FA), ("xauscalper_map_en.pine", EN)):
        p = os.path.join(D, "..", name)
        open(p, "w", encoding="utf-8").write(build(tpl, d))
        print("wrote", os.path.normpath(p))
if __name__ == "__main__":
    main()
