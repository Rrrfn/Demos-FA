# -*- coding: utf-8 -*-
"""اجزای رابط — کارت، شاخص، جدول، نمودار و پیام‌های خالی.

هر جزء یک تکهٔ مستقل رابط است که چند صفحه از آن استفاده می‌کنند. هدف این است
که ظاهر یک جا تعریف شود: اگر اندازهٔ کارت یا رنگ نمودار عوض شود، همهٔ صفحه‌ها
با هم عوض می‌شوند و ظاهر ناهمگون نمی‌ماند.
"""
from __future__ import annotations

import html as html_lib

import altair as alt
import pandas as pd
import streamlit as st

from .explain import Explanation
from .labels import (fa_number, fa_percent, fa_price_short, feature_value_label,
                     floor_label)
from .listings import Listing
from .photos import photo_url
from .state import MAX_COMPARE, is_in_compare, is_saved, toggle_compare, toggle_saved
from .theme import CHART_COLORS, PALETTE

SYNTHETIC_NOTE = (
    "دادهٔ این پلتفرم **سینتتیک** است و قیمت‌ها قیمت واقعی بازار نیستند. "
    "هدف، نمایش یک سامانهٔ هوش قیمت‌گذاری است، نه اعلام نرخ ملک."
)


# --------------------------------------------------------------- سازندهٔ پایه
def mark(markup: str) -> None:
    """درج HTML خام — نقطهٔ ورود همهٔ اجزای ظاهری."""
    st.markdown(markup, unsafe_allow_html=True)


def _esc(text: object) -> str:
    return html_lib.escape(str(text))


def eyebrow(text: str) -> None:
    mark(f'<span class="kh-eyebrow">{_esc(text)}</span>')


def lead(text: str) -> None:
    mark(f'<p class="kh-lead">{_esc(text)}</p>')


def muted(text: str) -> None:
    mark(f'<p class="kh-muted">{_esc(text)}</p>')


def rule(tight: bool = False) -> None:
    mark(f'<hr class="kh-rule{" kh-hr-tight" if tight else ""}">')


def section(title: str, subtitle: str | None = None, eyebrow_text: str | None = None) -> None:
    if eyebrow_text:
        eyebrow(eyebrow_text)
    mark(f"<h2>{_esc(title)}</h2>")
    if subtitle:
        mark(f'<p class="kh-muted">{_esc(subtitle)}</p>')


def disclaimer(text: str = SYNTHETIC_NOTE) -> None:
    mark(f'<div class="kh-warn">{text}</div>')


def note(text: str) -> None:
    mark(f'<div class="kh-note">{text}</div>')


def empty_state(text: str, hint: str | None = None) -> None:
    body = f"<div><strong>{_esc(text)}</strong></div>"
    if hint:
        body += f'<div class="kh-muted" style="margin-top:.4rem">{_esc(hint)}</div>'
    mark(f'<div class="kh-empty">{body}</div>')


def kpi_row(items: list[tuple[str, str, str]], columns: int = 4) -> None:
    """ردیف شاخص — هر عضو (برچسب، مقدار، توضیح)."""
    for start in range(0, len(items), columns):
        row = items[start:start + columns]
        cols = st.columns(len(row))
        for col, (label, value, note_text) in zip(cols, row):
            with col:
                mark(
                    f'<div class="kh-kpi">'
                    f'<div class="kh-kpi-label">{_esc(label)}</div>'
                    f'<div class="kh-kpi-value">{_esc(value)}</div>'
                    f'<div class="kh-kpi-note">{_esc(note_text)}</div>'
                    f"</div>"
                )


def badges(items: list[str], style: str = "") -> None:
    if not items:
        return
    cls = f"kh-badge {style}".strip()
    chips = "".join(f'<span class="{cls}">{_esc(item)}</span>' for item in items)
    mark(f'<div class="kh-badges">{chips}</div>')


# ------------------------------------------------------------------ کارت ملک
def listing_url(listing_id: str) -> str:
    """نشانی صفحهٔ یک ملک — لینک واقعی مرورگر، نه فقط ناوبری درون‌برنامه‌ای.

    می‌خواهیم کاربر بتواند نشانی یک ملک را کپی کند یا در تب تازه باز کند؛
    پس کارت یک پیوند واقعی است.
    """
    return f"/listing?item={listing_id}"


