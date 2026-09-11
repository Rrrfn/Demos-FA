# -*- coding: utf-8 -*-
"""Shared test fixtures.

Every test runs against a throwaway SQLite file created by the same
``create_app`` factory the production code uses — no monkey-patching of module
globals, no import-order tricks.
"""
from __future__ import annotations

import pytest

from app import create_app
from app.database import FaqRepository, session


@pytest.fixture()
def app(tmp_path):
    """A fully initialised application bound to a temporary database."""
    database = tmp_path / "hamyar-test.db"
    application = create_app(
        "testing",
        overrides={
            "DB_PATH": database,
            "TESTING": True,
            "DEBUG": False,
            "ADMIN_TOKEN": None,
        },
    )
    yield application


@pytest.fixture()
def protected_app(tmp_path):
    """An application whose write endpoints require an admin token."""
    database = tmp_path / "hamyar-protected.db"
    application = create_app(
        "testing",
        overrides={
            "DB_PATH": database,
            "TESTING": True,
            "DEBUG": False,
            "ADMIN_TOKEN": "s3cret-token",
        },
    )
    yield application


@pytest.fixture()
def client(app):
    """Flask test client for the standard application."""
    return app.test_client()


@pytest.fixture()
def protected_client(protected_app):
    """Flask test client for the token-protected application."""
    return protected_app.test_client()


@pytest.fixture()
def ctx(app):
    """Push an application context so database helpers resolve correctly."""
    with app.app_context():
        yield app


@pytest.fixture()
def engine(ctx):
    """The application's chat engine, already indexed from the test database."""
    from app.services import get_engine

    return get_engine()


@pytest.fixture()
def faq_payload():
    """A valid FAQ payload builder."""
    def build(**overrides):
        payload = {
            "question": "آیا امکان تحویل در روز تعطیل وجود دارد؟",
            "answer": "بله، برای شهر تهران در تعطیلات رسمی هم پیک اختصاصی داریم.",
            "category": "سفارش و ارسال",
            "variants": ["تعطیلات هم ارسال دارید؟", "پیک روز تعطیل"],
        }
        payload.update(overrides)
        return payload

    return build


@pytest.fixture()
def faq_count(ctx):
    """Number of seeded knowledge-base entries."""
    with session() as conn:
        return FaqRepository(conn).count()
