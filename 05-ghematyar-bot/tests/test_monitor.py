# -*- coding: utf-8 -*-
"""تست پایشگر پس‌زمینه.

چرخهٔ کامل «شرط برقرار شد → اعلان رفت» بدون شبکه و بدون تلگرام آزموده
می‌شود؛ همین کد در تولید با Notifier تلگرامی اجرا می‌شود.
"""
from __future__ import annotations

import pytest

from ghematyar.core.errors import PriceUnavailable, ProviderError
from ghematyar.core.models import Quote
from ghematyar.services import AlertMonitor, AlertService, CallbackNotifier, MarketService
from ghematyar.storage import AlertDirection, AlertStatus


def quote(slug: str = "usd", price: float = 250_000.0) -> Quote:
    import time

    now = time.time()
    return Quote(slug=slug, price=price, source="test", observed_at=now, fetched_at=now)


def build_monitor(config, storage, alert_service, provider, notifier=None):
    market = MarketService(config, storage, providers={"tgju": provider})
    if notifier is None:
        notifier = CallbackNotifier(lambda alert, q: None)
    return AlertMonitor(config, market, alert_service, notifier), market


class TestTriggering:
    """فعال شدن هشدار."""

    @pytest.mark.anyio
    async def test_alert_fires_when_condition_met(self, config, storage, alert_service, scripted_provider):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        notifier = CallbackNotifier(lambda alert, q: None)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}), notifier,
        )
        result = await monitor.check_once()
        assert result.sent == 1
        assert result.matched == 1
        assert notifier.sent == [(1, "usd")]

    @pytest.mark.anyio
    async def test_alert_does_not_fire_below_threshold(self, config, storage, alert_service, scripted_provider):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=240_000)}),
        )
        result = await monitor.check_once()
        assert result.sent == 0
        assert result.matched == 0

    @pytest.mark.anyio
    async def test_one_shot_alert_is_consumed(self, config, storage, alert_service, scripted_provider):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000, one_shot=True)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
        )
        await monitor.check_once()
        refreshed = alert_service.get(1, alert.id)
        assert refreshed.status is AlertStatus.TRIGGERED

        # دور بعد نباید دوباره اعلان بدهد
        second = await monitor.check_once()
        assert second.sent == 0

    @pytest.mark.anyio
    async def test_recurring_alert_fires_again_after_cooldown(self, config, storage, alert_service, scripted_provider):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000,
                                     one_shot=False, cooldown_seconds=0)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
        )
        first = await monitor.check_once()
        second = await monitor.check_once()
        assert first.sent == 1 and second.sent == 1
        refreshed = alert_service.get(1, alert.id)
        assert refreshed.triggered_count == 2

    @pytest.mark.anyio
    async def test_multiple_alerts_are_evaluated(self, config, storage, alert_service, scripted_provider):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        alert_service.create(2, "usd", AlertDirection.BELOW, 300_000)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
        )
        result = await monitor.check_once()
        assert result.checked == 2
        assert result.sent == 2


class TestSuppression:
    """سرکوب اعلان — ضد سیل و ضد تکرار."""

    @pytest.mark.anyio
    async def test_cooldown_suppresses_repeat(self, config, storage, alert_service, scripted_provider):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000,
                             one_shot=False, cooldown_seconds=3600)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
        )
        await monitor.check_once()
        second = await monitor.check_once()
        assert second.sent == 0
        assert second.suppressed == 1
        assert second.skipped_reasons.get("cooldown") == 1

    @pytest.mark.anyio
    async def test_hourly_cap_stops_flood(self, config, storage, scripted_provider, tuned):
        cap = config.alerts.max_notifications_per_hour
        # سقف هشدار هر کاربر باید بالاتر از سقف اعلان ساعتی باشد تا این تست
        # واقعاً سقف اعلان را بسنجد، نه سقف هشدار را.
        service = AlertService(
            tuned(config, alerts={"max_per_user": cap + 2}),
            storage.alerts,
            storage.events,
            storage.users,
        )
        # چند هشدار روی یک قلم با فاصلهٔ صفر
        for index in range(cap + 2):
            service.create(1, "usd", AlertDirection.ABOVE, 100_000 + index,
                           one_shot=False, cooldown_seconds=0)
        monitor, _ = build_monitor(
            config, storage, service,
            scripted_provider("tgju", {"usd": quote(price=999_999)}),
        )
        result = await monitor.check_once()
        assert result.sent == cap
        assert result.suppressed == 2
        assert result.skipped_reasons.get("hourly_cap") == 2

    @pytest.mark.anyio
    async def test_paused_alert_is_skipped(self, config, storage, alert_service, scripted_provider):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000)
        alert_service.toggle(1, alert.id)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
        )
        result = await monitor.check_once()
        assert result.sent == 0
        assert result.checked == 0  # هشدار خاموش حتی پایش هم نمی‌شود

    @pytest.mark.anyio
    async def test_suppression_is_logged(self, config, storage, alert_service, scripted_provider):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000,
                             one_shot=False, cooldown_seconds=3600)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
        )
        await monitor.check_once()
        await monitor.check_once()
        kinds = [row["kind"] for row in storage.events.list_recent(1, limit=10)]
        assert "suppressed" in kinds


