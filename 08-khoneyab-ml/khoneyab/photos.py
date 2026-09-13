# -*- coding: utf-8 -*-
"""انتساب عکس به آگهی‌ها بر پایهٔ فهرست عکس‌های دانلودشده.

هر ملک در این پروژه سینتتیک است، پس «عکس واقعی آن ملک» وجود ندارد. کاری که
اینجا انجام می‌شود انتساب عکس‌های واقعیِ با مجوز آزاد به آگهی‌های نمونه است:
همان کاری که در یک نمونه‌کار با داده‌ی نمایشی معنا دارد. شرط استفاده، ثبت
نام پدیدآورنده و مجوز است که در فایل ``CREDITS.md`` و در صفحهٔ «متدولوژی»
آمده است.

دو قاعده رعایت می‌شود:

۱) **پایداری.** یک آگهی همیشه همان عکس را می‌گیرد. انتساب بر پایهٔ شمارهٔ آگهی
   محاسبه می‌شود، نه تصادفی؛ پس با هر بار بازآفرینی صفحه عکس‌ها نمی‌پرند.
۲) **صداقت.** اگر عکسی موجود نباشد، جای آن خالی می‌ماند و رابط پیام مناسب
   نشان می‌دهد؛ هیچ عکس جانشین ساختگی یا آیکون تزئینی جای عکس واقعی نمی‌گذارد.
"""
from __future__ import annotations

import json
import os

from .config import PHOTO_DIR, THUMB_DIR

MANIFEST_PATH = os.path.join(PHOTO_DIR, "manifest.json")

#: پیشوند نشانی عکس‌ها. مسیر مطلق است (با اسلش ابتدایی) چون وبه‌سرور پوشهٔ
#: ``static`` را از ریشه سرو می‌کند؛ مسیر نسبی در صفحه‌های تودرتو (مثل
#: ``/listing/KH-1001``) به مسیر جاری می‌چسبد و عکس پیدا نمی‌شود.
PHOTO_URL_PREFIX = "/static/img/properties/"
THUMB_URL_PREFIX = "/static/img/properties/thumbs/"

#: نام نسخه‌های کم‌حجم، هم‌آهنگ با ``tools/make_thumbs.py``.
TINY_VARIANT = "tiny"
CARD_VARIANT = "card"
HERO_VARIANT = "hero"
FULL_VARIANT = "source"

#: فایل ابعاد واقعی — نوشتهٔ ``tools/make_thumbs.py``.
DIMENSIONS_PATH = os.path.join(THUMB_DIR, "dimensions.json")
_dimensions_cache: dict | None = None


def load_manifest() -> list[dict]:
    """خواندن فهرست عکس‌ها. در نبود فایل، فهرست خالی برمی‌گردد."""
    if not os.path.exists(MANIFEST_PATH):
        return []
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as handle:
            entries = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return [entry for entry in entries if _file_exists(entry.get("file"))]


def _file_exists(name: str | None) -> bool:
    return bool(name) and os.path.exists(os.path.join(PHOTO_DIR, name))


def by_kind(entries: list[dict], kind: str) -> list[str]:
    """نام فایل‌های یک دسته («exterior» یا «interior») به ترتیب فهرست."""
    return [entry["file"] for entry in entries if entry.get("kind") == kind]


def license_family(name: str | None) -> str:
    """مجوز به خانوادهٔ خوانا و بدون شمارهٔ نسخه تبدیل می‌شود.

    متن مجوز ویکی‌انبار با شمارهٔ نسخه می‌آید (``CC BY-SA 4.0``) و در رابط
    فارسی رقم لاتین می‌سازد. عبارت ``CC BY-SA`` همان معنا را می‌رساند و لازم
    نیست شمارهٔ نسخه در متن دیده‌شده بیاید (نسخهٔ دقیق در جدول اعتبارها و در
    ``CREDITS.md`` ثبت است).
    """
    low = (name or "").strip().lower()
    if not low or low in ("—", "pdm"):
        return "نامشخص"
    if low.startswith("cc0") or "public domain" in low:
        return "مالکیت عمومی"
    if "by-nc" in low:
        return "CC BY-NC (غیرتجاری)"
    if "by-sa" in low:
        return "CC BY-SA"
    if low.startswith("cc by"):
        return "CC BY"
    return "سایر"


def photo_url(name: str | None) -> str:
    """نشانی وب نسخهٔ اصلی عکس."""
    return f"{PHOTO_URL_PREFIX}{name}" if name else ""


def variant_exists(name: str, variant: str) -> bool:
    """آیا نسخهٔ کم‌حجم این عکس ساخته شده است؟"""
    stem, _ = os.path.splitext(name or "")
    return bool(stem) and os.path.exists(os.path.join(THUMB_DIR, f"{stem}.{variant}.jpg"))


