# -*- coding: utf-8 -*-
"""صفحهٔ برآورد قیمت — مشخصات را بگیر، ارزش برآوردی و دلیلش را بده."""
from __future__ import annotations

import streamlit as st

from .. import components as ui
from .. import runtime
from ..config import (AGE_RANGE, AREA_RANGE, BEDROOM_RANGE, FLOOR_RANGE,
                      DISTRICT_CODES, to_persian_digits)
from ..labels import district_name, fa_number, floor_label
from ..state import default_features, estimate_features, set_estimate_features

PRESETS: dict[str, dict] = {
    "آپارتمان میان‌شهر": {"district": 8, "area": 85, "bedrooms": 2, "age": 12,
                          "floor": 2, "parking": 1, "storage": 1, "elevator": 1},
    "واحد نوساز شمال شهر": {"district": 1, "area": 165, "bedrooms": 3, "age": 1,
                            "floor": 6, "parking": 1, "storage": 1, "elevator": 1},
    "خانهٔ ویلایی حاشیه": {"district": 22, "area": 240, "bedrooms": 4, "age": 8,
                           "floor": 0, "parking": 1, "storage": 1, "elevator": 0},
}


def _controls() -> dict:
    current = estimate_features()
    first = st.columns(2)
    with first[0]:
        district = st.selectbox(
            "منطقه", options=list(DISTRICT_CODES),
            index=list(DISTRICT_CODES).index(current["district"])
            if current["district"] in DISTRICT_CODES else 0,
            format_func=lambda code: district_name(code))
    with first[1]:
        area = st.slider("متراژ (مترمربع)", min_value=AREA_RANGE[0],
                         max_value=AREA_RANGE[1], value=int(current["area"]),
                         step=5)

    second = st.columns(3)
    with second[0]:
        bedrooms = st.selectbox(
            "تعداد اتاق خواب",
            options=list(range(BEDROOM_RANGE[0], BEDROOM_RANGE[1] + 1)),
            index=list(range(BEDROOM_RANGE[0], BEDROOM_RANGE[1] + 1)).index(
                int(current["bedrooms"])),
            format_func=lambda value: f"{to_persian_digits(value)} اتاق"
            if value else "بدون اتاق")
    with second[1]:
        age = st.slider("سن بنا (سال)", min_value=AGE_RANGE[0],
                        max_value=AGE_RANGE[1], value=int(current["age"]), step=1)
    with second[2]:
        floors = list(range(FLOOR_RANGE[0], FLOOR_RANGE[1] + 1))
        floor = st.selectbox("طبقه", options=floors,
                             index=floors.index(int(current["floor"])),
                             format_func=floor_label)

    third = st.columns(3)
    with third[0]:
        parking = st.checkbox("پارکینگ", value=bool(current["parking"]))
    with third[1]:
        storage = st.checkbox("انباری", value=bool(current["storage"]))
    with third[2]:
        elevator = st.checkbox("آسانسور", value=bool(current["elevator"]))

    features = {
        "district": district, "area": area, "bedrooms": bedrooms, "age": age,
        "floor": floor, "parking": int(parking), "storage": int(storage),
        "elevator": int(elevator),
    }
    if features != current:
        set_estimate_features(features)
    return features


