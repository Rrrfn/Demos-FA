# -*- coding: utf-8 -*-
"""Development entry point — ``python -m app``.

Production never uses this module; it runs under gunicorn via ``wsgi:app``.
"""
from __future__ import annotations

import os

from app import create_app


def main() -> None:
    """Start the development server with auto-reload."""
    app = create_app("development")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(
        host=host,
        port=port,
        debug=app.config["DEBUG"],
        use_reloader=app.config["DEBUG"],
        threaded=True,
    )


if __name__ == "__main__":
    main()
