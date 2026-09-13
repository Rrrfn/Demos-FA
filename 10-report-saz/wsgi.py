# -*- coding: utf-8 -*-
"""نقطهٔ ورود تولید — برای gunicorn و سرورهای WSGI.

    gunicorn wsgi:app --bind 0.0.0.0:$PORT
"""
from __future__ import annotations

from reportsaz.webapp import app

__all__ = ["app"]
