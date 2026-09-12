# -*- coding: utf-8 -*-
"""صفحهٔ خانه — معرفی کوتاه، نبض بازار و آگهی‌های منتخب."""
from __future__ import annotations

import streamlit as st

from .. import components as ui
from .. import runtime
from ..config import to_persian_digits
from ..labels import (FEATURE_LABELS, fa_number, fa_percent, fa_price_short)
from ..photos import photo_url
from ..theme import CHART_COLORS


def render() -> None:
    hero_photo = photo_url(runtime.photos().gallery(0)[0])
    ui.mark(
        f'<div class="kh-hero">'
        + (f'<img src="{hero_photo}" alt="نمای یک ساختمان مسکونی">' if hero_photo else "")
        + '<div class="kh-hero-veil"></div>'
        '<div class="kh-hero-body">'
        '<span class="kh-eyebrow">هوش بازار مسکن تهران</span>'
        "<h1>خانه‌یاب — قیمت را قبل از تصمیم بدانید</h1>"
        "<p>جست‌وجو، مقایسه و برآورد ارزش ملک در یک جا. مدل یادگیری ماشین روی "
        "مشخصات ملک آموزش دیده و برای هر آگهی، ارزش برآوردی، بازهٔ اطمینان و "
        "دلیل عدد را نشان می‌دهد.</p>"
        "</div></div>"
    )

    ui.mark('<div style="height:1.4rem"></div>')
    overview = runtime.overview()
    stats = runtime.insights()
    ui.kpi_row([
        ("آگهی فعال", fa_number(overview["listings"]), "در کاتالوگ نمونه"),
        ("میانهٔ قیمت", f"{fa_number(overview['median_price'] / 1e9, decimals=2)} میلیارد",
         "تومان برای هر ملک"),
        ("میانهٔ قیمت متر", f"{fa_number(overview['median_price_m2'] / 1e6)} میلیون",
         "تومان در هر مترمربع"),
        ("دقت مدل (R²)", fa_number(stats["r2"], decimals=3) if stats["r2"] else "—",
         "روی داده آزمون"),
    ])

    ui.rule()
    ui.section("چطور کار می‌کند", eyebrow_text="مسیر سه‌گامی")
    steps = st.columns(3)
    titles = [
        ("۱. بگردید", "با فیلتر منطقه، متراژ، اتاق، سن بنا و امکانات، آگهی‌های "
                      "مناسب را پیدا کنید."),
        ("۲. مقایسه کنید", "چند ملک را کنار هم بگذارید و قیمت، متراژ، سن و "
                           "امکاناتشان را در یک جدول ببینید."),
        ("۳. برآورد بگیرید", "ارزش برآوردی مدل، بازهٔ ۸۰ درصدی، سهم هر ویژگی در "
                            "قیمت و ملک‌های مشابه."),
    ]
    for column, (title, text) in zip(steps, titles):
        with column:
            ui.mark(f"<h3>{title}</h3>")
            ui.muted(text)

    ui.rule()
    ui.section("آگهی‌های منتخب", "بر پایهٔ قیمت هر مترمربع در کاتالوگ",
               eyebrow_text="گزیده")
    featured = sorted(runtime.listings(), key=lambda item: -item.price_per_m2)[:3]
    ui.property_grid(featured, columns=3, tags=["گران‌ترین متر شهر"] * 3,
                     key_prefix="home_")

    ui.rule()
    ui.section("نبض بازار", "میانهٔ قیمت هر مترمربع به تفکیک منطقه",
               eyebrow_text="تحلیل")
    districts = runtime.districts()
    left, right = st.columns([1.15, 1])
    with left:
        ui.bar_chart(
            districts.head(8)[["short_name", "median_price_m2"]].assign(
                میلیون=lambda frame: frame["median_price_m2"] / 1e6),
            x="میلیون", y="short_name", x_title="میلیون تومان در مترمربع",
            horizontal=True, color=CHART_COLORS["bronze"], height=320,
            tooltip_labels={"short_name": "منطقه", "میلیون": "قیمت متر"})
    with right:
        distribution = runtime.distribution().assign(
            میلیارد=lambda frame: frame["center"])
        ui.bar_chart(distribution, x="میلیارد", y="count",
                     x_title="میلیارد تومان", y_title="تعداد آگهی",
                     color=CHART_COLORS["ink"], height=320,
                     tooltip_labels={"count": "تعداد", "میلیارد": "قیمت"})

    ui.rule()
    costliest = districts.iloc[0]
    cheapest = districts.iloc[-1]
    gap = (costliest["median_price_m2"] / cheapest["median_price_m2"] - 1) if cheapest["median_price_m2"] else 0
    ui.note(
        f"گران‌ترین منطقه در این کاتالوگ <strong>{costliest['district_name']}</strong> با میانهٔ "
        f"{fa_number(costliest['median_price_m2'] / 1e6)} میلیون تومان در مترمربع است و "
        f"ارزان‌ترین <strong>{cheapest['district_name']}</strong> با "
        f"{fa_number(cheapest['median_price_m2'] / 1e6)} میلیون — فاصلهٔ "
        f"{fa_percent(gap)}. همین پراکندگی است که برآورد بی‌توجه به منطقه را بی‌معنا می‌کند: "
        f"<strong>{FEATURE_LABELS['district']}</strong> بیشترین سهم را در تصمیم مدل دارد."
    )

    ui.mark('<div style="height:1rem"></div>')
    ui.disclaimer()
    ui.muted(
        f"این نسخهٔ نمایشی روی {to_persian_digits(overview['listings'])} آگهی نمونه "
        f"و {fa_number(runtime.metrics()['n_samples'])} رکورد آموزشی کار می‌کند."
    )
