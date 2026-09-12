# -*- coding: utf-8 -*-
"""کانکتور فیدهای دلخواه — هر RSS عمومی که کاربر معرفی کند.

این کانکتور همان مسیری است که «شکست یک منبع» را در عمل نشان می‌دهد: اگر
فید کاربر ۴۰۳ بدهد یا ساختارش خراب باشد، فقط همین منبع خطا می‌گیرد، در
صفحهٔ منابع با علت واقعی ثبت می‌شود و بقیهٔ خط لوله بی‌وقفه ادامه می‌دهد.
"""
from __future__ import annotations

import hashlib

from ..core.models import RawJob
from .base import SourceConnector


class CustomFeedSource(SourceConnector):
    key = "custom_feeds"
    label = "فیدهای دلخواه"
    kind = "rss"

    def __init__(self, urls: list[str], client=None) -> None:
        super().__init__(client)
        self.urls = [u.strip() for u in urls if u and u.strip()]

    def fetch(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        failures: list[str] = []

        for url in self.urls:
            try:
                for job in self._rss_jobs(url, limit=self._limit()):
                    # شناسهٔ یکتا بر پایهٔ خود آدرس تا دو فید با GUID یکسان قاطی نشوند
                    suffix = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
                    job.external_id = f"{job.external_id}#{suffix}"
                    job.tags = list(job.tags) + [f"feed:{_host(url)}"]
                    jobs.append(job)
            except Exception as exc:  # noqa: BLE001 — عمداً پهن: یک فید خراب بقیه را نباید بخواباند
                failures.append(f"{_host(url)}: {exc}")

        if not jobs and failures:
            from ..core.errors import SourceError

            raise SourceError("هیچ‌کدام از فیدهای دلخواه خوانده نشد",
                              detail=" | ".join(failures[:3]))
        return jobs


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).netloc or url)[:40]
