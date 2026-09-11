# -*- coding: utf-8 -*-
"""سرویس بازار — لایهٔ خواندن و شکل‌دهی داده برای رابط و API.

قاعده‌ای که همه‌چیز را می‌سازد:

**وضعیت تازگی در زمان خواندن تعیین می‌شود، نه در زمان نوشتن.** اگر برچسب
تازگی هنگام ذخیره ثابت می‌شد، قیمت ۳۰ دقیقه پیش تا ابد «زنده» می‌ماند. این‌جا
هر بار سن داده محاسبه و برچسب تازه می‌شود؛ نتیجه اینکه قیمت کهنه هرگز به‌عنوان
قیمت زنده نمایش داده نمی‌شود و ``is_usable`` برای دادهٔ منقضی نادرست است.

تغییر هم دو مسیر دارد: اگر منبع درصد را داده باشد (رمزارز) همان استفاده
می‌شود؛ وگرنه از تاریخچهٔ ثبت‌شدهٔ خودمان محاسبه می‌شود. اگر مرجعی نباشد،
درصد ``None`` می‌ماند و رابط «—» نشان می‌دهد — هیچ‌وقت صفر یا عدد ساختگی.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..assets import ASSETS, KIND_ORDER, all_assets_ordered, by_kind, get, search
from ..config import Config
from ..core.formatting import fa_duration, fa_number, fa_percent, fa_price, fa_signed, arrow
from ..core.models import (
    Asset,
    AssetKind,
    Freshness,
    MarketSnapshot,
    Quote,
    SourceStatus,
    clone_quote,
)
from ..storage import Storage, resolve_range
from .collector import CHANGE_WINDOW_SECONDS, Collector, CollectionResult

#: پنجرهٔ محاسبهٔ «بیشترین تغییرها»
MOVER_WINDOWS: dict[str, tuple[str, int]] = {
    "1D": ("۲۴ ساعت", 86_400),
    "7D": ("۷ روز", 604_800),
    "30D": ("۳۰ روز", 2_592_000),
}


@dataclass(slots=True)
class CacheEntry:
    """یک مقدار کش‌شده همراه با زمان انقضا."""

    value: object
    expires_at: float


@dataclass(slots=True)
class MarketService:
    """خواندن، تازه‌سازی و شکل‌دهی دادهٔ بازار."""

    config: Config
    storage: Storage
    collector: Collector
    _cache: dict[str, CacheEntry] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ cache
    def _cache_get(self, key: str):
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return entry.value

    def _cache_put(self, key: str, value, ttl: int | None = None):
        ttl = self.config.api.cache_seconds if ttl is None else ttl
        self._cache[key] = CacheEntry(value=value, expires_at=time.time() + ttl)
        return value

    def invalidate(self) -> None:
        """خالی‌کردن کش — بعد از هر جمع‌آوری موفق."""
        self._cache.clear()

    # --------------------------------------------------------------- decorate
    def _decorate(self, quote: Quote) -> Quote:
        """نسخهٔ خواندنی یک نقل‌قول: تازگی تازه، تغییر کامل‌شده."""
        item = clone_quote(quote)
        if item.change_pct is None:
            self._fill_change_from_history(item)
        item.mark_freshness(
            self.config.data.live_within,
            self.config.data.stale_after,
            self.config.data.expire_after,
        )
        return item

    def _fill_change_from_history(self, quote: Quote) -> None:
        """تلاش برای کامل‌کردن تغییر از تاریخچه — بدون ساختن عدد."""
        reference = self.storage.history.reference(quote.slug, seconds=CHANGE_WINDOW_SECONDS)
        if reference is None:
            return
        previous_price, previous_at = reference
        if previous_price <= 0 or quote.price <= 0:
            return
        change = quote.price - previous_price
        quote.previous_price = previous_price
        quote.previous_at = previous_at
        quote.change_abs = change
        quote.change_pct = (change / previous_price) * 100.0
        quote.change_basis = quote.change_basis or "۲۴ ساعته (تاریخچهٔ ثبت‌شده)"

    # ---------------------------------------------------------------- snapshot
    def quotes(self, *, only_usable: bool = False) -> dict[str, Quote]:
        """همهٔ نقل‌قول‌های ذخیره‌شده با تازگی محاسبه‌شده."""
        cached = self._cache_get("quotes")
        if cached is None:
            stored = self.storage.quotes.all()
            decorated = {slug: self._decorate(quote) for slug, quote in stored.items()}
            cached = self._cache_put("quotes", decorated)
        if only_usable:
            return {slug: quote for slug, quote in cached.items() if quote.is_usable}
        return dict(cached)

    def snapshot(self, *, refresh: bool = False) -> MarketSnapshot:
        """نمای لحظه‌ای بازار.

        ``refresh=True`` یک دور جمع‌آوری تازه اجرا می‌کند؛ در غیر این صورت
        آخرین دادهٔ ذخیره‌شده با تازگی بازمحاسبه‌شده برگردانده می‌شود — نه یک
        قیمت ساختگی.
        """
        if refresh:
            result = self.collector.collect()
            self.invalidate()
        else:
            result = None

        quotes = self.quotes()
        missing = [asset.slug for asset in all_assets_ordered() if asset.slug not in quotes]
        statuses = self.storage.sources.latest()
        has_live = any(quote.is_usable for quote in quotes.values())
        return MarketSnapshot(
            quotes=quotes,
            statuses=statuses or [],
            from_cache=result is None,
            fetched_at=time.time(),
            missing=missing if not has_live else [],
        )

    def refresh(self) -> CollectionResult:
        """جمع‌آوری دستی — خروجی کامل برای شفافیت در رابط."""
        result = self.collector.collect()
        self.invalidate()
        return result

    # ------------------------------------------------------------------- cards
    def card(self, slug: str, *, quotes: dict[str, Quote] | None = None) -> dict:
        """کارت یک دارایی — همهٔ اعدادی که رابط نیاز دارد."""
        asset = get(slug)
        pool = quotes if quotes is not None else self.quotes()
        quote = pool.get(slug)
        if quote is None:
            return self._empty_card(asset)
        return self._card_from(asset, quote)

    def _empty_card(self, asset: Asset) -> dict:
        """کارت بدون داده — صریح و بدون جای‌نگهدار عددی."""
        return {
            "slug": asset.slug,
            "title": asset.title,
            "kind": asset.kind.value,
            "kind_label": asset.kind.label,
            "symbol": asset.symbol,
            "unit": asset.unit,
            "unit_label": asset.unit_label,
            "precision": asset.precision,
            "price": None,
            "price_text": "—",
            "change_abs": None,
            "change_pct": None,
            "change_pct_text": "—",
            "change_abs_text": "—",
            "change_basis": None,
            "direction": 0,
            "arrow": "•",
            "source": None,
            "observed_at": None,
            "fetched_at": None,
            "age_seconds": None,
            "age_text": "—",
            "freshness": Freshness.UNKNOWN.value,
            "freshness_label": Freshness.UNKNOWN.label,
            "is_usable": False,
            "has_data": False,
            "day_low": None,
            "day_high": None,
            "day_low_text": "—",
            "day_high_text": "—",
            "previous_price": None,
        }

    def _card_from(self, asset: Asset, quote: Quote) -> dict:
        price_text = fa_price(quote.price, quote.unit, asset.precision)
        return {
            "slug": asset.slug,
            "title": asset.title,
            "kind": asset.kind.value,
            "kind_label": asset.kind.label,
            "symbol": asset.symbol,
            "unit": quote.unit,
            "unit_label": "دلار" if quote.unit == "usd" else "تومان",
            "precision": asset.precision,
            "price": quote.price,
            "price_text": price_text,
            "change_abs": quote.change_abs,
            "change_pct": quote.change_pct,
            "change_pct_text": fa_percent(quote.change_pct),
            "change_abs_text": (
                fa_signed(quote.change_abs, asset.precision)
                if quote.change_abs is not None
                else "—"
            ),
            "change_basis": quote.change_basis or None,
            "direction": quote.direction,
            "arrow": arrow(quote.direction),
            "source": quote.source or None,
            "observed_at": quote.observed_at or None,
            "fetched_at": quote.fetched_at or None,
            "age_seconds": None if quote.age_seconds == float("inf") else round(quote.age_seconds, 1),
            "age_text": fa_duration(None if quote.age_seconds == float("inf") else quote.age_seconds),
            "freshness": quote.freshness.value,
            "freshness_label": quote.freshness.label,
            "is_usable": quote.is_usable,
            "has_data": True,
            "day_low": quote.day_low,
            "day_high": quote.day_high,
            "day_low_text": fa_price(quote.day_low, quote.unit, asset.precision),
            "day_high_text": fa_price(quote.day_high, quote.unit, asset.precision),
            "previous_price": quote.previous_price,
        }

    # ---------------------------------------------------------------- overview
    def overview(self) -> dict:
        """نمای کلی: گروه‌بندی‌شده بر پایهٔ دسته، به‌همراه وضعیت منابع."""
        quotes = self.quotes()
        groups = []
        for kind in KIND_ORDER:
            assets = by_kind(kind)
            cards = [self.card(asset.slug, quotes=quotes) for asset in assets]
            groups.append({
                "kind": kind.value,
                "label": kind.label,
                "count": len(cards),
                "with_data": sum(1 for card in cards if card["has_data"]),
                "assets": cards,
            })

        from ..assets import FEATURED

        featured = [self.card(slug, quotes=quotes) for slug in FEATURED if slug in ASSETS]
        usable = [quote for quote in quotes.values() if quote.is_usable]
        gainers, losers = self._movers_from(quotes, window_seconds=CHANGE_WINDOW_SECONDS)

        return {
            "generated_at": time.time(),
            "groups": groups,
            "featured": featured,
            "totals": {
                "assets": len(ASSETS),
                "with_data": len(quotes),
                "usable": len(usable),
                "missing": len(ASSETS) - len(quotes),
                "moving": sum(1 for quote in quotes.values() if quote.change_pct not in (None, 0)),
                "gainers": sum(1 for quote in quotes.values() if quote.direction > 0),
                "losers": sum(1 for quote in quotes.values() if quote.direction < 0),
            },
            "movers": {
                "window": "1D",
                "gainers": gainers,
                "losers": losers,
            },
            "sources": [status.to_dict() for status in self.storage.sources.latest()],
            "database": self.storage.stats(),
            "history": self.storage.history.stats(),
        }

    # ------------------------------------------------------------------ movers
    def _change_over(self, quote: Quote, window_seconds: int) -> float | None:
        """درصد تغییر یک قلم در یک بازهٔ مشخص — بدون ساختن عدد.

        اگر بازه همان پنجرهٔ پیش‌فرض باشد، درصد خودِ منبع (رمزارز) اولویت دارد؛
        برای بازه‌های دیگر، مرجع از تاریخچهٔ ثبت‌شدهٔ خودمان خوانده می‌شود. اگر
        مرجعی نباشد ``None`` برمی‌گردد تا آن قلم از فهرست حذف شود، نه اینکه
        با عدد نادرست بیاید.
        """
        if window_seconds == CHANGE_WINDOW_SECONDS and quote.change_pct is not None:
            return quote.change_pct
        reference = self.storage.history.reference(quote.slug, seconds=window_seconds)
        if reference is None:
            return None
        previous_price, _ = reference
        if previous_price <= 0 or quote.price <= 0:
            return None
        return ((quote.price - previous_price) / previous_price) * 100.0

    def _movers_from(
        self, quotes: dict[str, Quote], *, window_seconds: int, limit: int = 5
    ) -> tuple[list[dict], list[dict]]:
        """پرشتاب‌ترین صعودها و نزول‌ها — فقط از درصدهای واقعی همان بازه."""
        ranked: list[tuple[str, Quote, float]] = []
        for slug, quote in quotes.items():
            if not quote.is_usable:
                continue
            change = self._change_over(quote, window_seconds)
            if change is None:
                continue
            ranked.append((slug, quote, change))
        ranked.sort(key=lambda item: item[2], reverse=True)
        gainers = [
            self._mover_entry(slug, quote, change)
            for slug, quote, change in ranked if change > 0
        ][:limit]
        losers = [
            self._mover_entry(slug, quote, change)
            for slug, quote, change in reversed(ranked) if change < 0
        ][:limit]
        return gainers, losers

    def _mover_entry(self, slug: str, quote: Quote, change_pct: float) -> dict:
        asset = ASSETS.get(slug)
        direction = 1 if change_pct > 0 else (-1 if change_pct < 0 else 0)
        return {
            "slug": slug,
            "title": asset.title if asset else slug,
            "symbol": asset.symbol if asset else "",
            "kind": asset.kind.value if asset else "",
            "price_text": fa_price(quote.price, quote.unit, asset.precision if asset else 0),
            "change_pct": change_pct,
            "change_pct_text": fa_percent(change_pct),
            "direction": direction,
            "arrow": arrow(direction),
            "freshness": quote.freshness.value,
        }

    def movers(self, *, window: str = "1D", limit: int = 5) -> dict:
        """بیشترین تغییرها در یک بازه.

        کلید ناشناخته به بازهٔ پیش‌فرض می‌افتد و همان کلید مؤثر هم گزارش
        می‌شود؛ رابط نباید برچسب بازه‌ای را نشان دهد که محاسبه نشده است.
        """
        key = (window or "1D").strip().upper()
        if key not in MOVER_WINDOWS:
            key = "1D"
        label, seconds = MOVER_WINDOWS[key]
        quotes = self.quotes()
        gainers, losers = self._movers_from(quotes, window_seconds=seconds, limit=limit)
        return {
            "window": key,
            "window_label": label,
            "gainers": gainers,
            "losers": losers,
        }

    # ------------------------------------------------------------------ series
    def series(self, slug: str, *, range_key: str | None = None) -> dict:
        """سری زمانی یک دارایی از دادهٔ واقعی پایگاه داده."""
        asset = get(slug)
        window, points = self.storage.history.series(slug, range_key=range_key)
        coverage = self.storage.history.coverage(slug)
        payload_points = [
            {
                "ts": point.ts,
                "price": point.price,
                "price_text": fa_number(point.price, asset.precision),
                "samples": point.samples,
            }
            for point in points
        ]
        return {
            "slug": slug,
            "title": asset.title,
            "unit": asset.unit,
            "unit_label": asset.unit_label,
            "precision": asset.precision,
            "range": window.key,
            "range_label": window.label,
            "points": payload_points,
            "count": len(payload_points),
            "has_data": len(payload_points) >= 2,
            "coverage": coverage,
            "ranges": self.storage.history.available_ranges(slug),
        }

    def ranges(self, slug: str | None = None) -> list[dict]:
        """بازه‌های نمودار — کلی یا برای یک دارایی."""
        from ..storage import RANGES

        if slug is None:
            return [
                {"key": item.key, "label": item.label, "seconds": item.seconds, "has_data": True}
                for item in RANGES
            ]
        return self.storage.history.available_ranges(slug)

    # ------------------------------------------------------------------ search
    def search(self, query: str) -> list[dict]:
        """جستجوی نرم بین دارایی‌ها."""
        from ..assets import normalize_query

        needle = normalize_query(query)
        if not needle:
            return []
        quotes = self.quotes()
        hits: list[dict] = []
        for asset in all_assets_ordered():
            haystack = " ".join(
                (asset.slug, asset.title, asset.symbol.lower(), normalize_query(asset.title))
            ).lower()
            if needle in haystack:
                hits.append(self.card(asset.slug, quotes=quotes))
        exact = search(query)
        if exact is not None and not any(hit["slug"] == exact.slug for hit in hits):
            hits.insert(0, self.card(exact.slug, quotes=quotes))
        return hits[:20]

    # --------------------------------------------------------------- watchlist
    def watchlist(self, owner: str) -> dict:
        """اقلام دیده‌بان یک بازدیدکننده با کارت‌های تازه‌محاسبه‌شده."""
        quotes = self.quotes()
        entries = self.storage.watchlist.entries(owner)
        return {
            "owner": owner,
            "count": len(entries),
            "items": [
                {**self.card(entry["slug"], quotes=quotes), "added_at": entry["created_at"]}
                for entry in entries
                if entry["slug"] in ASSETS
            ],
        }

    # ------------------------------------------------------------------ digest
    def digest(self) -> dict:
        """خلاصهٔ کوتاه برای هدر: قیمت‌های شاخص + وضعیت منابع."""
        quotes = self.quotes()
        from ..assets import FEATURED

        return {
            "items": [self.card(slug, quotes=quotes) for slug in FEATURED if slug in ASSETS],
            "sources": [
                {"name": status.name, "ok": status.ok, "checked_at": status.checked_at,
                 "latency_ms": status.latency_ms, "items": status.items,
                 "error": status.error or None}
                for status in self.storage.sources.latest()
            ],
            "last_update": self.storage.quotes.last_update(),
            "generated_at": time.time(),
        }


__all__ = ["MOVER_WINDOWS", "MarketService"]
