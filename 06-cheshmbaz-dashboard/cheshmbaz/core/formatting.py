# -*- coding: utf-8 -*-
"""قالب‌بندی فارسی — ارقام، قیمت، درصد و زمان.

همهٔ متن‌های قابل‌نمایش از این‌جا می‌گذرند تا ارقام و جداکننده‌ها یکدست
بمانند. هیچ لایه‌ای عدد خام انگلیسی چاپ نمی‌کند.
"""
from __future__ import annotations

import time

# ارقام، جداکنندهٔ هزارگان و جداکنندهٔ اعشار فارسی
FA_DIGITS = str.maketrans("0123456789,.", "۰۱۲۳۴۵۶۷۸۹٬٫")


def fa_digits(value: object) -> str:
    """تبدیل ارقام لاتین به فارسی، بدون جداکننده."""
    return str(value).translate(FA_DIGITS)


def fa_number(value: float | int, decimals: int = 0) -> str:
    """عدد با جداکنندهٔ هزارگان و ارقام فارسی."""
    if value is None:
        return "—"
    text = f"{value:,.{decimals}f}" if decimals > 0 else f"{value:,.0f}"
    return text.translate(FA_DIGITS)


def fa_price(value: float | int | None, unit: str = "toman", decimals: int = 0) -> str:
    """قیمت به‌همراه واحد."""
    if value is None:
        return "—"
    label = "دلار" if unit == "usd" else "تومان"
    return f"{fa_number(value, decimals)} {label}"


def fa_signed(value: float | None, decimals: int = 0) -> str:
    """عدد با علامت صریح (+/−)."""
    if value is None:
        return "—"
    sign = "−" if value < 0 else "+"
    return f"{sign}{fa_number(abs(value), decimals)}"


def fa_percent(value: float | None, decimals: int = 2) -> str:
    """درصد با ارقام فارسی و حذف صفرهای انتهایی."""
    if value is None:
        return "—"
    text = f"{abs(value):.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.translate(FA_DIGITS) + "٪"


def arrow(direction: int) -> str:
    """فلش جهت تغییر."""
    return {1: "▲", -1: "▼", 0: "•"}[direction]


def fa_duration(seconds: float | None) -> str:
    """توصیف فاصلهٔ زمانی به فارسی."""
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "همین حالا" if seconds < 10 else f"{fa_digits(seconds)} ثانیه پیش"
    minutes = seconds // 60
    if minutes < 60:
        return f"{fa_digits(minutes)} دقیقه پیش"
    hours = minutes // 60
    if hours < 24:
        return f"{fa_digits(hours)} ساعت پیش"
    days = hours // 24
    return f"{fa_digits(days)} روز پیش"


def fa_clock(ts: float | None = None) -> str:
    """ساعت و دقیقه به وقت محلی."""
    ts = ts if ts is not None else time.time()
    return time.strftime("%H:%M:%S", time.localtime(ts)).translate(FA_DIGITS)


def fa_datetime(ts: float | None = None) -> str:
    """تاریخ و ساعت عددی."""
    ts = ts if ts is not None else time.time()
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)).translate(FA_DIGITS)


__all__ = [
    "arrow",
    "fa_clock",
    "fa_datetime",
    "fa_digits",
    "fa_duration",
    "fa_number",
    "fa_percent",
    "fa_price",
    "fa_signed",
]
