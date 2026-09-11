# -*- coding: utf-8 -*-
"""تست موتور هشدار — سیاست‌ها، ضد سیل و ضد تکرار."""
from __future__ import annotations

import time

import pytest

from ghematyar.core.errors import AlertLimitReached, AlertNotFound, DuplicateAlert
from ghematyar.core.models import Freshness, Quote
from ghematyar.services import AlertService
from ghematyar.storage import AlertDirection, AlertStatus


def quote(slug: str = "usd", price: float = 250_000.0, *, fresh: bool = True) -> Quote:
    return Quote(
        slug=slug, price=price, source="test",
        freshness=Freshness.LIVE if fresh else Freshness.UNAVAILABLE,
        fetched_at=time.time(),
    )


class TestCondition:
    """ارزیابی شرط بالای/زیر."""

    def test_above_triggers_at_or_above(self, alert_service: AlertService):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        assert alert_service.evaluate(alert, quote(price=250_000)) is True
        assert alert_service.evaluate(alert, quote(price=249_999)) is False

    def test_below_triggers_at_or_below(self, alert_service: AlertService):
        alert = alert_service.create(1, "usd", AlertDirection.BELOW, 250_000)
        assert alert_service.evaluate(alert, quote(price=250_000)) is True
        assert alert_service.evaluate(alert, quote(price=250_001)) is False

    def test_missing_quote_never_triggers(self, alert_service: AlertService):
        """نبود داده نباید به اعلان تبدیل شود."""
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 1)
        assert alert_service.evaluate(alert, None) is False
        assert alert_service.evaluate(alert, quote(fresh=False)) is False


class TestCreationPolicy:
    """سیاست ساخت هشدار."""

    def test_create_records_event(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        rows = storage.events.list_recent(1)
        assert rows and rows[0]["kind"] == "created"
        assert rows[0]["alert_id"] == alert.id

    def test_duplicate_rejected(self, alert_service: AlertService):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        with pytest.raises(DuplicateAlert):
            alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)

    def test_limit_reached(self, alert_service: AlertService):
        for index in range(alert_service.config.alerts.max_per_user):
            alert_service.create(1, "usd", AlertDirection.ABOVE, 100.0 + index)
        with pytest.raises(AlertLimitReached):
            alert_service.create(1, "usd", AlertDirection.ABOVE, 999_999)

    def test_usage_reports_capacity(self, alert_service: AlertService):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        used, limit = alert_service.usage(1)
        assert used == 1 and limit == alert_service.config.alerts.max_per_user


class TestManagement:
    """مدیریت هشدارها."""

    def test_toggle_records_event(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        toggled = alert_service.toggle(1, alert.id)
        assert toggled.status is AlertStatus.PAUSED
        kinds = [r["kind"] for r in storage.events.list_recent(1)]
        assert "updated" in kinds

    def test_remove_missing_raises(self, alert_service: AlertService):
        with pytest.raises(AlertNotFound):
            alert_service.remove(1, 4242)

    def test_remove_logs_event(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        assert alert_service.remove(1, alert.id) is True
        assert any(r["kind"] == "deleted" for r in storage.events.list_recent(1))

    def test_get_enforces_ownership(self, alert_service: AlertService):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        with pytest.raises(AlertNotFound):
            alert_service.get(2, alert.id)

    def test_clear_removes_all(self, alert_service: AlertService):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        alert_service.create(1, "eur", AlertDirection.ABOVE, 200_000)
        assert alert_service.clear(1) == 2
        assert alert_service.list(1) == []


class TestNotificationPolicy:
    """درِ اعلان: چه زمانی اجازهٔ ارسال داریم؟"""

    def test_allowed_when_condition_met(self, alert_service: AlertService):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        decision = alert_service.decide_notification(alert, quote(price=260_000))
        assert decision.allowed is True

    def test_paused_alert_is_not_notified(self, alert_service: AlertService):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        alert_service.toggle(1, alert.id)
        paused = alert_service.get(1, alert.id)
        decision = alert_service.decide_notification(paused, quote(price=260_000))
        assert decision.allowed is False
        assert decision.reason == "status"

    def test_cooldown_blocks_rapid_repeats(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000,
                                     one_shot=False, cooldown_seconds=600)
        storage.alerts.mark_notified(alert.id, 260_000, one_shot=False)
        refreshed = alert_service.get(1, alert.id)
        decision = alert_service.decide_notification(refreshed, quote(price=260_000))
        assert decision.allowed is False
        assert decision.reason == "cooldown"

    def test_cooldown_expires(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000,
                                     one_shot=False, cooldown_seconds=600)
        storage.alerts.mark_notified(alert.id, 260_000, one_shot=False)
        # آخرین اعلان را به گذشته منتقل می‌کنیم
        with storage.database.transaction() as conn:
            conn.execute("UPDATE alerts SET last_notified_at = ? WHERE id = ?",
                         (time.time() - 700, alert.id))
        refreshed = alert_service.get(1, alert.id)
        assert alert_service.decide_notification(refreshed, quote(price=260_000)).allowed is True

    def test_hourly_cap_blocks_flood(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000,
                                     one_shot=False, cooldown_seconds=0)
        cap = alert_service.config.alerts.max_notifications_per_hour
        for _ in range(cap):
            storage.events.add(1, "usd", "triggered")
        decision = alert_service.decide_notification(alert, quote(price=260_000))
        assert decision.allowed is False
        assert decision.reason == "hourly_cap"

    def test_hourly_cap_is_per_user(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000,
                                     one_shot=False, cooldown_seconds=0)
        cap = alert_service.config.alerts.max_notifications_per_hour
        for _ in range(cap):
            storage.events.add(2, "usd", "triggered")  # کاربر دیگر
        assert alert_service.decide_notification(alert, quote(price=260_000)).allowed is True

    def test_muted_user_is_respected(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        storage.users.touch(1)
        storage.users.set_notifications(1, False)
        decision = alert_service.decide_notification(alert, quote(price=260_000))
        assert decision.allowed is False
        assert decision.reason == "user_muted"

    def test_unusable_quote_blocks_notification(self, alert_service: AlertService):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 100_000)
        decision = alert_service.decide_notification(alert, quote(fresh=False))
        assert decision.allowed is False
        assert decision.reason == "unusable_quote"


class TestEventRecording:
    """ثبت رخدادها برای شفافیت."""

    def test_record_triggered_increments(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        alert_service.record_triggered(alert, quote(price=260_000))
        refreshed = alert_service.get(1, alert.id)
        assert refreshed.triggered_count == 1
        assert refreshed.status is AlertStatus.TRIGGERED  # یک‌بار مصرف
        rows = storage.events.list_recent(1)
        assert rows[0]["kind"] == "triggered"
        assert rows[0]["price"] == pytest.approx(260_000)

    def test_suppressed_is_logged(self, alert_service: AlertService, storage):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        decision = alert_service.decide_notification(alert, quote(price=100.0))
        alert_service.record_suppressed(alert, quote(price=260_000), decision)
        kinds = [r["kind"] for r in storage.events.list_recent(1)]
        assert "suppressed" in kinds

    def test_failure_can_disable_alert(self, alert_service: AlertService):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        threshold = alert_service.config.alerts.disable_after_failures
        status = None
        for index in range(threshold):
            status = alert_service.record_failure(alert, "blocked")
        assert status is AlertStatus.DISABLED
        refreshed = alert_service.get(1, alert.id)
        assert refreshed.status is AlertStatus.DISABLED

    def test_recent_events_listing(self, alert_service: AlertService):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        assert len(alert_service.recent_events(1)) >= 1
