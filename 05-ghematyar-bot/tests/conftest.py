# -*- coding: utf-8 -*-
"""فیکسچرهای مشترک تست.

هیچ تستی به شبکه یا توکن تلگرام نیاز ندارد: پایگاه داده موقت است، منابع
داده با پاسخ‌های از پیش تعیین‌شده جایگزین می‌شوند و تلگرام با یک نشست
قلابی شبیه‌سازی می‌شود.
"""
from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

# اجرای pytest از هر مسیری
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ghematyar.config import AlertsConfig, Config, DataConfig, TelegramConfig  # noqa: E402
from ghematyar.services import AlertService, MarketService, Services, build_services  # noqa: E402
from ghematyar.storage import Storage  # noqa: E402
from tests.fakes import FakeSession, ScriptedProvider, make_bot  # noqa: E402


@pytest.fixture()
def config(tmp_path, monkeypatch) -> Config:
    """پیکربندی تست با پایگاه دادهٔ موقت و آستانه‌های سریع."""
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    return Config(
        telegram=TelegramConfig(token="123456:TEST-TOKEN", webhook_base_url=""),
        data=DataConfig(
            cache_ttl=60,
            stale_after=900,
            expire_after=3600,
            request_timeout=1.0,
            max_attempts=2,
            backoff_base=0.001,
            backoff_max=0.01,
            breaker_threshold=3,
            breaker_cooldown=60,
        ),
        alerts=AlertsConfig(
            interval=1,
            max_per_user=3,
            notify_cooldown=0,
            max_notifications_per_hour=5,
            disable_after_failures=3,
        ),
        db_path=tmp_path / "test.db",
        env="testing",
    )


@pytest.fixture()
def tuned():
    """سازندهٔ پیکربندی تغییریافته.

    ``Config`` عمداً تغییرناپذیر است تا در زمان اجرا کسی آن را دست‌کاری
    نکند؛ پس تست‌ها به‌جای انتساب مستقیم، نسخهٔ تازه می‌سازند.
    """

    def _tune(config: Config, *, data=None, alerts=None, telegram=None) -> Config:
        return replace(
            config,
            data=replace(config.data, **(data or {})),
            alerts=replace(config.alerts, **(alerts or {})),
            telegram=replace(config.telegram, **(telegram or {})),
        )

    return _tune


@pytest.fixture()
def storage(config) -> Storage:
    """پایگاه دادهٔ تازه با اسکیمای کامل."""
    store = Storage(config.db_path)
    yield store
    store.close()


@pytest.fixture()
def alert_service(config, storage) -> AlertService:
    """سرویس هشدار روی پایگاه دادهٔ تست."""
    return AlertService(config, storage.alerts, storage.events, storage.users)


@pytest.fixture()
def market(config, storage) -> MarketService:
    """سرویس بازار با ارائه‌دهنده‌های تزریق‌شده (بدون شبکه)."""
    service = MarketService(config, storage, providers={})
    yield service


@pytest.fixture()
def services(config, storage, market, alert_service) -> Services:
    """مجموعهٔ سرویس‌ها برای تست هندلرها."""
    return Services(config=config, storage=storage, market=market, alerts=alert_service)


@pytest.fixture()
def scripted_provider(config):
    """سازندهٔ ارائه‌دهندهٔ سناریومحور برای تست‌های خطا."""

    def factory(name: str, script):
        return ScriptedProvider(name, script, config.data)

    return factory


@pytest.fixture()
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def bot(session: FakeSession):
    return make_bot(session)


@pytest.fixture()
def app_context(tmp_path, monkeypatch):
    """سرویس‌های واقعی (با منابع واقعی ولی بدون فراخوانی) روی db موقت."""
    monkeypatch.setenv("GHEMATYAR_DB_PATH", str(tmp_path / "app.db"))
    built = build_services(Config(db_path=tmp_path / "app.db", env="testing"))
    yield built
    built.storage.close()
    os.environ.pop("GHEMATYAR_DB_PATH", None)
