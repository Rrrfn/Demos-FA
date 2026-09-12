# -*- coding: utf-8 -*-
"""صفحهٔ جست‌وجوی ملک — فیلتر، مرتب‌سازی و مرور نتیجه‌ها."""
from __future__ import annotations

import math

import streamlit as st

from .. import components as ui
from .. import runtime
from ..config import AREA_RANGE, BEDROOM_RANGE, DISTRICT_BY_CODE, DISTRICT_CODES
from ..labels import district_name, fa_number, fa_price_short, bedrooms_label
from ..search import SORT_OPTIONS
from ..state import is_in_compare, is_saved

FILTER_KEY = "search_filters"
PAGE_SIZE = 12


def _price_slider_bounds() -> tuple[float, float, float]:
    """کمینه، بیشینه و گام اسلایدر قیمت.

    کران‌ها روی مضرب گام گرد می‌شوند؛ اگر مقدار اولیه با گام نخواند، مرورگر
    خطای «مقدار با گام سازگار نیست» می‌دهد و دستهٔ اسلایدر جابه‌جا می‌شود.
    """
    frame = runtime.listings_frame_bounds()
    step = 0.5
    low = math.floor(frame["price_min"] / 1e9 / step) * step
    high = math.ceil(frame["price_max"] / 1e9 / step) * step
    return low, high, step


def _default_filters() -> dict:
    low, high, _ = _price_slider_bounds()
    return {
        "districts": (),
        "price": (int(round(low * 1e9)), int(round(high * 1e9))),
        "area": (AREA_RANGE[0], AREA_RANGE[1]),
        "bedrooms": (),
        "age_max": 45,
        "parking": False,
        "storage": False,
        "elevator": False,
        "sort": "تازه‌ترین",
        "page": 1,
    }


def _filters() -> dict:
    if FILTER_KEY not in st.session_state:
        st.session_state[FILTER_KEY] = _default_filters()
    return st.session_state[FILTER_KEY]


def _set(**changes) -> None:
    state = dict(_filters())
    state.update(changes)
    st.session_state[FILTER_KEY] = state


