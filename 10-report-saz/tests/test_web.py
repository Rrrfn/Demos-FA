# -*- coding: utf-8 -*-
"""صفحه‌های وب — گردش کامل از بارگذاری تا گزارش، و صفحه‌های خطا."""
from __future__ import annotations

import io
import re

import pytest

#: هر عدد لاتین در متن فارسی یک نقص نمایش است — به جز جایی که خودِ مقدار
#: فنی است. نام کدگذاری، پسوند فایل و شناسهٔ هگز نویسهٔ لاتین دارند و
#: تبدیل‌شان به رقم فارسی غلط می‌بود.
LATIN_DIGITS = re.compile(r"[0-9]")
TECHNICAL_TOKENS = re.compile(
    r"UTF-8|UTF-16|CP1256|BOM|XLSX|CSV|\b[0-9a-f]{12}\b", re.I)


def latin_digits_in_persian_prose(markup: str) -> list[str]:
    """عدد لاتین در متن فارسی — پس از کنار گذاشتن نشانه‌های فنی."""
    text = _visible_text(markup)
    text = TECHNICAL_TOKENS.sub(" ", text)
    return LATIN_DIGITS.findall(text)


def _text(response) -> str:
    return response.data.decode("utf-8")


def _visible_text(markup: str) -> str:
    """متن قابل مشاهده — بدون تگ، اسکریپت، استایل و نشانی‌ها."""
    body = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", markup,
                  flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"&[a-zA-Z#0-9]+;", " ", body)
    return re.sub(r"\s+", " ", body)


# ------------------------------------------------------------------ صفحه‌ها
def test_landing_describes_the_product(client):
    response = client.get("/")
    assert response.status_code == 200
    body = _text(response)
    assert "گزارش" in body
    assert "upload" in body
    #: صفحهٔ خانه باید گردش کار و ضمانت‌ها را نشان بدهد، نه فقط یک جعبهٔ بارگذاری.
    assert "گردش کار" in body
    assert "پاک‌سازی" in body


def test_landing_links_the_demo_download(client):
    assert 'href="/demo"' in _text(client.get("/"))


def test_methodology_explains_every_claim(client):
    body = _text(client.get("/methodology"))
    for phrase in ("امتیاز کیفیت", "IQR", "Z-score", "محدودیت",
                   "امنیت ورودی"):
        assert phrase in body, phrase


def test_static_assets_are_served(client):
    for path in ("/static/css/app.css", "/static/js/app.js",
                 "/static/img/favicon.svg",
                 "/static/fonts/Vazirmatn-Regular.woff2"):
        assert client.get(path).status_code == 200, path


# ------------------------------------------------------------------ گردش کار
def test_upload_redirects_to_inspection(client, xlsx_file):
    response = client.post("/upload",
                           data={"file": (io.BytesIO(xlsx_file), "d.xlsx")},
                           content_type="multipart/form-data")
    assert response.status_code == 302
    assert "/inspect" in response.headers["Location"]


def test_inspection_page_shows_profile_and_quality(client, bundle_id):
    body = _text(client.get(f"/dataset/{bundle_id}/inspect"))
    assert "بازرسی داده" in body
    assert "امتیاز کیفیت" in body
    assert "پروفایل ستون‌ها" in body
    assert "پیش‌نمایش" in body


def test_cleaning_page_shows_findings_and_options(client, bundle_id):
    body = _text(client.get(f"/dataset/{bundle_id}/clean"))
    assert "پاک‌سازی داده" in body
    assert "مسائل پیداشده" in body
    assert "اجرای پاک‌سازی" in body


def test_applying_cleaning_records_fixes(client, bundle_id):
    response = client.post(
        f"/dataset/{bundle_id}/clean",
        data={"drop_duplicates": "on", "drop_empty_rows": "on",
              "drop_empty_columns": "on", "trim_text": "on",
              "numeric_as_text": "on", "parse_dates": "on",
              "normalize_nulls": "on"})
    assert response.status_code == 302
    body = _text(client.get(f"/dataset/{bundle_id}/clean"))
    assert "اصلاحات اعمال‌شده" in body
    assert "سطر پس از پاک‌سازی" in body


def test_cleaning_can_be_reapplied_with_other_options(client, bundle_id):
    """دادهٔ خام باید بماند تا گزینه‌ها قابل تغییر باشند."""
    first = client.post(f"/dataset/{bundle_id}/clean",
                        data={"drop_duplicates": "on"}).status_code
    second = client.post(f"/dataset/{bundle_id}/clean", data={}).status_code
    assert first == 302 and second == 302
    profile = client.get(f"/api/profile/{bundle_id}").get_json()["data"]
    assert profile["rows"] > 0


def test_dashboard_shows_kpis_insights_and_charts(client, bundle_id):
    body = _text(client.get(f"/dataset/{bundle_id}/dashboard"))
    assert "شاخص‌های کلیدی" in body
    assert "بینش‌های کلیدی" in body
    assert "نمودارها" in body
    assert body.count("<svg") >= 1


