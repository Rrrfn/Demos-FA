# -*- coding: utf-8 -*-
"""نقطهٔ ورود تولیدی — gunicorn این را بالا می‌آورد.

تفاوت مهم با ``app.py`` در یک چیز است: اینجا مدل **پیش از نخستین درخواست**
گرم می‌شود. اگر گرم‌کردن انجام نشود، کارگر هنگام رسیدن اولین بازدیدکننده
باید مدل را از دیسک بخواند و نخستین صفحهٔ «تحلیل متن» چند صد میلی‌ثانیه کند
می‌شود؛ همان چیزی که در بار سرد به چشم می‌آید. مدل کوچک است، پس این هزینه یک
بار پرداخت می‌شود و بعد حافظه سرویس می‌ماند.

اجرا:
    gunicorn wsgi:application --bind 0.0.0.0:$PORT
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from hassanj.web import create_app          # noqa: E402

application = create_app()                  # noqa: N816

#: در آزمون‌ها و ابزارهای کاوش، گرم‌کردن با متغیر محیطی خاموش می‌شود.
if os.environ.get("HASSANJ_WARM_MODEL", "1") not in ("0", "false", "False"):
    try:
        from hassanj import services

        services.model()
    except Exception:                       # noqa: BLE001
        # گرم‌کردن نباید بالا آمدن سرویس را بشکند؛ اگر شکست خورد، مدل در
        # نخستین درخواست ساخته می‌شود — کندتر، ولی سالم.
        application.logger.warning("گرم‌کردن مدل شکست خورد؛ در نخستین درخواست ساخته می‌شود.",
                                   exc_info=True)
