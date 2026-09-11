# -*- coding: utf-8 -*-
"""آزمون موتور هشدار — شرط‌ها، محافظ‌ها و صداقت در برابر دادهٔ کهنه.

مهم‌ترین قاعدهٔ این لایه: **قیمت کهنه هرگز هشدار «الان» نمی‌سازد.** اگر
قاعده‌ای روی دادهٔ منقضی فعال شود، کاربر پیامی می‌گیرد که انگار همین حالا
اتفاق افتاده — و این بدترین نوع خطا در یک ابزار مالی است.
"""
from __future__ import annotations

import time

import pytest

from cheshmbaz.core.errors import UnknownAsset, ValidationError
from cheshmbaz.core.models import AlertKind, AlertStatus, Quote
from cheshmbaz.services.alerts import RATE_MAX_EVENTS, AlertEngine
from cheshmbaz.services.market import MarketService


# ------------------------------------------------------------------ helpers
def _market(storage, config) -> MarketService:
    return MarketService(config=config, storage=storage, collector=None)  # type: ignore[arg-type]


def _engine(storage, config):
    return AlertEngine(config, storage, _market(storage, config))


def _store(storage, slug: str, price: float, *, age_seconds: float = 30.0, **kwargs) -> Quote:
    stamp = time.time() - age_seconds
    quote = Quote(
        slug=slug,
        price=price,
        unit="usd" if slug in {"bitcoin", "ethereum"} else "toman",
        source="test",
        observed_at=stamp,
        fetched_at=stamp,
        **kwargs,
    )
    storage.quotes.save_many({slug: quote})
    return quote


# ------------------------------------------------------------------- create
def test_create_returns_persisted_rule(storage, config):
    engine = _engine(storage, config)
    rule = engine.create("usd", AlertKind.ABOVE, 300_000, owner="u1", note="گارد فروش")
    assert rule.id > 0
    assert rule.status is AlertStatus.ACTIVE
    assert rule.cooldown_seconds == config.alerts.cooldown_seconds
    assert storage.alerts.require(rule.id).note == "گارد فروش"


def test_create_rejects_unknown_asset(storage, config):
    with pytest.raises(UnknownAsset):
        _engine(storage, config).create("planet-x", AlertKind.ABOVE, 10)


@pytest.mark.parametrize("threshold", [0, -5, 1000.5])
def test_create_rejects_impossible_pct_threshold(storage, config, threshold):
    error = pytest.raises(ValidationError)
    with error as captured:
        _engine(storage, config).create("usd", AlertKind.PCT_MOVE, threshold)
    assert captured.value.to_payload()["field"] == "threshold"


def test_create_rejects_sub_unit_threshold_for_integer_asset(storage, config):
    """قلمی که اعشار ندارد نمی‌تواند آستانهٔ کسری داشته باشد (تومان)."""
    with pytest.raises(ValidationError) as captured:
        _engine(storage, config).create("geram18", AlertKind.ABOVE, 0.5)
    assert captured.value.to_payload()["field"] == "threshold"


def test_create_accepts_fractional_threshold_for_fractional_asset(storage, config):
    """قلمی که اعشار دارد (مانند سولانا) آستانهٔ کسری می‌پذیرد."""
    rule = _engine(storage, config).create("solana", AlertKind.ABOVE, 0.5)
    assert rule.threshold == pytest.approx(0.5)


def test_create_enforces_rule_cap_per_owner(storage, config):
    engine = _engine(storage, config)
    for index in range(config.alerts.max_rules):
        engine.create("usd", AlertKind.ABOVE, 1 + index, owner="u1")
    with pytest.raises(ValidationError) as captured:
        engine.create("usd", AlertKind.ABOVE, 999, owner="u1")
    assert captured.value.to_payload()["field"] == "rules"
    # مالک دیگر سقف خودش را دارد
    assert engine.create("usd", AlertKind.ABOVE, 999, owner="u2").id > 0


