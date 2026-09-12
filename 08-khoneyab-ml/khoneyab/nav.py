# -*- coding: utf-8 -*-
"""فهرست صفحه‌ها — نقطهٔ واحد تعریف مسیرها.

صفحه‌ها یک بار ساخته و در متغیرهای همین ماژول نگه داشته می‌شوند، تا هر جای
برنامه بتواند با ``from .nav import SEARCH_PAGE`` به آن‌ها لینک بدهد. اگر
مسیرها چند جا تعریف شوند، دیر یا زود یک لینک به مسیر ناموجود اشاره می‌کند.
"""
from __future__ import annotations

import streamlit as st

HOME_PAGE: st.Page | None = None
SEARCH_PAGE: st.Page | None = None
DETAIL_PAGE: st.Page | None = None
COMPARE_PAGE: st.Page | None = None
PREDICT_PAGE: st.Page | None = None
ANALYTICS_PAGE: st.Page | None = None
METHODOLOGY_PAGE: st.Page | None = None

_PAGES: list[st.Page] = []

#: عنوان گروه در نوار کنار — ترتیب همان ترتیب نمایش است.
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("مرور", ("home", "search", "compare")),
    ("تحلیل و برآورد", ("estimate", "analytics")),
    ("درباره", ("methodology", "listing")),
)


def build_pages() -> list[st.Page]:
    """ساخت (یا بازگرداندن) فهرست صفحه‌ها."""
    global HOME_PAGE, SEARCH_PAGE, DETAIL_PAGE, COMPARE_PAGE
    global PREDICT_PAGE, ANALYTICS_PAGE, METHODOLOGY_PAGE, _PAGES

    if _PAGES:
        return _PAGES

    from .views import (analytics, compare, detail, home, methodology, predict,
                        search)

    HOME_PAGE = st.Page(home.render, title="خانه", url_path="home", default=True)
    SEARCH_PAGE = st.Page(search.render, title="جست‌وجوی ملک", url_path="search")
    COMPARE_PAGE = st.Page(compare.render, title="مقایسه", url_path="compare")
    PREDICT_PAGE = st.Page(predict.render, title="برآورد قیمت", url_path="estimate")
    ANALYTICS_PAGE = st.Page(analytics.render, title="تحلیل بازار", url_path="analytics")
    METHODOLOGY_PAGE = st.Page(methodology.render, title="متدولوژی", url_path="methodology")
    # صفحهٔ جزئیات در نوار کنار دیده نمی‌شود: از کارت‌ها و لینک‌ها باز می‌شود.
    DETAIL_PAGE = st.Page(detail.render, title="جزئیات ملک", url_path="listing")

    _PAGES = [HOME_PAGE, SEARCH_PAGE, COMPARE_PAGE, PREDICT_PAGE,
              ANALYTICS_PAGE, METHODOLOGY_PAGE, DETAIL_PAGE]
    return _PAGES


def sidebar_pages() -> list[st.Page]:
    """صفحه‌هایی که در نوار کنار فهرست می‌شوند — بدون صفحهٔ جزئیات."""
    pages = build_pages()
    return [page for page in pages if page is not DETAIL_PAGE]
