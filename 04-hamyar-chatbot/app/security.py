# -*- coding: utf-8 -*-
"""Lightweight write protection for the admin API.

A public demo must stay usable, so protection is *opt-in*: set
``HAMYAR_ADMIN_TOKEN`` and every write endpoint starts requiring the matching
``X-Admin-Token`` header. When the variable is unset the demo runs open and the
UI says so explicitly.
"""
from __future__ import annotations

import hmac
from functools import wraps
from typing import Callable, TypeVar

from flask import current_app, request

from .errors import UnauthorizedError

F = TypeVar("F", bound=Callable)


def admin_token() -> str | None:
    """Configured admin token, if any."""
    return current_app.config.get("ADMIN_TOKEN") or None


def admin_protected() -> bool:
    """True when write endpoints are protected by a token."""
    return admin_token() is not None


def _token_matches(supplied: str | None) -> bool:
    """Constant-time comparison of the supplied token."""
    expected = admin_token()
    if not expected:
        return True
    return bool(supplied) and hmac.compare_digest(str(supplied), expected)


def admin_required(view: F) -> F:
    """Reject the request unless it carries the configured admin token."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        supplied = request.headers.get("X-Admin-Token") or request.args.get("token")
        if not _token_matches(supplied):
            raise UnauthorizedError(
                "برای تغییر دانشنامه، توکن مدیریت لازم است.",
                {"header": "X-Admin-Token"},
            )
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