def test_custom_cooldown_can_be_zero_and_is_never_negative(storage, config):
    engine = _engine(storage, config)
    assert engine.create("usd", AlertKind.ABOVE, 1, cooldown_seconds=0).cooldown_seconds == 0
    assert engine.create("usd", AlertKind.ABOVE, 2, cooldown_seconds=-99).cooldown_seconds == 0


# ------------------------------------------------------------------ matching
def test_above_below_and_pct_conditions():
    rule = lambda kind, threshold: type(  # noqa: E731 - خوانایی بهتر در این تست
        "R", (), {"kind": kind, "threshold": threshold}
    )()
    above, below = 200_000, 100_000
    quote_up = Quote(slug="usd", price=250_000, change_pct=3.0)
    quote_flat = Quote(slug="usd", price=250_000, change_pct=None)

    assert AlertEngine.matches(rule(AlertKind.ABOVE, above), quote_up) is True
    assert AlertEngine.matches(rule(AlertKind.ABOVE, 300_000), quote_up) is False
    assert AlertEngine.matches(rule(AlertKind.BELOW, below), quote_up) is False
    assert AlertEngine.matches(rule(AlertKind.PCT_MOVE, 2.0), quote_up) is True
    assert AlertEngine.matches(rule(AlertKind.PCT_MOVE, 2.0), quote_flat) is False


# ------------------------------------------------------------------ evaluate
def test_above_rule_fires_on_live_price(storage, config):
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.ABOVE, 200_000, owner="u1")

    outcome = engine.evaluate()
    assert outcome.checked == 1
    assert outcome.notified == 1
    assert outcome.fired[0].slug == "usd"
    assert outcome.fired[0].suppressed is False

    events = storage.alerts.events()
    assert len(events) == 1
    assert events[0].message
    assert not any(char.isdigit() and char.isascii() for char in events[0].message)


def test_below_rule_fires_downward(storage, config):
    _store(storage, "usd", 90_000)
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.BELOW, 100_000)
    outcome = engine.evaluate()
    assert outcome.notified == 1
    assert "افتاد" in outcome.fired[0].message


def test_pct_move_rule_uses_real_change_only(storage, config):
    _store(storage, "bitcoin", 77_000, change_pct=4.2, change_basis="۲۴ ساعتهٔ منبع")
    engine = _engine(storage, config)
    engine.create("bitcoin", AlertKind.PCT_MOVE, 3.0, cooldown_seconds=0)
    assert [event.slug for event in engine.evaluate().fired] == ["bitcoin"]

    # قلمی که منبعش درصد نمی‌دهد و تاریخچه‌ای هم ندارد، نباید هشدار نوسان بسازد
    _store(storage, "eur", 300_000)
    engine.create("eur", AlertKind.PCT_MOVE, 1.0, cooldown_seconds=0)
    outcome = engine.evaluate()
    assert outcome.checked == 2
    assert storage.alerts.events(slug="eur") == []


def test_stale_price_never_fires_and_is_reported(storage, config):
    """قلب این فایل: قیمت منقضی هشدار نمی‌سازد، ولی بی‌صدا هم نمی‌ماند."""
    _store(storage, "usd", 250_000, age_seconds=300_000)
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.ABOVE, 1, owner="u1")

    outcome = engine.evaluate()
    assert outcome.notified == 0
    assert outcome.fired == []
    assert outcome.skipped_stale == ["usd"]
    assert storage.alerts.events_count() == 0
    # ولی قیمت در قاعده ثبت می‌شود تا پنل بتواند «چقدر مانده» را نشان دهد
    assert storage.alerts.active()[0].last_price == pytest.approx(250_000)


def test_asset_without_any_quote_is_reported_as_missing(storage, config):
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.ABOVE, 1)
    outcome = engine.evaluate()
    assert outcome.checked == 1
    assert outcome.skipped_missing == ["usd"]
    assert outcome.notified == 0


