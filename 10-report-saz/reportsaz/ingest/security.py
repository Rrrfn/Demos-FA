# -*- coding: utf-8 -*-
"""اعتبارسنجی امنیتی ورودی.

این ماژول مرز اعتماد است: هر چیزی که از اینجا رد شود، دادهٔ کاربر شمرده
می‌شود و بقیهٔ سامانه با آن مثل داده رفتار می‌کند — نه مثل کد.

چه چیزهایی بررسی می‌شود و چرا:

* **پسوند** — سقف اول. نبودنش در فهرست سفید، همان‌جا پرونده را می‌بندد.
* **محتوای واقعی (امضای بایتی)** — پسوند به‌تنهایی قابل جعل است؛ فایلی به نام
  ``data.xlsx`` می‌تواند هر چیزی باشد. امضای zip برای xlsx و نبودن بایت
  صفر/کنترل برای CSV سنجیده می‌شود.
* **نوع اعلامی مرورگر** — بررسی می‌شود ولی **ملاک نیست**؛ این مقدار از سمت
  کلاینت می‌آید و کاربر می‌تواند هر چیزی بفرستد. فقط برای تشخیص ناهماهنگی
  به‌کار می‌رود و همان را در هشدار گزارش می‌کند.
* **حجم** — هم در لایهٔ Flask (رد زودهنگام) و هم جریانی در زمان ذخیره.
* **نام فایل** — هرگز در مسیر ذخیره نمی‌شود؛ فقط در فراداده می‌ماند، آن هم
  پاک‌شده از نویسه‌های کنترلی و مسیرساز.

هیچ فایل بارگذاری‌شده‌ای هرگز اجرا نمی‌شود: خواندن داده فقط با pandas و
openpyxl انجام می‌شود و نه ``eval``، نه ``exec``، نه بارگذاری ماژول.
"""
from __future__ import annotations

import os
import re

from ..config import (ALLOWED_EXTENSIONS, LEGACY_EXTENSIONS, MAGIC,
                      MAX_UPLOAD_BYTES, extension_of)
from ..errors import (CorruptFileError, FileTooLargeError, LegacyFormatError,
                      MissingFileError, UnsupportedFormatError)

#: نویسه‌های کنترلی و مسیرساز که در نام نمایشی نمی‌مانند.
UNSAFE = re.compile(r"[\x00-\x1f\x7f<>:\"/\\|?*\u202a-\u202e]")
#: سقف طول نام نمایشی.
MAX_NAME_LENGTH = 120

#: نوع‌های اعلامی مرورگر که برای هر پسوند پذیرفته می‌شوند. مقدار خالی هم
#: پذیرفته است، چون بعضی کلاینت‌ها نوع نمی‌فرستند و ما به امضای بایتی تکیه داریم.
MIME_WHITELIST = {
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "application/vnd.ms-excel", "application/octet-stream",
             "application/zip", ""),
    "csv": ("text/csv", "text/plain", "application/csv", "application/vnd.ms-excel",
            "text/x-csv", "application/octet-stream", ""),
}

#: نشانه‌های متنی‌بودن یک فایل CSV. اگر فایل بایت صفر داشته باشد یا نسبت
#: نویسه‌های کنترل‌شدنی‌اش بالا باشد، CSV نیست — هرچه هم که پسوندش بگوید.
CONTROL_RATIO_LIMIT = 0.02
SNIFF_BYTES = 4096


def display_name(filename: str | None) -> str:
    """نام نمایشی امن — بدون مسیر، بدون نویسهٔ کنترلی، با طول محدود."""
    name = os.path.basename(str(filename or "")).strip()
    name = UNSAFE.sub("", name)
    name = name.replace("..", ".").strip(". ")
    if not name:
        return "فایل بدون نام"
    if len(name) > MAX_NAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            name = stem[: MAX_NAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_NAME_LENGTH]
    return name


def validate_name(filename: str | None, size: int | None = None) -> str:
    """بررسی نام و حجم پیش از ذخیره — سبک‌ترین سد."""
    if not filename or not str(filename).strip():
        raise MissingFileError("فایلی انتخاب نشده است. یک فایل XLSX یا CSV بفرستید.")
    size_value = int(size or 0)
    if size_value > MAX_UPLOAD_BYTES:
        raise FileTooLargeError(
            f"حجم فایل بیش از حد مجاز است. سقف مجاز "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} مگابایت است.")
    return display_name(filename)