def card_html(listing: Listing, *, tag: str | None = None) -> str:
    cover = photo_url(listing.cover)
    media = (f'<img src="{cover}" alt="{_esc(listing.title)}" loading="lazy">'
             if cover else
             '<div style="height:208px;display:flex;align-items:center;'
             'justify-content:center;color:#8A7F6C">بدون تصویر</div>')
    tag_html = f'<span class="kh-card-tag">{_esc(tag)}</span>' if tag else ""
    chips = "".join(f'<span class="kh-badge">{_esc(item)}</span>'
                     for item in listing.amenities)
    if not chips:
        chips = '<span class="kh-badge">بدون امکانات ویژه</span>'
    return (
        f'<div class="kh-card">'
        f'<a class="kh-card-link" href="{listing_url(listing.id)}">'
        f'<div class="kh-card-media">{media}{tag_html}</div>'
        f'<div class="kh-card-body">'
        f'<h3 class="kh-card-title">{_esc(listing.title)}</h3>'
        f'<div class="kh-card-meta">{_esc(listing.district_label)} · '
        f'{_esc(floor_label(listing.floor))} · {_esc(listing.bedrooms_label)}</div>'
        f'<div class="kh-badges">{chips}</div>'
        f'<div class="kh-card-price">{_esc(fa_price_short(listing.price))} تومان'
        f'<span class="kh-card-unit"> · {_esc(fa_number(listing.price_per_m2))} تومان/متر</span></div>'
        f'<div class="kh-card-more">مشاهدهٔ جزئیات ←</div>'
        f"</div></a></div>"
    )


def property_card(listing: Listing, *, tag: str | None = None,
                  actions: bool = True, key_prefix: str = "") -> None:
    """کارت یک ملک؛ خودِ کارت پیوند است و دو دکمهٔ عملیات زیر آن می‌آید."""
    mark(card_html(listing, tag=tag))
    if not actions:
        return
    comparing = is_in_compare(listing.id)
    saved = is_saved(listing.id)
    left, right = st.columns(2)
    with left:
        if st.button("حذف از مقایسه" if comparing else "افزودن به مقایسه",
                     key=f"{key_prefix}cmp_{listing.id}", type="secondary",
                     use_container_width=True):
            added = toggle_compare(listing.id)
            if not added and not comparing:
                st.toast(f"فهرست مقایسه پر است (حداکثر {fa_number(MAX_COMPARE)})")
            st.rerun()
    with right:
        if st.button("نشان‌شده ✓" if saved else "نشان‌کردن",
                     key=f"{key_prefix}save_{listing.id}", type="secondary",
                     use_container_width=True):
            toggle_saved(listing.id)
            st.rerun()


def property_grid(listings: list[Listing], *, columns: int = 3,
                  tags: list[str] | None = None, key_prefix: str = "") -> None:
    """چیدمان کارت‌ها در شبکه — هر ردیف چند ستون."""
    for start in range(0, len(listings), columns):
        chunk = listings[start:start + columns]
        cols = st.columns(len(chunk))
        for offset, (col, listing) in enumerate(zip(cols, chunk)):
            index = start + offset
            with col:
                property_card(
                    listing,
                    tag=tags[index] if tags and index < len(tags) else None,
                    key_prefix=key_prefix,
                )


# ----------------------------------------------------------- صفحهٔ جزئیات ملک
def gallery_html(listing: Listing) -> str:
    photos = [photo_url(name) for name in listing.gallery if name]
    if not photos:
        return ('<div class="kh-empty">برای این ملک عکسی در دسترس نیست.'
                "</div>")
    main = f'<div class="kh-gallery-main"><img src="{photos[0]}" alt="{_esc(listing.title)}"></div>'
    sides = "".join(
        f'<div class="kh-gallery-side"><img src="{photo}" alt="{_esc(listing.title)}" loading="lazy"></div>'
        for photo in photos[1:3])
    return f'<div class="kh-gallery">{main}{sides}</div>'


