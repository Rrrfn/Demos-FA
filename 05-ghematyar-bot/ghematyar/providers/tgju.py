# -*- coding: utf-8 -*-
"""ارائه‌دهندهٔ tgju — بازار داخل (طلا، سکه، ارز) و رمزارزها.

سه مسیر به‌ترتیب اولویت امتحان می‌شوند؛ هر سه یک خانوادهٔ داده‌اند ولی
مسیرهای شبکه‌ای متفاوتی دارند:

1. ``call1.tgju.org/ajax.json`` — خوراک ماشین‌خوان (سبک، کامل، ترجیحی)
2. ``call.tgju.org/ajax.json``  — میزبان دوم همان خوراک (fallback شبکه‌ای)
3. صفحهٔ HTML tgju             — آخرین راه، برای اقلامی که در خوراک نیستند

نکتهٔ مهم دربارهٔ «تغییر»: این خوراک برای طلا/سکه/ارز مقدار ``d`` و ``dp``
را صفر می‌دهد (تغییر روزانه منتشر نمی‌شود) و فقط برای رمزارزها مقدار
واقعی دارد. بنابراین تغییر اقلام ریالی از تاریخچهٔ خودمان محاسبه می‌شود
(``MarketService``) و هرگز از خودمان «درصد تغییر» نمی‌سازیم.
"""
from __future__ import annotations

import html as htmllib
import logging
import re
import time
from datetime import datetime
from typing import Any, Sequence

from bs4 import BeautifulSoup

from ..config import DataConfig
from ..core import assets as asset_registry
from ..core.models import AssetKind, Quote
from ..core.formatting import to_float
from .base import BaseProvider, HttpClient

log = logging.getLogger("ghematyar.providers.tgju")

AJAX_URLS: tuple[str, ...] = (
    "https://call1.tgju.org/ajax.json",
    "https://call.tgju.org/ajax.json",
)
HTML_URL = "https://www.tgju.org/"

# نگاشت کلیدهای خوراک به slugهای ثبت‌شده — از رجیستری ساخته می‌شود
_AJAX_INDEX: dict[str, str] = {}
_HTML_INDEX: dict[str, str] = {}
for _asset in asset_registry.ALL_ASSETS:
    for _key in _asset.tgju_ajax:
        _AJAX_INDEX.setdefault(_key, _asset.slug)
    for _key in _asset.tgju_html:
        _HTML_INDEX.setdefault(_key, _asset.slug)


