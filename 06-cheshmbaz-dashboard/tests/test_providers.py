# -*- coding: utf-8 -*-
"""آزمون منابع داده — پارس، تبدیل واحد، تلاش مجدد و مدارشکن.

این تست‌ها روی پاسخ واقعی ضبط‌شده اجرا می‌شوند. مهم‌ترینشان
`test_tgju_converts_rial_to_toman` است: فراموش‌کردن این تبدیل، همهٔ بازار
داخلی را ده برابر واقعیت نشان می‌دهد و یک خطای جدی محصول است.
"""
from __future__ import annotations

import json
import time

import pytest

from cheshmbaz.assets import by_provider
from cheshmbaz.config import DataConfig
from cheshmbaz.core.errors import CircuitOpen, MalformedResponse, ProviderError, RateLimited
from cheshmbaz.providers.coingecko import CoinGeckoProvider, build_url, parse_quotes as cg_parse
from cheshmbaz.providers.tgju import TgjuProvider, parse_quotes as tgju_parse
from tests.fakes import FakeTransport, http_with, load_fixture, load_json_fixture


# ------------------------------------------------------------------------- tgju
@pytest.fixture()
def tgju_assets():
    return by_provider("tgju")


@pytest.fixture()
def crypto_assets():
    return by_provider("coingecko")


def test_tgju_converts_rial_to_toman(tgju_assets):
    """واحد خوراک ریال است و خروجی باید تومان باشد (تقسیم بر ده)."""
    payload = load_json_fixture("tgju_ajax.json")
    quotes, missing = tgju_parse(payload, tgju_assets, raw_unit="rial")

    assert missing == []
    assert len(quotes) == len(tgju_assets)
    for asset in tgju_assets:
        raw = float(str(payload["current"][asset.provider_key]["p"]).replace(",", ""))
        assert quotes[asset.slug].price == pytest.approx(raw / 10), asset.slug
        assert quotes[asset.slug].unit == "toman"

    # لنگر عددی: دلار بازار داخلی در این ضبط حدود ۲۳۵ هزار تومان است
    assert 50_000 < quotes["usd"].price < 5_000_000


def test_tgju_reports_missing_and_drops_zero_prices(tgju_assets):
    payload = {
        "current": {
            "geram18": {"p": "24,181,400"},
            "price_dollar_rl": {"p": "0"},
            "price_eur": {"p": ""},
            "sekee": {"p": "not-a-number"},
        }
    }
    quotes, missing = tgju_parse(payload, tgju_assets)

    assert set(quotes) == {"geram18"}
    assert quotes["geram18"].price == pytest.approx(2_418_140)
    assert "usd" in missing and "eur" in missing and "sekee" in missing
    assert "geram18" not in missing


def test_tgju_never_invents_change(tgju_assets):
    """منبع داخلی درصد تغییر ندارد؛ پس نباید هیچ عددی ساخته شود."""
    quotes, _ = tgju_parse(load_json_fixture("tgju_ajax.json"), tgju_assets)
    for quote in quotes.values():
        assert quote.change_pct is None
        assert quote.change_abs is None
        assert quote.change_basis == ""


def test_tgju_malformed_payload_reports_everything_missing(tgju_assets):
    quotes, missing = tgju_parse(["not", "a", "dict"], tgju_assets)
    assert quotes == {}
    assert set(missing) == {asset.slug for asset in tgju_assets}


def test_tgju_fetch_marks_freshness(tgju_assets, tgju_transport, config):
    provider = TgjuProvider(http_with(tgju_transport, config.data), config.data)
    result = provider.fetch(tgju_assets)
    assert len(result.quotes) == len(tgju_assets)
    assert result.requested == len(tgju_assets)
    for quote in result.quotes.values():
        assert quote.freshness.value == "live"
        assert quote.observed_at > 0


def test_tgju_fetch_fails_honestly_when_all_endpoints_break(tgju_assets, config):
    transport = FakeTransport()
    transport.add("call1.tgju.org", status=500, body=b"boom")
    transport.add("call.tgju.org", status=503, body=b"boom")
    provider = TgjuProvider(http_with(transport, config.data), config.data)

    with pytest.raises(ProviderError):
        provider.fetch(tgju_assets)


def test_tgju_fetch_ignores_html_instead_of_json(tgju_assets, config):
    transport = FakeTransport()
    transport.add("call1.tgju.org", body=load_fixture("malformed.html"))
    transport.add_json("call.tgju.org", load_json_fixture("tgju_ajax.json"))
    provider = TgjuProvider(http_with(transport, config.data), config.data)

    result = provider.fetch(tgju_assets)
    assert len(result.quotes) == len(tgju_assets)


# -------------------------------------------------------------------- CoinGecko
def test_coingecko_parses_change_and_source_timestamp(crypto_assets):
    payload = load_json_fixture("coingecko_price.json")
    quotes, missing = cg_parse(payload, crypto_assets)

    assert missing == []
    for asset in crypto_assets:
        record = payload[asset.provider_key]
        quote = quotes[asset.slug]
        assert quote.price == pytest.approx(record["usd"])
        assert quote.change_pct == pytest.approx(record["usd_24h_change"])
        assert quote.observed_at == pytest.approx(record["last_updated_at"])
        assert quote.unit == "usd"
        # mabna: previous = price / (1 + pct/100)
        expected_previous = record["usd"] / (1 + record["usd_24h_change"] / 100)
        assert quote.previous_price == pytest.approx(expected_previous)
        assert quote.change_abs == pytest.approx(record["usd"] - expected_previous)


