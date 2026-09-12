# -*- coding: utf-8 -*-
"""ثبت و ساخت منابع.

افزودن منبع تازه = نوشتن یک کلاس کانکتور و افزودن آن به ``REGISTRY``.
هیچ جای دیگری از کد لازم نیست تغییر کند؛ خط لوله، گزارش منابع و داشبورد
همه از همین فهرست تغذیه می‌شوند.
"""
from __future__ import annotations

from ..config import Settings, get_settings
from .arbeitnow import ArbeitnowSource
from .base import HttpClient, SourceConnector
from .feeds import CustomFeedSource
from .hn_hiring import HackersNewsJobsSource
from .jobvision import JobVisionSource
from .remoteok import RemoteOKSource
from .remotive import RemotiveSource
from .weworkremotely import WeWorkRemotelySource

#: ترتیب نمایش در داشبورد = ترتیب همین فهرست
REGISTRY: tuple[type[SourceConnector], ...] = (
    JobVisionSource,
    RemotiveSource,
    RemoteOKSource,
    ArbeitnowSource,
    WeWorkRemotelySource,
    HackersNewsJobsSource,
)

#: منبعی که همیشه در دسترس است ولی از پیش فعال نیست
OPTIONAL_KEYS = ("custom_feeds",)

ALL_KEYS: tuple[str, ...] = tuple(cls.key for cls in REGISTRY) + OPTIONAL_KEYS

LABELS: dict[str, str] = {cls.key: cls.label for cls in REGISTRY}
LABELS["custom_feeds"] = "فیدهای دلخواه"

KINDS: dict[str, str] = {cls.key: cls.kind for cls in REGISTRY}
KINDS["custom_feeds"] = "rss"


def build_sources(settings: Settings | None = None,
                  client: HttpClient | None = None) -> list[SourceConnector]:
    """منابع فعال را بر اساس تنظیمات می‌سازد.

    ``KARINO_SOURCES`` فهرست کلیدهاست؛ خالی‌بودنش یعنی همهٔ منابع اصلی
    فعال‌اند. کلید ناشناخته بی‌صدا رد می‌شود تا یک اشتباه تایپی باعث خطای
    راه‌اندازی نشود.
    """
    settings = settings or get_settings()
    enabled = [k for k in (settings.enabled_sources or []) if k in ALL_KEYS]
    if not enabled:
        enabled = [cls.key for cls in REGISTRY]

    sources: list[SourceConnector] = []
    for cls in REGISTRY:
        if cls.key in enabled:
            sources.append(cls(client=client))

    if "custom_feeds" in enabled or settings.extra_feeds:
        sources.append(CustomFeedSource(settings.extra_feeds, client=client))

    return sources


def describe(key: str) -> dict:
    return {"key": key, "label": LABELS.get(key, key), "kind": KINDS.get(key, "rss")}


__all__ = [
    "REGISTRY", "ALL_KEYS", "LABELS", "KINDS", "OPTIONAL_KEYS",
    "build_sources", "describe",
    "SourceConnector", "HttpClient",
    "JobVisionSource", "RemotiveSource", "RemoteOKSource", "ArbeitnowSource",
    "WeWorkRemotelySource", "HackersNewsJobsSource", "CustomFeedSource",
]
