# -*- coding: utf-8 -*-
"""دست‌آویزهای تست — انتقال‌دهندهٔ جعلی و منبع اسکریپتی.

هیچ تستی به شبکه نمی‌زند. پاسخ‌های واقعی منابع یک‌بار ضبط شده‌اند
(``tests/fixtures``) و انتقال‌دهندهٔ جعلی همان‌ها را سرو می‌کند؛ بنابراین
آزمون‌ها هم واقع‌گرا هستند و هم تکرارپذیر.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Sequence

from cheshmbaz.config import DataConfig
from cheshmbaz.core.models import Asset, Quote
from cheshmbaz.providers.base import BaseProvider, HttpClient, ProviderResult

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> bytes:
    """خواندن یک فیکسچر خام."""
    return (FIXTURES / name).read_bytes()


def load_json_fixture(name: str) -> Any:
    """خواندن یک فیکسچر JSON."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeTransport:
    """انتقال‌دهندهٔ جعلی: نقشهٔ زیررشتهٔ نشانی → صف پاسخ.

    ``add`` یک پاسخ ثابت ثبت می‌کند و ``add_sequence`` چند پاسخ پشت‌سرهم
    (آخرین تکرار می‌شود) تا مسیر «۵۰۰ موقت، سپس موفقیت» قابل آزمون باشد.
    ``fail`` خطای شبکه را برای چند درخواست اول شبیه‌سازی می‌کند.
    """

    def __init__(self) -> None:
        self.queues: dict[str, list[tuple[int, bytes, dict]]] = {}
        self.failures: dict[str, int] = {}
        self.calls: list[str] = []
        self.raised: list[str] = []

    # -------------------------------------------------------------- recording
    def add(self, needle: str, *, status: int = 200, body: bytes = b"", headers=None) -> "FakeTransport":
        self.queues[needle] = [(status, body, headers or {})]
        return self

    def add_sequence(self, needle: str, responses: list[tuple[int, bytes]]) -> "FakeTransport":
        """چند پاسخ پشت‌سرهم؛ آخرین پاسخ برای درخواست‌های بعدی تکرار می‌شود."""
        self.queues[needle] = [(status, body, {}) for status, body in responses]
        return self

    def add_json(self, needle: str, payload: Any, *, status: int = 200) -> "FakeTransport":
        return self.add(
            needle, status=status,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    def fail(self, needle: str, times: int = 1) -> "FakeTransport":
        """اولین ``times`` درخواست منطبق با خطای شبکه شکست می‌خورد."""
        self.failures[needle] = times
        return self

    # ----------------------------------------------------------------- calling
    def __call__(self, url: str):
        self.calls.append(url)
        for needle, remaining in list(self.failures.items()):
            if needle in url and remaining > 0:
                self.failures[needle] = remaining - 1
                self.raised.append(url)
                raise OSError("simulated network failure")
        for needle, queue in self.queues.items():
            if needle in url and queue:
                if len(queue) > 1:
                    return queue.pop(0)
                return queue[0]
        raise OSError(f"no route for {url}")


def http_with(transport: FakeTransport, config: DataConfig | None = None) -> HttpClient:
    """کلاینت با تأخیر نمایی بسیار کوچک تا تست‌ها سریع بمانند."""
    cfg = config or DataConfig(max_attempts=3, backoff_base=0.001, backoff_max=0.002)
    return HttpClient(cfg, transport=transport)


class ScriptedProvider(BaseProvider):
    """منبعی که رفتارش را تست تعیین می‌کند."""

    def __init__(
        self,
        name: str,
        http: HttpClient,
        config: DataConfig,
        *,
        prices: dict[str, float] | None = None,
        error: Exception | None = None,
        latency_ms: int = 1,
        observed_offset: float = 0.0,
        change_pct: dict[str, float] | None = None,
    ) -> None:
        super().__init__(http, config)
        self.name = name
        self.prices = prices or {}
        self.error = error
        self.latency_ms = latency_ms
        self.observed_offset = observed_offset
        self.change_pct = change_pct or {}

    def fetch(self, assets: Sequence[Asset]) -> ProviderResult:
        if self.error is not None:
            raise self.error
        stamp = time.time() + self.observed_offset
        quotes: dict[str, Quote] = {}
        for asset in assets:
            price = self.prices.get(asset.slug)
            if price is None:
                continue
            pct = self.change_pct.get(asset.slug)
            quotes[asset.slug] = Quote(
                slug=asset.slug, price=price, unit=asset.unit, source=f"{self.name}.test",
                observed_at=stamp, fetched_at=stamp, precision=asset.precision,
                change_pct=pct, change_basis="تست" if pct is not None else "",
            )
        self.mark_stale(quotes)
        return ProviderResult(
            name=self.name, quotes=quotes, latency_ms=self.latency_ms, requested=len(assets)
        )


__all__ = [
    "FIXTURES",
    "FakeTransport",
    "ScriptedProvider",
    "http_with",
    "load_fixture",
    "load_json_fixture",
]
