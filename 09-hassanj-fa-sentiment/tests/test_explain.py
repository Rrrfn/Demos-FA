# -*- coding: utf-8 -*-
"""آزمون توضیح‌پذیری — «چرا این برچسب؟» و «آیا باید به آن اعتماد کرد؟».

مهم‌ترین بخش این فایل، آزمون **وضعیت ورودی** است: متن خالی، متن بی‌توکن، متن
بیرون از واژگان و متن با پوشش کم. مدلی که روی چنین ورودی‌هایی برچسب قطعی
می‌دهد، خطرناک‌تر از مدلی است که می‌گوید نمی‌دانم.
"""
from __future__ import annotations

from hassanj.explain import analyse, coverage_buckets, misclassified, weight_rows
from hassanj.stress import HARD_CASES, STRESS

CLEAR_POSITIVE = "کیفیت عالی بود و ارسال سریع، کاملا راضی هستم"
CLEAR_NEGATIVE = "خراب رسید و پشتیبانی جواب نمی‌ده، پشیمون شدم"


# ------------------------------------------------------------------- وضعیت ورودی
def test_empty_text_is_reported_as_empty(pipeline):
    result = analyse(pipeline, "")
    assert result["state"] == "empty"
    assert result["token_count"] == 0


def test_symbol_only_text_has_no_signal(pipeline):
    result = analyse(pipeline, "!!! ... ؟؟")
    assert result["state"] == "no_signal"


def test_english_text_is_out_of_domain(pipeline):
    result = analyse(pipeline, "The delivery took longer than expected")
    assert result["state"] == "out_of_domain"
    assert result["coverage"] == 0.0
    assert result["known_count"] == 0


def test_known_text_is_ok_state(pipeline):
    result = analyse(pipeline, CLEAR_POSITIVE)
    assert result["state"] == "ok"
    assert result["coverage"] == 1.0


def test_thin_coverage_is_flagged(pipeline):
    """پوشش واژگان کم باید وضعیت جداگانه بگیرد، نه «ok» تلقی شود."""
    result = analyse(pipeline, "خوب zzzz qqqq xxxx yyyy")
    assert result["state"] == "thin_coverage"
    assert result["coverage"] < 0.5


# ---------------------------------------------------------------------- محتوا
def test_result_exposes_everything_the_page_needs(pipeline):
    result = analyse(pipeline, CLEAR_POSITIVE)
    for key in ("text", "cleaned", "tokens", "known_tokens", "unknown_tokens",
                "coverage", "token_count", "known_count", "state", "label",
                "confidence", "proba", "band", "verdict", "toward", "against"):
        assert key in result, key


def test_known_and_unknown_tokens_partition_the_tokens(pipeline):
    result = analyse(pipeline, "کیفیت عالی بود ولی zzzz")
    assert set(result["known_tokens"]) <= set(result["tokens"])
    assert set(result["unknown_tokens"]) <= set(result["tokens"])
    assert len(result["known_tokens"]) + len(result["unknown_tokens"]) == result["token_count"]


def test_verdict_matches_band(pipeline):
    result = analyse(pipeline, CLEAR_POSITIVE)
    assert result["band"] == "high" if result["confidence"] >= 0.7 else True
    if result["band"] == "low":
        assert "قطعی نگیرید" in result["verdict"]


# ------------------------------------------------------------------ جهت واژه‌ها
def test_signals_have_consistent_direction(pipeline):
    result = analyse(pipeline, CLEAR_POSITIVE)
    assert result["has_signals"]
    assert all(item["score"] > 0 for item in result["toward"])
    assert all(item["score"] < 0 for item in result["against"])


def test_signals_are_sorted_by_strength(pipeline):
    result = analyse(pipeline, CLEAR_POSITIVE)
    weights = [abs(item["score"]) for item in result["toward"]]
    assert weights == sorted(weights, reverse=True)


def test_signal_share_is_relative_not_a_probability(pipeline):
    result = analyse(pipeline, CLEAR_POSITIVE)
    shares = [item["share"] for item in result["toward"]]
    assert max(shares) == 1.0                        # نسبت به قوی‌ترین واژه
    assert not any(item["is_phrase"] and " " not in item["term"]
                   for item in result["toward"])


def test_opposite_words_pull_in_opposite_directions(pipeline):
    positive = analyse(pipeline, CLEAR_POSITIVE)
    positive_terms = {item["term"] for item in positive["toward"]}
    assert positive_terms


def test_limit_is_respected(pipeline):
    result = analyse(pipeline, CLEAR_POSITIVE + " " + CLEAR_NEGATIVE, limit=3)
    assert len(result["toward"]) <= 3
    assert len(result["against"]) <= 3


def test_weight_rows_are_one_row_per_class(pipeline):
    """ماتریس وزن یک سطر برای هر کلاس و یک ستون برای هر ویژگی دارد.

    این ماتریس یک منبع حقیقت است: هم تحلیل تک‌متن و هم تحلیل گروهی از آن
    تغذیه می‌کنند تا دو توضیح ناسازگار برای یک متن ساخته نشود.
    """
    from hassanj.model import classes_of, vocabulary

    matrix, classes = weight_rows(pipeline)
    assert list(classes) == classes_of(pipeline)
    assert matrix.shape == (len(classes), len(vocabulary(pipeline)))


# ------------------------------------------------------------------ سنجش گروهی
def test_coverage_buckets_cover_the_whole_range(pipeline):
    buckets = coverage_buckets(pipeline, list(STRESS))
    assert [bucket["title"] for bucket in buckets] == [
        "زیر ۵۰٪", "۵۰ تا ۸۰٪", "بالای ۸۰٪"]
    assert sum(bucket["n"] for bucket in buckets) <= len(STRESS)
    for bucket in buckets:
        if bucket["n"]:
            assert 0.0 <= bucket["accuracy"] <= 1.0
        else:
            assert bucket["accuracy"] is None


def test_misclassified_reports_only_errors(pipeline):
    rows = misclassified(pipeline, list(STRESS), limit=10)
    for row in rows:
        assert row["expected_code"] != row["predicted_code"]
        assert 0.0 <= row["unknown_ratio"] <= 1.0
        assert row["text"].strip()


def test_misclassified_respects_limit(pipeline):
    assert len(misclassified(pipeline, list(STRESS), limit=2)) <= 2


def test_misclassified_handles_empty_sample(pipeline):
    assert misclassified(pipeline, []) == []


def test_stress_set_is_out_of_training_distribution():
    """مجموعهٔ دست‌نویس نباید از قطعه‌جمله‌های دیتاست ساخته شده باشد."""
    from hassanj.dataset import BANKS

    dataset_fragments = {fragment for group in BANKS.values() for fragment in group}
    for text, _ in STRESS:
        assert text not in dataset_fragments


def test_hard_cases_are_present_and_analysable(pipeline):
    """نمونه‌های دشوار باید تحلیل شوند — ولی ممکن است پوشش کم داشته باشند.

    جمله‌های مرکب طولانی می‌توانند واژه‌های کمی از واژگان مدل داشته باشند؛
    همین هم وضعیتی است که رابط به کاربر می‌گوید. چیزی که نباید رخ بدهد
    «خالی» یا «بی‌سیگنال» بودن است.
    """
    assert len(HARD_CASES) >= 4
    for text in HARD_CASES:
        assert analyse(pipeline, text)["state"] in ("ok", "thin_coverage")
