# -*- coding: utf-8 -*-
"""آزمون توضیح پیش‌بینی: سهم عامل‌ها، بازه و ملک‌های مشابه."""
from __future__ import annotations

import re

from khoneyab.config import FEATURES
from khoneyab.explain import (explain, explain_listing, explanation_summary,
                              factor_table, find_comparables)
from khoneyab.labels import fa_number
from khoneyab.train import predict

LATIN_DIGITS = re.compile(r"[0-9]")


def test_explanation_covers_price_and_interval(bundle, sample_features):
    result = explain(bundle, sample_features)
    assert result.price == predict(bundle, sample_features)
    assert result.low <= result.price <= result.high
    assert result.interval_width > 0
    assert 0 < result.relative_width < 1
    assert result.price_per_m2 == int(result.price / sample_features["area"])


def test_attribution_sums_to_the_prediction(bundle, sample_features):
    """مجموع سهم‌ها + قیمت پایه باید قیمت نهایی را بدهد.

    این آزمون جوهر روش است: اگر باقی‌ماندهٔ توضیع‌نشده بزرگ باشد، عدد پایه
    و سهم‌ها به هم نمی‌خوانند و گزارش «چرا این عدد؟» بی‌اعتبار می‌شود.
    """
    result = explain(bundle, sample_features)
    total = result.base_price + sum(item.amount for item in result.factors)
    assert abs(total - result.price) <= max(2_000_000, result.price * 0.005)
    assert abs(result.residual) <= max(2_000_000, result.price * 0.005)


def test_every_feature_has_an_effect(bundle, sample_features):
    result = explain(bundle, sample_features)
    assert {item.feature for item in result.factors} == set(FEATURES)
    assert result.factors == tuple(sorted(result.factors, key=lambda item: -abs(item.amount)))


def test_expensive_area_raises_attribution(bundle, sample_features):
    """نقل به منطقهٔ گران‌تر باید سهم مثبت بدهد."""
    dear = dict(sample_features, district=1)
    cheap = dict(sample_features, district=19)
    dear_effects = {item.feature: item.amount for item in explain(bundle, dear).factors}
    cheap_effects = {item.feature: item.amount for item in explain(bundle, cheap).factors}
    assert dear_effects["district"] > 0
    assert dear_effects["district"] > cheap_effects["district"]


def test_missing_amenity_has_negative_effect(bundle, sample_features):
    without = dict(sample_features, parking=0, storage=0, elevator=0)
    effects = {item.feature: item.amount for item in explain(bundle, without).factors}
    assert effects["parking"] < 0 or effects["storage"] < 0 or effects["elevator"] < 0


def test_comparables_come_from_the_same_district(env, bundle, sample_features):
    comparables = find_comparables(sample_features)
    assert not comparables.is_empty
    assert comparables.count <= 6
    assert all(item.district == sample_features["district"] for item in comparables.items)
    assert all(abs(item.area - sample_features["area"]) <= sample_features["area"] * 0.20
               for item in comparables.items)
    assert comparables.median_price > 0
    assert comparables.median_price_per_m2 > 0


def test_comparable_selection_is_deterministic(env, bundle, sample_features):
    """دو فراخوانی پیاپی باید دقیقاً یک مجموعه و یک ترتیب بدهند.

    اگر ترتیب انتخاب به پیمایش دیکشنری یا ترتیب ردیف‌های تصادفی وابسته باشد،
    کاربر با هر بار بازکردن صفحه اعداد متفاوتی می‌بیند.
    """
    first = find_comparables(sample_features)
    second = find_comparables(sample_features)
    assert [item.id for item in first.items] == [item.id for item in second.items]
    assert first.count == second.count
    assert len(first.items) >= 1


def test_comparables_never_come_back_empty_for_a_real_district(bundle):
    """برای هر منطقهٔ کاتالوگ باید حداقل یک ملک مشابه پیدا شود.

    اگر دامنهٔ سن و متراژ تنگ باشد ممکن است چند ملک پیدا شود؛ ولی «خالی»
    برگرداندن یعنی صفحهٔ ملک بخش مشابه‌ها را بی‌دلیل خالی نشان می‌دهد.
    """
    for features in (
        {"district": 1, "area": 400, "bedrooms": 5, "age": 0, "floor": 15,
         "parking": 1, "storage": 1, "elevator": 1},          # گران‌ترین گوشهٔ بازار
        {"district": 19, "area": 40, "bedrooms": 0, "age": 45, "floor": -1,
         "parking": 0, "storage": 0, "elevator": 0},           # ارزان‌ترین گوشه
    ):
        comparables = find_comparables(features)
        assert not comparables.is_empty
        assert all(item.district == features["district"] for item in comparables.items)
        assert comparables.median_price > 0


def test_listing_explanation_matches_its_features(env, bundle):
    listing = env["all"][7]
    result = explain_listing(bundle, listing)
    assert result.price == predict(bundle, listing.as_features())
    assert result.price_per_m2 == int(result.price / listing.area)


def test_factor_table_is_persian_and_complete(bundle, sample_features):
    table = factor_table(explain(bundle, sample_features))
    assert list(table.columns) == ["ویژگی", "مقدار", "اثر (تومان)", "سهم"]
    assert len(table) == len(FEATURES)
    assert not table["ویژگی"].str.contains(LATIN_DIGITS).any()


def test_summary_is_readable_persian(bundle, sample_features):
    text = explanation_summary(explain(bundle, sample_features))
    assert "تومان" in text
    assert fa_number(0) in text or "٪" in text
    assert not LATIN_DIGITS.search(text)
