# -*- coding: utf-8 -*-
"""ابزارهای مشترک آزمون.

سه اصل در این فایل رعایت شده است:

۱) **هر آزمون دادهٔ خودش را می‌سازد.** هیچ آزمونی به فایل روی دیسک یا به
   ترتیب اجرای دیگری وابسته نیست؛ هر آزمون از هر ترتیبی سبز می‌شود.

۲) **بستهٔ پردازش در پوشهٔ موقت.** آزمون‌ها نباید دادهٔ واقعی سرویس را عوض
   کنند یا به آن نگاه کنند. یک پوشهٔ موقت برای کل نشست کافی است.

۳) **سازنده‌های واقع‌گرا.** دادهٔ آزمون مثل دادهٔ واقعی است — تاریخ شمسی،
   مبلغ متنی، سلول خالی، ردیف تکراری. آزمونی که فقط با دادهٔ تمیز کار کند،
   همان جایی می‌شکند که کاربر می‌شکند.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REGIONS = ["تهران", "شیراز", "مشهد", "اصفهان", "تبریز"]
PRODUCTS = ["لپ‌تاپ", "موبایل", "تبلت", "هدفون"]


# ------------------------------------------------------------------ داده
def sales_rows(rows: int = 120, seed: int = 11, *, issues: bool = True) -> list[dict]:
    """سطرهای فروش ساختگی — با عیب‌های اختیاری مثل دادهٔ واقعی."""
    import random

    generator = random.Random(seed)
    output: list[dict] = []
    for index in range(rows):
        month = generator.randint(1, 12)
        day = generator.randint(1, 28)
        product = generator.choice(PRODUCTS)
        quantity = generator.randint(1, 20)
        price = generator.randint(900_000, 48_000_000)
        record = {
            "تاریخ": f"1403/{month:02d}/{day:02d}",
            "منطقه": generator.choice(REGIONS),
            "محصول": product,
            "مبلغ فروش": f"{price:,}",
            "تعداد": quantity,
            "کد سفارش": f"SO-{index:05d}",
        }
        if issues:
            if index % 31 == 0:
                record["مبلغ فروش"] = f"{price:,} ریال"
            if index % 47 == 0:
                record["منطقه"] = ""
        output.append(record)
    if issues and len(output) > 3:
        output.append(dict(output[0]))
        output.append(dict(output[1]))
    return output


@pytest.fixture
def frame() -> pd.DataFrame:
    """جدول فروش با نوع‌های طبیعی پایتون (بدون عیب)."""
    return pd.DataFrame(sales_rows(140, issues=False))


@pytest.fixture
def messy_frame() -> pd.DataFrame:
    """جدول با عیب‌های عمدی: تکراری، خالی، متن عددی، تاریخ متنی."""
    return pd.DataFrame(sales_rows(140, issues=True))


@pytest.fixture
def wide_frame() -> pd.DataFrame:
    """جدول بدون ستون تاریخ — برای سنجش صداقت در نبود داده."""
    rows = [{"منطقه": r["منطقه"], "محصول": r["محصول"],
             "مبلغ فروش": r["مبلغ فروش"], "تعداد": r["تعداد"]}
            for r in sales_rows(60, issues=False)]
    return pd.DataFrame(rows)


@pytest.fixture
def tiny_frame() -> pd.DataFrame:
    """جدول کوچک‌تر از حد لازم برای تحلیل روند."""
    return pd.DataFrame([{"منطقه": "تهران", "مبلغ": "100"},
                         {"منطقه": "شیراز", "مبلغ": "200"}])


@pytest.fixture
def text_only_frame() -> pd.DataFrame:
    """جدول بدون هیچ ستون عددی — برای سنجش رفتار در نبود متریک."""
    return pd.DataFrame({
        "توضیح": ["الف", "ب", "ج", "د"],
        "وضعیت": ["بسته", "باز", "بسته", "باز"],
    })


# ------------------------------------------------------------------ فایل
def xlsx_bytes(frame: pd.DataFrame, sheet: str = "داده") -> bytes:
    """ساخت فایل XLSX در حافظه از یک جدول."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=sheet)
    return buffer.getvalue()


