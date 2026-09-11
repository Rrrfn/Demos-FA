# -*- coding: utf-8 -*-
"""Application configuration.

Every tunable value is read from the environment so the same code base can run
in development, tests and production without edits.

Environment variables
---------------------
HAMYAR_ENV            development | production | testing   (default: development)
HAMYAR_DB_PATH        absolute path of the SQLite file    (default: <repo>/data/hamyar.db)
HAMYAR_SECRET_KEY     Flask secret key
HAMYAR_ADMIN_TOKEN    if set, write APIs require X-Admin-Token
HAMYAR_HIGH_CONF      high-confidence threshold override  (default: 0.52)
HAMYAR_MED_CONF       medium-confidence threshold override(default: 0.30)
PORT                  port used by the dev server and gunicorn
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "hamyar.db"


def _env_float(name: str, default: float) -> float:
    """Read a float from the environment, ignoring malformed values."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Config:
    """Base configuration shared by every environment."""

    ENV_NAME = "development"
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.environ.get("HAMYAR_SECRET_KEY", "hamyar-demo-secret-key")

    # ---------------------------------------------------------------- storage
    DB_PATH = Path(os.environ.get("HAMYAR_DB_PATH") or DEFAULT_DB_PATH)

    # ------------------------------------------------------------- retrieval
    HIGH_CONFIDENCE = _env_float("HAMYAR_HIGH_CONF", 0.52)
    MEDIUM_CONFIDENCE = _env_float("HAMYAR_MED_CONF", 0.30)
    SUGGESTION_FLOOR = _env_float("HAMYAR_SUGGEST_FLOOR", 0.12)
    MAX_SUGGESTIONS = 3
    # A match must be backed by IDF-weighted evidence, or by strong character
    # overlap when the visitor's words are unknown to the corpus.
    EVIDENCE_FLOOR = _env_float("HAMYAR_EVIDENCE_FLOOR", 0.45)
    CHAR_SUPPORT_FLOOR = _env_float("HAMYAR_CHAR_SUPPORT", 0.75)

    # ------------------------------------------------------------------- API
    MAX_MESSAGE_LENGTH = 500
    MAX_ANSWER_LENGTH = 4000
    ADMIN_TOKEN = os.environ.get("HAMYAR_ADMIN_TOKEN") or None
    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 200

    # Keep Persian text readable inside JSON responses.
    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False

    @classmethod
    def as_dict(cls) -> dict:
        """Return the non-secret configuration, used by /health."""
        return {
            "env": cls.ENV_NAME,
            "high_confidence": cls.HIGH_CONFIDENCE,
            "medium_confidence": cls.MEDIUM_CONFIDENCE,
            "evidence_floor": cls.EVIDENCE_FLOOR,
            "char_support": cls.CHAR_SUPPORT_FLOOR,
            "admin_protected": bool(cls.ADMIN_TOKEN),
        }


class DevelopmentConfig(Config):
    ENV_NAME = "development"
    DEBUG = True


class ProductionConfig(Config):
    ENV_NAME = "production"
    DEBUG = False


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    DEBUG = False
    SECRET_KEY = "hamyar-testing-key"
    ADMIN_TOKEN = None
    DB_PATH = DATA_DIR / "hamyar-test.db"


_CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a configuration class from an explicit name or the environment."""
    key = (name or os.environ.get("HAMYAR_ENV") or "development").strip().lower()
    return _CONFIGS.get(key, DevelopmentConfig)


def project_path(*parts: str) -> Path:
    """Build a path relative to the project root."""
    return PROJECT_ROOT.joinpath(*parts)
