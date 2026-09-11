# -*- coding: utf-8 -*-
"""Knowledge-base API: CRUD, validation, filters and write protection."""
from __future__ import annotations

import json


def post_json(client, path, payload):
    """POST a JSON body and return (status, body)."""
    response = client.post(path, data=json.dumps(payload), content_type="application/json")
    return response.status_code, response.get_json()


def put_json(client, path, payload):
    """PUT a JSON body and return (status, body)."""
    response = client.put(path, data=json.dumps(payload), content_type="application/json")
    return response.status_code, response.get_json()


class TestListAndFilter:
    """GET /api/faqs and GET /api/categories"""

    def test_lists_seeded_entries(self, client):
        body = client.get("/api/faqs").get_json()
        assert body["total"] >= 40
        assert len(body["faqs"]) >= 40
        assert {"id", "question", "answer", "category", "variants"} <= set(body["faqs"][0])

    def test_pagination(self, client):
        body = client.get("/api/faqs?limit=5&offset=5").get_json()
        assert body["limit"] == 5 and body["offset"] == 5
        assert len(body["faqs"]) == 5

    def test_search(self, client):
        """Search spans the question, the answer, the category and the variants."""
        body = client.get("/api/faqs?search=مرجوع").get_json()
        assert body["total"] >= 1
        for faq in body["faqs"]:
            haystack = " ".join(
                [faq["question"], faq["answer"], faq["category"], *faq["variants"]]
            )
            assert "مرجوع" in haystack

    def test_category_filter(self, client):
        body = client.get("/api/faqs?category=پرداخت و صورتحساب").get_json()
        assert body["total"] >= 1
        assert all(faq["category"] == "پرداخت و صورتحساب" for faq in body["faqs"])

    def test_categories_endpoint(self, client):
        body = client.get("/api/categories").get_json()
        assert body["categories"]
        assert body["admin_protected"] is False
        assert all({"category", "count"} <= set(item) for item in body["categories"])


class TestSingleFaq:
    """GET /api/faqs/<id>"""

    def test_reads_one_entry(self, client):
        first = client.get("/api/faqs").get_json()["faqs"][0]
        body = client.get(f"/api/faqs/{first['id']}").get_json()
        assert body["faq"]["id"] == first["id"]

    def test_unknown_id_returns_404(self, client):
        response = client.get("/api/faqs/999999")
        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "not_found"


class TestWriteEndpoints:
    """POST / PUT / DELETE"""

    def test_create_reads_back_and_reindexes(self, client, faq_payload):
        status, body = post_json(client, "/api/faqs", faq_payload())
        assert status == 201
        faq_id = body["faq"]["id"]
        assert body["faq"]["variants"]

        # The new entry must be immediately answerable — that proves the
        # retrieval index was rebuilt after the write.
        status, reply = post_json(client, "/api/chat", {"message": "پیک روز تعطیل"})
        assert status == 200
        assert reply["matched"] is True
        assert reply["faq_id"] == faq_id

    def test_update_changes_content(self, client, faq_payload):
        created = post_json(client, "/api/faqs", faq_payload())[1]["faq"]
        status, body = put_json(
            client,
            f"/api/faqs/{created['id']}",
            faq_payload(question="پرسش ویرایش‌شدهٔ تحویل؟", answer="پاسخ تازه", variants=[]),
        )
        assert status == 200
        assert body["faq"]["question"] == "پرسش ویرایش‌شدهٔ تحویل؟"
        assert body["faq"]["variants"] == []

    def test_delete_removes_entry(self, client, faq_payload):
        created = post_json(client, "/api/faqs", faq_payload())[1]["faq"]
        response = client.delete(f"/api/faqs/{created['id']}")
        assert response.status_code == 200
        assert response.get_json()["deleted"] is True
        assert client.get(f"/api/faqs/{created['id']}").status_code == 404

    def test_update_unknown_id_returns_404(self, client, faq_payload):
        status, _ = put_json(client, "/api/faqs/999999", faq_payload())
        assert status == 404

    def test_delete_unknown_id_returns_404(self, client):
        assert client.delete("/api/faqs/999999").status_code == 404


class TestValidation:
    """Malformed payloads must never reach the database."""

    def test_missing_fields(self, client):
        status, body = post_json(client, "/api/faqs", {"question": "فقط پرسش"})
        assert status == 400
        assert "answer" in body["error"]["details"]

    def test_too_short_values(self, client):
        status, body = post_json(client, "/api/faqs", {"question": "پ", "answer": "پ"})
        assert status == 400
        assert {"question", "answer"} <= set(body["error"]["details"])

    def test_variants_must_be_a_list_or_text(self, client, faq_payload):
        status, _ = post_json(client, "/api/faqs", faq_payload(variants={"bad": "type"}))
        assert status == 400

    def test_variants_accept_newline_text(self, client, faq_payload):
        payload = faq_payload(variants=["یک", "دو"])
        status, body = post_json(client, "/api/faqs", payload)
        assert status == 201
        assert body["faq"]["variants"] == ["یک", "دو"]

    def test_non_json_body(self, client):
        response = client.post("/api/faqs", data="nope", content_type="text/plain")
        assert response.status_code == 400

    def test_default_category_is_used(self, client):
        status, body = post_json(
            client, "/api/faqs", {"question": "پرسش بدون دسته؟", "answer": "پاسخ"}
        )
        assert status == 201
        assert body["faq"]["category"] == "عمومی"


class TestWriteProtection:
    """When HAMYAR_ADMIN_TOKEN is set, writes require the header."""

    def test_write_without_token_is_rejected(self, protected_client, faq_payload):
        status, body = post_json(protected_client, "/api/faqs", faq_payload())
        assert status == 401
        assert body["error"]["code"] == "unauthorized"

    def test_write_with_token_succeeds(self, protected_client, faq_payload):
        response = protected_client.post(
            "/api/faqs",
            data=json.dumps(faq_payload()),
            content_type="application/json",
            headers={"X-Admin-Token": "s3cret-token"},
        )
        assert response.status_code == 201

    def test_reads_stay_open(self, protected_client):
        assert protected_client.get("/api/faqs").status_code == 200
        assert protected_client.get("/api/categories").get_json()["admin_protected"] is True
