# -*- coding: utf-8 -*-
"""آزمون لایهٔ ذخیره‌سازی — اسکیما، سری زمانی، منابع، دیده‌بان و هشدارها."""
from __future__ import annotations

import time

import pytest

from cheshmbaz.assets import all_assets_ordered
from cheshmbaz.core.errors import RuleNotFound
from cheshmbaz.core.models import AlertKind, AlertStatus, Quote, SourceStatus
from cheshmbaz.storage import SCHEMA_VERSION, Storage


# ------------------------------------------------------------------- schema
def test_schema_is_created_and_versioned(config):
    storage = Storage(config.db_path)
    assert storage.schema_version() == SCHEMA_VERSION
    tables = {
        row["name"]
        for row in storage.query("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "meta", "assets", "quotes", "readings", "source_runs",
        "alert_rules", "alert_events", "watchlist",
    } <= tables


def test_schema_is_idempotent(config):
    first = Storage(config.db_path)
    second = Storage(config.db_path)
    assert first.schema_version() == second.schema_version() == SCHEMA_VERSION


def test_asset_registry_is_mirrored(storage):
    storage.sync_assets(all_assets_ordered())
    row = storage.query_one("SELECT COUNT(*) AS n FROM assets")
    assert row["n"] == len(all_assets_ordered())
    storage.sync_assets(all_assets_ordered())  # تکرار بی‌عارضه
    assert storage.query_one("SELECT COUNT(*) AS n FROM assets")["n"] == len(all_assets_ordered())


def test_stats_reports_reality(storage):
    stats = storage.stats()
    assert stats["quotes"] == 0
    assert stats["readings"] == 0
    assert stats["schema_version"] == SCHEMA_VERSION
    assert stats["size_bytes"] >= 0


# ------------------------------------------------------------------- quotes
def _quote(slug="geram18", price=1000.0, observed_at=None, **kwargs) -> Quote:
    stamp = time.time() if observed_at is None else observed_at
    return Quote(
        slug=slug, price=price, unit="toman", source="test", observed_at=stamp,
        fetched_at=stamp, **kwargs
    )


def test_quote_roundtrip(storage):
    quote = _quote(price=1234.5, day_low=1200.0, day_high=1300.0)
    assert storage.quotes.save_many({quote.slug: quote}) == 1
    loaded = storage.quotes.get("geram18")
    assert loaded is not None
    assert loaded.price == pytest.approx(1234.5)
    assert loaded.day_low == 1200.0
    assert loaded.day_high == 1300.0
    assert loaded.source == "test"


def test_quote_write_moves_current_price_to_previous(storage):
    first = _quote(price=100.0, observed_at=1_000_000.0)
    storage.quotes.save_many({"geram18": first})
    second = _quote(price=110.0, observed_at=1_000_600.0)
    storage.quotes.save_many({"geram18": second})

    stored = storage.quotes.get("geram18")
    assert stored.price == pytest.approx(110.0)
    assert stored.previous_price == pytest.approx(100.0)
    assert stored.previous_at == pytest.approx(1_000_000.0)


def test_quote_rejects_stale_observation(storage):
    """مشاهدهٔ قدیمی‌تر نباید قیمت جاری را بازنویسی کند."""
    storage.quotes.save_many({"geram18": _quote(price=100.0, observed_at=2_000_000.0)})
    written = storage.quotes.save_many({"geram18": _quote(price=90.0, observed_at=1_999_000.0)})
    assert written == 0
    assert storage.quotes.get("geram18").price == pytest.approx(100.0)


def test_quote_rejects_duplicate_observation(storage):
    storage.quotes.save_many({"geram18": _quote(price=100.0, observed_at=5_000.0)})
    assert storage.quotes.save_many({"geram18": _quote(price=100.0, observed_at=5_000.0)}) == 0
    assert storage.quotes.get("geram18").previous_price is None


def test_quotes_bulk_helpers(storage):
    storage.quotes.save_many({
        "geram18": _quote("geram18", 1.0, 10.0),
        "usd": _quote("usd", 2.0, 10.0),
    })
    assert storage.quotes.count() == 2
    assert set(storage.quotes.get_many(["geram18", "usd", "eur"])) == {"geram18", "usd"}
    assert set(storage.quotes.all()) == {"geram18", "usd"}
    assert storage.quotes.last_update() is not None
    assert storage.quotes.save_many({}) == 0


# ------------------------------------------------------------------ history
def test_history_records_and_dedupes(storage):
    stamp = time.time()
    assert storage.history.record_many({"geram18": _quote(price=10.0, observed_at=stamp)}) == 1
    assert storage.history.record_many({"geram18": _quote(price=10.0, observed_at=stamp)}) == 0
    assert storage.history.record_many({"geram18": _quote(price=12.0, observed_at=stamp + 1)}) == 1

    coverage = storage.history.coverage("geram18")
    assert coverage["points"] == 2
    assert coverage["span_hours"] >= 0
    assert storage.history.point_counts()["geram18"] == 2


def test_history_series_buckets_points(storage):
    now = time.time()
    for index in range(10):
        storage.history.record_many({
            "usd": _quote("usd", 100.0 + index, observed_at=now - (10 - index) * 600)
        })
    window, points = storage.history.series("usd", range_key="1D")
    assert window.key == "1D"
    assert 1 <= len(points) <= 10
    assert all(point.samples >= 1 for point in points)
    assert [point.ts for point in points] == sorted(point.ts for point in points)


def test_history_series_is_empty_without_data(storage):
    window, points = storage.history.series("usd", range_key="90D")
    assert points == []
    assert window.key == "90D"


def test_history_reference_prefers_nearest_before_cutoff(storage):
    now = time.time()
    storage.history.record_many({"usd": _quote("usd", 150.0, now - 40 * 3600)})  # دورتر از مرز
    storage.history.record_many({"usd": _quote("usd", 200.0, now - 30 * 3600)})  # نزدیک‌ترین پیش از مرز
    storage.history.record_many({"usd": _quote("usd", 100.0, now - 4000)})       # داخل بازه
    storage.history.record_many({"usd": _quote("usd", 300.0, now - 100)})        # تازه

    reference = storage.history.reference("usd", seconds=86400)
    assert reference is not None
    price, at = reference
    assert price == pytest.approx(200.0)
    assert at == pytest.approx(now - 30 * 3600, abs=1)
    assert at <= now - 86400


def test_history_reference_falls_back_to_earliest_inside_window(storage):
    now = time.time()
    storage.history.record_many({"usd": _quote("usd", 150.0, now - 60)})
    reference = storage.history.reference("usd", seconds=86400)
    assert reference is not None
    assert reference[0] == pytest.approx(150.0)


def test_history_reference_is_none_without_readings(storage):
    assert storage.history.reference("usd") is None


def test_history_available_ranges_flags_missing_data(storage):
    ranges = storage.history.available_ranges("usd")
    assert [item["key"] for item in ranges] == ["1D", "7D", "30D", "90D"]
    assert all(item["has_data"] is False for item in ranges)


def test_history_stats(storage):
    storage.history.record_many({"usd": _quote("usd", 1.0, 10.0)})
    stats = storage.history.stats()
    assert stats == {"points": 1, "assets": 1}


# ------------------------------------------------------------------ sources
def test_source_runs_latest_and_reliability(storage):
    now = time.time()
    storage.sources.record(SourceStatus("tgju", True, latency_ms=100, items=14, checked_at=now - 5))
    storage.sources.record(SourceStatus("tgju", False, latency_ms=50, error="timeout", checked_at=now))
    storage.sources.record(SourceStatus("coingecko", True, latency_ms=200, items=8, checked_at=now))

    latest = {status.name: status for status in storage.sources.latest()}
    assert latest["tgju"].ok is False
    assert latest["tgju"].error == "timeout"
    assert latest["coingecko"].ok is True
    assert storage.sources.last_checked() == pytest.approx(now)
    assert storage.sources.names() == ["coingecko", "tgju"]
    assert storage.sources.count() == 3

    reliability = storage.sources.reliability("tgju")
    assert reliability["attempts"] == 2
    assert reliability["success_rate"] == pytest.approx(0.5)

    history = storage.sources.history("tgju", limit=1)
    assert len(history) == 1 and history[0].checked_at == pytest.approx(now)


def test_source_reliability_without_history(storage):
    assert storage.sources.reliability("nobody")["attempts"] == 0
    assert storage.sources.reliability("nobody")["success_rate"] is None


# ---------------------------------------------------------------- watchlist
def test_watchlist_is_idempotent_and_toggleable(storage):
    assert storage.watchlist.add("u1", "usd") is True
    assert storage.watchlist.add("u1", "usd") is False
    assert storage.watchlist.add("u1", "no-such") is False
    assert storage.watchlist.has("u1", "usd") is True
    assert storage.watchlist.slugs("u1") == ["usd"]
    assert storage.watchlist.count("u1") == 1

    assert storage.watchlist.toggle("u1", "usd") is False
    assert storage.watchlist.count("u1") == 0
    assert storage.watchlist.toggle("u1", "usd") is True
    assert storage.watchlist.entries("u1")[0]["slug"] == "usd"

    storage.watchlist.add("u2", "usd")
    assert storage.watchlist.owners("usd") == ["u1", "u2"]
    assert storage.watchlist.clear("u1") == 1
    assert storage.watchlist.count("u1") == 0
    assert storage.watchlist.count("u2") == 1
    assert storage.watchlist.remove("u2", "eur") is False


# ------------------------------------------------------------------- alerts
def test_alert_rules_are_unique_per_identity(storage):
    first = storage.alerts.add("usd", AlertKind.ABOVE, 300_000, owner="u1")
    again = storage.alerts.add("usd", AlertKind.ABOVE, 300_000, owner="u1")
    other = storage.alerts.add("usd", AlertKind.ABOVE, 300_000, owner="u2")
    different = storage.alerts.add("usd", AlertKind.BELOW, 300_000, owner="u1")

    assert first.id == again.id
    assert storage.alerts.count() == 3
    assert other.id != first.id
    assert different.id != first.id


def test_alert_rule_lifecycle(storage):
    rule = storage.alerts.add("geram18", AlertKind.PCT_MOVE, 2.5, owner="u1", note="نوسان")
    assert storage.alerts.require(rule.id).note == "نوسان"
    assert len(storage.alerts.active()) == 1
    assert storage.alerts.count(owner="u1") == 1
    assert storage.alerts.count(owner="other") == 0

    paused = storage.alerts.set_status(rule.id, AlertStatus.PAUSED)
    assert paused.status is AlertStatus.PAUSED
    assert storage.alerts.active() == []
    assert storage.alerts.list(status=AlertStatus.PAUSED)[0].id == rule.id
    assert [item.id for item in storage.alerts.list(slug="geram18")] == [rule.id]
    assert storage.alerts.list(slug="usd") == []

    storage.alerts.mark_fired(rule.id, 123.0)
    fired = storage.alerts.get(rule.id)
    assert fired.fired_count == 1
    assert fired.last_price == pytest.approx(123.0)
    assert fired.last_fired_at is not None

    storage.alerts.mark_checked(rule.id, 130.0)
    assert storage.alerts.get(rule.id).last_price == pytest.approx(130.0)
    assert storage.alerts.get(rule.id).fired_count == 1

    assert storage.alerts.delete(rule.id) is True
    assert storage.alerts.delete(rule.id) is False
    with pytest.raises(RuleNotFound):
        storage.alerts.require(rule.id)


def test_alert_rules_delete_by_slug(storage):
    storage.alerts.add("usd", AlertKind.ABOVE, 1, owner="u1")
    storage.alerts.add("usd", AlertKind.BELOW, 1, owner="u1")
    storage.alerts.add("eur", AlertKind.ABOVE, 1, owner="u1")
    assert storage.alerts.delete_by_slug("usd", owner="u1") == 2
    assert storage.alerts.count() == 1


def test_alert_events_log_and_filters(storage):
    rule = storage.alerts.add("usd", AlertKind.ABOVE, 100, owner="u1")
    now = time.time()
    storage.alerts.log_event(
        slug="usd", kind="above", price=110, threshold=100,
        message="پیام", rule_id=rule.id, owner="u1", at=now,
    )
    storage.alerts.log_event(
        slug="usd", kind="above", price=111, threshold=100, message="مهار",
        rule_id=rule.id, owner="u1", suppressed=True, reason="خنک‌شدن", at=now + 1,
    )
    storage.alerts.log_event(
        slug="eur", kind="above", price=1, threshold=1, message="دیگر", owner="u1", at=now + 2
    )

    assert storage.alerts.events_count() == 3
    assert storage.alerts.events_count(since=now + 1) == 2
    assert storage.alerts.events_count(owner="u1") == 3
    assert len(storage.alerts.events(slug="usd")) == 2
    assert len(storage.alerts.events(include_suppressed=False)) == 2
    assert storage.alerts.events(slug="usd")[0].suppressed is True

    last = storage.alerts.last_event_for(rule.id)
    assert last is not None and last.suppressed is True
    assert storage.alerts.last_event_for(999_999) is None


def test_alert_events_are_pruned(storage):
    for index in range(10):
        storage.alerts.log_event(
            slug="usd", kind="above", price=float(index), threshold=0,
            message=f"m{index}", at=1000 + index,
        )
    removed = storage.alerts.prune_events(4)
    assert removed == 6
    assert storage.alerts.events_count() == 4
    remaining = storage.alerts.events(limit=10)
    assert remaining[0].message == "m9"
    assert storage.alerts.prune_events(100) == 0


def test_alert_stats(storage):
    rule = storage.alerts.add("usd", AlertKind.ABOVE, 100, owner="u1")
    storage.alerts.log_event(slug="usd", kind="above", price=1, threshold=0, message="x", rule_id=rule.id)
    stats = storage.alerts.stats()
    assert stats["rules"] == 1
    assert stats["active_rules"] == 1
    assert stats["events_24h"] == 1


def test_prune_removes_old_readings_only(storage):
    old = time.time() - 400 * 86400
    storage.history.record_many({"usd": _quote("usd", 1.0, old)})
    storage.history.record_many({"eur": _quote("eur", 2.0, time.time())})
    storage.sources.record(SourceStatus("tgju", True, checked_at=old))

    result = storage.prune(retention_days=30)
    assert result["readings"] == 1
    assert result["source_runs"] == 1
    assert storage.history.stats()["points"] == 1


def test_transaction_rolls_back_on_error(storage):
    with pytest.raises(RuntimeError):
        with storage.transaction() as connection:
            connection.execute(
                "INSERT INTO watchlist (owner, slug, created_at) VALUES ('u', 'usd', 1)"
            )
            raise RuntimeError("boom")
    assert storage.watchlist.count("u") == 0
