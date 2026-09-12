# -*- coding: utf-8 -*-
"""خانه‌یاب — پلتفرم هوش بازار مسکن تهران.

اجرا:

    streamlit run app.py

این فایل فقط پوسته است: پیکربندی صفحه، پوستهٔ ظاهری، نوار کنار و اعلام فهرست
صفحه‌ها. منطق هر صفحه در ``khoneyab/views`` است.
"""
from __future__ import annotations

import streamlit as st

from khoneyab import theme
from khoneyab.nav import build_pages
from khoneyab.photos import photo_url
from khoneyab.runtime import photos

BRAND_FA = "خانه‌یاب"
BRAND_EN = "KHANEYAB"
TAGLINE = "پلتفرم هوش بازار مسکن تهران"


def sidebar() -> None:
    """نوار کنار — نشان برند و یادآوری ماهیت داده."""
    library = photos()
    logo = photo_url(library.gallery(2)[0]) if library.total else ""
    logo_tag = (
        f'<img src="{logo}" alt="" style="width:100%;height:88px;object-fit:cover;'
        'border-radius:12px;margin-bottom:.7rem">' if logo else ""
    )
    with st.sidebar:
        st.markdown(
            '<div style="padding:.2rem 0 1rem">'
            f"{logo_tag}"
            f'<div class="kh-serif" style="letter-spacing:.28em;font-size:.7rem;'
            f'color:#A8854E">{BRAND_EN}</div>'
            '<div style="font-weight:900;font-size:1.28rem;color:#12100E;'
            f'line-height:1.6">{BRAND_FA}</div>'
            f'<div class="kh-muted" style="font-size:.76rem">{TAGLINE}</div>'
            '<hr style="border:0;height:1px;background:#E6DED1;margin:.9rem 0">'
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="kh-muted" style="font-size:.72rem;line-height:1.9">'
            "داده‌ها سینتتیک‌اند و قیمت واقعی بازار نیستند.</div>",
            unsafe_allow_html=True,
        )


def main() -> None:
    st.set_page_config(
        page_title=f"{BRAND_FA} — {TAGLINE}",
        page_icon="🏛",
        layout="wide",
        # ``auto`` یعنی در عرض‌های باریک نوار کنار بسته شروع می️شود. در Streamlit
        # نوار کنار در صفحهٔ کوچک روی محتوا می‌نشیند، نه کنارش؛ اگر باز شروع
        # شود، بخشی از کارت‌ها و محور نمودارها زیرش پنهان می‌ماند.
        initial_sidebar_state="auto",
    )
    theme.inject()
    sidebar()
    st.navigation(build_pages(), position="sidebar").run()


main()
