# -*- coding: utf-8 -*-
"""آزمون دیتاست سینتتیک."""
from __future__ import annotations

import pytest

from khoneyab.config import (AGE_RANGE, AREA_RANGE, BEDROOM_RANGE, FEATURES,
                             FLOOR_RANGE, TARGET)
from khoneyab.dataset import generate


def test_columns_and_shape():
    frame = generate(n=400, seed=3)
    assert list(frame.columns) == list(FEATURES) + [TARGET]
    assert len(frame) == 400


def test_value_ranges():
    frame = generate(n=800, seed=3)
    assert frame["district"].between(1, 22).all()
    assert frame["area"].between(*AREA_RANGE).all()
    assert frame["bedrooms"].between(*BEDROOM_RANGE).all()
    assert frame["age"].between(*AGE_RANGE).all()
    assert frame["floor"].between(*FLOOR_RANGE).all()
    for column in ("parking", "storage", "elevator"):
        assert set(frame[column].unique()) <= {0, 1}
    assert (frame[TARGET] > 0).all()


def test_reproducible_with_seed():
    assert generate(n=120, seed=11).equals(generate(n=120, seed=11))


def test_different_seeds_differ():
    assert not generate(n=120, seed=1).equals(generate(n=120, seed=2))


def test_invalid_sample_count():
    with pytest.raises(ValueError):
        generate(n=0)


def test_district_premium_is_visible():
    """منطقهٔ ۱ (ضریب ۲٫۵) باید به‌طور میانگین چند برابر منطقهٔ ۱۹ (۰٫۶) باشد."""
    frame = generate(n=4000, seed=5)
    per_m2 = frame[TARGET] / frame["area"]
    assert per_m2[frame["district"] == 1].mean() > per_m2[frame["district"] == 19].mean() * 2


def test_bedrooms_are_not_a_pure_function_of_area():
    """اتاق خواب با نویز ساخته می‌شود؛ وگرنه مدل چیز تازه‌ای یاد نمی‌گیرد."""
    frame = generate(n=2000, seed=9)
    for area in (80, 120, 160):
        chunk = frame[frame["area"].between(area - 3, area + 3)]
        if len(chunk) > 20:
            assert chunk["bedrooms"].nunique() > 1


def test_amenities_follow_price():
    """داشتن پارکینگ باید میانگین قیمت متر را بالا ببرد."""
    frame = generate(n=3000, seed=6)
    per_m2 = frame[TARGET] / frame["area"]
    assert per_m2[frame["parking"] == 1].mean() > per_m2[frame["parking"] == 0].mean()


def test_age_depreciates_value():
    frame = generate(n=3000, seed=8)
    per_m2 = frame[TARGET] / frame["area"]
    assert per_m2[frame["age"] <= 3].mean() > per_m2[frame["age"] >= 30].mean()
