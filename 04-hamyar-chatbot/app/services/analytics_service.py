# -*- coding: utf-8 -*-
"""Analytics and log read models for the admin panel."""
from __future__ import annotations

from typing import Any

from flask import current_app

from app.database import (
    AnalyticsRepository,
    ConversationRepository,
    HandoffRepository,
    session,
)


class AnalyticsService:
    """Aggregated metrics, conversation logs and handoff queue."""

    @staticmethod
    def overview(days: int = 14) -> dict[str, Any]:
        """Everything the dashboard renders, in one database round trip."""
        days = max(2, min(int(days), 90))
        with session() as conn:
            return AnalyticsRepository(conn).overview(days=days)

    @staticmethod
    def conversations(
        search: str | None = None,
        status: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return a filtered page of the conversation log."""
        if status not in (None, "answered", "unanswered"):
            status = None
        limit = max(1, min(int(limit), int(current_app.config["MAX_PAGE_SIZE"])))
        offset = max(0, int(offset))
        with session() as conn:
            repository = ConversationRepository(conn)
            items = repository.list(
                search=search, status=status, limit=limit, offset=offset
            )
            total = repository.count(search=search, status=status)
        return {
            "items": [turn.to_dict() for turn in items],
            "total": total,
            "limit": limit,
            "offset": offset,
            "search": search or "",
            "status": status or "",
        }

    @staticmethod
    def handoffs(limit: int = 25) -> list[dict[str, Any]]:
        """Return the most recent human-agent requests."""
        with session() as conn:
            return [h.to_dict() for h in HandoffRepository(conn).list(limit=limit)]
