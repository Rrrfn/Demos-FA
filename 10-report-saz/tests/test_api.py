# -*- coding: utf-8 -*-
"""API — هر endpoint، شکل پاسخ و خطاهای ورودی."""
from __future__ import annotations

import io
import json

import pytest


def _data(response) -> dict:
    payload = response.get_json()
    assert payload is not None, response.data[:200]
    assert payload["ok"] is True, payload
    return payload["data"]


def _error(response) -> dict:
    payload = response.get_json()
    assert payload["ok"] is False
    return payload["error"]


# ------------------------------------------------------------------ فهرست
def test_index_documents_the_endpoints(client):
    data = _data(client.get("/api"))
    paths = {item["path"] for item in data["endpoints"]}
    for expected in ("/api/upload", "/api/profile/<id>", "/api/analyze/<id>",
                     "/api/report/<id>", "/api/export/<id>/excel",
                     "/api/export/<id>/pdf"):
        assert expected in paths
    assert data["limits"]["max_upload_mb"] > 0
    assert data["quality_method"]


# ------------------------------------------------------------------ بارگذاری
def test_upload_returns_id_and_profile(client, xlsx_file):
    response = client.post("/api/upload",
                           data={"file": (io.BytesIO(xlsx_file), "data.xlsx")},
                           content_type="multipart/form-data")
    assert response.status_code == 201
    data = _data(response)
    assert data["stage"] == "inspected"
    assert data["dataset_id"]
    assert data["read"]["rows"] > 0
    assert data["links"]["profile"].endswith(data["dataset_id"])


def test_upload_accepts_csv(client, csv_file):
    response = client.post("/api/upload",
                           data={"file": (io.BytesIO(csv_file), "data.csv")},
                           content_type="multipart/form-data")
    assert response.status_code == 201
    assert _data(response)["read"]["rows"] > 0


def test_upload_without_file_is_a_clear_400(client):
    response = client.post("/api/upload", data={},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    error = _error(response)
    assert error["code"] == "missing_file"
    assert "فایل" in error["message"]


def test_upload_rejects_legacy_format_with_guidance(client):
    response = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 64),
                       "old.xls")},
        content_type="multipart/form-data")
    assert response.status_code == 400
    error = _error(response)
    assert error["code"] == "legacy_format"
    assert "xlsx" in error["message"].lower() or "csv" in error["message"].lower()


def test_upload_rejects_unknown_extension(client):
    response = client.post("/api/upload",
                           data={"file": (io.BytesIO(b"hello"), "notes.txt")},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert _error(response)["code"] == "unsupported_format"


def test_upload_rejects_empty_file(client):
    response = client.post("/api/upload",
                           data={"file": (io.BytesIO(b""), "empty.csv")},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert _error(response)["code"] in ("empty_file", "corrupt_file")


def test_upload_rejects_mislabelled_file(client):
    """فایل متنی با پسوند xlsx باید رد شود، نه این‌که منفجر شود."""
    response = client.post("/api/upload",
                           data={"file": (io.BytesIO(b"just text here"),
                                          "fake.xlsx")},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert _error(response)["code"] == "corrupt_file"


def test_upload_accepts_persian_filename(client, xlsx_file):
    response = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(xlsx_file), "آمار فروش ۱۴۰۳.xlsx")},
        content_type="multipart/form-data")
    assert response.status_code == 201
    assert "۱۴۰۳" in _data(response)["display_name"]


# ------------------------------------------------------------------ بسته
def test_dataset_metadata(client, bundle_id):
    data = _data(client.get(f"/api/dataset/{bundle_id}"))
    assert data["dataset_id"] == bundle_id
    assert data["stage"] in ("inspected", "cleaned", "analysed")
    assert data["read"]["rows"] > 0


def test_unknown_dataset_is_404(client):
    response = client.get("/api/dataset/000000000000")
    assert response.status_code == 404
    assert _error(response)["code"] == "dataset_not_found"


def test_malformed_dataset_id_is_rejected(client):
    """شناسه در نشانی می‌نشیند و باید الگو داشته باشد، وگرنه مسیرسازی ممکن
    می‌شود."""
    for bad in ("../../etc/passwd", "zzzz", "12345", "a" * 40):
        response = client.get(f"/api/dataset/{bad}")
        assert response.status_code == 404, bad


def test_profile_endpoint(client, bundle_id):
    data = _data(client.get(f"/api/profile/{bundle_id}"))
    assert data["rows"] > 0
    assert data["columns_profile"]
    assert data["quality"]["score"] >= 0
    assert data["quality_method"]
    assert data["findings"] is not None
    assert "metrics" in data["suggested"]


