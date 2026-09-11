# -*- coding: utf-8 -*-
"""مدل‌های دامنه.

قاعدهٔ ثابت این لایه: هر عددی که به کاربر می‌رسد باید بداند از کجا آمده و
چقدر تازه است. برای همین ``Quote`` هم‌زمان «زمان مشاهده در منبع»، «زمان
واکشی»، «مبنای تغییر» و «وضعیت تازگی» را حمل می‌کند.
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
            AssetKind.GOLD: "طلا",
            AssetKind.COIN: "سکه",
            AssetKind.CURRENCY: "ارز",
            AssetKind.CRYPTO: "رمزارز",
        }[self]

    @property
    def order(self) -> int:
        return {
            AssetKind.GOLD: 10,
            AssetKind.COIN: 20,
            AssetKind.CURRENCY: 30,
            AssetKind.CRYPTO: 40,
        }[self]


class Freshness(str, Enum):
    """وضعیت تازگی داده."""

    LIVE = "live"
    RECENT = "recent"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            Freshness.LIVE: "زنده",
            Freshness.RECENT: "تازه",
            Freshness.STALE: "کهنه",
            Freshness.EXPIRED: "منقضی",
            Freshness.UNKNOWN: "نامعلوم",
        }[self]

    @property
    def is_usable(self) -> bool:
        """آیا این داده قابل نمایش به‌عنوان قیمت جاری است؟"""
        return self in {Freshness.LIVE, Freshness.RECENT}


@dataclass(slots=True)
class Asset:
    """یک دارایی قابل پایش."""

    slug: str
    title: str
    kind: AssetKind
    unit: str = "toman"
    precision: int = 0
    provider: str = "tgju"
    provider_key: str = ""
    symbol: str = ""

    @property
    def unit_label(self) -> str:
        return "دلار" if self.unit == "usd" else "تومان"

    @property
    def is_crypto(self) -> bool:
        return self.kind is AssetKind.CRYPTO


@dataclass(slots=True)
class Quote:
    """یک نقل‌قول قیمت با فرادادهٔ کامل."""

    slug: str
    price: float
    unit: str = "toman"
    source: str = ""
    observed_at: float = 0.0
    fetched_at: float = 0.0
    day_low: float | None = None
    day_high: float | None = None
    change_abs: float | None = None
    change_pct: float | None = None
    change_basis: str = ""
    freshness: Freshness = Freshness.UNKNOWN
    precision: int = 0
    previous_price: float | None = None
    previous_at: float | None = None

    @property
    def age_seconds(self) -> float:
        """سن داده نسبت به ساعت سیستم."""
        stamp = self.observed_at or self.fetched_at
        return max(0.0, time.time() - stamp) if stamp else float("inf")

    @property
    def is_usable(self) -> bool:
        return self.freshness.is_usable

    @property
    def direction(self) -> int:
        """۱ صعودی، ‎-۱ نزولی، ۰ بی‌تغییر یا نامعلوم."""
        if self.change_pct is None:
            return 0
        if self.change_pct > 0:
            return 1
        if self.change_pct < 0:
            return -1
        return 0

    def mark_freshness(self, live_within: int, stale_after: int, expire_after: int) -> None:
        """تعیین وضعیت تازگی از روی سن داده — بدون هیچ حدس."""
        age = self.age_seconds
        if age == float("inf"):
            self.freshness = Freshness.UNKNOWN
        elif age <= live_within:
            self.freshness = Freshness.LIVE
        elif age <= stale_after:
            self.freshness = Freshness.RECENT
        elif age <= expire_after:
            self.freshness = Freshness.STALE
        else:
            self.freshness = Freshness.EXPIRED

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "price": self.price,
            "unit": self.unit,
            "precision": self.precision,
            "source": self.source,
            "observed_at": self.observed_at or None,
            "fetched_at": self.fetched_at or None,
            "day_low": self.day_low,
            "day_high": self.day_high,
            "previous_price": self.previous_price,
            "previous_at": self.previous_at,
            "change_abs": self.change_abs,
            "change_pct": self.change_pct,
            "change_basis": self.change_basis,
            "direction": self.direction,
            "freshness": self.freshness.value,
            "is_usable": self.is_usable,
        }


def clone_quote(quote: Quote) -> Quote:
    """کپی مستقل تا دست‌کاری وضعیت تازگی روی نسخهٔ کش‌شده اثر نگذارد."""
    return Quote(
        slug=quote.slug,
        price=quote.price,
        unit=quote.unit,
        source=quote.source,
        observed_at=quote.observed_at,
        fetched_at=quote.fetched_at,
        day_low=quote.day_low,
        day_high=quote.day_high,
        change_abs=quote.change_abs,
        change_pct=quote.change_pct,
        change_basis=quote.change_basis,
        freshness=quote.freshness,
        precision=quote.precision,
        previous_price=quote.previous_price,
        previous_at=quote.previous_at,
    )


@dataclass(slots=True)
class SeriesPoint:
    """یک نقطهٔ سری زمانی."""

    ts: float
    price: float
    samples: int = 1

    def to_dict(self) -> dict:
        return {"ts": self.ts, "price": self.price, "samples": self.samples}


@dataclass(slots=True)
class SourceStatus:
    """وضعیت آخرین تلاش یک منبع داده."""

    name: str
    ok: bool
    latency_ms: int = 0
    items: int = 0
    error: str = ""
    checked_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "items": self.items,
            "error": self.error or None,
            "checked_at": self.checked_at or None,
        }


@dataclass(slots=True)
class MarketSnapshot:
    """مجموعهٔ نقل‌قول‌ها در یک لحظه."""

    quotes: dict[str, Quote] = field(default_factory=dict)
    statuses: list[SourceStatus] = field(default_factory=list)
    from_cache: bool = False
    fetched_at: float = 0.0
    missing: list[str] = field(default_factory=list)

    def get(self, slug: str) -> Quote | None:
        return self.quotes.get(slug)

    def to_dict(self) -> dict:
        return {
            "quotes": {slug: q.to_dict() for slug, q in self.quotes.items()},
            "statuses": [s.to_dict() for s in self.statuses],
            "from_cache": self.from_cache,
            "fetched_at": self.fetched_at or None,
            "missing": self.missing,
        }


class AlertKind(str, Enum):
    """نوع قاعدهٔ هشدار."""

    ABOVE = "above"
    BELOW = "below"
    PCT_MOVE = "pct_move"

    @property
    def label(self) -> str:
        return {
            AlertKind.ABOVE: "بالاتر از",
            AlertKind.BELOW: "پایین‌تر از",
            AlertKind.PCT_MOVE: "نوسان بیش از (٪)",
        }[self]


class AlertStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"

    @property
    def label(self) -> str:
        return "فعال" if self is AlertStatus.ACTIVE else "متوقف"


@dataclass(slots=True)
class AlertRule:
    """قاعدهٔ هشدار یک کاربر."""

    id: int
    slug: str
    kind: AlertKind
    threshold: float
    status: AlertStatus = AlertStatus.ACTIVE
    one_shot: bool = False
    cooldown_seconds: int = 0
    note: str = ""
    created_at: float = 0.0
    last_fired_at: float | None = None
    last_price: float | None = None
    fired_count: int = 0
    owner: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "kind": self.kind.value,
            "kind_label": self.kind.label,
            "threshold": self.threshold,
            "status": self.status.value,
            "status_label": self.status.label,
            "one_shot": self.one_shot,
            "cooldown_seconds": self.cooldown_seconds,
            "note": self.note or None,
            "created_at": self.created_at or None,
            "last_fired_at": self.last_fired_at,
            "last_price": self.last_price,
            "fired_count": self.fired_count,
            "owner": self.owner or None,
        }


@dataclass(slots=True)
class AlertEvent:
    """یک رخداد هشدار (وقوع یا مهارشدن)."""

    id: int
    rule_id: int | None
    slug: str
    kind: str
    price: float
    threshold: float
    message: str
    created_at: float
    suppressed: bool = False
    reason: str = ""
    owner: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "slug": self.slug,
            "kind": self.kind,
            "price": self.price,
            "threshold": self.threshold,
            "message": self.message,
            "created_at": self.created_at or None,
            "suppressed": self.suppressed,
            "reason": self.reason or None,
            "owner": self.owner or None,
        }


@dataclass(slots=True)
class HistoryRange:
    """یک بازهٔ زمانی قابل انتخاب برای نمودار."""

    key: str
    label: str
    seconds: int
    bucket_seconds: int
    max_points: int


__all__ = [
    "AlertEvent",
    "AlertKind",
    "AlertRule",
    "AlertStatus",
    "Asset",
    "AssetKind",
    "Freshness",
    "HistoryRange",
    "MarketSnapshot",
    "Quote",
    "SeriesPoint",
    "SourceStatus",
    "clone_quote",
]