def test_coingecko_handles_missing_entries(crypto_assets):
    quotes, missing = cg_parse({"bitcoin": {"usd": 50_000}}, crypto_assets)
    assert set(quotes) == {"bitcoin"}
    assert len(missing) == len(crypto_assets) - 1


def test_coingecko_ignores_non_positive_prices(crypto_assets):
    quotes, missing = cg_parse(
        {"bitcoin": {"usd": 0}, "ethereum": {"usd": -3}, "solana": {"usd": 12.5}}, crypto_assets
    )
    assert set(quotes) == {"solana"}
    assert "bitcoin" in missing and "ethereum" in missing


def test_coingecko_without_change_leaves_change_empty(crypto_assets):
    quotes, _ = cg_parse({"bitcoin": {"usd": 50_000, "last_updated_at": 1_700_000_000}}, crypto_assets)
    quote = quotes["bitcoin"]
    assert quote.change_pct is None
    assert quote.change_abs is None
    assert quote.previous_price is None
    assert quote.observed_at == pytest.approx(1_700_000_000)


def test_coingecko_url_is_bounded_and_complete():
    url = build_url(["bitcoin", "ethereum"])
    assert "ids=bitcoin,ethereum" in url
    assert "vs_currencies=usd" in url
    assert "include_24hr_change=true" in url
    assert "include_last_updated_at=true" in url


def test_coingecko_malformed_payload(crypto_assets):
    quotes, missing = cg_parse("nope", crypto_assets)
    assert quotes == {}
    assert len(missing) == len(crypto_assets)


# ----------------------------------------------------------- transport behaviour
def test_retries_then_succeeds_after_transient_network_error(config):
    transport = FakeTransport()
    transport.add_json("example.test", {"ok": True}).fail("example.test", times=1)
    http = http_with(transport, config.data)
    payload = http.get_json("https://example.test/data", provider="demo")
    assert payload == {"ok": True}
    assert len(transport.raised) == 1


def test_retries_transient_http_500_then_succeeds(config):
    transport = FakeTransport()
    transport.add_sequence(
        "example.test",
        [(500, b"temporary"), (200, json.dumps({"ok": True}).encode())],
    )
    http = http_with(transport, config.data)
    assert http.get_json("https://example.test/x", provider="demo") == {"ok": True}


def test_gives_up_after_max_attempts(config):
    transport = FakeTransport().fail("example.test", times=10)
    http = http_with(transport, config.data)
    with pytest.raises(ProviderError) as error:
        http.get_json("https://example.test/x", provider="demo")
    assert error.value.retryable is True
    assert len(transport.raised) == config.data.max_attempts


def test_invalid_json_raises_malformed(config):
    transport = FakeTransport().add("example.test", body=b"not json at all")
    http = http_with(transport, config.data)
    with pytest.raises(MalformedResponse):
        http.get_json("https://example.test/x", provider="demo")


def test_rate_limit_is_surfaced_with_retry_after(config):
    transport = FakeTransport().add(
        "example.test", status=429, body=b"slow down", headers={"Retry-After": "30"}
    )
    http = http_with(transport, config.data)
    with pytest.raises(RateLimited) as error:
        http.request("https://example.test/x", provider="demo")
    assert error.value.retry_after == 30


def test_circuit_breaker_opens_and_blocks(config):
    tight = config.retuned(data={"max_attempts": 1, "breaker_threshold": 2})
    transport = FakeTransport().fail("example.test", times=99)
    http = http_with(transport, tight.data)

    for _ in range(2):
        with pytest.raises(ProviderError):
            http.request("https://example.test/x", provider="demo")

    breaker = http.breaker("demo")
    assert breaker.is_open
    with pytest.raises(CircuitOpen):
        http.request("https://example.test/x", provider="demo")
    assert breaker.snapshot()["open"] is True


def test_circuit_breaker_closes_after_cooldown(config):
    tight = config.retuned(data={"max_attempts": 1, "breaker_threshold": 1, "breaker_cooldown": 0})
    transport = FakeTransport().fail("example.test", times=1).add_json("example.test", {"ok": 1})
    http = http_with(transport, tight.data)

    with pytest.raises(ProviderError):
        http.request("https://example.test/x", provider="demo")
    assert http.breaker("demo").is_open

    time.sleep(0.01)
    result = http.get_json("https://example.test/x", provider="demo")
    assert result == {"ok": 1}
    assert not http.breaker("demo").is_open


def test_provider_available_reflects_breaker_state(config):
    tight = config.retuned(data={"max_attempts": 1, "breaker_threshold": 1})
    transport = FakeTransport().fail("call1.tgju.org", times=9)
    provider = TgjuProvider(http_with(transport, tight.data), tight.data)

    assert provider.available is True
    with pytest.raises(ProviderError):
        provider.fetch(by_provider("tgju"))
    assert provider.available is False


def test_coingecko_provider_fetch_uses_recorded_payload(crypto_assets, coingecko_transport, config):
    provider = CoinGeckoProvider(http_with(coingecko_transport, config.data), config.data)
    result = provider.fetch(crypto_assets)
    assert len(result.quotes) == len(crypto_assets)
    assert all(quote.source == "coingecko.com" for quote in result.quotes.values())
