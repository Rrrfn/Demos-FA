# -*- coding: utf-8 -*-
"""سرویس بازار — هماهنگ‌کنندهٔ ارائه‌دهنده‌ها، کش و تاریخچه.

قواعد غیرقابل‌مذاکرهٔ این لایه:

1. **هیچ قیمت ساختگی، هیچ مقدار پیش‌فرض.** اگر هیچ منبعی داده ندهد،
   :class:`PriceUnavailable` بالا می‌رود و ربات صادقانه «دردسترس نیست»
   نشان می‌دهد.
2. **کش کوتاه‌مدت مجاز است، ولی کهنگی اعلام می‌شود.** دادهٔ کش‌شده برچسب
   زمان و وضعیت تازگی می‌گیرد؛ چیزی که از حد تحمل قدیمی‌تر باشد هرگز
   به‌عنوان live نمایش داده نمی‌شود.
3. **تغییر از تاریخچهٔ واقعی.** درصد تغییر فقط وقتی نمایش داده می‌شود که
   یک مشاهدهٔ ثبت‌شدهٔ قبلی موجود باشد.
"""
from __future__ import annotations

import asyncio
import logging
import time

from ..config import Config
from ..core import assets as asset_registry
from ..core.errors import PriceUnavailable, ProviderError, UnknownAsset
from ..core.models import AssetKind, Freshness, MarketSnapshot, ProviderStatus, Quote
from ..providers import CoinGeckoProvider, HttpClient, TgjuProvider
from ..providers.base import BaseProvider
from ..storage import Storage

log = logging.getLogger("ghematyar.market")

# پنجره‌های تغییر به‌ترتیب اولویت؛ اولین پنجره‌ای که تاریخچهٔ کافی داشته
# باشد برنده است. ترتیب از معنادارترین به کوتاه‌ترین است.
CHANGE_WINDOWS: tuple[float, ...] = (86400.0, 21600.0, 3600.0)


