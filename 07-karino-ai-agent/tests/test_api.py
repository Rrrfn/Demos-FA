# -*- coding: utf-8 -*-
"""آزمون‌های API — پوشش پاسخ، اعتبارسنجی، کش پیشنهاد و توکن مدیریت.

قرارداد API این است که کلاینت هیچ‌وقت حدس نزند: یا ``{"ok": true, "data": …}``
یا ``{"ok": false, "error": {"code": …}}``. اینجا هم مسیرهای درست و هم همهٔ
ورودی‌های غلط آزموده می‌شوند.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from karino.pipeline.scoring import BUDGETS
from karino.profile import PORTFOLIO, SKILLS


def payload(response):
    return response.get_json()


# ---------------------------------------------------------------- سلامت


def test_health_reports_budget_and_source_count(client):
    data = payload(client.get("/health"))
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["score_budget"] == sum(BUDGETS.values()) == 100
    assert data["sources"] == 7          # شش منبع ثبتی + فیدهای دلخواه


def test_versioned_health_uses_the_same_envelope(client):
    """هر پاسخ زیر /api/v1 یک شکل دارد؛ استثنای پوشش فقط /health بدون پیشوند است."""
    body = payload(client.get("/api/v1/health"))
    assert body["ok"] is True
    assert body["data"]["service"] == "karino-ai-agent"
    assert body["data"]["status"] == "ok"


# ---------------------------------------------------------------- نمای کلی


def test_overview_envelope_and_totals(client, seeded):
    body = payload(client.get("/api/v1/overview"))
    assert body["ok"] is True
    data = body["data"]
    assert data["total_jobs"] == 3
    assert data["top_matches"]
    assert sum(data["distribution"].values()) == 3


def test_profile_endpoint_lists_skills_and_portfolio(client):
    data = payload(client.get("/api/v1/profile"))["data"]
    assert len(data["skills"]) == len(SKILLS)
    assert len(data["portfolio"]) == len(PORTFOLIO)
    assert data["total_weight"] > 0


# ---------------------------------------------------------------- فهرست آگهی‌ها


def test_jobs_list_is_sorted_by_score_descending(client, seeded):
    body = payload(client.get("/api/v1/jobs"))
    assert body["ok"] is True
    scores = [job["score"] for job in body["data"]]
    assert scores == sorted(scores, reverse=True)
    assert body["meta"]["total"] == 3


def test_jobs_pagination_meta_is_consistent(client, seeded):
    body = payload(client.get("/api/v1/jobs?per_page=2&page=1"))
    meta = body["meta"]
    assert meta["count"] == 2
    assert meta["page_count"] == 2
    assert meta["has_next"] is True
    assert meta["has_prev"] is False

    second = payload(client.get("/api/v1/jobs?per_page=2&page=2"))["meta"]
    assert second["has_prev"] is True and second["has_next"] is False


def test_jobs_search_and_remote_filters(client, seeded):
    assert payload(client.get("/api/v1/jobs?q=پایتون"))["meta"]["total"] >= 1
    assert payload(client.get("/api/v1/jobs?q=واژهٔ‌ناموجود"))["meta"]["total"] == 0
    assert payload(client.get("/api/v1/jobs?remote=true"))["ok"] is True
    assert payload(client.get("/api/v1/jobs?saved=true"))["meta"]["total"] == 0


def test_jobs_accepts_a_known_source_and_rejects_unknown(client, seeded):
    assert payload(client.get("/api/v1/jobs?source=remotive"))["meta"]["total"] == 0
    response = client.get("/api/v1/jobs?source=not_a_source")
    assert response.status_code == 400
    assert payload(response)["error"]["code"] == "invalid_request"


def test_jobs_rejects_non_numeric_arguments(client, seeded):
    response = client.get("/api/v1/jobs?page=abc")
    assert response.status_code == 400
    assert "page" in payload(response)["error"]["message"]


def test_jobs_rejects_out_of_range_arguments(client, seeded):
    for query in ("page=0", "per_page=0", "per_page=101", "min=101", "max=-1"):
        assert client.get(f"/api/v1/jobs?{query}").status_code == 400, query


def test_jobs_rejects_inverted_score_range(client, seeded):
    response = client.get("/api/v1/jobs?min=80&max=20")
    assert response.status_code == 400


def test_jobs_rejects_unsupported_sort(client, seeded):
    response = client.get("/api/v1/jobs?sort=magic")
    assert response.status_code == 400


def test_jobs_rejects_non_boolean_remote(client, seeded):
    response = client.get("/api/v1/jobs?remote=maybe")
    assert response.status_code == 400


# ---------------------------------------------------------------- جزئیات


def test_job_detail_includes_breakdown(client, seeded):
    job_id = seeded[0]
    data = payload(client.get(f"/api/v1/jobs/{job_id}"))["data"]
    assert data["id"] == job_id
    assert len(data["match"]["factors"]) == len(BUDGETS)
    assert data["match"]["verdict_label"]


def test_job_match_endpoint_matches_detail(client, seeded):
    job_id = seeded[1]
    direct = payload(client.get(f"/api/v1/jobs/{job_id}/match"))["data"]
    detail = payload(client.get(f"/api/v1/jobs/{job_id}"))["data"]["match"]
    assert direct["score"] == detail["score"]


def test_unknown_job_returns_404_envelope(client, seeded):
    for path in ("/api/v1/jobs/999999", "/api/v1/jobs/999999/match",
                 "/api/v1/jobs/999999/proposal"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert payload(response)["error"]["code"] == "not_found"


def test_rescore_returns_a_fresh_analysis(client, seeded):
    body = payload(client.post(f"/api/v1/jobs/{seeded[0]}/rescore"))
    assert body["ok"] is True
    assert len(body["data"]["factors"]) == len(BUDGETS)


# ---------------------------------------------------------------- پیشنهاد


def test_proposal_is_absent_until_generated(client, seeded):
    data = payload(client.get(f"/api/v1/jobs/{seeded[0]}/proposal"))["data"]
    assert data["exists"] is False
    assert data["body"] is None
    assert data["tone"] == "formal"


def test_proposal_is_generated_then_served_from_cache(client, seeded):
    job_id = seeded[0]
    first = payload(client.post(f"/api/v1/jobs/{job_id}/proposal"))["data"]
    assert first["writer"] == "rule_based"
    assert first["cached"] is False
    assert first["char_count"] > 200

    second = payload(client.post(f"/api/v1/jobs/{job_id}/proposal"))["data"]
    assert second["cached"] is True
    assert second["body"] == first["body"]

    stored = payload(client.get(f"/api/v1/jobs/{job_id}/proposal"))["data"]
    assert stored["exists"] is True
    assert stored["body"] == first["body"]


def test_proposal_force_rebuilds(client, seeded):
    job_id = seeded[0]
    client.post(f"/api/v1/jobs/{job_id}/proposal")
    forced = payload(client.post(f"/api/v1/jobs/{job_id}/proposal",
                                 json={"force": True}))["data"]
    assert forced["cached"] is False


def test_proposal_tone_and_length_variants(client, seeded):
    job_id = seeded[0]
    short = payload(client.post(f"/api/v1/jobs/{job_id}/proposal",
                                json={"tone": "concise", "variant": "short"}))["data"]
    assert short["tone_label"]
    assert short["variant"] == "short"
    assert short["word_count"] > 0


def test_proposal_rejects_unknown_tone_and_variant(client, seeded):
    job_id = seeded[0]
    assert client.post(f"/api/v1/jobs/{job_id}/proposal",
                       json={"tone": "shouty"}).status_code == 400
    assert client.post(f"/api/v1/jobs/{job_id}/proposal",
                       json={"variant": "essay"}).status_code == 400
    assert client.get(f"/api/v1/jobs/{job_id}/proposal?tone=shouty").status_code == 400


def test_proposal_for_unknown_job_is_404(client, seeded):
    response = client.post("/api/v1/jobs/999999/proposal")
    assert response.status_code == 404


# ---------------------------------------------------------------- ذخیره‌شده


def test_unsave_for_unknown_job_is_404(client, seeded):
    assert client.delete("/api/v1/jobs/999999/save").status_code == 404


def test_saving_is_idempotent(client, seeded):
    job_id = seeded[0]
    assert payload(client.post(f"/api/v1/jobs/{job_id}/save"))["data"]["created"] is True
    assert payload(client.post(f"/api/v1/jobs/{job_id}/save"))["data"]["created"] is False

    saved = payload(client.get("/api/v1/saved"))
    assert saved["meta"]["total"] == 1
    assert saved["meta"]["saved_total"] == 1
    assert saved["data"][0]["saved"] is True


def test_saved_list_is_reflected_on_the_job(client, seeded):
    job_id = seeded[0]
    client.post(f"/api/v1/jobs/{job_id}/save")
    assert payload(client.get(f"/api/v1/jobs/{job_id}"))["data"]["saved"] is True


# ---------------------------------------------------------------- منابع


def test_sources_endpoint_reports_health_for_every_source(client, seeded):
    data = payload(client.get("/api/v1/sources"))["data"]
    assert len(data) == 7
    for item in data:
        assert item["key"] and item["label"]
        assert 0.0 <= item["success_rate"] <= 1.0


# ---------------------------------------------------------------- فعالیت


def test_activity_endpoint_groups_and_counts(client, seeded):
    body = payload(client.get("/api/v1/activity"))
    assert body["ok"] is True
    assert body["meta"]["counts"]["info"] >= 1
    assert any(event["kind"] == "test" for event in body["data"])


def test_activity_rejects_unknown_level(client, seeded):
    assert client.get("/api/v1/activity?level=panic").status_code == 400
    assert payload(client.get("/api/v1/activity?level=success"))["ok"] is True


def test_saving_a_job_is_logged(client, seeded):
    client.post(f"/api/v1/jobs/{seeded[0]}/save")
    kinds = [event["kind"] for event in payload(client.get("/api/v1/activity"))["data"]]
    assert "job_saved" in kinds


# ---------------------------------------------------------------- جمع‌آوری


def test_ingest_rejects_an_empty_source_list(client):
    response = client.post("/api/v1/ingest", json={"sources": []})
    assert response.status_code == 400


def test_ingest_rejects_unknown_source_keys(client):
    response = client.post("/api/v1/ingest", json={"sources": ["not_a_source"]})
    assert response.status_code == 400
    assert "not_a_source" in payload(response)["error"]["detail"]


def test_ingest_handles_a_source_with_nothing_to_fetch(client):
    """فید دلخواه بدون آدرس خطا نیست — خط لوله صفر آگهی گزارش می‌کند."""
    body = payload(client.post("/api/v1/ingest", json={"sources": ["custom_feeds"]}))
    assert body["ok"] is True
    assert body["data"]["new"] == 0
    assert body["data"]["message"]


# ---------------------------------------------------------------- رفتار HTTP


def test_unsupported_method_returns_a_json_envelope(client):
    response = client.delete("/api/v1/jobs")
    assert response.status_code == 405
    assert payload(response)["error"]["code"] == "method_not_allowed"


def test_unknown_api_path_returns_404_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert payload(response)["error"]["code"] == "not_found"


# ---------------------------------------------------------------- توکن مدیریت


@pytest.fixture()
def guarded_client(settings, db):
    """اپ با توکن مدیریت روشن — همهٔ مسیرهای نوشتن باید محافظت شوند."""
    from karino.webapp import create_app

    guarded = replace(settings, admin_token="s3cret")
    app = create_app(bootstrap=False, settings=guarded)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_writes_are_open_when_no_token_is_configured(client, seeded):
    """دموی عمومی باید با یک کلیک کار کند؛ نبود توکن یعنی مسیر باز است."""
    assert client.post(f"/api/v1/jobs/{seeded[0]}/save").status_code == 200


def test_writes_require_the_token_once_configured(guarded_client, seeded):
    job_id = seeded[0]
    assert guarded_client.post(f"/api/v1/jobs/{job_id}/save").status_code == 401
    assert guarded_client.post("/api/v1/ingest", json={}).status_code == 401
    assert guarded_client.post(f"/api/v1/jobs/{job_id}/rescore").status_code == 401
    assert guarded_client.post(f"/api/v1/jobs/{job_id}/proposal").status_code == 401


def test_valid_token_allows_writes(guarded_client, seeded):
    response = guarded_client.post(f"/api/v1/jobs/{seeded[0]}/save",
                                   headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    assert payload(response)["data"]["created"] is True


def test_wrong_token_is_rejected(guarded_client, seeded):
    response = guarded_client.post(f"/api/v1/jobs/{seeded[0]}/save",
                                   headers={"X-Admin-Token": "nope"})
    assert response.status_code == 401


def test_reads_stay_open_even_with_a_token(guarded_client, seeded):
    assert guarded_client.get("/api/v1/jobs").status_code == 200
    assert guarded_client.get("/api/v1/overview").status_code == 200
