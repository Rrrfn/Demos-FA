# -*- coding: utf-8 -*-
"""زمینهٔ مشترک قالب‌ها.

هر قالبی که ``base.html`` را گسترش می‌دهد — از جمله صفحه‌های خطا — به این
متغیرها نیاز دارد: فهرست ناوبری، شمارندهٔ مقایسه و نشان‌ها، و تعداد عکس‌ها.
اگر جایی از قلم بیفتد، صفحهٔ خطا خودش خطا می‌دهد و کاربر یک صفحهٔ خالی
می‌بیند. به همین دلیل اینها یک جا تعریف و در همهٔ مسیرها استفاده می‌شوند.
"""
from __future__ import annotations

from .. import services
from . import session as store

#: (کلید، نشانی، برچسب) — ترتیب همان ترتیب نمایش در نوار بالاست.
NAV: tuple[tuple[str, str, str], ...] = (
    ("search", "/search", "جست‌وجو"),
    ("estimate", "/estimate", "برآورد قیمت"),
    ("compare", "/compare", "مقایسه"),
    ("analytics", "/analytics", "تحلیل بازار"),
    ("methodology", "/methodology", "متدولوژی"),
)


def shell(active: str = "") -> dict:
    """متغیرهای پایهٔ همهٔ صفحه‌ها."""
    library = services.photos()
    return {
        "page": active,
        "nav": NAV,
        "compare_count": len(store.compare_ids()),
        "saved_count": len(store.saved_ids()),
        "photo_total": library.total,
        "exterior_count": library.exteriors_count,
        "interior_count": library.interiors_count,
    }
