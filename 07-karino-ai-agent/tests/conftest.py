# -*- coding: utf-8 -*-
"""فیکسچرهای آزمون — پایگاه دادهٔ موقت، تنظیمات تازه و بدون هیچ شبکه‌ای.

متغیرهای محیطی **پیش از** نخستین import تنظیم می‌شوند، چون ``karino.webapp``
یک ``app`` سطح ماژول می‌سازد و آن اپ در راه‌اندازی، پایگاه داده و دور نخست
را اجرا می‌کند. با خاموش‌کردن جمع‌آوری و زمان‌بند، همان مسیر راه‌اندازی
آزموده می‌شود ولی هیچ درخواست بیرونی زده نمی‌شود.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["KARINO_COLLECT_ON_BOOT"] = "0"
os.environ["ENABLE_SCHEDULER"] = "0"
os.environ["KARINO_SEED_DEMO"] = "0"
os.environ.pop("KARINO_LLM_URL", None)
os.environ.pop("KARINO_ADMIN_TOKEN", None)

# ``karino.webapp`` یک ``app`` سطح ماژول می‌سازد؛ هرچه زودتر مسیر پایگاه داده
# را به یک پوشهٔ موقت ببریم، تا آزمون هرگز به ``data/`` واقعی پروژه دست نزند.
_SESSION_TMP = tempfile.mkdtemp(prefix="karino-tests-")
os.environ["KARINO_DATA_DIR"] = _SESSION_TMP
os.environ["KARINO_DB_PATH"] = os.path.join(_SESSION_TMP, "session.db")

import pytest  # noqa: E402

from karino.config import get_settings  # noqa: E402


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    """تنظیمات تازه با پایگاه دادهٔ موقت و جمع‌آوری خاموش."""
    db_file = tmp_path / "karino-test.db"
    monkeypatch.setenv("KARINO_DB_PATH", str(db_file))
    monkeypatch.setenv("KARINO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KARINO_COLLECT_ON_BOOT", "0")
    monkeypatch.setenv("ENABLE_SCHEDULER", "0")
    return get_settings(refresh=True)


@pytest.fixture()
def db(settings):
    """پایگاه دادهٔ تازه و خالی که به فایل موقت اشاره می‌کند."""
    from karino.storage import database, reset_init_flag

    reset_init_flag()
    database.init_db(force=True)
    yield database
    reset_init_flag()


@pytest.fixture()
def client(settings, db):
    """کلاینت Flask با میان‌بر bootstrap (بدون دور جمع‌آوری)."""
    from karino.webapp import create_app

    app = create_app(bootstrap=False, settings=settings)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def transport():
    from .fakes import FakeTransport

    return FakeTransport()


@pytest.fixture()
def seeded(db):
    """چند آگهی واقعی در پایگاه داده، امتیازدهی‌شده — پایهٔ آزمون‌های API."""
    from karino.pipeline.normalize import normalize
    from karino.pipeline.scoring import score
    from karino.storage import activity
    from karino.storage import jobs as jobs_repo, scores as scores_repo

    from .fakes import raw_job

    created = []
    samples = [
        raw_job(source="alpha", index=1, title="توسعه‌دهندهٔ پایتون و Flask",
                description="پروژهٔ ساخت API با Python، Flask و SQLite. دورکاری و پروژه‌ای.",
                tags=["python", "flask", "sql"], employment="freelance", remote=True),
        raw_job(source="alpha", index=2, title="کارشناس فروش تلفنی",
                description="تماس با مشتریان و پیگیری سفارش‌ها.", tags=[],
                employment="fulltime", remote=False),
        raw_job(source="beta", index=3, title="مهندس یادگیری ماشین",
                description="مدل پیش‌بینی با scikit-learn و pandas. دورکاری.",
                tags=["python", "machine learning"], employment="freelance", remote=True),
    ]
    for raw in samples:
        job = normalize(raw)
        job_id, _ = jobs_repo.upsert(job)
        scores_repo.save(job_id, score(job))
        created.append(job_id)

    activity.log("test", "دادهٔ آزمون بارگذاری شد")
    return created
