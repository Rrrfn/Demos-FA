# -*- coding: utf-8 -*-
"""قیمت‌یار — ربات تلگرام پایش هوشمند بازار.

اجرا:

* توسعه (polling): ``python -m ghematyar``
* تولید (webhook):  ``python -m ghematyar webhook``  یا  ``gunicorn webapp:app``
* آزمون منابع:      ``python -m ghematyar check``

نکتهٔ معماری: import کردن این پکیج هیچ عارضهٔ جانبی ندارد — نه پایگاه
داده ساخته می‌شود، نه به شبکه می‌رود و نه توکن تلگرام لازم است. همه‌چیز
داخل ``build_services`` و ``build_runtime`` ساخته می‌شود.
"""
from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["__version__"]
