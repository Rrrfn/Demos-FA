# -*- coding: utf-8 -*-
"""تبدیل مقدار سلول به نوع واقعی.

فایل‌های واقعی اکسل پر از عددی هستند که *متن* ذخیره شده‌اند: ``"1,200,000"``،
``"۱۲٬۵۰۰"``، ``"۲۵۰٬۰۰۰ ریال"`` و ``"(۳٬۲۰۰)"`` به‌معنای منفی. اگر این‌ها متن
بمانند، هر جمع و میانگینی روی آن‌ها غلط است و گزارش هم غلط می‌شود. این ماژول
همان تبدیل را انجام می‌دهد و **دلیل** هر تبدیل را نگه می‌دارد تا در بخش
«پاک‌سازی» سایت قابل بازرسی باشد.

تقویم: تاریخ‌های شمسی هم تجزیه می‌شوند. کاربر ایرانی داده‌اش را با تاریخ شمسی
می‌آورد و ابزاری که فقط Gregorian می‌فهمد، ستون تاریخ او را متن می‌بیند و
تحلیل روند را بی‌دلیل از دست می‌دهد. تبدیل از تقویم حساب‌شدهٔ استاندارد
(چرخهٔ ۳۳ ساله) استفاده می‌کند — همان چیزی که نرم‌افزارهای اداری ایران
به‌کار می‌برند.
"""
from __future__ import annotations

import datetime as dt
import math
import re

TRUE_WORDS = {"true", "yes", "y", "1", "بله", "آری", "درست", "دارد", "فعال"}
FALSE_WORDS = {"false", "no", "n", "0", "خیر", "نه", "غلط", "ندارد", "غیرفعال"}

NULL_WORDS = {"", "-", "--", "—", "n/a", "na", "null", "none", "بدون مقدار",
              "نامشخص", "خالی", "?", "؟"}

#: واحدهایی که هنگام خواندن عدد پاک می‌شوند. مرتب‌شده از بلند به کوتاه تا
#: «هزار میلیارد» پیش از «میلیارد» امتحان شود.
MULTIPLIERS = (("هزار میلیارد", 1e12), ("میلیارد", 1e9), ("میلیون", 1e6),
               ("هزار", 1e3), ("مگا", 1e6), ("کیلو", 1e3),
               ("billion", 1e9), ("million", 1e6), ("thousand", 1e3))

#: جداکننده‌های هزارگان در متن فارسی و لاتین.
GROUP_SEPARATORS = "٬,\u00a0\u202f "
#: علامت‌های ممیز.
DECIMAL_MARKS = "٫."
#: علامت‌های منفی، شامل منفی نگارشی فارسی.
MINUS_SIGNS = "-−–—"

DIGIT_WORDS = {"صفر": 0, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
               "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10}

_NUMBER_CLEAN = re.compile(r"[^0-9.\-]")
_DATE_PARTS = re.compile(r"(\d{1,4})\D+(\d{1,2})\D+(\d{1,4})")


# ------------------------------------------------------------------ ارقام و متن
def normalize_digits(text: str) -> str:
    """رقم فارسی و عربی → لاتین، و ممیز/جداکنندهٔ فارسی → لاتین.

    تبدیل ممیز هم اینجا انجام می‌شود چون بدون آن «۳٫۵» در پاک‌سازی بعدی به
    «۳۵» تبدیل می‌شد — دو نیمهٔ عدد به هم می‌چسبیدند و عدد ده برابر می‌شد.
    """
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2)
    return str(text).translate(table).replace("٫", ".").replace("٬", ",")


