# -*- coding: utf-8 -*-
"""صفحهٔ مقایسه — چند ملک کنار هم، با ستون ارزش برآوردی."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from .. import components as ui
from .. import runtime
from ..labels import fa_number, fa_percent, fa_price_short
from ..state import (MAX_COMPARE, clear_compare, compare_ids, set_compare,
                     toggle_compare)
from ..theme import CHART_COLORS, PALETTE


def _row(label: str, values: list[str]) -> dict:
    return {"ویژگی": label, **{header: value for header, value in values}}


def render() -> None:
    ui.eyebrow("مقایسهٔ ملک")
    ui.mark("<h1>چند ملک را کنار هم بگذارید</h1>")
    ui.lead(f"حداکثر {fa_number(MAX_COMPARE)} ملک. مقایسه سه چیز را روشن می‌کند: قیمت "
            "خواسته‌شده، ارزش برآوردی مدل، و امکاناتی که تفاوت را می‌سازند.")

    # نشانی اشتراکی: ?ids=KH-1001,KH-1002 — مقایسه را می‌توان برای همکار فرستاد.
    shared = st.query_params.get("ids")
    if shared:
        requested = [part.strip() for part in str(shared).split(",") if part.strip()]
        valid = [item for item in requested if runtime.listing(item) is not None]
        if valid:
            set_compare(valid)

    ids = compare_ids()
    if not ids:
        ui.rule()
        ui.empty_state("هنوز ملکی به فهرست مقایسه اضافه نشده",
                       "از صفحهٔ جست‌وجو یا صفحهٔ ملک، دکمهٔ «افزودن به مقایسه» را بزنید.")
        from ..nav import SEARCH_PAGE
        st.page_link(SEARCH_PAGE, label="رفتن به جست‌وجو")
        return

    items = [item for item in (runtime.listing(identifier) for identifier in ids)
             if item is not None]
    if not items:
        ui.empty_state("ملک‌های انتخابی دیگر در کاتالوگ نیستند")
        clear_compare()
        return

    ui.rule()
    headers = [item.id for item in items]
    explanations = {}
    for item in items:
        explanations[item.id] = runtime.explanation(
            item.district, item.area, item.bedrooms, item.age, item.floor,
            item.parking, item.storage, item.elevator)[0]

    def values(getter) -> list[tuple[str, str]]:
        return [(item.id, getter(item)) for item in items]

    table = pd.DataFrame([
        _row("عنوان", values(lambda i: i.title)),
        _row("منطقه", values(lambda i: i.district_label)),
        _row("قیمت آگهی", values(lambda i: fa_number(i.price))),
        _row("ارزش برآوردی", values(
            lambda i: fa_number(explanations[i.id].price))),
        _row("اختلاف با برآورد", values(
            lambda i: fa_percent((i.price - explanations[i.id].price) / explanations[i.id].price,
                                 signed=True)
            if explanations[i.id].price else "—")),
        _row("قیمت هر متر", values(lambda i: fa_number(i.price_per_m2))),
        _row("متراژ", values(lambda i: f"{fa_number(i.area)} متر")),
        _row("اتاق خواب", values(lambda i: i.bedrooms_label)),
        _row("سن بنا", values(lambda i: f"{fa_number(i.age)} سال")),
        _row("طبقه", values(lambda i: i.floor_label)),
        _row("پارکینگ", values(lambda i: "دارد" if i.parking else "ندارد")),
        _row("انباری", values(lambda i: "دارد" if i.storage else "ندارد")),
        _row("آسانسور", values(lambda i: "دارد" if i.elevator else "ندارد")),
    ]).set_index("ویژگی")

    ui.fa_table(table, use_container_width=True)

    ui.rule()
    left, right = st.columns(2)
    with left:
        ui.section("قیمت هر مترمربع", eyebrow_text="نمودار")
        frame = pd.DataFrame([{
            "شناسه": item.id,
            "میلیون": item.price_per_m2 / 1e6,
        } for item in items])
        chart = (alt.Chart(frame).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                 .encode(x=alt.X("شناسه:N", title="", axis=alt.Axis(labelAngle=0)),
                         y=alt.Y("میلیون:Q", title="میلیون تومان"),
                         color=alt.value(CHART_COLORS["bronze"]),
                         tooltip=[alt.Tooltip("شناسه:N"), alt.Tooltip("میلیون:Q", format=".0f")])
                 .properties(height=280, background="transparent")
                 .configure_axis(labelColor=PALETTE["muted"], titleColor=PALETTE["muted"],
                                 gridColor=CHART_COLORS["grid"], domainColor=PALETTE["line"])
                 .configure_view(strokeWidth=0))
        st.altair_chart(chart, use_container_width=True)
    with right:
        ui.section("ارزش برآوردی در برابر قیمت آگهی", eyebrow_text="نمودار")
        compare_frame = pd.DataFrame([
            {"شناسه": item.id,
             "قیمت آگهی": item.price / 1e9,
             "ارزش برآوردی": explanations[item.id].price / 1e9}
            for item in items
        ]).melt("شناسه", var_name="نوع", value_name="میلیارد")
        chart = (alt.Chart(compare_frame)
                 .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                 .encode(x=alt.X("شناسه:N", title="", axis=alt.Axis(labelAngle=0)),
                         xOffset="نوع:N",
                         y=alt.Y("میلیارد:Q", title="میلیارد تومان"),
                         color=alt.Color("نوع:N", scale=alt.Scale(
                             domain=["قیمت آگهی", "ارزش برآوردی"],
                             range=[CHART_COLORS["muted"], CHART_COLORS["ink"]]),
                             legend=alt.Legend(orient="bottom", title=None)),
                         tooltip=[alt.Tooltip("شناسه:N"), alt.Tooltip("نوع:N"),
                                  alt.Tooltip("میلیارد:Q", format=".2f")])
                 .properties(height=280, background="transparent")
                 .configure_axis(labelColor=PALETTE["muted"], titleColor=PALETTE["muted"],
                                 gridColor=CHART_COLORS["grid"], domainColor=PALETTE["line"])
                 .configure_view(strokeWidth=0))
        st.altair_chart(chart, use_container_width=True)

    ui.rule()
    ui.section("اشتراک‌گذاری", "نشانی این مقایسه را برای همکار بفرستید",
               eyebrow_text="نشانی")
    share_url = "/compare?ids=" + ",".join(item.id for item in items)
    ui.mark(f'<div class="kh-note" style="direction:ltr;text-align:left">{share_url}</div>')

    ui.rule()
    ui.section("حذف از مقایسه", eyebrow_text="مدیریت فهرست")
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        with column:
            ui.muted(f"{item.id} — {item.title[:34]}")
            if st.button("حذف", key=f"remove_{item.id}", type="secondary",
                         use_container_width=True):
                toggle_compare(item.id)
                st.rerun()
    if st.button("پاک‌کردن کل فهرست", type="secondary"):
        clear_compare()
        st.rerun()

    cheapest = min(items, key=lambda item: item.price_per_m2)
    dearest = max(items, key=lambda item: item.price_per_m2)
    ui.note(
        f"ارزان‌ترین متر در این فهرست <strong>{cheapest.id}</strong> با "
        f"{fa_number(cheapest.price_per_m2 / 1e6)} میلیون و گران‌ترین "
        f"<strong>{dearest.id}</strong> با {fa_number(dearest.price_per_m2 / 1e6)} میلیون "
        f"تومان است — اختلاف {fa_percent(dearest.price_per_m2 / cheapest.price_per_m2 - 1)}. "
        f"بخشی از این اختلاف با منطقه توضیح داده می‌شود و بخشی با مشخصات خود ملک."
    )
    ui.disclaimer()
