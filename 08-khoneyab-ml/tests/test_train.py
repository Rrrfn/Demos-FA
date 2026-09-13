# -*- coding: utf-8 -*-
"""آزمون آموزش، ارزیابی و پیش‌بینی."""
from __future__ import annotations

import json
import os

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn

from khoneyab.config import FEATURES
from khoneyab.train import (INTERVAL_COVERAGE, evaluate, features_frame,
                            load_bundle, load_metrics, predict,
                            predict_interval, train_all)


def test_three_models_are_compared(env):
    results = env["metrics"]["results"]
    assert set(results) == {"LinearRegression", "RandomForest", "HistGradientBoosting"}


def test_model_quality_is_sane(env):
    """رگرسیون خطی ساده باید ضعیف‌تر و بهترین مدل قوی باشد.

    اگر این ترتیب به هم بخورد یعنی یا داده ساختارش را از دست داده، یا
    ارزیابی اشتباه گرفته شده است.
    """
    results = env["metrics"]["results"]
    assert results["LinearRegression"]["r2"] < results["HistGradientBoosting"]["r2"]
    best = results[env["metrics"]["best_model"]]
    assert best["r2"] > 0.85
    assert best["mape_pct"] < 20


def test_cross_validation_only_reported_for_winner(env):
    metrics = env["metrics"]
    winner = metrics["results"][metrics["best_model"]]
    assert "cv_r2_mean" in winner
    assert abs(winner["cv_r2_mean"] - winner["r2"]) < 0.1
    assert winner["cv_r2_std"] < 0.05      # نتیجه به یک تقسیم خوش‌شانس وابسته نیست
    for name, row in metrics["results"].items():
        if name != metrics["best_model"]:
            assert "cv_r2_mean" not in row


def test_metrics_file_written(env):
    assert os.path.exists(env["metrics_path"])
    with open(env["metrics_path"], encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["best_model"] == env["metrics"]["best_model"]
    assert payload["n_samples"] == len(env["frame"])
    assert payload["data_note"]


def test_feature_importance_covers_every_feature(env):
    importance = env["metrics"]["importance"]
    names = [row["feature"] for row in importance]
    assert sorted(names) == sorted(FEATURES)          # هیچ ویژگی جا نمی‌ماند
    assert names == sorted(names, key=
                          lambda name: -dict((row["feature"], row["importance"])
                                             for row in importance)[name])
    assert abs(sum(row["importance"] for row in importance) - 1.0) < 0.05
    assert all(row["importance"] >= 0 for row in importance)


def test_interval_report_meets_its_own_target(env):
    """پوشش واقعی بازه باید نزدیک به هدف اعلامی باشد — نه ادعا، اندازه‌گیری."""
    interval = env["metrics"]["interval"]
    assert interval["target_coverage_pct"] == INTERVAL_COVERAGE
    measured = interval["measured_coverage_pct"]
    assert INTERVAL_COVERAGE - 15 <= measured <= 100
    assert interval["mean_width_toman"] > 0
    assert interval["calibration_factor"] > 0


def test_bundle_is_self_contained(env):
    payload = load_bundle()
    assert set(payload) >= {"model", "quantiles", "metrics", "interval_factor"}
    assert set(payload["quantiles"]) == {0.1, 0.9}
    assert payload["interval_factor"] == env["metrics"]["interval"]["calibration_factor"]


def test_load_metrics_matches_bundle(env):
    assert load_metrics()["best_model"] == env["metrics"]["best_model"]


def test_features_frame_orders_columns():
    frame = features_frame({"district": 1, "area": 90, "bedrooms": 2, "age": 5,
                            "floor": 2, "parking": 1, "storage": 0, "elevator": 1})
    assert list(frame.columns) == list(FEATURES)
    assert len(frame) == 1


def test_features_frame_rejects_missing_feature():
    with pytest.raises(ValueError):
        features_frame({"district": 1, "area": 90})


def test_prediction_is_positive_and_deterministic(bundle, sample_features):
    first = predict(bundle, sample_features)
    second = predict(bundle, sample_features)
    assert first == second
    assert first > 0


def test_expensive_district_predicts_higher(bundle, sample_features):
    cheap = dict(sample_features, district=19, age=35, parking=0, storage=0, elevator=0)
    dear = dict(sample_features, district=1, age=0, parking=1, storage=1, elevator=1)
    assert predict(bundle, dear) > predict(bundle, cheap) * 2


def test_interval_brackets_the_point_prediction(bundle, sample_features):
    point = predict(bundle, sample_features)
    low, high = predict_interval(bundle, sample_features)
    assert low <= point <= high
    assert high > low
    assert low > 0


def test_evaluate_reports_known_values():
    truth = pd.Series([100, 200, 300])
    metrics = evaluate(truth, np.array([100, 200, 300]))
    assert metrics["r2"] == 1.0
    assert metrics["mape_pct"] == 0.0
    assert metrics["mae_toman"] == 0


def test_bundle_records_the_sklearn_version(env):
    """نسخهٔ scikit-learn باید داخل بسته ثبت شود.

    ``joblib`` نام کلاس‌های scikit-learn را در فایل ذخیره می‌کند و بین دو
    نسخه حتی کلاس‌های خصوصی عوض می‌شوند. بارگذاری چنین بسته‌ای با
    ``AttributeError`` می‌شکند و هر صفحهٔ برآورد خطای ۵۰۰ می‌دهد. ثبت نسخه
    اجازه می‌دهد ناسازگاری *پیش از* تلاش برای بازکردن فایل تشخیص داده شود.
    """
    assert joblib.load(env["bundle_path"]).get("sklearn_version") == sklearn.__version__


def test_load_bundle_rebuilds_a_bundle_from_another_version(env, monkeypatch):
    """بستهٔ ساخته‌شده با نسخهٔ دیگر باید کنار گذاشته و از نو ساخته شود."""
    train = env["train"]
    path = env["bundle_path"]
    good = joblib.load(path)

    stale = dict(good)
    stale["sklearn_version"] = "0.0.1"
    joblib.dump(stale, path)

    rebuilt = []

    def fake_train_all(*args, **kwargs):
        rebuilt.append(True)
        joblib.dump(good, path)          # محیط آزمون به حالت اول برمی‌گردد
        return good["metrics"]

    monkeypatch.setattr(train, "train_all", fake_train_all)
    loaded = train.load_bundle()
    assert rebuilt, "بستهٔ ناسازگار دوباره ساخته نشد"
    assert loaded["sklearn_version"] == sklearn.__version__


def test_load_bundle_recovers_from_an_unreadable_file(env, monkeypatch):
    """فایل خراب نباید صفحهٔ برآورد را با خطای ۵۰۰ بشکند."""
    train = env["train"]
    path = env["bundle_path"]
    good = joblib.load(path)

    with open(path, "wb") as handle:
        handle.write(b"\x00\x01 not a joblib file")

    def fake_train_all(*args, **kwargs):
        joblib.dump(good, path)
        return good["metrics"]

    monkeypatch.setattr(train, "train_all", fake_train_all)
    loaded = train.load_bundle()
    assert loaded["metrics"]["best_model"] == good["metrics"]["best_model"]


def test_training_is_stable_across_runs(env):
    """آموزش دوباره روی همان داده باید همان معیارها را بدهد."""
    again = train_all(env["frame"])
    assert again["best_model"] == env["metrics"]["best_model"]
    assert again["results"][again["best_model"]]["r2"] == \
        env["metrics"]["results"][env["metrics"]["best_model"]]["r2"]
