# -*- coding: utf-8 -*-
"""فیکسچرهای مشترک آزمون‌ها.

آزمون‌ها نباید به فایل‌های واقعی پروژه دست بزنند: نه ``data/housing.csv`` را
بازنویسی کنند، نه مدل ذخیره‌شده را جایگزین کنند، نه عکس‌های آرشیو را بخوانند.
برای همین همهٔ مسیرها به یک پوشهٔ موقت هدایت می‌شوند و یک دیتاست کوچک با
seed ثابت ساخته می‌شود.

یک نکتهٔ مهم دربارهٔ پیوند نام‌ها: ماژول‌های ``khoneyab`` مسیرها را با
``from .config import bundle_path`` می‌گیرند؛ این کار *تابع* را در زمان
import به فضای نام آن ماژول می‌چسباند. پس عوض‌کردن ``config.bundle_path``
تنها کافی نیست — همهٔ ماژول‌هایی که آن نام را import کرده‌اند هم باید
دوباره بسته شوند، وگرنه آزمون در سکوت روی دادهٔ واقعی اجرا می‌شود.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

#: تعداد آگهی‌های کاتالوگ در آزمون — کمتر از مقدار واقعی، برای سرعت.
TEST_LISTINGS = 240
TEST_SAMPLES = 1500

#: نام‌های مسیر که باید در همهٔ ماژول‌ها دوباره بسته شوند.
PATH_NAMES = ("dataset_path", "bundle_path", "metrics_path", "model_path")


def _rebind(modules, name: str, value) -> None:
    """جایگزینی یک نام در همهٔ ماژول‌هایی که آن را import کرده‌اند."""
    for module in modules:
        if hasattr(module, name):
            setattr(module, name, value)


@pytest.fixture(scope="session")
def env(tmp_path_factory):
    """محیط ایزوله: دیتاست، مدل و آرشیو عکس همه در پوشهٔ موقت."""
    root = tmp_path_factory.mktemp("khoneyab")
    data_dir = root / "data"
    models_dir = root / "models"
    photos_dir = root / "photos"
    thumbs_dir = photos_dir / "thumbs"
    for folder in (data_dir, models_dir, photos_dir, thumbs_dir):
        folder.mkdir()

    import khoneyab.config as cfg
    import khoneyab.dataset as ds
    import khoneyab.explain as ex
    import khoneyab.listings as ls
    import khoneyab.market as mk
    import khoneyab.photos as ph
    import khoneyab.search as se
    import khoneyab.services as sv
    import khoneyab.train as tr

    bound = (ds, tr, ls, ex, sv)

    cfg.dataset_path = lambda: str(data_dir / "housing.csv")
    cfg.bundle_path = lambda: str(models_dir / "model_bundle.joblib")
    cfg.metrics_path = lambda: str(models_dir / "metrics.json")
    cfg.model_path = lambda: str(models_dir / "best_model.joblib")
    for name in PATH_NAMES:
        _rebind(bound, name, getattr(cfg, name))

    ph.PHOTO_DIR = str(photos_dir)
    ph.THUMB_DIR = str(thumbs_dir)
    ph.MANIFEST_PATH = str(photos_dir / "manifest.json")
    ph.DIMENSIONS_PATH = str(thumbs_dir / "dimensions.json")
    ph._dimensions_cache = None

    def _rebind_photo(name: str, value) -> None:
        _rebind((sv, ls), name, value)

    _rebind_photo("PHOTO_DIR", ph.PHOTO_DIR)
    _rebind_photo("THUMB_DIR", ph.THUMB_DIR)

    frame = ds.generate(n=TEST_SAMPLES, seed=11)
    frame.to_csv(cfg.dataset_path(), index=False)
    metrics = tr.train_all(frame)

    ls.N_LISTINGS = TEST_LISTINGS
    _clear_caches(ls, sv, ex, mk, se, ph)
    listings = ls.all_listings()

    yield {
        "root": root, "cfg": cfg, "dataset": ds, "train": tr, "photos": ph,
        "listings": ls, "explain": ex, "services": sv,
        "frame": frame, "metrics": metrics, "all": listings,
        "photo_dir": photos_dir, "thumbs_dir": thumbs_dir,
        "bundle_path": cfg.bundle_path(), "metrics_path": cfg.metrics_path(),
    }

    _clear_caches(ls, sv, ex, mk, se, ph)


def _clear_caches(listings, services, explain, market, search, photos) -> None:
    """پاک‌کردن همهٔ حافظه‌های میانی.

    بدون این کار، نتیجهٔ یک آزمون به آزمون بعدی نشت می‌کند: کاتالوگ ساخته‌شده
    با مسیر قبلی، فهرست عکس قدیمی، و توضیح‌های محاسبه‌شده برای دادهٔ دیگر.
    """
    from khoneyab import charts  # noqa: F401  (بارگذاری برای وابستگی قالب)

    listings.clear_cache()
    for module in (services, explain, market, search):
        for name in dir(module):
            attr = getattr(module, name, None)
            cache_clear = getattr(attr, "cache_clear", None)
            if callable(cache_clear):
                try:
                    cache_clear()
                except (TypeError, ValueError):
                    pass
    photos._dimensions_cache = None


@pytest.fixture(scope="session")
def bundle(env):
    """بستهٔ مدل آموزش‌دیده — یک بار بارگذاری می‌شود."""
    return env["train"].load_bundle()


@pytest.fixture(scope="session")
def sample_features(env):
    """مشخصات یک ملک نمونه برای آزمون پیش‌بینی."""
    return {"district": 2, "area": 120, "bedrooms": 3, "age": 4,
            "floor": 3, "parking": 1, "storage": 1, "elevator": 1}


@pytest.fixture()
def app(env):
    """برنامهٔ Flask روی همان محیط ایزوله."""
    from khoneyab.web import create_app

    application = create_app(TESTING=True, SECRET_KEY="test-key")
    return application


@pytest.fixture()
def client(app):
    """کارخواه آزمون — بدون سرور واقعی، ولی از همان مسیرهای WSGI."""
    return app.test_client()
