# -*- coding: utf-8 -*-
"""آزمون جمع‌آور — تفکیک شکست منابع، تغییر از تاریخچهٔ خودمان و قرارداد.

هیچ‌کدام از این آزمون‌ها به شبکه نمی‌زنند: منبع‌ها اسکریپتی‌اند و رفتارشان را
خود تست تعیین می‌کند. نکتهٔ کلیدی این لایه **تفکیک شکست** است: قطع شدن tgju
نباید جلوی ثبت رمزارز را بگیرد، و برعکس.
"""
from __future__ import annotations

import time

import pytest

from cheshmbaz.core.errors import ProviderError
from cheshmbaz.core.models import Quote
from cheshmbaz.services.collector import CHANGE_WINDOW_SECONDS, Collector, seed_registry
from cheshmbaz.services.market import MarketService
from tests.fakes import FakeTransport, ScriptedProvider, http_with


# ------------------------------------------------------------------ helpers
def _provider(config, name: str, **kwargs) -> ScriptedProvider:
    transport = FakeTransport()
    return ScriptedProvider(name, http_with(transport, config.data), config.data, **kwargs)


def _collector(config, storage, providers) -> Collector:
    return Collector(
        config, storage, providers=providers, http=http_with(FakeTransport(), config.data)
    )


@pytest.fixture()
def inline(config, storage):
    """جمع‌آوری درون‌خط و بدون قرارداد — سریع و قطعی."""
    def run(providers):
        return _collector(config, storage, providers).collect(use_lease=False)

    return run


# --------------------------------------------------------------- happy path
def test_collect_end_to_end(config, storage, inline):
    provider = _provider(config, "tgju", prices={"geram18": 24_000_000})
    result = inline({"tgju": provider})

    assert result.ok is True
    assert result.skipped is False
    assert result.quotes_received == 1
    assert result.quotes_saved == 1
    assert result.readings_saved == 1
    assert result.duration_ms >= 0

    run = result.providers[0]
    assert run.name == "tgju"
    assert run.ok is True
    assert run.received == 1
    assert "geram18" not in run.missing
    assert len(run.missing) > 0  # بقیهٔ اقلام tgju در این پاسخ نبودند

    stored = storage.quotes.get("geram18")
    assert stored is not None
    assert stored.price == pytest.approx(24_000_000)
    assert stored.unit == "toman"
    assert storage.history.coverage("geram18")["points"] == 1


def test_collect_never_fabricates_change_without_history(config, storage, inline):
    """نبود مرجع تاریخی یعنی درصد خالی می‌ماند — نه صفر، نه عدد ساختگی."""
    result = inline({"tgju": _provider(config, "tgju", prices={"usd": 220_000, "eur": 300_000})})

    assert result.quotes_saved == 2
    assert result.with_change == 0
    for slug in ("usd", "eur"):
        stored = storage.quotes.get(slug)
        assert stored.change_pct is None
        assert stored.change_abs is None
        assert stored.change_basis == ""


def test_change_is_computed_from_our_own_history(config, storage, inline):
    now = time.time()
    storage.history.record_many({
        "usd": Quote(slug="usd", price=200_000, unit="toman", source="test",
                     observed_at=now - CHANGE_WINDOW_SECONDS - 3600,
                     fetched_at=now - CHANGE_WINDOW_SECONDS - 3600),
    })

    result = inline({"tgju": _provider(config, "tgju", prices={"usd": 220_000})})

    stored = storage.quotes.get("usd")
    assert stored.change_pct == pytest.approx(10.0)
    assert stored.change_abs == pytest.approx(20_000)
    assert stored.previous_price == pytest.approx(200_000)
    assert stored.change_basis == "۲۴ ساعته (تاریخچهٔ ثبت‌شده)"
    assert result.with_change == 1


def test_reference_falls_back_to_the_oldest_observation_inside_the_window(config, storage, inline):
    """اگر تاریخی پیش از مرز ۲۴ ساعت نداریم، قدیمی‌ترین مشاهدهٔ موجود مرجع می‌شود.

    این رفتار عمدی است (در `HistoryRepository.reference` مستند شده): کاربر در
    روز اول کار سامانه به‌جای «—» یک درصد واقعی می‌بیند، هرچند مبنا کوتاه‌تر از
    ۲۴ ساعت است. مبنا همیشه در ``change_basis`` اعلام می‌شود.
    """
    now = time.time()
    storage.history.record_many({
        "usd": Quote(slug="usd", price=200_000, unit="toman", source="test",
                     observed_at=now - 3600, fetched_at=now - 3600),
    })
    inline({"tgju": _provider(config, "tgju", prices={"usd": 220_000})})

    stored = storage.quotes.get("usd")
    assert stored.change_pct == pytest.approx(10.0)
    assert stored.previous_at == pytest.approx(now - 3600, abs=5)
    assert stored.change_basis == "۲۴ ساعته (تاریخچهٔ ثبت‌شده)"


