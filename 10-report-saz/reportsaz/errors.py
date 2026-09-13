# -*- coding: utf-8 -*-
"""خطاهای قابل‌نمایش به کاربر.

قاعدهٔ این ماژول یک جمله است: **خطای کاربر با خطای برنامه قاطی نمی‌شود.**
هر چیزی که از ``ReportSazError`` ارث می‌برد، پیامش برای کاربر نوشته شده و
سرور آن را با کد وضعیت مناسب برمی‌گرداند؛ هر چیز دیگری خطای واقعی است، در
لاگ با رد کامل ثبت می‌شود و کاربر فقط یک پیام کوتاه می‌بیند.

بدون این تفکیک، هر اشتباه کاربر (فایل خراب، فرمت نادرست، فایل خالی) به
«خطای داخلی سرور» تبدیل می‌شود و رفع مشکل برای کاربر ناممکن می‌شود.
"""
from __future__ import annotations


class ReportSazError(Exception):
    """پایهٔ خطاهای کاربرمحور."""

    #: کد وضعیت HTTP که این خطا باید با آن برگردد.
    status = 400
    #: کلید کوتاه برای مصرف‌کنندهٔ ماشینی.
    code = "error"

    def __init__(self, message: str, *, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class MissingFileError(ReportSazError):
    code = "missing_file"


class FileTooLargeError(ReportSazError):
    code = "file_too_large"
    status = 413


class UnsupportedFormatError(ReportSazError):
    code = "unsupported_format"


class LegacyFormatError(ReportSazError):
    """فرمت قدیمی که می‌شناسیم ولی نمی‌توانیم بخوانیم — با راهنمای تبدیل."""

    code = "legacy_format"


class CorruptFileError(ReportSazError):
    code = "corrupt_file"


class EmptyFileError(ReportSazError):
    code = "empty_file"


class EmptyDatasetError(ReportSazError):
    """فایل خوانده شد ولی هیچ سطر داده‌ای نداشت."""

    code = "empty_dataset"


class NoHeaderError(ReportSazError):
    code = "no_header"


class TooManyColumnsError(ReportSazError):
    code = "too_many_columns"


class DatasetNotFoundError(ReportSazError):
    code = "dataset_not_found"
    status = 404


class UnknownThemeError(ReportSazError):
    code = "unknown_theme"


class ExportFailedError(ReportSazError):
    code = "export_failed"
    status = 500
