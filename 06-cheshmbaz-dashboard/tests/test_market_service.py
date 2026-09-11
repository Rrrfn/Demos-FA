# -*- coding: utf-8 -*-
"""آزمون سرویس بازار — تازگی در زمان خواندن، تغییر صادقانه و نماهای داشبورد.

مهم‌ترین آزمون این فایل `test_freshness_is_computed_at_read_time` است: اگر
برچسب تازگی هنگام نوشتن ثابت می‌شد، قیمت نیم‌ساعته تا ابد «زنده» می‌ماند.
"""
from __future__ import annotations

import time

import pytest

from cheshmbaz.core.models import AssetKind, Freshness, Quote
from cheshmbaz.services.market import MarketService


def _store_quote(storage, slug: str, price: float, *, age_seconds: float, **kwargs) -> Quote:
    stamp = time.time() - age_seconds
    quote = Quote(
        slug=slug, price=price, unit="usd" if slug in {"bitcoin", "ethereum"} else "toman",
        source="test", observed_at=stamp, fetched_at=stamp, **kwargs
    )
    storage.quotes.save_many({slug: quote})
    return quote


def test_freshness_is_computed_at_read_time(storage, config, monkeypatch):
    """قیمتی که هنگام نوشتن تازه بود، بعد از گذشت زمان دیگر زنده نیست."""
    # آستانه‌ها از پیکربندی می‌آیند، پس برای این سناریو کوتاهشان می‌کنیم.
    tuned = config.retuned(
        data={"live_within": 60, "stale_after": 120, "expire_after": 240}
    )
    now = time.time()
    stored = Quote(
        slug="usd", price=200_000, unit="toman", source="test",
        observed_at=now, fetched_at=now,
    )
    stored.mark_freshness(
        tuned.data.live_within, tuned.data.stale_after, tuned.data.expire_after
    )
    assert stored.freshness is Freshness.LIVE
    storage.quotes.save_many({"usd": stored})

    # ساعت سیستم چهارصد ثانیه جلو می‌رود؛ ردیف پایگاه داده دست‌نخورده است
    monkeypatch.setattr(time, "time", lambda: now + 400)
    service = MarketService(config=tuned, storage=storage, collector=None)  # type: ignore[arg-type]
    quote = service.quotes()["usd"]

    assert quote.freshness is Freshness.EXPIRED
    assert quote.is_usable is False
    card = service.card("usd")
    assert card["is_usable"] is False
    assert card["freshness"] == "expired"
    assert card["price"] is not None, "قیمت نمایش داده می‌شود، ولی با برچسب کهنه"


def test_live_and_recent_are_usable(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=30)
    _store_quote(storage, "eur", 300_000, age_seconds=3600)
    _store_quote(storage, "gbp", 400_000, age_seconds=20_000)

    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[arg-type]
    quotes = service.quotes()
    assert quotes["usd"].freshness is Freshness.LIVE
    assert quotes["eur"].freshness is Freshness.RECENT
    assert quotes["gbp"].freshness is Freshness.STALE
    assert quotes["gbp"].is_usable is False
    usable = service.quotes(only_usable=True)
    assert set(usable) == {"usd", "eur"}


def test_missing_asset_card_is_explicit(storage, config):
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[arg-type]
    card = service.card("solana")
    assert card["has_data"] is False
    assert card["price"] is None
    assert card["price_text"] == "—"
    assert card["change_pct_text"] == "—"
    assert card["freshness"] == "unknown"
    assert card["is_usable"] is False


def test_change_stays_empty_without_history(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=30)
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    quote = service.quotes()["usd"]
    assert quote.change_pct is None
    card = service.card("usd")
    assert card["change_pct_text"] == "—"
    assert card["direction"] == 0


def test_change_is_computed_from_own_history(storage, config):
    """مرجع ۲۴ ساعته از تاریخچهٔ خودمان خوانده می‌شود."""
    now = time.time()
    storage.history.record_many({
        "usd": Quote(slug="usd", price=200_000, unit="toman", source="test",
                     observed_at=now - 90000, fetched_at=now - 90000),
        "eur": Quote(slug="eur", price=250_000, unit="toman", source="test",
                     observed_at=now - 90000, fetched_at=now - 90000),
    })
    _store_quote(storage, "usd", 210_000, age_seconds=30)
    _store_quote(storage, "eur", 240_000, age_seconds=30)

    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    quotes = service.quotes()

    assert quotes["usd"].change_pct == pytest.approx(5.0, rel=1e-3)
    assert quotes["usd"].change_abs == pytest.approx(10_000)
    assert quotes["usd"].direction == 1
    assert quotes["eur"].change_pct == pytest.approx(-4.0, rel=1e-3)
    assert quotes["eur"].direction == -1

    card = service.card("usd")
    assert card["change_pct_text"] == "۵٪"
    assert card["arrow"] == "▲"


def test_provider_change_is_preferred_over_history(storage, config):
    _store_quote(
        storage, "bitcoin", 77_000, age_seconds=30,
        change_pct=1.5, change_abs=1100.0, change_basis="۲۴ ساعتهٔ منبع",
        previous_price=75_900.0,
    )
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    quote = service.quotes()["bitcoin"]
    assert quote.change_pct == pytest.approx(1.5)
    assert quote.change_basis == "۲۴ ساعتهٔ منبع"


