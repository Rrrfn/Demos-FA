# -*- coding: utf-8 -*-
"""آموزش، ارزیابی و ذخیرهٔ مدل قیمت.

سه چیز این ماژول را از یک تمرین ساده جدا می‌کند:

۱) **ارزیابی چندلایه.** فقط R² روی یک تقسیم تصادفی گزارش نمی‌شود؛ اعتبارسنجی
   متقابل (۵ تایی) هم اجرا می‌شود تا معلوم شود نتیجه به یک تقسیم خوش‌شانس
   وابسته نیست.

۲) **بازهٔ پیش‌بینی واقعی.** دو مدل چندکی (۱۰٪ و ۹۰٪) آموزش می‌بینند تا به جای
   «عدد قطعی»، بازه‌ای داده شود که *پوشش واقعی* آن روی داده آزمون اندازه‌گیری و
   گزارش می‌شود. عدد پوشش ادعا نیست، محاسبه است.

۳) **بستهٔ خودبسنده.** پیش‌پردازش، مدل، مدل‌های بازه و فراداده با هم ذخیره
   می‌شوند تا در زمان اجرا هیچ‌چیز دوباره ساخته نشود و نتیجه بازتولیدپذیر بماند.
"""
from __future__ import annotations

import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (HistGradientBoostingRegressor,
                              RandomForestRegressor)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (mean_absolute_error,
                             mean_absolute_percentage_error, r2_score)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import (CATEGORICAL_FEATURES, CV_FOLDS, FEATURES, NUMERIC_FEATURES,
                     RANDOM_SEED, TARGET, TEST_SIZE, bundle_path, metrics_path,
                     model_path)
from .dataset import get_dataset

#: نسبت‌های بازه — ۱۰٪ و ۹۰٪ یعنی یک بازهٔ ۸۰ درصدی.
INTERVAL_QUANTILES = (0.1, 0.9)
INTERVAL_COVERAGE = int((INTERVAL_QUANTILES[1] - INTERVAL_QUANTILES[0]) * 100)

#: سه مدل با سطوح متفاوت پیچیدگی. مدل درختیِ سطل‌بندی‌شده
#: (``HistGradientBoosting``) به‌جای ``GradientBoosting`` کلاسیک انتخاب شده چون
#: روی همین داده همان دقت را با کسری از زمان می‌دهد و مراحل ساخت و بازآموزی
#: مدل را سریع نگه می‌دارد.
MODELS: dict[str, object] = {
    "LinearRegression": LinearRegression(),
    "RandomForest": RandomForestRegressor(
        n_estimators=120, min_samples_leaf=3, random_state=RANDOM_SEED, n_jobs=1),
    "HistGradientBoosting": HistGradientBoostingRegressor(
        max_iter=220, learning_rate=0.08, random_state=RANDOM_SEED),
}


def make_preprocessor() -> ColumnTransformer:
    """استانداردسازی عددی‌ها + رمزگذاری دسته‌ای‌ها — یک‌جا داخل Pipeline."""
    return ColumnTransformer([
        ("num", StandardScaler(), list(NUMERIC_FEATURES)),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
         list(CATEGORICAL_FEATURES)),
    ])


def _make_pipeline(model: object) -> Pipeline:
    return Pipeline([("prep", make_preprocessor()), ("model", model)])