def csv_bytes(frame: pd.DataFrame, encoding: str = "utf-8",
              separator: str = ",") -> bytes:
    """ساخت فایل CSV در حافظه با کدگذاری و جداکنندهٔ دلخواه."""
    return frame.to_csv(index=False, sep=separator).encode(encoding)


@pytest.fixture
def xlsx_file(frame) -> bytes:
    return xlsx_bytes(frame)


@pytest.fixture
def csv_file(frame) -> bytes:
    return csv_bytes(frame)


@pytest.fixture
def titled_xlsx() -> bytes:
    """فایل با چند سطر عنوان پیش از سرصفحه — حالت رایج فایل‌های اداری."""
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet["A1"] = "گزارش فروش دورهٔ اول"
    sheet["A2"] = "تهیه‌شده توسط واحد فروش"
    sheet["A3"] = "تاریخ گزارش: ۱۴۰۳/۰۵/۱۲"
    headers = ["منطقه", "محصول", "مبلغ", "تعداد"]
    for index, name in enumerate(headers, start=1):
        sheet.cell(row=4, column=index, value=name)
    for offset in range(1, 21):
        sheet.cell(row=4 + offset, column=1, value=REGIONS[offset % 5])
        sheet.cell(row=4 + offset, column=2, value=PRODUCTS[offset % 4])
        sheet.cell(row=4 + offset, column=3, value=1000 * offset)
        sheet.cell(row=4 + offset, column=4, value=offset)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ برنامه
@pytest.fixture(scope="session")
def workspace():
    """پوشهٔ موقت داده — یک بار برای کل نشست، و پاک‌سازی در پایان."""
    #: در ویندوز فایل‌های باز شده ممکن است لحظهٔ پاک‌سازی هنوز قفل باشند؛
    #: خطای پاک‌سازی نباید نتیجهٔ آزمون‌ها را عوض کند.
    with tempfile.TemporaryDirectory(prefix="reportsaz-tests-",
                                     ignore_cleanup_errors=True) as directory:
        yield directory


@pytest.fixture
def app(workspace, monkeypatch):
    """برنامهٔ آزمون با پوشهٔ دادهٔ موقت.

    مسیرهای ذخیره‌سازی پیش از import شدن ماژول‌ها عوض می‌شوند تا هیچ آزمونی
    روی دادهٔ واقعی سرویس ننویسد.
    """
    import reportsaz.config as config

    store = os.path.join(workspace, "store")
    uploads = os.path.join(workspace, "uploads")
    outputs = os.path.join(workspace, "outputs")
    for path in (store, uploads, outputs):
        os.makedirs(path, exist_ok=True)
    monkeypatch.setattr(config, "STORE_DIR", store, raising=True)
    monkeypatch.setattr(config, "UPLOAD_DIR", uploads, raising=True)
    monkeypatch.setattr(config, "OUTPUT_DIR", outputs, raising=True)

    import reportsaz.store as store_module

    monkeypatch.setattr(store_module, "STORE_DIR", store, raising=True)

    from reportsaz.web import create_app

    application = create_app(testing=True)
    #: پاک‌سازی بسته‌های آزمون پیش از هر آزمون، تا سقف بسته‌ها پر نشود.
    store_module.sweep(force=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def upload(client, xlsx_file):
    """بارگذاری یک فایل و برگرداندن شناسهٔ بسته."""

    def _upload(payload: bytes | None = None, name: str = "data.xlsx",
                content_type: str = "application/vnd.openxmlformats-"
                                    "officedocument.spreadsheetml.sheet"):
        response = client.post(
            "/api/upload",
            data={"file": (io.BytesIO(payload if payload is not None else xlsx_file),
                           name)},
            content_type="multipart/form-data")
        assert response.status_code in (200, 201), response.data[:400]
        return response.get_json()["data"]["dataset_id"]

    return _upload


@pytest.fixture
def bundle_id(upload) -> str:
    """بسته‌ای که بازرسی روی آن انجام شده است."""
    return upload()
