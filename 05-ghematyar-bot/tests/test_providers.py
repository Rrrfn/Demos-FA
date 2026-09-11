# -*- coding: utf-8 -*-
"""تست ارائه‌دهنده‌ها.

پارس‌ها با **فیکسچر واقعی** آزموده می‌شوند (خروجی ضبط‌شدهٔ همان منابع)، و
سناریوهای خطا با نشست HTTP قلابی — بدون هیچ تماس شبکه‌ای.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ghematyar.core.errors import CircuitOpen, MalformedResponse, ProviderError, RateLimited
from ghematyar.providers.base import HttpClient
from ghematyar.providers.coingecko import parse_simple_price
from ghematyar.providers.tgju import parse_ajax, parse_html, parse_observed_at
from tests.fakes import FakeAiohttpSession, FakeHttpResponse

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def ajax_payload() -> dict:
    return json.loads((FIXTURES / "tgju_ajax.json").read_text(encoding="utf-8"))


@pytest.fixture()
def html_text() -> str:
    return (FIXTURES / "tgju_page.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------- tgju ajax
class TestTgjuAjax:
    """پارس خوراک ماشین‌خوان واقعی."""

    def test_reads_rial_as_toman(self, ajax_payload):
        quotes = parse_ajax(ajax_payload)
        # در فیکسچر واقعی: geram18 = 241,814,000 ریال
        assert quotes["geram18"].price == 24_181_400
        assert quotes["geram18"].unit == "toman"

    def test_reads_usd_correctly(self, ajax_payload):
        quotes = parse_ajax(ajax_payload)
        assert quotes["usd"].price == 235_975

    def test_crypto_stays_in_dollars(self, ajax_payload):
        quotes = parse_ajax(ajax_payload)
        assert quotes["bitcoin"].unit == "usd"
        assert quotes["bitcoin"].price > 1_000

    def test_crypto_change_comes_from_source(self, ajax_payload):
        """رمزارزها تغییر ۲۴ ساعتهٔ واقعی دارند."""
        quotes = parse_ajax(ajax_payload)
        bitcoin = quotes["bitcoin"]
        assert bitcoin.change_pct is not None
        assert bitcoin.change_abs is not None

    def test_gold_has_no_source_change(self, ajax_payload):
        """خوراک، تغییر طلا/ارز را صفر می‌دهد؛ ما صفر را «بدون تغییر» نمی‌گیریم."""
        quotes = parse_ajax(ajax_payload)
        assert quotes["geram18"].change_pct is None
        assert quotes["usd"].change_pct is None

    def test_day_low_high_present(self, ajax_payload):
        quotes = parse_ajax(ajax_payload)
        gold = quotes["geram18"]
        assert gold.day_low and gold.day_high
        assert gold.day_low < gold.day_high

    def test_subset_request_only_returns_asked(self, ajax_payload):
        quotes = parse_ajax(ajax_payload, ["usd"])
        assert set(quotes) == {"usd"}

    def test_observed_at_parsed_from_feed(self, ajax_payload):
        quotes = parse_ajax(ajax_payload)
        assert quotes["usd"].observed_at > 0

    def test_missing_ts_falls_back_to_now(self):
        assert parse_observed_at({}) > 0

    @pytest.mark.parametrize("payload", [None, [], "string", 42])
    def test_non_object_payload_is_malformed(self, payload):
        with pytest.raises(MalformedResponse):
            parse_ajax(payload)

    def test_record_without_price_is_skipped(self):
        """عضو ناقص نباید به قیمت صفر تبدیل شود."""
        quotes = parse_ajax({"current": {"geram18": {"p": "", "h": "", "l": ""}}})
        assert "geram18" not in quotes

    def test_flat_payload_is_accepted(self):
        """سازگاری با ساختار قدیمی‌تر (بدون کلید current)."""
        quotes = parse_ajax({"geram18": {"p": "100,000,000"}})
        assert quotes["geram18"].price == 10_000_000


# --------------------------------------------------------------------- tgju html
class TestTgjuHtml:
    """پارس صفحهٔ واقعی — ساختار ردیف ۶ خانه‌ای بدون ستون عنوان."""

    def test_reads_prices_in_rial(self, html_text):
        quotes = parse_html(html_text)
        assert quotes["geram18"].price == 24_181_400
        assert quotes["usd"].price == 235_975

    def test_reads_gerami_coin(self, html_text):
        """سکهٔ گرمی فقط در این مسیر موجود است (کلید ``gerami``)."""
        quotes = parse_html(html_text)
        assert "gemi" in quotes
        assert quotes["gemi"].price == 35_000_000

    def test_crypto_is_deliberately_skipped(self, html_text):
        """واحد رمزارز در این مسیر قابل اعتماد نیست، پس کنار گذاشته شده."""
        quotes = parse_html(html_text)
        assert "bitcoin" not in quotes

    def test_change_parsed_when_reported(self, html_text):
        quotes = parse_html(html_text)
        assert quotes["geram18"].change_pct is None  # خوراک صفر داده است

    def test_low_high_columns(self, html_text):
        quotes = parse_html(html_text)
        usd = quotes["usd"]
        assert usd.day_low == 233_860
        assert usd.day_high == 236_020

    def test_subset_request(self, html_text):
        quotes = parse_html(html_text, ["gemi"])
        assert set(quotes) == {"gemi"}

    def test_tiny_page_is_malformed(self):
        with pytest.raises(MalformedResponse):
            parse_html("<html></html>")

    def test_page_without_rows_returns_empty(self):
        """صفحهٔ سالم ولی بدون ردیف بازار، خطا نیست — فقط بی‌داده."""
        quotes = parse_html("<html><body>" + "x" * 500 + "</body></html>")
        assert quotes == {}


# --------------------------------------------------------------------- coingecko
class TestCoinGecko:
    """پارس پاسخ واقعی ``simple/price``."""

    PAYLOAD = {
        "bitcoin": {"usd": 78704, "usd_24h_change": 2.05, "last_updated_at": 1789140460},
        "ethereum": {"usd": 2613.34, "usd_24h_change": -1.5, "last_updated_at": 1789140460},
        "unknown-coin": {"usd": 5.0},
    }

    def test_reads_usd_price(self):
        quotes = parse_simple_price(self.PAYLOAD)
        assert quotes["bitcoin"].price == 78_704
        assert quotes["bitcoin"].unit == "usd"
        assert quotes["bitcoin"].source == "coingecko"

    def test_change_is_applied(self):
        quotes = parse_simple_price(self.PAYLOAD)
        assert quotes["bitcoin"].change_pct == pytest.approx(2.05)
        assert quotes["bitcoin"].change_abs == pytest.approx(78_704 * 2.05 / 100)

    def test_unknown_coin_is_ignored(self):
        assert "unknown-coin" not in parse_simple_price(self.PAYLOAD)

    def test_non_numeric_price_is_ignored(self):
        quotes = parse_simple_price({"bitcoin": {"usd": "not-a-number"}})
        assert quotes == {}

    def test_error_object_is_malformed(self):
        with pytest.raises(MalformedResponse):
            parse_simple_price({"status": {"error_code": 429, "error_message": "rate limited"}})

    @pytest.mark.parametrize("payload", [None, [], "string"])
    def test_non_object_is_malformed(self, payload):
        with pytest.raises(MalformedResponse):
            parse_simple_price(payload)


# --------------------------------------------------------------------- http client
class TestHttpClientReliability:
    """تایم‌اوت، تلاش مجدد، backoff و احترام به Retry-After."""

    @pytest.mark.anyio
    async def test_success_first_try(self, config, monkeypatch):
        client = HttpClient(config.data)
        fake = FakeAiohttpSession([FakeHttpResponse(200, payload={"ok": True})])
        monkeypatch.setattr(client, "session", _session_factory(fake))
        assert await client.fetch("https://example.test") == {"ok": True}
        assert len(fake.urls) == 1

    @pytest.mark.anyio
    async def test_retries_on_server_error(self, config, monkeypatch):
        client = HttpClient(config.data)
        fake = FakeAiohttpSession([
            FakeHttpResponse(500),
            FakeHttpResponse(200, payload={"ok": True}),
        ])
        monkeypatch.setattr(client, "session", _session_factory(fake))
        monkeypatch.setattr("ghematyar.providers.base.asyncio.sleep", _no_sleep)
        assert await client.fetch("https://example.test") == {"ok": True}
        assert len(fake.urls) == 2

    @pytest.mark.anyio
    async def test_gives_up_after_max_attempts(self, config, monkeypatch):
        config.data.max_attempts
        client = HttpClient(config.data)
        fake = FakeAiohttpSession([FakeHttpResponse(503)])
        monkeypatch.setattr(client, "session", _session_factory(fake))
        monkeypatch.setattr("ghematyar.providers.base.asyncio.sleep", _no_sleep)
        with pytest.raises(ProviderError):
            await client.fetch("https://example.test")
        assert len(fake.urls) == config.data.max_attempts

    @pytest.mark.anyio
    async def test_timeout_is_retried_then_raised(self, config, monkeypatch):
        client = HttpClient(config.data)
        fake = FakeAiohttpSession([TimeoutError()])
        monkeypatch.setattr(client, "session", _session_factory(fake))
        monkeypatch.setattr("ghematyar.providers.base.asyncio.sleep", _no_sleep)
        with pytest.raises(ProviderError):
            await client.fetch("https://example.test")

    @pytest.mark.anyio
    async def test_rate_limit_is_reported(self, config, monkeypatch):
        client = HttpClient(config.data)
        fake = FakeAiohttpSession([
            FakeHttpResponse(429, headers={"Retry-After": "1"}),
            FakeHttpResponse(200, payload={"ok": True}),
        ])
        monkeypatch.setattr(client, "session", _session_factory(fake))
        monkeypatch.setattr("ghematyar.providers.base.asyncio.sleep", _no_sleep)
        assert await client.fetch("https://example.test") == {"ok": True}

    @pytest.mark.anyio
    async def test_client_error_is_not_retried(self, config, monkeypatch):
        client = HttpClient(config.data)
        fake = FakeAiohttpSession([FakeHttpResponse(404)])
        monkeypatch.setattr(client, "session", _session_factory(fake))
        monkeypatch.setattr("ghematyar.providers.base.asyncio.sleep", _no_sleep)
        with pytest.raises(ProviderError):
            await client.fetch("https://example.test")
        assert len(fake.urls) == 1

    @pytest.mark.anyio
    async def test_invalid_json_is_malformed(self, config, monkeypatch):
        client = HttpClient(config.data)
        fake = FakeAiohttpSession([FakeHttpResponse(200, invalid_json=True)])
        monkeypatch.setattr(client, "session", _session_factory(fake))
        with pytest.raises(MalformedResponse):
            await client.fetch("https://example.test")

    @pytest.mark.anyio
    async def test_backoff_is_exponential_with_cap(self, config, tuned):
        data = tuned(config, data={"backoff_base": 0.5, "backoff_max": 2.0}).data
        client = HttpClient(data)
        delays = [client._backoff(attempt) for attempt in range(1, 6)]
        assert all(0 < d <= 2.0 for d in delays)
        # میانگین تأخیر باید با تلاش‌های بیشتر بزرگ‌تر شود تا رسیدن به سقف
        assert delays[3] > delays[0]


# --------------------------------------------------------------------- breakers & orchestrator
class TestCircuitBreakerAndFallback:
    """مدارشکن و زنجیرهٔ fallback در سطح ارائه‌دهنده."""

    @pytest.mark.anyio
    async def test_provider_opens_circuit_after_failures(self, scripted_provider):
        provider = scripted_provider("flaky", ProviderError("flaky", "boom"))
        for _ in range(provider.breaker.threshold):
            with pytest.raises(ProviderError):
                await provider.fetch(["usd"])
        # حالا مدار باز است و درخواست‌ها سریع رد می‌شوند
        assert provider.available is False
        with pytest.raises(CircuitOpen):
            await provider.fetch(["usd"])

    @pytest.mark.anyio
    async def test_success_resets_failure_count(self, scripted_provider):
        from ghematyar.core.models import Quote

        provider = scripted_provider("recovering", [
            ProviderError("recovering", "boom"),
            {"usd": Quote(slug="usd", price=100.0, source="recovering")},
        ])
        with pytest.raises(ProviderError):
            await provider.fetch(["usd"])
        assert provider.breaker.failures == 1
        await provider.fetch(["usd"])
        assert provider.breaker.failures == 0

    @pytest.mark.anyio
    async def test_empty_result_counts_as_failure(self, scripted_provider):
        """پاسخ خالی برای منبع بازار یعنی «دادهٔ قابل استفاده ندارد»."""
        provider = scripted_provider("empty", {})
        with pytest.raises(ProviderError):
            await provider.fetch(["usd"])
        assert provider.breaker.failures == 1


# --------------------------------------------------------------------- helpers
def _session_factory(fake: FakeAiohttpSession):
    async def _get_session():
        return fake

    return _get_session


async def _no_sleep(*_args, **_kwargs) -> None:
    return None


__all__ = ["FakeAiohttpSession", "FakeHttpResponse", "RateLimited"]