def test_rule_that_does_not_match_only_updates_price(storage, config):
    _store(storage, "usd", 150_000)
    engine = _engine(storage, config)
    rule = engine.create("usd", AlertKind.ABOVE, 500_000)
    outcome = engine.evaluate()
    assert outcome.notified == 0
    assert storage.alerts.events_count() == 0
    refreshed = storage.alerts.get(rule.id)
    assert refreshed.last_price == pytest.approx(150_000)
    assert refreshed.fired_count == 0


def test_no_rules_means_no_work(storage, config):
    outcome = _engine(storage, config).evaluate()
    assert outcome.checked == 0
    assert outcome.notified == 0


def test_paused_rule_is_not_evaluated(storage, config):
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    rule = engine.create("usd", AlertKind.ABOVE, 1)
    storage.alerts.set_status(rule.id, AlertStatus.PAUSED)
    assert engine.evaluate().checked == 0


# ------------------------------------------------------------------ cooldown
def test_cooldown_suppresses_repeat_and_records_why(storage, config):
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.ABOVE, 1, owner="u1", cooldown_seconds=3600)

    first = engine.evaluate()
    assert first.notified == 1

    second = engine.evaluate()
    assert second.notified == 0
    assert len(second.suppressed) == 1
    assert second.suppressed[0].suppressed is True
    assert "خنک‌شدن" in second.suppressed[0].reason

    # هر دو رخداد در دفتر می‌مانند — پنهان‌کردن مهارشدن، ابهام می‌سازد
    assert storage.alerts.events_count() == 2


def test_zero_cooldown_allows_repeat_firing(storage, config):
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.ABOVE, 1, cooldown_seconds=0)
    assert engine.evaluate().notified == 1
    assert engine.evaluate().notified == 1


# ------------------------------------------------------------------ one-shot
def test_one_shot_rule_pauses_itself_after_firing(storage, config):
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    rule = engine.create("usd", AlertKind.ABOVE, 1, one_shot=True, cooldown_seconds=0)

    assert engine.evaluate().notified == 1
    assert storage.alerts.get(rule.id).status is AlertStatus.PAUSED
    assert engine.evaluate().notified == 0


# --------------------------------------------------------------- rate limit
def test_rate_limit_caps_notifications_per_owner(storage, config):
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    for index in range(RATE_MAX_EVENTS + 1):
        engine.create("usd", AlertKind.ABOVE, 1 + index, owner="u1", cooldown_seconds=0)

    outcome = engine.evaluate()
    assert outcome.notified == RATE_MAX_EVENTS
    assert len(outcome.suppressed) == 1
    assert "سقف نرخ" in outcome.suppressed[0].reason


def test_rate_limit_is_per_owner_not_global(storage, config):
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    for index in range(RATE_MAX_EVENTS):
        engine.create("usd", AlertKind.ABOVE, 1 + index, owner="u1", cooldown_seconds=0)
    other = engine.create("usd", AlertKind.ABOVE, 500, owner="u2", cooldown_seconds=0)

    engine.evaluate()
    assert storage.alerts.get(other.id).fired_count == 1


# ------------------------------------------------------------------ preview
def test_preview_says_whether_it_would_fire_now(storage, config):
    _store(storage, "usd", 200_000)
    engine = _engine(storage, config)

    firing = engine.preview(AlertKind.ABOVE, "usd", 100_000)
    assert firing["would_fire"] is True
    assert firing["current_price_text"]

    quiet = engine.preview(AlertKind.ABOVE, "usd", 900_000)
    assert quiet["would_fire"] is False

    # پیش‌نمایش هیچ قاعده‌ای نمی‌سازد
    assert storage.alerts.count() == 0


def test_preview_explains_stale_and_missing_feeds(storage, config):
    _store(storage, "usd", 200_000, age_seconds=300_000)
    engine = _engine(storage, config)
    stale = engine.preview(AlertKind.ABOVE, "usd", 1)
    assert stale["would_fire"] is False
    assert "تازه نیست" in stale["reason"]

    missing = engine.preview(AlertKind.ABOVE, "eur", 1)
    assert missing["would_fire"] is False
    assert "ثبت نشده" in missing["reason"]


