# -*- coding: utf-8 -*-
"""زیرساخت ارائه‌دهندهٔ داده.

* ``HttpClient`` مهلت زمانی، تلاش مجدد، تأخیر نمایی با نوسان تصادفی، احترام
  به ``Retry-After`` و مدارشکن هر منبع را تأمین می‌کند.
* ``BaseProvider`` قرارداد مشترک منابع است: هر منبع تعدادی دارایی می‌گیرد و
  نگاشتی از ``slug`` به ``Quote`` برمی‌گرداند.

هیچ منبعی اجازه ندارد در نبود داده، عدد پیش‌فرض بسازد. نبود داده یا یعنی آن
قلم در پاسخ نیست (که در خروجی غایب می‌ماند) یا یعنی کل منبع شکست خورده (که
``ProviderError`` بالا می‌رود).
"""
from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..config import DataConfig
from ..core.errors import CircuitOpen, MalformedResponse, ProviderError, RateLimited
from ..core.models import Asset, Quote

log = logging.getLogger("cheshmbaz.providers")

# کدهایی که تلاش مجدد روی آن‌ها معنا دارد
_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass(slots=True)
class CircuitBreaker:
    """مدارشکن ساده: پس از چند خطای پیوسته، منبع موقتاً کنار گذاشته می‌شود."""

    name: str
    threshold: int = 4
    cooldown: float = 120.0
    failures: int = 0
    opened_at: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.opened_at > 0.0

    def remaining(self) -> float:
        if not self.is_open:
            return 0.0
        return max(0.0, self.cooldown - (time.time() - self.opened_at))

    def allow(self) -> None:
        """اگر مدار باز است ``CircuitOpen`` می‌دهد."""
        if not self.is_open:
            return
        left = self.remaining()
        if left > 0:
            raise CircuitOpen(self.name, left)
        # پنجرهٔ خنک‌شدن تمام شده؛ یک تلاش آزمایشی آزاد است
        self.opened_at = 0.0
        self.failures = 0

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.time()
            log.warning(
                "circuit opened for %s after %d consecutive failures", self.name, self.failures
            )

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "open": self.is_open,
            "failures": self.failures,
            "remaining": round(self.remaining(), 1),
        }


@dataclass(slots=True)
class HttpResponse:
    """پاسخ خام یک درخواست."""

    status: int
    body: bytes
    url: str
    elapsed_ms: int = 0


@dataclass(slots=True)
class _Transport:
    """انتقال‌دهندهٔ پیش‌فرض بر پایهٔ ``urllib`` (بدون وابستگی بیرونی)."""

    timeout: float
    user_agent: str

    def __call__(self, url: str) -> tuple[int, bytes, dict[str, str]]:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:  # پاسخ با کد خطا
            headers = dict(error.headers or {})
            return error.code, error.read() or b"", headers