def render() -> None:
    ui.eyebrow("جست‌وجوی ملک")
    ui.mark("<h1>آگهی‌ها را با معیارهای خودتان ببینید</h1>")
    ui.lead("فیلترها همه اختیاری‌اند: هر کدام را باز بگذارید یعنی «مهم نیست». "
            "نتیجه‌ها در پایان هر تغییر به‌روز می‌شوند.")

    state = _filters()

    with st.expander("فیلترها", expanded=True):
        first = st.columns(3)
        with first[0]:
            chosen_districts = st.multiselect(
                "منطقه", options=list(DISTRICT_CODES),
                default=list(state["districts"]),
                placeholder="همهٔ مناطق",
                format_func=lambda code: district_name(code))
        with first[1]:
            chosen_bedrooms = st.multiselect(
                "تعداد اتاق خواب", options=list(range(BEDROOM_RANGE[0], BEDROOM_RANGE[1] + 1)),
                default=list(state["bedrooms"]),
                placeholder="مهم نیست",
                format_func=lambda value: bedrooms_label(value))
        with first[2]:
            sort = st.selectbox("ترتیب نمایش", options=list(SORT_OPTIONS),
                                index=list(SORT_OPTIONS).index(state["sort"]))

        second = st.columns(3)
        with second[0]:
            price_low, price_high, price_step = _price_slider_bounds()
            price_billions = st.slider(
                "بازهٔ قیمت (میلیارد تومان)",
                min_value=price_low, max_value=price_high,
                value=(state["price"][0] / 1e9, state["price"][1] / 1e9),
                step=price_step, format="%.1f")
        with second[1]:
            area_range = st.slider("بازهٔ متراژ (مترمربع)", min_value=AREA_RANGE[0],
                                   max_value=AREA_RANGE[1],
                                   value=(state["area"][0], state["area"][1]), step=5)
        with second[2]:
            age_max = st.slider("حداکثر سن بنا (سال)", min_value=0, max_value=45,
                                value=int(state["age_max"]), step=1)

        third = st.columns(4)
        with third[0]:
            parking = st.checkbox("پارکینگ", value=state["parking"])
        with third[1]:
            storage = st.checkbox("انباری", value=state["storage"])
        with third[2]:
            elevator = st.checkbox("آسانسور", value=state["elevator"])
        with third[3]:
            st.markdown('<div style="height:1.6rem"></div>', unsafe_allow_html=True)
            if st.button("پاک‌کردن فیلترها", type="secondary", use_container_width=True):
                st.session_state[FILTER_KEY] = _default_filters()
                st.rerun()

    price_range = (int(round(price_billions[0] * 1e9)), int(round(price_billions[1] * 1e9)))
    changed = (
        tuple(chosen_districts) != tuple(state["districts"])
        or tuple(chosen_bedrooms) != tuple(state["bedrooms"])
        or price_range != tuple(state["price"])
        or tuple(area_range) != tuple(state["area"])
        or int(age_max) != int(state["age_max"])
        or sort != state["sort"]
        or parking != state["parking"]
        or storage != state["storage"]
        or elevator != state["elevator"]
    )
    if changed:
        # هر تغییر فیلتر، صفحه را به اول برمی‌گرداند؛ وگرنه کاربر در صفحهٔ ۷
        # نتیجه‌ای می‌بیند که فقط دو مورد دارد و فکر می‌کند باگ است.
        _set(districts=tuple(chosen_districts), bedrooms=tuple(chosen_bedrooms),
             price=price_range, area=tuple(area_range), age_max=int(age_max),
             sort=sort, parking=parking, storage=storage, elevator=elevator, page=1)
        state = _filters()

    result = runtime.search(
        tuple(state["districts"]), tuple(state["price"]), tuple(state["area"]),
        tuple(state["bedrooms"]), int(state["age_max"]), bool(state["parking"]),
        bool(state["storage"]), bool(state["elevator"]), state["sort"],
        int(state["page"]),
    )

    ui.rule()
    if result.is_empty:
        ui.empty_state("آگهی‌ای با این مشخصات پیدا نشد",
                       "بازهٔ قیمت یا متراژ را بازتر کنید یا فیلتر امکانات را بردارید.")
        return

    active = []
    if state["districts"]:
        active.append(f"{fa_number(len(state['districts']))} منطقه")
    if state["bedrooms"]:
        active.append(f"{fa_number(len(state['bedrooms']))} گروه اتاق")
    for flag, name in ((state["parking"], "پارکینگ"), (state["storage"], "انباری"),
                       (state["elevator"], "آسانسور")):
        if flag:
            active.append(name)

    ui.kpi_row([
        ("نتیجه", fa_number(result.total),
         f"صفحهٔ {fa_number(result.page)} از {fa_number(result.pages)}"),
        ("میانهٔ قیمت این صفحه", f"{fa_number(result.median_price() / 1e9, decimals=2)} میلیارد",
         "تومان"),
        ("میانهٔ قیمت متر", f"{fa_number(result.median_price_per_m2() / 1e6)} میلیون",
         "تومان در هر مترمربع"),
        ("مقایسه‌شده", fa_number(len(st.session_state.get("compare_ids", []))),
         "ملک در فهرست مقایسه"),
    ])

    if active:
        ui.mark('<div style="height:.5rem"></div>')
        ui.badges(active, "kh-badge-bronze")

    ui.rule()
    items = result.items()
    tags = ["در مقایسه" if is_in_compare(item.id) else ("نشان‌شده" if is_saved(item.id) else "")
            for item in items]
    ui.property_grid(items, columns=3, tags=[tag or None for tag in tags],
                     key_prefix="search_")

    ui.rule()
    nav = st.columns([1, 2, 1])
    with nav[0]:
        if st.button("صفحهٔ بعد", disabled=not result.has_next, use_container_width=True):
            _set(page=result.page + 1)
            st.rerun()
    with nav[1]:
        st.markdown(
            f'<div style="text-align:center;color:#6F675C;padding-top:.5rem">'
            f'صفحهٔ {fa_number(result.page)} از {fa_number(result.pages)}'
            f"</div>", unsafe_allow_html=True)
    with nav[2]:
        if st.button("صفحهٔ قبل", disabled=not result.has_prev,
                     type="secondary", use_container_width=True):
            _set(page=result.page - 1)
            st.rerun()
