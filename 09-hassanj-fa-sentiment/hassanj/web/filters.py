# -*- coding: utf-8 -*-
"""فیلترهای قالب — قالب‌بندی عدد، درصد و نشانی دارایی‌ها.

هر عددی که به کاربر می‌رسد از اینجا می‌گذرد. اگر قالبی مستقیم عدد پایتون چاپ
کند، ممیز و جداکنندهٔ هزارگان لاتین می‌مانند و در متن فارسی ناهمخوان می‌شوند.
"""
from __future__ import annotations

import hashlib
import os

from ..labels import fa_datetime, fa_number, fa_percent, to_persian_digits


def register(app) -> None:
    """فیلترها را روی برنامه ثبت می‌کند."""

    @app.template_filter("fa_number")
    def _fa_number(value, decimals: int = 0) -> str:
        try:
            return fa_number(float(value), decimals=decimals)
        except (TypeError, ValueError):
            return "—"

    @app.template_filter("fa_percent")
    def _fa_percent(value, decimals: int = 1, signed: bool = False) -> str:
        try:
            return fa_percent(float(value), decimals=decimals, signed=signed)
        except (TypeError, ValueError):
            return "—"

    @app.template_filter("fa_digits")
    def _fa_digits(value) -> str:
        return to_persian_digits(value if value is not None else "—")

    @app.template_filter("fa_datetime")
    def _fa_datetime(value) -> str:
        return fa_datetime(value)

    @app.template_filter("asset")
    def _asset(path: str) -> str:
        """نشانی دارایی با نشانهٔ محتوا.

        دارایی‌ها با کش طولانی سرو می‌شوند؛ بدون نشانهٔ محتوا، مرورگر پس از هر
        تغییر CSS همان نسخهٔ قدیمی را می‌آورد و «تغییر اعمال نشد» به نظر
        می‌رسد. نشانه از هش خود فایل می‌آید، پس خودکار عوض می‌شود.
        """
        from ..config import STATIC_DIR

        full = os.path.join(STATIC_DIR, path.lstrip("/"))
        try:
            with open(full, "rb") as handle:
                stamp = hashlib.sha1(handle.read()).hexdigest()[:8]
        except OSError:
            return f"/static/{path.lstrip('/')}"
        return f"/static/{path.lstrip('/')}?v={stamp}"
