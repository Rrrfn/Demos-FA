# -*- coding: utf-8 -*-
"""ساخت نسخه‌های کم‌حجم عکس‌ها برای نمایش در صفحه.

عکس‌های برداشت‌شده از ویکی‌انبار در ابعاد اصلی (حدود ۱۹۲۰ پیکسل) و هرکدام ۱۵۰ تا
۳۵۰ کیلوبایت‌اند. نمایش آن‌ها در کارتی که عرضش ۳۶۰ پیکسل است، پهنای باند
بی‌دلیلی می‌سوزاند: یک صفحهٔ جست‌وجو با دوازده کارت، نزدیک سه مگابایت عکس
می‌کشد در حالی که دویست کیلوبایت کافی است.

این ابزار برای هر عکس دو نسخه می‌سازد:

* ``card`` — عرض ۶۴۰ پیکسل برای کارت‌ها و فهرست‌ها
* ``hero`` — عرض ۱۵۰۰ پیکسل برای نمای اصلی صفحهٔ ملک و بنر خانه

قاعدهٔ اجرا **بی‌اثر بودن تکرار** است: اگر نسخهٔ موجود از فایل اصلی تازه‌تر
باشد، دوباره ساخته نمی‌شود. پس می‌توان این را در هر استقرار صدا زد.

اجرا::

    python -m tools.make_thumbs
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from khoneyab.config import PHOTO_DIR, THUMB_DIR  # noqa: E402

#: فایل ابعاد — کنار نسخه‌های کم‌حجم. قالب‌ها از اینجا عرض و ارتفاع واقعی
#: هر تصویر را می‌خوانند تا مرورگر جای درست را پیش از دانلود رزرو کند.
DIMENSIONS_PATH = os.path.join(THUMB_DIR, "dimensions.json")

#: (نام نسخه، عرض، کیفیت) — ارتفاع به نسبت حفظ می‌شود.
#:
#: ``tiny`` برای جایی است که عکس در اندازهٔ انگشتی دیده می‌شود — جدول اعتبار
#: تصاویر با ۲۹ ردیف. با نسخهٔ کارتی، همان جدول نزدیک یک مگابایت عکس می‌کشید.
VARIANTS: tuple[tuple[str, int, int], ...] = (
    ("tiny", 200, 72),
    ("card", 640, 76),
    ("hero", 1500, 78),
)

SOURCE_SUFFIXES = (".jpg", ".jpeg", ".png")


def thumb_path(name: str, variant: str) -> str:
    """مسیر نسخهٔ کم‌حجم یک عکس."""
    stem, _ = os.path.splitext(name)
    return os.path.join(THUMB_DIR, f"{stem}.{variant}.jpg")


def is_fresh(source: str, target: str) -> bool:
    """آیا نسخهٔ موجود به‌روز است؟"""
    if not os.path.exists(target):
        return False
    return os.path.getmtime(target) >= os.path.getmtime(source)


def measure(path: str) -> list[int]:
    """عرض و ارتفاع یک فایل تصویر."""
    from PIL import Image

    with Image.open(path) as image:
        return [image.width, image.height]


def write_dimensions() -> dict:
    """ثبت ابعاد واقعی همهٔ نسخه‌ها در یک فایل JSON.

    قالب‌ها به این ابعاد نیاز دارند. نوشتن عدد ساختگی (مثلاً «۱۹۲۰» برای
    تصویری که ۱۲۸۰ است) در ``srcset`` و در ویژگی‌های ``width``/``height``
    باعث انتخاب غلط مرورگر و پرش چیدمان می‌شود؛ عدد باید واقعی باشد.
    """
    # کلیدها از خود فهرست نسخه‌ها می‌آیند تا با اضافه‌شدن نسخهٔ تازه
    # (مثل ``tiny``) این تابع از قلم نیفتد.
    table: dict[str, dict[str, list[int]]] = {
        "source": {}, **{name: {} for name, _, _ in VARIANTS}
    }
    for source in sources():
        name = os.path.basename(source)
        try:
            table["source"][name] = measure(source)
        except Exception:
            continue
        for variant, _, _ in VARIANTS:
            path = thumb_path(name, variant)
            if os.path.exists(path):
                table[variant][name] = measure(path)
    os.makedirs(THUMB_DIR, exist_ok=True)
    with open(DIMENSIONS_PATH, "w", encoding="utf-8") as handle:
        json.dump(table, handle, ensure_ascii=False, indent=1, sort_keys=True)
    return table


def build_one(source: str, variant: str, width: int, quality: int) -> bool:
    """ساخت یک نسخه. خروجی: آیا فایل تازه ساخته شد؟"""
    target = thumb_path(os.path.basename(source), variant)
    if is_fresh(source, target):
        return False

    # Pillow فقط وقتی وارد می‌شود که واقعاً کاری مانده باشد. در یک استقرار
    # معمولی همهٔ نسخه‌ها موجودند و این import هیچ‌وقت هزینه‌اش پرداخت نمی‌شود.
    from PIL import Image, ImageOps

    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if image.width > width:
            ratio = width / float(image.width)
            image = image.resize(
                (width, max(1, int(round(image.height * ratio)))),
                Image.LANCZOS,
            )
        os.makedirs(os.path.dirname(target), exist_ok=True)
        image.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
    return True


def sources() -> list[str]:
    names = []
    for entry in sorted(os.listdir(PHOTO_DIR)):
        if entry.lower().endswith(SOURCE_SUFFIXES):
            names.append(os.path.join(PHOTO_DIR, entry))
    return names


def build_all(*, quiet: bool = False) -> dict[str, int]:
    """ساخت همهٔ نسخه‌ها برای همهٔ عکس‌ها. خروجی: آمار."""
    stats = {"sources": 0, "built": 0, "skipped": 0, "failed": 0}
    for source in sources():
        stats["sources"] += 1
        for variant, width, quality in VARIANTS:
            try:
                if build_one(source, variant, width, quality):
                    stats["built"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as error:  # یک عکس خراب نباید کل ساخت را بخواباند
                stats["failed"] += 1
                if not quiet:
                    print(f"  ! {os.path.basename(source)} [{variant}]: {error}")
    if stats["built"] or not os.path.exists(DIMENSIONS_PATH):
        write_dimensions()
    if not quiet:
        print(
            f"عکس‌ها: {stats['sources']} منبع، {stats['built']} نسخه ساخته شد، "
            f"{stats['skipped']} از قبل موجود، {stats['failed']} ناموفق"
        )
    return stats


def pending() -> list[tuple[str, str]]:
    """کارهای باقی‌مانده — بدون وارد کردن Pillow."""
    todo: list[tuple[str, str]] = []
    for source in sources():
        for variant, _, _ in VARIANTS:
            if not is_fresh(source, thumb_path(os.path.basename(source), variant)):
                todo.append((source, variant))
    return todo


def ensure_all() -> dict[str, int] | None:
    """ساخت نسخه‌ها تنها اگر لازم باشد — برای راه‌اندازی برنامه.

    اگر همه‌چیز به‌روز باشد ``None`` برمی‌گردد و هیچ کاری نمی‌کند؛ پس صدا زدنش
    در هر بار بالا آمدن سرویس بی‌هزینه است.
    """
    if not pending():
        return None
    return build_all(quiet=True)


if __name__ == "__main__":
    build_all()
