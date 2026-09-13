# -*- coding: utf-8 -*-
"""پیکربندی گزارش‌ساز — یک منبع حقیقت برای سقف‌ها، مسیرها، وزن‌ها و تم‌ها.

هر عددی که هم هستهٔ پردازش و هم رابط به آن نیاز دارند اینجاست: سقف حجم و سطر،
آستانهٔ تشخیص نوع ستون، وزن‌های امتیاز کیفیت، و پالت تم‌های گزارش. هیچ‌جای
دیگری نباید این‌ها را از نو تعریف کند، وگرنه آستانه‌ای که رابط به کاربر وعده
می‌دهد با آنچه موتور اجرا می‌کند یکی نمی‌ماند.
"""
from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
STORE_DIR = os.path.join(DATA_DIR, "store")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

for _directory in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR, STORE_DIR):
    os.makedirs(_directory, exist_ok=True)

SERVICE_NAME = "گزارش‌ساز"
SERVICE_TAGLINE = "پلتفرم هوش داده و گزارش‌سازی خودکار"

PORT = int(os.environ.get("PORT", "10000"))

# ------------------------------------------------------------------ سقف ورودی
#: سقف حجم فایل بارگذاری‌شده (بایت). Flask هم همین را برای رد کردن زودهنگام
#: درخواست بزرگ می‌خواند.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_UPLOAD_MB = MAX_UPLOAD_BYTES // (1024 * 1024)
#: سقف سطرهای خوانده‌شده. فراتر از این، فایل بریده می‌شود و *همین* به کاربر
#: گفته می‌شود — بریدن بی‌اعلام، گزارش را غلط می‌کند.
MAX_ROWS = 120_000
#: سقف ستون‌ها. فایل‌های با ستون‌های خیلی زیاد نشانهٔ ساختار اشتباه‌اند، نه داده.
MAX_COLUMNS = 120
#: سقفی که بالاتر از آن هشدار «فایل بزرگ» نشان داده می‌شود.
LARGE_FILE_BYTES = 4 * 1024 * 1024
#: تعداد سطری که برای تشخیص نوع ستون نمونه‌گیری می‌شود. تشخیص روی کل فایل
#: برای فایل بزرگ کند است و نتیجه‌اش عملاً تفاوتی ندارد.
TYPE_SAMPLE_ROWS = 6_000
#: تعداد ردیف پیش‌نمایش در رابط و گزارش.
PREVIEW_ROWS = 12
#: تعداد ردیف نمایش‌داده‌شده در جدول صفحهٔ بازرسی.
INSPECT_ROWS = 40

#: پسوندهای پشتیبانی‌شده. ``xls`` عمداً اینجا نیست: خواندنش به ``xlrd`` نیاز
#: دارد که در محیط اجرا نیست. فرستادن فایل xls با پیام روشن رد می‌شود، نه با
#: خطای عمومی.
ALLOWED_EXTENSIONS = ("xlsx", "csv")
#: پسوندهایی که می‌شناسیم و *دلیل* ردشان را می‌گوییم.
LEGACY_EXTENSIONS = ("xls", "xlsm", "ods")

#: امضای بایتی فایل‌ها — بررسی محتوا، نه فقط نام.
MAGIC = {
    "xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "ods": (b"PK\x03\x04",),
}

#: کدگذاری‌هایی که برای CSV امتحان می‌شوند، به ترتیب اولویت. ``utf-8-sig``
#: خروجی اکسل است و ``cp1256`` کدگذاری رایج فایل‌های فارسی ویندوزی.
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1256")
#: جداکننده‌های محتمل CSV؛ تشخیص خودکار با موتور خود pandas.
CSV_SEPARATORS = (None, ",", ";", "\t", "|")

