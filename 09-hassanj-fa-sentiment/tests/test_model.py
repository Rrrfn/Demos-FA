# -*- coding: utf-8 -*-
"""آزمون لایهٔ مدل: آموزش، انتخاب، ذخیره، خودترمیمی و پیش‌بینی.

آزمونِ خودترمیمی معادل «منبع داده در دسترس نیست» در این پروژه است: فایل مدل
خراب یا ساخت نسخهٔ دیگری از کتابخانه باشد. رفتار درست، سقوط نیست؛ ساختن
دوباره است.
"""
from __future__ import annotations

import json
import os

import joblib
import pytest
import sklearn

import hassanj.model as model_module
from hassanj.model import (classifier_of, classes_of, decision_matrix, load_model,
                           load_metrics, make_candidates, predict_many, predict_one,
                           top_terms, vocabulary)

CANDIDATE_NAMES = {"MultinomialNB", "LinearSVM (calibrated)", "LogisticRegression"}


# ------------------------------------------------------------------ ساخت و انتخاب
def test_all_candidates_are_evaluated(fast_env):
    results = fast_env["metrics"]["results"]
    assert set(results) == CANDIDATE_NAMES


def test_metrics_are_in_valid_range(fast_env):
    metrics = fast_env["metrics"]
    for name, values in metrics["results"].items():
        assert 0.0 <= values["f1_macro"] <= 1.0, name
        assert 0.0 <= values["accuracy"] <= 1.0, name
        assert 0.0 <= values["stress_f1_macro"] <= 1.0, name
        assert values["fit_seconds"] >= 0.0


def test_best_model_is_the_highest_f1_candidate(fast_env):
    metrics = fast_env["metrics"]
    scores = {name: values["f1_macro"] for name, values in metrics["results"].items()}
    assert metrics["best_model"] == max(scores, key=scores.get)


def test_in_domain_beats_out_of_domain(fast_env):
    """عدد خوش‌بینانه باید بالاتر باشد؛ اگر نباشد یعنی سنجش دست‌نویس معنا ندارد."""
    metrics = fast_env["metrics"]
    assert metrics["in_domain"]["f1_macro"] >= metrics["out_domain"]["f1_macro"]


def test_metrics_file_is_persisted(fast_env):
    assert os.path.exists(fast_env["metrics_path"])
    with open(fast_env["metrics_path"], encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored["best_model"] in CANDIDATE_NAMES
    assert stored["stress_n"] > 0
    assert "سینتتیک" in stored["data_note"]


def test_metrics_helper_returns_same_shape(fast_env):
    metrics = load_metrics()
    for key in ("best_model", "n_samples", "in_domain", "out_domain", "cv"):
        assert key in metrics


def test_cross_validation_reported(fast_env):
    cv = fast_env["metrics"]["cv"]
    assert 0.0 <= cv["f1_macro_mean"] <= 1.0
    assert cv["f1_macro_std"] >= 0.0


def test_candidate_factories_return_fresh_objects():
    first, second = make_candidates(), make_candidates()
    assert set(first) == set(second) == CANDIDATE_NAMES
    assert first["MultinomialNB"] is not second["MultinomialNB"]


# ---------------------------------------------------------------------- خودترمیمی
def test_bundle_records_sklearn_version(fast_env):
    bundle = joblib.load(fast_env["model_path"])
    assert isinstance(bundle, dict)
    assert bundle["sklearn_version"] == sklearn.__version__


def test_corrupt_bundle_is_rebuilt(monkeypatch, fast_env):
    """فایل مدل خراب → بازسازی، نه استثنا.

    این همان کلاس اشکالی است که در عمل هر صفحهٔ برآورد را ۵۰۰ می‌کرد.
    """
    path = fast_env["model_path"]
    backup = open(path, "rb").read()
    try:
        with open(path, "wb") as handle:
            handle.write(b"not a joblib bundle at all")
        pipeline = load_model()
        assert pipeline is not None
        assert os.path.exists(path)
    finally:
        with open(path, "wb") as handle:
            handle.write(backup)


def test_mismatched_version_bundle_is_rebuilt(monkeypatch, fast_env, pipeline):
    """نسخهٔ متفاوت کتابخانه → بازسازی، نه تلاش برای بارگذاری."""
    path = fast_env["model_path"]
    backup = open(path, "rb").read()
    try:
        joblib.dump({"pipeline": pipeline, "sklearn_version": "0.0.0-never"},
                    path)
        reloaded = load_model()
        assert reloaded is not None
        assert joblib.load(path)["sklearn_version"] == sklearn.__version__
    finally:
        with open(path, "wb") as handle:
            handle.write(backup)


def test_discard_removes_only_the_bundle(tmp_path, monkeypatch):
    target = tmp_path / "broken.joblib"
    target.write_bytes(b"x")
    monkeypatch.setattr(model_module, "model_path", lambda: str(target))
    model_module._discard_model("آزمون")
    assert not target.exists()


# ---------------------------------------------------------------------- پیش‌بینی
def test_clear_cases_get_confident_labels(pipeline):
    positive = predict_one(pipeline, "کیفیت عالی بود، ارسال سریع، کاملا راضی هستم")
    negative = predict_one(pipeline, "خراب رسید، پشیمون شدم، توصیه نمی‌کنم")
    assert positive["label"] == "pos" and positive["confidence"] > 0.7
    assert negative["label"] == "neg" and negative["confidence"] > 0.7


def test_emoji_only_text_is_read_by_its_emoji(pipeline):
    """«❤️💯» باید مثبت خوانده شود، نه بی‌سیگنال.

    پیش از اصلاح تزریق ایموجی، همین متن به «منفی» می‌افتاد چون ایموجی در هر
    سه کلاس حاضر بود و سیگنالی نداشت.
    """
    result = predict_one(pipeline, "❤️💯")
    assert result["label"] == "pos"
    assert result["confidence"] > 0.7


def test_probabilities_sum_to_one(pipeline):
    for text in ("معمولی بود", "عالی", "بد", "بسته رسید"):
        result = predict_one(pipeline, text)
        assert abs(sum(result["proba"].values()) - 1.0) < 0.02


def test_probabilities_sorted_descending(pipeline):
    result = predict_one(pipeline, "خیلی خوب بود ولی گرون")
    values = list(result["proba"].values())
    assert values == sorted(values, reverse=True)
    assert result["label"] == next(iter(result["proba"]))


def test_predict_many_matches_predict_one(pipeline):
    texts = ["عالی بود", "افتضاح بود", "بسته رسید"]
    batch = predict_many(pipeline, texts)
    assert len(batch) == 3
    for text, row in zip(texts, batch):
        single = predict_one(pipeline, text)
        assert row["label"] == single["label"]
        assert abs(row["confidence"] - single["confidence"]) < 1e-6


def test_predict_many_handles_empty_list(pipeline):
    assert predict_many(pipeline, []) == []


def test_classes_and_classifier_are_exposed(pipeline):
    assert set(classes_of(pipeline)) == {"pos", "neu", "neg"}
    assert classifier_of(pipeline) is not None
    assert decision_matrix(pipeline).shape[0] >= 1


# ---------------------------------------------------------------------- واژگان
def test_top_terms_are_discriminative(pipeline):
    positive = {term for term, _ in top_terms(pipeline, "pos", 8)}
    negative = {term for term, _ in top_terms(pipeline, "neg", 8)}
    assert positive and negative
    assert not positive & negative


def test_vocabulary_is_a_non_empty_set_of_strings(pipeline):
    terms = vocabulary(pipeline)
    assert terms and all(isinstance(term, str) for term in terms)
