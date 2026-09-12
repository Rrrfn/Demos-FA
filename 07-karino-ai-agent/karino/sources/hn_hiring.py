# -*- coding: utf-8 -*-
"""کانکتور Hacker News «Who is hiring» — فید RSS عمومی.

hnrss یک سرویس عمومی است که رشته‌های «چه کسی استخدام می‌کند» را به فید
تبدیل می‌کند. آگهی‌های این فید معمولاً فنی و با شرح مفصل‌اند، پس برای
موتور تطبیق مهارت سیگنال خوبی می‌دهند.
"""
from __future__ import annotations

from ..core.models import RawJob
from .base import SourceConnector

FEED_URL = "https://hnrss.org/jobs"


class HackersNewsJobsSource(SourceConnector):
    key = "hn_hiring"
    label = "Hacker News (Who is hiring)"
    kind = "rss"
    homepage = "https://news.ycombinator.com/jobs"

    def fetch(self) -> list[RawJob]:
        return self._rss_jobs(FEED_URL, limit=self._limit())
