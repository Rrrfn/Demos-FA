# -*- coding: utf-8 -*-
"""کانکتور Arbeitnow — API عمومی جیسون آگهی‌های اروپا.

این منبع پرچم دورکاری، محل، برچسب و انواع همکاری را می‌دهد؛ برای سنجش
عامل «محل» و «نوع همکاری» در موتور امتیازدهی مفید است.
"""
from __future__ import annotations

import time

from ..core.models import RawJob
from ..core.text import strip_html
from .base import SourceConnector

API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(SourceConnector):
    key = "arbeitnow"
    label = "Arbeitnow"
    kind = "json"
    homepage = "https://www.arbeitnow.com"

    def fetch(self) -> list[RawJob]:
        payload = self.client.get_json(API_URL)
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            from ..core.errors import SourceError

            raise SourceError("ساختار پاسخ Arbeitnow غیرمنتظره بود",
                              detail=str(payload)[:150])

        jobs: list[RawJob] = []
        for item in rows[: self._limit()]:
            title = strip_html(item.get("title"))
            if not title:
                continue
            job_types = item.get("job_types") or []
            jobs.append(RawJob(
                source=self.key,
                external_id=str(item.get("slug") or item.get("url") or title),
                title=title,
                company=strip_html(item.get("company_name")),
                url=item.get("url") or "",
                description=strip_html(item.get("description")),
                tags=[t for t in (item.get("tags") or []) if isinstance(t, str)],
                location=strip_html(item.get("location")),
                remote=bool(item.get("remote")),
                employment=", ".join(job_types) if job_types else "",
                published_ts=_epoch(item.get("created_at")),
            ))
        return jobs


def _epoch(value) -> int | None:
    """``created_at`` می‌تواند عدد یونیکس یا رشتهٔ عددی باشد."""
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    # مقادیر میلی‌ثانیه‌ای را به ثانیه برگردان
    if number > 10_000_000_000:
        number //= 1000
    if number > time.time() + 86_400:
        return None
    return number
