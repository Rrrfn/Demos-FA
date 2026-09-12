# -*- coding: utf-8 -*-
"""صفحهٔ جزئیات ملک — عکس، مشخصات، ارزش برآوردی و ملک‌های مشابه."""
from __future__ import annotations

import streamlit as st

from .. import components as ui
from .. import runtime
from ..labels import fa_code, fa_number, fa_percent, fa_price_short
from ..photos import license_family, photo_url
from ..state import (features_from_listing, is_in_compare, is_saved,
                     toggle_compare, toggle_saved)


def _missing() -> None:
    ui.empty_state("این ملک پیدا نشد",
                   "شناسهٔ آگهی در نشانی صفحه درست نیست. از صفحهٔ جست‌وجو یک ملک انتخاب کنید.")
    from ..nav import SEARCH_PAGE
    st.page_link(SEARCH_PAGE, label="رفتن به جست‌وجو")


def render() -> None:
    listing_id = st.query_params.get("item") or ""
    listing = runtime.listing(str(listing_id)) if listing_id else None
    if listing is None:
        _missing()
        return

    ui.eyebrow(f"کد آگهی {fa_code(listing.id)}")
    ui.mark(f"<h1>{listing.title}</h1>")
    ui.mark(
        f'<div class="kh-badges">'
        f'<span class="kh-badge kh-badge-ink">{listing.property_type}</span>'
        f'<span class="kh-badge">{listing.district_label}</span>'
        f'<span class="kh-badge">{listing.floor_label}</span>'
        f'<span class="kh-badge">{listing.bedrooms_label}</span>'
        f"</div>"
    )

    ui.mark('<div style="height:1rem"></div>')
    ui.mark(ui.gallery_html(listing))

    ui.mark('<div style="height:1.2rem"></div>')
    explanation, summary = runtime.explanation(
        listing.district, listing.area, listing.bedrooms, listing.age,
        listing.floor, listing.parking, listing.storage, listing.elevator)

    left, right = st.columns([1.05, 1])
    with left:
        ui.mark(
            f'<div class="kh-price-hero">'
            f'<div class="kh-kpi-label">قیمت آگهی</div>'
            f'<div class="kh-price-value">{fa_number(listing.price)} تومان</div>'
            f'<div class="kh-price-sub">{fa_number(listing.price_per_m2)} تومان در هر مترمربع</div>'
            f'<div class="kh-band">ارزش برآوردی مدل: '
            f'<strong>{fa_price_short(explanation.price)}</strong> تومان · '
            f"بازهٔ ۸۰ درصدی {fa_price_short(explanation.low)} تا "
            f"{fa_price_short(explanation.high)}</div>"
            f"</div>"
        )
        gap = (listing.price - explanation.price) / explanation.price if explanation.price else 0
        if abs(gap) <= 0.05:
            ui.note("قیمت آگهی با برآورد مدل هم‌خوان است (اختلاف زیر ۵٪).")
        elif gap > 0:
            ui.mark(f'<div class="kh-warn">قیمت آگهی <strong>{fa_percent(gap)}</strong> '
                    f"بالاتر از برآورد مدل است.</div>")
        else:
            ui.note(f"قیمت آگهی <strong>{fa_percent(abs(gap))}</strong> پایین‌تر از "
                    f"برآورد مدل است.")
    with right:
        ui.specs_table(listing)

    ui.mark('<div style="height:.4rem"></div>')
    ui.mark(f'<p class="kh-muted">{listing.description}</p>')

    actions = st.columns(4)
    with actions[0]:
        comparing = is_in_compare(listing.id)
        if st.button("حذف از مقایسه" if comparing else "افزودن به مقایسه",
                     use_container_width=True, type="secondary"):
            toggle_compare(listing.id)
            st.rerun()
    with actions[1]:
        saved = is_saved(listing.id)
        if st.button("برداشتن نشان" if saved else "نشان‌کردن",
                     use_container_width=True, type="secondary"):
            toggle_saved(listing.id)
            st.rerun()
    with actions[2]:
        if st.button("برآورد برای همین ملک", use_container_width=True):
            features_from_listing(listing)
            from ..nav import PREDICT_PAGE
            st.switch_page(PREDICT_PAGE)
    with actions[3]:
        from ..nav import COMPARE_PAGE
        st.page_link(COMPARE_PAGE, label="مشاهدهٔ مقایسه", use_container_width=True)

    ui.rule()
    ui.section("چرا این عدد؟", "سهم هر ویژگی در ارزش برآوردی، از ملک مرجع شهر",
               eyebrow_text="توضیح‌پذیری")
    ui.mark(f'<p class="kh-lead">{summary}</p>')
    explain_left, explain_right = st.columns([1.15, 1])
    with explain_left:
        ui.factor_bars(explanation)
    with explain_right:
        ui.kpi_row([
            ("ارزش پایهٔ شهر", f"{fa_number(explanation.base_price / 1e9, decimals=2)} میلیارد",
             "ملک مرجع با میانهٔ مشخصات"),
            ("اتاق خواب", f"{fa_number(explanation.price_per_m2 / 1e6)} میلیون",
             "قیمت برآوردی هر متر"),
        ], columns=1)
        ui.muted("«پایهٔ شهر» پیش‌بینی مدل برای ملکی با میانهٔ مشخصات شهر است؛ "
                 "نوارهای بالا نشان می‌دهند این آگهی نسبت به آن پایه کجا ایستاده.")
        if explanation.residual:
            ui.muted(f"اختلاف گردکردن: {fa_number(explanation.residual)} تومان")

    ui.rule()
    ui.section("ملک‌های مشابه", "نزدیک‌ترین آگهی‌های همین منطقه از نظر متراژ، سن و اتاق",
               eyebrow_text="مقایسه با بازار")
    if explanation.comparables.is_empty:
        ui.empty_state("ملک مشابهی در این منطقه پیدا نشد")
    else:
        ui.property_grid(list(explanation.comparables.items)[:3], columns=3,
                         key_prefix="detail_cmp_")
        ui.muted(
            f"میانهٔ {fa_number(explanation.comparables.count)} ملک مشابه: "
            f"{fa_number(explanation.comparables.median_price / 1e9, decimals=2)} میلیارد تومان "
            f"({fa_number(explanation.comparables.median_price_per_m2 / 1e6)} میلیون در مترمربع)."
        )

    credit = runtime.photos().credit(listing.cover)
    if credit:
        ui.rule(tight=True)
        ui.muted(
            f"عکس‌ها نمادین‌اند و از تصاویر آزاد {credit.get('provider', '')} "
            f"(مجوز {license_family(credit.get('license'))}) انتخاب شده‌اند؛ "
            "عکس واقعی این ملک نیست."
        )
    ui.disclaimer()
