# -*- coding: utf-8 -*-
"""بازرسی صفحه‌ها — یک ابزار توسعه، نه بخشی از محصول.

هر صفحه را با کارخواه آزمون Flask رندر می‌کند و چیزهایی را بررسی می‌کند که
چشم به‌سختی می‌بیند و آزمون واحد هم معمولاً از قلم می‌اندازد:

* **رقم لاتین در متن دیده‌شده.** در یک رابط تمام‌فارسی، یک «2024» تنها جای
  ناهمخوان است.
* **قالب‌بندی‌نشدهٔ Jinja.** ``{{`` در خروجی یعنی یک متغیر جا افتاده.
* **دارایی‌های گمشده.** هر ``src``/``href`` داخلی که ۴۰۴ بدهد، عکس شکسته یا
  لینک مرده است.
* **پیوندهای داخلی مرده.** هر نشانی که به صفحه‌ای نمی‌رسد.

اجرا::

    python -m tools.audit_pages
"""
from __future__ import annotations

import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from khoneyab.web import create_app  # noqa: E402

PAGES = (
    "/", "/search", "/search?districts=1&districts=2&amin=90&bedrooms=2&sort=کم‌ترین قیمت متر",
    "/search?pmax=15&parking=1", "/search?page=3", "/search?page=999",
    "/listing/KH-1001", "/listing/KH-1050", "/listing/KH-1200",
    "/compare", "/compare?ids=KH-1001,KH-1002,KH-1003",
    "/estimate", "/estimate?f=1&district=1&area=200&bedrooms=3&age=2&floor=8",
    "/analytics", "/methodology", "/saved",
    "/api/health", "/api/overview", "/api/listings", "/api/estimate",
    "/api/analytics", "/api/methodology", "/robots.txt", "/nope",
)

_TAG = re.compile(r"<(script|style)\b.*?</\1>", re.S)
#: بخش‌هایی که لاتین بودنشان درست است: کد، شناسهٔ فنی، نام پدیدآورنده و نشانی
#: بیرونی. اینها ترجمه‌شدنی نیستند و نباید هشدار بدهند.
_LATIN_OK = re.compile(
    r'''<(code|kbd|samp|pre)\b.*?</\1>'''
    r'''|<[^>]+class=["'][^"']*\blatin\b[^"']*["'][^>]*>.*?</[a-z]+>''',
    re.S | re.I,
)
_MARKUP = re.compile(r"<[^>]+>")
_ASSET = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""")
_JINJA = re.compile(r"\{\{|\{%")


def visible_text(html: str) -> str:
    """متن دیده‌شده — بدون برچسب، بدون اسکریپت، بدون ویژگی و بدون بخش لاتین."""
    body = _TAG.sub(" ", html)
    body = _LATIN_OK.sub(" ", body)
    body = _MARKUP.sub(" ", body)
    return body


def latin_digits(text: str) -> list[str]:
    """رقم‌های لاتین متن — ``[0-9]`` نه ``\\d`` که رقم فارسی را هم می‌گیرد."""
    return re.findall(r"[0-9]", text)


def internal_links(html: str) -> set[str]:
    """نشانی‌های داخلی که در صفحه به آن‌ها ارجاع شده."""
    found: set[str] = set()
    for raw in _ASSET.findall(html):
        if raw.startswith(("data:", "mailto:", "javascript:", "#", "//")):
            continue
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            continue
        found.add(urljoin("/", parsed.path) + (f"?{parsed.query}" if parsed.query else ""))
    return found


def asset_bytes(client, html: str) -> tuple[int, int]:
    """مجموع حجم دارایی‌هایی که مرورگر برای این صفحه می‌گیرد — (کل، عکس).

    فقط ``/static/`` شمرده می‌شود. پیوندهای ناوبری هم در ``href`` می‌آیند و اگر
    شمرده شوند، عدد بی‌معنا بزرگ می‌شود: صفحهٔ تحلیل بازار خودش عکسی ندارد،
    پس نباید یک مگابایت وزن داشته باشد.
    """
    total = 0
    images = 0
    counted: set[str] = set()
    for link in internal_links(html):
        if not link.startswith("/static/") or link in counted:
            continue
        counted.add(link)
        response = client.get(link)
        if response.status_code >= 400:
            continue
        size = len(response.data)
        total += size
        if link.startswith("/static/img"):
            images += size
    return total, images


def run() -> int:
    app = create_app()
    client = app.test_client()

    problems: list[str] = []
    print(f"{'مسیر':<52} {'کد':>4} {'HTML':>8} {'کل صفحه':>9} {'عکس':>8} {'زمان':>7}  یادداشت")
    print("-" * 116)

    heaviest = 0.0
    for path in PAGES:
        started = time.perf_counter()
        response = client.get(path)
        elapsed = (time.perf_counter() - started) * 1000
        body = response.get_data(as_text=True)
        is_html = "text/html" in response.headers.get("Content-Type", "")
        notes: list[str] = []

        weight = 0.0
        image_weight = 0.0
        if is_html:
            weight, image_weight = asset_bytes(client, body)
            heaviest = max(heaviest, weight / 1024)
            if weight > 1_500_000:
                notes.append("سنگین")
                problems.append(
                    f"{path}: حجم صفحه {weight/1024:.0f}KB — بیش از یک و نیم مگابایت")
            text = visible_text(body)
            digits = latin_digits(text)
            if digits:
                notes.append(f"{len(digits)} رقم لاتین")
                problems.append(f"{path}: رقم لاتین در متن → {' '.join(digits[:12])}")
            if _JINJA.search(body):
                notes.append("Jinja قالب‌بندی‌نشده")
                problems.append(f"{path}: نشانهٔ قالب‌بندی‌نشدهٔ Jinja")
            if response.status_code < 400:
                missing = [link for link in internal_links(body)
                           if link.startswith("/") and client.get(link).status_code >= 400]
                if missing:
                    notes.append(f"{len(missing)} لینک مرده")
                    problems.append(f"{path}: پیوند مرده → {missing[:4]}")

        expected_error = path == "/nope"
        if (response.status_code >= 400) != expected_error:
            problems.append(f"{path}: کد وضعیت {response.status_code}")

        print(f"{path:<52} {response.status_code:>4} {len(body)/1024:>6.1f}KB "
              f"{weight/1024:>7.1f}KB {image_weight/1024:>6.1f}KB {elapsed:>5.0f}ms  "
              f"{'، '.join(notes) or 'سالم'}")

    print("-" * 116)
    print(f"سنگین‌ترین صفحه: {heaviest:.0f}KB — برای یک بازدید کامل با کش سرد.")
    if problems:
        print(f"\n{len(problems)} مورد برای بررسی:")
        for item in problems:
            print(f"  • {item}")
        return 1
    print("\nهمهٔ صفحه‌ها سالم: بدون رقم لاتین، بدون لینک مرده، بدون خطای وضعیت.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
