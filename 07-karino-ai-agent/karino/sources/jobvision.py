# -*- coding: utf-8 -*-
"""کانکتور جاب‌ویژن — فید RSS فارسی، منبع اصلی آگهی‌های ایرانی.

جاب‌ویژن فید عمومی خود را منتشر می‌کند (۱۰۰ آگهی تازه در هر بارخوانی)؛
همین فید مستندشده استفاده می‌شود و هیچ صفحه‌ای اسکرپ نمی‌شود.
"""
from __future__ import annotations

from ..core.models import RawJob
from .base import SourceConnector

FEED_URL = "https://www.jobvision.ir/feed"


class JobVisionSource(SourceConnector):
    key = "jobvision"
    label = "جاب‌ویژن"
    kind = "rss"
    homepage = "https://jobvision.ir"

    def fetch(self) -> list[RawJob]:
        jobs = self._rss_jobs(FEED_URL, limit=self._limit())
        # فید جاب‌ویژن شرکت را جدا نمی‌دهد؛ عنوان آگهی خودش گویا است
        return jobs
