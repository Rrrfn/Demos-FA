# -*- coding: utf-8 -*-
"""آزمون API — شکل یکدست پاسخ، اعتبارسنجی ورودی و صداقت داده.

API یک قرارداد است. اگر شکل پاسخ بین موفقیت و شکست فرق کند، مصرف‌کننده باید
دو حالت را حدس بزند؛ اگر ورودی نامعتبر بی‌صدا با مقدار پیش‌فرض جواب بگیرد،
کاربر فکر می‌کند داده‌اش پذیرفته شده. این آزمون‌ها همان دو مرز را می‌سنجند.
"""
from __future__ import annotations

import pytest

ENDPOINTS = (
    "/api/health",
    "/api/overview",
    "/api/listings",
    "/api/estimate",
    "/api/analytics",
    "/api/methodology",
)


def payload(response):
    """بدنهٔ JSON با بررسی صریح موفقیت — تا خطای سرور به شکل «تست ناموفق» بیاید."""
    assert response.is_json, f"پاسخ JSON نیست: {response.status_code}"
    body = response.get_json()
    assert body is not None, "بدنهٔ JSON خالی است"
    return body


@pytest.mark.parametrize("path", ENDPOINTS)
def test_endpoints_answer_with_the_same_envelope(client, path):
    body = payload(client.get(path))
    assert body["ok"] is True
    assert isinstance(body["data"], dict)


@pytest.mark.parametrize("path", ENDPOINTS)
def test_errors_use_the_same_envelope(client, path):
    """حتی در خطا، مصرف‌کننده یک شکل ثابت می‌گیرد."""
    response = client.get(path.replace("/api/", "/api/nope-"))
    assert response.status_code == 404


def test_health_reports_model_and_data(client):
    data = payload(client.get("/api/health"))["data"]
    assert data["status"] == "ok"
    assert data["listings"] > 0
    assert data["model"]
    assert "سینتتیک" in data["data_note"]


def test_listings_pagination_is_consistent(client):
    data = payload(client.get("/api/listings?page=1"))["data"]
    assert data["page"] == 1
    assert len(data["items"]) <= data["page_size"]
    assert data["pages"] >= 1
    assert data["has_prev"] is False


def test_listings_page_beyond_the_end_is_clamped(client):
    data = payload(client.get("/api/listings?page=99999"))["data"]
    assert data["page"] == data["pages"]
    assert data["has_next"] is False


def test_listings_filter_narrows_the_result(client):
    everything = payload(client.get("/api/listings"))["data"]["total"]
    filtered = payload(client.get("/api/listings?parking=1&elevator=1"))["data"]["total"]
    assert filtered <= everything


def test_listings_cards_carry_what_a_view_needs(client):
    card = payload(client.get("/api/listings"))["data"]["items"][0]
    for key in ("id", "url", "title", "price", "price_per_m2", "image"):
        assert key in card, f"کلید {key} در کارت نیست"


def test_estimate_returns_price_interval_and_factors(client):
    data = payload(client.get("/api/estimate?district=3&area=120&bedrooms=2&age=5"
                              "&floor=2&parking=1&storage=1&elevator=1"))["data"]
    explanation = data["explanation"]
    assert explanation["price"] > 0
    assert explanation["low"] <= explanation["price"] <= explanation["high"]
    assert explanation["factors"]
    assert data["available"] is True


def test_estimate_rejects_an_out_of_range_value(client):
    response = client.get("/api/estimate?area=99999")
    assert response.status_code == 400
    body = payload(response)
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_parameter"
    assert body["error"]["field"] == "area"


def test_estimate_rejects_a_non_numeric_value(client):
    response = client.get("/api/estimate?district=تهران")
    assert response.status_code == 400
    assert payload(response)["error"]["field"] == "district"


def test_estimate_explains_why_the_price_is_what_it_is(client):
    """جمع سهم‌ها باید با اختلاف قیمت پایه تا ملک بخواند."""
    data = payload(client.get("/api/estimate?district=1&area=200&bedrooms=3"))["data"]
    explanation = data["explanation"]
    assert explanation["base_price"] > 0
    assert explanation["delta_short"]
    # باقی‌ماندهٔ گردکردن باید ناچیز بماند، نه هزاران میلیارد.
    assert abs(explanation["residual"]) < explanation["price"]


def test_listing_detail_includes_comparables(client):
    data = payload(client.get("/api/listings/KH-1001"))["data"]
    assert data["listing"]["id"] == "KH-1001"
    assert "estimate" in data
    assert isinstance(data["comparables"], list)


def test_listing_detail_unknown_identifier_is_404(client):
    response = client.get("/api/listings/KH-000000")
    assert response.status_code == 404
    assert payload(response)["error"]["code"] == "not_found"


def test_analytics_covers_every_district(client):
    data = payload(client.get("/api/analytics"))["data"]
    codes = {row["district"] for row in data["districts"]}
    assert len(codes) == len(data["districts"]), "کد منطقه تکراری است"
    assert codes, "فهرست مناطق خالی است"


def test_methodology_states_its_limitations(client):
    data = payload(client.get("/api/methodology"))["data"]
    assert data["best_model"]
    assert data["limitations"]
    assert data["interval"]["measured_coverage_pct"] > 0