class HttpClient:
    """کلاینت HTTP با تلاش مجدد، تأخیر نمایی و مدارشکن."""

    def __init__(self, config: DataConfig, *, transport=None) -> None:
        self.config = config
        self._transport = transport or _Transport(config.request_timeout, config.user_agent)
        self._breakers: dict[str, CircuitBreaker] = {}

    # ------------------------------------------------------------ breakers
    def breaker(self, provider: str) -> CircuitBreaker:
        breaker = self._breakers.get(provider)
        if breaker is None:
            breaker = CircuitBreaker(
                provider, self.config.breaker_threshold, self.config.breaker_cooldown
            )
            self._breakers[provider] = breaker
        return breaker

    def breaker_states(self) -> list[dict]:
        return [breaker.snapshot() for breaker in self._breakers.values()]

    # ------------------------------------------------------------- backoff
    def _backoff(self, attempt: int) -> float:
        """تأخیر نمایی با نوسان تصادفی و سقف."""
        base = self.config.backoff_base * (2 ** max(0, attempt - 1))
        capped = min(self.config.backoff_max, base)
        return capped * (0.6 + random.random() * 0.8)

    # ------------------------------------------------------------- request
    def request(self, url: str, *, provider: str) -> HttpResponse:
        """درخواست GET با تلاش مجدد — در شکست نهایی ``ProviderError``."""
        breaker = self.breaker(provider)
        breaker.allow()
        attempts = max(1, self.config.max_attempts)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                status, body, headers = self._transport(url)
            except Exception as error:  # noqa: BLE001 - خطای شبکه/مهلت
                last_error = error
                log.warning("%s: %s attempt %d/%d failed: %s", provider, url, attempt, attempts, error)
                if attempt < attempts:
                    time.sleep(self._backoff(attempt))
                    continue
                breaker.record_failure()
                raise ProviderError(provider, f"network error: {error}") from error

            elapsed_ms = int((time.perf_counter() - started) * 1000)

            if status == 429:
                retry_after = _retry_after(headers)
                breaker.record_failure()
                raise RateLimited(provider, retry_after)

            if status in _RETRY_STATUS and attempt < attempts:
                log.warning("%s: %s returned %d, retrying", provider, url, status)
                time.sleep(self._backoff(attempt))
                continue

            if status >= 400:
                breaker.record_failure()
                raise ProviderError(provider, f"HTTP {status}", retryable=status >= 500)

            breaker.record_success()
            return HttpResponse(status=status, body=body, url=url, elapsed_ms=elapsed_ms)

        breaker.record_failure()
        raise ProviderError(provider, f"all attempts failed: {last_error}")

    def get_json(self, url: str, *, provider: str) -> Any:
        """دریافت و پارس JSON — پاسخ نامعتبر ``MalformedResponse`` می‌دهد."""
        response = self.request(url, provider=provider)
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MalformedResponse(provider, f"invalid JSON: {error}") from error

    def get_text(self, url: str, *, provider: str) -> str:
        """دریافت متن با تشخیص سادهٔ رمزگذاری."""
        response = self.request(url, provider=provider)
        for encoding in ("utf-8", "cp1256", "latin-1"):
            try:
                return response.body.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise MalformedResponse(provider, "undecodable body")


def _retry_after(headers: dict[str, str]) -> float | None:
    """خواندن ``Retry-After`` در صورت وجود."""
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


@dataclass(slots=True)
class ProviderResult:
    """خروجی یک بار واکشی از منبع."""

    name: str
    quotes: dict[str, Quote] = field(default_factory=dict)
    latency_ms: int = 0
    requested: int = 0

    @property
    def missing(self) -> int:
        return max(0, self.requested - len(self.quotes))


class BaseProvider(ABC):
    """قرارداد مشترک همهٔ منابع داده."""

    name = "base"
    #: واحد خام منبع؛ اگر ریال باشد به تومان تبدیل می‌شود
    raw_unit = "toman"

    def __init__(self, http: HttpClient, config: DataConfig) -> None:
        self.http = http
        self.config = config

    @abstractmethod
    def fetch(self, assets: Sequence[Asset]) -> ProviderResult:
        """واکشی قیمت اقلام درخواستی.

        در شکست کامل ``ProviderError`` بالا می‌رود. اقلامی که در پاسخ منبع
        نیستند در خروجی غایب می‌مانند و هرگز مقدار پیش‌فرض نمی‌گیرند.
        """
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """آیا مدارشکن اجازهٔ تلاش می‌دهد؟"""
        return not self.http.breaker(self.name).is_open

    def mark_stale(self, quotes: dict[str, Quote]) -> None:
        """اعمال وضعیت تازگی روی نقل‌قول‌ها."""
        for quote in quotes.values():
            quote.mark_freshness(
                self.config.live_within, self.config.stale_after, self.config.expire_after
            )


__all__ = [
    "BaseProvider",
    "CircuitBreaker",
    "HttpClient",
    "HttpResponse",
    "ProviderResult",
]