def test_provider_supplied_change_is_not_overwritten(config, storage, inline):
    provider = _provider(
        config, "coingecko",
        prices={"bitcoin": 77_000, "ethereum": 3_100},
        change_pct={"bitcoin": 2.5, "ethereum": -1.25},
    )
    result = inline({"coingecko": provider})

    assert storage.quotes.get("bitcoin").change_pct == pytest.approx(2.5)
    assert storage.quotes.get("ethereum").change_pct == pytest.approx(-1.25)
    assert storage.quotes.get("bitcoin").change_basis == "تست"
    assert result.with_change == 2


# ------------------------------------------------------- failure isolation
def test_one_broken_provider_does_not_stop_the_other(config, storage, inline):
    providers = {
        "tgju": _provider(config, "tgju", error=ProviderError("tgju", "timeout")),
        "coingecko": _provider(config, "coingecko", prices={"bitcoin": 77_000}),
    }
    result = inline(providers)

    runs = {run.name: run for run in result.providers}
    assert runs["tgju"].ok is False
    assert runs["tgju"].error == "timeout"
    assert runs["coingecko"].ok is True
    assert runs["coingecko"].received == 1

    # نتیجه: دادهٔ سالم ثبت شد، منبع خراب فقط خودش را از دست داد
    assert result.ok is True
    assert storage.quotes.get("bitcoin") is not None
    assert storage.quotes.get_many(["geram18"]) == {}


def test_every_provider_attempt_lands_in_the_source_log(config, storage, inline):
    providers = {
        "tgju": _provider(config, "tgju", error=ProviderError("tgju", "connection reset")),
        "coingecko": _provider(config, "coingecko", prices={"bitcoin": 77_000}),
    }
    inline(providers)

    latest = {status.name: status for status in storage.sources.latest()}
    assert latest["tgju"].ok is False
    assert latest["tgju"].error == "connection reset"
    assert latest["coingecko"].ok is True
    assert latest["coingecko"].items == 1
    assert storage.sources.reliability("tgju")["attempts"] == 1
    assert storage.sources.reliability("tgju")["success_rate"] == 0.0


def test_all_providers_down_reports_not_ok(config, storage, inline):
    providers = {
        "tgju": _provider(config, "tgju", error=ProviderError("tgju", "down")),
        "coingecko": _provider(config, "coingecko", error=ProviderError("coingecko", "down")),
    }
    result = inline(providers)
    assert result.ok is False
    assert result.quotes_received == 0
    assert storage.quotes.count() == 0


def test_provider_with_no_registered_assets_is_not_an_error(config, storage, inline):
    result = inline({"mystery": _provider(config, "mystery", prices={"x": 1})})
    run = result.providers[0]
    assert run.requested == 0
    assert run.received == 0
    assert storage.sources.count() == 0


# -------------------------------------------------------------------- lease
def test_lease_blocks_a_second_collector(config, storage):
    providers = {"tgju": _provider(config, "tgju", prices={"geram18": 24_000_000})}
    first = _collector(config, storage, providers)
    second = _collector(config, storage, providers)
    second._lease_owner = "other-process@1"

    assert first.acquire_lease() is True
    assert first.lease_holder() is not None

    blocked = second.collect(use_lease=True)
    assert blocked.skipped is True
    assert "جمع‌آوری" in blocked.reason
    assert storage.quotes.count() == 0

    # فراخوانی دستی هرگز بلاک نمی‌شود
    manual = second.collect(use_lease=False)
    assert manual.skipped is False
    assert manual.quotes_saved == 1

    first.release_lease()
    assert first.lease_holder() is None
    assert second.collect(use_lease=True).skipped is False


def test_collect_releases_the_lease_even_when_everything_fails(config, storage):
    """قرارداد نباید پس از شکست گیر کند، وگرنه بازهٔ بعدی هرگز اجرا نمی‌شود."""
    collector = _collector(
        config, storage,
        {"tgju": _provider(config, "tgju", error=ProviderError("tgju", "boom"))},
    )
    result = collector.collect(use_lease=True)
    assert result.ok is False
    assert collector.lease_holder() is None


# ------------------------------------------------------------- integration
def test_collected_data_becomes_a_fresh_card(config, storage, inline):
    """زنجیرهٔ کامل: منبع → جمع‌آور → ذخیره‌سازی → سرویس → کارت رابط."""
    inline({"coingecko": _provider(config, "coingecko", prices={"bitcoin": 77_000},
                                   change_pct={"bitcoin": 1.5})})

    service = MarketService(config=config, storage=storage, collector=None)
    card = service.card("bitcoin")
    assert card["has_data"] is True
    assert card["price"] == pytest.approx(77_000)
    assert card["price_text"]
    assert card["freshness"] == "live"
    assert card["is_usable"] is True
    assert card["change_pct_text"] == "۱٫۵٪"
    assert card["arrow"] == "▲"


def test_seeding_registry_is_idempotent(storage):
    seed_registry(storage)
    first = storage.query_one("SELECT COUNT(*) AS n FROM assets")["n"]
    seed_registry(storage)
    assert storage.query_one("SELECT COUNT(*) AS n FROM assets")["n"] == first > 0
