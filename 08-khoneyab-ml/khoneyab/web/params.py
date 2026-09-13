# -*- coding: utf-8 -*-
"""خواندن ورودی کاربر از رشتهٔ پرس‌وجو.

ورودی نشانی هرگز قابل اعتماد نیست: ممکن است خالی باشد، متن باشد، یا عددی
بیرون از دامنهٔ داده. این ماژول همه را به یک مقدار معتبر تبدیل می‌کند و
مقدار نامعتبر را نادیده می‌گیرد — بی‌آنکه خطا بدهد. قاعده این است که یک
فیلتر خراب نباید کل صفحه را از کار بیندازد.
"""
from __future__ import annotations

from ..config import (AGE_RANGE, AREA_RANGE, BEDROOM_RANGE, DISTRICT_CODES,
                      FLOOR_RANGE)
from ..search import SORT_OPTIONS, SearchQuery

def integer(raw: object, *, low: int | None = None, high: int | None = None) -> int | None:
    """یک عدد صحیح معتبر، یا ``None``."""
    if raw is None or raw == "":
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if low is not None and value < low:
        return None
    if high is not None and value > high:
        return None
    return value


def integer_list(raw: object, *, allowed: tuple[int, ...],
                 limit: int = 40) -> tuple[int, ...]:
    """فهرست اعداد صحیح — از ورودی تکراری یا جداشده با کاما."""
    if raw is None or raw == "":
        return ()
    values: list[object] = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    chosen: list[int] = []
    for item in values:
        value = integer(item)
        if value is not None and value in allowed and value not in chosen:
            chosen.append(value)
        if len(chosen) >= limit:
            break
    return tuple(sorted(chosen))


def flag(raw: object) -> bool:
    """پرچم بولی — حضور کلید با مقدار روشن یکی است."""
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "on", "yes", "")


#: واحد ورودی قیمت در نشانی «میلیارد تومان» است.
#: نوشتن ۹ رقم صفر در نوار نشانی نه خواناست و نه قابل اشتراک؛ ``pmax=15.5``
#: همان معنا را می‌رساند و قابل تایپ است.
BILLION = 1_000_000_000

#: سقف پذیرفته‌شدهٔ قیمت، به میلیارد تومان. گران‌ترین آگهی کاتالوگ حدود
#: ۱۵۰ میلیارد است؛ سقف هزار، هم جای رشد دارد و هم عدد بی‌معنا را رد می‌کند.
MAX_BILLIONS = 1_000


def billions(raw: object) -> int | None:
    """مقدار میلیاردی نشانی به تومان.

    ``float`` رقم فارسی را هم می‌شناسد، پس لینکی که کاربر با صفحه‌کلید فارسی
    تایپ کرده باشد هم کار می‌کند.
    """

    if raw is None or raw == "":
        return None
    try:
        value = float(str(raw).strip().replace("٫", ".").replace("٬", ""))
    except (TypeError, ValueError):
        return None
    if value <= 0 or value > MAX_BILLIONS:
        return None
    return int(round(value * BILLION))


def search_query(args) -> SearchQuery:
    """ساخت پرس‌وجوی جست‌وجو از پارامترهای نشانی.

    نام‌ها کوتاه‌اند چون در نشانی اشتراکی دیده می‌شوند:
    ``districts`` ``pmin`` ``pmax`` ``amin`` ``amax`` ``bedrooms`` ``age``
    ``parking`` ``storage`` ``elevator`` ``sort`` ``page``.
    """
    sort = args.get("sort") or "تازه‌ترین"
    if sort not in SORT_OPTIONS:
        sort = "تازه‌ترین"
    return SearchQuery(
        districts=integer_list(args.get("districts"), allowed=DISTRICT_CODES),
        price_min=billions(args.get("pmin")),
        price_max=billions(args.get("pmax")),
        area_min=integer(args.get("amin"), low=0, high=AREA_RANGE[1]),
        area_max=integer(args.get("amax"), low=0, high=AREA_RANGE[1]),
        bedrooms=integer_list(args.get("bedrooms"),
                              allowed=tuple(range(BEDROOM_RANGE[0], BEDROOM_RANGE[1] + 1)),
                              limit=8),
        age_max=integer(args.get("age"), low=AGE_RANGE[0], high=AGE_RANGE[1]),
        parking=flag(args.get("parking")),
        storage=flag(args.get("storage")),
        elevator=flag(args.get("elevator")),
        sort=sort,
        # شمارهٔ صفحه اینجا سقف نمی‌گیرد. تنها جایی که تعداد واقعی صفحه‌ها
        # معلوم است ``run_search`` است؛ همان‌جا صفحه به آخرین صفحهٔ موجود
        # بسته می‌شود. سقف گذاشتن اینجا یعنی یک نشانی اشتراکی مثل ``?page=40``
        # بی‌صدا به صفحهٔ اول بپرد، که برای کاربر گیج‌کننده است.
        page=integer(args.get("page"), low=1) or 1,
    )


#: نشانهٔ «فرم برآورد فرستاده شده». بدون آن، نبودِ یک کلید جعبهٔ انتخابی را
#: نمی‌توان از «کاربر فرم را نفرستاده» تشخیص داد؛ جعبهٔ تیک‌نخورده در HTML
#: هیچ پارامتری تولید نمی‌کند.
FORM_MARKER = "f"


def estimate_features(args, *, fallback: dict | None = None) -> dict:
    """مشخصات ملک برای برآورد — هر مقدار خارج از دامنه، نادیده گرفته می‌شود.

    اگر فرم فرستاده شده باشد، جعبه‌های تیک‌نخورده واقعاً «ندارد»‌اند. اگر
    نه، مقادیر ذخیره‌شدهٔ نشست یا پیش‌فرض می‌نشینند — وگرنه نخستین بازدید
    از صفحه، همهٔ امکانات را خاموش نشان می‌داد.
    """
    submitted = FORM_MARKER in args
    base = dict(fallback or default_features())

    def pick(key: str, low: int, high: int) -> int:
        value = integer(args.get(key), low=low, high=high)
        if value is not None:
            return value
        return int(base.get(key, default_features()[key]))

    def binary(key: str) -> int:
        if not submitted:
            return int(base.get(key, 1))
        return 1 if flag(args.get(key)) else 0

    return {
        "district": pick("district", min(DISTRICT_CODES), max(DISTRICT_CODES)),
        "area": pick("area", AREA_RANGE[0], AREA_RANGE[1]),
        "bedrooms": pick("bedrooms", BEDROOM_RANGE[0], BEDROOM_RANGE[1]),
        "age": pick("age", AGE_RANGE[0], AGE_RANGE[1]),
        "floor": pick("floor", FLOOR_RANGE[0], FLOOR_RANGE[1]),
        "parking": binary("parking"),
        "storage": binary("storage"),
        "elevator": binary("elevator"),
    }


def default_features() -> dict:
    """ملکی معمولی در شهر — نقطهٔ شروع فرم برآورد."""
    return {"district": 2, "area": 110, "bedrooms": 2, "age": 6, "floor": 3,
            "parking": 1, "storage": 1, "elevator": 1}


def ids(raw: object) -> list[str]:
    """شناسه‌های ملک از نشانی اشتراکی — مثل ``KH-1001,KH-1002``."""
    if raw is None or raw == "":
        return []
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    found: list[str] = []
    for part in parts:
        identifier = str(part).strip()
        if identifier and identifier not in found:
            found.append(identifier)
    return found
