# -*- coding: utf-8 -*-
"""Hamyar — AI customer support platform (Flask application package).

Importing this package has **no side effects**: it does not open the database,
build the search index or create an application instance. Everything happens
inside :func:`create_app`, which is what removes the import-order coupling the
previous single-module layout suffered from.

Running the app
---------------
development      ``python -m app``
production       ``gunicorn wsgi:app``
flask CLI        ``flask --app app run``
"""
from __future__ import annotations

import logging
import os
import sys

from flask import Flask

from app.config import get_config
from app.database import initialize_database
from app.errors import register_error_handlers
from app.nlp import digits_to_persian
from app.routes import register_blueprints
from app.services import init_engine, rebuild_engine

APP_VERSION = "2.0.0"


def configure_logging(app: Flask) -> None:
    """Log to stdout so the platform (Render, Docker) captures it."""
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    app.logger.setLevel(level)


def configure_json(app: Flask) -> None:
    """Apply the JSON rendering policy.

    Flask 2.3 moved these switches off ``app.config`` onto the JSON provider.
    They are copied across explicitly here, because a configuration key that
    silently does nothing is worse than no key at all: Persian answers are
    meant to stay readable in the response body.
    """
    app.json.ensure_ascii = bool(app.config.get("JSON_AS_ASCII", False))
    app.json.sort_keys = bool(app.config.get("JSON_SORT_KEYS", False))


def register_template_helpers(app: Flask) -> None:
    """Expose small formatting helpers to Jinja."""

    @app.template_filter("fa_digits")
    def _fa_digits(value: object) -> str:
        """Render numbers with Persian digits."""
        return digits_to_persian(value)

    @app.context_processor
    def _globals() -> dict:
        return {
            "app_version": APP_VERSION,
            "brand_name": "همیار",
            "brand_tagline": "دستیار هوشمند پشتیبانی",
        }


def create_app(
    config_name: str | None = None,
    overrides: dict | None = None,
) -> Flask:
    """Build the Flask application.

    ``config_name`` selects development / production / testing, and
    ``overrides`` lets tests point at their own database.
    """
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
        static_url_path="/static",
    )
    app.config.from_object(get_config(config_name))
    app.config["APP_VERSION"] = APP_VERSION
    if overrides:
        app.config.update(overrides)

    configure_logging(app)
    configure_json(app)

    # Storage first, then the in-memory index built from it. Doing this inside
    # an explicit application context keeps the order obvious and testable.
    initialize_database(app.config["DB_PATH"])
    init_engine(app)
    with app.app_context():
        rebuild_engine()

    register_error_handlers(app)
    register_blueprints(app)
    register_template_helpers(app)

    @app.cli.command("init-db")
    def init_db_command() -> None:  # pragma: no cover - manual utility
        """Create the schema and seed the knowledge base if it is empty."""
        path = initialize_database(app.config["DB_PATH"])
        with app.app_context():
            stats = rebuild_engine()
        print(f"database ready at {path} — index: {stats}")

    app.logger.info(
        "hamyar %s started (env=%s, debug=%s)", APP_VERSION, app.config["ENV_NAME"], app.debug
    )
    return app


__all__ = ["create_app", "APP_VERSION"]
