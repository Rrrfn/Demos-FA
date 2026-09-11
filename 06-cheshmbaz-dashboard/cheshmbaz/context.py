# -*- coding: utf-8 -*-
"""زمینهٔ برنامه — تنها جایی که لایه‌ها به هم وصل می‌شوند.

این ماژول مرز بین ساخت و استفاده است: هیچ ماژول دیگری مجبور نیست بداند
سرویس قیمت از کجا ساخته می‌شود. ساختن زمینه هیچ عارضهٔ جانبی ندارد — شبکه
نمی‌زند و زمان‌بند را روشن نمی‌کند. راه‌اندازی عمداً جدا است تا تست‌ها بتوانند
فقط آن بخشی را بسازند که لازم دارند.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Config, load_config
from .providers import build_providers
from .providers.base import BaseProvider, HttpClient
from .scheduler import Scheduler
from .services.alerts import AlertEngine
from .services.collector import Collector, seed_registry
from .services.market import MarketService
from .storage import Storage

log = logging.getLogger("cheshmbaz.context")


@dataclass
class AppContext:
    """همهٔ اجزای زندهٔ برنامه در یک جا."""

    config: Config
    storage: Storage
    http: HttpClient
    collector: Collector
    market: MarketService
    engine: AlertEngine
    scheduler: Scheduler
    _started: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------- build
    @classmethod
    def build(
        cls,
        config: Config | None = None,
        *,
        storage: Storage | None = None,
        providers: dict[str, BaseProvider] | None = None,
        http: HttpClient | None = None,
    ) -> "AppContext":
        """ساخت زمینه. هیچ واکشی شبکه‌ای انجام نمی‌شود."""
        config = config or load_config()
        if storage is None:
            config.ensure_dirs()
            storage = Storage(config.db_path)
        client = http or HttpClient(config.data)
        collector = Collector(config, storage, providers=providers, http=client)
        market = MarketService(config=config, storage=storage, collector=collector)
        engine = AlertEngine(config, storage, market)
        scheduler = Scheduler(config, collector, market, engine)
        return cls(
            config=config, storage=storage, http=client, collector=collector,
            market=market, engine=engine, scheduler=scheduler,
        )

    # --------------------------------------------------------------- lifecycle
    def storage_ready(self) -> None:
        """آماده‌سازی پایگاه داده بدون روشن‌کردن زمان‌بند (برای CLI و تست)."""
        seed_registry(self.storage)

    def bootstrap(self) -> None:
        """آماده‌سازی پایگاه داده و روشن‌کردن زمان‌بند در صورت فعال بودن."""
        seed_registry(self.storage)
        self.storage.prune(self.config.data.history_retention_days)
        if self.config.collector.enabled:
            self.scheduler.start()
        else:
            log.info("collector disabled by configuration")

    def shutdown(self) -> None:
        self.scheduler.stop()
        self.storage.close()

    # ------------------------------------------------------------------ health
    def health(self) -> dict:
        """وضعیت سرویس — از دادهٔ ثبت‌شده، بدون واکشی شبکه."""
        quotes = self.storage.quotes.all()
        newest = self.storage.quotes.last_update()
        return {
            "status": "ok",
            "service": "cheshmbaz-dashboard",
            "environment": self.config.env,
            "engine_ready": True,
            "scheduler": self.scheduler.status(),
            "database": self.storage.stats(),
            "quotes": len(quotes),
            "last_update": newest,
            "providers": self.collector.provider_health(),
        }


def build_context(**kwargs) -> AppContext:
    """میان‌بر ساخت زمینه."""
    return AppContext.build(**kwargs)


__all__ = ["AppContext", "build_context"]
