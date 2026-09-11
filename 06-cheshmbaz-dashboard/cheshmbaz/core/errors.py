# -*- coding: utf-8 -*-
"""خطاهای دامنه.

همهٔ خطاها یک ریشه دارند تا لایهٔ API بتواند یک‌جا و یکدست به آن‌ها پاسخ
بدهد. هیچ خطایی به «نمایش عدد ساختگی» ترجمه نمی‌شود؛ نبود داده یک وضعیت
صریح است، نه چیزی که پنهان شود.
"""
from __future__ import annotations

from .formatting import fa_digits


class CheshmbazError(Exception):
    """ریشهٔ همهٔ خطاهای برنامه."""

    code = "internal_error"
    http_status = 500
    message = "خطای داخلی سرویس"

    def to_payload(self) -> dict:
        return {"code": self.code, "message": self.message}


class UnknownAsset(CheshmbazError):
    """قلم درخواستی در رجیستری نیست."""

    code = "unknown_asset"
    http_status = 404
    message = "قلم درخواستی یافت نشد"

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.message = f"قلم «{slug}» در فهرست دارایی‌ها نیست"
        super().__init__(self.message)


class DataUnavailable(CheshmbazError):
    """هیچ منبعی دادهٔ قابل‌اتکا برنگرداند."""

    code = "data_unavailable"
    http_status = 503
    message = "داده در دسترس نیست"

    def __init__(self, slugs: list[str] | None = None, detail: str = "") -> None:
        self.slugs = slugs or []
        self.detail = detail
        self.message = "در حال حاضر داده‌ای از منابع دریافت نشد"
        super().__init__(self.message)


class StaleData(CheshmbazError):
    """داده در ذخیره‌سازی هست ولی از حد تحمل قدیمی‌تر است."""

    code = "stale_data"
    http_status = 409
    message = "داده موجود قدیمی است"

    def __init__(self, age_seconds: float) -> None:
        self.age_seconds = age_seconds
        self.message = "آخرین دادهٔ موجود از حد مجاز قدیمی‌تر است"
        super().__init__(self.message)


class ProviderError(CheshmbazError):
    """خطای یک ارائه‌دهندهٔ داده (شبکه، مهلت زمانی، پاسخ نامعتبر)."""

    code = "provider_error"
    http_status = 502

    def __init__(self, provider: str, message: str, *, retryable: bool = True) -> None:
        self.provider = provider
        self.raw_message = message
        self.retryable = retryable
        self.message = f"منبع {provider} پاسخ نداد"
        super().__init__(f"{provider}: {message}")


class MalformedResponse(ProviderError):
    """پاسخ ارائه‌دهنده ساختار مورد انتظار را ندارد."""

    code = "malformed_response"

    def __init__(self, provider: str, message: str = "malformed response") -> None:
        super().__init__(provider, message, retryable=False)


class CircuitOpen(ProviderError):
    """مدارشکن باز است؛ ارائه‌دهنده موقتاً کنار گذاشته شده است."""

    code = "circuit_open"

    def __init__(self, provider: str, remaining: float) -> None:
        super().__init__(provider, f"circuit open for {remaining:.0f}s", retryable=False)
        self.remaining = remaining


class ValidationError(CheshmbazError):
    """ورودی نامعتبر."""

    code = "validation_error"
    http_status = 400
    message = "ورودی نامعتبر"

    def __init__(self, message: str, field: str | None = None) -> None:
        self.field = field
        self.message = message
        super().__init__(message)
        if field:
            self.field_name = field

    def to_payload(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        field = getattr(self, "field_name", None)
        if field:
            payload["field"] = field
        return payload


class RuleNotFound(CheshmbazError):
    """قاعدهٔ هشدار وجود ندارد."""

    code = "rule_not_found"
    http_status = 404
    message = "قاعدهٔ هشدار یافت نشد"

    def __init__(self, rule_id: int) -> None:
        self.rule_id = rule_id
        # شناسه عدد کمیتی نیست؛ جداکنندهٔ هزارگان نمی‌گیرد
        self.message = f"قاعدهٔ هشدار شمارهٔ {fa_digits(rule_id)} یافت نشد"
        super().__init__(self.message)


class RateLimited(ProviderError):
    """ارائه‌دهنده نرخ درخواست را محدود کرده است."""

    code = "rate_limited"

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        super().__init__(provider, "rate limited", retryable=True)
        self.retry_after = retry_after


__all__ = [
    "CheshmbazError",
    "CircuitOpen",
    "DataUnavailable",
    "MalformedResponse",
    "ProviderError",
    "RateLimited",
    "RuleNotFound",
    "StaleData",
    "UnknownAsset",
    "ValidationError",
]
