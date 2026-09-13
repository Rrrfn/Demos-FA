# -*- coding: utf-8 -*-
"""زمینهٔ مشترک قالب‌ها — ناوبری، عنوان صفحه و یادداشت صداقت.

یک نکته که در کل محصول تکرار می‌شود: داده سینتتیک است. متن این یادداشت اینجا
و در پابرگ یک جا نوشته شده تا در هیچ صفحه‌ای جا نیفتد؛ چون پنهان‌کردن آن،
تنها ادعای نادرستی است که این پروژه می‌تواند بکند.
"""
from __future__ import annotations

#: ناوبری اصلی. ترتیب همان مسیر طبیعی استفاده است: از نمای کلی به متن، بعد
#: انبوه، بعد تحلیل، بعد خود مدل.
NAV = (
    {"endpoint": "pages.overview", "label": "نمای کلی", "slug": "overview"},
    {"endpoint": "pages.analyze", "label": "تحلیل متن", "slug": "analyze"},
    {"endpoint": "pages.batch", "label": "تحلیل گروهی", "slug": "batch"},
    {"endpoint": "pages.analytics_page", "label": "تحلیل", "slug": "analytics"},
    {"endpoint": "pages.model_page", "label": "مدل", "slug": "model"},
    {"endpoint": "pages.methodology", "label": "متدولوژی", "slug": "methodology"},
)

#: یادداشت همیشگی دربارهٔ داده.
DATA_NOTE = "دیتاست سینتتیک و قالب‌محور است؛ هیچ کامنت واقعی کاربری در آن نیست."


def base_context(active: str, title: str) -> dict:
    return {
        "nav": NAV,
        "active": active,
        "page_title": title,
        "data_note": DATA_NOTE,
    }