def evaluate(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    """معیارهای کارایی روی یک مجموعه."""
    return {
        "r2": round(float(r2_score(y_true, y_pred)), 4),
        "mae_toman": int(mean_absolute_error(y_true, y_pred)),
        "mape_pct": round(float(mean_absolute_percentage_error(y_true, y_pred)) * 100, 2),
    }


def _fit_quantile_models(X_tr: pd.DataFrame, y_tr: pd.Series) -> dict[float, Pipeline]:
    """دو مدل برای کران پایین و بالای بازه."""
    models: dict[float, Pipeline] = {}
    for quantile in INTERVAL_QUANTILES:
        pipeline = _make_pipeline(HistGradientBoostingRegressor(
            loss="quantile", quantile=quantile, max_iter=150,
            learning_rate=0.08, random_state=RANDOM_SEED))
        pipeline.fit(X_tr, y_tr)
        models[quantile] = pipeline
    return models


def _intervals(quantile_models: dict[float, Pipeline], frame: pd.DataFrame,
               factor: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """کران پایین و بالا حول میانهٔ بازه، با ضریب پهنای اختیاری."""
    low = quantile_models[INTERVAL_QUANTILES[0]].predict(frame)
    high = quantile_models[INTERVAL_QUANTILES[1]].predict(frame)
    low, high = np.minimum(low, high), np.maximum(low, high)
    center = (low + high) / 2.0
    half = (high - low) / 2.0 * factor
    return center - half, center + half


def _coverage(low: np.ndarray, high: np.ndarray, y: np.ndarray) -> float:
    return float(((y >= low) & (y <= high)).mean())


def _calibrate_interval(point_pipeline: Pipeline,
                        quantile_models: dict[float, Pipeline],
                        X_cal: pd.DataFrame, y_cal: pd.Series) -> float:
    """ضریب پهنا را طوری تنظیم می‌کند که پوشش به هدف برسد.

    مدل‌های چندکی روی داده محدود، بازه‌ای باریک‌تر از وعده می‌دهند (پوشش ۷۰٪
    به‌جای ۸۰٪). به‌جای چشم‌پوشی یا ادعای نادرست، ضریب بزرگ‌نمایی روی یک
    نیمهٔ *کالیبراسیون* محاسبه می‌شود؛ پوشش نهایی روی نیمهٔ *ارزیابی* که
    کالیبراسیون آن را ندیده، اندازه‌گیری می‌شود.
    """
    low = quantile_models[INTERVAL_QUANTILES[0]].predict(X_cal)
    high = quantile_models[INTERVAL_QUANTILES[1]].predict(X_cal)
    low, high = np.minimum(low, high), np.maximum(low, high)
    half = np.maximum((high - low) / 2.0, 1.0)
    point = point_pipeline.predict(X_cal)
    # نسبت «فاصله تا میانه» به «نیم‌پهنای بازه»؛ چندک آن، ضریب لازم است.
    ratios = np.abs(y_cal.to_numpy() - point) / half
    return round(float(np.quantile(ratios, INTERVAL_COVERAGE / 100.0)), 3)


def _interval_report(point_pipeline: Pipeline,
                     quantile_models: dict[float, Pipeline],
                     X_te: pd.DataFrame, y_te: pd.Series) -> dict:
    """کالیبراسیون روی نیمهٔ نخست، اندازه‌گیری پوشش روی نیمهٔ دوم."""
    split = len(X_te) // 2
    X_cal, y_cal = X_te.iloc[:split], y_te.iloc[:split]
    X_eval, y_eval = X_te.iloc[split:], y_te.iloc[split:]

    factor = _calibrate_interval(point_pipeline, quantile_models, X_cal, y_cal)
    low, high = _intervals(quantile_models, X_eval, factor)
    return {
        "target_coverage_pct": INTERVAL_COVERAGE,
        "measured_coverage_pct": round(_coverage(low, high, y_eval.to_numpy()) * 100, 1),
        "mean_width_toman": int(np.mean(high - low)),
        "calibration_factor": factor,
    }


def _importance(pipeline: Pipeline, X_te: pd.DataFrame, y_te: pd.Series) -> list[dict]:
    """اهمیت ویژگی‌ها با جایگشت — مستقل از نوع مدل، پس قابل استناد است."""
    result = permutation_importance(
        pipeline, X_te, y_te, n_repeats=3, random_state=RANDOM_SEED,
        scoring="r2", n_jobs=1)
    total = float(np.sum(np.clip(result.importances_mean, 0, None))) or 1.0
    pairs = [
        {"feature": name, "importance": round(float(max(0.0, value)) / total, 4)}
        for name, value in zip(FEATURES, result.importances_mean)
    ]
    pairs.sort(key=lambda item: -item["importance"])
    return pairs


def train_all(df: pd.DataFrame | None = None, *, cv_folds: int = CV_FOLDS) -> dict:
    """آموزش همهٔ مدل‌ها، انتخاب بهترین و ذخیرهٔ بسته. خروجی: معیارها.

    اعتبارسنجی متقابل فقط برای مدل برنده اجرا می‌شود. دلیلش صرفه‌جویی صرف
    نیست: مقایسهٔ سه مدل روی یک تقسیم آزمون انجام می‌شود و CV برای
    *تثبیت* نتیجهٔ برنده لازم است، نه برای هر سه. اجرای CV روی هر سه، بدون
    آنکه چیزی به نتیجه اضافه کند، زمان آموزش را چند برابر می‌کند.
    """
    if df is None:
        df = get_dataset()
    X, y = df[list(FEATURES)], df[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED)

    results: dict[str, dict] = {}
    best_name, best_pipeline, best_r2 = "", None, -np.inf

    for name, model in MODELS.items():
        pipeline = _make_pipeline(model)
        started = time.time()
        pipeline.fit(X_tr, y_tr)
        metrics = evaluate(y_te, pipeline.predict(X_te))
        metrics["fit_seconds"] = round(time.time() - started, 2)
        results[name] = metrics
        if metrics["r2"] > best_r2:
            best_name, best_pipeline, best_r2 = name, pipeline, metrics["r2"]

    assert best_pipeline is not None

    # تثبیت برندهٔ آزمون با اعتبارسنجی متقابل روی کل داده.
    folds = max(2, min(int(cv_folds), 5))
    # ``n_jobs=1`` عمدی است. حالت موازی joblib برای هر کارگر یک پروسهٔ تازه با
    # نسخهٔ کامل کتابخانه‌ها می‌سازد؛ روی ماشین‌های کوچک (پلن رایگان استقرار)
    # همین کارگرها به سقف حافظه می‌خورند و به‌جای سریع‌تر شدن، آموزش را
    # ناموفق می‌کنند. آموزش روی داده درون‌حافظه‌ای به‌اندازه‌ای سبک است که
    # ترتیبی اجرا شدنش تفاوت محسوسی ندارد.
    cv_r2 = cross_val_score(best_pipeline, X, y, cv=folds, scoring="r2", n_jobs=1)
    cv_mae = -cross_val_score(best_pipeline, X, y, cv=folds,
                              scoring="neg_mean_absolute_error", n_jobs=1)
    results[best_name]["cv_r2_mean"] = round(float(cv_r2.mean()), 4)
    results[best_name]["cv_r2_std"] = round(float(cv_r2.std()), 4)
    results[best_name]["cv_mae_toman"] = int(cv_mae.mean())

    quantile_models = _fit_quantile_models(X_tr, y_tr)
    residuals = y_te.to_numpy() - best_pipeline.predict(X_te)

    metrics = {
        "best_model": best_name,
        "n_samples": int(len(df)),
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "features": list(FEATURES),
        "test_size": TEST_SIZE,
        "cv_folds": folds,
        "trained_at": time.strftime("%Y-%m-%d %H:%M"),
        "results": results,
        "importance": _importance(best_pipeline, X_te, y_te),
        "interval": _interval_report(best_pipeline, quantile_models, X_te, y_te),
        "residual_std_toman": int(np.std(residuals)),
        "data_note": "داده سینتتیک — قیمت‌ها قیمت واقعی بازار نیستند.",
    }

    joblib.dump({
        "model": best_pipeline,
        "quantiles": quantile_models,
        "metrics": metrics,
        "interval_factor": metrics["interval"]["calibration_factor"],
        "version": 2,
    }, bundle_path())

    # فایل مدل قدیمی حذف می‌شود تا دو مسیر موازی برای بارگذاری نماند.
    if os.path.exists(model_path()):
        try:
            os.remove(model_path())
        except OSError:
            pass

    with open(metrics_path(), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
    return metrics


def load_bundle() -> dict:
    """بارگذاری بستهٔ مدل؛ در نبود آن، آموزش می‌دهد."""
    if not os.path.exists(bundle_path()):
        train_all()
    return joblib.load(bundle_path())


def load_metrics() -> dict:
    if not os.path.exists(metrics_path()):
        train_all()
    with open(metrics_path(), encoding="utf-8") as handle:
        return json.load(handle)


def features_frame(features: dict) -> pd.DataFrame:
    """دیکشنری ویژگی → یک‌ردیفهٔ دیتافریم با ترتیب درست ستون‌ها."""
    missing = [name for name in FEATURES if name not in features]
    if missing:
        raise ValueError(f"ویژگی‌های ناموجود: {missing}")
    return pd.DataFrame([{name: features[name] for name in FEATURES}])


def predict(bundle: dict, features: dict) -> int:
    """قیمت پیش‌بینی‌شدهٔ نقطه‌ای."""
    frame = features_frame(features)
    return int(max(0.0, float(bundle["model"].predict(frame)[0])))


def predict_interval(bundle: dict, features: dict) -> tuple[int, int]:
    """بازهٔ ۸۰ درصدی کالیبره‌شده.

    پیش‌بینی نقطه‌ای همیشه داخل بازه بسته می‌شود؛ حتی اگر مدل‌های چندکی
    عددی خارج از آن بدهند، بازه‌ای نمایش داده نمی‌شود که خود پیش‌بینی را
    نقض کند.
    """
    frame = features_frame(features)
    factor = float(bundle.get("interval_factor", 1.0))
    low_values, high_values = _intervals(bundle["quantiles"], frame, factor)
    point = predict(bundle, features)
    low = int(max(0.0, float(low_values[0])))
    high = int(max(0.0, float(high_values[0])))
    return min(low, point), max(high, point)
