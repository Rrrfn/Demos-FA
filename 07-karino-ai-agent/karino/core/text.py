# -*- coding: utf-8 -*-
"""ابزارهای متن فارسی — پاک‌سازی، یکسان‌سازی و قالب‌بندی.

یکسان‌سازی متن مهم‌ترین پایهٔ تطبیق مهارت است: «پایتون» و «پايتون» (با ی عربی)
و «Python» و «python» باید یک چیز شمرده شوند. همین‌طور نیم‌فاصله و اعداد.
"""
from __future__ import annotations

import html
import re
import unicodedata

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

#: جداکنندهٔ هزارگان فارسی (U+066C) — نه ویرگول لاتین
THOUSANDS_SEP = "٬"

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]")

#: نویسه‌هایی که در متن فارسی/عربی به‌شکل‌های گوناگون تایپ می‌شوند
_CHAR_MAP = {
    "ي": "ی", "ى": "ی", "ﻯ": "ی",
    "ك": "ک", "ﻙ": "ک",
    "ة": "ه", "ۀ": "ه",
    "أ": "ا", "إ": "ا", "آ": "آ", "ٱ": "ا",
    "ؤ": "و", "ئ": "ی",
    "ـ": "",          # کشیده
}

#: واژه‌هایی که در متن آگهی معنی «دورکاری» می‌دهند
REMOTE_HINTS = ("دورکاری", "دور کار", "ریموت", "از راه دور", "remote", "work from home", "wfh", "anywhere")

#: واژه‌های «پروژه‌ای/فریلنس»
FREELANCE_HINTS = ("پروژه ای", "پروژه‌ای", "فریلنس", "فریلنسری", "قراردادی", "freelance", "contract", "part-time", "پارت تایم", "پارت‌تایم")

#: واژه‌های «تمام‌وقت»
FULLTIME_HINTS = ("تمام وقت", "تمام‌وقت", "full-time", "full time", "fulltime")

#: واژه‌های «کارآموزی»
INTERNSHIP_HINTS = ("کارآموز", "کارآموزی", "intern", "internship")


