# -*- coding: utf-8 -*-
"""وضعیت نشست — فهرست مقایسه، نشان‌شده‌ها و فرم برآورد.

نگه‌داشتن این‌ها در ``session_state`` یعنی کاربر می‌تواند بین صفحه‌ها جابه‌جا شود
بدون آن‌که انتخاب‌هایش پاک شوند. همهٔ دسترسی‌ها از همین‌جا انجام می‌شود تا
کلیدهای وضعیت در چند فایل پخش نشوند.
"""
from __future__ import annotations

import streamlit as st

from .config import AREA_RANGE, BEDROOM_RANGE, FLOOR_RANGE
from .listings import Listing

COMPARE_KEY = "compare_ids"
SAVED_KEY = "saved_ids"
FORM_KEY = "estimate_form"
PAGE_KEY = "search_page"
QUERY_KEY = "search_query"

#: بیشترین تعداد ملک قابل مقایسه — بیشتر از این، جدول خوانا نمی‌ماند.
MAX_COMPARE = 4


def _ids(key: str) -> list[str]:
    return list(st.session_state.get(key, []))


def compare_ids() -> list[str]:
    return _ids(COMPARE_KEY)


def saved_ids() -> list[str]:
    return _ids(SAVED_KEY)


def is_in_compare(listing_id: str) -> bool:
    return listing_id in compare_ids()


def is_saved(listing_id: str) -> bool:
    return listing_id in saved_ids()


def toggle_compare(listing_id: str) -> bool:
    """افزودن/برداشتن از مقایسه. خروجی: آیا الان در فهرست است؟"""
    current = compare_ids()
    if listing_id in current:
        current.remove(listing_id)
        st.session_state[COMPARE_KEY] = current
        return False
    if len(current) >= MAX_COMPARE:
        return False
    current.append(listing_id)
    st.session_state[COMPARE_KEY] = current
    return True


def toggle_saved(listing_id: str) -> bool:
    current = saved_ids()
    if listing_id in current:
        current.remove(listing_id)
        st.session_state[SAVED_KEY] = current
        return False
    current.append(listing_id)
    st.session_state[SAVED_KEY] = current
    return True


def set_compare(ids: list[str]) -> None:
    """جایگزینی کل فهرست مقایسه — برای بارگذاری از نشانی اشتراکی."""
    unique: list[str] = []
    for identifier in ids:
        if identifier and identifier not in unique:
            unique.append(identifier)
    st.session_state[COMPARE_KEY] = unique[:MAX_COMPARE]


def clear_compare() -> None:
    st.session_state[COMPARE_KEY] = []


def compare_full() -> bool:
    return len(compare_ids()) >= MAX_COMPARE


def default_features() -> dict:
    """مقادیر آغازین فرم برآورد — ملکی معمولی در شهر، نه صفر و نه افراطی."""
    return {
        "district": 2, "area": 110, "bedrooms": 2, "age": 6,
        "floor": 3, "parking": 1, "storage": 1, "elevator": 1,
    }


def estimate_features() -> dict:
    """مشخصات فعلی فرم؛ در نبود آن، مقادیر پیش‌فرض."""
    stored = st.session_state.get(FORM_KEY)
    return dict(stored) if stored else default_features()


def set_estimate_features(features: dict) -> None:
    st.session_state[FORM_KEY] = dict(features)


def features_from_listing(listing: Listing) -> None:
    """پر کردن فرم برآورد با مشخصات یک آگهی — برای دکمهٔ «برآورد همین ملک»."""
    set_estimate_features(listing.as_features())


def bounds() -> dict:
    """بازهٔ مجاز ورودی‌های فرم."""
    return {
        "area": AREA_RANGE,
        "bedrooms": BEDROOM_RANGE,
        "floor": FLOOR_RANGE,
    }
