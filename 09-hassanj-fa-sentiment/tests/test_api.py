# -*- coding: utf-8 -*-
"""آزمون API — پوشش پاسخ یکدست و رفتار درست روی درخواست نامعتبر.

هر پاسخ یا ``{"ok": true, "data": …}`` است یا ``{"ok": false, "error": …}``.
یکدست بودن این پوشش یعنی مصرف‌کننده لازم نیست برای هر مسیر شکل پاسخ را جدا
حدس بزند، و خطا هرگز به صفحهٔ HTML تبدیل نمی‌شود.
"""
from __future__ import annotations

import pytest

from hassanj.config import LABELS, MAX_ANALYZE_CHARS


def payload(response) -> dict:
    data = response.get_json()
    assert isinstance(data, dict)
    assert "ok" in data
    return data


# --------------------------------------------------------------------- سلامت
def test_health_reports_model_and_data_note(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = payload(response)
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["best_model"]
    assert body["data"]["labels"] == list(LABELS)
    assert "سینتتیک" in body["data"]["data_note"]


def test_model_status_endpoint(client):
    body = payload(client.get("/api/model-status"))
    assert body["ok"] is True
    assert body["data"]["trained"] is True
    assert body["data"]["bytes"] > 0


# --------------------------------------------------------------------- تحلیل
def test_analyze_accepts_json(client):
    response = client.post("/api/analyze", json={"text": "کیفیت عالی بود و سریع"})
    assert response.status_code == 200
    data = payload(response)["data"]
    assert data["label"] == "pos"
    assert data["label_fa"] == "مثبت"
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["state"] == "ok"
    assert set(data["proba"]) == set(LABELS)


def test_analyze_accepts_form_encoded_body(client):
    response = client.post("/api/analyze", data={"text": "خراب رسید و پشیمون شدم"})
    assert response.status_code == 200
    assert payload(response)["data"]["label"] == "neg"


def test_analyze_reports_coverage_and_tokens(client):
    data = payload(client.post("/api/analyze",
                              json={"text": "کیفیت عالی بود ولی zzzz"}))["data"]
    assert data["coverage"] is not None
    assert data["tokens"] >= 1
    assert isinstance(data["known_tokens"], list)
    assert isinstance(data["unknown_tokens"], list)
    assert "toward" in data and "against" in data


@pytest.mark.parametrize("body,message", [
    ({}, "خالی"),
    ({"text": ""}, "خالی"),
    ({"text": "   "}, "خالی"),
    ({"text": 42}, "رشته"),
    ({"text": ["خوب"]}, "رشته"),
])
def test_analyze_rejects_invalid_input(client, body, message):
    response = client.post("/api/analyze", json=body)
    assert response.status_code == 400
    result = payload(response)
    assert result["ok"] is False
    assert message in result["error"]


def test_analyze_rejects_json_array_body(client):
    response = client.post("/api/analyze", json=["خوب"])
    assert response.status_code == 400
    assert payload(response)["ok"] is False


def test_analyze_truncates_and_flags_long_text(client):
    response = client.post("/api/analyze", json={"text": "خوب بود " * 2000})
    data = payload(response)["data"]
    assert data["truncated"] is True
    assert data["max_chars"] == MAX_ANALYZE_CHARS


def test_analyze_handles_out_of_domain_input_honestly(client):
    data = payload(client.post("/api/analyze",
                              json={"text": "Delivery was slow"}))["data"]
    assert data["state"] == "out_of_domain"
    assert data["coverage"] == 0.0


def test_analyze_handles_symbol_only_input(client):
    data = payload(client.post("/api/analyze", json={"text": "!!! ..."}))["data"]
    assert data["state"] == "no_signal"


# --------------------------------------------------------------- معیارها و داده‌ها
def test_metrics_endpoint_exposes_both_evaluations(client):
    data = payload(client.get("/api/metrics"))["data"]
    assert {"in_domain", "out_domain", "results", "vocabulary_size"} <= set(data)
    assert data["out_domain"]["f1_macro"] <= data["in_domain"]["f1_macro"]
    assert data["cv"]["f1_macro_mean"] >= 0.0


def test_mix_endpoint_separates_actual_from_predicted(client):
    data = payload(client.get("/api/mix"))["data"]
    assert {"actual", "predicted", "comparison"} <= set(data)
    assert abs(sum(data["actual"]["shares"].values()) - 1.0) < 1e-3
    assert abs(sum(data["predicted"]["shares"].values()) - 1.0) < 1e-3


@pytest.mark.parametrize("label", list(LABELS))
def test_terms_endpoint_per_label(client, label):
    data = payload(client.get(f"/api/terms?label={label}"))["data"]
    assert data["label"] == label
    assert isinstance(data["terms"], list)


def test_terms_endpoint_rejects_unknown_label(client):
    response = client.get("/api/terms?label=love")
    assert response.status_code == 400
    result = payload(response)
    assert result["ok"] is False
    assert "برچسب نامعتبر" in result["error"]


def test_terms_endpoint_defaults_to_positive(client):
    data = payload(client.get("/api/terms"))["data"]
    assert data["label"] == "pos"


def test_trend_endpoint_returns_persian_month_labels(client):
    data = payload(client.get("/api/trend"))["data"]
    assert data["months"]
    for month in data["months"]:
        assert month["label"]
        assert not any(char in month["label"] for char in "0123456789")
        assert abs(sum(month["shares"].values()) - 1.0) < 1e-3


# --------------------------------------------------------------------- خطاها
def test_unknown_api_route_returns_json_not_html(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.is_json
    assert payload(response)["ok"] is False


def test_api_errors_are_never_html(client):
    for response in (client.get("/api/nope"),
                     client.post("/api/analyze", json={}),
                     client.get("/api/terms?label=bad")):
        assert response.is_json
        assert "text/html" not in response.headers.get("Content-Type", "")


def test_error_messages_are_persian(client):
    message = payload(client.post("/api/analyze", json={}))["error"]
    assert all(ord(char) < 128 or ord(char) > 0x200 for char in message)