def clean_text(value: object) -> str:
    """متن پاک‌شده: نیم‌فاصله یکدست، فاصله‌های تکراری جمع، بدون فاصلهٔ لبه."""
    if value is None:
        return ""
    text = str(value).replace("\u200f", "").replace("\u200e", "")
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------------------------ عدد
def parse_number(value: object) -> float | None:
    """تجزیهٔ عدد از هر شکل متنی. اگر عدد نبود ``None``.

    سه دام که هر کدام یک بار در همین پروژه سر باز کرده‌اند و اینجا بسته شده‌اند:

    * **حرف در عدد.** کدی مثل ``A-1`` اگر فقط بر پایهٔ ارقام تجزیه شود، به
      منفی یک تبدیل می‌شود. پس هر حرفی که پس از پاک‌کردن واحدها بماند، سلول
      را متن می‌کند.
    * **واژهٔ مقدار.** «۲۵۰ هزار» عدد است، ولی واژهٔ «هزار» حرف است و اگر
      پیش از بررسی حرف پاک نشود، عدد رد می‌شود.
    * **بی‌نهایت.** ``inf`` یک عدد پایتونی است ولی مقدار داده نیست؛ اگر رد
      نشود، جمع کل ستون بی‌نهایت می‌شود.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number

    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered in NULL_WORDS:
        return None
    if lowered in DIGIT_WORDS:
        return float(DIGIT_WORDS[lowered])

    negative = False
    #: پرانتز در حسابداری یعنی منفی.
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    #: علامت منفی باید در *ابتدا* باشد، یا در برخی سیستم‌های حسابداری در
    #: *انتها*. جست‌وجوی ساده در دو نویسهٔ اول غلط بود: «A-1» هم منفی خوانده
    #: می‌شد. علامت پس از تشخیص، از متن برداشته می‌شود وگرنه ``float`` آن را
    #: پس می‌زند.
    signs = "".join(MINUS_SIGNS)
    bare = text.strip()
    if bare[:1] in tuple(signs) or bare[-1:] in tuple(signs):
        negative = True
        text = bare.strip(signs + " ")

    #: واژهٔ مقدار پیش از بررسی حرف، از متن برداشته می‌شود.
    lowered = text.lower()
    multiplier = 1.0
    for word, factor in MULTIPLIERS:
        if word in lowered:
            multiplier = factor
            text = re.sub(re.escape(word), " ", text, flags=re.IGNORECASE)
            break

    text = normalize_digits(text)
    #: واحدها و علامت‌های پول حذف می‌شوند.
    text = re.sub(r"(ریال|تومان|درهم|دلار|یورو|rls|irr|toman|\$|€|£|٪|%)",
                  " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(تعداد|عدد|کیلوگرم|کیلو|گرم|تن|متر|لیتر|نفر|دستگاه|بسته|"
                  r"kg|km|m2|m3)", " ", text, flags=re.IGNORECASE)
    #: اگر پس از پاک‌کردن واحدها هنوز حرفی مانده، این سلول متن است نه عدد.
    if any(char.isalpha() for char in text):
        return None
    #: ویرگول در این فهرست لازم است: منطق جدایی ممیز و جداکنندهٔ هزارگان
    #: *پس از* همین خط اجرا می‌شود و اگر ویرگول اینجا حذف شود، «۱٫۲۳۴٬۵۶»
    #: به هم می‌چسبد و عدد غلط می‌دهد.
    text = "".join(char for char in text if char.isdigit() or char in ".-+ ,")

    #: جداکنندهٔ هزارگان پیش از ممیز حذف می‌شود. اگر هم نقطه و هم ویرگول باشد،
    #: آخری ممیز است — قاعدهٔ رایج فایل‌های دوزبانه.
    if "." in text and "," in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", "")
    text = text.replace(" ", "")

    if text.count(".") > 1:
        head, _, tail = text.rpartition(".")
        text = head.replace(".", "") + "." + tail
    text = text.lstrip("+")

    if not text or text in {"-", "."}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if negative:
        number = -abs(number)
    return number * multiplier


# ------------------------------------------------------------------ مقدار بولی
def parse_bool(value: object) -> bool | None:
    """تجزیهٔ بولی از متن فارسی و لاتین."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = clean_text(value).lower()
    if not text:
        return None
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    return None


