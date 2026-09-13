# -*- coding: utf-8 -*-
"""نقطهٔ ورود توسعه.

    python app.py

برای اجرای تولیدی از gunicorn استفاده کنید:

    gunicorn reportsaz.webapp:app --workers 1 --threads 4
"""
from __future__ import annotations

import os

from reportsaz.config import PORT
from reportsaz.web import create_app

app = create_app()


if __name__ == "__main__":
    #: ``--reload`` فقط در توسعه؛ در تولید gunicorn بار را می‌کشد.
    debug = os.environ.get("APP_ENV", "development") != "production"
    app.run(host="0.0.0.0", port=PORT, debug=debug, threaded=True)
