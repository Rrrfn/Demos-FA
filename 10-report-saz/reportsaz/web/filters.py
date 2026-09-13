# -*- coding: utf-8 -*-
"""فیلترهای Jinja — تبدیل اعداد در لبهٔ نمایش.

هر عددی که به کاربر می‌رسد از اینجا می‌گذرد. اگر تبدیل در قالب انجام نشود،
دیر یا زود یک عدد لاتین لای متن فارسی جا می‌ماند — همان چیزی که در نسخهٔ
قبلی این پروژه در چند صفحه دیده می‌شد.

فیلترها نازک‌اند و منطق ندارند؛ همه‌شان به ``labels`` تکیه می‌کنند تا رابط،
PDF و اکسل یک شکل عدد نشان دهند.
"""
from __future__ import annotations

from flask import Flask

from ..labels import (fa_bytes, fa_compact, fa_datetime, fa_duration, fa_number,
                      fa_percent, to_persian_digits)


def register_filters(app: Flask) -> None:
    """ثبت همهٔ فیلترها روی برنامه."""

    @app.template_filter("fa")
    def _fa(value, decimals: int = 0):
        """عدد با جداکننده و ممیز فارسی."""
        if value is None:
            return "—"
        try:
            return fa_number(value, decimals=int(decimals or 0))
        except (TypeError, ValueError):
            return to_persian_digits(value)

    @app.template_filter("fa_compact")
    def _compact(value):
        return fa_compact(value)

    @app.template_filter("fa_pct")
    def _percent(value, decimals: int = 1, signed: bool = False):
        """نسبت بین ۰ و ۱ به درصد فارسی."""
        if value is None:
            return "—"
        return fa_percent(value, decimals=int(decimals or 0),
                          signed=bool(signed))

    @app.template_filter("fa_bytes")
    def _bytes(value):
        return fa_bytes(value)

    @app.template_filter("fa_dt")
    def _datetime(value):
        return fa_datetime(value)

    @app.template_filter("fa_duration")
    def _duration(value):
        return fa_duration(value)

    @app.template_filter("digits")
    def _digits(value):
        """فقط تبدیل رقم — بدون جداکننده. برای سال و شناسه."""
        return to_persian_digits(value if value is not None else "—")

    @app.template_filter("shares")
    def _shares(value, signed: bool = False):
        """مقدار که خودش نسبت است و باید درصد شود."""
        if value is None:
            return "—"
        sign = ""
        if signed:
            sign = "−" if float(value) < 0 else "+"
        return f"{sign}{fa_number(abs(float(value)) * 100, decimals=1)}٪"
