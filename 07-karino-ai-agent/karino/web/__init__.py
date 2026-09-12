# -*- coding: utf-8 -*-
"""لایهٔ وب — بلوپرینت‌های صفحات و API."""
from .api import bp as api_bp
from .pages import bp as pages_bp

__all__ = ["pages_bp", "api_bp"]