def specs_table(listing: Listing) -> None:
    rows = [
        ("منطقه", listing.district_label),
        ("متراژ", f"{fa_number(listing.area)} مترمربع"),
        ("اتاق خواب", listing.bedrooms_label),
        ("سن بنا", f"{fa_number(listing.age)} سال"),
        ("طبقه", listing.floor_label),
        ("نوع ملک", listing.property_type),
        ("قیمت هر متر", f"{fa_number(listing.price_per_m2)} تومان"),
        ("تاریخ انتشار", f"{fa_number(listing.days_ago)} روز پیش"),
    ]
    for flag, name in ((listing.parking, "پارکینگ"), (listing.storage, "انباری"),
                       (listing.elevator, "آسانسور")):
        rows.append((name, "دارد" if flag else "ندارد"))
    cells = "".join(
        f"<tr><td>{_esc(label)}</td><td>{_esc(value)}</td></tr>" for label, value in rows)
    mark(f'<table class="kh-specs">{cells}</table>')


def price_hero(explanation: Explanation) -> None:
    mark(
        f'<div class="kh-price-hero">'
        f'<div class="kh-kpi-label">ارزش برآوردی مدل</div>'
        f'<div class="kh-price-value">{_esc(fa_number(explanation.price))} تومان</div>'
        f'<div class="kh-price-sub">{_esc(fa_number(explanation.price_per_m2))} تومان در هر مترمربع</div>'
        f'<div class="kh-band">بازهٔ ۸۰ درصدی: '
        f'<strong>{_esc(fa_price_short(explanation.low))}</strong> تا '
        f'<strong>{_esc(fa_price_short(explanation.high))}</strong> تومان '
        f"(±{_esc(fa_number(explanation.relative_width * 50, decimals=1))}٪)</div>"
        f"</div>"
    )


def factor_bars(explanation: Explanation, limit: int = 6) -> None:
    """نوارهای سهم هر ویژگی در قیمت."""
    factors = explanation.factors[:limit]
    if not factors:
        return
    largest = max(abs(item.amount) for item in factors) or 1
    blocks = []
    for item in factors:
        direction = "up" if item.amount >= 0 else "down"
        width = max(2.0, abs(item.amount) / largest * 100)
        sign = "+" if item.amount >= 0 else "−"
        blocks.append(
            f'<div class="kh-factor">'
            f'<div class="kh-factor-head">'
            f'<span class="kh-factor-name">{_esc(item.label)}: {_esc(item.value_label)}</span>'
            f'<span class="kh-factor-amount {direction}">{sign}{_esc(fa_price_short(abs(item.amount)))}</span>'
            f"</div>"
            f'<div class="kh-bar"><span class="{direction}" style="width:{width:.1f}%"></span></div>'
            f"</div>"
        )
    mark("".join(blocks))


def comparables_table(explanation: Explanation) -> pd.DataFrame:
    return pd.DataFrame([{
        "شناسه": item.id,
        "عنوان": item.title,
        "متراژ": item.area,
        "سن": item.age,
        "قیمت (تومان)": item.price,
        "قیمت هر متر": item.price_per_m2,
    } for item in explanation.comparables.items])


def _fa_cell(value: object) -> str:
    """یک خانهٔ جدول به شکل نمایشی فارسی.

    مقادیر خالی به خط تیره بدل می‌شوند (مثلاً «R² اعتبارسنجی» که فقط برای
    مدل برنده محاسبه می‌شود) و عددها با جداکنندهٔ فارسی.
    """
    if value is None:
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return "دارد" if value else "ندارد"
    if isinstance(value, (int, float)):
        return fa_number(value) if float(value).is_integer() \
            else fa_number(value, decimals=2)
    return str(value)


