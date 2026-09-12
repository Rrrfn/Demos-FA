# -*- coding: utf-8 -*-
"""صفحهٔ متدولوژی — داده، مدل، ارزیابی و محدودیت‌ها."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import components as ui
from .. import runtime
from ..config import ANNUAL_DEPRECIATION, district_factor, to_persian_digits
from ..labels import (FEATURE_LABELS, fa_code, fa_datetime, fa_number,
                      fa_price_short)
from ..photos import license_family


def render() -> None:
    ui.eyebrow("متدولوژی")
    ui.mark("<h1>این اعداد از کجا می‌آیند؟</h1>")
    ui.lead("شفافیت اینجا یک ادعا نیست: هر عدد این صفحه یا از کد تولید داده "
            "می‌آید و یا از اندازه‌گیری روی داده‌ای که مدل ندیده است.")

    ui.mark('<div style="height:.6rem"></div>')
    ui.mark(
        '<div class="kh-warn"><strong>داده سینتتیک است.</strong> هیچ رکوردی از '
        "آگهی واقعی گرفته نشده و قیمت‌ها قیمت واقعی بازار نیستند. هدف این پروژه "
        "نمایش یک سامانهٔ کامل هوش قیمت‌گذاری است — از تولید داده تا مدل، "
        "توضیح‌پذیری و رابط — و نه اعلام نرخ ملک.</div>"
    )

    metrics = runtime.metrics()
    insights = runtime.insights()

    ui.rule()
    ui.section("۱. داده", "چرا داده ساختگی و چگونه ساخته شده", eyebrow_text="داده")
    ui.mark(
        f'<p class="kh-lead">داده از یک مدل قیمت صریح تولید می‌شود؛ یعنی می‌دانیم '
        f"مدل باید چه چیزی را کشف کند:</p>"
    )
    ui.mark(
        '<pre style="direction:ltr;text-align:left;background:#FFFFFF;'
        'border:1px solid #E6DED1;border-radius:12px;padding:1rem;font-size:.82rem;'
        'overflow-x:auto">price_per_m2 = BASE × district_factor\n'
        '             × (1 + parking×0.07 + storage×0.02 + elevator×0.03\n'
        '                  + bedrooms×0.015)\n'
        '             × (1 − min(age, 35) × 0.012)\n'
        '             × floor_factor × noise(σ=0.08)\n'
        'price        = price_per_m2 × area</pre>'
    )
    districts = sorted({district_factor(code) for code in range(1, 23)})
    ui.kpi_row([
        ("رکورد آموزشی", fa_number(metrics["n_samples"]), "ردیف"),
        ("آگهی قابل مرور", fa_number(runtime.overview()["listings"]), "در کاتالوگ"),
        ("دامنهٔ ضریب منطقه", f"{fa_number(districts[0], decimals=2)} تا "
                             f"{fa_number(districts[-1], decimals=2)}",
         "ارزان‌ترین تا گران‌ترین"),
        ("استهلاک سالانه", f"{fa_number(ANNUAL_DEPRECIATION * 100, decimals=1)}٪",
         "تا سقف ۳۵ سال"),
    ])
    ui.muted("ضریب هر منطقه از ساختار واقعی بازار تهران الگو گرفته (شمال گران‌تر، "
             "حاشیهٔ جنوبی و غربی ارزان‌تر) اما خودِ ضریب‌ها ساختگی‌اند.")
    ui.muted("تولید داده با seed ثابت انجام می‌شود؛ اجرای دوباره دقیقاً همان "
             "دیتاست را می‌سازد، پس نتیجه‌ها و نمودارهای این صفحه تکرارپذیرند.")

    ui.rule()
    ui.section("۲. خط لوله", "از فایل خام تا عددی که کاربر می‌بیند",
               eyebrow_text="معماری")
    steps = pd.DataFrame([
        ("تولید داده", "مدل قیمت صریح، ۲۲ منطقه، نویز ۸٪"),
        ("پیش‌پردازش", "استانداردسازی ویژگی‌های عددی و رمزگذاری منطقه و امکانات"),
        ("آموزش", "سه مدل با پیچیدگی متفاوت روی یک تقسیم ۸۰/۲۰"),
        ("انتخاب", "برندهٔ آزمون با R²؛ سپس تثبیت با اعتبارسنجی متقابل"),
        ("بازه", "دو مدل چندکی ۱۰٪ و ۹۰٪ برای بازهٔ اطمینان"),
        ("کالیبراسیون", "تنظیم پهنای بازه تا پوشش واقعی به هدف برسد"),
        ("توضیح", "سهم هر ویژگی با میانگین‌گیری از چند ترتیب"),
        ("مقایسه", "یافتن آگهی‌های نزدیک در فضای متراژ، سن، اتاق و طبقه"),
    ], columns=["مرحله", "کار"])
    ui.fa_table(steps, use_container_width=True, hide_index=True)

    ui.rule()
    ui.section("۳. مدل و ارزیابی", "سنجه‌ها روی داده‌ای که مدل ندیده",
               eyebrow_text="ارزیابی")
    frame = pd.DataFrame([{
        "مدل": name,
        "R² آزمون": values["r2"],
        "MAPE٪": values["mape_pct"],
        "MAE (میلیارد تومان)": round(values["mae_toman"] / 1e9, 2),
        "R² اعتبارسنجی": values.get("cv_r2_mean", "—"),
        "انحراف اعتبارسنجی": values.get("cv_r2_std", "—"),
        "زمان آموزش (ثانیه)": values["fit_seconds"],
    } for name, values in metrics["results"].items()]).set_index("مدل")
    ui.fa_table(frame, use_container_width=True)
    ui.muted(
        f"اعتبارسنجی متقابل با {to_persian_digits(metrics['cv_folds'])} بخش فقط برای "
        "مدل برنده اجرا می‌شود. این کار تصمیم طراحی است: مقایسهٔ سه مدل روی یک "
        "تقسیم آزمون انجام می‌شود و اعتبارسنجی برای *تثبیت* برنده لازم است، نه "
        "برای هر سه؛ اجرای آن روی همه، بدون افزودن اطلاعات، زمان آموزش را چند "
        "برابر می‌کرد."
    )

    left, right = st.columns([1, 1])
    with left:
        ui.muted("اهمیت ویژگی‌ها (روش جایگشت)")
        ui.importance_chart(metrics["importance"], FEATURE_LABELS)
    with right:
        ui.muted("معیارهای بازهٔ اطمینان")
        ui.interval_summary(metrics["interval"])
        ui.mark('<div style="height:.5rem"></div>')
        ui.muted("مدل‌های چندکی روی داده محدود، بازهٔ باریک‌تری از وعده می‌دهند. "
                 "ضریب کالیبراسیون روی نیمهٔ نخست داده آزمون محاسبه می‌شود و پوشش "
                 "نهایی روی نیمهٔ دوم اندازه‌گیری می‌شود — نیمه‌ای که کالیبراسیون "
                 "آن را ندیده است.")

    ui.rule()
    ui.section("۴. توضیح‌پذیری", "«چرا این عدد؟» به زبان محاسبه",
               eyebrow_text="روش")
    ui.mark(
        '<p class="kh-lead">از یک «ملک مرجع» با میانهٔ مشخصات شهر شروع می‌کنیم و '
        "ویژگی‌ها را یکی‌یکی به مقدار ملک واقعی می‌بریم. هر گام، قیمت را جابه‌جا "
        "می‌کند و همان جابه‌جایی سهم آن ویژگی است.</p>"
    )
    ui.muted(
        "ترتیب برداشتن ویژگی‌ها روی نتیجه اثر دارد، پس چند ترتیب مختلف اجرا و سهم‌ها "
        f"میانگین گرفته می‌شود. مزیت این روش آن است که مجموع سهم‌ها دقیقاً برابر "
        "اختلاف قیمت با ملک مرجع می‌ماند و «باقی‌ماندهٔ توضیح‌داده‌نشده» باقی نمی‌ماند. "
        "روش مستقل از نوع مدل است و به ضرایب مدل خطی وابسته نیست."
    )

    ui.rule()
    ui.section("۵. محدودیت‌ها", "چیزهایی که این نسخه انجام نمی‌دهد",
               eyebrow_text="صداقت")
    limitations = [
        "داده واقعی نیست؛ نتیجهٔ مدل را نمی‌توان به‌عنوان نرخ بازار استناد کرد.",
        "ویژگی‌های مهم بازار — جهت نور، کیفیت ساخت، سند، دسترسی به مترو و "
        "قیمت‌های معاملات ثبت‌شده — در داده وجود ندارد.",
        "تورم و روند زمانی مدل نشده است؛ مدل یک مقطع از بازار را می‌بیند.",
        "عکس آگهی‌ها نمادین‌اند و عکس واقعی همان ملک نیستند.",
        "کاتالوگ نمونه است؛ همهٔ آگهی‌های بازار در آن نیست.",
    ]
    ui.mark("<ul style='line-height:2'>" + "".join(
        f"<li>{item}</li>" for item in limitations) + "</ul>")

    ui.rule()
    ui.section("۶. اعتبار تصاویر", "عکس‌های واقعی، مجوز آزاد",
               eyebrow_text="منابع")
    library = runtime.photos()
    if library.is_empty:
        ui.empty_state("فهرست عکس‌ها موجود نیست")
    else:
        table = pd.DataFrame([{
            "فایل": entry["file"],
            "موضوع": entry.get("title", ""),
            "مخزن": entry.get("provider", ""),
            "مجوز": str(entry.get("license", "")).upper(),
        } for entry in library.entries])
        ui.fa_table(table, use_container_width=True, hide_index=True)
        # متن از خود فهرست ساخته می‌شود، نه دست‌نویس: اگر روزی منبع یا مجوز
        # عکسی عوض شود، همین جمله هم خودکار درست می‌ماند.
        providers = {}
        for entry in library.entries:
            name = entry.get("provider", "—")
            providers[name] = providers.get(name, 0) + 1
        licenses = {}
        for entry in library.entries:
            family = license_family(entry.get("license"))
            licenses[family] = licenses.get(family, 0) + 1
        non_commercial = any("غیرتجاری" in name for name in licenses)
        ui.muted(
            f"{fa_number(library.total)} عکس ({fa_number(library.exteriors_count)} نما و "
            f"{fa_number(library.interiors_count)} فضای داخلی) از "
            + " و ".join(providers)
            + " برداشته شده‌اند. نام پدیدآورنده و مجوز هر عکس در جدول بالا و در "
            "فایل `CREDITS.md` همین پوشه ثبت شده است؛ استفاده از آن‌ها با ذکر "
            "منبع انجام می‌شود."
        )
        ui.badges([f"مجوز {name}: {fa_number(count)} عکس"
                   for name, count in licenses.items()], "kh-badge-bronze")
        if non_commercial:
            ui.muted("برخی عکس‌ها مجوز غیرتجاری دارند و برای استفادهٔ تجاری باید "
                     "جایگزین شوند.")

    ui.rule(tight=True)
    ui.muted(
        f"آخرین آموزش: {fa_datetime(insights['trained_at'])} · نسخهٔ بستهٔ مدل: "
        f"{fa_code(runtime.bundle().get('version', 1))} · خطای معیار باقی‌مانده: "
        f"{fa_price_short(insights['residual_std_toman'] or 0)} تومان"
    )
