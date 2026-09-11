# -*- coding: utf-8 -*-
"""HTTP layer: one blueprint per concern."""
from flask import Flask

from .chat_api import bp as chat_api_bp
from .faq_api import bp as faq_api_bp
from .pages import bp as pages_bp
from .system_api import bp as system_api_bp

BLUEPRINTS = (pages_bp, chat_api_bp, faq_api_bp, system_api_bp)


def register_blueprints(app: Flask) -> None:
    """Attach every blueprint to the application."""
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