# ------------------------------------------------------------------ سقف ذخیره‌سازی
#: عمر هر بستهٔ پردازش روی دیسک (ثانیه). پاک‌سازی خودکار از پر شدن دیسک
#: سرویس رایگان جلوگیری می‌کند.
STORE_TTL_SECONDS = 6 * 60 * 60
#: سقف تعداد بسته‌های نگه‌داشته‌شده؛ قدیمی‌ترین‌ها پیش از رسیدن به سقف پاک می‌شوند.
STORE_MAX_BUNDLES = 40

# ------------------------------------------------------------------ تشخیص نوع
#: نسبتی از مقادیر غیرخالی که باید با یک نوع بخوانند تا آن نوع پذیرفته شود.
TYPE_PASS_RATIO = 0.85
#: ستونی که بیش از این نسبت مقدار یکتا دارد شناسه شمرده می‌شود، نه متریک.
ID_UNIQUE_RATIO = 0.95
#: کمترین و بیشترین شمار مقدار یکتا برای این‌که ستونی «بعد» (dimension) باشد.
DIMENSION_MIN_UNIQUE = 2
DIMENSION_MAX_UNIQUE = 60
#: بالای این تعداد یکتا، ستون هنوز بعد است ولی به‌عنوان «پرتعداد» علامت می‌خورد.
DIMENSION_BUSY_UNIQUE = 200
#: کمترین شمار ردیف برای این‌که تحلیل روند معنا داشته باشد.
TREND_MIN_POINTS = 3

#: نشانه‌های نام برای حدس نقش ستون‌ها. همه با حروف کوچک مقایسه می‌شوند.
DATE_HINTS = ("date", "time", "month", "year", "day", "period", "timestamp",
              "تاریخ", "زمان", "ماه", "سال", "روز", "دوره", "فصل")
METRIC_HINTS = ("revenue", "sales", "amount", "total", "price", "cost", "profit",
                "margin", "quantity", "qty", "count", "units", "score", "value",
                "weight", "duration", "فروش", "درآمد", "مبلغ", "قیمت", "هزینه",
                "سود", "تعداد", "مقدار", "امتیاز", "وزن", "مدت", "جمع")
ID_HINTS = ("id", "code", "sku", "key", "uuid", "شناسه", "کد")
REGION_HINTS = ("region", "city", "province", "country", "state", "area",
                "منطقه", "شهر", "استان", "کشور", "ناحیه")
PRODUCT_HINTS = ("product", "item", "goods", "service", "category", "brand",
                 "محصول", "کالا", "دسته", "برند", "خدمت")
CUSTOMER_HINTS = ("customer", "client", "user", "buyer", "segment",
                  "مشتری", "کاربر", "خریدار", "مشتریان")
#: نشانه‌های واحد پول و مقدار که هنگام تبدیل سلول حذف می‌شوند.
CURRENCY_SUFFIXES = ("ریال", "تومان", "درهم", "دلار", "یورو", "rls", "toman",
                     "irr", "$", "€", "£")
#: نشانه‌های عددی که در متن سلول معنا دارند و باید پاک شوند.
UNIT_SUFFIXES = ("تعداد", "عدد", "کیلوگرم", "کیلو", "گرم", "تن", "متر", "لیتر",
                 "درصد", "٪", "%", "kg", "km", "m2", "m³")

# ------------------------------------------------------------------ امتیاز کیفیت
#: وزن چهار زیرامتیاز. جمعشان باید ۱ باشد و در رابط و README هم اعلام می‌شود.
QUALITY_WEIGHTS = {
    "completeness": 0.35,
    "validity": 0.25,
    "uniqueness": 0.20,
    "consistency": 0.20,
}
#: متن روش کار — یک منبع حقیقت تا رابط، PDF و README یک چیز بگویند.
QUALITY_METHOD = (
    "امتیاز کیفیت از چهار زیرامتیاز ساخته می‌شود: کامل‌بودن (وزن ۳۵٪) نسبت "
    "سلول‌های پرشده به کل سلول‌ها، اعتبار (۲۵٪) نسبت سلول‌هایی که با نوع تشخیص‌داده‌شدهٔ "
    "ستون می‌خوانند، یکتایی (۲۰٪) نسبت ردیف‌های غیرتکراری، و یکدستی (۲۰٪) نسبت "
    "ستون‌هایی که همهٔ مقادیرشان با یک قالب نمایش داده شده‌اند."
)
#: آستانه‌های برچسب‌گذاری امتیاز.
QUALITY_BANDS = ((85, "عالی"), (70, "خوب"), (50, "قابل قبول"), (0, "ضعیف"))

