# -*- coding: utf-8 -*-
"""زمینهٔ پردازش — چرخهٔ عمر یک بستهٔ داده از بارگذاری تا گزارش.

هر بستهٔ پردازش پنج گام دارد و هر گام خروجی خودش را روی دیسک می‌گذارد:

    upload → inspect → clean → analyze → report

**چرا روی دیسک و نه در حافظه؟** سرور با چند کارگر اجرا می‌شود و هر کارگر
حافظهٔ خودش را دارد. اگر نتیجه در حافظهٔ یک کارگر بماند، درخواست بعدی که به
کارگر دیگری برسد «پیدا نشد» می‌دهد.

**چرا گام‌ها از هم جدا هستند؟** چون محصول می‌خواهد کاربر *ببیند* بین بارگذاری
و گزارش چه اتفاقی می‌افتد: پروفایل، مسائل، اصلاحات. اگر همه در یک درخواست
انجام شود، کاربر به گزارش نهایی پرت می‌شود و نمی‌فهمد چه چیزی عوض شده.

جدول خام پس از گام ``inspect`` روی دیسک ذخیره می‌شود تا کاربر بتواند گزینه‌های
پاک‌سازی را عوض کند و دوباره اجرا کند، بدون بارگذاری دوبارهٔ فایل.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from dataclasses import dataclass

from ..analytics import Analysis, analyse
from ..cleaning import CleanOptions, CleanResult, clean, detect
from ..config import MAX_UPLOAD_BYTES, theme as theme_of
from ..errors import DatasetNotFoundError, EmptyFileError, ReportSazError
from ..ingest import inspect_upload, read_table, validate_content
from ..profile import Profile, profile_frame
from ..report import meta_payload
from ..store import (FRAME_CLEAN, FRAME_RAW, drop_frame, exists, load_frame,
                     load_meta, new_id, patch_meta, remove, save_frame,
                     save_meta, save_source, source_path, touch, validate_id)

#: گام‌های پردازش، به ترتیب.
STAGE_UPLOADED = "uploaded"
STAGE_INSPECTED = "inspected"
STAGE_CLEANED = "cleaned"
STAGE_ANALYSED = "analysed"

STAGES = [
    {"key": STAGE_UPLOADED, "label": "بارگذاری", "icon": "۱"},
    {"key": STAGE_INSPECTED, "label": "بازرسی", "icon": "۲"},
    {"key": STAGE_CLEANED, "label": "پاک‌سازی", "icon": "۳"},
    {"key": STAGE_ANALYSED, "label": "تحلیل", "icon": "۴"},
    {"key": "reported", "label": "گزارش", "icon": "۵"},
]


def json_safe(value):
    """تبدیل بازگشتی به JSON سالم.

    ``json.dump`` مقدار ``NaN`` را می‌نویسد که JSON معتبر نیست و مرورگر ردش
    می‌کند. هر ``NaN`` و بی‌نهایت به ``None`` تبدیل می‌شود — «مقدار نامعلوم»
    صادقانه‌تر از عدد نامعتبر است.
    """
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return json_safe(value.item())
        except (ValueError, AttributeError):
            return str(value)
    return value


@dataclass
class Bundle:
    """بستهٔ پردازش — پوشش نازک روی دیسک، با دسترسی نوع‌دار."""

    dataset_id: str

    # ---------------------------------------------------------- خواندن
    def exists(self) -> bool:
        return exists(self.dataset_id)

    @property
    def meta(self) -> dict:
        return load_meta(self.dataset_id)

    def touch(self) -> None:
        touch(self.dataset_id)

    def stage(self) -> str:
        return self.meta.get("stage", STAGE_UPLOADED)

    def reached(self, stage: str) -> bool:
        order = [item["key"] for item in STAGES]
        try:
            return order.index(self.stage()) >= order.index(stage)
        except ValueError:
            return False

    # ---------------------------------------------------------- داده
    def raw_frame(self):
        """جدول خام خوانده‌شده از فایل — همان چیزی که بازرسی رویش انجام شد."""
        return load_frame(self.dataset_id, FRAME_RAW)

    def working_frame(self):
        """جدول جاری — پاک‌شده اگر پاک‌سازی اجرا شده باشد، وگرنه خام."""
        if self.reached(STAGE_CLEANED):
            frame = load_frame(self.dataset_id, FRAME_CLEAN)
            if frame is not None:
                return frame
        return self.raw_frame()


    def profile(self) -> Profile | None:
        payload = self.meta.get("profile")
        return _profile_from_dict(payload) if payload else None

    def clean_result(self) -> CleanResult | None:
        payload = self.meta.get("cleaning")
        if not payload:
            return None
        frame = self.working_frame()
        return _clean_from_dict(payload, frame)

    def analysis(self) -> Analysis | None:
        payload = self.meta.get("analysis")
        return _analysis_from_dict(payload) if payload else None


# ------------------------------------------------------------------ گام‌ها
def create_bundle(file_storage) -> Bundle:
    """گام بارگذاری — ذخیرهٔ امن فایل و ثبت فراداده.

    ترتیب بررسی‌ها عمدی است: ارزان‌ترین سد اول. نام و حجم پیش از خواندن فایل،
    امضای بایتی پیش از خواندن جدول.
    """
    dataset_id = new_id()
    info = inspect_upload(getattr(file_storage, "filename", None),
                          getattr(file_storage, "mimetype", None), None)

    #: حجم واقعی از خود جریان خوانده می‌شود، نه از سرآمد درخواست که قابل
    #: دست‌کاری است.
    stream = file_storage.stream
    position = stream.tell() if hasattr(stream, "tell") else 0
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(position)
    if size > MAX_UPLOAD_BYTES:
        raise ReportSazError(
            f"حجم فایل بیش از حد مجاز است. سقف مجاز "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} مگابایت است.")
    if size == 0:
        raise EmptyFileError("فایل خالی است و داده‌ای برای تحلیل ندارد.")

    path, written, _truncated = save_source(dataset_id, stream,
                                            info["extension"], MAX_UPLOAD_BYTES)
    warnings = list(info["warnings"])
    warnings.extend(validate_content(path, info["extension"]))

    save_meta(dataset_id, {
        "stage": STAGE_UPLOADED,
        "display_name": info["display_name"],
        "extension": info["extension"],
        "size_bytes": written,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "warnings": warnings,
        "files": {"source": f"source.{info['extension']}"},
    })
    return Bundle(dataset_id)


def run_inspect(bundle: Bundle) -> dict:
    """گام بازرسی — خواندن جدول، پروفایل و ثبت مسائل پیش از پاک‌سازی."""
    meta = bundle.meta
    warnings: list[str] = []
    result = read_table(source_path(bundle.dataset_id), meta["extension"], warnings)
    save_frame(bundle.dataset_id, result.frame)
    profile = profile_frame(result.frame)
    findings = detect(result.frame)

    patch = {
        "stage": STAGE_INSPECTED,
        "read": result.summary(),
        "profile": json_safe(profile.as_dict()),
        "findings": [item.as_dict() for item in findings],
        "files": {"source": meta["files"]["source"], "frame_raw": True},
        #: گام‌های بعدی با بارگذاری دوباره باطل می‌شوند.
        "cleaning": None,
        "analysis": None,
    }
    patch_meta(bundle.dataset_id, **patch)
    drop_frame(bundle.dataset_id, FRAME_CLEAN)
    return {"profile": profile, "read": result.summary(), "findings": findings}


def run_clean(bundle: Bundle, options: CleanOptions) -> CleanResult:
    """گام پاک‌سازی — از جدول خام، با گزینه‌های انتخابی کاربر."""
    if not bundle.reached(STAGE_INSPECTED):
        run_inspect(bundle)
    raw = bundle.raw_frame()
    if raw is None:
        raise EmptyFileError(
            "جدول خوانده‌شده در دسترس نیست؛ فایل را دوباره بارگذاری کنید.")
    result = clean(raw, options)
    _save_working_frame(bundle, result.frame, "clean")
    profile = profile_frame(result.frame)
    patch_meta(
        bundle.dataset_id,
        stage=STAGE_CLEANED,
        cleaning=json_safe({**result.as_dict(), "options": options.as_dict()}),
        profile=json_safe(profile.as_dict()),
        findings=[item.as_dict() for item in result.findings],
        analysis=None,
        theme=_current_theme(bundle),
    )
    return result


def run_analyze(bundle: Bundle, *, metric: str = "", dimension: str = "",
                date_column: str = "") -> Analysis:
    """گام تحلیل — شاخص، بینش، روند و ناهنجاری روی جدول جاری."""
    frame = bundle.working_frame()
    profile = bundle.profile()
    if frame is None or profile is None:
        raise DatasetNotFoundError(
            "برای تحلیل، ابتدا فایل باید بارگذاری و بازرسی شود.")
    analysis = analyse(frame, profile, metric or None, dimension or None,
                       date_column or None)
    patch_meta(bundle.dataset_id, stage=STAGE_ANALYSED,
               analysis=json_safe(analysis.as_dict()),
               selection={"metric": metric, "dimension": dimension,
                          "date": date_column})
    return analysis


def set_theme(bundle: Bundle, name: str) -> None:
    """ثبت تم انتخابی کاربر."""
    patch_meta(bundle.dataset_id, theme=name)


def report_meta(bundle: Bundle) -> dict:
    """فرادادهٔ گزارش — از فرادادهٔ بسته ساخته می‌شود."""
    meta = bundle.meta
    return meta_payload(
        display_name=meta.get("display_name", "—"),
        size_bytes=meta.get("size_bytes", 0),
        extension=meta.get("extension", ""),
        processed_at=meta.get("created_at", ""),
        theme_name=_current_theme(bundle),
        sheet=(meta.get("read") or {}).get("sheet", ""),
        encoding=(meta.get("read") or {}).get("encoding", ""),
        separator=(meta.get("read") or {}).get("separator", ""),
        skipped_rows=(meta.get("read") or {}).get("skipped_rows", 0),
        truncated=bool((meta.get("read") or {}).get("truncated")),
    )


def _current_theme(bundle: Bundle) -> str:
    return (bundle.meta.get("theme") or "corporate")


def _save_working_frame(bundle: Bundle, frame, kind: str) -> None:
    """ذخیرهٔ جدول جاری زیر نام خودش.

    جدول خام دست‌نخورده می‌ماند تا گزینه‌های پاک‌سازی قابل تغییر بمانند.
    """
    from ..store import create

    create(bundle.dataset_id)
    save_frame(bundle.dataset_id, frame,
               FRAME_CLEAN if kind == "clean" else FRAME_RAW)


def open_bundle(dataset_id: str | None) -> Bundle:
    """باز کردن بسته با اعتبارسنجی شناسه."""
    bundle = Bundle(validate_id(dataset_id))
    if not bundle.exists():
        raise DatasetNotFoundError(
            "این بستهٔ پردازش پیدا نشد یا منقضی شده است.")
    return bundle


def purge(dataset_id: str) -> None:
    remove(dataset_id)


# ------------------------------------------------------------------ بازسازی
def _profile_from_dict(payload: dict) -> Profile:
    """ساخت دوبارهٔ پروفایل از JSON — بدون دست‌زدن به داده."""
    from ..profile import ColumnProfile

    columns = []
    for item in payload.get("columns_profile", []):
        columns.append(ColumnProfile(
            name=item.get("name", ""), position=int(item.get("position", 0)),
            dtype=item.get("dtype", ""), type=item.get("type", "text"),
            role=item.get("role", "text"), missing=int(item.get("missing", 0)),
            unique=int(item.get("unique", 0)), filled=int(item.get("filled", 0)),
            validity=float(item.get("validity", 1.0)),
            minimum=item.get("min"), maximum=item.get("max"),
            mean=item.get("mean"), median=item.get("median"),
            std=item.get("std"), total=item.get("total"),
            top_value=item.get("top_value", ""),
            top_share=float(item.get("top_share", 0.0)),
            date_min=item.get("date_min", ""), date_max=item.get("date_max", ""),
            suspicious=list(item.get("suspicious", [])),
            formats=int(item.get("formats", 1)),
        ))
    return Profile(
        rows=int(payload.get("rows", 0)), columns=int(payload.get("columns", 0)),
        cells=int(payload.get("cells", 0)), missing=int(payload.get("missing", 0)),
        duplicates=int(payload.get("duplicates", 0)),
        columns_profile=columns, quality=dict(payload.get("quality", {})),
        suspicious_total=int(payload.get("suspicious_total", 0)),
        notes=list(payload.get("notes", [])),
    )


def _clean_from_dict(payload: dict, frame) -> CleanResult:
    from ..cleaning import Finding, Fix

    if frame is None:
        import pandas as pd

        frame = pd.DataFrame()
    return CleanResult(
        frame=frame,
        findings=[Finding(**item) for item in payload.get("findings", [])],
        fixes=[Fix(**item) for item in payload.get("fixes", [])],
        rows_before=int(payload.get("rows_before", 0)),
        rows_after=int(payload.get("rows_after", 0)),
        columns_before=int(payload.get("columns_before", 0)),
        columns_after=int(payload.get("columns_after", 0)),
    )


def _analysis_from_dict(payload: dict) -> Analysis:
    from ..analytics import Anomaly, Breakdown, Insight, Kpi, Point, Series

    analysis = Analysis(
        primary_metric=payload.get("primary_metric", ""),
        primary_dimension=payload.get("primary_dimension", ""),
        date_column=payload.get("date_column", ""),
        notes=list(payload.get("notes", [])),
        correlation=dict(payload.get("correlation", {})),
    )
    analysis.kpis = [Kpi(**item) for item in payload.get("kpis", [])]
    analysis.insights = [Insight(**item) for item in payload.get("insights", [])]
    for item in payload.get("series", []):
        series = Series(key=item.get("key", ""), title=item.get("title", ""),
                        kind=item.get("kind", "bar"), unit=item.get("unit", ""),
                        empty_reason=item.get("empty_reason", ""))
        series.points = [Point(**point) for point in item.get("points", [])]
        analysis.series.append(series)
    for item in payload.get("breakdowns", []):
        breakdown = Breakdown(dimension=item.get("dimension", ""),
                              metric=item.get("metric", ""),
                              total=float(item.get("total", 0.0)),
                              dropped=int(item.get("dropped", 0)))
        breakdown.rows = list(item.get("rows", []))
        analysis.breakdowns.append(breakdown)
    analysis.anomalies = [Anomaly(**item) for item in payload.get("anomalies", [])]
    return analysis


def theme_name(bundle: Bundle) -> str:
    """نام تم جاری بسته — با اعتبارسنجی."""
    return _current_theme(bundle)


def theme_palette(bundle: Bundle) -> dict:
    return theme_of(_current_theme(bundle))
