# -*- coding: utf-8 -*-
"""Production WSGI entry point.

    gunicorn wsgi:app --bind 0.0.0.0:$PORT

``HAMYAR_ENV=production`` (the default in this module) turns on the production
configuration; gunicorn's own workers provide the concurrency.
"""
from __future__ import annotations

import os

from app import create_app

os.environ.setdefault("HAMYAR_ENV", "production")

app = create_app()

if __name__ == "__main__":  # pragma: no cover - convenience for plain python
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