# ------------------------------------------------------------------ پاک‌سازی
def test_clean_endpoint_applies_options(client, bundle_id):
    response = client.post(f"/api/clean/{bundle_id}",
                           json={"options": {"drop_duplicates": True,
                                             "numeric_as_text": True}})
    data = _data(response)
    assert data["cleaning"]["rows_before"] >= data["cleaning"]["rows_after"]
    assert data["options"]["drop_duplicates"] is True


def test_clean_endpoint_with_everything_off(client, bundle_id):
    response = client.post(f"/api/clean/{bundle_id}",
                           json={"options": {"drop_duplicates": False,
                                             "trim_text": False,
                                             "numeric_as_text": False,
                                             "parse_dates": False,
                                             "normalize_nulls": False,
                                             "drop_empty_rows": False,
                                             "drop_empty_columns": False}})
    data = _data(response)
    assert data["cleaning"]["rows_after"] == data["cleaning"]["rows_before"]


def test_clean_endpoint_requires_valid_json(client, bundle_id):
    class _Payload:
        data = b"hello"

    response = client.post(f"/api/clean/{bundle_id}", data=b"hello",
                           content_type="application/json")
    #: بدنهٔ خراب نباید ۵۰۰ بدهد؛ یعنی «تحلیل با پیش‌فرض» یا خطای ورودی.
    assert response.status_code in (200, 400)


# ------------------------------------------------------------------ تحلیل
def test_analyze_endpoint_returns_full_analysis(client, bundle_id):
    data = _data(client.post(f"/api/analyze/{bundle_id}", json={}))
    assert data["kpis"]
    assert "series" in data and "insights" in data
    assert "correlation" in data


def test_analyze_endpoint_accepts_chosen_axes(client, messy_frame):
    import io as _io

    from tests.conftest import xlsx_bytes

    response = client.post(
        "/api/upload",
        data={"file": (_io.BytesIO(xlsx_bytes(messy_frame)), "d.xlsx")},
        content_type="multipart/form-data")
    dataset_id = _data(response)["dataset_id"]
    data = _data(client.post(f"/api/analyze/{dataset_id}",
                             json={"metric": "تعداد", "dimension": "محصول"}))
    assert data["primary_metric"] == "تعداد"
    assert data["primary_dimension"] == "محصول"


def test_analyze_with_unknown_axis_falls_back(client, bundle_id):
    data = _data(client.post(f"/api/analyze/{bundle_id}",
                             json={"metric": "چیزی که نیست"}))
    assert data["primary_metric"] != "چیزی که نیست"
    assert data["notes"]


# ------------------------------------------------------------------ گزارش
def test_report_endpoint_returns_sections(client, bundle_id):
    data = _data(client.get(f"/api/report/{bundle_id}"))
    keys = [section["key"] for section in data["sections"]]
    for expected in ("summary", "quality", "kpis", "charts", "insights"):
        assert expected in keys
    assert data["meta_lines"]


def test_theme_endpoint_validates_name(client, bundle_id):
    assert _data(client.post(f"/api/theme/{bundle_id}",
                             json={"theme": "executive"}))["theme"] == "executive"
    response = client.post(f"/api/theme/{bundle_id}", json={"theme": "ناشناخته"})
    assert response.status_code == 400
    assert _error(response)["code"] == "unknown_theme"


# ------------------------------------------------------------------ خروجی
def test_excel_export(client, bundle_id):
    response = client.get(f"/api/export/{bundle_id}/excel")
    assert response.status_code == 200
    assert response.data[:2] == b"PK"
    assert "spreadsheetml" in response.headers["Content-Type"]


def test_pdf_export(client, bundle_id):
    response = client.get(f"/api/export/{bundle_id}/pdf")
    assert response.status_code == 200
    assert response.data[:5] == b"%PDF-"
    assert response.headers["Content-Type"] == "application/pdf"


def test_export_filename_is_ascii(client, bundle_id):
    """نام فایل فارسی خام در سرآمد مجاز نیست و پاسخ را می‌شکند."""
    response = client.get(f"/api/export/{bundle_id}/pdf")
    disposition = response.headers["Content-Disposition"]
    disposition.encode("latin-1")          #: نباید استثنا بدهد
    assert bundle_id in disposition


def test_exports_of_unknown_dataset_are_404(client):
    assert client.get("/api/export/000000000000/pdf").status_code == 404
    assert client.get("/api/export/000000000000/excel").status_code == 404


# ------------------------------------------------------------------ سلامت
def test_health_reports_storage(client):
    payload = client.get("/health").get_json()
    assert payload["status"] == "ok"
    assert "storage" in payload
    assert payload["storage"]["bundles"] >= 0


def test_json_errors_are_never_html(client):
    """خطا روی مسیر API باید JSON بماند، نه صفحهٔ HTML."""
    for path in ("/api/dataset/000000000000", "/api/export/000000000000/pdf"):
        response = client.get(path)
        assert response.is_json, path
