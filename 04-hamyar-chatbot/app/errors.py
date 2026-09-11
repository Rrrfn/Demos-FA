# -*- coding: utf-8 -*-
"""Application errors and their JSON handlers.

Every API failure follows one envelope:

``{"error": {"code": "validation_error", "message": "...", "details": {...}}}``

so the front-end can render a message without guessing the shape.
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException


class HamyarError(Exception):
    """Base class for expected, user-facing failures."""

    status_code = 400
    code = "error"

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        """Serialise the error envelope."""
        payload: dict = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return {"error": payload}


class ValidationError(HamyarError):
    """The request payload was missing or malformed."""

    status_code = 400
    code = "validation_error"


class NotFoundError(HamyarError):
    """The requested resource does not exist."""

    status_code = 404
    code = "not_found"


class UnauthorizedError(HamyarError):
    """The caller is not allowed to perform this action."""

    status_code = 401
    code = "unauthorized"


def wants_json() -> bool:
    """True when the client expects JSON rather than an HTML page."""
    if request.path.startswith("/api/") or request.path == "/health":
        return True
    return request.accept_mimetypes.best == "application/json"


def register_error_handlers(app: Flask) -> None:
    """Attach JSON/HTML handlers for application and HTTP errors."""

    @app.errorhandler(HamyarError)
    def _handle_app_error(error: HamyarError):
        if wants_json():
            return jsonify(error.to_dict()), error.status_code
        return render_template("error.html", error=error), error.status_code

    @app.errorhandler(HTTPException)
    def _handle_http_error(error: HTTPException):
        if error.code == 404 and not wants_json():
            return render_template(
                "error.html",
                error=NotFoundError("صفحه‌ای که دنبالش بودید پیدا نشد."),
            ), 404
        if wants_json():
            return (
                jsonify(
                    {
                        "error": {
                            "code": (error.name or "http_error").lower().replace(" ", "_"),
                            "message": error.description,
                        }
                    }
                ),
                error.code,
            )
        return error

    @app.errorhandler(Exception)
    def _handle_unexpected(error: Exception):
        app.logger.exception("unhandled error: %s", error)
        if wants_json():
            return (
                jsonify(
                    {
                        "error": {
                            "code": "internal_error",
                            "message": "خطای غیرمنتظره در سرور رخ داد.",
                        }
                    }
                ),
                500,
            )
        return render_template(
            "error.html",
            error=HamyarError("خطای غیرمنتظره در سرور رخ داد."),
        ), 500
