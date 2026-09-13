# -*- coding: utf-8 -*-
"""آزمون صفحه‌ها — هر مسیر باید کامل و بی‌خطا رندر شود.

این آزمون جای بازبینی دستی را می‌گیرد: صفحهٔ خالی، متغیر جاافتاده، قالب‌بندی
ناقص و استثنای زمان رندر همه اینجا لو می‌روند. علاوه بر کد وضعیت، سه چیز
بررسی می‌شود که چشم به‌سختی می‌بیند:

* متن دیده‌شده رقم لاتین نداشته باشد (رابط تمام‌فارسی است).
* هیچ نشانهٔ قالب‌بندی‌نشدهٔ Jinja در خروجی نمانده باشد.
* دارایی‌های ارجاع‌شده (CSS، JS، عکس) واقعاً موجود باشند.
"""
from __future__ import annotations

import re

import pytest

#: مسیر صفحه‌ها و انتظار وضعیت. صفحهٔ ناموجود عمداً اینجاست.
PAGES = (
    ("/", 200),
    ("/search", 200),
    ("/search?districts=1&districts=3&amin=90&bedrooms=2", 200),
    ("/search?pmax=15&parking=1&sort=کم‌ترین قیمت متر", 200),
    ("/search?page=2", 200),
    ("/search?page=9999", 200),
    ("/search?pmin=99&pmax=1", 200),           # بازهٔ وارونه
    ("/search?districts=وهمی&amin=خالی", 200),  # ورودی نامعتبر
    ("/listing/KH-1001", 200),
    ("/compare", 200),
    ("/compare?ids=KH-1001,KH-1002", 200),
    ("/compare?ids=نادرست", 200),
    ("/estimate", 200),
    ("/estimate?f=1&district=1&area=200&bedrooms=3&age=2&floor=8", 200),
    ("/estimate?district=9999&area=99999&floor=999", 200),
    ("/analytics", 200),
    ("/methodology", 200),
    ("/saved", 200),
    ("/robots.txt", 200),
    ("/nope", 404),
    ("/listing/KH-999999", 404),
)

_TAG = re.compile(r"<(script|style)\b.*?</\1>", re.S)
_MARKUP = re.compile(r"<[^>]+>")
#: بخش‌هایی که لاتین بودنشان درست است: کد و نام پدیدآورنده.
_LATIN_OK = re.compile(
    r"<(code|kbd|samp|pre)\b.*?</\1>"
    r"|<[^>]+class=[\"'][^\"']*\blatin\b[^\"']*[\"'][^>]*>.*?</[a-z]+>",
    re.S | re.I,
)
_JINJA = re.compile(r"\{\{|\{%")
_ASSET = re.compile(r"""(?:src|href)\s*=\s*["'](/static/[^"']+)["']""")


def visible_text(html: str) -> str:
    """متن دیده‌شده — بدون برچسب، اسکریپت، ویژگی و بخش لاتین‌مجاز."""
    body = _TAG.sub(" ", html)
    body = _LATIN_OK.sub(" ", body)
    return _MARKUP.sub(" ", body)


@pytest.mark.parametrize("path,status", PAGES, ids=[p for p, _ in PAGES])
def test_page_status(client, path, status):
    assert client.get(path).status_code == status


@pytest.mark.parametrize("path", [path for path, _ in PAGES])
def test_pages_have_no_unrendered_jinja(client, path):
    body = client.get(path).get_data(as_text=True)
    assert not _JINJA.search(body), f"{path}: نشانهٔ قالب‌بندی‌نشدهٔ Jinja"


@pytest.mark.parametrize("path", [path for path, _ in PAGES])
def test_no_latin_digits_in_visible_text(client, path):
    """در رابط فارسی هیچ رقم لاتینی نباید دیده شود.

    رقم لاتین فقط در چند جای مجاز است: نام فایل عکس، نشانی، و شناسهٔ فنی کد.
    این آزمون همان مرز را نگه می‌دارد و نمونهٔ متن را گزارش می‌کند تا
    پیدا کردنش آسان باشد.
    """
    body = client.get(path).get_data(as_text=True)
    text = re.sub(r"\s+", " ", visible_text(body))
    offenders = [text[max(0, hit.start() - 34): hit.start() + 18]
                 for hit in re.finditer(r"[0-9]", text)]
    assert not offenders, f"{path}: رقم لاتین در متن → {offenders[:3]}"


