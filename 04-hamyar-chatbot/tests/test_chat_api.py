# -*- coding: utf-8 -*-
"""Conversation API: happy paths, validation and persistence."""
from __future__ import annotations

import json


def post_json(client, path, payload):
    """POST a JSON body and return (status, body)."""
    response = client.post(path, data=json.dumps(payload), content_type="application/json")
    return response.status_code, response.get_json()


class TestChatEndpoint:
    """POST /api/chat"""

    def test_answers_a_known_question(self, client):
        status, body = post_json(
            client, "/api/chat", {"message": "شرایط مرجوعی چیست؟", "session_id": "web-abc123"}
        )
        assert status == 200
        assert body["matched"] is True
        assert body["confidence"] == "high"
        assert "۷ روز" in body["answer"]
        assert body["faq_id"] is not None
        assert body["latency_ms"] >= 0
        assert 0 <= body["relevance"] <= 100

    def test_persian_stays_readable_in_the_response(self, client):
        """The JSON policy is real: answers are not escaped into \\uXXXX."""
        response = client.post(
            "/api/chat",
            data=json.dumps({"message": "هزینه ارسال چقدر است؟"}),
            content_type="application/json",
        )
        raw = response.get_data(as_text=True)
        assert "ارسال" in raw
        assert "\\u0627" not in raw

    def test_generates_a_session_when_missing(self, client):
        status, body = post_json(client, "/api/chat", {"message": "هزینه ارسال چقدر است؟"})
        assert status == 200
        assert body["session_generated"] is True
        assert body["session_id"].startswith("web-")

    def test_keeps_the_supplied_session(self, client):
        status, body = post_json(
            client, "/api/chat", {"message": "سلام", "session_id": "web-keepme1"}
        )
        assert status == 200
        assert body["session_id"] == "web-keepme1"
        assert body["session_generated"] is False

    def test_rejects_empty_message(self, client):
        status, body = post_json(client, "/api/chat", {"message": "   "})
        assert status == 400
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["details"]["field"] == "message"

    def test_rejects_missing_message(self, client):
        status, body = post_json(client, "/api/chat", {})
        assert status == 400
        assert body["error"]["code"] == "validation_error"

    def test_rejects_non_string_message(self, client):
        status, body = post_json(client, "/api/chat", {"message": 12345})
        assert status == 400
        assert body["error"]["details"]["field"] == "message"

    def test_rejects_overlong_message(self, client):
        status, body = post_json(client, "/api/chat", {"message": "الف" * 600})
        assert status == 400
        assert "max_length" in body["error"]["details"]

    def test_rejects_invalid_session_id(self, client):
        status, body = post_json(
            client, "/api/chat", {"message": "سلام", "session_id": "a b"}
        )
        assert status == 400
        assert body["error"]["details"]["field"] == "session_id"

    def test_rejects_non_json_body(self, client):
        response = client.post("/api/chat", data="not json", content_type="text/plain")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "validation_error"

    def test_unknown_question_is_answered_gracefully(self, client):
        status, body = post_json(
            client, "/api/chat", {"message": "قیمت بیت‌کوین امروز چنده؟", "session_id": "web-abc123"}
        )
        assert status == 200
        assert body["matched"] is False
        assert body["confidence"] == "low"
        assert body["answer"]
        assert body["fallback_reason"] in (
            "low_confidence",
            "out_of_domain",
            "no_knowledge_base",
        )

    def test_repeated_turns_are_logged(self, client):
        for _ in range(3):
            post_json(
                client,
                "/api/chat",
                {"message": "هزینه ارسال چقدر است؟", "session_id": "web-rep1234"},
            )
        data = client.get("/api/history?session_id=web-rep1234").get_json()
        assert data["count"] == 3
        assert all(turn["message"] == "هزینه ارسال چقدر است؟" for turn in data["turns"])


class TestHistoryEndpoint:
    """GET /api/history"""

    def test_unknown_session_returns_empty_list(self, client):
        data = client.get("/api/history?session_id=web-nothing1").get_json()
        assert data["count"] == 0
        assert data["turns"] == []

    def test_missing_session_is_rejected(self, client):
        response = client.get("/api/history")
        assert response.status_code == 400

    def test_transcript_is_ordered_oldest_first(self, client):
        post_json(client, "/api/chat", {"message": "پیام اول دربارهٔ ارسال", "session_id": "web-order01"})
        post_json(client, "/api/chat", {"message": "پیام دوم دربارهٔ پرداخت", "session_id": "web-order01"})
        turns = client.get("/api/history?session_id=web-order01").get_json()["turns"]
        assert turns[0]["message"].startswith("پیام اول")
        assert turns[1]["message"].startswith("پیام دوم")


class TestFeedbackEndpoint:
    """POST /api/feedback"""

    def test_accepts_up_and_down(self, client):
        conversation_id = post_json(
            client, "/api/chat", {"message": "سلام", "session_id": "web-vote001"}
        )[1]["conversation_id"]
        status, body = post_json(
            client, "/api/feedback", {"conversation_id": conversation_id, "feedback": "up"}
        )
        assert status == 200 and body["ok"] is True

        status, _ = post_json(
            client, "/api/feedback", {"conversation_id": conversation_id, "feedback": "down"}
        )
        assert status == 200

    def test_rejects_unknown_value(self, client):
        status, body = post_json(
            client, "/api/feedback", {"conversation_id": 1, "feedback": "maybe"}
        )
        assert status == 400
        assert body["error"]["details"]["field"] == "feedback"

    def test_rejects_invalid_id(self, client):
        status, _ = post_json(client, "/api/feedback", {"conversation_id": "abc", "feedback": "up"})
        assert status == 400

    def test_unknown_conversation_returns_404(self, client):
        status, body = post_json(
            client, "/api/feedback", {"conversation_id": 987654, "feedback": "up"}
        )
        assert status == 404
        assert body["error"]["code"] == "not_found"


class TestHandoffAndSuggestions:
    """POST /api/handoff and GET /api/suggestions"""

    def test_handoff_returns_a_ticket(self, client):
        status, body = post_json(
            client,
            "/api/handoff",
            {"session_id": "web-hand001", "reason": "نیاز به کارشناس", "last_query": "پرسش"},
        )
        assert status == 201
        assert body["ok"] is True
        assert body["ticket"].startswith("HM-")

    def test_handoff_requires_session(self, client):
        status, _ = post_json(client, "/api/handoff", {"reason": "بدون نشست"})
        assert status == 400

    def test_suggestions_are_filtered_by_query(self, client):
        data = client.get("/api/suggestions?q=مرجوع").get_json()
        assert data["suggestions"]
        assert all("مرجوع" in item for item in data["suggestions"])

    def test_suggestions_without_query_return_defaults(self, client):
        data = client.get("/api/suggestions").get_json()
        assert len(data["suggestions"]) >= 1