def test_dashboard_reports_truthfully_when_there_is_no_metric(client,
                                                              text_only_frame):
    from tests.conftest import xlsx_bytes

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(xlsx_bytes(text_only_frame)), "text.xlsx")},
        content_type="multipart/form-data")
    dataset_id = response.headers["Location"].split("/")[-2]
    body = _text(client.get(f"/dataset/{dataset_id}/dashboard"))
    assert "شاخص‌های کلیدی" in body
    #: نباید کارت شاخص جعلی داشته باشد ولی باید دلیلش را بگوید.
    assert "متریک" in body or "شاخصی ساخته نشد" in body


def test_report_page_renders_sections_and_charts(client, bundle_id):
    body = _text(client.get(f"/dataset/{bundle_id}/report"))
    for title in ("خلاصهٔ مدیریتی", "کیفیت داده", "شاخص‌های کلیدی",
                  "نمودارها", "بینش‌های کلیدی", "تحلیل تفصیلی",
                  "پیوست"):
        assert title in body, title


def test_report_preview_and_pdf_share_the_same_structure(client, bundle_id):
    """پیش‌نمایش و PDF از یک مدل ساخته می‌شوند؛ اگر یکی بخشی داشته باشد و
    دیگری نداشته باشد، این آزمون می‌شکند."""
    preview = _text(client.get(f"/dataset/{bundle_id}/report"))
    payload = client.get(f"/dataset/{bundle_id}/export/pdf")
    assert payload.status_code == 200
    assert preview.count("<svg") >= 1


def test_dataset_shortcut_redirects_to_current_stage(client, bundle_id):
    response = client.get(f"/dataset/{bundle_id}")
    assert response.status_code == 302


def test_theme_change_shows_in_the_report(client, bundle_id):
    client.get(f"/dataset/{bundle_id}/dashboard")
    response = client.post(f"/dataset/{bundle_id}/theme",
                           data={"theme": "minimal", "next": "report"})
    assert response.status_code == 302
    body = _text(client.get(f"/dataset/{bundle_id}/report"))
    assert "مینیمال" in body


def test_theme_change_rejects_unknown_name(client, bundle_id):
    response = client.post(f"/dataset/{bundle_id}/theme",
                           data={"theme": "ناشناخته"})
    assert response.status_code == 400


def test_exports_from_the_page(client, bundle_id):
    pdf = client.get(f"/dataset/{bundle_id}/export/pdf")
    excel = client.get(f"/dataset/{bundle_id}/export/excel")
    assert pdf.data[:5] == b"%PDF-"
    assert excel.data[:2] == b"PK"


# ------------------------------------------------------------------ خطا
def test_unknown_page_shows_a_persian_error_page(client):
    response = client.get("/این-صفحه-نیست")
    assert response.status_code == 404
    body = _text(response)
    assert "پیدا نشد" in body or "وجود ندارد" in body
    #: صفحهٔ خطا باید مسیر بازگشت بدهد، نه این‌که کاربر گیر کند.
    assert "بازگشت به صفحهٔ اصلی" in body


def test_user_error_page_explains_the_problem(client):
    response = client.post("/upload", data={},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    body = _text(response)
    assert "فایل" in body
    assert "Internal Server Error" not in body


def test_legacy_format_error_page_offers_a_fix(client):
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 40),
                       "old.xls")},
        content_type="multipart/form-data")
    assert response.status_code == 400
    body = _text(response)
    assert "xlsx" in body.lower()


def test_expired_dataset_shows_a_friendly_error(client):
    response = client.get("/dataset/abcdef123456/inspect")
    assert response.status_code == 404
    assert "Internal Server Error" not in _text(response)


# ------------------------------------------------------------------ نمایش
@pytest.mark.parametrize("path", ["/", "/methodology"])
def test_public_pages_have_no_latin_digits(client, path):
    """رقم لاتین در متن فارسی خواندن را بد می‌کند؛ تبدیل در فیلترها است."""
    found = latin_digits_in_persian_prose(_text(client.get(path)))
    assert not found, f"{path}: {found[:10]}"


def test_dashboard_has_no_latin_digits(client, bundle_id):
    found = latin_digits_in_persian_prose(
        _text(client.get(f"/dataset/{bundle_id}/dashboard")))
    assert not found, f"dashboard: {found[:10]}"


def test_report_has_no_latin_digits(client, bundle_id):
    found = latin_digits_in_persian_prose(
        _text(client.get(f"/dataset/{bundle_id}/report")))
    assert not found, f"report: {found[:10]}"


def test_inspection_and_cleaning_have_no_latin_digits(client, bundle_id):
    for path in (f"/dataset/{bundle_id}/inspect",
                 f"/dataset/{bundle_id}/clean"):
        found = latin_digits_in_persian_prose(_text(client.get(path)))
        assert not found, f"{path}: {found[:10]}"


def test_insight_evidence_is_formatted_for_persian(client, bundle_id):
    """شاهد عددی نباید مقدار خام پایتونی نشان بدهد."""
    body = _text(client.get(f"/dataset/{bundle_id}/dashboard"))
    assert "0." not in _visible_text(body).replace("۰٫", "")
    assert "share :" not in body


def test_pages_declare_rtl_and_persian(client):
    body = _text(client.get("/"))
    assert 'dir="rtl"' in body
    assert 'lang="fa"' in body


def test_layout_is_responsive(client):
    """صفحه باید برای موبایل تعریف شده باشد، وگرنه روی گوشی بی‌استفاده است."""
    css = _text(client.get("/static/css/app.css"))
    assert "@media" in css
    assert "max-width: 760px" in css
