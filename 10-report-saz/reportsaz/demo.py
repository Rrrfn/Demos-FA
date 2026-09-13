# -*- coding: utf-8 -*-
"""مجموعهٔ دادهٔ نمونه — تا کارفرما بی‌درنگ بتواند محصول را امتحان کند.

داده **ساختگی** است و این در سه جا صریح گفته می‌شود: نام فایل، ستون «نوع
داده» در خود کارپوشه، و توضیحی که کنار دکمهٔ دانلود می‌آید. دلیلش ساده است:
دادهٔ ساختگی که با داده واقعی اشتباه گرفته شود، بدتر از نبود داده است.

چند عیب واقعی هم عمداً در داده کاشته شده — ردیف تکراری، سلول خالی،
«۱٬۲۰۰٬۰۰۰» به‌جای عدد، و تاریخ شمسی. بدون آن‌ها صفحه‌های بازرسی و پاک‌سازی
خالی می‌مانند و کاربر نمی‌بیند محصول چه کاری انجام می‌دهد.
"""
from __future__ import annotations

import io
import random

#: نام‌های ساختگی — ترکیبی که به یک کسب‌وکار واقعی اشاره نمی‌کند.
REGIONS = ["تهران", "شیراز", "مشهد", "اصفهان", "تبریز", "کرج"]
PRODUCTS = ["لپ‌تاپ", "موبایل", "تبلت", "هدفون", "مانیتور", "کیبورد"]
CHANNELS = ["فروشگاه", "آنلاین", "نمایندگی", "تلفنی"]
SEGMENTS = ["خرد", "متوسط", "سازمانی"]
SALES_REPS = ["کارشناس الف", "کارشناس ب", "کارشناس ج", "کارشناس د"]

#: تعداد سطرهای نمونه — کوچک نگه داشته می‌شود تا بارگذاری در سرور رایگان سریع باشد.
DEMO_ROWS = 420

#: شیب رشد فصلی: ضریب قیمت از ابتدای سال تا انتهای آن این‌قدر بالا می‌رود.
#: عمداً از پراکندگی طبیعی سطرها بزرگ‌تر است؛ وگرنه نوسان تصادفی روی «رشد دو
#: نیمه» غالب می‌شود و گزارش چیزی می‌گوید که در نمودار دیده نمی‌شود.
SEASONAL_GROWTH = 0.35

#: ضریب چند برابر شدن یک سطر برای ساخت «مقدار پرت» عمدی. بزرگ انتخاب نشده:
#: پرتی که چند برابر بقیه باشد، جمع کل را جابه‌جا می‌کند و روند واقعی داده را
#: زیر خودش می‌پوشاند. با ۴ برابر، مقدار هم‌چنان بیرون از بازهٔ IQR می‌افتد و
#: ناهنجاری شناسایی می‌شود، ولی تصویر کلی داده را عوض نمی‌کند.
OUTLIER_FACTOR = 4

#: ماه‌هایی که یک مقدار پرت در آن کاشته می‌شود — یکی در نیمهٔ اول سال و یکی
#: در نیمهٔ دوم. اگر پرت‌ها در یک نیمه جمع شوند، مقایسهٔ دو نیمه به‌جای داده، به
#: همان چند سطر جواب می‌دهد.
OUTLIER_MONTHS = (2, 11)

#: قیمت پایهٔ ساختگی هر محصول (ریال).
BASE_UNIT_PRICE = {
    "لپ‌تاپ": 42_000_000,
    "موبایل": 18_000_000,
    "تبلت": 12_500_000,
    "هدفون": 2_400_000,
    "مانیتور": 9_800_000,
    "کیبورد": 1_250_000,
}


def demo_description() -> dict:
    """توضیح کوتاه نمونه برای نمایش در صفحهٔ خانه."""
    return {
        "rows": DEMO_ROWS,
        "columns": 10,
        "filename": "sample-sales.xlsx",
        "note": "داده ساختگی و برای نمایش است؛ هیچ نسبت واقعی با بازار ندارد.",
        "issues": [
            "ردیف‌های تکراری برای نمایش بخش پاک‌سازی",
            "سلول‌های خالی در ستون مشتری",
            "مبلغ‌های ذخیره‌شده به‌صورت متن با واحد ریال",
            "تاریخ‌های شمسی با ارقام فارسی",
            "چند مقدار پرت برای نمایش تشخیص ناهنجاری",
        ],
    }