def variant_url(name: str | None, variant: str) -> str:
    """نشانی نسخهٔ کم‌حجم؛ در نبود آن، برمی‌گردد به نسخهٔ اصلی.

    این عقب‌نشینی عمدی است: اگر مرحلهٔ ساخت نسخه‌های کم‌حجم در استقرار اجرا
    نشود، سایت باید همچنان کار کند — فقط سنگین‌تر، نه شکسته.
    """
    if not name:
        return ""
    if variant_exists(name, variant):
        stem, _ = os.path.splitext(name)
        return f"{THUMB_URL_PREFIX}{stem}.{variant}.jpg"
    return photo_url(name)


def dimensions() -> dict:
    """جدول ابعاد واقعی — یک بار خوانده و نگه داشته می‌شود."""
    global _dimensions_cache
    if _dimensions_cache is None:
        try:
            with open(DIMENSIONS_PATH, encoding="utf-8") as handle:
                _dimensions_cache = json.load(handle)
        except (OSError, json.JSONDecodeError):
            _dimensions_cache = {}
    return _dimensions_cache


def size_of(name: str | None, variant: str = CARD_VARIANT) -> tuple[int, int] | None:
    """ابعاد واقعی یک نسخهٔ مشخص، یا ``None`` اگر ناشناخته باشد."""
    if not name:
        return None
    entry = dimensions().get(variant, {}).get(name)
    if not entry or len(entry) != 2:
        return None
    return int(entry[0]), int(entry[1])


def sized(name: str | None, variant: str = CARD_VARIANT) -> dict[str, object]:
    """اطلاعات یک عکس برای قالب: نشانی و ابعاد واقعی.

    عمداً از ``srcset`` استفاده نمی‌شود. با توصیف‌گر ``w``، مرورگر بر پایهٔ
    عددی که ما اعلام می‌کنیم تصمیم می‌گیرد؛ اگر آن عدد با عرض واقعی فایل
    نخواند (مثلاً ۱۹۲۰ برای تصویری که ۱۲۸۰ است)، هم انتخاب غلط می‌شود و هم
    نسبت ابعاد اعلامی با واقعیت فرق می‌کند. اینجا هر نقش، یک فایل با اندازهٔ
    درست و ابعاد راستین می‌گیرد: کارت ۶۴۰ پیکسل، بنر تا ۱۵۰۰.
    """
    if not name:
        return {"src": "", "width": 0, "height": 0, "exists": False}

    if variant == FULL_VARIANT:
        url = photo_url(name)
        actual = size_of(name, FULL_VARIANT)
    else:
        url = variant_url(name, variant)
        actual = size_of(name, variant)

    fallback = {
        TINY_VARIANT: (200, 125),
        CARD_VARIANT: (640, 420),
        HERO_VARIANT: (1500, 900),
    }.get(variant, (1280, 800))
    width, height = actual or fallback
    return {"src": url, "width": width, "height": height, "exists": True}


def credit_for(entries: list[dict], name: str | None) -> dict:
    """اطلاعات اعتبار یک عکس — برای نمایش در صفحهٔ جزئیات و متدولوژی."""
    if not name:
        return {}
    for entry in entries:
        if entry.get("file") == name:
            return entry
    return {}


class PhotoLibrary:
    """کتابخانهٔ عکس — انتساب پایدار و دسترسی به اطلاعات اعتبار."""

    def __init__(self, entries: list[dict] | None = None) -> None:
        self.entries: list[dict] = list(entries) if entries is not None else load_manifest()
        self.exteriors: list[str] = by_kind(self.entries, "exterior")
        self.interiors: list[str] = by_kind(self.entries, "interior")

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return not self.entries

    @property
    def exteriors_count(self) -> int:
        return len(self.exteriors)

    @property
    def interiors_count(self) -> int:
        return len(self.interiors)

    def cover(self, index: int) -> str | None:
        """عکس نمای اصلی یک آگهی."""
        if self.exteriors:
            return self.exteriors[index % len(self.exteriors)]
        return self.interiors[index % len(self.interiors)] if self.interiors else None

    def gallery(self, index: int, size: int = 3) -> tuple[str, ...]:
        """نمایش اصلی + دو نمای داخلی — با گام‌های متفاوت تا تکرار کم شود."""
        chosen: list[str] = []
        cover = self.cover(index)
        if cover:
            chosen.append(cover)
        pools = [self.interiors]
        if not self.interiors:
            pools = [self.exteriors]
        step = 1
        for pool in pools:
            if not pool:
                continue
            for multiplier in (3, 5, 7):
                if len(chosen) >= size:
                    break
                candidate = pool[(index * multiplier + step) % len(pool)]
                if candidate not in chosen:
                    chosen.append(candidate)
                step += 1
        return tuple(chosen[:size])

    def credit(self, name: str | None) -> dict:
        return credit_for(self.entries, name)