# ------------------------------------------------------------------ تقویم شمسی
def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int] | None:
    """تبدیل تاریخ شمسی به میلادی — تقویم حساب‌شدهٔ استاندارد.

    ماه‌های ۱ تا ۶ سی‌ویک روزه‌اند و ۷ تا ۱۲ سی‌روزه، پس شمار روزهای سپری‌شده
    از آغاز سال دو بازه دارد (نه یک ضرب ساده).
    """
    if not (1 <= jm <= 12 and 1 <= jd <= 31):
        return None
    if jm <= 6 and jd > 31:
        return None
    if jm > 6 and jd > 30:
        return None

    jy_shifted = jy - 979
    day_of_year = (jm - 1) * 31 if jm <= 7 else (jm - 7) * 30 + 186
    days = (365 * jy_shifted + (jy_shifted // 33) * 8
            + ((jy_shifted % 33 + 3) // 4) + jd + day_of_year - 1)
    g_days = days + 79
    gy = 1600 + 400 * (g_days // 146097)
    g_days %= 146097
    leap = True
    if g_days >= 36525:
        g_days -= 1
        gy += 100 * (g_days // 36524)
        g_days %= 36524
        if g_days >= 365:
            g_days += 1
        else:
            leap = False
    gy += 4 * (g_days // 1461)
    g_days %= 1461
    if g_days >= 366:
        leap = False
        g_days -= 1
        gy += g_days // 365
        g_days %= 365
    gd = g_days + 1
    months = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gm = 0
    while gm < 12 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    try:
        return gy, gm + 1, gd
    except IndexError:
        return None


def parse_date(value: object) -> dt.date | None:
    """تجزیهٔ تاریخ از متن یا مقدار سلول — شمسی و میلادی، با ارقام فارسی."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value

    text = clean_text(value)
    if not text or text.lower() in NULL_WORDS:
        return None
    text = normalize_digits(text).replace("T", " ")

    #: قالب «۵ مهر ۱۴۰۳» فاصله دارد، پس نمی‌توان ساده اول متن را برید. اول کل
    #: متن امتحان می‌شود و بریدن فقط برای جدا کردن بخش ساعت است.
    named = _parse_named_month(text)
    if named is not None:
        return named
    text = text.split(" ")[0]

    match = _DATE_PARTS.match(text)
    if not match:
        return None

    first, second, third = (int(part) for part in match.groups())
    #: سال آخر یعنی قالب میلادی/شمسی «YYYY/MM/DD»؛ سال اول یعنی «DD/MM/YYYY».
    if first > 31:
        year, month, day = first, second, third
    elif third > 31:
        day, month, year = first, second, third
    else:
        return None
    return _assemble(year, month, day)


def _assemble(year: int, month: int, day: int) -> dt.date | None:
    """ساخت تاریخ از سه جزء با تشخیص تقویم از بازهٔ سال."""
    if year >= 1700:                      # میلادی
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    if 1200 <= year <= 1599:              # شمسی
        converted = jalali_to_gregorian(year, month, day)
        if not converted:
            return None
        try:
            return dt.date(*converted)
        except ValueError:
            return None
    return None


#: نام ماه‌های شمسی برای قالب «۵ مهر ۱۴۰۳».
JALALI_MONTHS = {"فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5,
                 "شهریور": 6, "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10,
                 "بهمن": 11, "اسفند": 12}
GREGORIAN_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4,
                    "may": 5, "june": 6, "july": 7, "august": 8,
                    "september": 9, "october": 10, "november": 11,
                    "december": 12}


def _parse_named_month(text: str) -> dt.date | None:
    lowered = text.lower()
    for name, number in JALALI_MONTHS.items():
        if name in text:
            parts = re.findall(r"\d+", text)
            if len(parts) >= 2:
                day, year = int(parts[0]), int(parts[-1])
                return _assemble(year, number, day)
    for name, number in GREGORIAN_MONTHS.items():
        if name in lowered:
            parts = re.findall(r"\d+", text)
            if len(parts) >= 2:
                day, year = int(parts[0]), int(parts[-1])
                return _assemble(year, number, day)
    return None


#: بازهٔ معتبر برای سال — نگهبان مقادیری مثل «۱۴۰۳۰» که سال نیستند.
MIN_YEAR = 1990
MAX_YEAR = 2100


def plausible_date(value: dt.date | None) -> bool:
    """تاریخ در بازهٔ معقول است؟ تاریخ‌های بیرون از بازه «مشکوک» علامت می‌خورند."""
    if value is None:
        return False
    return MIN_YEAR <= value.year <= MAX_YEAR
