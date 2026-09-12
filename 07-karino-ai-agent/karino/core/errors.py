# -*- coding: utf-8 -*-
"""خطاهای دسته‌بندی‌شده — تا لایهٔ API بتواند کد وضعیت درست را برگرداند.

هر خطا یک ``code`` ماشین‌خوان و یک ``message`` فارسی دارد؛ رابط کاربر همان
پیام را نشان می‌دهد و کلاینت برنامه‌ای روی کد تصمیم می‌گیرد.
"""
from __future__ import annotations


class KarinoError(Exception):
    """ریشهٔ همهٔ خطاهای دامنه."""

    code = "internal_error"
    status = 500
    message = "خطای داخلی رخ داد."

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class ValidationError(KarinoError):
    code = "invalid_request"
    status = 400
    message = "درخواست نامعتبر است."


class NotFoundError(KarinoError):
    code = "not_found"
    status = 404
    message = "موردی با این شناسه پیدا نشد."


class ConflictError(KarinoError):
    code = "conflict"
    status = 409
    message = "این مورد از قبل ثبت شده است."


class SourceError(KarinoError):
    """خطای یک منبع — هرگز کل خط لوله را متوقف نمی‌کند."""

    code = "source_unavailable"
    status = 502
    message = "منبع در دسترس نیست."


class UnauthorizedError(KarinoError):
    code = "unauthorized"
    status = 401
    message = "برای این عملیات دسترسی لازم را ندارید."


class ProviderError(KarinoError):
    """خطای ارائه‌دهندهٔ بیرونی (مثلاً LLM) با برگشت امن."""

    code = "provider_error"
    status = 503
    message = "سرویس بیرونی پاسخ نداد."
