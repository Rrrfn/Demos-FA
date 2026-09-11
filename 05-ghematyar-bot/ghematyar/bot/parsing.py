# -*- coding: utf-8 -*-
"""پارس عبارت‌های محاوره‌ای هشدار.

کاربر نباید فرم پر کند؛ کافی است بنویسد:

* «دلار بالای ۲۵۰۰۰۰»
* «سکه امامی زیر ۲ میلیارد»  (پشتیبانی از «میلیارد» و «میلیون»)
* «بیت‌کوین بالاتر از ۸۵۰۰۰ دلار»

این ماژول کاملاً خالص است (بدون شبکه و بدون تلگرام) تا مستقیم تست شود.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..core import assets as asset_registry
from ..core.formatting import to_float
from ..storage import AlertDirection

# ترتیب مهم است: عبارت‌های طولانی‌تر اول می‌آیند تا «بیشتر از» با «بیشتر» جابه‌جا نشود
_ABOVE = ("بیشتر از", "بالاتر از", "بالای", "بیش از", "ببالا", "بیشتر", "بالاتر", "بالا")
_BELOW = ("کمتر از", "پایین‌تر از", "پایین تر از", "زیر", "کمتر", "پایین", "کم از", "پایین‌تر")

_SCALES: tuple[tuple[str, float], ...] = (
    ("میلیارد", 1_000_000_000),
    ("میلیون", 1_000_000),
    ("هزار", 1_000),
    ("تومان", 1),
    ("دلار", 1),
)

_NUMBER_RE = re.compile(r"(\d[\d.,٫،]*)\s*(میلیارد|میلیون|هزار|تومان|دلار)?")


@dataclass(slots=True)
class AlertExpression:
    """نتیجهٔ پارس: قلم، جهت و آستانه (هر کدام می‌تواند خالی باشد)."""

    slug: str | None
    direction: AlertDirection | None
    target: float | None
    raw: str = ""
    scale_word: str = ""

    @property
    def complete(self) -> bool:
        """آیا همهٔ اجزای لازم پیدا شد؟"""
        return bool(self.slug and self.direction and self.target and self.target > 0)

    @property
    def unit_word(self) -> str:
        return self.scale_word or ""


def _find_direction(text: str) -> tuple[AlertDirection | None, str]:
    """یافتن جهت شرط و برگرداندن متن بدون آن."""
    for keyword in _BELOW:
        if keyword in text:
            return AlertDirection.BELOW, text.replace(keyword, " ", 1)
    for keyword in _ABOVE:
        if keyword in text:
            return AlertDirection.ABOVE, text.replace(keyword, " ", 1)
    return None, text


def _find_target(text: str) -> tuple[float | None, str, str]:
    """یافتن بزرگ‌ترین عدد به‌همراه ضریب (هزار/میلیون/میلیارد)."""
    best: float | None = None
    best_scale = ""
    consumed: list[str] = []
    for match in _NUMBER_RE.finditer(text):
        raw, scale = match.group(1), match.group(2)
        value = to_float(raw)
        if value <= 0:
            continue
        factor = 1.0
        if scale:
            for word, multiplier in _SCALES:
                if word == scale:
                    factor = multiplier
                    break
        scaled = value * factor
        if best is None or scaled > best:
            best = scaled
            best_scale = scale or ""
        consumed.append(match.group(0))
    for chunk in consumed:
        text = text.replace(chunk, " ", 1)
    return best, text, best_scale


def parse_alert_expression(text: str) -> AlertExpression:
    """پارس یک عبارت هشدار.

    اگر بخشی پیدا نشود، همان بخش ``None`` می‌ماند تا هندلر بتواند مرحلهٔ
    بعدی را از کاربر بپرسد — نه اینکه مقدار پیش‌فرض بسازد.
    """
    raw = (text or "").strip()
    if not raw:
        return AlertExpression(None, None, None, raw)

    direction, rest = _find_direction(raw)
    target, rest_after_number, scale = _find_target(rest)
    asset = asset_registry.search(rest_after_number)
    if asset is None:
        # شاید در بخش شاملِ عدد هم نام قلم بوده (مثلاً «طلای ۱۸»)
        asset = asset_registry.search(rest)
    return AlertExpression(
        slug=asset.slug if asset else None,
        direction=direction,
        target=target,
        raw=raw,
        scale_word=scale,
    )


def detect_direction(text: str) -> AlertDirection | None:
    """فقط جهت شرط — برای حالتی که کاربر عدد را در پیام بعدی می‌فرستد."""
    direction, _ = _find_direction(text or "")
    return direction


__all__ = ["AlertExpression", "detect_direction", "parse_alert_expression"]
