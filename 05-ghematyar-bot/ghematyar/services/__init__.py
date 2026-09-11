# -*- coding: utf-8 -*-
"""لایهٔ سرویس — منطق محصول روی ذخیره‌سازی و ارائه‌دهنده‌ها."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..storage import Storage
from .alerts import AlertService, NotificationDecision
from .charts import ChartUnavailable, render_price_chart, render_price_chart_async
from .market import MarketService
from .monitor import AlertMonitor, CallbackNotifier, MonitorResult, Notifier

__all__ = [
    "AlertService",
    "AlertMonitor",
    "CallbackNotifier",
    "ChartUnavailable",
    "MarketService",
    "MonitorResult",
    "NotificationDecision",
    "Services",
    "build_services",
    "render_price_chart",
    "render_price_chart_async",
]


@dataclass(slots=True)
class Services:
    """مجموعهٔ سرویس‌های آماده برای تزریق به لایهٔ ربات."""

    config: Config
    storage: Storage
    market: MarketService
    alerts: AlertService

    async def close(self) -> None:
        await self.market.close()
        self.storage.close()


def build_services(config: Config) -> Services:
    """ساخت پایگاه داده، سرویس بازار و سرویس هشدار.

    تنها نقطهٔ سیم‌کشی برنامه است؛ نه هندلر ربات و نه لایهٔ وب چیزی
    می‌سازند — همه از این‌جا تغذیه می‌شوند.
    """
    config.ensure_dirs()
    database = Storage(config.db_path)
    market = MarketService(config, database)
    alerts = AlertService(
        config,
        alerts=database.alerts,
        events=database.events,
        users=database.users,
    )
    return Services(config=config, storage=database, market=market, alerts=alerts)
