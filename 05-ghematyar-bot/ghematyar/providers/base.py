# -*- coding: utf-8 -*-
"""زیرساخت ارائه‌دهنده‌ها — کلاینت HTTP مقاوم و مدارشکن.

اصول:

* **timeout** روی هر درخواست، تا یک منبع کند کل ربات را معطل نکند.
* **retry با backoff نمایی و jitter** برای خطاهای گذرا (۵xx، شبکه، timeout).
* **احترام به Retry-After** در پاسخ ۴۲۹.
* **مدارشکن** تا وقتی منبعی پیوسته خطا می‌دهد، درخواست‌ها بی‌فایده
  پشت سر هم فرستاده نشوند و کاربر معطل نماند.
* **پاسخ نامعتبر** خطای صریح است، نه لیست خالی.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Protocol, Sequence

import aiohttp

from ..config import DataConfig
from ..core.errors import CircuitOpen, MalformedResponse, ProviderError, RateLimited
from ..core.models import Quote

log = logging.getLogger("ghematyar.providers")


class CircuitBreaker:
    """مدارشکن سادهٔ per-provider.

    پس از ``threshold`` خطای پیوسته باز می‌شود و تا ``cooldown`` ثانیه
    درخواست‌ها را سریع رد می‌کند (fail-fast) — بهتر از انتظار برای timeout.
    """

    def __init__(self, name: str, threshold: int, cooldown: float) -> None:
        self.name = name
        self.threshold = max(1, threshold)
        self.cooldown = max(0.0, cooldown)
        self._failures = 0
        self._opened_at = 0.0

    @property
    def failures(self) -> int:
        return self._failures

    def is_open(self) -> bool:
        """آیا مدار بسته است؟ اگر مدت سرد شدن تمام شده باشد، نیمه‌باز می‌شود."""
        if self._opened_at == 0.0:
            return False
        if time.monotonic() - self._opened_at >= self.cooldown:
            # اجازهٔ یک تلاش آزمایشی
            self._opened_at = 0.0
            self._failures = 0
            return False
        return True

    def remaining(self) -> float:
        if self._opened_at == 0.0:
            return 0.0
        return max(0.0, self.cooldown - (time.monotonic() - self._opened_at))

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = time.monotonic()
            log.warning(
                "circuit opened for %s after %d failures (cooldown %.0fs)",
                self.name, self._failures, self.cooldown,
            )

    def guard(self) -> None:
        """در صورت باز بودن مدار، خطا می‌دهد."""
        if self.is_open():
            raise CircuitOpen(self.name, self.remaining())


class HttpClient:
    """کلاینت HTTP مشترک با retry و backoff نمایی."""

    def __init__(self, config: DataConfig) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def session(self) -> aiohttp.ClientSession:
        """نشست مشترک aiohttp (تنبل ساخته می‌شود)."""
        async with self._lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
                    headers={
                        "User-Agent": self.config.user_agent,
                        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                    },
                )
            return self._session

    async def close(self) -> None:
        """بستن نشست."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def fetch(
        self,
        url: str,
        *,
        provider: str = "",
        as_json: bool = True,
        attempts: int | None = None,
    ) -> Any:
        """یک URL را با retry می‌گیرد و JSON یا متن برمی‌گرداند.

        در پایان تلاش‌ها، آخرین خطا به‌شکل :class:`ProviderError` بالا
        می‌رود؛ هرگز مقدار ساختگی برگردانده نمی‌شود.
        """
        provider = provider or url
        attempts = attempts or self.config.max_attempts
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                session = await self.session()
                async with session.get(url) as response:
                    if response.status == 429:
                        retry_after = _retry_after(response)
                        raise RateLimited(provider, retry_after)
                    if response.status >= 500:
                        raise ProviderError(provider, f"server error {response.status}")
                    if response.status >= 400:
                        # ۴xx غیر از ۴۲۹ قابل تکرار نیست
                        raise ProviderError(
                            provider, f"client error {response.status}", retryable=False
                        )
                    if as_json:
                        try:
                            return await response.json(content_type=None)
                        except Exception as exc:  # noqa: BLE001
                            raise MalformedResponse(provider, f"invalid JSON: {exc}") from exc
                    return await response.text()
            except (asyncio.TimeoutError,) as exc:
                last_error = ProviderError(provider, "timeout")
                log.warning("%s attempt %d/%d timed out", provider, attempt, attempts)
                _ = exc
            except aiohttp.ClientError as exc:
                last_error = ProviderError(provider, f"network error: {exc}")
                log.warning("%s attempt %d/%d failed: %s", provider, attempt, attempts, exc)
            except RateLimited as exc:
                last_error = exc
                wait = exc.retry_after if exc.retry_after is not None else self._backoff(attempt)
                log.warning("%s rate limited; waiting %.1fs", provider, wait)
                if attempt < attempts:
                    await asyncio.sleep(wait)
                continue
            except ProviderError as exc:
                last_error = exc
                if not exc.retryable:
                    raise
                log.warning("%s attempt %d/%d: %s", provider, attempt, attempts, exc.message)
            except Exception as exc:  # noqa: BLE001
                last_error = ProviderError(provider, f"unexpected error: {exc}")
                log.warning("%s attempt %d/%d unexpected: %s", provider, attempt, attempts, exc)

            if attempt < attempts:
                await asyncio.sleep(self._backoff(attempt))

        assert last_error is not None
        if isinstance(last_error, ProviderError):
            raise last_error
        raise ProviderError(provider, str(last_error))

    def _backoff(self, attempt: int) -> float:
        """تأخیر نمایی با jitter — تا چند کلاینت هم‌زمان به منبع نکوبند."""
        raw = self.config.backoff_base * (2 ** (attempt - 1))
        capped = min(raw, self.config.backoff_max)
        return capped * (0.5 + random.random() / 2)