def fa_table(frame: pd.DataFrame, **kwargs) -> None:
    """جدول با اعداد فارسی.

    ``st.dataframe`` ستون‌های عددی را خام نشان می‌دهد و در رابط فارسی رقم لاتین
    می‌ماند. اینجا ستون‌های عددی از پیش قالب‌بندی می‌شوند؛ نتیجه یک جدول
    یکدست است. (مرتب‌سازی ستون به‌جای عددی، متنی می‌شود — که برای جدول نمایشی
    این پروژه هزینه‌ای ندارد.)

    ستون شمارهٔ ردیف هم پنهان می‌شود: آن هم رقم لاتین می‌آورد و هیچ اطلاعاتی
    به جدول اضافه نمی‌کند.
    """
    if frame.empty:
        empty_state("داده‌ای برای این جدول نیست")
        return
    display = frame.copy()
    for name in list(display.columns):
        column = display[name]
        # ستون‌های «مخلوط» هم قالب‌بندی می‌شوند: ستونی که فقط برای مدل برنده
        # عدد دارد و بقیهٔ ردیف‌هایش خالی است، نه عددی خالص است و نه متنی.
        # اگر خام به ``st.dataframe`` برود، تبدیل Arrow روی نوع مخلوط
        # شکست می‌خورد و جدول رندر نمی‌شود.
        if pd.api.types.is_numeric_dtype(column) or all(
                isinstance(value, (int, float)) or value is None or
                (not isinstance(value, str) and pd.isna(value))
                for value in column):
            display[name] = [_fa_cell(value) for value in column]
    kwargs.setdefault("hide_index", True)
    st.dataframe(display, **kwargs)


# ------------------------------------------------------------------ نمودارها
def persian_digit_expr(field: str = "datum.label") -> str:
    """عبارت Vega برای فارسی‌کردن رقم‌ها و جداکننده‌ها.

    کتابخانهٔ نمودار، عدد محورها را با رقم لاتین می‌نویسد و در یک رابط تمام‌فارسی
    این تنها جای ناهمخوان می‌ماند. Vega تابع تنطیم «رقم‌به‌رقم» ندارد، پس برای
    هر رقم یک ``split``/``join`` تودرتو ساخته می‌شود؛ ``split`` همهٔ تکرارها را
    می‌گیرد (برخلاف ``replace`` با الگوی رشته‌ای که فقط اولی را عوض می‌کند).
    """
    expression = field
    for latin, persian in zip("0123456789", "۰۱۲۳۴۵۶۷۸۹"):
        expression = f"join(split({expression},'{latin}'),'{persian}')"
    for latin, persian in ((",", "٬"), (".", "٫")):
        expression = f"join(split({expression},'{latin}'),'{persian}')"
    return expression


def _style(chart: alt.Chart, *, height: int = 300) -> alt.Chart:
    return (chart.properties(height=height, background="transparent")
            .configure_axis(labelColor=PALETTE["muted"], titleColor=PALETTE["muted"],
                            gridColor=CHART_COLORS["grid"], domainColor=PALETTE["line"],
                            labelFontSize=12, titleFontSize=12, labelLimit=220,
                            labelExpr=persian_digit_expr())
            .configure_view(strokeWidth=0))


def bar_chart(frame: pd.DataFrame, *, x: str, y: str, x_title: str = "",
              y_title: str = "", color: str | None = None,
              horizontal: bool = False, height: int = 300,
              tooltip_labels: dict[str, str] | None = None) -> None:
    if frame.empty:
        empty_state("داده‌ای برای این نمودار نیست")
        return
    # تولتیپ‌ها هم باید فارسی باشند. ستون‌های عددی برای جای‌گیری محور لازم‌اند و
    # نمی‌توان رشته‌شان کرد، پس برای هر ستون عددی یک همزادِ رشته‌ای ساخته
    # می‌شود که فقط در تولتیپ استفاده می‌شود.
    frame = frame.copy()
    tips = []
    for name in list(frame.columns):        # فهرست از پیش گرفته می‌شود چون ستون اضافه می‌کنیم
        label = (tooltip_labels or {}).get(name, name)
        if pd.api.types.is_numeric_dtype(frame[name]):
            twin = f"__{name}"
            frame[twin] = [fa_number(value) if float(value).is_integer()
                           else fa_number(value, decimals=2) for value in frame[name]]
            tips.append(alt.Tooltip(field=twin, title=label))
        else:
            tips.append(alt.Tooltip(field=name, title=label))
    base = alt.Chart(frame)
    if horizontal:
        chart = base.mark_bar(cornerRadiusEnd=3).encode(
            y=alt.Y(f"{y}:N", sort="-x", title=y_title, axis=alt.Axis(labelAngle=0)),
            x=alt.X(f"{x}:Q", title=x_title),
            color=alt.value(color or CHART_COLORS["bronze"]), tooltip=tips)
    else:
        chart = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X(f"{x}:N" if frame[x].dtype == object else f"{x}:Q",
                    title=x_title, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{y}:Q", title=y_title),
            color=alt.value(color or CHART_COLORS["bronze"]), tooltip=tips)
    st.altair_chart(_style(chart, height=height), use_container_width=True)


