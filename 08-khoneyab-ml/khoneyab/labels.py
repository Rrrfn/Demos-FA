# -*- coding: utf-8 -*-
"""برچسب‌های فارسی و قالب‌بندی اعداد.

همهٔ متن‌هایی که به کاربر می‌رسد از اینجا می‌آید تا هیچ‌جا مقدار خام انگلیسی
(مثل ``full_time`` یا ``parking``) در رابط دیده نشود و رقم‌ها یکدست فارسی
باشند.
"""
from __future__ import annotations

from .config import DISTRICT_BY_CODE, to_persian_digits

#: نام فارسی ویژگی‌ها — کلید همان نام ستون دیتاست است.
FEATURE_LABELS: dict[str, str] = {
    "district": "منطقه",
    "area": "متراژ",
    "bedrooms": "اتاق خواب",
    "age": "سن بنا",
    "floor": "طبقه",
    "parking": "پارکینگ",
    "storage": "انباری",
    "elevator": "آسانسور",
}

#: واحد هر ویژگی برای نمایش کنار عدد.
FEATURE_UNITS: dict[str, str] = {
    "area": "مترمربع",
    "age": "سال",
    "bedrooms": "اتاق",
}

BOOLEAN_LABELS = {0: "ندارد", 1: "دارد"}


def fa_datetime(value: object) -> str:
    """تاریخ و وقت با رقم فارسی — مثل «۲۰۲۶-۰۹-۱۲ ۱۵:۳۶».

    مهر زمانی مدل به شکل خام لاتین ذخیره می‌شود؛ اگر بدون تبدیل نمایش داده
    شود، تنها جای رابط فارسی است که رقم لاتین دارد.
    """
    return to_persian_digits(value if value not in (None, "") else "—")


def fa_code(value: object) -> str:
    """شناسه‌ای مثل ``KH-1001`` با بخش عددی فارسی.

    حروف شناسه دست‌نخورده می‌مانند (کد کالا در همهٔ فروشگاه‌ها لاتین است)
    ولی رقم‌ها فارسی می‌شوند تا در متن فارسی ناهمخوان نباشند.
    """
    return to_persian_digits(value)


def fa_number(value: float | int, *, decimals: int = 0) -> str:
    """عدد با جداکنندهٔ هزارگان فارسی.

    جداکنندهٔ هزارگان ``٬`` و ممیز ``٫`` است. اگر ممیز لاتین (``.``) بماند،
    در متن فارسی یک نقطهٔ کوچک وسط عدد دیده می‌شود که هم ناهمخوان است و هم
    از نظر خوانایی با جداکنندهٔ هزارگان اشتباه گرفته می‌شود.
    """
    if decimals:
        text = f"{value:,.{decimals}f}"
    else:
        text = f"{int(round(value)):,}"
    return (text.replace(",", "٬").replace(".", "٫")
            .translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))


def fa_price(toman: float | int) -> str:
    """قیمت کامل به تومان."""
    return f"{fa_number(toman)} تومان"


def fa_price_short(toman: float | int) -> str:
    """قیمت خلاصه — میلیارد و میلیون، برای کارت ملک."""
    value = float(toman)
    if value >= 1_000_000_000:
        return f"{fa_number(value / 1_000_000_000, decimals=2)} میلیارد"
    if value >= 1_000_000:
        return f"{fa_number(value / 1_000_000, decimals=0)} میلیون"
    return fa_number(value)


def fa_price_per_m2(toman: float | int) -> str:
    return f"{fa_number(toman)} تومان/متر"


def fa_percent(ratio: float, *, decimals: int = 1, signed: bool = False) -> str:
    """درصد فارسی؛ ``signed`` علامت مثبت/منفی را هم نشان می‌دهد."""
    sign = ""
    if signed:
        sign = "−" if ratio < 0 else "+"
    return f"{sign}{fa_number(abs(ratio) * 100, decimals=decimals)}٪"


def floor_label(floor: int) -> str:
    if int(floor) < 0:
        return "زیرزمین"
    if int(floor) == 0:
        return "همکف"
    return f"طبقه {to_persian_digits(int(floor))}"


def district_name(code: int) -> str:
    district = DISTRICT_BY_CODE.get(int(code))
    return f"منطقه {to_persian_digits(int(code))}" + (
        f" — {district.neighborhoods[0]}" if district else "")


def bedrooms_label(count: int) -> str:
    count = int(count)
    if count <= 0:
        return "بدون اتاق"
    return f"{to_persian_digits(count)} خواب"


def feature_value_label(feature: str, value: object) -> str:
    """نمایش یک مقدار ویژگی به فارسی."""
    if feature == "district":
        return district_name(int(value))
    if feature in ("parking", "storage", "elevator"):
        return BOOLEAN_LABELS.get(int(value), "—")
    if feature == "floor":
        return floor_label(int(value))
    if feature == "bedrooms":
        return f"{fa_number(value)} اتاق"
    unit = FEATURE_UNITS.get(feature)
    number = fa_number(value)
    return f"{number} {unit}" if unit else number


def feature_delta_label(feature: str, delta: float) -> str:
    """اثر یک ویژگی بر قیمت — برای بخش «چرا این عدد؟»."""
    if feature == "district":
        return "جایگاه منطقه"
    if feature in ("parking", "storage", "elevator"):
        state = "دارد" if delta >= 0 else "ندارد"
        return f"{FEATURE_LABELS[feature]} ({state})"
    return FEATURE_LABELS.get(feature, feature)
