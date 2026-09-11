# -*- coding: utf-8 -*-
"""منبع بازار داخلی (tgju) — طلا، سکه و ارز.

سه نکته که با مشاهدهٔ واقعی خوراک تأیید شده‌اند و رفتار این ماژول را تعیین
می‌کنند:

۱. **واحد خوراک ریال است.** برای رسیدن به تومان بر ۱۰ تقسیم می‌شود. اگر این
   تبدیل انجام نشود، همهٔ اعداد بازار داخلی ده برابر واقعیت نمایش داده
   می‌شوند.
۲. **خوراک ماشین‌خوان برای طلا، سکه و ارز هیچ درصد تغییر روزانه‌ای ندارد**
   (``dp`` برای همه صفر است). پس این ماژول هیچ تغییری نمی‌سازد؛ درصد تغییر
   در لایهٔ سرویس از تاریخچهٔ ثبت‌شدهٔ خودمان محاسبه می‌شود.
۳. **زمان مشاهده در منبع منتشر نمی‌شود** (فقط برچسب تاریخ شمسی). بنابراین
   ``observed_at`` برابر زمان واکشی می‌گذاشتیم و درستی آن صریح است.
"""
from __future__ import annotations

import time
from typing import Any, Sequence

from ..core.models import Asset, Quote
from .base import BaseProvider, HttpClient, ProviderResult

AJAX_URLS = (
    "https://call1.tgju.org/ajax.json",
    "https://call.tgju.org/ajax.json",
)


def _to_float(raw: Any) -> float | None:
    """تبدیل مقدار متنی منبع («۲۴۱,۸۱۴,۰۰۰») به عدد."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("٬", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value


def _to_toman(value: float, unit: str) -> float:
    """ریال به تومان."""
    return value / 10.0 if unit == "rial" else value


def parse_quotes(
    payload: Any,
    assets: Sequence[Asset],
    *,
    fetched_at: float | None = None,
    raw_unit: str = "rial",
) -> tuple[dict[str, Quote], list[str]]:
    """پارس خالص پاسخ خوراک — بدون شبکه، برای تست مستقیم.

    ``raw_unit`` واحدی است که خود منبع منتشر می‌کند، نه واحد خروجی؛ خوراک
    tgju ریالی است و برای رسیدن به تومان تقسیم بر ده لازم است. این پارامتر
    عمداً صریح است تا واحد خروجی رجیستری (تومان) به‌اشتباه جای واحد منبع
    گذاشته نشود.

    خروجی: (نگاشت slug → Quote، فهرست شناسه‌های غایب). هیچ مقداری حدس زده
    نمی‌شود و اقلام با قیمت نامعتبر یا صفر کنار گذاشته می‌شوند.
    """
    stamp = fetched_at if fetched_at is not None else time.time()
    if not isinstance(payload, dict):
        return {}, [asset.slug for asset in assets]

    current = payload.get("current")
    if not isinstance(current, dict):
        current = payload

    quotes: dict[str, Quote] = {}
    missing: list[str] = []

    for asset in assets:
        record = current.get(asset.provider_key or asset.slug)
        if not isinstance(record, dict):
            missing.append(asset.slug)
            continue

        raw_price = _to_float(record.get("p"))
        if raw_price is None or raw_price <= 0:
            missing.append(asset.slug)
            continue

        price = _to_toman(raw_price, raw_unit)
        low = _to_float(record.get("l"))
        high = _to_float(record.get("h"))

        quotes[asset.slug] = Quote(
            slug=asset.slug,
            price=price,
            unit="toman",
            source="tgju.org",
            observed_at=stamp,
            fetched_at=stamp,
            day_low=_to_toman(low, raw_unit) if low and low > 0 else None,
            day_high=_to_toman(high, raw_unit) if high and high > 0 else None,
            change_abs=None,
            change_pct=None,
            change_basis="",
            precision=asset.precision,
        )

    return quotes, missing


class TgjuProvider(BaseProvider):
    """ارائه‌دهندهٔ بازار داخلی."""

    name = "tgju"
    raw_unit = "rial"

    def fetch(self, assets: Sequence[Asset]) -> ProviderResult:
        started = time.perf_counter()
        assets = [asset for asset in assets if asset.kind.value != "crypto"]
        if not assets:
            return ProviderResult(name=self.name, requested=0)

        last_error: Exception | None = None
        for url in AJAX_URLS:
            try:
                payload = self.http.get_json(url, provider=self.name)
            except Exception as error:  # noqa: BLE001 - شبکه، مهلت یا JSON
                last_error = error
                continue

            quotes, missing = parse_quotes(payload, assets, raw_unit=self.raw_unit)
            if not quotes:
                last_error = None
                continue

            self.mark_stale(quotes)
            latency = int((time.perf_counter() - started) * 1000)
            return ProviderResult(
                name=self.name, quotes=quotes, latency_ms=latency, requested=len(assets)
            )

        if last_error is not None:
            raise last_error
        from ..core.errors import ProviderError

        raise ProviderError(self.name, "no usable quotes in response")


__all__ = ["AJAX_URLS", "TgjuProvider", "parse_quotes"]
