# -*- coding: utf-8 -*-
"""کانکتور RemoteOK — API عمومی جیسون با بازهٔ حقوق واقعی.

نکتهٔ ساختاری مهم: عنصر نخست پاسخ RemoteOK یک اطلاعیهٔ حقوقی است، نه آگهی.
اگر بدون فیلتر خوانده شود، یک «آگهی» بی‌معنا وارد خط لوله می‌شود. همچنین
این منبع حدود نیمی از آگهی‌ها را با حقوق عددی می‌دهد که عامل «بودجه» را
از تخمین به داده بدل می‌کند.
"""
from __future__ import annotations

import calendar
import time

from ..core.models import RawJob
from ..core.text import strip_html
from .base import SourceConnector

API_URL = "https://remoteok.com/api"


class RemoteOKSource(SourceConnector):
    key = "remoteok"
    label = "RemoteOK"
    kind = "json"
    homepage = "https://remoteok.com"

    def fetch(self) -> list[RawJob]:
        payload = self.client.get_json(API_URL)
        if not isinstance(payload, list):
            from ..core.errors import SourceError

            raise SourceError("ساختار پاسخ RemoteOK غیرمنتظره بود",
                              detail=str(payload)[:150])

        jobs: list[RawJob] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            # عنصر اطلاعیهٔ حقوقی و رکوردهای ناقص را رد کن
            title = strip_html(item.get("position") or item.get("title"))
            if not title or "legal" in item:
                continue

            salary_min = _number(item.get("salary_min"))
            salary_max = _number(item.get("salary_max"))
            jobs.append(RawJob(
                source=self.key,
                external_id=str(item.get("id") or item.get("slug") or title),
                title=title,
                company=strip_html(item.get("company")),
                url=item.get("apply_url") or item.get("url") or "",
                description=strip_html(item.get("description")),
                tags=[t for t in (item.get("tags") or []) if isinstance(t, str)],
                location=strip_html(item.get("location")),
                remote=True,
                employment="",
                salary_text=_salary_text(salary_min, salary_max),
                salary_min=salary_min,
                salary_max=salary_max,
                published_ts=_epoch(item.get("epoch") or item.get("date")),
            ))
            if len(jobs) >= self._limit():
                break
        return jobs


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _salary_text(low: float | None, high: float | None) -> str:
    if not low and not high:
        return ""
    if low and high and low != high:
        return f"${int(low):,} – ${int(high):,}"
    amount = low or high
    return f"${int(amount):,}"


def _epoch(value) -> int | None:
    """``epoch`` عدد یونیکس است و ``date`` رشتهٔ ISO؛ هر دو پذیرفته می‌شوند."""
    if value is None:
        return None
    if isinstance(value, str) and not value.isdigit():
        try:
            return calendar.timegm(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        number //= 1000
    return number if number <= time.time() + 86_400 else None