class MarketService:
    """دسترسی واحد به قیمت‌ها با کش، fallback و تاریخچه."""

    def __init__(
        self,
        config: Config,
        storage: Storage,
        *,
        providers: dict[str, BaseProvider] | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.http = http or HttpClient(config.data)
        self.providers: dict[str, BaseProvider] = providers or {
            "coingecko": CoinGeckoProvider(self.http, config.data),
            "tgju": TgjuProvider(self.http, config.data),
        }
        self._cache: dict[str, Quote] = {}
        self._cache_at: float = 0.0
        self._lock = asyncio.Lock()
        self._last_statuses: list[ProviderStatus] = []

    # ------------------------------------------------------------------ chain
    def _provider_passes(
        self, slugs: list[str]
    ) -> list[tuple[BaseProvider, list[str]]]:
        """ترتیب تلاش منابع برای اقلام درخواستی.

        رمزارزها ابتدا از CoinGecko (منبع مستقل و دارای تغییر ۲۴ ساعته) و
        سپس از tgju گرفته می‌شوند؛ اقلام بازار داخل فقط از tgju.
        """
        passes: list[tuple[BaseProvider, list[str]]] = []
        crypto = [s for s in slugs if asset_registry.ASSETS[s].kind is AssetKind.CRYPTO]
        coingecko = self.providers.get("coingecko")
        if crypto and coingecko is not None:
            passes.append((coingecko, crypto))
        tgju = self.providers.get("tgju")
        if tgju is not None:
            passes.append((tgju, list(slugs)))
        return passes

    # ---------------------------------------------------------------- public
    async def snapshot(
        self, slugs: list[str] | None = None, *, force: bool = False
    ) -> MarketSnapshot:
        """دریافت وضعیت بازار برای اقلام درخواستی.

        در صورت موفقیت یک :class:`MarketSnapshot` برمی‌گرداند و در صورت
        نبود دادهٔ قابل‌اتکا :class:`PriceUnavailable` بالا می‌رود.
        """
        requested = list(slugs) if slugs else []
        wanted = [s for s in (requested or list(asset_registry.ASSETS)) if asset_registry.exists(s)]
        if not wanted:
            # درخواست صریح برای قلمی که در فهرست نیست، خطای برنامه است
            # («قلم ناشناخته») نه «داده در دسترس نیست» — این دو یکی نیستند.
            if requested:
                raise UnknownAsset(requested[0])
            raise PriceUnavailable([], "no known assets requested")

        async with self._lock:
            cached = self._fresh_cache(wanted, force=force)
            if cached is not None:
                return cached
            return await self._fetch(wanted)

    async def quote(self, slug: str, *, force: bool = False) -> Quote:
        """یک قلم؛ در نبود داده خطای صریح می‌دهد."""
        if not asset_registry.exists(slug):
            raise UnknownAsset(slug)
        snapshot = await self.snapshot([slug], force=force)
        quote = snapshot.get(slug)
        if quote is None:
            raise PriceUnavailable([asset_registry.ASSETS[slug].title])
        return quote

    def provider_status(self) -> list[ProviderStatus]:
        """آخرین وضعیت منابع (برای /status)."""
        return list(self._last_statuses)

    def cache_info(self) -> tuple[int, float]:
        """(تعداد اقلام کش‌شده، سن کش به ثانیه)."""
        if not self._cache:
            return 0, 0.0
        return len(self._cache), max(0.0, time.time() - self._cache_at)

    async def close(self) -> None:
        await self.http.close()

    # ----------------------------------------------------------------- cache
    def _fresh_cache(self, wanted: list[str], *, force: bool) -> MarketSnapshot | None:
        """کش معتبر در محدودهٔ TTL، در صورت پوشش همهٔ اقلام درخواستی."""
        if force or not self._cache:
            return None
        age = time.time() - self._cache_at
        if age >= self.config.data.cache_ttl:
            return None
        if any(slug not in self._cache for slug in wanted):
            return None
        quotes = {slug: _copy_quote(self._cache[slug]) for slug in wanted}
        snapshot = MarketSnapshot(quotes=quotes, statuses=list(self._last_statuses),
                                  from_cache=True, fetched_at=self._cache_at)
        return snapshot

    def _stale_cache(self, wanted: list[str]) -> MarketSnapshot | None:
        """کش کهنه — فقط اگر در حدی باشد که نمایش با برچسب کهنگی مجاز است."""
        usable: dict[str, Quote] = {}
        for slug in wanted:
            quote = self._cache.get(slug)
            if quote is None:
                continue
            quote = _copy_quote(quote)
            quote.mark_stale(self.config.data.stale_after, self.config.data.expire_after)
            if quote.is_usable:
                usable[slug] = quote
        if not usable:
            return None
        return MarketSnapshot(quotes=usable, statuses=list(self._last_statuses),
                              from_cache=True, fetched_at=self._cache_at)

    # ---------------------------------------------------------------- fetching
    async def _fetch(self, wanted: list[str]) -> MarketSnapshot:
        """تلاش از منابع، ثبت تاریخچه، محاسبهٔ تغییر و اعمال تازگی."""
        quotes: dict[str, Quote] = {}
        statuses: list[ProviderStatus] = []
        errors: list[str] = []

        for provider, candidates in self._provider_passes(wanted):
            pending = [s for s in candidates if s not in quotes]
            if not pending:
                continue
            started = time.perf_counter()
            try:
                found = await provider.fetch(pending)
            except ProviderError as exc:
                statuses.append(ProviderStatus(
                    name=provider.name, ok=False,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=exc.message,
                ))
                errors.append(f"{provider.name}: {exc.message}")
                log.warning("provider %s failed: %s", provider.name, exc.message)
                continue
            except Exception as exc:  # noqa: BLE001
                statuses.append(ProviderStatus(
                    name=provider.name, ok=False,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=str(exc)[:200],
                ))
                errors.append(f"{provider.name}: {exc}")
                continue
            fresh = {s: q for s, q in found.items() if s in pending and q.price > 0}
            quotes.update(fresh)
            statuses.append(ProviderStatus(
                name=provider.name, ok=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
                items=len(fresh),
            ))
            log.info("provider %s supplied %d/%d quotes", provider.name, len(fresh), len(pending))

        self._last_statuses = statuses

        if not quotes:
            # هیچ داده‌ای نرسید: یا کش کهنه داریم (با برچسب) یا صادقانه خطا
            stale = self._stale_cache(wanted)
            if stale is not None:
                log.warning("all providers failed; serving stale cache with label")
                return stale
            detail = "; ".join(errors)[:400]
            raise PriceUnavailable([asset_registry.ASSETS[s].title for s in wanted if s], detail)

        self._finalise(quotes)
        self._cache.update(quotes)
        self._cache_at = time.time()
        self._record_history(quotes)
        return MarketSnapshot(quotes=quotes, statuses=statuses, from_cache=False,
                              fetched_at=self._cache_at)

    def _finalise(self, quotes: dict[str, Quote]) -> None:
        """تکمیل تغییر و وضعیت تازگی هر نقل‌قول."""
        now = time.time()
        for quote in quotes.values():
            if quote.change_pct is None:
                self._derive_change_from_history(quote)
            if not quote.observed_at:
                quote.observed_at = quote.fetched_at or now
            quote.mark_stale(self.config.data.stale_after, self.config.data.expire_after)

    def _derive_change_from_history(self, quote: Quote) -> None:
        """محاسبهٔ تغییر از تاریخچهٔ خودمان — بدون حدس.

        اگر هیچ مشاهدهٔ قبلی در پنجره‌های تعریف‌شده نباشد، هیچ عددی ساخته
        نمی‌شود و ``change_pct`` مقدار ``None`` می‌ماند.
        """
        for window in CHANGE_WINDOWS:
            result = self.storage.history.change_since(quote.slug, quote.price, window)
            if result is None:
                continue
            delta, pct, label = result
            quote.change_abs = delta
            quote.change_pct = pct
            quote.change_basis = label
            return

    def _record_history(self, quotes: dict[str, Quote]) -> None:
        """ثبت نمونه‌ها برای محاسبهٔ تغییر و نمودار."""
        try:
            written = self.storage.history.record_many(quotes)
            if written:
                log.debug("recorded %d history points", written)
        except Exception as exc:  # noqa: BLE001
            # خطای تاریخچه نباید نمایش قیمت را از کار بیندازد
            log.warning("history write failed: %s", exc)


def _copy_quote(quote: Quote) -> Quote:
    """کپی سطحی برای اینکه تغییر وضعیت کش، مقدار اصلی را دست‌کاری نکند."""
    clone = Quote(
        slug=quote.slug, price=quote.price, unit=quote.unit, source=quote.source,
        observed_at=quote.observed_at, fetched_at=quote.fetched_at,
        day_low=quote.day_low, day_high=quote.day_high,
        change_abs=quote.change_abs, change_pct=quote.change_pct,
        change_basis=quote.change_basis, freshness=quote.freshness,
        decimals=quote.decimals,
    )
    return clone


__all__ = ["MarketService", "CHANGE_WINDOWS", "Freshness"]
