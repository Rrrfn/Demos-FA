# -*- coding: utf-8 -*-
"""وضعیت کاربر — فهرست مقایسه و نشان‌شده‌ها.

این‌ها در نشست امضاشدهٔ Flask نگه داشته می‌شوند، نه در پایگاه داده: حجمشان
چند شناسه است، باید بین صفحه‌ها و پس از تازه‌سازی مرورگر بمانند، و هیچ‌کدام
ارزش نگه‌داری سمت سرور را ندارند. نتیجه اینکه کاربر بدون حساب و بدون کوکی
ردیابی هم می‌تواند فهرستش را بسازد.

حداکثر چهار ملک برای مقایسه نگه داشته می‌شود. بیشتر از این، جدول روی صفحهٔ
کوچک خوانا نمی‌ماند و مقایسه بی‌معنا می‌شود.
"""
from __future__ import annotations

from flask import session

COMPARE_KEY = "compare"
SAVED_KEY = "saved"
FORM_KEY = "estimate"

MAX_COMPARE = 4
MAX_SAVED = 60


def _clean(raw: object, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    unique: list[str] = []
    for item in raw:
        identifier = str(item)
        if identifier and identifier not in unique:
            unique.append(identifier)
    return unique[:limit]


def compare_ids() -> list[str]:
    return _clean(session.get(COMPARE_KEY), MAX_COMPARE)


def saved_ids() -> list[str]:
    return _clean(session.get(SAVED_KEY), MAX_SAVED)


def set_compare(identifiers: list[str]) -> None:
    """جایگزینی کل فهرست — برای بارگذاری از نشانی اشتراکی."""
    session[COMPARE_KEY] = _clean(identifiers, MAX_COMPARE)


def toggle_compare(identifier: str) -> bool:
    """افزودن یا برداشتن یک ملک. خروجی: آیا پس از تغییر در فهرست است؟"""
    current = compare_ids()
    if identifier in current:
        current.remove(identifier)
        session[COMPARE_KEY] = current
        return False
    if len(current) >= MAX_COMPARE:
        return False
    current.append(identifier)
    session[COMPARE_KEY] = current
    return True


def clear_compare() -> None:
    session.pop(COMPARE_KEY, None)


def compare_full() -> bool:
    return len(compare_ids()) >= MAX_COMPARE


def toggle_saved(identifier: str) -> bool:
    current = saved_ids()
    if identifier in current:
        current.remove(identifier)
        session[SAVED_KEY] = current
        return False
    current.append(identifier)
    session[SAVED_KEY] = current[-MAX_SAVED:]
    return True


def clear_saved() -> None:
    session.pop(SAVED_KEY, None)


def set_estimate(features: dict) -> None:
    session[FORM_KEY] = {key: int(value) for key, value in features.items()}


def stored_estimate() -> dict | None:
    raw = session.get(FORM_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return {key: int(value) for key, value in raw.items()}
    except (TypeError, ValueError):
        return None
