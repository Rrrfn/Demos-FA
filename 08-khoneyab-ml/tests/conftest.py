# -*- coding: utf-8 -*-
"""فیکسچرهای مشترک آزمون‌ها.

آزمون‌ها نباید به فایل‌های واقعی پروژه دست بزنند: نه `data/housing.csv` را
بازنویسی کنند، نه مدل ذخیره‌شده را جایگزین کنند، نه عکس‌های آرشیو را بخوانند.
برای همین همهٔ مسیرها به یک پوشهٔ موقت هدایت می‌شوند و یک دیتاست کوچک با
seed ثابت ساخته می‌شود. مدل هم فقط **یک بار** برای کل نشست آموزش می‌بیند؛
آموزش در هر آزمون، مجموعه را بی‌دلیل کند می‌کرد.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

#: تعداد آگهی‌های کاتالوگ در آزمون — کمتر از مقدار واقعی، برای سرعت.
TEST_LISTINGS = 240
TEST_SAMPLES = 1500


@pytest.fixture(scope="session")
def env(tmp_path_factory):
    """محیط ایزوله: دیتاست، مدل و آرشیو عکس همه در پوشهٔ موقت."""
    root = tmp_path_factory.mktemp("khoneyab")
    data_dir = root / "data"
    models_dir = root / "models"
    photos_dir = root / "photos"
    for folder in (data_dir, models_dir, photos_dir):
        folder.mkdir()

    import khoneyab.config as cfg
    import khoneyab.dataset as ds
    import khoneyab.explain as ex
    import khoneyab.listings as ls
    import khoneyab.photos as ph
    import khoneyab.train as tr

    # مسیرها را از نو به پوشهٔ موقت می‌بندیم.
    cfg.dataset_path = lambda: str(data_dir / "housing.csv")
    cfg.bundle_path = lambda: str(models_dir / "model_bundle.joblib")
    cfg.metrics_path = lambda: str(models_dir / "metrics.json")
    cfg.model_path = lambda: str(models_dir / "best_model.joblib")

    ds.dataset_path = cfg.dataset_path
    tr.bundle_path = cfg.bundle_path
    tr.metrics_path = cfg.metrics_path
    tr.model_path = cfg.model_path

    ph.PHOTO_DIR = str(photos_dir)
    ph.MANIFEST_PATH = str(photos_dir / "manifest.json")

    frame = ds.generate(n=TEST_SAMPLES, seed=11)
    frame.to_csv(cfg.dataset_path(), index=False)
    metrics = tr.train_all(frame)

    # کاتالوگ آگهی‌ها کش‌شده است؛ پس از تغییر مسیر و اندازه باید از نو ساخته شود.
    ls.N_LISTINGS = TEST_LISTINGS
    ls.clear_cache()
    ex.reference_property.cache_clear()
    ex.attribution_orders.cache_clear()
    listings = ls.all_listings()

    yield {
        "root": root, "cfg": cfg, "dataset": ds, "train": tr, "photos": ph,
        "listings": ls, "explain": ex,
        "frame": frame, "metrics": metrics, "all": listings,
        "photo_dir": photos_dir,
        "bundle_path": cfg.bundle_path(), "metrics_path": cfg.metrics_path(),
    }

    ls.clear_cache()


@pytest.fixture(scope="session")
def bundle(env):
    """بستهٔ مدل آموزش‌دیده — یک بار بارگذاری می‌شود."""
    return env["train"].load_bundle()


@pytest.fixture(scope="session")
def sample_features(env):
    """مشخصات یک ملک نمونه برای آزمون پیش‌بینی."""
    return {"district": 2, "area": 120, "bedrooms": 3, "age": 4,
            "floor": 3, "parking": 1, "storage": 1, "elevator": 1}
