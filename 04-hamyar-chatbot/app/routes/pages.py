# -*- coding: utf-8 -*-
"""Server-rendered pages.

GET /         visitor chat experience
GET /admin    support console (dashboard, knowledge base, logs)
GET /embed    demo of the embeddable widget on a mock storefront
GET /widget.js the widget itself, servable to any other site
"""
from __future__ import annotations

from flask import Blueprint, current_app, make_response, render_template, request

from app.security import admin_protected
from app.services import AnalyticsService, FaqService, get_engine

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    """Visitor-facing chat experience with categories and starter questions."""
    engine = get_engine()
    categories = FaqService.categories()
    return render_template(
        "index.html",
        categories=categories,
        sample_questions=engine.sample_questions(6),
        engine_stats=engine.stats(),
        admin_protected=admin_protected(),
    )


@bp.get("/admin")
def admin():
    """Support console: metrics, knowledge base and conversation log."""
    page = FaqService.list(limit=200)
    logs = AnalyticsService.conversations(limit=25)
    return render_template(
        "admin.html",
        overview=AnalyticsService.overview(days=14),
        faqs=page["items"],
        faq_total=page["total"],
        categories=FaqService.categories(),
        logs=logs["items"],
        log_total=logs["total"],
        handoffs=AnalyticsService.handoffs(limit=10),
        engine_stats=get_engine().stats(),
        admin_protected=admin_protected(),
    )


@bp.get("/embed")
def embed():
    """Show the widget embedded in a mock storefront page."""
    return render_template(
        "embed_demo.html",
        widget_host=request.host_url.rstrip("/"),
    )


@bp.get("/widget.js")
def widget():
    """Serve the embeddable widget with CORS enabled."""
    response = make_response(current_app.send_static_file("js/widget.js"))
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "public, max-age=300"
    return response
