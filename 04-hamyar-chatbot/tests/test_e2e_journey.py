# -*- coding: utf-8 -*-
"""End-to-end journeys.

The first test walks the whole product through HTTP: a visitor asks, rates the
answer, asks something unknown, requests a human, and an operator sees all of it
in the console. The second test drives a real browser when Playwright is
installed; otherwise it is skipped, not failed.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest


def post_json(client, path, payload):
    """POST a JSON body and return (status, body)."""
    response = client.post(path, data=json.dumps(payload), content_type="application/json")
    return response.status_code, response.get_json()


class TestVisitorToOperatorJourney:
    """One continuous story across the whole application."""

    def test_complete_journey(self, client):
        session_id = "web-journey1"

        # 1. A visitor asks a question the knowledge base can answer.
        status, reply = post_json(
            client, "/api/chat", {"message": "هزینه ارسال چقدر است؟", "session_id": session_id}
        )
        assert status == 200 and reply["matched"] is True
        conversation_id = reply["conversation_id"]

        # 2. The answer is rated as helpful.
        assert post_json(
            client, "/api/feedback", {"conversation_id": conversation_id, "feedback": "up"}
        )[0] == 200

        # 3. The visitor asks something outside the knowledge base.
        status, unknown = post_json(
            client, "/api/chat", {"message": "برای من یک فنجان قهوه سفارش بده", "session_id": session_id}
        )
        assert status == 200
        assert unknown["matched"] is False
        assert unknown["answer"]

        # 4. The visitor asks for a human instead.
        status, handoff = post_json(
            client, "/api/handoff", {"session_id": session_id, "reason": "پاسخ کافی نبود"}
        )
        assert status == 201 and handoff["ticket"].startswith("HM-")

        # 5. The transcript holds every turn in order.
        transcript = client.get(f"/api/history?session_id={session_id}").get_json()
        assert transcript["count"] == 2
        assert transcript["turns"][0]["feedback"] == "up"

        # 6. The dashboard reflects the activity.
        stats = client.get("/api/stats").get_json()
        assert stats["turns"] >= 2
        assert stats["answered"] >= 1
        assert stats["unanswered"] >= 1
        assert stats["handoffs"] >= 1
        assert stats["top_unanswered"][0]["message"] == "برای من یک فنجان قهوه سفارش بده"

        # 7. The operator sees the question in the log and opens the console.
        log = client.get("/api/conversations?status=unanswered").get_json()
        assert log["total"] >= 1
        assert client.get("/admin").status_code == 200

    def test_knowledge_gap_can_be_closed_from_the_console(self, client):
        """Whatever the visitors keep failing to ask becomes a new FAQ."""
        question = "برای من یک فنجان قهوه سفارش بده"
        post_json(client, "/api/chat", {"message": question, "session_id": "web-gap00001"})
        assert client.get("/api/stats").get_json()["unanswered"] >= 1

        status, created = post_json(
            client,
            "/api/faqs",
            {
                "question": "سفارش قهوه یا نوشیدنی هم می‌گیرید؟",
                "answer": "خیر، تنها کالاهای فهرست‌شده در فروشگاه قابل سفارش هستند.",
                "category": "محصولات و موجودی",
                "variants": [question, "نوشیدنی هم دارید؟"],
            },
        )
        assert status == 201
        assert created["faq"]["id"]

        # The same visitor question is now answered from the knowledge base.
        status, reply = post_json(client, "/api/chat", {"message": question})
        assert status == 200
        assert reply["matched"] is True
        assert reply["faq_id"] == created["faq"]["id"]


def _free_port() -> int:
    """Ask the OS for an unused port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.browser
def test_browser_smoke(tmp_path):
    """Drive a real browser through the chat page (Playwright only)."""
    playwright = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")
    port = _free_port()
    env = dict(os.environ, PORT=str(port), HAMYAR_ENV="development", HAMYAR_DB_PATH=str(tmp_path / "e2e.db"))
    server = subprocess.Popen(
        [sys.executable, "-m", "app"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):  # wait for the server to accept connections
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                if server.poll() is not None:
                    pytest.fail("dev server exited during start-up")
                time.sleep(0.5)

        with playwright.sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.goto(base + "/", wait_until="networkidle")

            assert page.locator("#chatRoot").is_visible()
            page.fill("#message", "شرایط مرجوعی چیست؟")
            page.click("#send")
            page.wait_for_selector(".msg--bot .msg__bubble", timeout=15000)
            page.wait_for_function(
                "() => document.querySelector('.msg--bot .msg__bubble').textContent.length > 20"
            )
            assert "۷ روز" in page.locator(".msg--bot .msg__bubble").first.text_content()
            assert not console_errors, console_errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