def strip_html(raw: str | None) -> str:
    """حذف تگ‌های HTML، رمزگشایی موجودیت‌ها و فشرده‌کردن فاصله‌ها."""
    if not raw:
        return ""
    text = html.unescape(str(raw))
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = _HTML_TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize_fa(text: str | None) -> str:
    """یکسان‌سازی متن برای تطبیق: ی/ک عربی، اعداد، نیم‌فاصله و فاصله‌ها.

    نیم‌فاصله (U+200C) حذف نمی‌شود بلکه به فاصلهٔ معمولی تبدیل می‌شود، تا
    «دورکاری» و «دور کاری» به یک شکل برسند و هر دو الگو یکی شوند.

    اعداد (چه فارسی و چه عربی) به شکل لاتین درمی‌آیند، چون این تابع پایهٔ
    *تطبیق* است نه نمایش: با یک شکل ثابت، الگویی مثل «python3» یا «۴G»
    همیشه پیدا می‌شود. نمایش اعداد فارسی کارِ ``fa_number`` است.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.translate(str.maketrans(PERSIAN_DIGITS + ARABIC_DIGITS,
                                        "0123456789" * 2))
    text = text.translate(str.maketrans(_CHAR_MAP))
    text = _ZERO_WIDTH.sub(" ", text)
    text = text.replace("\u00a0", " ")
    text = _WS.sub(" ", text)
    return text.strip()


def search_key(text: str | None) -> str:
    """کلید جست‌وجو/تطبیق: بدون HTML، فارسی‌شده، بدون فاصله‌های اضافی و lowercase."""
    return normalize_fa(strip_html(text)).lower()


def compact(text: str | None, limit: int = 240) -> str:
    """برش متن برای نمایش کارتی، با احترام به مرز واژه."""
    clean = strip_html(text)
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"


def fa_digits(text) -> str:
    """رقم‌های لاتین یک متن را به رقم فارسی بدل می‌کند (بدون گروه‌بندی).

    برای مقدارهایی که عدد نیستند ولی رقم دارند — مثل شمارهٔ نسخه (``1.0``)
    یا کد شناسه. قاعدهٔ محصول این است که متن نمایشی هیچ رقم لاتینی نداشته
    باشد؛ این تابع همان قاعده را برای رشته‌ها اجرا می‌کند.
    """
    if text is None:
        return ""
    return str(text).translate(str.maketrans("0123456789", PERSIAN_DIGITS))


def fa_number(value: int | float, *, group: bool = True) -> str:
    """تبدیل عدد به رشتهٔ فارسی؛ ``group`` جداکنندهٔ هزارگان می‌گذارد.

    برای شناسه‌ها ``group=False`` لازم است، وگرنه «۱۲۳۴» به «۱٬۲۳۴» تبدیل
    می‌شود و شناسه را خراب می‌کند.
    """
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        digits = f"{value:,}" if group else str(value)
    else:
        digits = f"{value:,.1f}" if group else f"{value:.1f}"
    if group:
        # ویرگول لاتین در متن فارسی ناهمخوان است؛ به جداکنندهٔ فارسی برمی‌گردد
        digits = digits.replace(",", THOUSANDS_SEP)
    return digits.translate(str.maketrans("0123456789", PERSIAN_DIGITS))


def fa_delta(value: int) -> str:
    """تغییر عددی با علامت — «+۱۲» یا «−۵» (منهای واقعی، نه خط تیره)."""
    if value > 0:
        return "＋" + fa_number(value)
    if value < 0:
        return "−" + fa_number(abs(value))
    return fa_number(0)


def relative_time(ts: int | None, *, now: int | None = None) -> str:
    """زمان نسبی فارسی: «همین حالا»، «۳ ساعت پیش»، «۲ روز پیش»."""
    import time as _time

    if not ts:
        return "نامشخص"
    now = int(now if now is not None else _time.time())
    delta = max(0, now - int(ts))
    if delta < 90:
        return "همین حالا"
    minutes = delta // 60
    if minutes < 60:
        return f"{fa_number(minutes)} دقیقه پیش"
    hours = minutes // 60
    if hours < 24:
        return f"{fa_number(hours)} ساعت پیش"
    days = hours // 24
    if days < 30:
        return f"{fa_number(days)} روز پیش"
    months = days // 30
    if months < 12:
        return f"{fa_number(months)} ماه پیش"
    return f"{fa_number(days // 365)} سال پیش"


def freshness_band(ts: int | None, *, now: int | None = None) -> str:
    """دستهٔ تازگی: fresh / recent / aging / stale / unknown."""
    import time as _time

    if not ts:
        return "unknown"
    now = int(now if now is not None else _time.time())
    days = max(0.0, (now - int(ts)) / 86_400)
    if days <= 3:
        return "fresh"
    if days <= 7:
        return "recent"
    if days <= 21:
        return "aging"
    return "stale"


def has_any(haystack: str, needles: tuple[str, ...]) -> bool:
    """آیا متنِ از قبل یکسان‌شده یکی از الگوها را دارد؟"""
    return any(n in haystack for n in needles)


#: نگاشت شکل‌های ناهمگون منابع به کلید یکسان نوع همکاری. منابع عبارت‌هایی
#: مثل ``full_time``، ``Full-Time`` و ``contract`` می‌فرستند؛ اگر این‌ها
#: یکسان نشوند، برچسب فارسی پیدا نمی‌کنند و متن خام انگلیسی به رابط می‌رسد.
ENGAGEMENT_ALIASES: dict[str, str] = {
    "fulltime": "fulltime", "full time": "fulltime", "full_time": "fulltime",
    "full-time": "fulltime", "تمام وقت": "fulltime", "تمام‌وقت": "fulltime",
    "permanent": "fulltime",
    "freelance": "freelance", "freelancer": "freelance", "contract": "freelance",
    "contractor": "freelance", "part time": "freelance", "part_time": "freelance",
    "part-time": "freelance", "پروژه‌ای": "freelance", "قراردادی": "freelance",
    "internship": "internship", "intern": "internship", "trainee": "internship",
    "کارآموزی": "internship",
    "unknown": "unknown", "": "unknown",
}


def canonical_engagement(raw: str | None) -> str:
    """نوع همکاری خام منبع → یکی از کلیدهای استاندارد پروفایل.

    ناشناخته‌ها به ``unknown`` برمی‌گردند تا رابط هرگز متن خام انگلیسی
    (مثل ``full_time``) را به کاربر نشان ندهد.
    """
    key = search_key(raw).strip()
    if key in ENGAGEMENT_ALIASES:
        return ENGAGEMENT_ALIASES[key]
    return detect_engagement(key) if key else "unknown"


def detect_engagement(text_key: str) -> str:
    """نوع همکاری: internship / freelance / fulltime / unknown."""
    if has_any(text_key, INTERNSHIP_HINTS):
        return "internship"
    if has_any(text_key, FREELANCE_HINTS):
        return "freelance"
    if has_any(text_key, FULLTIME_HINTS):
        return "fulltime"
    return "unknown"


SENIORITY_HINTS: dict[str, tuple[str, ...]] = {
    "junior": ("جونیور", "تازه کار", "تازه‌کار", "کارآموز", "junior", "entry level", "entry-level", "intern", "مبتدی"),
    "mid": ("میان رده", "میان‌رده", "mid level", "mid-level", "intermediate", "middle", "mid "),
    "senior": ("سنیور", "ارشد", "senior", "sr.", "sr ", "lead", "لید", "سرپرست تیم", "principal", "staff engineer"),
}


def detect_seniority(text_key: str) -> str:
    """سطح ارشدیت از متن آگهی. ترتیب: senior → junior → mid (ارشد قوی‌تر است)."""
    for level in ("senior", "junior", "mid"):
        if has_any(text_key, SENIORITY_HINTS[level]):
            return level
    return "unknown"


def normalize_title(title: str) -> str:
    """عنوان را برای کلید یکتایی/تطبیق تکراری آماده می‌کند."""
    key = search_key(title)
    key = re.sub(r"[^\w\sآ-ی]", " ", key)
    return _WS.sub(" ", key).strip()
