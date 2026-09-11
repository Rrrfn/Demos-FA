# -*- coding: utf-8 -*-
"""چشم‌باز — داشبورد هوشمند بازار.

قرارداد این پکیج:

* import کردن آن هیچ عارضهٔ جانبی ندارد — نه پایگاه داده می‌سازد، نه به
  شبکه می‌رود، نه زمان‌بند را روشن می‌کند.
* هیچ عددی بدون منبع و بدون برچسب تازگی به کاربر نمی‌رسد.
* نقطهٔ ورود ``python -m cheshmbaz`` است.

نمونهٔ استفاده::

    from cheshmbaz.context import AppContext

    context = AppContext.build()
    context.bootstrap()
    context.market.overview()
"""
from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["__version__"]
