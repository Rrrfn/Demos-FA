# -*- coding: utf-8 -*-
"""قالب‌بندی فارسی — ارقام، قیمت، درصد و زمان.

لایهٔ نمایش هیچ عدد خامی چاپ نمی‌کند؛ همه‌چیز از این‌جا می‌گذرد تا
یکدستی ارقام و جداکننده‌ها تضمین شود.
"""
from __future__ import annotations

import time

# ارقام، جداکنندهٔ هزارگان و جداکنندهٔ اعشار فارسی
FA_DIGITS = str.maketrans("0123456789,.", "۰۱۲۳۴۵۶۷۸۹٬٫")

_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)


def fa_plain(value: object) -> str:
    """تبدیل هر عدد/رشته به ارقام فارسی بدون جداکننده."""
    return str(value).translate(FA_DIGITS)


def fa_num(value: float, decimals: int = 0) -> str:
    """عدد با جداکنندهٔ هزارگان و ارقام فارسی.

    >>> fa_num(1234567)
    '۱٬۲۳۴٬۵۶۷'
    """
    if decimals > 0:
        text = f"{value:,.{decimals}f}"
    else:
        text = f"{value:,.0f}"
    return text.translate(FA_DIGITS)


def fa_price(value: float, unit: str = "toman", decimals: int = 0) -> str:
    """قیمت همراه واحد پول."""
    label = "دلار" if unit == "usd" else "تومان"
    return f"{fa_num(value, decimals)} {label}"


def fa_signed(value: float, decimals: int = 0) -> str:
    """عدد با علامت صریح مثبت/منفی."""
    sign = "−" if value < 0 else "+"
    return f"{sign}{fa_num(abs(value), decimals)}"


def fa_pct(value: float, decimals: int = 2) -> str:
    """درصد با ارقام فارسی و حذف صفرهای انتهایی."""
    text = f"{abs(value):.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.translate(FA_DIGITS) + "٪"


def arrow(direction: int) -> str:
    """فلش وضعیت: صعودی، نزولی یا بی‌تغییر."""
    return {1: "▲", -1: "▼", 0: "•"}[direction]


def direction_word(direction: int) -> str:
    return {1: "صعودی", -1: "نزولی", 0: "بی‌تغییر"}[direction]


def fa_duration(seconds: float) -> str:
    """توصیف فاصلهٔ زمانی به فارسی."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "لحظه‌ای پیش" if seconds < 5 else f"{fa_plain(seconds)} ثانیه پیش"
    minutes = seconds // 60
    if minutes < 60:
        return f"{fa_plain(minutes)} دقیقه پیش"
    hours = minutes // 60
    if hours < 24:
        return f"{fa_plain(hours)} ساعت پیش"
    days = hours // 24
    return f"{fa_plain(days)} روز پیش"


def fa_clock(ts: float | None = None) -> str:
    """ساعت و دقیقه به وقت محلی، با ارقام فارسی."""
    ts = ts if ts is not None else time.time()
    return time.strftime("%H:%M", time.localtime(ts)).translate(FA_DIGITS)


def fa_date(ts: float | None = None) -> str:
    """تاریخ میلادی به شکل سال/ماه/روز با ارقام فارسی."""
    ts = ts if ts is not None else time.time()
    return time.strftime("%Y-%m-%d", time.localtime(ts)).translate(FA_DIGITS)


def to_int(text: str) -> int:
    """استخراج عدد صحیح از متن با ارقام فارسی/عربی و جداکننده‌ها."""
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = str(text).translate(table)
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    return int(digits) if digits else 0


def to_float(text: str) -> float:
    """استخراج عدد اعشاری از متن (پشتیبانی از ٫ و نقطه)."""
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")
    cleaned = str(text).translate(table).replace(",", "")
    keep = "".join(ch for ch in cleaned if ch.isdigit() or ch == ".")
    try:
        return float(keep) if keep else 0.0
    except ValueError:
        return 0.0
