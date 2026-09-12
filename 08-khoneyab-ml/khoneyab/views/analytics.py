# -*- coding: utf-8 -*-
"""صفحهٔ تحلیل بازار — تجمیع‌های واقعی کاتالوگ و بینش مدل."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import components as ui
from .. import runtime
from ..labels import (FEATURE_LABELS, fa_datetime, fa_number, fa_percent,
                      fa_price_short)
from ..theme import CHART_COLORS


def render() -> None:
    ui.eyebrow("تحلیل بازار")
    ui.mark("<h1>نبض بازار در یک نگاه</h1>")
    ui.lead("هر عدد و هر نمودار این صفحه از تجمیع آگهی‌های همین کاتالوگ ساخته شده "
            "است. جایی که داده کافی نباشد، نمودار خالی می‌ماند و پیام می‌دهد — "
            "نه این‌که با مقدار ساختگی پر شود.")

    overview = runtime.overview()
    ui.rule()
    ui.kpi_row([
        ("آگهی فعال", fa_number(overview["listings"]), "در کاتالوگ"),
        ("میانهٔ قیمت", f"{fa_number(overview['median_price'] / 1e9, decimals=2)} میلیارد",
         "تومان"),
        ("میانهٔ قیمت متر", f"{fa_number(overview['median_price_m2'] / 1e6)} میلیون",
         "تومان در مترمربع"),
        ("میانهٔ سن بنا", f"{fa_number(overview['median_age'], decimals=1)} سال",
         "در کاتالوگ"),
        ("میانگین متراژ", f"{fa_number(overview['mean_area'])} متر", "زیربنا"),
        ("سهم واحدهای بزرگ", fa_percent(overview["luxury_share"]),
         "بالای ۲۰۰ مترمربع"),
    ], columns=3)

    districts = runtime.districts()
    ui.rule()
    ui.section("مناطق", "میانهٔ قیمت هر مترمربع، از گران به ارزان",
               eyebrow_text="تحلیل منطقه‌ای")
    # نمودار تمام‌عرض است، نه نصف صفحه: ۲۲ نام منطقه در نیم‌عرض جا نمی‌شوند و
    # Vega-Lite برچسب‌ها را حذف می‌کند؛ آن‌وقت نمودار بی‌نام می‌ماند. جدول
    # هم زیر نمودار می‌آید تا ستون‌ها در عرض کوچک فشرده نشوند.
    chart_frame = districts.assign(میلیون=lambda frame: frame["median_price_m2"] / 1e6)
    ui.bar_chart(chart_frame, x="میلیون", y="short_name",
                 x_title="میلیون تومان در مترمربع", horizontal=True,
                 color=CHART_COLORS["bronze"], height=560,
                 tooltip_labels={"short_name": "منطقه", "میلیون": "قیمت متر"})
    display = districts[["short_name", "listings", "median_price_m2", "median_price"]].copy()
    display["median_price_m2"] = (display["median_price_m2"] / 1e6).round(1)
    display["median_price"] = (display["median_price"] / 1e9).round(2)
    display.columns = ["منطقه", "تعداد آگهی", "میلیون/متر", "میلیارد"]
    with st.expander("جدول کامل مناطق"):
        ui.fa_table(display, use_container_width=True, height=420)

    ui.rule()
    ui.section("توزیع‌ها", "چگالی قیمت در کاتالوگ", eyebrow_text="پراکندگی")
    left, right = st.columns(2)
    with left:
        ui.muted("توزیع قیمت کل (میلیارد تومان)")
        ui.bar_chart(runtime.distribution(), x="center", y="count",
                     x_title="میلیارد تومان", y_title="تعداد آگهی",
                     color=CHART_COLORS["ink"], height=280,
                     tooltip_labels={"count": "تعداد", "center": "مرکز سطل"})
    with right:
        ui.muted("توزیع قیمت هر مترمربع (میلیون تومان)")
        per_m2 = runtime.per_m2_distribution().assign(
            میلیون=lambda frame: frame["center"] / 1e6)
        ui.bar_chart(per_m2, x="میلیون", y="count",
                     x_title="میلیون تومان در مترمربع", y_title="تعداد آگهی",
                     color=CHART_COLORS["bronze"], height=280,
                     tooltip_labels={"count": "تعداد", "میلیون": "مرکز سطل"})

    ui.rule()
    ui.section("رابطهٔ متراژ و اتاق با قیمت", eyebrow_text="ساختار")
    left, right = st.columns(2)
    with left:
        ui.muted("میانهٔ قیمت هر متر در سطل‌های متراژ")
        buckets = runtime.area_buckets()
        buckets = buckets[buckets["count"] > 0].assign(
            میلیون=lambda frame: frame["median_price_m2"] / 1e6)
        ui.bar_chart(buckets, x="bucket", y="میلیون",
                     x_title="مترمربع", y_title="میلیون تومان در متر",
                     color=CHART_COLORS["ink"], height=280,
                     tooltip_labels={"bucket": "بازهٔ متراژ", "میلیون": "قیمت متر",
                                     "count": "تعداد"})
    with right:
        ui.muted("میانهٔ قیمت کل بر پایهٔ تعداد اتاق خواب")
        rooms = runtime.bedrooms().assign(
            میلیارد=lambda frame: frame["median_price"] / 1e9)
        ui.bar_chart(rooms, x="bedrooms", y="میلیارد",
                     x_title="تعداد اتاق", y_title="میلیارد تومان",
                     color=CHART_COLORS["bronze"], height=280,
                     tooltip_labels={"bedrooms": "اتاق", "میلیارد": "قیمت میانه",
                                     "count": "تعداد"})

    movers = runtime.market_movers()
    ui.rule()
    ui.section("گران‌ترین و ارزان‌ترین مناطق", eyebrow_text="جابه‌جایی‌ها")
    left, right = st.columns(2)
    for column, (title, key) in zip((left, right),
                                    (("گران‌ترین", "expensive"), ("ارزان‌ترین", "affordable"))):
        with column:
            ui.mark(f"<h3>{title}</h3>")
            frame = movers[key][["short_name", "median_price_m2", "listings"]].copy()
            frame["median_price_m2"] = (frame["median_price_m2"] / 1e6).round(1)
            frame.columns = ["منطقه", "میلیون/متر", "تعداد آگهی"]
            ui.fa_table(frame, use_container_width=True, hide_index=True)

    ui.rule()
    ui.section("بینش مدل", "چه چیزی قیمت را می‌سازد و با چه دقتی",
               eyebrow_text="مدل")
    insights = runtime.insights()
    ui.kpi_row([
        ("مدل برنده", insights["best_model"] or "—", "انتخاب‌شده با R² آزمون"),
        ("R² آزمون", fa_number(insights["r2"], decimals=4) if insights["r2"] else "—",
         "توضیح تغییرات قیمت"),
        ("R² اعتبارسنجی متقابل",
         f"{fa_number(insights['cv_r2_mean'], decimals=4)} ± "
         f"{fa_number(insights['cv_r2_std'], decimals=4)}"
         if insights["cv_r2_mean"] else "—",
         f"میانگین {fa_number(insights['cv_folds'] or 0)} بخش"),
        ("میانگین خطای مطلق", fa_percent((insights["mape_pct"] or 0) / 100),
         "درصد از قیمت واقعی"),
    ])

    ui.mark('<div style="height:.6rem"></div>')
    left, right = st.columns([1, 1])
    with left:
        ui.muted("اهمیت ویژگی‌ها با روش جایگشت — مستقل از نوع مدل")
        ui.importance_chart(insights["importance"], FEATURE_LABELS)
    with right:
        ui.muted("دقت بازهٔ اطمینان")
        ui.interval_summary(insights["interval"])
        ui.mark('<div style="height:.6rem"></div>')
        best = runtime.metrics()["results"]
        frame = pd.DataFrame([{
            "مدل": name,
            "R² آزمون": values["r2"],
            "MAPE٪": values["mape_pct"],
            "MAE (میلیارد)": round(values["mae_toman"] / 1e9, 2),
            "زمان آموزش (ثانیه)": values["fit_seconds"],
        } for name, values in best.items()]).set_index("مدل")
        ui.fa_table(frame, use_container_width=True)

    ui.rule(tight=True)
    ui.muted(
        f"آخرین آموزش مدل: {fa_datetime(insights['trained_at'])} · "
        f"{fa_number(insights['n_samples'])} رکورد آموزشی · "
        f"خطای معیار باقی‌مانده "
        f"{fa_number((insights['residual_std_toman'] or 0) / 1e9, decimals=2)} میلیارد تومان."
    )
    ui.disclaimer()