class TestFailures:
    """خطای ارسال و نبود داده."""

    @pytest.mark.anyio
    async def test_send_failure_is_recorded(self, config, storage, alert_service, scripted_provider):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000, one_shot=False)

        def boom(_alert, _quote):
            raise RuntimeError("telegram down")

        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
            CallbackNotifier(boom),
        )
        result = await monitor.check_once()
        assert result.failed == 1
        assert result.sent == 0
        refreshed = alert_service.get(1, alert.id)
        assert refreshed.failure_count == 1
        assert refreshed.status is AlertStatus.ACTIVE

    @pytest.mark.anyio
    async def test_repeated_failures_disable_alert(self, config, storage, alert_service, scripted_provider):
        alert = alert_service.create(1, "usd", AlertDirection.ABOVE, 250_000, one_shot=False)

        def boom(_alert, _quote):
            raise RuntimeError("telegram down")

        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote(price=260_000)}),
            CallbackNotifier(boom),
        )
        for _ in range(config.alerts.disable_after_failures):
            await monitor.check_once()
        refreshed = alert_service.get(1, alert.id)
        assert refreshed.status is AlertStatus.DISABLED
        # پس از غیرفعال شدن، دیگر پایش نمی‌شود
        assert (await monitor.check_once()).checked == 0

    @pytest.mark.anyio
    async def test_unavailable_prices_never_notify(self, config, storage, alert_service, scripted_provider):
        """قطع منبع نباید به اعلان ساختگی تبدیل شود."""
        alert_service.create(1, "usd", AlertDirection.ABOVE, 1)
        notifier = CallbackNotifier(lambda alert, q: None)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", ProviderError("tgju", "down")), notifier,
        )
        result = await monitor.check_once()
        assert result.unavailable is True
        assert result.sent == 0
        assert notifier.sent == []

    @pytest.mark.anyio
    async def test_price_unavailable_marks_round(self, config, storage, alert_service, scripted_provider):
        alert_service.create(1, "usd", AlertDirection.ABOVE, 1)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", PriceUnavailable(["دلار"])),
        )
        result = await monitor.check_once()
        assert result.unavailable is True
        assert result.skipped_reasons.get("prices_unavailable") == 1

    @pytest.mark.anyio
    async def test_no_alerts_is_a_noop(self, config, storage, alert_service, scripted_provider):
        provider = scripted_provider("tgju", {"usd": quote()})
        monitor, _ = build_monitor(config, storage, alert_service, provider)
        result = await monitor.check_once()
        assert result.checked == 0
        assert provider.calls == []  # بدون هشدار، منبع هم صدا زده نمی‌شود

    @pytest.mark.anyio
    async def test_missing_asset_quote_skips_alert(self, config, storage, alert_service, scripted_provider):
        alert_service.create(1, "eur", AlertDirection.ABOVE, 1)
        monitor, _ = build_monitor(
            config, storage, alert_service,
            scripted_provider("tgju", {"usd": quote()}),
        )
        result = await monitor.check_once()
        assert result.sent == 0
        assert result.skipped_reasons.get("quote_unusable") == 1


class TestLoopLifecycle:
    """چرخهٔ حلقه."""

    @pytest.mark.anyio
    async def test_stop_ends_loop(self, config, storage, alert_service, scripted_provider):
        import asyncio

        monitor, _ = build_monitor(
            config, storage, alert_service, scripted_provider("tgju", {"usd": quote()})
        )
        task = asyncio.create_task(monitor.run())
        await asyncio.sleep(0.05)
        monitor.stop()
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done()