def test_overview_groups_and_totals(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=30)
    _store_quote(storage, "geram18", 24_000_000, age_seconds=30)
    _store_quote(storage, "bitcoin", 77_000, age_seconds=30)

    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    data = service.overview()

    assert [group["kind"] for group in data["groups"]] == [k.value for k in AssetKind]
    assert data["totals"]["assets"] == data["totals"]["with_data"] + data["totals"]["missing"]
    assert data["totals"]["with_data"] == 3
    assert data["totals"]["usable"] == 3
    assert data["totals"]["missing"] >= 1
    assert len(data["featured"]) == 6
    assert all(card["slug"] in {"geram18", "sekee", "usd", "eur", "bitcoin", "ethereum"}
               for card in data["featured"])
    assert data["database"]["quotes"] == 3


def test_movers_only_use_usable_and_real_changes(storage, config):
    now = time.time()
    for slug, old_price, new_price in (
        ("usd", 200_000, 220_000),       # +10%
        ("eur", 300_000, 285_000),       # -5%
        ("gbp", 400_000, 400_000),       # بی‌تغییر
    ):
        storage.history.record_many({
            slug: Quote(slug=slug, price=old_price, unit="toman", source="test",
                        observed_at=now - 90000, fetched_at=now - 90000)
        })
        _store_quote(storage, slug, new_price, age_seconds=30)
    # قلم کهنه با تغییر بزرگ نباید در فهرست بیشترین تغییرها بیاید
    _store_quote(storage, "geram18", 99_000_000, age_seconds=200_000)

    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    movers = service.movers(window="1D", limit=5)

    assert [item["slug"] for item in movers["gainers"]] == ["usd"]
    assert [item["slug"] for item in movers["losers"]] == ["eur"]
    assert movers["gainers"][0]["change_pct_text"] == "۱۰٪"
    assert "geram18" not in [item["slug"] for item in movers["gainers"]]
    assert movers["window_label"] == "۲۴ ساعت"


def test_movers_window_labels(storage, config):
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    assert service.movers(window="7D")["window_label"] == "۷ روز"
    assert service.movers(window="30D")["window_label"] == "۳۰ روز"
    assert service.movers(window="bogus")["window"] == "1D"
    assert service.movers(window="bogus")["window_label"] == "۲۴ ساعت"


def test_movers_window_uses_that_windows_real_history(storage, config):
    """بازهٔ ۷ روزه نباید عدد ۲۴ ساعته را زیر برچسب خودش نشان دهد."""
    now = time.time()
    storage.history.record_many({
        "bitcoin": Quote(slug="bitcoin", price=50_000, unit="usd", source="test",
                         observed_at=now - 20 * 86400, fetched_at=now - 20 * 86400),
    })
    # درصد خودِ منبع فقط برای پنجرهٔ پیش‌فرض معتبر است
    _store_quote(storage, "bitcoin", 77_000, age_seconds=30,
                 change_pct=1.5, change_basis="۲۴ ساعتهٔ منبع")

    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    daily = service.movers(window="1D")
    weekly = service.movers(window="7D")

    assert daily["gainers"][0]["change_pct"] == pytest.approx(1.5)
    assert weekly["gainers"][0]["change_pct"] == pytest.approx(54.0)


def test_search_finds_assets_and_letters(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=30)
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]

    hits = service.search("دلار")
    assert [card["slug"] for card in hits] == ["usd"]
    assert service.search("btc")[0]["slug"] == "bitcoin"
    assert service.search("") == []
    assert service.search("هرچیزینامربوط") == []


def test_series_returns_real_points_only(storage, config):
    now = time.time()
    for index in range(6):
        storage.history.record_many({
            "usd": Quote(slug="usd", price=200_000 + index * 100, unit="toman", source="test",
                         observed_at=now - (6 - index) * 1200, fetched_at=now)
        })
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    series = service.series("usd", range_key="7D")

    assert series["has_data"] is True
    assert series["count"] >= 2
    assert all(point["price_text"] for point in series["points"])
    assert series["coverage"]["points"] == 6
    assert series["range"] == "7D"


def test_series_without_data_is_honest(storage, config):
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    series = service.series("usd", range_key="30D")
    assert series["has_data"] is False
    assert series["points"] == []
    assert all(item["has_data"] is False for item in series["ranges"])


def test_watchlist_view(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=30)
    storage.watchlist.add("u1", "usd")
    storage.watchlist.add("u1", "eur")  # بدون قیمت

    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    view = service.watchlist("u1")
    assert view["count"] == 2
    items = {item["slug"]: item for item in view["items"]}
    assert items["usd"]["has_data"] is True
    assert items["eur"]["has_data"] is False


def test_digest_shape(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=30)
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    digest = service.digest()
    assert len(digest["items"]) == 6
    assert "generated_at" in digest


def test_snapshot_without_refresh_reports_missing(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=30)
    _store_quote(storage, "eur", 300_000, age_seconds=30)
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    snapshot = service.snapshot()
    assert snapshot.from_cache is True
    assert set(snapshot.quotes) == {"usd", "eur"}
    assert snapshot.missing == []  # داده تازه هست، پس «ناقص» گزارش نمی‌شود


def test_snapshot_reports_missing_when_no_live_data(storage, config):
    _store_quote(storage, "usd", 200_000, age_seconds=300_000)
    service = MarketService(config=config, storage=storage, collector=None)  # type: ignore[assignment]
    snapshot = service.snapshot()
    assert snapshot.missing, "وقتی هیچ داده تازه‌ای نیست، اقلام غایب باید گزارش شوند"
