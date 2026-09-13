# -*- coding: utf-8 -*-
"""تبدیل دادهٔ دامنه به شکل قابل نمایش.

قالب‌ها نباید بدانند عکس کارت ۶۴۰ پیکسل است یا ۱۵۰۰، و نباید «قیمت متر»
را دو جا متفاوت قالب‌بندی کنند. این ماژول همان یک جایی است که این تصمیم‌ها
گرفته می‌شوند؛ هر قالبی که کارت ملک می‌خواهد، ``card_view`` صدا می‌زند.

این تفکیک یک فایدهٔ جانبی مهم دارد: اگر ساختار کارت عوض شود، فقط یک تابع
تغییر می‌کند و پنج قالب با هم درست می‌مانند.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import charts
from ..config import to_persian_digits
from ..labels import (bedrooms_label, district_name, fa_number, fa_percent,
                      fa_price, fa_price_short, floor_label)
from ..listings import Listing
from ..photos import license_family, sized

if TYPE_CHECKING:                      # فقط راهنمای نوع؛ sklearn را نمی‌کشد
    from ..explain import Explanation


def card_view(item: Listing, *, tag: str | None = None,
              comparing: bool = False, saved: bool = False) -> dict:
    """اطلاعات یک کارت ملک."""
    cover = item.cover
    return {
        "id": item.id,
        "url": f"/listing/{item.id}",
        "title": item.title,
        "district": item.district_label,
        "bedrooms": item.bedrooms_label,
        "floor": item.floor_label,
        "area": f"{fa_number(item.area)} متر",
        "age": f"{fa_number(item.age)} سال",
        "type": item.property_type,
        "price": fa_price_short(item.price),
        "price_full": fa_price(item.price),
        "price_per_m2": f"{fa_number(item.price_per_m2)} تومان",
        "amenities": list(item.amenities),
        "tag": tag,
        "image": sized(cover, "card") if cover else None,
        "is_luxury": item.is_luxury,
        "comparing": comparing,
        "saved": saved,
    }


def hero_view(name: str | None) -> dict | None:
    """تصویر بنر صفحهٔ خانه — نسخهٔ بزرگ با نامزدهای اندازه."""
    return sized(name, "hero") if name else None


def card_thumb(name: str | None) -> dict | None:
    """بندانگشتی یک عکس — برای جدول اعتبار تصاویر.

    از نسخهٔ ``tiny`` استفاده می‌شود: این جدول ۲۹ ردیف دارد و با نسخهٔ کارتی
    تنها عکس‌هایش یک مگابایت می‌شد، برای تصویری که در ۹۶ پیکسل دیده می‌شود.
    """
    from ..photos import TINY_VARIANT

    return sized(name, TINY_VARIANT) if name else None


def gallery_view(item: Listing) -> dict:
    """نمای گالری صفحهٔ ملک — یک تصویر اصلی و دو تصویر کناری."""
    names = [name for name in item.gallery if name]
    if not names:
        return {"main": None, "sides": []}
    return {
        "main": sized(names[0], "hero"),
        "sides": [sized(name, "card") for name in names[1:3]],
    }


def specs_view(item: Listing) -> list[tuple[str, str]]:
    """جدول مشخصات — ترتیب ثابت و از بالا به پایین مهم‌ترین."""
    return [
        ("منطقه", item.district_label),
        ("متراژ", f"{fa_number(item.area)} مترمربع"),
        ("اتاق خواب", item.bedrooms_label),
        ("سن بنا", f"{fa_number(item.age)} سال"),
        ("طبقه", item.floor_label),
        ("نوع ملک", item.property_type),
        ("قیمت هر متر", f"{fa_number(item.price_per_m2)} تومان"),
        ("تاریخ انتشار", f"{fa_number(item.days_ago)} روز پیش"),
        ("پارکینگ", "دارد" if item.parking else "ندارد"),
        ("انباری", "دارد" if item.storage else "ندارد"),
        ("آسانسور", "دارد" if item.elevator else "ندارد"),
    ]


def factor_view(explanation: "Explanation", *, limit: int = 8) -> list[dict]:
    """سهم ویژگی‌ها با عرض نوار آماده — محاسبهٔ عرض در قالب معنا ندارد."""
    factors = explanation.factors[:limit]
    if not factors:
        return []
    largest = max(abs(item.amount) for item in factors) or 1
    views = []
    for item in factors:
        width = max(2.0, abs(item.amount) / largest * 100)
        views.append({
            "label": item.label,
            "value": item.value_label,
            "amount": fa_price_short(abs(item.amount)),
            "signed": "+" if item.amount >= 0 else "−",
            "direction": "up" if item.amount >= 0 else "down",
            "width": round(width, 1),
        })
    return views


def estimate_view(explanation: "Explanation", summary: str) -> dict:
    """بلوک نتیجهٔ برآورد — همان چیزی که API هم برمی‌گرداند."""
    return {
        "price": explanation.price,
        "price_text": fa_number(explanation.price),
        "price_short": fa_price_short(explanation.price),
        "price_per_m2": fa_number(explanation.price_per_m2),
        "low": explanation.low,
        "low_short": fa_price_short(explanation.low),
        "high": explanation.high,
        "high_short": fa_price_short(explanation.high),
        "half_width_pct": fa_number(explanation.relative_width * 50, decimals=1),
        "base_price": explanation.base_price,
        "base_short": fa_price_short(explanation.base_price),
        "delta_short": fa_price_short(explanation.price - explanation.base_price),
        "residual": explanation.residual,
        "summary": summary,
        "factors": factor_view(explanation),
        "comparable_count": explanation.comparables.count,
        "comparable_median": explanation.comparables.median_price,
        "comparable_median_short": fa_price_short(explanation.comparables.median_price),
        "comparable_median_m2": fa_number(explanation.comparables.median_price_per_m2),
        "gap": explanation.comparable_gap(),
        "gap_text": (fa_percent(abs(explanation.comparable_gap()), signed=True)
                     if explanation.comparable_gap() is not None else "—"),
        "standing": ("بالاتر" if (explanation.comparable_gap() or 0) > 0 else "پایین‌تر"),
    }


def district_chart(limit: int = 10) -> str:
    """نمودار میله‌ای افقی میانهٔ قیمت متر — از دادهٔ واقعی تحلیل بازار."""
    from .. import services

    frame = services.districts().head(limit)
    bars = [
        charts.Bar(
            label=str(row["district_name"]),
            value=float(row["median_price_m2"]) / 1e6,
            hint=f"{row['district_name']} — میانهٔ {fa_number(row['median_price_m2'] / 1e6)} "
                 f"میلیون تومان در مترمربع ({fa_number(row['listings'])} آگهی)",
            display=f"{fa_number(row['median_price_m2'] / 1e6)}",
        )
        for _, row in frame.iterrows()
    ]
    return charts.horizontal_bars(
        bars, unit=" م", title="میانهٔ قیمت هر مترمربع به تفکیک منطقه")


def movers_charts(top: int = 6) -> tuple[str, str]:
    """دو نمودار گران‌ترین و ارزان‌ترین مناطق."""
    from .. import services

    data = services.market_movers()
    expensive = charts.horizontal_bars(
        [charts.Bar(
            label=str(row["short_name"]),
            value=float(row["median_price_m2"]) / 1e6,
            hint=f"{district_name(int(row['district']))} — "
                 f"{fa_number(row['median_price_m2'] / 1e6)} میلیون در متر",
            display=fa_number(row["median_price_m2"] / 1e6),
        ) for _, row in data["expensive"].head(top).iterrows()],
        unit=" م", color="var(--chart-1)", title="گران‌ترین مناطق")
    affordable = charts.horizontal_bars(
        [charts.Bar(
            label=str(row["short_name"]),
            value=float(row["median_price_m2"]) / 1e6,
            hint=f"{district_name(int(row['district']))} — "
                 f"{fa_number(row['median_price_m2'] / 1e6)} میلیون در متر",
            display=fa_number(row["median_price_m2"] / 1e6),
        ) for _, row in data["affordable"].head(top).iterrows()],
        unit=" م", color="var(--chart-2)", title="ارزان‌ترین مناطق")
    return expensive, affordable


def distribution_chart() -> str:
    """توزیع قیمت آگهی‌ها بر پایهٔ هیستوگرام واقعی کاتالوگ."""
    from .. import services

    frame = services.distribution()
    points = [(float(row["center"]), int(row["count"])) for _, row in frame.iterrows()]
    return charts.histogram(
        points, unit=" م", x_decimals=0, label_every=6,
        title="توزیع قیمت آگهی‌ها (میلیارد تومان)")


def per_m2_chart() -> str:
    """توزیع قیمت هر مترمربع."""
    from .. import services

    frame = services.per_m2_distribution()
    points = [(float(row["center"]), int(row["count"])) for _, row in frame.iterrows()]
    return charts.histogram(
        points, unit=" م", x_decimals=0, label_every=6,
        color="var(--chart-3)",
        title="توزیع قیمت هر مترمربع (میلیون تومان)")


def area_chart() -> str:
    """میانهٔ قیمت مترمربع در سطل‌های متراژ."""
    from .. import services

    frame = services.area_buckets()
    return charts.columns(
        [charts.Bar(
            label=str(row["bucket"]),
            value=float(row["median_price_m2"]) / 1e6,
            hint=f"{row['bucket']} متر — میانهٔ "
                 f"{fa_number(row['median_price_m2'] / 1e6)} میلیون در متر "
                 f"({fa_number(row['count'])} آگهی)",
            display=fa_number(row["median_price_m2"] / 1e6),
        ) for _, row in frame.iterrows()],
        unit=" م", title="میانهٔ قیمت هر مترمربع به تفکیک متراژ")


def bedrooms_chart() -> str:
    """میانهٔ قیمت ملک به تفکیک تعداد اتاق."""
    from .. import services

    frame = services.bedrooms()
    return charts.columns(
        [charts.Bar(
            label=f"{to_persian_digits(int(row['bedrooms']))} اتاق",
            value=float(row["median_price"]) / 1e9,
            hint=f"{bedrooms_label(int(row['bedrooms']))} — میانهٔ "
                 f"{fa_number(row['median_price'] / 1e9, decimals=2)} میلیارد "
                 f"({fa_number(row['count'])} آگهی)",
            display=fa_number(row["median_price"] / 1e9, decimals=1),
        ) for _, row in frame.iterrows()],
        unit=" میلیارد", decimals=1, title="میانهٔ قیمت به تفکیک تعداد اتاق")


def importance_chart(limit: int = 8) -> str:
    """اهمیت ویژگی‌ها در مدل — از معیارهای واقعی آموزش."""
    from .. import services

    from ..labels import FEATURE_LABELS

    importance = services.insights().get("importance", [])[:limit]
    return charts.horizontal_bars(
        [charts.Bar(
            label=FEATURE_LABELS.get(item["feature"], item["feature"]),
            value=float(item["importance"]) * 100,
            hint=f"{FEATURE_LABELS.get(item['feature'], item['feature'])}: "
                 f"{fa_number(item['importance'] * 100, decimals=1)}٪",
            display=f"{fa_number(item['importance'] * 100, decimals=1)}٪",
        ) for item in importance],
        unit="٪", decimals=0, color="var(--chart-4)",
        title="سهم هر ویژگی در تصمیم مدل (جایگشت روی دادهٔ آزمون)",
    )


def interval_chart() -> str:
    """پوشش اندازه‌گیری‌شدهٔ بازه در برابر هدف — نسبت واقعی، نه ادعا."""
    from .. import services

    interval = services.insights().get("interval", {})
    if not interval:
        return ""
    measured = float(interval.get("measured_coverage_pct", 0))
    target = float(interval.get("target_coverage_pct", 0)) or 1.0
    return charts.stacked_share(
        [
            ("پوشش اندازه‌گیری‌شده", measured, "var(--chart-1)"),
            ("کمبود تا هدف", max(0.0, target - measured), "var(--chart-soft)"),
        ],
        title="پوشش بازهٔ اطمینان در برابر هدف",
    )


def compare_chart(items: list[Listing], prices: list[int]) -> tuple[str, str]:
    """دو نمودار مقایسه: قیمت هر متر، و قیمت آگهی در برابر برآورد.

    شناسهٔ ملک در محور نمودار با رقم فارسی نوشته می‌شود؛ حروف شناسه لاتین
    می‌مانند (کد کالا در همهٔ فروشگاه‌ها لاتین است) ولی رقم لاتین در یک رابط
    فارسی ناهمخوان است.
    """
    def shown(identifier: str) -> str:
        return to_persian_digits(identifier)

    meters = charts.columns(
        [charts.Bar(
            label=shown(item.id), value=item.price_per_m2 / 1e6,
            hint=f"{shown(item.id)} — {fa_number(item.price_per_m2 / 1e6)} میلیون در متر",
            display="",
        ) for item in items],
        unit=" م", decimals=0, title="قیمت هر مترمربع")
    grouped = charts.grouped_bars(
        [shown(item.id) for item in items],
        [
            ("قیمت آگهی", [item.price / 1e9 for item in items], "var(--chart-soft)"),
            ("ارزش برآوردی", [value / 1e9 for value in prices], "var(--chart-1)"),
        ],
        unit=" میلیارد", decimals=1, title="قیمت آگهی در برابر ارزش برآوردی")
    return meters, grouped


def credit_note(item: Listing) -> dict | None:
    """اعتبار عکس صفحهٔ ملک — اگر ثبت شده باشد."""
    from .. import services

    credit = services.photos().credit(item.cover)
    if not credit:
        return None
    return {
        "provider": credit.get("provider", ""),
        "license": license_family(credit.get("license")),
        "author": credit.get("author", ""),
        "page": credit.get("page", ""),
    }
