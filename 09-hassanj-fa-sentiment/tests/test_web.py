# -*- coding: utf-8 -*-
"""آزمون صفحه‌ها — رندر، ناوبری، یکدستی رقم‌ها و صفحه‌های خطا.

قاعدهٔ رقم: هر عددی که کاربر *می‌خواند* باید فارسی باشد. بررسی روی متنِ
HTML انجام می‌شود، نه روی کل بدنه؛ چون مختصات و ویژگی‌های SVG عمداً لاتین‌اند
و ربطی به متن خواندنی ندارند.
"""
from __future__ import annotations

import io
import re

import pytest

PAGES = ("/", "/analyze", "/batch", "/analytics", "/model", "/methodology")

LATIN_DIGIT = re.compile(r"[0-9]")
SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
#: بخش‌های تزریق‌شدهٔ عمدی: نام مدل‌ها و کدهای API که لاتین‌اند و باید بمانند.
ALLOWED_LATIN = re.compile(r"(LinearSVM|LogisticRegression|MultinomialNB|"
                           r"calibrated|hassanj|api|health|metrics|MIX_BY_MONTH|"
                           r"TYPOS|python|utf|html|text|comment|review|MIX|F1)")


def visible_text(html: str) -> str:
    """متن خواندنی صفحه — بدون اسکریپت، سبک و ویژگی‌های تگ‌ها."""
    cleaned = SCRIPT_OR_STYLE.sub(" ", html)
    return TAGS.sub(" ", cleaned)


# ---------------------------------------------------------------------- صفحه‌ها
@pytest.mark.parametrize("path", PAGES)
def test_every_page_renders(client, path):
    response = client.get(path)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "<!doctype html>" in body
    assert 'dir="rtl"' in body and 'lang="fa"' in body


@pytest.mark.parametrize("path", PAGES)
def test_every_page_has_navigation_and_footer(client, path):
    body = client.get(path).get_data(as_text=True)
    for label in ("نمای کلی", "تحلیل متن", "تحلیل گروهی", "مدل", "متدولوژی"):
        assert label in body, (path, label)
    assert "دیتاست سینتتیک" in body


@pytest.mark.parametrize("path,slug", zip(PAGES, ("نمای کلی", "تحلیل متن",
                                                  "تحلیل گروهی", "تحلیل", "مدل",
                                                  "متدولوژی")))
def test_current_page_is_marked_in_navigation(client, path, slug):
    body = client.get(path).get_data(as_text=True)
    assert re.search(r'aria-current="page">' + re.escape(slug) + "<", body)


@pytest.mark.parametrize("path", PAGES)
def test_no_latin_digits_in_readable_text(client, path):
    """رگرسیون: برچسب ماه هفتم رقم لاتین به رابط می‌ریخت."""
    text = visible_text(client.get(path).get_data(as_text=True))
    leaks = []
    for match in LATIN_DIGIT.finditer(text):
        window = text[max(0, match.start() - 24): match.end() + 24]
        if not ALLOWED_LATIN.search(window):
            leaks.append(window.strip())
    assert leaks == [], (path, leaks[:4])


@pytest.mark.parametrize("path", PAGES)
def test_no_console_breaking_markup(client, path):
    """تگ‌های باز بدون بسته‌شدن، نشانهٔ قالب نیمه‌کاره است."""
    body = client.get(path).get_data(as_text=True)
    for tag in ("section", "figure", "table", "details"):
        assert body.count(f"<{tag}") == body.count(f"</{tag}>"), tag


def test_static_assets_are_served_with_content_version(client):
    body = client.get("/").get_data(as_text=True)
    assert re.search(r'/static/css/app\.css\?v=[0-9a-f]{8}', body)
    assert re.search(r'/static/js/app\.js\?v=[0-9a-f]{8}', body)
    assert client.get("/static/css/app.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/favicon.svg").status_code == 200


# ------------------------------------------------------------------ صفحهٔ تحلیل متن
def test_analyze_without_query_shows_no_result(client):
    body = client.get("/analyze").get_data(as_text=True)
    assert 'id="result-region"' in body
    assert 'class="verdict"' not in body


def test_analyze_renders_verdict_and_signals(client):
    body = client.get("/analyze?q=کیفیت عالی بود و ارسال سریع").get_data(as_text=True)
    assert 'class="verdict"' in body
    assert "مثبت" in body
    assert 'class="meter-row"' in body
    assert "٪" in body


def test_analyze_explains_out_of_domain_input(client):
    body = client.get(
        "/analyze?q=The+delivery+took+longer+than+expected").get_data(as_text=True)
    assert "سیگنال ناکافی" in body
    assert "واژگان مدل نیست" in body