def render() -> None:
    ui.eyebrow("برآورد ارزش")
    ui.mark("<h1>ارزش ملک را با مدل بسنجید</h1>")
    ui.lead("مشخصات را وارد کنید؛ نتیجه بی‌درنگ به‌روز می‌شود. کنار هر عدد، سهم "
            "ویژگی‌ها در آن عدد و بازهٔ اطمینان مدل نمایش داده می‌شود.")

    presets = st.columns([1, 1, 1, 2.2])
    for column, (name, preset) in zip(presets, PRESETS.items()):
        with column:
            if st.button(name, type="secondary", use_container_width=True):
                set_estimate_features(dict(preset))
                st.rerun()
    with presets[-1]:
        st.markdown(
            '<div class="kh-muted" style="padding-top:.55rem">نمونه‌های آماده — '
            "برای دیدن تفاوت مناطق و متراژها</div>", unsafe_allow_html=True)

    ui.rule()
    left, right = st.columns([1, 1.5])
    with left:
        ui.section("مشخصات ملک", eyebrow_text="ورودی")
        features = _controls()
        if st.button("بازنشانی به مقادیر پیش‌فرض", type="secondary"):
            set_estimate_features(default_features())
            st.rerun()

    explanation, summary = runtime.explanation(
        features["district"], features["area"], features["bedrooms"],
        features["age"], features["floor"], features["parking"],
        features["storage"], features["elevator"])

    with right:
        ui.section("نتیجه", eyebrow_text="خروجی مدل")
        ui.price_hero(explanation)
        st.markdown('<div style="height:.8rem"></div>', unsafe_allow_html=True)
        ui.mark(f'<p class="kh-lead">{summary}</p>')

    ui.rule()
    ui.section("سهم هر ویژگی در قیمت", "پایهٔ شهر + سهم‌ها = ارزش برآوردی",
               eyebrow_text="توضیح‌پذیری")
    bar_column, table_column = st.columns([1.2, 1])
    with bar_column:
        ui.factor_bars(explanation, limit=8)
    with table_column:
        ui.kpi_row([
            ("ارزش پایهٔ شهر", f"{fa_number(explanation.base_price / 1e9, decimals=2)} میلیارد",
             "ملکی با میانهٔ مشخصات شهر"),
            ("ارزش این ملک", f"{fa_number(explanation.price / 1e9, decimals=2)} میلیارد",
             "با مشخصات وارد‌شده"),
            ("اختلاف پایه تا این ملک",
             f"{fa_number((explanation.price - explanation.base_price) / 1e9, decimals=2)} میلیارد",
             "جمع سهم همهٔ ویژگی‌ها"),
        ], columns=1)
        if explanation.residual:
            ui.muted(f"اختلاف گردکردن: {fa_number(explanation.residual)} تومان")
        ui.muted("سهم‌ها از میانگین چند ترتیب مختلف محاسبه می‌شوند تا اثر ترتیب "
                 "برداشتن ویژگی‌ها خنثی شود؛ به همین دلیل جمعشان با اختلاف قیمت "
                 "دقیقاً برابر درمی‌آید.")

    ui.rule()
    ui.section("ملک‌های مشابه در کاتالوگ",
               "برای سنجیدن عدد، آن را با آگهی‌های واقعی همین کاتالوگ مقایسه کنید",
               eyebrow_text="بازبینی")
    if explanation.comparables.is_empty:
        ui.empty_state("در این منطقه آگهی مشابهی نیست")
    else:
        ui.kpi_row([
            ("تعداد مشابه", fa_number(explanation.comparables.count), "آگهی نزدیک"),
            ("میانهٔ قیمت مشابه‌ها",
             f"{fa_number(explanation.comparables.median_price / 1e9, decimals=2)} میلیارد", "تومان"),
            ("میانهٔ قیمت متر",
             f"{fa_number(explanation.comparables.median_price_per_m2 / 1e6)} میلیون", "تومان"),
            ("جایگاه این برآورد",
             "بالاتر" if (explanation.comparable_gap() or 0) > 0 else "پایین‌تر",
             "نسبت به میانهٔ مشابه‌ها"),
        ])
        ui.property_grid(list(explanation.comparables.items)[:3], columns=3,
                         key_prefix="predict_cmp_")

    ui.rule(tight=True)
    ui.muted("برای دیدن جزئیات یک ملک، روی «مشاهدهٔ ملک» بزنید. برآورد همین "
             "مشخصات روی هر آگهی هم در صفحهٔ آن ملک نمایش داده می‌شود.")
    ui.disclaimer()
