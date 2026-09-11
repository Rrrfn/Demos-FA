# -*- coding: utf-8 -*-
"""Operational endpoints.

GET /health      liveness + readiness, also used by the Render health check
GET /api/stats   dashboard aggregates (JSON view of the same numbers)
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.database import connect
from app.services import AnalyticsService, get_engine

bp = Blueprint("system_api", __name__)


@bp.get("/health")
def health():
    """Report service, engine and database status.

    Always returns HTTP 200 while the process can serve traffic; the ``status``
    field turns to ``degraded`` when the knowledge index is empty, which keeps a
    cold deploy alive instead of being marked unhealthy.
    """
    engine = get_engine()
    stats = engine.stats()

    counts = {"faqs": 0, "conversations": 0, "handoffs": 0}
    try:
        with connect() as conn:
            counts["faqs"] = conn.execute("SELECT COUNT(*) FROM faq").fetchone()[0]
            counts["conversations"] = conn.execute(
                "SELECT COUNT(*) FROM conversation"
            ).fetchone()[0]
            counts["handoffs"] = conn.execute("SELECT COUNT(*) FROM handoff").fetchone()[0]
    except Exception as error:  # pragma: no cover - database unavailable
        current_app.logger.warning("health check could not read the database: %s", error)
        counts["error"] = "database_unavailable"

    ready = bool(stats["ready"]) and counts["faqs"] > 0
    return jsonify(
        {
            "status": "ok" if ready else "degraded",
            "service": "hamyar-chatbot",
            "version": current_app.config.get("APP_VERSION", "2.0.0"),
            "env": current_app.config["ENV_NAME"],
            "engine": stats,
            "database": counts,
            "config": {
                "high_confidence": current_app.config["HIGH_CONFIDENCE"],
                "medium_confidence": current_app.config["MEDIUM_CONFIDENCE"],
            },
        }
    )


@bp.get("/api/stats")
def stats():
    """Return dashboard aggregates as JSON."""
    days = request.args.get("days", 14, type=int)
    return jsonify(AnalyticsService.overview(days=days))


@bp.get("/api/conversations")
def conversations():
    """Search and filter the conversation log."""
    return jsonify(
        AnalyticsService.conversations(
            search=request.args.get("search") or None,
            status=request.args.get("status") or None,
            limit=request.args.get("limit", 25, type=int),
            offset=request.args.get("offset", 0, type=int),
        )
    )


@bp.get("/api/handoffs")
def handoffs():
    """Return the human-agent queue."""
    return jsonify({"handoffs": AnalyticsService.handoffs(limit=50)})