def validate_extension(filename: str) -> str:
    """پسوند را بررسی و برمی‌گرداند."""
    extension = extension_of(filename)
    if not extension:
        raise UnsupportedFormatError(
            "فایل پسوند ندارد. ساختار فایل قابل شناسایی نیست؛ لطفاً یک فایل "
            "XLSX یا CSV معتبر انتخاب کنید.")
    if extension in LEGACY_EXTENSIONS:
        raise LegacyFormatError(
            f"قالب «{extension}» پشتیبانی نمی‌شود. فایل را در اکسل با فرمت "
            "«Excel Workbook (.xlsx)» ذخیره کنید یا آن را به CSV تبدیل کنید.")
    if extension not in ALLOWED_EXTENSIONS:
        allowed = "، ".join(item.upper() for item in ALLOWED_EXTENSIONS)
        raise UnsupportedFormatError(
            f"قالب «{extension}» پشتیبانی نمی‌شود. ساختار فایل قابل شناسایی "
            f"نیست؛ لطفاً یک فایل {allowed} معتبر انتخاب کنید.")
    return extension


def validate_content(path: str, extension: str) -> list[str]:
    """بررسی محتوای واقعی فایل با امضای بایتی. فهرست هشدارها را برمی‌گرداند."""
    warnings: list[str] = []
    try:
        with open(path, "rb") as handle:
            head = handle.read(SNIFF_BYTES)
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
    except OSError as error:
        raise CorruptFileError("فایل ذخیره‌شده خوانده نشد.", detail=str(error)) from error

    if size == 0:
        raise CorruptFileError("فایل خالی است و داده‌ای برای تحلیل ندارد.")

    if extension == "xlsx":
        if not any(head.startswith(signature) for signature in MAGIC["xlsx"]):
            raise CorruptFileError(
                "محتوای فایل با قالب XLSX نمی‌خواند یا فایل آسیب دیده است. "
                "اگر فایل در اکسل باز می‌شود، آن را دوباره با فرمت .xlsx ذخیره کنید.")
        #: فایل zip سالم با امضای درست شروع می‌شود ولی ممکن است وسط کار بریده
        #: باشد؛ دنبال نشانهٔ پایان آرشیو در انتهای فایل می‌گردیم.
        try:
            with open(path, "rb") as handle:
                handle.seek(max(0, size - 4096))
                tail = handle.read()
            if b"PK\x05\x06" not in tail and b"PK\x01\x02" not in tail:
                warnings.append(
                    "فایل ساختار آرشیو کاملی ندارد؛ اگر خطا گرفتید، آن را از "
                    "اکسل دوباره ذخیره کنید.")
        except OSError:
            pass
        return warnings

    # CSV: متن است، پس امضای بایتی ندارد. برعکسش بررسی می‌شود: نبودن نشانهٔ
    # فایل دودویی.
    if head[:4] in (MAGIC["xls"][0][:4],) or head.startswith(b"%PDF"):
        raise CorruptFileError(
            "محتوای فایل متن نیست؛ پسوند CSV با یک فایل دودویی نمی‌خواند.")
    if b"\x00" in head:
        raise CorruptFileError(
            "فایل بایت صفر دارد، پس متن خواندنی نیست. آن را با کدگذاری UTF-8 "
            "به‌صورت CSV ذخیره کنید.")
    controls = sum(1 for byte in head if byte < 9 or (13 < byte < 32))
    if head and controls / len(head) > CONTROL_RATIO_LIMIT:
        raise CorruptFileError(
            "بخش بزرگی از فایل نویسهٔ کنترلی است، پس ساختار CSV قابل تشخیص "
            "نیست. فایل را با کدگذاری UTF-8 ذخیره کنید.")
    return warnings


def check_mime(declared: str | None, extension: str) -> list[str]:
    """همخوانی نوع اعلامی با پسوند. ملاک نیست، فقط هشدار می‌دهد."""
    value = (declared or "").split(";")[0].strip().lower()
    if not value:
        return []
    allowed = MIME_WHITELIST.get(extension, ())
    if value in allowed:
        return []
    return [f"نوع اعلامی مرورگر ({value}) با پسوند {extension.upper()} یکی نیست؛ "
            f"ساختار واقعی فایل ملاک پردازش است."]


def inspect_upload(filename: str | None, declared_mime: str | None,
                   size: int | None) -> dict:
    """همهٔ بررسی‌های پیش از ذخیره، در یک فراخوانی."""
    name = validate_name(filename, size)
    extension = validate_extension(name)
    warnings = check_mime(declared_mime, extension)
    return {"display_name": name, "extension": extension, "warnings": warnings}
