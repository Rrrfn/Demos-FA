# -*- coding: utf-8 -*-
"""پایهٔ کانکتورها — یک کلاینت HTTP مقاوم و کلاس پایهٔ منبع.

قاعدهٔ این لایه: **هیچ منبعی کل خط لوله را متوقف نمی‌کند.** هر کانکتور
خطای خودش را به ``SourceError`` بدل می‌کند و لایهٔ بالاتر آن را در گزارش
منابع ثبت می‌کند؛ بقیهٔ منابع به کار خود ادامه می‌دهند.
"""
from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

import feedparser

from ..config import get_settings
from ..core.errors import SourceError
from ..core.models import RawJob
from ..core.text import strip_html

log = logging.getLogger("krn.sources")

DEFAULT_HEADERS = {
    "User-Agent": "Karino/1.0 (+job-intelligence-demo; contact: demo@example.com)",
    "Accept": "application/json, application/rss+xml, application/xml, text/xml, */*",
}


class HttpClient:
    """GET ساده با مهلت، تلاش مجدد و عقب‌نشینی نمایی.

    فقط برای منابعی که خودشان دادهٔ عمومی عرضه می‌کنند استفاده می‌شود — فید
    RSS یا API عمومی. هیچ صفحهٔ HTML اسکرپ نمی‌شود و هیچ هدر جعلی مرورگر
    فرستاده نمی‌شود.
    """

    def __init__(self, timeout: int | None = None, retries: int | None = None,
                 backoff: float | None = None, transport=None) -> None:
        settings = get_settings()
        self.timeout = timeout if timeout is not None else settings.http_timeout
        self.retries = retries if retries is not None else settings.http_retries
        self.backoff = backoff if backoff is not None else settings.http_backoff
        #: تزریق‌پذیر برای تست — تابعی با امضای ``(url, headers) -> bytes``
        self._transport = transport

    def get(self, url: str, *, headers: dict | None = None) -> bytes:
        """دریافت بایت‌ها. در پایانِ تلاش‌ها ``SourceError`` می‌دهد."""
        hdrs = {**DEFAULT_HEADERS, **(headers or {})}
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                return self._once(url, hdrs)
            except urllib.error.HTTPError as exc:
                last_error = exc
                # ۴xx تلاش مجدد را توجیه نمی‌کند؛ ۴۲۹ و ۵xx می‌کند
                if exc.code < 500 and exc.code != 429:
                    raise SourceError(
                        f"منبع کد {exc.code} برگرداند",
                        detail=f"{url} → HTTP {exc.code}",
                    ) from exc
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
                last_error = exc
            except ValueError as exc:  # آدرس نامعتبر
                raise SourceError("آدرس منبع نامعتبر است", detail=f"{url} → {exc}") from exc

            if attempt < self.retries:
                delay = self.backoff ** attempt
                log.warning("source retry %d/%d in %.1fs: %s", attempt + 1, self.retries, delay, url)
                time.sleep(delay)

        raise SourceError(
            "منبع در دسترس نیست",
            detail=f"{url} → {type(last_error).__name__}: {last_error}",
        ) from last_error

    def _once(self, url: str, headers: dict) -> bytes:
        if self._transport is not None:
            return self._transport(url, headers)
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def get_json(self, url: str, *, headers: dict | None = None):
        raw = self.get(url, headers=headers)
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SourceError("پاسخ منبع JSON معتبر نبود",
                              detail=f"{url} → {raw[:120]!r}") from exc

    def parse_feed(self, url: str):
        """فید RSS/Atom را با feedparser می‌خواند و نتیجهٔ نامعتبر را خطا می‌داند."""
        raw = self.get(url)
        parsed = feedparser.parse(raw)
        if getattr(parsed, "bozo", 0) and not parsed.entries:
            reason = getattr(parsed, "bozo_exception", None)
            raise SourceError("فید قابل خواندن نبود", detail=f"{url} → {reason}")
        return parsed


class SourceConnector(ABC):
    """قرارداد مشترک همهٔ منابع."""

    key: str = ""
    label: str = ""
    kind: str = "rss"
    homepage: str = ""

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    @abstractmethod
    def fetch(self) -> list[RawJob]:
        """آگهی‌های خام. در خطا ``SourceError`` می‌دهد."""

    # --- ابزارهای مشترک ---

    def _rss_jobs(self, url: str, *, limit: int | None = None) -> list[RawJob]:
        """تبدیل ورودی‌های فید به آگهی خام با یکسان‌سازی حداقلی."""
        feed = self.client.parse_feed(url)
        title = strip_html(getattr(feed, "feed", {}).get("title", "") or "")
        jobs: list[RawJob] = []

        for entry in feed.entries[: limit or get_settings().per_source_limit]:
            link = entry.get("link") or ""
            guid = entry.get("id") or link or entry.get("title") or ""
            if not guid or not entry.get("title"):
                continue

            tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
            published = entry.get("published_parsed") or entry.get("updated_parsed")

            jobs.append(RawJob(
                source=self.key,
                external_id=str(guid)[:300],
                title=strip_html(entry.get("title")),
                company=strip_html(entry.get("author")) or self._company_from_title(entry.get("title")),
                url=link,
                description=strip_html(entry.get("summary") or entry.get("description") or ""),
                tags=tags,
                location=strip_html(entry.get("region") or ""),
                published_ts=int(time.mktime(published)) if published else None,
                salary_text="",
            ))
        log.info("source %s: %d entries", self.key, len(jobs))
        return jobs

    @staticmethod
    def _company_from_title(title: str | None) -> str:
        """برخی فیدها نام شرکت را داخل عنوان می‌گذارند: «Stadium: AWS Engineer»."""
        text = strip_html(title)
        if ":" in text:
            head = text.split(":", 1)[0].strip()
            if 2 <= len(head) <= 40:
                return head
        return ""

    def _limit(self) -> int:
        return get_settings().per_source_limit