def _clean_number(raw: Any) -> float | None:
    """تبدیل مقدار خوراک (رشتهٔ دارای جداکننده یا عدد) به عدد.

    مقدار نامعتبر ``None`` می‌شود تا دادهٔ ناقص به‌جای صفر ثبت نشود.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = htmllib.unescape(str(raw)).strip()
    if not text or text in {"-", "—", "N/A"}:
        return None
    return to_float(text)


def _to_unit(value: float, unit: str) -> float:
    """ریال → تومان برای اقلام داخلی؛ رمزارزها به دلار می‌مانند."""
    if unit == "toman":
        return value / 10.0
    return value


def parse_observed_at(record: dict[str, Any]) -> float:
    """زمان انتشار داده نزد منبع از فیلد ``ts``.

    اگر قابل خواندن نبود، زمان دریافت فعلی برگردانده می‌شود؛ تخمین زدن
    زمان دروغین بدتر از اعلام زمان دریافت است.
    """
    raw = (record or {}).get("ts")
    if not raw:
        return time.time()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).timestamp()
        except (ValueError, TypeError):
            continue
    return time.time()


def parse_ajax(payload: Any, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
    """پارس خوراک JSON به نقل‌قول‌ها.

    پاسخ نامعتبر خطای صریح می‌دهد (نه دیکشنری خالی) تا لایهٔ بالاتر
    بتواند fallback را درست انتخاب کند.
    """
    from ..core.errors import MalformedResponse

    if not isinstance(payload, dict):
        raise MalformedResponse("tgju", "payload is not an object")
    current = payload.get("current")
    if not isinstance(current, dict):
        current = payload  # سازگاری با ساختار قدیمی‌تر

    wanted = set(slugs) if slugs else None
    quotes: dict[str, Quote] = {}
    for key, record in current.items():
        slug = _AJAX_INDEX.get(key)
        if slug is None or not isinstance(record, dict):
            continue
        if wanted is not None and slug not in wanted:
            continue
        asset = asset_registry.ASSETS[slug]
        raw_price = record.get("p")
        price = _clean_number(raw_price)
        if price is None or price <= 0:
            continue
        price = _to_unit(price, asset.unit)

        low = _clean_number(record.get("l"))
        high = _clean_number(record.get("h"))
        change_abs = _clean_number(record.get("d"))
        change_pct = _clean_number(record.get("dp"))

        quote = Quote(
            slug=slug,
            price=price,
            unit=asset.unit,
            source="tgju",
            observed_at=parse_observed_at(record),
            day_low=_to_unit(low, asset.unit) if low and low > 0 else None,
            day_high=_to_unit(high, asset.unit) if high and high > 0 else None,
            decimals=asset.precision,
        )
        # برای اقلام داخلی این خوراک تغییر روزانه ندارد؛ صفرِ منتشرشده را
        # به‌عنوان «بی‌تغییر» جا نمی‌زنیم و محاسبه را به تاریخچه می‌سپاریم.
        if asset.kind is AssetKind.CRYPTO and change_abs not in (None, 0):
            quote.change_abs = _to_unit(change_abs, asset.unit)
            quote.change_pct = change_pct
            quote.change_basis = "تغییر ۲۴ ساعته (منبع)"
        quotes[slug] = quote
    return quotes


def _signed(raw: str) -> float:
    """عدد با حفظ علامت.

    ``to_float`` عمداً فقط ارقام را نگه می‌دارد (ورودی کاربر علامت ندارد)،
    ولی سلول تغییر tgju می‌تواند منفی باشد؛ نادیده گرفتن منفی یعنی نمایش
    افت قیمت به‌جای رشد.
    """
    text = (raw or "").strip()
    value = to_float(text)
    return -value if text.startswith("-") else value


def _parse_change_cell(cell: str) -> tuple[float | None, float | None]:
    """خواندن سلول تغییر با قالب ``(1.86%) 1436.08``.

    صفر منتشرشده «بدون تغییر» نیست، بلکه «تغییری گزارش نشده» است؛
    بنابراین صفر به ``None`` تبدیل می‌شود تا لایهٔ بالاتر مسیر تاریخچه
    را انتخاب کند.
    """
    pct = None
    abs_change = None
    match = re.search(r"\(\s*(-?[\d.,]+)\s*%\s*\)\s*(-?[\d.,]*)", cell or "")
    if match:
        pct = _signed(match.group(1))
        if match.group(2):
            abs_change = _signed(match.group(2))
    if pct == 0:
        pct = None
    if abs_change == 0:
        abs_change = None
    return pct, abs_change


def parse_html(html_text: str, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
    """پارس ردیف‌های بازار در صفحهٔ tgju — آخرین راه (برای سکهٔ گرمی).

    ساختار ردیف تاییدشده (۶ خانه، بدون ستون عنوان):
    ``[قیمت, (درصد%) تغییر, کمینه, بیشینه, زمان]`` و مقادیر **ریالی**اند.

    رمزارزها عامدانه از این مسیر کنار گذاشته شده‌اند: در خوراک ماشین‌خوان
    رمزارزها دلاری‌اند ولی در همین صفحهٔ HTML تتر به تومان است. تفاوت
    واحد یک قلم بین دو منبع، خطرناک‌تر از نبود داده است.
    """
    from ..core.errors import MalformedResponse

    if not html_text or len(html_text) < 200:
        raise MalformedResponse("tgju-html", "page too small")
    soup = BeautifulSoup(html_text, "lxml")
    wanted = set(slugs) if slugs else None
    quotes: dict[str, Quote] = {}

    for node in soup.find_all(attrs={"data-market-nameslug": True}):
        key = node.get("data-market-nameslug")
        slug = _HTML_INDEX.get(key) if key else None
        if slug is None or (wanted is not None and slug not in wanted):
            continue
        asset = asset_registry.ASSETS[slug]
        if asset.kind is AssetKind.CRYPTO:
            continue  # واحد در این مسیر قابل اعتماد نیست
        cells = [c.get_text(" ", strip=True) for c in node.find_all("td")]
        if len(cells) < 4:
            continue
        raw_price = to_float(cells[0])
        price = _to_unit(raw_price, asset.unit)
        # نگهبان منطقی: قیمت ریالی کمتر از ۱۰۰ تومان احتمالاً ستون اشتباه است
        if price <= 0 or (asset.unit == "toman" and price < 100):
            continue
        low = _to_unit(to_float(cells[2]), asset.unit) if cells[2] else None
        high = _to_unit(to_float(cells[3]), asset.unit) if cells[3] else None
        change_pct, change_abs = _parse_change_cell(cells[1])
        quotes[slug] = Quote(
            slug=slug,
            price=price,
            unit=asset.unit,
            source="tgju-html",
            observed_at=time.time(),
            day_low=low if low and low > 0 else None,
            day_high=high if high and high > 0 else None,
            change_abs=_to_unit(change_abs, asset.unit) if change_abs else None,
            change_pct=change_pct,
            change_basis="تغییر ۲۴ ساعته (منبع)" if change_pct is not None else "",
            decimals=asset.precision,
        )
    return quotes


def _extract_html_payload(html_text: str) -> list[dict[str, Any]]:
    """استخراج آرایهٔ JSON تعبیه‌شده در صفحه (در صورت وجود)."""
    match = re.search(r"var\s+data\s*=\s*(\[.*?\]);", html_text, re.S)
    if not match:
        return []
    try:
        import json

        data = json.loads(match.group(1))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


class TgjuProvider(BaseProvider):
    """ارائه‌دهندهٔ بازار داخل با زنجیرهٔ fallback."""

    name = "tgju"

    def __init__(self, client: HttpClient, config: DataConfig) -> None:
        super().__init__(client, config)

    async def _fetch(self, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
        wanted = [s for s in (slugs or asset_registry.ASSETS) if asset_registry.exists(s)]
        if not wanted:
            return {}
        quotes: dict[str, Quote] = {}
        errors: list[str] = []

        for url in AJAX_URLS:
            try:
                payload = await self.client.fetch(url, provider=f"tgju:{url}")
                found = parse_ajax(payload, wanted)
                if found:
                    log.info("tgju ajax ok via %s (%d quotes)", url, len(found))
                    quotes.update(found)
                    break
                errors.append(f"{url}: empty feed")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")
                log.warning("tgju ajax failed %s: %s", url, exc)

        missing = [s for s in wanted if s not in quotes]
        if missing:
            # آخرین راه: صفحهٔ HTML (برای اقلامی که در خوراک نیستند)
            try:
                html_text = await self.client.fetch(HTML_URL, provider="tgju:html", as_json=False)
                found = parse_html(html_text, missing)
                if found:
                    log.info("tgju html fallback ok (%d quotes)", len(found))
                    quotes.update(found)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{HTML_URL}: {exc}")
                log.warning("tgju html failed: %s", exc)

        if not quotes:
            self.last_error = "; ".join(errors)[:300]
        return quotes
