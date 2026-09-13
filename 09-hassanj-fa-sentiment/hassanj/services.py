# -*- coding: utf-8 -*-
"""لایهٔ دسترسی به داده — همهٔ صفحه‌ها از اینجا تغذیه می‌شوند.

دو تصمیم که مستقیم روی رفتار محصول اثر دارند:

**۱) بارگذاری تنبل مدل.** ``scikit-learn`` حدود نیم‌ثانیه از زمان راه‌اندازی
را می‌خورد و فقط صفحه‌های «تحلیل متن»، «گروهی»، «تحلیل» و «مدل» به آن نیاز
دارند. صفحهٔ «نمای کلی» تنها با معیارهای ذخیره‌شده در ``metrics.json`` ساخته
می‌شود و هیچ‌وقت مدل را بیدار نمی‌کند.

**۲) حافظهٔ نتیجه.** محاسبهٔ تحلیل روی ۱۸۰۰ نمونه (ترکیب پیش‌بینی‌شده، توزیع
اطمینان، سنجش پوشش) گران است و ورودی‌اش هیچ‌وقت عوض نمی‌شود. با کش کردنش،
جابه‌جایی بین صفحه‌ها به یک نگاه‌زدن به حافظه بدل می‌شود.

هیچ‌جای دیگری نباید مستقیم سراغ مدل یا دیتاست برود؛ مرز داده همین‌جاست و
قالب‌ها فقط چیز آمادهٔ نمایش می‌گیرند.
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache

import pandas as pd

from .config import metrics_path
from .dataset import get_dataset
from .stress import STRESS

#: قفل ساخت مدل — دو درخواست هم‌زمان نباید دو بار آموزش راه بیندازند.
_MODEL_LOCK = threading.Lock()


# ------------------------------------------------------------------ پایه
@lru_cache(maxsize=1)
def dataset() -> pd.DataFrame:
    return get_dataset()


@lru_cache(maxsize=1)
def metrics() -> dict:
    path = metrics_path()
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        # معیارها هنوز ساخته نشده‌اند؛ همان لحظه ساخته می‌شوند تا صفحهٔ «مدل»
        # بی‌عدد نماند.
        from .model import train_all

        return train_all()


@lru_cache(maxsize=1)
def model():
    """طبقه‌بند آموزش‌دیده — با قفل، تا یک بار ساخته شود."""
    with _MODEL_LOCK:
        from .model import load_model

        return load_model()


@lru_cache(maxsize=1)
def stress_set() -> tuple[tuple[str, str], ...]:
    return tuple(STRESS)


def stress_texts() -> list[str]:
    return [text for text, _ in stress_set()]


@lru_cache(maxsize=1)
def dataset_texts() -> tuple[str, ...]:
    return tuple(str(text) for text in dataset()["text"])


# ------------------------------------------------------------------ تحلیل‌ها
@lru_cache(maxsize=1)
def mix() -> dict:
    """ترکیب واقعی، ترکیب پیش‌بینی‌شده، و مقایسهٔ آن دو."""
    from . import analytics

    frame = dataset()
    return {
        "actual": analytics.actual_mix(frame),
        "predicted": analytics.predicted_mix(model(), list(dataset_texts())),
        "comparison": analytics.comparison(model(), frame),
    }


@lru_cache(maxsize=1)
def monthly() -> list[dict]:
    from . import analytics

    return analytics.monthly_mix(dataset())


@lru_cache(maxsize=1)
def declared_trend() -> list[dict]:
    from . import analytics

    return analytics.declared_trend()


@lru_cache(maxsize=1)
def confidence_distribution() -> list[tuple[float, int]]:
    from . import analytics

    return analytics.confidence_histogram(model(), list(dataset_texts()))


@lru_cache(maxsize=1)
def length_distribution() -> list[tuple[float, int]]:
    from . import analytics

    return analytics.length_histogram(dataset())


@lru_cache(maxsize=1)
def class_terms() -> dict[str, list[dict]]:
    from . import analytics

    return analytics.class_terms(model())


@lru_cache(maxsize=1)
def unknown_terms() -> list[dict]:
    from . import analytics

    return analytics.unknown_terms(dataset(), model())


@lru_cache(maxsize=1)
def coverage_buckets() -> list[dict]:
    from .explain import coverage_buckets as compute

    return compute(model(), list(stress_set()))


@lru_cache(maxsize=1)
def misclassifications() -> list[dict]:
    from .explain import misclassified

    return misclassified(model(), list(stress_set()), limit=8)


@lru_cache(maxsize=1)
def hard_cases() -> list[dict]:
    """نمونه‌های دشوار با آنچه مدل روی‌شان گفته.

    این‌ها عمداً نمایش داده می‌شوند: مدلی که فقط موفقیت‌هایش را نشان می‌دهد
    ابزار تصمیم‌گیری نیست، تبلیغ است.
    """
    from .explain import analyse
    from .stress import HARD_CASES

    pipe = model()
    return [analyse(pipe, text, limit=3) for text in HARD_CASES]


@lru_cache(maxsize=1)
def summary_cards() -> list[dict]:
    from . import analytics

    return analytics.summary(dataset(), model(), metrics())


# ------------------------------------------------------------------ تحلیل تک‌متن
def analyse_text(text: str, limit: int = 6) -> dict:
    """تحلیل یک متن — نقطهٔ ورود مشترک صفحه، API و آزمون.

    متن بلندتر از سقف بریده می‌شود و *همین* به کاربر گفته می‌شود؛ بریدن بی‌اعلام
    باعث می‌شود کاربر فکر کند کل متن تحلیل شده است.
    """
    from .config import MAX_ANALYZE_CHARS
    from .explain import analyse

    raw = "" if text is None else str(text)
    truncated = len(raw) > MAX_ANALYZE_CHARS
    result = analyse(model(), raw[:MAX_ANALYZE_CHARS], limit=limit)
    result["truncated"] = truncated
    result["original_length"] = len(raw)
    return result


# ------------------------------------------------------------------ گروهی
def analyse_table(payload: bytes) -> dict:
    """بارگذاری و تحلیل یک فایل CSV — با اعتبارسنجی کامل."""
    from . import batch

    frame, warnings = batch.read_table(payload)
    text_column, date_column, guessed = batch.detect_columns(frame)
    results = batch.analyse_rows(model(), [str(value) for value in frame[text_column]])
    return {
        "results": results,
        "summary": batch.summarise(results),
        "warnings": warnings,
        "text_column": text_column,
        "date_column": date_column,
        "guessed_column": guessed,
        "rows": len(frame),
        "row_preview": [batch.persian_row(row)
                        for row in batch.preview(results, limit=50)],
    }


def clear_cache() -> None:
    """پاک‌کردن همهٔ حافظه‌های میانی — برای آزمون‌ها و بازآزمایی."""
    for name in ("dataset", "metrics", "model", "stress_set", "dataset_texts",
                 "mix", "monthly", "declared_trend", "confidence_distribution",
                 "length_distribution", "class_terms", "unknown_terms",
                 "coverage_buckets", "misclassifications", "hard_cases",
                 "summary_cards"):
        target = globals().get(name)
        cache_clear = getattr(target, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()
    dataset.cache_clear()
    metrics.cache_clear()
