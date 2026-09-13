# -*- coding: utf-8 -*-
"""فیلترها و توابع قالب.

قالب‌ها نباید عدد و تاریخ را خودشان قالب‌بندی کنند وگرنه هر قالب یک
جداکنندهٔ متفاوت می‌سازد. همهٔ قالب‌بندی‌ها اینجا ثبت می‌شوند و قالب فقط
``{{ price | fa_price }}`` می‌نویسد.
"""
from __future__ import annotations

import os
from functools import lru_cache

from flask import Flask, url_for

from .. import charts
from ..config import STATIC_DIR, to_persian_digits
from ..labels import (bedrooms_label, district_name, fa_code, fa_datetime,
                      fa_number, fa_percent, fa_price, fa_price_per_m2,
                      fa_price_short, floor_label, feature_value_label)
from ..photos import sized


@lru_cache(maxsize=256)
def asset_url(path: str) -> str:
    """نشانی یک دارایی ایستا با نشانهٔ نسخه.

    دارایی‌ها یک ماه کش می‌شوند — که برای سرعت درست است، ولی یعنی تغییر CSS
    تا یک ماه به کاربر قدیمی نمی‌رسد. با چسباندن زمان آخرین تغییر فایل به
    نشانی، هم کش طولانی حفظ می‌شود و هم تغییر بعدی فوراً دیده می‌شود.
    """
    full = os.path.join(STATIC_DIR, path)
    try:
        stamp = int(os.path.getmtime(full))
    except OSError:
        stamp = 0
    return f"{url_for('static', filename=path)}?v={stamp}"


def register(app: Flask) -> None:
    """ثبت فیلترها، توابع سراسری و نام‌های مشترک در محیط قالب."""
    app.jinja_env.filters.update(
        fa=fa_number,
        fa_price=fa_price,
        fa_price_short=fa_price_short,
        fa_price_per_m2=fa_price_per_m2,
        fa_percent=fa_percent,
        fa_code=fa_code,
        fa_date=fa_datetime,
        digits=to_persian_digits,
    )
    app.jinja_env.globals.update(
        asset=asset_url,
        to_persian_digits=to_persian_digits,
        district_name=district_name,
        floor_label=floor_label,
        bedrooms_label=bedrooms_label,
        feature_value_label=feature_value_label,
        photo=sized,
        chart=charts,
    )
    # فاصلهٔ زائد در HTML جمع می‌شود — چند کیلوبایت صرفه‌جویی در حجم صفحه.
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