def test_analyze_offers_examples(client):
    body = client.get("/analyze").get_data(as_text=True)
    assert body.count('class="chip"') >= 5


def test_analyze_echoes_the_submitted_text(client):
    body = client.get("/analyze?q=بسته+رسید").get_data(as_text=True)
    assert "بسته رسید" in body


def test_analyze_truncates_and_says_so(client):
    payload = "خوب بود " * 2000
    body = client.get("/analyze", query_string={"q": payload}).get_data(as_text=True)
    assert len(payload) > 4000
    assert 'maxlength="4000"' in body


def test_analyze_handles_symbol_only_query(client):
    body = client.get("/analyze", query_string={"q": "!!! ..."}).get_data(as_text=True)
    assert "سیگنال ناکافی" in body


def test_analyze_page_has_live_region_for_progressive_enhancement(client):
    """بدون JavaScript هم کار می‌کند؛ با آن، جای نتیجه بدون رفرش عوض می‌شود."""
    body = client.get("/analyze?q=خوب بود").get_data(as_text=True)
    assert 'aria-live="polite"' in body
    assert 'class="analyze-form"' in body
    assert 'id="char-counter"' in body


# ------------------------------------------------------------------ صفحهٔ گروهی
def test_batch_get_shows_upload_form(client):
    body = client.get("/batch").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in body
    assert 'type="file"' in body


def test_batch_post_without_file_is_a_400(client):
    response = client.post("/batch", data={})
    assert response.status_code == 400
    assert "فایلی انتخاب نشده است" in response.get_data(as_text=True)


def test_batch_post_renders_summary_and_rows(client):
    payload = ("text\n"
               "کیفیت عالی بود و ارسال سریع\n"
               "خراب رسید و پشتیبانی جواب نداد\n"
               "بسته رسید باید تست کنم\n").encode("utf-8")
    response = client.post("/batch",
                           data={"file": (io.BytesIO(payload), "comments.csv")},
                           content_type="multipart/form-data")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ردیف‌های فایل" in body
    assert "سهم هر برچسب" in body
    assert 'class="state' in body


def test_batch_post_with_broken_file_is_a_400(client):
    response = client.post("/batch",
                           data={"file": (io.BytesIO(b""), "empty.csv")},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert "فایل پردازش نشد" in response.get_data(as_text=True)


def test_batch_download_returns_a_csv_attachment(client):
    payload = "text\nکیفیت عالی بود\n".encode("utf-8")
    response = client.post("/batch",
                           data={"file": (io.BytesIO(payload), "comments.csv"),
                                 "action": "download"},
                           content_type="multipart/form-data")
    assert response.status_code == 200
    assert "text/csv" in response.headers["Content-Type"]
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"\xef\xbb\xbf")


def test_download_header_is_ascii_safe(client):
    """رگرسیون: نام فایل فارسی خام در سرآمد، پاسخ را روی سرور واقعی می‌شکند.

    سرآمدهای HTTP فقط لاتین-۱ می‌پذیرند؛ نام فارسی باید درصدگذاری‌شده باشد
    وگرنه سرور واقعی — نه آزمون‌کارخواه — با UnicodeEncodeError می‌افتد.
    """
    payload = "text\nکیفیت عالی بود\n".encode("utf-8")
    response = client.post("/batch",
                           data={"file": (io.BytesIO(payload), "comments.csv"),
                                 "action": "download"},
                           content_type="multipart/form-data")
    disposition = response.headers["Content-Disposition"]
    disposition.encode("latin-1")                     # بدون درصدگذاری می‌شکند
    assert "filename*=UTF-8''" in disposition
    assert "%" in disposition
    for _, value in response.headers:
        value.encode("latin-1")                       # همهٔ سرآمدها باید امن باشند


# ------------------------------------------------------------------ صفحه‌های خطا
def test_unknown_page_renders_the_persian_404(client):
    response = client.get("/چنین-صفحه‌ای-نیست")
    assert response.status_code == 404
    body = response.get_data(as_text=True)
    assert "این صفحه پیدا نشد" in body
    assert "۴۰۴" in body


def test_oversized_upload_renders_the_persian_413(client):
    big = io.BytesIO(b"x" * (9 * 1024 * 1024))
    response = client.post("/batch",
                           data={"file": (big, "big.csv")},
                           content_type="multipart/form-data")
    assert response.status_code == 413
    assert "بزرگ‌تر از حد مجاز" in response.get_data(as_text=True)


def test_error_pages_keep_the_site_shell(client):
    body = client.get("/missing").get_data(as_text=True)
    assert "حس‌سنج" in body and "دیتاست سینتتیک" in body
