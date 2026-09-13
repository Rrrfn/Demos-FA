# -*- coding: utf-8 -*-
"""موتور تحلیل — از جدول پاک‌شده تا شاخص، بینش، روند و ناهنجاری.

قاعدهٔ سخت این ماژول: **هیچ عددی ساخته نمی‌شود.** هر کارت شاخص، هر بینش و هر
ناهنجاری یک ``evidence`` دارد که همان اعدادی را نگه می‌دارد که در متن آمده‌اند.
اگر دادهٔ لازم نباشد، آن بخش *خالی می‌ماند* و دلیلش گفته می‌شود — نه این‌که با
مقدار ساختگی پر شود. مثلاً اگر جدول ستون تاریخ نداشته باشد، «رشد دوره» تولید
نمی‌شود و همین در بخش یادداشت‌ها می‌آید.

نقش ستون‌ها از لایهٔ پروفایل می‌آید: متریک، بعد، تاریخ، شناسه. تحلیل روی
همان نقش‌ها بسته می‌شود، پس ستون «کد سفارش» هرگز به‌عنوان مبلغ جمع نمی‌شود.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import asdict, dataclass, field

import pandas as pd

from .config import TREND_MIN_POINTS
from .labels import fa_compact, fa_number, fa_percent
from .profile import (Profile, ROLE_DIMENSION, ROLE_METRIC, pick_dimensions,
                      pick_metrics)

#: روش‌های تشخیص ناهنجاری که در رابط اعلام می‌شوند.
METHOD_IQR = "IQR"
METHOD_Z = "Z-score"

#: آستانهٔ Z برای علامت‌گذاری.
Z_LIMIT = 3.0
#: کمترین تعداد نمونهٔ لازم برای معنا داشتن IQR یا Z.
MIN_SAMPLES = 8


@dataclass
class Kpi:
    """کارت شاخص — یک عدد، یک برچسب، و مسیر رسیدن به آن."""

    key: str
    label: str
    value: str
    raw: float | None
    column: str
    hint: str = ""
    #: جهت تغییر نسبت به دورهٔ قبل: ``up`` / ``down`` / ``""``.
    direction: str = ""
    change: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Insight:
    """یک بینش — متن کوتاه به‌همراه شاهد عددی."""

    key: str
    title: str
    body: str
    severity: str = "info"
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Point:
    label: str
    value: float

    def as_dict(self) -> dict:
        return {"label": self.label, "value": self.value}


@dataclass
class Series:
    """یک سری زمانی یا دسته‌بندی — برای نمودار و جدول."""

    key: str
    title: str
    kind: str                     #: ``line`` یا ``bar``
    points: list[Point] = field(default_factory=list)
    unit: str = ""
    #: دلیل خالی بودن سری، اگر خالی باشد.
    empty_reason: str = ""
    #: توضیح روش ساخت سری — مثلاً اینکه سطل ناقص انتهایی چرا در نمودار
    #: نیامده. بدون این توضیح، کاربر تفاوت نمودار با جدول را نمی‌فهمد.
    note: str = ""

    @property
    def total(self) -> float:
        return float(sum(point.value for point in self.points))

    def as_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "kind": self.kind,
            "unit": self.unit, "empty_reason": self.empty_reason,
            "note": self.note, "total": self.total,
            "points": [point.as_dict() for point in self.points],
        }


@dataclass
class Anomaly:
    column: str
    row: int
    value: float
    method: str
    score: float
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Breakdown:
    """تفکیک یک بعد — جدول «سهم هر گروه».

    ``dropped`` شمار سطرهایی است که مقدارشان عددی بود ولی گروه نداشتند (سلول
    دسته خالی). این سطرها نمی‌توانند به هیچ گروهی نسبت داده شوند، پس از
    جمع گروه‌ها بیرون می‌مانند — و *همین* به کاربر گفته می‌شود. اگر اعلام
    نشود، جمع گروه‌ها از جمع کل کمتر می‌شود و کاربر فکر می‌کند عددی گم شده.
    """

    dimension: str
    metric: str
    rows: list[dict] = field(default_factory=list)
    total: float = 0.0
    dropped: int = 0

    def as_dict(self) -> dict:
        return {
            "dimension": self.dimension, "metric": self.metric,
            "total": self.total, "rows": list(self.rows),
            "dropped": self.dropped,
        }


@dataclass
class Analysis:
    """خروجی کامل تحلیل یک جدول."""

    kpis: list[Kpi] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    breakdowns: list[Breakdown] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    correlation: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    #: ستون‌های انتخاب‌شده به‌عنوان محور تحلیل.
    primary_metric: str = ""
    primary_dimension: str = ""
    date_column: str = ""

    def series_by_key(self, key: str) -> Series | None:
        for item in self.series:
            if item.key == key:
                return item
        return None

    def as_dict(self) -> dict:
        return {
            "kpis": [item.as_dict() for item in self.kpis],
            "insights": [item.as_dict() for item in self.insights],
            "series": [item.as_dict() for item in self.series],
            "breakdowns": [item.as_dict() for item in self.breakdowns],
            "anomalies": [item.as_dict() for item in self.anomalies],
            "correlation": dict(self.correlation),
            "notes": list(self.notes),
            "primary_metric": self.primary_metric,
            "primary_dimension": self.primary_dimension,
            "date_column": self.date_column,
        }


# ------------------------------------------------------------------ کمک‌ها
def _numeric(frame: pd.DataFrame, name: str) -> pd.Series:
    """یک ستون به‌صورت عددی، حتی اگر متن ذخیره شده باشد."""
    from .ingest.cells import parse_number

    if name not in frame.columns:
        return pd.Series(dtype="float64")
    series = frame[name]
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    return pd.to_numeric(series.map(parse_number), errors="coerce")


def _safe_ratio(part: float, whole: float) -> float | None:
    if not whole:
        return None
    return part / whole


def range_split(dates: pd.Series):
    """نقطهٔ تقسیم بازهٔ تاریخی — میانهٔ *زمانی*، نه میانهٔ شمار ردیف.

    «نیمهٔ اول و دوم بازه» یعنی نیمهٔ نخست و دومِ فاصلهٔ میان نخستین و آخرین
    تاریخ، نه نیمهٔ نخست و دومِ فهرست ردیف‌ها. تفاوتشان وقتی بیرون می‌زند که
    تاریخ‌ها نامنظم پخش شده باشند: تقسیم بر شمار ردیف، دو نیمهٔ *نابرابر از
    نظر زمان* می‌سازد و عددی می‌دهد که با نمودار روند نمی‌خواند.

    خروجی ``None`` یعنی بازه‌ای برای تقسیم وجود ندارد (همهٔ تاریخ‌ها یکی، یا
    هیچ تاریخ معتبری نیست).
    """
    clean = pd.Series(dates).dropna()
    if clean.empty:
        return None
    low, high = clean.min(), clean.max()
    if low == high:
        return None
    return low + (high - low) / 2


def period_growth(dates: pd.Series,
                  values: pd.Series) -> tuple[float, float, float] | None:
    """رشد بین دو نیمهٔ بازهٔ تاریخی — ``(نیمهٔ دوم, نیمهٔ اول, نسبت)``.

    این تابع **تنها** مرجع محاسبهٔ رشد دوره‌ای است. پیش از این، سه جای مختلف
    هر کدام نیمه‌ها را جور دیگری می‌بریدند (یکی بر حسب شمار سطل‌های نمودار،
    یکی بر حسب شمار ردیف) و نتیجه این بود که کارت شاخص «۳٫۴٪ کاهش» و بینش
    «۴٫۳٪ افزایش» را برای یک ادعای واحد نشان می‌دادند.
    """
    table = pd.DataFrame({"date": pd.Series(list(dates)),
                          "value": pd.Series(list(values))}).dropna()
    if len(table) < MIN_SAMPLES:
        return None
    split = range_split(table["date"])
    if split is None:
        return None
    previous = float(table.loc[table["date"] < split, "value"].sum())
    recent = float(table.loc[table["date"] >= split, "value"].sum())
    if previous == 0:
        return None
    return recent, previous, (recent - previous) / abs(previous)


def _trend_series(frame: pd.DataFrame, date_column: str,
                  metric: str) -> Series:
    """سری زمانی متریک روی ستون تاریخ، گروه‌بندی‌شده بر اساس بازه."""
    from .ingest.cells import parse_date

    dates = frame[date_column].map(parse_date) if date_column else pd.Series(dtype=object)
    values = _numeric(frame, metric)
    clean = pd.DataFrame({"date": dates, "value": values}).dropna()
    if len(clean) < TREND_MIN_POINTS:
        return Series(
            key="trend", title=f"روند {metric}", kind="line", unit=metric,
            empty_reason=(
                f"برای نمودار روند حداقل {TREND_MIN_POINTS} نقطهٔ تاریخ‌دار لازم "
                "است و در این جدول کمتر است."))
    #: ``parse_date`` تاریخ ساده برمی‌گرداند، ولی گروه‌بندی بازه‌ای pandas به
    #: نوع datetime خودش نیاز دارد. تبدیل اینجا انجام می‌شود تا تجمیع ماه/هفته
    #: ممکن شود.
    clean["date"] = pd.to_datetime(clean["date"], errors="coerce")
    clean = clean.dropna(subset=["date"]).sort_values("date")
    if len(clean) < TREND_MIN_POINTS:
        return Series(
            key="trend", title=f"روند {metric}", kind="line", unit=metric,
            empty_reason="تاریخ‌های معتبر کافی برای ساخت روند وجود ندارد.")
    span_days = max(1, (clean["date"].max() - clean["date"].min()).days)
    if span_days <= 45:
        width, unit = 1, "روز"
    elif span_days <= 400:
        width, unit = 7, "هفته"
    else:
        #: نام واحد دقیقاً همان چیزی است که اجرا می‌شود: سطل ۳۰ روزه، نه ماه
        #: تقویمی. «ماه» گفتن وقتی مرزها تقویمی نیستند، ادعای نادرست است.
        width, unit = 30, "بازهٔ ۳۰روزه"

    #: سطل‌ها از نخستین تاریخِ داده شمرده می‌شوند و نه از تقویم. با تفکیک
    #: تقویمی (هفتهٔ شنبه‌محور یا ماه میلادی), نخستین و آخرین سطل تقریباً همیشه
    #: ناقص می‌شدند: جمع کمتری داشتند و مثل «افت فروش» در انتهای نمودار دیده
    #: می‌شدند. با شمارش از ابتدای داده, تنها سطل انتهایی می‌تواند ناقص باشد.
    start = clean["date"].min()
    offsets = (clean["date"] - start).map(lambda value: value.days)
    bucket = offsets // width
    totals = clean.assign(bucket=bucket).groupby("bucket")["value"].sum()

    total_days = span_days + 1
    full_buckets = total_days // width
    trimmed = False
    if total_days % width and full_buckets >= TREND_MIN_POINTS:
        totals = totals[totals.index < full_buckets]
        trimmed = True

    from .labels import fa_date_label
    points = [Point(label=fa_date_label(start + datetime.timedelta(
                        days=int(index) * width)),
                    value=float(value))
              for index, value in totals.items()]
    note = ""
    if trimmed:
        note = (f"سطل انتهایی کمتر از یک {unit} کامل روز داشت و در نمودار "
                f"نیامده است، چون جمعِ بازهٔ ناقص با بقیهٔ سطل‌ها قابل مقایسه "
                f"نیست. شاخص‌های بالای صفحه همهٔ سطرها را در بر می‌گیرند.")
    return Series(key="trend", title=f"روند {metric}", kind="line",
                  points=points, unit=unit, note=note)


def _breakdown(frame: pd.DataFrame, dimension: str, metric: str,
               limit: int = 12) -> Breakdown:
    """تفکیک متریک بر حسب یک بعد، با سهم هر گروه."""
    values = _numeric(frame, metric)
    labels = frame[dimension].map(lambda value: str(value).strip() if pd.notna(value) else "")
    table = pd.DataFrame({"label": labels, "value": values}).dropna()
    unlabelled = int((table["label"] == "").sum())
    table = table[table["label"] != ""]
    if table.empty:
        return Breakdown(dimension=dimension, metric=metric,
                         dropped=unlabelled)
    grouped = table.groupby("label")["value"].sum().sort_values(ascending=False)
    total = float(grouped.sum())
    rows: list[dict] = []
    for label, value in grouped.head(limit).items():
        share = _safe_ratio(float(value), total)
        rows.append({
            "label": str(label), "value": float(value),
            "share": share if share is not None else None,
            "share_text": fa_percent(share) if share is not None else "—",
            "value_text": fa_compact(value),
        })
    return Breakdown(dimension=dimension, metric=metric, rows=rows,
                     total=total, dropped=unlabelled)


# ------------------------------------------------------------------ ناهنجاری
def detect_anomalies(frame: pd.DataFrame, profile: Profile,
                     limit: int = 40) -> list[Anomaly]:
    """ناهنجاری‌های ستون‌های متریک با دو روش، و *دلیل* هر مورد.

    دو روش با هم به‌کار می‌روند نه یکی: IQR به توزیع نامتقارن حساس نیست ولی
    روی دادهٔ خیلی چوله پرت‌های واقعی را نمی‌بیند؛ Z-score برعکس. مقداری که
    هر دو روش تأییدش کنند اول نمایش داده می‌شود.
    """
    found: list[Anomaly] = []
    for column in profile.metrics():
        series = _numeric(frame, column.name).dropna()
        if len(series) < MIN_SAMPLES:
            continue
        low, high = series.quantile(0.25), series.quantile(0.75)
        spread = float(high - low)
        mean, std = float(series.mean()), float(series.std())
        for index, value in series.items():
            number = float(value)
            reasons: list[str] = []
            if spread > 0:
                lower, upper = float(low) - 1.5 * spread, float(high) + 1.5 * spread
                if number < lower or number > upper:
                    reasons.append("بیرون از بازهٔ ۱٫۵ برابر دامنهٔ میان‌چارکی")
            score = 0.0
            if std > 0:
                score = abs(number - mean) / std
                if score >= Z_LIMIT:
                    reasons.append(f"انحراف بیش از {fa_number(Z_LIMIT)} برابر انحراف معیار")
            if not reasons:
                continue
            method = METHOD_IQR if len(reasons) > 1 else (
                METHOD_IQR if "میان‌چارکی" in reasons[0] else METHOD_Z)
            found.append(Anomaly(
                column=column.name, row=int(index), value=number, method=method,
                score=round(score, 2), reason="؛ ".join(reasons)))
    found.sort(key=lambda item: -item.score)
    return found[:limit]


# ------------------------------------------------------------------ همبستگی
def correlation(frame: pd.DataFrame, profile: Profile, limit: int = 6) -> dict:
    """ماتریس همبستگی پیرسون ستون‌های متریک — فقط اگر حداقل دو متریک باشد."""
    names = [column.name for column in profile.metrics()][:limit]
    if len(names) < 2:
        return {"columns": [], "matrix": [], "note":
                "برای محاسبهٔ همبستگی حداقل دو ستون عددی لازم است."}
    table = pd.DataFrame({name: _numeric(frame, name) for name in names}).dropna()
    if len(table) < MIN_SAMPLES:
        return {"columns": [], "matrix": [], "note":
                f"برای همبستگی معتبر حداقل {MIN_SAMPLES} سطر کامل لازم است و "
                f"در این جدول {fa_number(len(table))} سطر ماند."}
    matrix = table.corr(method="pearson").round(3)
    return {
        "columns": names,
        "matrix": [[None if pd.isna(value) else float(value) for value in row]
                   for row in matrix.values.tolist()],
        "note": "ضریب پیرسون روی سطرهایی که همهٔ ستون‌های انتخابی مقدار دارند.",
    }


# ------------------------------------------------------------------ بینش‌ها
def _concentration(frame: pd.DataFrame, dimension: str, metric: str) -> Insight | None:
    """بینش تمرکز: چه سهمی از متریک در بزرگ‌ترین گروه است."""
    table = _breakdown(frame, dimension, metric, limit=200)
    if not table.rows or table.total == 0:
        return None
    top = table.rows[0]
    share = top["share"]
    if share is None or share < 0.2:
        return None
    return Insight(
        key="concentration", title="تمرکز در یک گروه",
        body=(f"«{top['label']}» با {fa_percent(share)} از کل {metric} "
              f"بزرگ‌ترین سهم را در ستون «{dimension}» دارد."),
        severity="info" if share < 0.5 else "warning",
        evidence={"dimension": dimension, "metric": metric, "label": top["label"],
                  "share": share, "value": top["value"], "total": table.total},
    )


def _trend_insight(growth: tuple[float, float, float] | None,
                   metric: str, date_column: str) -> Insight | None:
    """بینش رشد: مقایسهٔ دو نیمهٔ بازهٔ تاریخی.

    عدد رشد از بیرون می‌آید تا کارت شاخص و این جمله هرگز دو عدد متفاوت
    نگویند؛ محاسبه فقط یک‌جا انجام می‌شود.
    """
    if not date_column or growth is None:
        return None
    recent, previous, ratio = growth
    direction = "افزایش" if ratio >= 0 else "کاهش"
    return Insight(
        key="growth", title="تغییر بین دو نیمهٔ بازه",
        body=(f"{metric} در نیمهٔ دوم بازه نسبت به نیمهٔ اول "
              f"{fa_percent(abs(ratio))} {direction} داشته است."),
        severity="info" if ratio >= 0 else "warning",
        evidence={"metric": metric, "recent": recent, "previous": previous,
                  "ratio": ratio, "date_column": date_column},
    )


def _quality_insight(profile: Profile) -> Insight | None:
    """بینش کیفیت: کدام ستون بیشترین سلول خالی را دارد."""
    if profile.rows == 0:
        return None
    worst = max(profile.columns_profile,
                key=lambda column: column.missing, default=None)
    if worst is None or worst.missing == 0:
        return None
    share = worst.missing / max(1, profile.rows)
    return Insight(
        key="missing", title="بیشترین مقدار خالی",
        body=(f"ستون «{worst.name}» با {fa_number(worst.missing)} سلول خالی "
              f"({fa_percent(share)} از کل سطرها) بیشترین مقدار ازدست‌رفته را دارد."),
        severity="warning" if share > 0.2 else "info",
        evidence={"column": worst.name, "missing": worst.missing, "share": share},
    )


def _duplicate_insight(profile: Profile) -> Insight | None:
    if not profile.duplicates:
        return None
    share = profile.duplicates / max(1, profile.rows)
    return Insight(
        key="duplicates", title="ردیف تکراری در جدول پاک‌شده باقی مانده",
        body=(f"{fa_number(profile.duplicates)} ردیف تکراری "
              f"({fa_percent(share)}) در جدول هست. اگر هنوز در تحلیل است، "
              "جمع‌ها را بزرگ‌تر نشان می‌دهد."),
        severity="warning",
        evidence={"duplicates": profile.duplicates, "share": share},
    )


def _anomaly_insight(anomalies: list[Anomaly], metric: str) -> Insight | None:
    if not anomalies:
        return None
    top = anomalies[0]
    return Insight(
        key="anomaly", title="مقدار دور از معمول",
        body=(f"در ستون «{top.column}» سطر {fa_number(top.row + 1)} مقدار "
              f"{fa_compact(top.value)} دارد که {top.reason}."),
        severity="warning",
        evidence={"column": top.column, "row": top.row, "value": top.value,
                  "score": top.score, "method": top.method},
    )


def _dimension_insight(frame: pd.DataFrame, dimension: str,
                       metric: str) -> dict | None:
    """توزیع گروه‌ها: آیا یک گروه غالب است و چند گروه سهم ناچیز دارند."""
    table = _breakdown(frame, dimension, metric, limit=500)
    if len(table.rows) < 3 or table.total == 0:
        return None
    small = [row for row in table.rows if (row["share"] or 0) < 0.02]
    return {"groups": len(table.rows), "small": len(small),
            "top": table.rows[0]}


# ------------------------------------------------------------------ دروازه
def analyse(frame: pd.DataFrame, profile: Profile,
            metric: str | None = None, dimension: str | None = None,
            date_column: str | None = None) -> Analysis:
    """تحلیل کامل جدول پاک‌شده.

    انتخاب خودکار محورها از پروفایل می‌آید؛ اگر کاربر محوری را دستی انتخاب
    کرده باشد، همان اولویت می‌گیرد و اعتبارش بررسی می‌شود.
    """
    notes: list[str] = []
    metrics = pick_metrics(profile)
    dimensions = pick_dimensions(profile)
    dates = profile.date_column()

    chosen_metric = metric if metric and metric in frame.columns else (
        metrics[0] if metrics else "")
    chosen_dimension = dimension if dimension and dimension in frame.columns else (
        dimensions[0] if dimensions else "")
    chosen_date = date_column if date_column and date_column in frame.columns else (
        dates.name if dates else "")

    if metric and metric not in frame.columns:
        notes.append(f"ستون «{metric}» در جدول نیست؛ نزدیک‌ترین متریک انتخاب شد.")
    if dimension and dimension not in frame.columns:
        notes.append(f"ستون «{dimension}» در جدول نیست؛ نزدیک‌ترین بعد انتخاب شد.")
    if not chosen_metric:
        notes.append(
            "هیچ ستون عددی مناسبی برای متریک پیدا نشد؛ کارت‌های شاخص و نمودار "
            "مقدار ساخته نشدند. اگر جدول ستون مبلغ یا تعداد دارد، نوع آن را "
            "بررسی کنید.")
    if not chosen_dimension:
        notes.append(
            "ستون دسته‌بندی مناسبی (منطقه، محصول، مشتری) پیدا نشد؛ نمودار "
            "مقایسهٔ گروه‌ها ساخته نشد.")
    if not chosen_date:
        notes.append(
            "ستون تاریخ پیدا نشد؛ تحلیل روند و مقایسهٔ دوره‌ها انجام نشد.")

    analysis = Analysis(primary_metric=chosen_metric,
                        primary_dimension=chosen_dimension,
                        date_column=chosen_date)

    values = _numeric(frame, chosen_metric) if chosen_metric else pd.Series(dtype="float64")
    #: رشد دوره‌ای یک‌بار اینجا حساب می‌شود و هم کارت شاخص و هم بینش از همین
    #: عدد تغذیه می‌شوند.
    growth = None
    if chosen_metric and chosen_date:
        from .ingest.cells import parse_date

        growth = period_growth(frame[chosen_date].map(parse_date), values)

    #: ---------------------------------------------------------- کارت‌ها
    if chosen_metric and values.notna().any():
        total = float(values.sum())
        filled = values.dropna()
        analysis.kpis.append(Kpi(
            key="total", label=f"جمع {chosen_metric}", value=fa_compact(total),
            raw=total, column=chosen_metric, hint="مجموع همهٔ سطرها"))
        analysis.kpis.append(Kpi(
            key="mean", label=f"میانگین {chosen_metric}",
            value=fa_compact(float(filled.mean())), raw=float(filled.mean()),
            column=chosen_metric, hint="میانگین مقدارهای پرشده"))
        analysis.kpis.append(Kpi(
            key="max", label=f"بیشترین {chosen_metric}",
            value=fa_compact(float(filled.max())), raw=float(filled.max()),
            column=chosen_metric, hint="بزرگ‌ترین مقدار در جدول"))
        analysis.kpis.append(Kpi(
            key="median", label=f"میانهٔ {chosen_metric}",
            value=fa_compact(float(filled.median())), raw=float(filled.median()),
            column=chosen_metric, hint="مقدار وسط؛ نسبت به پرت‌ها مقاوم است"))
    else:
        analysis.kpis.append(Kpi(
            key="rows", label="تعداد ردیف", value=fa_number(profile.rows),
            raw=float(profile.rows), column="", hint="سطرهای جدول پاک‌شده"))

    analysis.kpis.append(Kpi(
        key="groups", label="تعداد گروه در بعد اصلی",
        value=fa_number(len(set(frame[chosen_dimension].dropna().astype(str))))
        if chosen_dimension else "—",
        raw=float(frame[chosen_dimension].nunique()) if chosen_dimension else None,
        column=chosen_dimension or "", hint="شمار مقدارهای متمایز"))
    analysis.kpis.append(Kpi(
        key="quality", label="امتیاز کیفیت داده",
        value=fa_number(profile.quality.get("score", 0), decimals=1),
        raw=float(profile.quality.get("score", 0)), column="",
        hint=profile.quality.get("label", "")))

    #: ---------------------------------------------------------- روند
    if chosen_metric and chosen_date:
        trend = _trend_series(frame, chosen_date, chosen_metric)
        analysis.series.append(trend)
        if growth:
            recent, previous, ratio = growth
            for kpi in analysis.kpis:
                if kpi.key == "total":
                    kpi.change = fa_percent(abs(ratio))
                    kpi.direction = "up" if ratio >= 0 else "down"
                    kpi.hint = ("تغییر نیمهٔ دوم بازه نسبت به نیمهٔ اول: "
                                f"{fa_percent(abs(ratio))} "
                                f"{'افزایش' if ratio >= 0 else 'کاهش'}")
                    break
    elif chosen_metric:
        analysis.series.append(Series(
            key="trend", title=f"روند {chosen_metric}", kind="line",
            empty_reason="ستون تاریخ در جدول نیست، پس روند قابل محاسبه نیست."))

    #: ---------------------------------------------------------- تفکیک‌ها
    if chosen_metric and chosen_dimension:
        main = _breakdown(frame, chosen_dimension, chosen_metric)
        analysis.breakdowns.append(main)
        if main.rows:
            analysis.series.append(Series(
                key="breakdown", title=f"{chosen_metric} بر حسب {chosen_dimension}",
                kind="bar", unit=chosen_metric,
                points=[Point(label=row["label"], value=row["value"])
                        for row in main.rows],
                empty_reason="" if main.rows else "داده‌ای برای تفکیک نبود."))

    #: ---------------------------------------------------------- توزیع
    if chosen_metric and len(values.dropna()) >= MIN_SAMPLES:
        filled = values.dropna()
        buckets = pd.cut(filled, bins=min(12, max(4, int(math.sqrt(len(filled))))))
        counts = buckets.value_counts().sort_index()
        #: ``pd.cut`` لبهٔ نخستین بازه را کمی پایین‌تر از کمترین مقدار باز
        #: می‌کند تا مطمئن شود همهٔ داده در بازه‌ها جا می‌گیرد. روی ستون مبلغ،
        #: این یعنی محور توزیع با «−۱٬۴۱۹٬۵۴۱» شروع می‌شود — عددی که در داده
        #: وجود ندارد و ادعای نادرست است. لبه‌های بیرونی به محدودهٔ واقعی داده
        #: چسبانده می‌شوند.
        edges = list(counts.items())
        low, high = float(filled.min()), float(filled.max())
        points: list[Point] = []
        for position, (interval, count) in enumerate(edges):
            left = low if position == 0 else float(interval.left)
            right = high if position == len(edges) - 1 else float(interval.right)
            points.append(Point(label=_bucket_label(left, right),
                                value=float(count)))
        analysis.series.append(Series(
            key="distribution", title=f"توزیع {chosen_metric}", kind="bar",
            unit="تعداد سطر", points=points))

    #: ---------------------------------------------------------- ناهنجاری
    analysis.anomalies = detect_anomalies(frame, profile)
    analysis.correlation = correlation(frame, profile)

    #: ---------------------------------------------------------- بینش‌ها
    insight_builders = []
    if chosen_metric and chosen_dimension:
        insight_builders.append(lambda: _concentration(frame, chosen_dimension,
                                                       chosen_metric))
    if chosen_metric and chosen_date:
        insight_builders.append(lambda: _trend_insight(growth, chosen_metric,
                                                       chosen_date))
    insight_builders.append(lambda: _quality_insight(profile))
    insight_builders.append(lambda: _duplicate_insight(profile))
    insight_builders.append(lambda: _anomaly_insight(analysis.anomalies,
                                                     chosen_metric))
    for builder in insight_builders:
        try:
            insight = builder()
        except Exception:                      # noqa: BLE001 — بینش نباید صفحه را بشکند
            continue
        if insight is not None:
            analysis.insights.append(insight)

    if chosen_metric and chosen_dimension:
        spread = _dimension_insight(frame, chosen_dimension, chosen_metric)
        if spread and spread["small"]:
            analysis.insights.append(Insight(
                key="long_tail", title="گروه‌های کم‌سهم",
                body=(f"از {fa_number(spread['groups'])} گروه در ستون "
                      f"«{chosen_dimension}»، {fa_number(spread['small'])} گروه "
                      "کمتر از ۲٪ سهم دارند."),
                severity="info",
                evidence={"groups": spread["groups"], "small": spread["small"]}))

    analysis.notes = notes
    return analysis


def _bucket_label(left: float, right: float) -> str:
    """برچسب خوانا برای بازهٔ هیستوگرام — با همان قالب اعداد بقیهٔ صفحه."""
    return f"{fa_number(left)} تا {fa_number(right)}"


def movers(frame: pd.DataFrame, metric: str, date_column: str,
           dimension: str, limit: int = 5) -> dict:
    """بیشترین رشد و بیشترین کاهش گروه‌ها بین دو نیمهٔ بازهٔ تاریخی.

    برای هر گروه، جمع نیمهٔ اول و دوم حساب و اختلاف نسبی گرفته می‌شود. گروهی
    که در نیمهٔ اول مقداری نداشته باشد از مقایسه کنار می‌رود — تقسیم بر صفر
    «رشد بی‌نهایت» می‌سازد که بینش نیست، خطاست.
    """
    from .ingest.cells import parse_date

    if not (metric and date_column and dimension):
        return {"gainers": [], "losers": [], "reason": "ستون‌های لازم موجود نیست."}
    dates = frame[date_column].map(parse_date)
    table = pd.DataFrame({
        "date": dates, "group": frame[dimension].astype(str),
        "value": _numeric(frame, metric),
    }).dropna()
    if len(table) < MIN_SAMPLES * 2:
        return {"gainers": [], "losers": [],
                "reason": "برای مقایسهٔ دوره‌ها دادهٔ کافی نیست."}

    table = table.sort_values("date")
    #: همان نقطهٔ تقسیمی که رشد کل و بینش دوره‌ای از آن استفاده می‌کنند، تا
    #: «بیشترین رشد» با عدد کل یک تعریف داشته باشد.
    midpoint = range_split(table["date"])
    if midpoint is None:
        return {"gainers": [], "losers": [],
                "reason": "بازهٔ تاریخی برای تقسیم کافی نیست."}
    first = table[table["date"] < midpoint].groupby("group")["value"].sum()
    second = table[table["date"] >= midpoint].groupby("group")["value"].sum()

    rows: list[dict] = []
    for group in set(first.index) | set(second.index):
        before = float(first.get(group, 0.0))
        after = float(second.get(group, 0.0))
        if before == 0 or after == 0:
            continue
        rows.append({
            "label": str(group), "before": before, "after": after,
            "change": (after - before) / abs(before),
            "before_text": fa_compact(before), "after_text": fa_compact(after),
        })
    if not rows:
        return {"gainers": [], "losers": [],
                "reason": "هیچ گروهی در هر دو نیمهٔ بازه مقدار نداشت."}
    rows.sort(key=lambda item: item["change"])
    return {"gainers": list(reversed(rows[-limit:])), "losers": rows[:limit],
            "reason": ""}