# -------------------------------------------------------------------- views
def test_rules_view_annotates_distance_and_freshness(storage, config):
    _store(storage, "usd", 200_000)
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.ABOVE, 250_000, owner="u1")
    engine.create("usd", AlertKind.PCT_MOVE, 2.0, owner="u1", note="نوسان")

    view = engine.rules_view(owner="u1")
    assert view["count"] == 2
    assert view["total"] == 2
    assert view["stats"]["rules"] == 2

    price_rule = next(item for item in view["items"] if item["kind"] == "above")
    assert price_rule["title"] == "دلار آمریکا"
    assert price_rule["current_price_text"]
    assert price_rule["is_usable"] is True
    assert price_rule["freshness"] == "live"
    assert price_rule["distance_pct"] == pytest.approx(-20.0)

    pct_rule = next(item for item in view["items"] if item["kind"] == "pct_move")
    assert pct_rule["threshold_text"].endswith("٪")
    assert pct_rule["distance_text"] == "—"  # درصدی ثبت نشده، پس فاصله نامعلوم است


def test_rules_view_without_quote_is_explicit(storage, config):
    engine = _engine(storage, config)
    engine.create("eur", AlertKind.ABOVE, 300_000)
    entry = engine.rules_view()["items"][0]
    assert entry["current_price"] is None
    assert entry["current_price_text"] == "—"
    assert entry["is_usable"] is False
    assert entry["freshness"] == "unknown"
    assert entry["distance_pct"] is None


def test_events_view_annotates_persian_price(storage, config):
    _store(storage, "usd", 200_000)
    engine = _engine(storage, config)
    rule = engine.create("usd", AlertKind.ABOVE, 1, owner="u1")
    engine.evaluate()

    view = engine.events_view(owner="u1")
    assert view["count"] == 1
    entry = view["items"][0]
    assert entry["title"] == "دلار آمریکا"
    assert entry["price_text"]
    assert entry["rule_id"] == rule.id


def test_user_facing_event_text_has_no_latin_digits(storage, config):
    """قاعدهٔ خودِ پروژه: هیچ متن قابل‌نمایشی عدد خام لاتین چاپ نمی‌کند."""
    _store(storage, "usd", 250_000)
    engine = _engine(storage, config)
    engine.create("usd", AlertKind.ABOVE, 1, owner="u1", cooldown_seconds=3600)
    engine.evaluate()
    engine.evaluate()  # بار دوم در بازهٔ خنک‌شدن مهار می‌شود

    texts = [event.message for event in storage.alerts.events()]
    texts += [event.reason for event in storage.alerts.events() if event.reason]
    assert len(texts) >= 2
    for text in texts:
        assert not any(char.isdigit() and char.isascii() for char in text), text


def test_domain_error_messages_use_persian_digits(storage, config):
    from cheshmbaz.core.errors import RuleNotFound

    engine = _engine(storage, config)
    for index in range(config.alerts.max_rules):
        engine.create("usd", AlertKind.ABOVE, 1 + index, owner="u1")
    with pytest.raises(ValidationError) as captured:
        engine.create("usd", AlertKind.ABOVE, 999, owner="u1")
    message = captured.value.to_payload()["message"]
    assert "۵۰" in message
    assert not any(char.isdigit() and char.isascii() for char in message)

    assert "۴۲" in RuleNotFound(42).message


def test_event_log_is_pruned_to_configured_cap(storage, config):
    _store(storage, "usd", 200_000)
    engine = _engine(storage, config)
    for index in range(config.alerts.max_events + 20):
        storage.alerts.log_event(
            slug="usd", kind="above", price=1.0, threshold=0.0,
            message=f"m{index}", at=1000 + index,
        )
    engine.create("usd", AlertKind.ABOVE, 1, cooldown_seconds=0)
    engine.evaluate()
    assert storage.alerts.events_count() <= config.alerts.max_events + 5
