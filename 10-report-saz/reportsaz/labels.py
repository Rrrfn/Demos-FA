# -*- coding: utf-8 -*-
"""قالب‌بندی برچسب‌ها و اعداد فارسی.

هر عددی که کاربر می‌خواند — در رابط، در PDF و در اکسل — از اینجا می‌گذرد.
رقم لاتین و ممیز لاتین در متن فارسی ناهمخوان است و با جداکنندهٔ هزارگان اشتباه
گرفته می‌شود؛ پس تبدیل در یک نقطه انجام می‌شود تا هیچ‌جا جا نیفتد.
"""
from __future__ import annotations

import math

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
LATIN_TO_PERSIAN = str.maketrans("0123456789", PERSIAN_DIGITS)
PERSIAN_TO_LATIN = str.maketrans(PERSIAN_DIGITS + "٠١٢٣٤٥٦٧٨٩",
                                 "0123456789" * 2)

#: نشانه‌های نگارشی فارسی.
THOUSANDS = "٬"
DECIMAL = "٫"


def to_persian_digits(value: object) -> str:
    """تبدیل رقم‌های لاتین به فارسی."""
    return str(value).translate(LATIN_TO_PERSIAN)


def to_latin_digits(value: object) -> str:
    """تبدیل رقم‌های فارسی و عربی به لاتین — برای تجزیهٔ عدد از متن."""
    return str(value).translate(PERSIAN_TO_LATIN)


def fa_number(value: object, *, decimals: int = 0, group: bool = True) -> str:
    """عدد با جداکنندهٔ هزارگان و ممیز فارسی.

    ``group=False`` جداکنندهٔ هزارگان را حذف می‌کند — برای عددهایی مثل سال که
    جداکننده آن‌ها را غلط نشان می‌دهد.
    """
    number = _to_float(value)
    if number is None:
        return "—"
    if decimals:
        text = f"{number:,.{decimals}f}"
    else:
        text = f"{int(round(number)):,}"
    if not group:
        text = text.replace(",", "")
    return text.replace(",", THOUSANDS).replace(".", DECIMAL).translate(LATIN_TO_PERSIAN)


def fa_percent(ratio: object, *, decimals: int = 1, signed: bool = False) -> str:
    """درصد فارسی از یک نسبت بین ۰ و ۱."""
    number = _to_float(ratio)
    if number is None:
        return "—"
    sign = ""
    if signed:
        sign = "−" if number < 0 else "+"
    return f"{sign}{fa_number(abs(number) * 100, decimals=decimals)}٪"


def fa_compact(value: object) -> str:
    """عدد خلاصه برای کارت‌های شاخص: ۱۲٫۴ میلیون، ۳٫۱ میلیارد.

    برای عددهای بزرگ، عدد کامل روی کارت خوانده نمی‌شود؛ خلاصه‌سازی خودِ عدد
    است، نه گِردکردنِ نادرست.
    """
    number = _to_float(value)
    if number is None:
        return "—"
    magnitude = abs(number)
    for threshold, label, decimals in ((1e12, "هزار میلیارد", 1),
                                       (1e9, "میلیارد", 1),
                                       (1e6, "میلیون", 1),
                                       (1e3, "هزار", 0)):
        if magnitude >= threshold:
            return f"{fa_number(number / threshold, decimals=decimals)} {label}"
    return fa_number(number, decimals=1 if number != int(number) else 0)


def fa_datetime(value: object) -> str:
    """مهر زمانی — ذخیره لاتین است، نمایش فارسی."""
    if value in (None, ""):
        return "—"
    return to_persian_digits(str(value).replace("T", " "))


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int] | None:
    """تبدیل تاریخ میلادی به شمسی — معکوس دقیق تبدیل سمت ورود داده.

    چرا به آن نیاز است: سطل‌های نمودار روند از تقویم داخلی pandas می‌آیند که
    میلادی است. محور یک محصول فارسی نباید ۲۰۲۴-۰۳-۲۴ نشان بدهد؛ تاریخ باید
    به تقویمی برگردد که کاربر با آن کار می‌کند.
    """
    if not (1 <= gm <= 12 and 1 <= gd <= 31):
        return None
    month_days = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = gy - 1600
    day_no = (365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100
              + (gy2 + 399) // 400)
    day_no += month_days[gm - 1] + (gd - 1)
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        day_no += 1
    j_day_no = day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    if j_day_no < 186:
        return jy, 1 + j_day_no // 31, 1 + j_day_no % 31
    return jy, 7 + (j_day_no - 186) // 30, 1 + (j_day_no - 186) % 30


def fa_date_label(value: object) -> str:
    """برچسب تاریخ شمسی برای محور نمودار — ``۱۴۰۳/۰۷/۰۳``.

    اگر مقدار تاریخ نباشد (چیزی که در ستون تاریخ تجزیه نشد)، متن دست‌نخورده
    برمی‌گردد تا برچسبی از خودمان به نمودار اضافه نشود.
    """
    import datetime as _dt

    moment = None
    if isinstance(value, _dt.datetime):
        moment = value.date()
    elif isinstance(value, _dt.date):
        moment = value
    else:
        text = str(value or "").strip()
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                moment = _dt.datetime.strptime(text[:len(
                    _dt.datetime(2000, 1, 1).strftime(pattern))], pattern).date()
                break
            except ValueError:
                continue
    if moment is None:
        return to_persian_digits(value)
    converted = gregorian_to_jalali(moment.year, moment.month, moment.day)
    if converted is None:
        return to_persian_digits(moment.isoformat())
    year, month, day = converted
    return to_persian_digits(f"{year}/{month:02d}/{day:02d}")


def fa_duration(seconds: object) -> str:
    """مدت زمان خوانا."""
    number = _to_float(seconds)
    if number is None:
        return "—"
    if number < 1:
        return f"{fa_number(number * 1000, decimals=0)} میلی‌ثانیه"
    if number < 60:
        return f"{fa_number(number, decimals=1)} ثانیه"
    return f"{fa_number(number / 60, decimals=1)} دقیقه"


def fa_bytes(size: object) -> str:
    """حجم فایل خوانا."""
    number = _to_float(size)
    if number is None:
        return "—"
    for threshold, label in ((1024 ** 3, "گیگابایت"), (1024 ** 2, "مگابایت"),
                             (1024, "کیلوبایت")):
        if number >= threshold:
            return f"{fa_number(number / threshold, decimals=1)} {label}"
    return f"{fa_number(number)} بایت"


def _to_float(value: object) -> float | None:
    """تبدیل امن به عدد. ``NaN`` و بی‌نهایت «عدد» شمرده نمی‌شوند."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number
