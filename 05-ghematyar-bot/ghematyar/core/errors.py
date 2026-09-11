# -*- coding: utf-8 -*-
"""خطاهای دامنهٔ برنامه.

همهٔ خطاها یک ریشه دارند تا لایهٔ ربات بتواند یک‌جا و به‌صورت کنترل‌شده
رفتار کند. هیچ خطایی باعث نمایش دادهٔ ساختگی نمی‌شود؛ نبود داده یک وضعیت
صریح است، نه یک استثنای پنهان.
"""
from __future__ import annotations


class GhematyarError(Exception):
    """ریشهٔ همهٔ خطاهای برنامه."""


class UnknownAsset(GhematyarError):
    """قلم درخواستی در فهرست دارایی‌ها نیست."""

    def __init__(self, query: str) -> None:
        super().__init__(f"asset not found: {query}")
        self.query = query


class ProviderError(GhematyarError):
    """خطای یک ارائه‌دهندهٔ داده (شبکه، پاسخ نامعتبر، نرخ درخواست)."""

    def __init__(self, provider: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message
        self.retryable = retryable


class MalformedResponse(ProviderError):
    """پاسخ ارائه‌دهنده ساختار مورد انتظار را ندارد."""

    def __init__(self, provider: str, message: str = "malformed response") -> None:
        super().__init__(provider, message, retryable=False)


class RateLimited(ProviderError):
    """ارائه‌دهنده نرخ درخواست را محدود کرده است."""

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        super().__init__(provider, "rate limited", retryable=True)
        self.retry_after = retry_after


class CircuitOpen(ProviderError):
    """مدارشکن باز است؛ ارائه‌دهنده موقتاً کنار گذاشته شده است."""

    def __init__(self, provider: str, remaining: float) -> None:
        super().__init__(provider, f"circuit open for {remaining:.0f}s", retryable=False)
        self.remaining = remaining


class PriceUnavailable(GhematyarError):
    """هیچ ارائه‌دهنده‌ای دادهٔ قابل‌اتکا برنگرداند.

    این خطا وضعیت «دردسترس نیست» را حمل می‌کند و ربات باید آن را صادقانه
    به کاربر نشان دهد — نه اینکه دادهٔ قدیمی یا ساختگی را live جا بزند.
    """

    def __init__(self, slugs: list[str] | None = None, detail: str = "") -> None:
        self.slugs = slugs or []
        self.detail = detail
        names = "، ".join(self.slugs) if self.slugs else "قیمت‌ها"
        super().__init__(f"price unavailable for: {names}")


class StaleData(GhematyarError):
    """داده در کش هست ولی از حد تحمل قدیمی‌تر است."""

    def __init__(self, age_seconds: float) -> None:
        self.age_seconds = age_seconds
        super().__init__(f"data is stale ({age_seconds:.0f}s old)")


class AlertLimitReached(GhematyarError):
    """کاربر به سقف تعداد هشدارها رسیده است."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"alert limit reached: {limit}")


class DuplicateAlert(GhematyarError):
    """هشدار یکسان از قبل برای همین کاربر ثبت شده است."""

    def __init__(self, alert_id: int) -> None:
        self.alert_id = alert_id
        super().__init__(f"duplicate alert (existing id={alert_id})")


class AlertNotFound(GhematyarError):
    """هشدار درخواستی برای این کاربر وجود ندارد."""

    def __init__(self, alert_id: int) -> None:
        self.alert_id = alert_id
        super().__init__(f"alert not found: {alert_id}")


class NotificationSuppressed(GhematyarError):
    """اعلان به‌دلیل محدودیت نرخ یا فاصلهٔ زمانی ارسال نشد."""