def _retry_after(response: aiohttp.ClientResponse) -> float | None:
    """خواندن هدر Retry-After در صورت وجود."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


class MarketProvider(Protocol):
    """قرارداد یک ارائه‌دهندهٔ داده.

    هر ارائه‌دهنده فقط برای دارایی‌هایی که در فهرستش هستند نقل‌قول
    برمی‌گرداند؛ نبود یک قلم در خروجی یعنی «این منبع آن را ندارد».
    """

    name: str

    async def fetch(self, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
        """دریافت نقل‌قول‌ها. در خطا استثنای دامنه می‌دهد."""
        ...


class BaseProvider:
    """پایهٔ مشترک ارائه‌دهنده‌ها — مدارشکن و کلاینت را تأمین می‌کند."""

    name = "base"

    def __init__(
        self,
        client: HttpClient,
        config: DataConfig,
        *,
        needs: Sequence[str] | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.breaker = CircuitBreaker(
            self.name, config.breaker_threshold, config.breaker_cooldown
        )
        self.last_error: str = ""
        self.last_latency_ms: int = 0

    async def fetch(self, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
        """قالب: مدارشکن را می‌سنجد، کار را انجام می‌دهد و نتیجه را ثبت می‌کند."""
        self.breaker.guard()
        started = time.perf_counter()
        try:
            quotes = await self._fetch(slugs)
        except Exception:
            self.breaker.record_failure()
            raise
        finally:
            self.last_latency_ms = int((time.perf_counter() - started) * 1000)
        if not quotes:
            # پاسخ خالی برای یک منبع بازار یعنی «دادهٔ قابل استفاده ندارد»
            self.breaker.record_failure()
            self.last_error = "no usable quotes"
            raise ProviderError(self.name, "no usable quotes")
        self.breaker.record_success()
        self.last_error = ""
        return quotes

    async def _fetch(self, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """آیا مدار بسته است (منبع قابل استفاده)؟"""
        return not self.breaker.is_open()