def build_demo_rows(rows: int = DEMO_ROWS, seed: int = 20260913) -> list[dict]:
    """ساخت سطرهای نمونه — با همان عیب‌های عمدی.

    بذر تصادفی ثابت است تا هر بار همان داده ساخته شود؛ نمونه‌ای که هر بار
    عوض شود، برای آزمون و برای نمایش یکسان بی‌فایده است.
    """
    random.seed(seed)
    output: list[dict] = []
    for index in range(rows):
        #: ماه‌ها به‌ترتیب چرخانده می‌شوند تا هر ماه سهم برابر داشته باشد.
        #: با انتخاب تصادفی ماه، سهم ردیف‌های دو نیمهٔ سال نابرابر می‌شد و
        #: مقایسهٔ دوره‌ها به‌جای رشد واقعی، همان نابرابری را نشان می‌داد.
        month = (index % 12) + 1
        day = random.randint(1, 28)
        #: محصول‌ها هم به‌ترتیب چرخانده می‌شوند: در هر ماه ترکیب محصول‌ها یکسان
        #: است. با انتخاب تصادفی، یک ماه بیش از دیگری «لپ‌تاپ» می‌گرفت و اختلاف
        #: جمع دو ماه، تفاوت ترکیب محصول می‌شد نه رشد فروش.
        product = PRODUCTS[(index // 12) % len(PRODUCTS)]
        quantity = random.randint(1, 24)
        unit_price = int(BASE_UNIT_PRICE[product] *
                         random.uniform(0.88, 1.18))
        #: رشد ملایم در نیمهٔ دوم سال تا تحلیل روند چیزی برای گفتن داشته باشد.
        seasonal = 1.0 + (month / 12) * SEASONAL_GROWTH
        unit_price = int(unit_price * seasonal)

        record = {
            "تاریخ سفارش": _jalali_text(month, day),
            "کد سفارش": f"ORD-{1400 + index:05d}",
            "منطقه": random.choice(REGIONS),
            "فروشگاه": f"شعبه {random.randint(1, 9)}",
            "محصول": product,
            "دسته": random.choice(CHANNELS),
            "بخش مشتری": random.choice(SEGMENTS),
            "کارشناس فروش": random.choice(SALES_REPS),
            "تعداد": quantity,
            "مبلغ فروش": _money_text(unit_price * quantity),
        }
        #: --- عیب‌های عمدی ------------------------------------------------
        if index % 37 == 0:
            record["بخش مشتری"] = ""                     #: سلول خالی
        if index % 53 == 0:
            record["مبلغ فروش"] = f"{quantity}"          #: عدد به‌صورت متن خالی
        if month in OUTLIER_MONTHS and day == 13:
            record["مبلغ فروش"] = _money_text(unit_price * quantity * OUTLIER_FACTOR,
                                              persian=True)   #: مقدار پرت
        if index % 29 == 0 and output:
            output.append(dict(output[index % max(1, len(output))]))   #: تکراری
        output.append(record)
    return output


def build_demo_workbook(rows: int = DEMO_ROWS) -> bytes:
    """ساخت کارپوشهٔ اکسل نمونه."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    data = build_demo_rows(rows)
    columns = list(data[0].keys())

    book = Workbook()
    sheet = book.active
    sheet.title = "فروش نمونه"
    sheet.sheet_view.rightToLeft = True

    header_fill = PatternFill("solid", fgColor="0E7C66")
    for index, name in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_index, record in enumerate(data, start=2):
        for column_index, name in enumerate(columns, start=1):
            sheet.cell(row=row_index, column=column_index,
                       value=record.get(name, ""))

    sheet.freeze_panes = "A2"
    from openpyxl.utils import get_column_letter

    for index, name in enumerate(columns, start=1):
        longest = max([len(str(name))] +
                      [len(str(record.get(name, ""))) for record in data[:200]])
        sheet.column_dimensions[get_column_letter(index)].width = min(
            34, max(11, longest + 3))

    #: برگهٔ دوم: توضیح صریح ساختگی بودن داده.
    note = book.create_sheet("درباره این داده")
    note.sheet_view.rightToLeft = True
    note.column_dimensions["A"].width = 96
    note["A1"] = "این داده ساختگی است"
    note["A1"].font = Font(bold=True, size=15, color="B45309")
    lines = [
        "این کارپوشه فقط برای نمایش قابلیت‌های گزارش‌ساز ساخته شده است.",
        "هیچ نسبت واقعی با هیچ کسب‌وکار، بازار یا برندی ندارد.",
        "نام محصول‌ها، مناطق و شعبه‌ها ساختگی‌اند و نباید مبنای تصمیم‌گیری شوند.",
        "چند عیب عمدی در داده هست تا مرحله‌های بازرسی و پاک‌سازی معنادار شوند:",
        "  — ردیف‌های تکراری",
        "  — سلول‌های خالی در ستون «بخش مشتری»",
        "  — مبلغ‌هایی که به‌صورت متن با واحد ریال ذخیره شده‌اند",
        "  — تاریخ‌های شمسی با ارقام فارسی",
        "  — چند مقدار پرت",
    ]
    for offset, line in enumerate(lines, start=3):
        note.cell(row=offset, column=1, value=line)

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _jalali_text(month: int, day: int) -> str:
    """تاریخ شمسی با ارقام فارسی — همان شکلی که کاربر ایرانی می‌آورد."""
    persian = "۰۱۲۳۴۵۶۷۸۹"
    value = f"1403/{month:02d}/{day:02d}"
    return value.translate(str.maketrans("0123456789", persian))


def _money_text(amount: int, persian: bool = False) -> str:
    """مبلغ به‌صورت متن با جداکنندهٔ هزارگان و واحد ریال."""
    grouped = f"{amount:,}"
    if persian:
        grouped = grouped.replace(",", "٬").translate(
            str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return f"{grouped} ریال"
