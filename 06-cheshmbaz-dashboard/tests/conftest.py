# -*- coding: utf-8 -*-
"""فیکسچرهای مشترک.

هر تست روی پایگاه دادهٔ موقت خودش اجرا می‌شود و هیچ تستی به شبکه نمی‌زند:
منابع داده با انتقال‌دهندهٔ جعلی و فیکسچرهای ضبط‌شده کار می‌کنند.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CHESHMAZ_ENV", "testing")
os.environ.setdefault("COLLECT_ENABLED", "0")
os.environ.setdefault("CHESHMAZ_ADMIN_TOKEN", "")

from cheshmbaz.config import Config, load_config  # noqa: E402
from cheshmbaz.context import AppContext  # noqa: E402
from cheshmbaz.core.models import Quote  # noqa: E402
from cheshmbaz.providers.coingecko import CoinGeckoProvider  # noqa: E402
from cheshmbaz.providers.tgju import TgjuProvider  # noqa: E402
from cheshmbaz.storage import Storage  # noqa: E402
from tests.fakes import FakeTransport, ScriptedProvider, http_with, load_json_fixture  # noqa: E402


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    """پیکربندی تست: پایگاه دادهٔ موقت، بازه‌های کوتاه، بدون توکن مدیر."""
    base = load_config()
    return base.retuned(
        env="testing",
        data_dir=tmp_path,
        db_path=tmp_path / "cheshmbaz-test.db",
        admin_token="",
        data={
            "max_attempts": 3,
            "backoff_base": 0.001,
            "backoff_max": 0.002,
            "live_within": 1800,
            "stale_after": 7200,
            "expire_after": 86400,
        },
        collector={"enabled": False, "interval_seconds": 1800},
        alerts={"cooldown_seconds": 3600, "default_pct": 2.0, "max_rules": 50, "max_events": 200},
        api={"cache_seconds": 0, "default_page_size": 10, "max_page_size": 50},
    )


@pytest.fixture()
def storage(config: Config) -> Storage:
    """پایگاه دادهٔ تست با اسکیمای ساخته‌شده."""
    return Storage(config.db_path)


@pytest.fixture()
def tgju_transport() -> FakeTransport:
    """انتقال‌دهنده‌ای که پاسخ واقعی ضبط‌شدهٔ tgju را می‌دهد."""
    transport = FakeTransport()
    transport.add_json("call1.tgju.org/ajax.json", load_json_fixture("tgju_ajax.json"))
    transport.add("call.tgju.org/ajax.json", status=500, body=b"upstream error")
    return transport


@pytest.fixture()
def coingecko_transport() -> FakeTransport:
    """انتقال‌دهنده‌ای که پاسخ واقعی ضبط‌شدهٔ CoinGecko را می‌دهد."""
    transport = FakeTransport()
    transport.add_json("api.coingecko.com", load_json_fixture("coingecko_price.json"))
    return transport


@pytest.fixture()
def live_providers(config: Config, tgju_transport, coingecko_transport):
    """هر دو منبع واقعی روی پاسخ‌های ضبط‌شده."""
    tgju_http = http_with(tgju_transport, config.data)
    crypto_http = http_with(coingecko_transport, config.data)
    return {
        "tgju": TgjuProvider(tgju_http, config.data),
        "coingecko": CoinGeckoProvider(crypto_http, config.data),
    }


@pytest.fixture()
def context(config: Config, storage: Storage, live_providers) -> AppContext:
    """زمینهٔ کامل با منابع ضبط‌شده و بدون زمان‌بند."""
    ctx = AppContext.build(config, storage=storage, providers=live_providers)
    ctx.storage_ready()
    return ctx


@pytest.fixture()
def client(context: AppContext):
    """کلاینت تست API."""
    from cheshmbaz.webapp import create_app

    app = create_app(context)
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def quote_factory():
    """سازندهٔ نقل‌قول برای تست‌های واحد."""

    def make(slug: str = "geram18", price: float = 1000.0, *, observed_at=None, **kwargs) -> Quote:
        import time as _time

        stamp = observed_at if observed_at is not None else _time.time()
        payload = dict(
            slug=slug, price=price, unit="toman", source="test", observed_at=stamp,
            fetched_at=stamp, precision=kwargs.pop("precision", 0),
        )
        payload.update(kwargs)
        return Quote(**payload)

    return make


@pytest.fixture()
def collect_once(context: AppContext):
    """اجرای یک دور جمع‌آوری روی منابع ضبط‌شده."""

    def run():
        return context.collector.collect(use_lease=True)

    return run


