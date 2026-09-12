# -*- coding: utf-8 -*-
"""کانکتور Remotive — API عمومی جیسون برای مشاغل دورکاری جهانی.

Remotive یک API عمومی و مستندشده دارد که استفادهٔ آن آزاد است و برخلاف
اسکرپینگ، ساختارش پایدار است. هر رکورد دسته، برچسب، نوع همکاری، محل
لازم و گاهی بازهٔ حقوق را می‌دهد.
"""
from __future__ import annotations

import calendar
import re
import time

from ..core.models import RawJob
from ..core.text import strip_html
from .base import SourceConnector

API_URL = "https://remotive.com/api/remote-jobs"
_SALARY_NUM = re.compile(r"(\d[\d,\.]*)\s*k?", re.I)


class RemotiveSource(SourceConnector):
    key = "remotive"
    label = "Remotive"
    kind = "json"
    homepage = "https://remotive.com"

    def fetch(self) -> list[RawJob]:
        payload = self.client.get_json(f"{API_URL}?limit={self._limit()}")
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            from ..core.errors import SourceError

            raise SourceError("ساختار پاسخ Remotive غیرمنتظره بود",
                              detail=str(payload)[:150])

        jobs: list[RawJob] = []
        for item in payload["jobs"]:
            title = strip_html(item.get("title"))
            if not title:
                continue
            salary_text = strip_html(item.get("salary"))
            low, high = _parse_salary(salary_text)
            jobs.append(RawJob(
                source=self.key,
                external_id=str(item.get("id") or item.get("url") or title),
                title=title,
                company=strip_html(item.get("company_name")),
                url=item.get("url") or "",
                description=strip_html(item.get("description")),
                tags=[t for t in (item.get("tags") or []) if isinstance(t, str)]
                     + ([item["category"]] if item.get("category") else []),
                location=strip_html(item.get("candidate_required_location")),
                remote=True,                       # Remotive فقط دورکاری منتشر می‌کند
                employment=strip_html(item.get("job_type")),
                salary_text=salary_text,
                salary_min=low,
                salary_max=high,
                published_ts=_parse_date(item.get("publication_date")),
            ))
        return jobs


def _parse_date(value: str | None) -> int | None:
    """ISO-8601 (با یا بدون منطقهٔ زمانی) → timestamp یونیکس UTC."""
    if not value:
        return None
    try:
        return calendar.timegm(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None


def _parse_salary(text: str) -> tuple[float | None, float | None]:
    """بازهٔ حقوق از متن آزاد مثل «OTE $25k - $35k» یا «$80,000 - $110,000»."""
    if not text:
        return None, None
    values: list[float] = []
    for match in _SALARY_NUM.finditer(text):
        raw = match.group(1).replace(",", "")
        try:
            number = float(raw)
        except ValueError:
            continue
        if re.search(r"k\b", match.group(0), re.I) or number < 1000:
            number *= 1000
        values.append(number)
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], None
    return min(values[:2]), max(values[:2])
