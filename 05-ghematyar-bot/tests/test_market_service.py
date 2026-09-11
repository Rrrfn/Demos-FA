# -*- coding: utf-8 -*-
"""تست سرویس بازار.

مهم‌ترین خاصیت‌هایی که این‌جا قفل می‌شوند:

* کش کوتاه‌مدت کار می‌کند ولی برچسب می‌خورد.
* fallback بین منابع واقعی است (رمزارز: CoinGecko → tgju).
* در نبود دادهٔ تازه، کش کهنه *با برچسب* سرو می‌شود، نه به‌عنوان live.
* در نبود هر داده، خطای صریح بالا می‌رود؛ هیچ قیمت ساختگی ساخته نمی‌شود.
* تغییر فقط از تاریخچهٔ واقعی محاسبه می‌شود.
"""
from __future__ import annotations

import time

import pytest

from ghematyar.core.errors import PriceUnavailable, ProviderError
from ghematyar.core.models import Freshness, Quote
from ghematyar.services import MarketService


def make_quote(slug: str = "usd", price: float = 250_000.0, *, source: str = "fake") -> Quote:
    now = time.time()
    return Quote(slug=slug, price=price, source=source, observed_at=now, fetched_at=now)


class TestCache:
    """کش کوتاه‌مدت."""

    @pytest.mark.anyio
    async def test_second_call_uses_cache(self, config, storage, scripted_provider):
        provider = scripted_provider("p", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        await service.snapshot(["usd"])
        await service.snapshot(["usd"])
        assert len(provider.calls) == 1

    @pytest.mark.anyio
    async def test_force_bypasses_cache(self, config, storage, scripted_provider):
        provider = scripted_provider("p", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        await service.snapshot(["usd"])
        await service.snapshot(["usd"], force=True)
        assert len(provider.calls) == 2

    @pytest.mark.anyio
    async def test_expired_cache_refetches(self, config, storage, scripted_provider, tuned):
        provider = scripted_provider("p", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        await service.snapshot(["usd"])
        service.config = tuned(config, data={"cache_ttl": 0})
        await service.snapshot(["usd"])
        assert len(provider.calls) == 2

    @pytest.mark.anyio
    async def test_cache_partial_coverage_refetches(self, config, storage, scripted_provider):
        """اگر قلم درخواستی در کش نباشد، دوباره از منبع می‌خوانیم."""
        provider = scripted_provider("p", lambda slugs: {
            s: make_quote(slug=s) for s in slugs
        })
        service = MarketService(config, storage, providers={"tgju": provider})
        await service.snapshot(["usd"])
        await service.snapshot(["usd", "eur"])
        assert len(provider.calls) == 2

    @pytest.mark.anyio
    async def test_cached_result_is_flagged(self, config, storage, scripted_provider):
        provider = scripted_provider("p", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        await service.snapshot(["usd"])
        cached = await service.snapshot(["usd"])
        assert cached.from_cache is True

    @pytest.mark.anyio
    async def test_cache_info(self, config, storage, scripted_provider):
        provider = scripted_provider("p", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        assert service.cache_info() == (0, 0.0)
        await service.snapshot(["usd"])
        items, age = service.cache_info()
        assert items == 1 and age >= 0


class TestFallback:
    """زنجیرهٔ fallback بین منابع."""

    @pytest.mark.anyio
    async def test_crypto_prefers_coingecko(self, config, storage, scripted_provider):
        coingecko = scripted_provider("coingecko", {"bitcoin": make_quote("bitcoin", 78_000, source="coingecko")})
        tgju = scripted_provider("tgju", {"bitcoin": make_quote("bitcoin", 99_999, source="tgju")})
        service = MarketService(config, storage, providers={"coingecko": coingecko, "tgju": tgju})
        snapshot = await service.snapshot(["bitcoin"])
        assert snapshot.get("bitcoin").source == "coingecko"
        assert tgju.calls == []  # منبع دوم بی‌دلیل صدا زده نشد

    @pytest.mark.anyio
    async def test_falls_back_to_tgju_when_coingecko_fails(self, config, storage, scripted_provider):
        coingecko = scripted_provider("coingecko", ProviderError("coingecko", "down"))
        tgju = scripted_provider("tgju", {"bitcoin": make_quote("bitcoin", 78_000, source="tgju")})
        service = MarketService(config, storage, providers={"coingecko": coingecko, "tgju": tgju})
        snapshot = await service.snapshot(["bitcoin"])
        assert snapshot.get("bitcoin").source == "tgju"

    @pytest.mark.anyio
    async def test_mixed_assets_use_their_own_sources(self, config, storage, scripted_provider):
        coingecko = scripted_provider("coingecko", lambda slugs: {
            s: make_quote(s, source="coingecko") for s in slugs
        })
        tgju = scripted_provider("tgju", lambda slugs: {
            s: make_quote(s, source="tgju") for s in slugs
        })
        service = MarketService(config, storage, providers={"coingecko": coingecko, "tgju": tgju})
        snapshot = await service.snapshot(["bitcoin", "usd"])
        assert snapshot.get("bitcoin").source == "coingecko"
        assert snapshot.get("usd").source == "tgju"
        # tgju فقط برای قلمی که CoinGecko ندارد صدا زده می‌شود
        assert tgju.calls == [["usd"]]

    @pytest.mark.anyio
    async def test_partial_success_returns_available_assets(self, config, storage, scripted_provider):
        provider = scripted_provider("tgju", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        snapshot = await service.snapshot(["usd", "eur"])
        assert "usd" in snapshot.quotes
        assert "eur" not in snapshot.quotes

    @pytest.mark.anyio
    async def test_provider_status_is_reported(self, config, storage, scripted_provider):
        coingecko = scripted_provider("coingecko", ProviderError("coingecko", "down"))
        tgju = scripted_provider("tgju", {"bitcoin": make_quote("bitcoin")})
        service = MarketService(config, storage, providers={"coingecko": coingecko, "tgju": tgju})
        await service.snapshot(["bitcoin"])
        statuses = {s.name: s for s in service.provider_status()}
        assert statuses["coingecko"].ok is False
        assert statuses["tgju"].ok is True


class TestHonestUnavailability:
    """نبود داده هرگز به دادهٔ ساختگی تبدیل نمی‌شود."""

    @pytest.mark.anyio
    async def test_all_providers_failing_raises(self, config, storage, scripted_provider):
        provider = scripted_provider("tgju", ProviderError("tgju", "down"))
        service = MarketService(config, storage, providers={"tgju": provider})
        with pytest.raises(PriceUnavailable):
            await service.snapshot(["usd"])

    @pytest.mark.anyio
    async def test_error_message_names_assets(self, config, storage, scripted_provider):
        provider = scripted_provider("tgju", ProviderError("tgju", "down"))
        service = MarketService(config, storage, providers={"tgju": provider})
        with pytest.raises(PriceUnavailable) as exc:
            await service.snapshot(["usd"])
        assert "دلار آمریکا" in exc.value.slugs

    @pytest.mark.anyio
    async def test_stale_cache_is_served_with_label(self, config, storage, scripted_provider, tuned):
        """وقتی منبع قطع می‌شود، کش کهنه با برچسب می‌آید — نه به‌عنوان live."""
        healthy = scripted_provider("tgju", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": healthy})
        await service.snapshot(["usd"])

        # منبع می‌افتد و کش از حد تازه گذشته است ولی هنوز منقضی نشده
        broken = scripted_provider("tgju", ProviderError("tgju", "down"))
        service.providers = {"tgju": broken}
        service.config = tuned(config, data={"cache_ttl": 0, "stale_after": 0})
        snapshot = await service.snapshot(["usd"])
        quote = snapshot.get("usd")
        assert quote is not None
        assert quote.freshness is Freshness.STALE
        assert snapshot.from_cache is True

    @pytest.mark.anyio
    async def test_expired_cache_is_not_served(self, config, storage, scripted_provider, tuned):
        healthy = scripted_provider("tgju", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": healthy})
        await service.snapshot(["usd"])

        broken = scripted_provider("tgju", ProviderError("tgju", "down"))
        service.providers = {"tgju": broken}
        service.config = tuned(
            config, data={"cache_ttl": 0, "stale_after": 0, "expire_after": 0}
        )
        with pytest.raises(PriceUnavailable):
            await service.snapshot(["usd"])

    @pytest.mark.anyio
    async def test_zero_prices_are_discarded(self, config, storage, scripted_provider):
        """قیمت صفر یعنی «داده نداریم»، نه «رایگان»."""
        provider = scripted_provider("tgju", {"usd": make_quote(price=0.0)})
        service = MarketService(config, storage, providers={"tgju": provider})
        with pytest.raises(PriceUnavailable):
            await service.snapshot(["usd"])

    @pytest.mark.anyio
    async def test_quote_for_unknown_asset_raises(self, config, storage, scripted_provider):
        provider = scripted_provider("tgju", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        from ghematyar.core.errors import UnknownAsset

        with pytest.raises(UnknownAsset):
            await service.snapshot(["not-an-asset"])

    @pytest.mark.anyio
    async def test_quote_helper_raises_when_asset_missing(self, config, storage, scripted_provider):
        provider = scripted_provider("tgju", {"eur": make_quote("eur")})
        service = MarketService(config, storage, providers={"tgju": provider})
        with pytest.raises(PriceUnavailable):
            await service.quote("usd")


class TestChangeFromHistory:
    """تغییر فقط از تاریخچهٔ خودمان — بدون حدس."""

    @pytest.mark.anyio
    async def test_no_history_means_no_change(self, config, storage, scripted_provider):
        provider = scripted_provider("tgju", {"usd": make_quote(price=250_000)})
        service = MarketService(config, storage, providers={"tgju": provider})
        snapshot = await service.snapshot(["usd"], force=True)
        quote = snapshot.get("usd")
        assert quote.change_pct is None
        assert quote.change_abs is None

    @pytest.mark.anyio
    async def test_change_computed_from_recorded_point(self, config, storage, scripted_provider):
        from ghematyar.core.models import PricePoint

        # نقطه‌ای در ۲۴ ساعت پیش در تاریخچه
        with storage.database.transaction() as conn:
            conn.execute(
                "INSERT INTO price_history (slug, price, unit, source, observed_at, captured_at)"
                " VALUES (?,?,?,?,?,?)",
                ("usd", 200_000.0, "toman", "test", time.time() - 86400, time.time() - 86400),
            )
        provider = scripted_provider("tgju", {"usd": make_quote(price=250_000)})
        service = MarketService(config, storage, providers={"tgju": provider})
        snapshot = await service.snapshot(["usd"], force=True)
        quote = snapshot.get("usd")
        assert quote.change_pct == pytest.approx(25.0)
        assert quote.change_abs == pytest.approx(50_000)
        assert "۲۴" in quote.change_basis
        _ = PricePoint

    @pytest.mark.anyio
    async def test_source_change_is_kept_when_present(self, config, storage, scripted_provider):
        """اگر منبع خودش تغییر بدهد، همان اولویت دارد."""
        quote = make_quote("bitcoin", 78_000)
        quote.change_pct = 2.5
        quote.change_abs = 1_950
        quote.change_basis = "تغییر ۲۴ ساعته (منبع)"
        provider = scripted_provider("coingecko", {"bitcoin": quote})
        service = MarketService(config, storage, providers={"coingecko": provider})
        snapshot = await service.snapshot(["bitcoin"])
        assert snapshot.get("bitcoin").change_pct == pytest.approx(2.5)
        assert snapshot.get("bitcoin").change_basis == "تغییر ۲۴ ساعته (منبع)"


class TestHistoryRecording:
    """ثبت خودکار تاریخچه در هر دریافت."""

    @pytest.mark.anyio
    async def test_snapshot_records_history(self, config, storage, scripted_provider):
        provider = scripted_provider("tgju", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})
        await service.snapshot(["usd"])
        assert storage.history.stats()["points"] == 1

    @pytest.mark.anyio
    async def test_history_failure_does_not_break_quotes(self, config, storage, scripted_provider, monkeypatch):
        provider = scripted_provider("tgju", {"usd": make_quote()})
        service = MarketService(config, storage, providers={"tgju": provider})

        def boom(*_args, **_kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(storage.history, "record_many", boom)
        snapshot = await service.snapshot(["usd"])
        assert snapshot.get("usd") is not None