def area_chart(frame: pd.DataFrame, *, x: str, y: str, x_title: str = "",
               y_title: str = "", height: int = 300) -> None:
    if frame.empty:
        empty_state("داده‌ای برای این نمودار نیست")
        return
    chart = (alt.Chart(frame).mark_area(
        line={"color": CHART_COLORS["bronze"]},
        color=alt.Gradient(gradient="linear",
                           stops=[alt.GradientStop(color="#EFE6D6", offset=0),
                                  alt.GradientStop(color="#FFFFFF", offset=1)],
                           x1=1, x2=1, y1=1, y2=0))
        .encode(x=alt.X(f"{x}:Q", title=x_title),
                y=alt.Y(f"{y}:Q", title=y_title)))
    st.altair_chart(_style(chart, height=height), use_container_width=True)


def importance_chart(importance: list[dict], labels: dict[str, str],
                     height: int = 280) -> None:
    if not importance:
        empty_state("اهمیت ویژگی‌ها محاسبه نشده است")
        return
    frame = pd.DataFrame([{
        "ویژگی": labels.get(item["feature"], item["feature"]),
        "اهمیت": item["importance"] * 100,
    } for item in importance])
    # محور باید عدد بماند و تولتیپ فارسی؛ پس همزاد رشته‌ای ساخته می‌شود.
    frame["__اهمیت"] = [fa_number(value, decimals=1) for value in frame["اهمیت"]]
    chart = (alt.Chart(frame).mark_bar(cornerRadiusEnd=3)
             .encode(y=alt.Y("ویژگی:N", sort="-x", title="", axis=alt.Axis(labelAngle=0)),
                     x=alt.X("اهمیت:Q", title="سهم از اهمیت (٪)"),
                     color=alt.value(CHART_COLORS["ink"]),
                     tooltip=[alt.Tooltip("ویژگی:N", title="ویژگی"),
                              alt.Tooltip("__اهمیت:N", title="اهمیت (٪)")]))
    st.altair_chart(_style(chart, height=height), use_container_width=True)


def interval_summary(label_interval: dict) -> None:
    """گزارش پوشش بازه — عددی که اندازه‌گیری شده، نه ادعاشده."""
    if not label_interval:
        return
    kpi_row([
        ("پوشش هدف بازه", f"{fa_number(label_interval['target_coverage_pct'])}٪",
         "سطح اطمینانی که وعده داده شده"),
        ("پوشش اندازه‌گیری‌شده",
         f"{fa_number(label_interval['measured_coverage_pct'], decimals=1)}٪",
         "روی نیمهٔ آزمونی که کالیبراسیون ندیده"),
        ("میانگین پهنای بازه",
         f"{fa_number(label_interval['mean_width_toman'] / 1e9, decimals=2)} میلیارد",
         "به تومان"),
        ("ضریب کالیبراسیون",
         f"×{fa_number(label_interval.get('calibration_factor', 1), decimals=2)}",
         "بزرگ‌نمایی لازم برای رسیدن به پوشش هدف"),
    ])


def feature_labels_map() -> dict[str, str]:
    from .labels import FEATURE_LABELS
    return dict(FEATURE_LABELS)


def percent_note(ratio: float | None) -> str:
    if ratio is None:
        return "—"
    return fa_percent(ratio, signed=True)


def value_label(feature: str, value: object) -> str:
    return feature_value_label(feature, value)
