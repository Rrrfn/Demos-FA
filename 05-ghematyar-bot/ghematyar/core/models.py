# -*- coding: utf-8 -*-
"""مدل‌های دامنه — مستقل از تلگرام و از ارائه‌دهندهٔ داده.

هر «Quote» یک مشاهدهٔ قیمت با مبدأ و زمان مشخص است. تفکیک صریح
``source``، ``observed_at`` و ``fetched_at`` باعث می‌شود لایهٔ نمایش
هیچ‌وقت نداند و نتواند داده‌ای را به‌جای live جا بزند.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class AssetKind(str, Enum):
    """دستهٔ دارایی."""

    GOLD = "gold"
    COIN = "coin"
    CURRENCY = "currency"
    CRYPTO = "crypto"

    @property
    def label(self) -> str:
        return {
            "gold": "طلا",
            "coin": "سکه",
            "currency": "ارز",
            "crypto": "رمزارز",
        }[self.value]


class Freshness(str, Enum):
    """وضعیت تازگی داده — مبنای صداقت نمایش."""

    LIVE = "live"          # تازه، در بازهٔ مجاز
    STALE = "stale"        # قابل نمایش، ولی کهنه؛ باید برچسب بخورد
    UNAVAILABLE = "unavailable"  # غیرقابل استفاده؛ نمایش داده نمی‌شود

    @property
    def label(self) -> str:
        return {
            "live": "زنده",
            "stale": "کهنه",
            "unavailable": "دردسترس نیست",
        }[self.value]


@dataclass(slots=True)
class Quote:
    """یک مشاهدهٔ قیمت با مبدأ، زمان و وضعیت تازگی."""

    slug: str
    price: float
    unit: str = "toman"                     # toman | usd
    source: str = ""                        # tgju | coingecko | er-api | ...
    observed_at: float = field(default_factory=time.time)   # زمان داده نزد منبع
    fetched_at: float = field(default_factory=time.time)    # زمان دریافت ما
    day_low: float | None = None
    day_high: float | None = None
    change_abs: float | None = None         # تغییر مطلق
    change_pct: float | None = None         # درصد تغییر
    change_basis: str = ""                  # توضیح صریح مبنای تغییر
    freshness: Freshness = Freshness.LIVE
    decimals: int = 0

    # ---------------------------------------------------------------- derived
    @property
    def age_seconds(self) -> float:
        """چند ثانیه از زمان دریافت این مشاهده گذشته است."""
        return max(0.0, time.time() - self.fetched_at)

    @property
    def source_age_seconds(self) -> float:
        """چند ثانیه از زمان داده نزد منبع گذشته است."""
        return max(0.0, time.time() - self.observed_at)

    @property
    def is_usable(self) -> bool:
        """آیا قیمت قابل نمایش است؟"""
        return self.freshness is not Freshness.UNAVAILABLE and self.price > 0

    @property
    def direction(self) -> int:
        """۱ صعودی، ‎-۱ نزولی، ۰ بدون تغییر."""
        if self.change_abs is None or self.change_abs == 0:
            return 0
        return 1 if self.change_abs > 0 else -1

    def mark_stale(self, age_limit: float, expire_limit: float) -> "Quote":
        """وضعیت تازگی را بر پایهٔ سن داده به‌روز می‌کند."""
        age = self.age_seconds
        if age >= expire_limit:
            self.freshness = Freshness.UNAVAILABLE
        elif age >= age_limit:
            self.freshness = Freshness.STALE
        else:
            self.freshness = Freshness.LIVE
        return self

    def to_dict(self) -> dict:
        """نمایش ساختاریافته (برای لاگ و API)."""
        return {
            "slug": self.slug,
            "price": self.price,
            "unit": self.unit,
            "source": self.source,
            "observed_at": self.observed_at,
            "fetched_at": self.fetched_at,
            "change_abs": self.change_abs,
            "change_pct": self.change_pct,
            "change_basis": self.change_basis,
            "freshness": self.freshness.value,
            "age_seconds": round(self.age_seconds, 1),
        }


@dataclass(slots=True)
class ProviderStatus:
    """وضعیت سلامت یک ارائه‌دهنده — برای شفافیت و /status."""

    name: str
    ok: bool
    latency_ms: int
    items: int = 0
    error: str = ""
    at: float = field(default_factory=time.time)


@dataclass(slots=True)
class MarketSnapshot:
    """نتیجهٔ یک تلاش برای دریافت بازار."""

    quotes: dict[str, Quote] = field(default_factory=dict)
    statuses: list[ProviderStatus] = field(default_factory=list)
    from_cache: bool = False
    fetched_at: float = field(default_factory=time.time)

    def __bool__(self) -> bool:
        return bool(self.quotes)

    def get(self, slug: str) -> Quote | None:
        return self.quotes.get(slug)

    @property
    def missing(self) -> list[str]:
        return []

    def sources(self) -> list[str]:
        """فهرست مبدأهایی که واقعاً داده دادند."""
        return sorted({q.source for q in self.quotes.values() if q.source})

    def freshness(self) -> Freshness:
        """بدترین وضعیت تازگی در میان نقل‌قول‌ها."""
        if not self.quotes:
            return Freshness.UNAVAILABLE
        if any(q.freshness is Freshness.LIVE for q in self.quotes.values()):
            return Freshness.LIVE
        if any(q.freshness is Freshness.STALE for q in self.quotes.values()):
            return Freshness.STALE
        return Freshness.UNAVAILABLE


@dataclass(slots=True)
class PricePoint:
    """یک نقطهٔ تاریخچه — همان چیزی که در پایگاه داده ذخیره می‌شود."""

    slug: str
    price: float
    source: str
    captured_at: float
    unit: str = "toman"

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "price": self.price,
            "source": self.source,
            "captured_at": self.captured_at,
            "unit": self.unit,
        }
