# -*- coding: utf-8 -*-
"""جعلیات آزمون — انتقال‌دهندهٔ ساختگی، پاسخ‌های آماده و منابع قابل‌کنترل.

هیچ آزمونی به شبکه واقعی وابسته نیست: همان لایهٔ ``HttpClient`` که در تولید
از urllib استفاده می‌کند، اینجا یک تابع تزریقی می‌گیرد. یعنی مسیر واقعی کد
(تلاش مجدد، خطاشناسی، تبدیل فید) آزموده می‌شود، بدون هیچ درخواست بیرونی.
"""
from __future__ import annotations

import json

from karino.core.errors import SourceError
from karino.core.models import RawJob
from karino.sources.base import SourceConnector

# ---------------------------------------------------------------- انتقال‌دهنده


class FakeTransport:
    """نقشهٔ «الگوی نشانی → پاسخ» با پشتیبانی از شکست و پاسخ پشت‌سرهم."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, int, bytes]] = []
        self.fail_times: dict[str, int] = {}
        self.calls: list[str] = []

    def add(self, needle: str, body, *, status: int = 200) -> "FakeTransport":
        raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.routes.append((needle, status, raw))
        return self

    def fail(self, needle: str, times: int = 1) -> "FakeTransport":
        """اولین ``times`` درخواست منطبق، خطای شبکه می‌دهد."""
        self.fail_times[needle] = times
        return self

    def __call__(self, url: str, headers: dict) -> bytes:
        self.calls.append(url)

        for needle, remaining in list(self.fail_times.items()):
            if needle in url and remaining > 0:
                self.fail_times[needle] = remaining - 1
                raise OSError("simulated network failure")

        for needle, status, body in self.routes:
            if needle in url:
                if status >= 400:
                    import urllib.error

                    raise urllib.error.HTTPError(url, status, "fake", {}, None)
                return body

        raise OSError(f"no fake route for {url}")


# ---------------------------------------------------------------- پاسخ‌های آماده


def rss_feed(entries: list[dict], *, title: str = "Test Feed") -> bytes:
    """ساخت یک فید RSS معتبر از فهرست ورودی‌ها."""
    items = []
    for entry in entries:
        tags = "".join(f"<category>{t}</category>" for t in entry.get("tags", []))
        items.append(
            "<item>"
            f"<title>{entry.get('title', '')}</title>"
            f"<link>{entry.get('link', 'https://example.com/job')}</link>"
            f"<guid>{entry.get('guid', entry.get('title', 'g'))}</guid>"
            f"<author>{entry.get('author', '')}</author>"
            f"<pubDate>{entry.get('pubDate', 'Mon, 08 Sep 2026 10:00:00 GMT')}</pubDate>"
            f"<description><![CDATA[{entry.get('summary', '')}]]></description>"
            f"{tags}"
            "</item>")
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<rss version="2.0"><channel><title>{title}</title>'
           f'{"".join(items)}</channel></rss>')
    return xml.encode("utf-8")


def remotive_payload(jobs: list[dict]) -> bytes:
    return json.dumps({"job-count": len(jobs), "jobs": jobs}).encode("utf-8")


def remoteok_payload(jobs: list[dict]) -> bytes:
    """RemoteOK همیشه یک عنصر اطلاعیهٔ حقوقی در ابتدا دارد."""
    return json.dumps([{"legal": "RemoteOK legal notice"}, *jobs]).encode("utf-8")


def arbeitnow_payload(jobs: list[dict]) -> bytes:
    return json.dumps({"data": jobs, "links": {}, "meta": {}}).encode("utf-8")


# ---------------------------------------------------------------- منابع جعلی


class FakeSource(SourceConnector):
    """منبعی که پاسخش را آزمون تعیین می‌کند — برای آزمودن انزوای خطا."""

    kind = "fake"

    def __init__(self, key: str, jobs: list[RawJob] | None = None,
                 *, error: str | Exception | None = None, delay: float = 0.0) -> None:
        super().__init__()
        self.key = key
        self.label = f"جعلی {key}"
        self._jobs = jobs or []
        self._error = error
        self._delay = delay
        self.calls = 0

    def fetch(self) -> list[RawJob]:
        self.calls += 1
        if self._delay:
            import time

            time.sleep(self._delay)
        if self._error is not None:
            raise self._error if isinstance(self._error, Exception) else SourceError(str(self._error))
        return list(self._jobs)


def raw_job(source: str = "fake", index: int = 1, **overrides) -> RawJob:
    """آگهی خام با پیش‌فرض‌های معقول و امکان بازنویسی هر فیلد."""
    data = dict(
        source=source,
        external_id=f"{source}-{index}",
        title=f"برنامه‌نویس پایتون {index}",
        company="شرکت آزمون",
        url=f"https://example.com/{source}/{index}",
        description="نیاز به توسعه‌دهندهٔ پایتون با تجربهٔ Flask و دیتابیس SQL. دورکاری.",
        tags=["python", "flask"],
        location="دورکاری",
        remote=True,
        employment="freelance",
        published_ts=1_789_000_000,
    )
    data.update(overrides)
    return RawJob(**data)
