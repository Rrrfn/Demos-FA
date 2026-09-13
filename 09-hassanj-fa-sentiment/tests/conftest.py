# -*- coding: utf-8 -*-
"""فیکسچرهای آزمون — محیط کوچک و کاملاً جدا از دادهٔ واقعی مخزن.

آزمون‌ها هرگز به ``data/comments.csv`` یا ``models/`` واقعی دست نمی‌زنند. یک
دیتاست کوچک در پوشهٔ موقت ساخته می‌شود، مدل همان‌جا آموزش می‌بیند، و مسیرها
در سه ماژولی که آن‌ها را می‌خوانند نشانه‌گذاری می‌شوند:

``hassanj.dataset`` / ``hassanj.model`` / ``hassanj.services``

این سه‌تایی مهم است: هر ماژول نام تابع مسیر را در فضای نام خودش import
می‌کند، پس نشانه‌گذاری فقط روی ``config`` کافی نیست و آزمون‌ها ناخواسته روی
مدل واقعی می‌افتند.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: حجم مجموعهٔ آزمون. عمداً کوچک است تا کل فایل آزمون در چند ثانیه بگذرد؛
#: چیزی که سنجیده می‌شود *درستی مسیر* است، نه دقت مدل.
N_PER_CLASS = 80


@pytest.fixture(scope="session")
def fast_env(tmp_path_factory):
    """دیتاست و مدل کوچک در پوشهٔ موقت — یک بار برای کل نشست آزمون."""
    root = tmp_path_factory.mktemp("hassanj")
    data_file = root / "comments.csv"
    model_file = root / "sentiment_model.joblib"
    metrics_file = root / "metrics.json"

    import hassanj.config as config
    import hassanj.dataset as dataset
    import hassanj.model as model
    import hassanj.services as services

    dataset.dataset_path = lambda: str(data_file)
    for module in (model, services):
        module.model_path = lambda: str(model_file)
        module.metrics_path = lambda: str(metrics_file)

    frame = dataset.generate(n_per_class=N_PER_CLASS, seed=7)
    frame.to_csv(data_file, index=False)
    metrics = model.train_all(frame)

    services.clear_cache()
    yield {
        "frame": frame,
        "metrics": metrics,
        "model_path": str(model_file),
        "metrics_path": str(metrics_file),
        "config": config,
    }
    services.clear_cache()


@pytest.fixture(scope="session")
def pipeline(fast_env):
    """طبقه‌بند آموزش‌دیدهٔ همان محیط کوچک."""
    from hassanj import services

    return services.model()


@pytest.fixture()
def client(fast_env):
    """کارخواه آزمون Flask — روی همان محیط کوچک."""
    from hassanj import services
    from hassanj.web import create_app

    services.clear_cache()
    app = create_app(TESTING=True, SECRET_KEY="test")
    with app.test_client() as test_client:
        yield test_client
