# -*- coding: utf-8 -*-
"""Knowledge-base index lifecycle.

The engine lives in ``app.extensions`` instead of a module-level global. That
single change removes the import-order coupling that made the previous version
need a live database at import time.
"""
from __future__ import annotations

import logging

from flask import Flask, current_app

from app.database import FaqRepository, session
from app.nlp import ChatEngine

logger = logging.getLogger(__name__)

EXTENSION_KEY = "hamyar"


def init_engine(app: Flask) -> ChatEngine:
    """Create the engine from configuration and register it on the app."""
    engine = ChatEngine(
        high_confidence=app.config["HIGH_CONFIDENCE"],
        medium_confidence=app.config["MEDIUM_CONFIDENCE"],
        suggestion_floor=app.config["SUGGESTION_FLOOR"],
        max_suggestions=app.config["MAX_SUGGESTIONS"],
        evidence_floor=app.config["EVIDENCE_FLOOR"],
        char_support=app.config["CHAR_SUPPORT_FLOOR"],
    )
    app.extensions.setdefault(EXTENSION_KEY, {})["engine"] = engine
    return engine


def get_engine() -> ChatEngine:
    """Return the engine bound to the current application."""
    engine = current_app.extensions.get(EXTENSION_KEY, {}).get("engine")
    if engine is None:  # pragma: no cover - only reachable on a broken setup
        raise RuntimeError("chat engine is not initialised on this application")
    return engine


def rebuild_engine() -> dict[str, object]:
    """Reload the index from the database and return engine statistics.

    Called once at start-up and after every knowledge-base write, which is what
    makes admin edits visible to the next question without a restart.
    """
    with session() as conn:
        repository = FaqRepository(conn)
        faqs = repository.list(limit=100_000)
        entries = repository.kb_entries()

    engine = get_engine()
    engine.load(entries, {faq.id: faq for faq in faqs})
    stats = engine.stats()
    logger.info(
        "knowledge index rebuilt: %s entries / %s faqs",
        stats["entries"],
        stats["faqs"],
    )
    return stats
