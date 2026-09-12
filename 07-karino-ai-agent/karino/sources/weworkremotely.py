# -*- coding: utf-8 -*-
"""کانکتور We Work Remotely — فید RSS عمومی مشاغل دورکاری انگلیسی.

عنوان ورودی‌های این فید با الگوی «شرکت: عنوان» می‌آید؛ جداکردن نام شرکت
در لایهٔ پایه انجام می‌شود تا کارت آگهی نام کارفرما را هم نشان دهد.
"""
from __future__ import annotations

from ..core.models import RawJob
from .base import SourceConnector

FEED_URL = "https://weworkremotely.com/remote-jobs.rss"


class WeWorkRemotelySource(SourceConnector):
    key = "weworkremotely"
    label = "We Work Remotely"
    kind = "rss"
    homepage = "https://weworkremotely.com"

    def fetch(self) -> list[RawJob]:
        return self._rss_jobs(FEED_URL, limit=self._limit())
