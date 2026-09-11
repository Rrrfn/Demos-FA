# -*- coding: utf-8 -*-
"""Pages, static assets, health and error handling."""
from __future__ import annotations


class TestVisitorPage:
    """GET /"""

    def test_renders_chat_experience(self, client):
        response = client.get("/")
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="chatRoot"' in html
        assert 'id="composer"' in html
        assert "دستیار پشتیبانی" in html

    def test_renders_categories_and_samples(self, client):
        html = client.get("/").get_data(as_text=True)
        assert "سفارش و ارسال" in html
        assert 'data-category=' in html
        assert 'data-ask=' in html

    def test_exposes_engine_metrics(self, client):
        html = client.get("/").get_data(as_text=True)
        assert 'id="kbCount"' in html
        assert 'id="mConfidence"' in html


class TestAdminPage:
    """GET /admin"""

    def test_renders_console(self, client):
        response = client.get("/admin")
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        for marker in ("داشبورد پشتیبانی", "مدیریت دانشنامه", "نشست‌های گفت‌وگو", "مرجع API"):
            assert marker in html

    def test_renders_kpis_and_knowledge_base(self, client):
        html = client.get("/admin").get_data(as_text=True)
        assert "نرخ پاسخ دانشنامه" in html
        assert 'id="kbRows"' in html
        assert 'id="faqModal"' in html
        assert 'data-tab="kb"' in html


class TestEmbedPage:
    """GET /embed and GET /widget.js"""

    def test_embed_demo_renders(self, client):
        html = client.get("/embed").get_data(as_text=True)
        assert "widget.js" in html
        assert "Hamyar.open()" in html

    def test_widget_is_served_as_javascript_with_cors(self, client):
        response = client.get("/widget.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["Content-Type"]
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        assert "Hamyar" in response.get_data(as_text=True)


class TestStaticAssets:
    """Static files must resolve — a missing font or stylesheet breaks the UI."""

    def test_stylesheets(self, client):
        for path in ("/static/css/app.css", "/static/css/admin.css"):
            assert client.get(path).status_code == 200

    def test_scripts(self, client):
        for path in ("/static/js/chat.js", "/static/js/admin.js", "/static/js/widget.js"):
            assert client.get(path).status_code == 200

    def test_fonts(self, client):
        for weight in ("Regular", "Bold", "Black"):
            assert client.get(f"/static/fonts/Vazirmatn-{weight}.woff2").status_code == 200


class TestHealth:
    """GET /health"""

    def test_reports_ok_with_index(self, client):
        body = client.get("/health").get_json()
        assert body["status"] == "ok"
        assert body["service"] == "hamyar-chatbot"
        assert body["engine"]["ready"] is True
        assert body["database"]["faqs"] >= 40

    def test_exposes_configuration(self, client):
        body = client.get("/health").get_json()
        assert body["config"]["high_confidence"] > body["config"]["medium_confidence"]
        assert body["env"] == "testing"


class TestStats:
    """GET /api/stats"""

    def test_returns_dashboard_shape(self, client):
        body = client.get("/api/stats").get_json()
        assert {"turns", "match_rate", "daily", "confidence", "top_unanswered"} <= set(body)
        assert isinstance(body["daily"], list)


class TestErrorHandling:
    """One envelope for JSON, one page for browsers."""

    def test_unknown_api_path_returns_json(self, client):
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.get_json()["error"]["code"]

    def test_unknown_page_returns_html(self, client):
        response = client.get("/nope", headers={"Accept": "text/html"})
        assert response.status_code == 404
        assert "text/html" in response.headers["Content-Type"]

    def test_method_not_allowed_is_json(self, client):
        response = client.get("/api/chat")
        assert response.status_code == 405
        assert response.get_json()["error"]["code"] == "method_not_allowed"
