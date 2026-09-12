# -*- coding: utf-8 -*-
"""تحلیل بازار — همهٔ اعداد از کاتالوگ آگهی‌ها محاسبه می‌شوند.

قاعدهٔ این ماژول ساده است: هیچ عدد تزئینی ساخته نمی‌شود. هر نمودار و هر
شاخص از یک تجمیع واقعی روی ``listings_frame()`` یا از فایل معیارهای مدل
می‌آید. اگر داده برای بازه‌ای کافی نباشد، تابع مقدار خالی برمی‌گرداند و رابط
همان را نشان می‌دهد — نه یک نمودار پر از صفر.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BEDROOM_RANGE, LUXURY_AREA_THRESHOLD, to_persian_digits
from .labels import district_name
from .listings import listings_frame

#: سطل‌های قیمت برای نمودار توزیع (میلیارد تومان).
DISTRIBUTION_BINS = 24
AREA_BUCKETS = ((0, 70), (70, 100), (100, 130), (130, 180), (180, 250), (250, 10_000))
AREA_BUCKET_LABELS = ("زیر ۷۰", "۷۰ تا ۱۰۰", "۱۰۰ تا ۱۳۰", "۱۳۰ تا ۱۸۰",
                      "۱۸۰ تا ۲۵۰", "بالای ۲۵۰")


def district_stats() -> pd.DataFrame:
    """شاخص‌های هر منطقه — تعداد، میانهٔ قیمت، میانهٔ قیمت متر، سهم لوکس."""
    frame = listings_frame()
    grouped = frame.groupby("district")
    stats = pd.DataFrame({
        "listings": grouped.size(),
        "median_price": grouped["price"].median(),
        "median_price_m2": grouped["price_per_m2"].median(),
        "mean_area": grouped["area"].mean(),
        "mean_age": grouped["age"].mean(),
    }).reset_index()
    luxury = (frame.assign(luxury=frame["area"] >= LUXURY_AREA_THRESHOLD)
              .groupby("district")["luxury"].mean().rename("luxury_share"))
    stats = stats.merge(luxury, on="district", how="left")
    stats["district_name"] = stats["district"].map(district_name)
    stats["short_name"] = stats["district"].map(lambda code: f"منطقه {to_persian_digits(int(code))}")
    return stats.sort_values("median_price_m2", ascending=False).reset_index(drop=True)


def price_distribution(bins: int = DISTRIBUTION_BINS) -> pd.DataFrame:
    """توزیع قیمت آگهی‌ها (میلیارد تومان) در سطل‌های مساوی."""
    frame = listings_frame()
    if frame.empty:
        return pd.DataFrame({"center": [], "count": []})
    billions = frame["price"] / 1_000_000_000
    counts, edges = np.histogram(billions, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return pd.DataFrame({"center": centers, "count": counts})


def price_per_m2_distribution(bins: int = DISTRIBUTION_BINS) -> pd.DataFrame:
    """توزیع قیمت هر مترمربع (میلیون تومان)."""
    frame = listings_frame()
    if frame.empty:
        return pd.DataFrame({"center": [], "count": []})
    millions = frame["price_per_m2"] / 1_000_000
    counts, edges = np.histogram(millions, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return pd.DataFrame({"center": centers, "count": counts})


def area_bucket_stats() -> pd.DataFrame:
    """میانهٔ قیمت مترمربع در سطل‌های متراژ — رابطهٔ متراژ و قیمت."""
    frame = listings_frame()
    rows = []
    for (low, high), label in zip(AREA_BUCKETS, AREA_BUCKET_LABELS):
        chunk = frame[(frame["area"] >= low) & (frame["area"] < high)]
        rows.append({
            "bucket": label,
            "count": int(len(chunk)),
            "median_price_m2": float(chunk["price_per_m2"].median()) if len(chunk) else 0.0,
            "median_price": float(chunk["price"].median()) if len(chunk) else 0.0,
        })
    return pd.DataFrame(rows)


def bedroom_stats() -> pd.DataFrame:
    """میانهٔ قیمت به تفکیک تعداد اتاق."""
    frame = listings_frame()
    rows = []
    for count in range(BEDROOM_RANGE[0], BEDROOM_RANGE[1] + 1):
        chunk = frame[frame["bedrooms"] == count]
        if chunk.empty:
            continue
        rows.append({
            "bedrooms": count,
            "count": int(len(chunk)),
            "median_price": float(chunk["price"].median()),
            "median_area": float(chunk["area"].median()),
        })
    return pd.DataFrame(rows)


def market_overview() -> dict:
    """شاخص‌های سرصفحهٔ داشبورد."""
    frame = listings_frame()
    if frame.empty:
        return {"listings": 0, "median_price": 0, "median_price_m2": 0,
                "mean_area": 0.0, "luxury_share": 0.0, "median_age": 0.0}
    return {
        "listings": int(len(frame)),
        "median_price": int(frame["price"].median()),
        "median_price_m2": int(frame["price_per_m2"].median()),
        "mean_area": float(frame["area"].mean()),
        "luxury_share": float((frame["area"] >= LUXURY_AREA_THRESHOLD).mean()),
        "median_age": float(frame["age"].median()),
    }


def movers(top: int = 5) -> dict[str, pd.DataFrame]:
    """گران‌ترین و ارزان‌ترین مناطق بر پایهٔ میانهٔ قیمت مترمربع."""
    stats = district_stats()
    if stats.empty:
        empty = pd.DataFrame()
        return {"expensive": empty, "affordable": empty}
    columns = ["district", "short_name", "median_price_m2", "median_price", "listings"]
    return {
        "expensive": stats.head(top)[columns].reset_index(drop=True),
        "affordable": stats.tail(top)[columns].iloc[::-1].reset_index(drop=True),
    }


def model_insights(metrics: dict) -> dict:
    """خلاصهٔ قابل نمایش معیارهای مدل."""
    results = metrics.get("results", {})
    best = metrics.get("best_model", "")
    best_metrics = results.get(best, {})
    return {
        "best_model": best,
        "r2": best_metrics.get("r2"),
        "mape_pct": best_metrics.get("mape_pct"),
        "mae_toman": best_metrics.get("mae_toman"),
        "cv_r2_mean": best_metrics.get("cv_r2_mean"),
        "cv_r2_std": best_metrics.get("cv_r2_std"),
        "cv_mae_toman": best_metrics.get("cv_mae_toman"),
        "n_samples": metrics.get("n_samples"),
        "cv_folds": metrics.get("cv_folds"),
        "trained_at": metrics.get("trained_at"),
        "importance": metrics.get("importance", []),
        "interval": metrics.get("interval", {}),
        "residual_std_toman": metrics.get("residual_std_toman"),
    }