@pytest.mark.parametrize("path", [path for path, _ in PAGES])
def test_referenced_assets_exist(client, path):
    """هر دارایی ارجاع‌شده باید پاسخ بدهد — نگهبان عکس شکسته و CSS گم‌شده."""
    body = client.get(path).get_data(as_text=True)
    missing = sorted({link for link in _ASSET.findall(body)
                      if client.get(link).status_code >= 400})
    assert not missing, f"{path}: دارایی گم‌شده → {missing[:4]}"


def test_home_is_rtl_and_persian(client):
    body = client.get("/").get_data(as_text=True)
    assert 'dir="rtl"' in body
    assert 'lang="fa"' in body


def test_home_leads_with_search(client):
    """جست‌وجو باید در همان نمای اول باشد، نه پشت یک صفحهٔ معرفی."""
    body = client.get("/").get_data(as_text=True)
    assert 'action="/search"' in body
    assert body.index('action="/search"') < body.index("sitefoot")


def test_home_states_the_data_is_synthetic(client):
    body = client.get("/").get_data(as_text=True)
    assert "سینتتیک" in body


def test_search_shows_result_metadata(client):
    body = client.get("/search").get_data(as_text=True)
    assert "class=\"card\"" in body
    assert "آگهی" in body


def test_invalid_filter_is_ignored_not_fatal(client):
    """فیلتر خراب باید نادیده گرفته شود، نه این‌که صفحه را بیندازد."""
    body = client.get("/search?districts=abc&amin=xyz&page=-4").get_data(as_text=True)
    assert "class=\"card\"" in body


def test_detail_shows_identifier_and_estimate(client):
    body = client.get("/listing/KH-1001").get_data(as_text=True)
    assert "KH-۱۰۰۱" in body                    # شناسه با رقم فارسی
    assert "KH-1001" not in visible_text(body)  # ولی نه با رقم لاتین در متن
    assert "ارزش برآوردی" in body
    assert "بازهٔ ۸۰ درصدی" in body


def test_detail_legacy_query_url_redirects(client):
    response = client.get("/listing?item=KH-1001")
    assert response.status_code == 301
    assert response.headers["Location"].endswith("/listing/KH-1001")


def test_compare_share_url_is_embedded(client):
    body = client.get("/compare?ids=KH-1001,KH-1002").get_data(as_text=True)
    assert "/compare?ids=KH-1001,KH-1002" in body
    assert "KH-۱۰۰۱" in body


def test_compare_with_no_selection_shows_guidance(client):
    body = client.get("/compare").get_data(as_text=True)
    assert "اضافه نشده" in body
    assert 'href="/search"' in body


def test_estimate_page_renders_a_prediction(client):
    body = client.get("/estimate").get_data(as_text=True)
    assert "ارزش برآوردی" in body
    assert "تومان" in body
    assert "بازهٔ ۸۰ درصدی" in body


def test_estimate_form_works_without_javascript(client):
    """فرم باید با ارسال معمولی هم کار کند، نه فقط با fetch."""
    body = client.get("/estimate?f=1&district=5&area=150&bedrooms=3").get_data(as_text=True)
    assert 'name="district"' in body
    assert 'value="150"' in body


def test_analytics_renders_table_and_charts(client):
    body = client.get("/analytics").get_data(as_text=True)
    assert "<svg class=\"chart\"" in body
    assert "<table>" in body


def test_methodology_lists_limitations_and_credits(client):
    body = client.get("/methodology").get_data(as_text=True)
    assert "محدودیت" in body
    assert "اعتبار تصاویر" in body


def test_methodology_page_does_not_double_a_context_variable(client):
    """متغیر تکراری در ``render_template`` استثنا می‌دهد؛ این آزمون نگهبانش است."""
    assert client.get("/methodology").status_code == 200


def test_404_page_keeps_the_site_shell(client):
    body = client.get("/nope").get_data(as_text=True)
    assert "topbar" in body and "sitefoot" in body
    assert "خطای ۴۰۴" in body


def test_base_template_lists_navigation(client):
    body = client.get("/").get_data(as_text=True)
    for href in ("/search", "/estimate", "/compare", "/analytics", "/methodology"):
        assert f'href="{href}"' in body