# ------------------------------------------------------------------ تم گزارش
#: سه تم گزارش. هر تم یک پالت کامل است تا رنگ در همهٔ خروجی‌ها — PDF، اکسل،
#: نمودارها و رابط — یکسان بماند.
THEMES = {
    "corporate": {
        "label": "شرکتی",
        "description": "سبز سازمانی، مناسب گزارش‌های داخلی و مدیریتی.",
        "primary": "#0e7c66",
        "primary_dark": "#0a5c4c",
        "accent": "#14b8a6",
        "ink": "#17233b",
        "muted": "#5b6b80",
        "line": "#dfe6ee",
        "soft": "#f0f9f7",
        "series": ["#0e7c66", "#14b8a6", "#6366f1", "#f59e0b", "#ef4444",
                   "#0ea5e9", "#8b5cf6", "#84cc16", "#ec4899", "#64748b"],
    },
    "executive": {
        "label": "اجرایی",
        "description": "سرمه‌ای و طلایی، مناسب ارائه به مدیران و هیئت‌مدیره.",
        "primary": "#1b2a4a",
        "primary_dark": "#111c33",
        "accent": "#b8924e",
        "ink": "#141b28",
        "muted": "#5d6a7d",
        "line": "#e0e4ec",
        "soft": "#f6f7fa",
        "series": ["#1b2a4a", "#b8924e", "#4c6ef5", "#9c7b3a", "#c94f4f",
                   "#2f8f9d", "#7a5ea8", "#5c8a3c", "#a8527a", "#67748a"],
    },
    "minimal": {
        "label": "مینیمال",
        "description": "خاکستری و کم‌رنگ، مناسب گزارش‌های فنی و پیوست‌ها.",
        "primary": "#2f3745",
        "primary_dark": "#1d232d",
        "accent": "#7c8798",
        "ink": "#1d232d",
        "muted": "#66717f",
        "line": "#e5e7eb",
        "soft": "#f7f8f9",
        "series": ["#2f3745", "#7c8798", "#b0b7c3", "#5c6675", "#98a1ad",
                   "#454e5c", "#c8cdd6", "#6d7787", "#8f98a5", "#aab1bb"],
    },
}
DEFAULT_THEME = "corporate"

#: ستون‌های خروجی اکسل تمیز — نام‌های فارسی در شیت «داده پاک‌شده» دست‌نخورده
#: می‌مانند؛ این‌ها فقط نام شیت‌ها هستند.
SHEET_SUMMARY = "خلاصه"
SHEET_DATA = "داده پاک‌شده"
SHEET_QUALITY = "کیفیت داده"
SHEET_COLUMNS = "پروفایل ستون‌ها"
SHEET_ISSUES = "مسائل و اصلاحات"

#: نام فایل‌های خروجی.
OUTPUT_BASENAMES = {
    "excel": "گزارش-داده",
    "pdf": "گزارش-تحلیلی",
}


def theme(name: str | None) -> dict:
    """پالت یک تم؛ نام ناشناس به تم پیش‌فرض برمی‌گردد."""
    return THEMES.get((name or "").lower().strip(), THEMES[DEFAULT_THEME])


def theme_names() -> list[str]:
    return list(THEMES)


def font_path(bold: bool = False) -> str:
    name = "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"
    return os.path.join(FONTS_DIR, name)


def extension_of(filename: str) -> str:
    """پسوند فایل با حروف کوچک، بدون نقطه. فایل بدون پسوند رشتهٔ خالی می‌دهد."""
    base = os.path.basename(filename or "")
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[1].lower().strip()
